"""The FROZEN evaluator for the incident router: dataset loading, grading, running.

The hill-climber may change configs (prompt sections, tools, model, effort).
It may not change this file or data/incidents.jsonl. `fingerprint()` hashes
both so hillclimb.py can refuse to continue if either changes mid-climb; that is
autoresearch's "prepare.py is read-only" rule, enforced instead of requested.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ainative_kit import LLMClient

from incident_router import cost_usd, route
from make_incidents import load_incidents
from sim_model import make_sim_client

HERE = Path(__file__).parent
DATA = HERE / "data" / "incidents.jsonl"

ClientFactory = Callable[[dict[str, Any], int], LLMClient]


def sim_factory(config: dict[str, Any], seed: int) -> LLMClient:
    return make_sim_client(effort=config.get("effort", "medium"), seed=seed)


def grade(predicted: str | None, label: str) -> int:
    """Binary exact-match grader. No partial credit: a wrong page is a wrong page."""
    return int(predicted == label)


@dataclass
class RunResult:
    name: str
    split: str
    ids: list[str]
    clusters: list[str]
    per_repeat: list[list[int]]          # per_repeat[r][i]: score of item i on repeat r
    predictions: list[list[str | None]]  # same shape
    cost_usd: float = 0.0
    calls: int = 0
    truncated: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def item_scores(self) -> list[float]:
        """Per-item mean over repeats: the unit every statistic in stats.py uses."""
        k = len(self.per_repeat)
        return [sum(rep[i] for rep in self.per_repeat) / k for i in range(len(self.ids))]

    @property
    def accuracy(self) -> float:
        s = self.item_scores
        return sum(s) / len(s)

    @property
    def run_means(self) -> list[float]:
        return [sum(rep) / len(rep) for rep in self.per_repeat]

    @property
    def cost_per_item(self) -> float:
        return self.cost_usd / (len(self.ids) * len(self.per_repeat))

    def failures(self, items: list[dict]) -> list[dict]:
        """Items failed on a majority of repeats, for error analysis."""
        by_id = {it["id"]: it for it in items}
        return [by_id[i] for i, s in zip(self.ids, self.item_scores) if s < 0.5]


def load_split(split: str, path: str | Path | None = None) -> list[dict]:
    return [r for r in load_incidents(path or DATA) if split == "all" or r["split"] == split]


def sim_factory_for(items: list[dict]) -> ClientFactory:
    """A simulated-model factory bound to a non-default dataset."""
    return lambda config, seed: make_sim_client(effort=config.get("effort", "medium"), seed=seed, items=items)


def evaluate(config: dict[str, Any], items: list[dict], repeats: int = 3, seed: int = 0,
             client_factory: ClientFactory = sim_factory, split: str = "?") -> RunResult:
    """Run `config` over `items`, `repeats` times, each repeat with its own seed."""
    res = RunResult(config.get("name", "?"), split, [it["id"] for it in items],
                    [it["cluster"] for it in items], [], [])
    for r in range(repeats):
        client = client_factory(config, seed * 1000 + r)
        scores, preds = [], []
        for it in items:
            out = route(client, config, it["text"])
            res.cost_usd += cost_usd(config.get("model", ""), out.input_tokens, out.output_tokens)
            res.calls += out.calls
            res.truncated += int(out.truncated)
            preds.append(out.team)
            scores.append(grade(out.team, it["label"]))
        res.per_repeat.append(scores)
        res.predictions.append(preds)
    return res


def fingerprint(paths: list[Path] | None = None) -> str:
    """sha256 over the grader source and the dataset. Changes => the climb is void."""
    h = hashlib.sha256()
    for p in paths or [Path(__file__), DATA]:
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:16]


def by_tag(result: RunResult, items: list[dict]) -> dict[str, float]:
    """Accuracy per difficulty tag: the error-analysis view that suggests the next hypothesis."""
    tags = {it["id"]: it["tag"] for it in items}
    acc: dict[str, list[float]] = {}
    for i, s in zip(result.ids, result.item_scores):
        acc.setdefault(tags[i], []).append(s)
    return {t: sum(v) / len(v) for t, v in sorted(acc.items())}


if __name__ == "__main__":
    from incident_router import DEFAULT_CONFIG
    from stats import clustered_se, mean_se

    dev = load_split("dev")
    r = evaluate(DEFAULT_CONFIG, dev, repeats=3, split="dev")
    naive, clus = mean_se(r.item_scores), clustered_se(r.item_scores, r.clusters)
    print(f"{r.name} on dev: acc {naive.fmt()}  clustered {clus.fmt()}  cost/item ${r.cost_per_item:.5f}")
    for tag, a in by_tag(r, dev).items():
        print(f"  {tag:10s} {a:.2f}")
