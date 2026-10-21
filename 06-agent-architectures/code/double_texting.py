"""Double-texting policy simulator: a user sends a new message while a run is in flight.

Policies (names follow LangGraph/LangSmith Deployment's multitask strategies):
  reject     try-lock, fail fast: the new message is refused while a run is active
  enqueue    per-thread FIFO, a single writer per thread: the new run starts after the current one
  interrupt  preempt at a step boundary, keep committed progress, continue with the new input
  rollback   abort the current run, revert the thread to before its input, start fresh
  adaptive   course synthesis: rollback if the run has not touched the world yet, else interrupt
  concurrent the broken baseline: two runs write the same thread at once (optionally with OCC)

The run commits one checkpoint per step (like a graph checkpointer). The simulator is
discrete-time and deterministic, so each policy's failure mode can be asserted in a test:
  - interrupt can leave a tool_use with no tool_result (the API rejects that transcript)
  - rollback reverts YOUR state, not the world: a sent email stays sent
  - concurrent runs interleave transcripts; OCC turns that into a detectable conflict

Run:  python double_texting.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

POLICIES = ("reject", "enqueue", "interrupt", "rollback", "adaptive", "concurrent")


@dataclass(frozen=True)
class Step:
    kind: str                       # "think" | "tool_use" | "tool_result" | "reply"
    name: str = ""
    side_effect: str | None = None  # an external effect performed by this step, e.g. "email:cust-17"


def default_planner(text: str) -> list[Step]:
    """Every run: look something up, maybe act on the world, reply."""
    steps = [Step("think"), Step("tool_use", "lookup_order"), Step("tool_result", "lookup_order")]
    if "refund" in text:
        steps += [Step("tool_use", "issue_refund", side_effect=f"refund:{re.search(r'\d+', text).group()}"),
                  Step("tool_result", "issue_refund")]
    return steps + [Step("reply")]


@dataclass
class Thread:
    messages: list[str] = field(default_factory=list)
    version: int = 0
    history: dict[int, list[str]] = field(default_factory=lambda: {0: []})   # version -> snapshot

    def commit(self, entry: str, expected_version: int | None = None) -> int:
        if expected_version is not None and expected_version != self.version:
            raise ConflictError(f"expected v{expected_version}, thread at v{self.version}")
        self.messages.append(entry)
        self.version += 1
        self.history[self.version] = list(self.messages)
        return self.version

    def revert_to(self, version: int) -> None:
        self.messages = list(self.history[version])
        self.version += 1                       # a revert is a new version, never a rewind of the counter
        self.history[self.version] = list(self.messages)


class ConflictError(Exception):
    pass


@dataclass
class Run:
    rid: int
    text: str
    steps: list[Step]
    base_version: int = 0           # thread version before this run's input was committed
    seen_version: int = 0           # last version this run observed (for OCC)
    pc: int = 0
    status: str = "pending"
    effects: list[str] = field(default_factory=list)


@dataclass
class SimResult:
    policy: str
    messages: list[str]
    runs: list[Run]
    world: list[str]
    warnings: list[str]
    transcript_errors: list[str]


def validate_transcript(messages: list[str]) -> list[str]:
    """The API's rule: every tool_use must be immediately followed by its tool_result."""
    errors = []
    for i, m in enumerate(messages):
        if m.startswith("tool_use:"):
            call = m.split(":", 1)[1]                       # "r1:issue_refund"
            nxt = messages[i + 1] if i + 1 < len(messages) else ""
            if not nxt.startswith(f"tool_result:{call}"):
                errors.append(f"message {i}: {m} not followed by its tool_result (got {nxt or 'end'!r})")
    return errors


def simulate(policy: str, arrivals: list[tuple[int, str]], *, planner: Callable[[str], list[Step]] = default_planner,
             occ: bool = False, patch_dangling: bool = True, max_ticks: int = 100) -> SimResult:
    if policy not in POLICIES:
        raise ValueError(policy)
    th, world, warnings = Thread(), [], []
    runs: list[Run] = []
    active: list[Run] = []
    queue: list[Run] = []
    pending = sorted(arrivals)

    def start(run: Run) -> None:
        run.base_version = th.version
        run.seen_version = th.commit(f"user:r{run.rid}:{run.text}")
        run.status = "running"
        active.append(run)

    def step(run: Run) -> None:
        s = run.steps[run.pc]
        entry = {"think": None, "reply": f"assistant:r{run.rid}:reply",
                 "tool_use": f"tool_use:r{run.rid}:{s.name}", "tool_result": f"tool_result:r{run.rid}:{s.name}"}[s.kind]
        if entry:
            try:
                run.seen_version = th.commit(entry, run.seen_version if occ else None)
            except ConflictError as e:
                run.status = "aborted_conflict"
                active.remove(run)
                warnings.append(f"r{run.rid}: OCC conflict ({e}); run aborted, its partial writes remain")
                warnings.extend(f"r{run.rid}: aborted after side effect {eff!r}; compensation needed" for eff in run.effects)
                return
        if s.side_effect:
            world.append(s.side_effect)
            run.effects.append(s.side_effect)
        run.pc += 1
        if run.pc == len(run.steps):
            run.status = "completed"
            active.remove(run)

    def cancel_current(how: str) -> None:
        cur = active.pop()
        cur.status = how
        if how == "interrupted" and patch_dangling and th.messages and th.messages[-1].startswith("tool_use:"):
            ran = cur.steps[cur.pc - 1].side_effect
            # Tell the model the truth: if the tool already acted on the world, it was NOT cancelled.
            outcome = "executed-result-not-observed" if ran else "cancelled"
            th.commit(th.messages[-1].replace("tool_use:", "tool_result:", 1) + f":{outcome}")
            warnings.append(f"r{cur.rid}: interrupted between tool_use and tool_result; "
                            f"inserted a synthetic '{outcome}' tool_result")
        if how == "rolled_back":
            th.revert_to(cur.base_version)
            for eff in cur.effects:
                warnings.append(f"r{cur.rid}: rolled back thread state, but side effect {eff!r} "
                                "already happened in the world; compensation needed")

    for tick in range(max_ticks):
        while pending and pending[0][0] <= tick:
            _, txt = pending.pop(0)
            run = Run(len(runs) + 1, txt, planner(txt))
            runs.append(run)
            busy = bool(active)
            if not busy or policy == "concurrent":
                start(run)
            elif policy == "reject":
                run.status = "rejected"
            elif policy == "enqueue":
                run.status = "queued"
                queue.append(run)
            else:                                   # interrupt | rollback | adaptive
                how = {"interrupt": "interrupted", "rollback": "rolled_back"}.get(policy)
                if how is None:                     # adaptive: rollback is safe only before any side effect
                    how = "interrupted" if active[-1].effects else "rolled_back"
                cancel_current(how)
                start(run)
        for run in list(active):
            step(run)
        if not active and queue:
            start(queue.pop(0))
        if not (active or queue or pending):
            break
    return SimResult(policy, th.messages, runs, world, warnings, validate_transcript(th.messages))


def main() -> None:
    # A refund request, then a correction. The refund tool fires on tick 3.
    for label, t in [("early correction (tick 2, before the refund fires)", 2),
                     ("late correction (tick 4, after the refund fired)", 4)]:
        arrivals = [(0, "please refund order 7731"), (t, "sorry, refund order 7713 instead")]
        print(f"#### {label}")
        for policy in POLICIES:
            r = simulate(policy, arrivals)
            print(f"== {policy:<10} runs={[(x.rid, x.status) for x in r.runs]} world={r.world}")
            for w in r.warnings + r.transcript_errors:
                print("   !", w)
        r = simulate("concurrent", arrivals, occ=True)
        print(f"== concurrent+OCC runs={[(x.rid, x.status) for x in r.runs]} world={r.world}\n")


if __name__ == "__main__":
    main()
