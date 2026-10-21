"""Audit an agent's tool manifest for the lethal trifecta (Willison, 2025).

The trifecta is a property of the *union* of tools in one context, not of any single tool:
  - private:   the tool can read data the attacker should not see
  - untrusted: the tool returns content an attacker can influence (issues, web pages, email, logs)
  - exfil:     the tool can move data to somewhere an attacker can read it

Manifest format (JSON):
  {"agent": "name",
   "servers": [{"name": "github-mcp", "tools": [
       {"name": "get_issue", "legs": ["untrusted"], "note": "public issue bodies"},
       {"name": "create_pr", "legs": ["exfil"], "mitigation": "..."}]}]}

A tool's `mitigation` field, if present, removes it from a leg only when it names a
*structural* control (one of STRUCTURAL_MITIGATIONS). "The prompt tells it not to" does not count.

Run: python trifecta_audit.py data/manifests/coding_agent.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

LEGS = ("private", "untrusted", "exfil")
STRUCTURAL_MITIGATIONS = {
    "egress_allowlist",       # outbound proxy, default deny, capability-scoped
    "human_approval",         # a human approves each call, out of band of the model
    "no_network",             # the tool's sandbox has no route out
    "credential_proxy",       # secrets held outside the sandbox; the agent never sees them
    "trusted_source_only",    # input is restricted to authors you trust (e.g. org members)
    "quarantined_llm",        # untrusted text is read by a tool-less LLM with constrained output
}


@dataclass
class ToolEntry:
    server: str
    name: str
    legs: set[str]
    mitigation: dict[str, str] = field(default_factory=dict)  # leg -> mitigation kind

    @property
    def qualified(self) -> str:
        return f"{self.server}.{self.name}"

    def effective_legs(self) -> set[str]:
        return {leg for leg in self.legs if self.mitigation.get(leg) not in STRUCTURAL_MITIGATIONS}


@dataclass
class AuditReport:
    agent: str
    providers: dict[str, list[str]]           # leg -> tools that provide it (after mitigation)
    mitigated: dict[str, list[str]]           # leg -> tools whose leg was structurally removed
    single_tool_trifectas: list[str]          # tools that are all three legs on their own
    cross_server: bool                        # trifecta only exists because servers were mixed
    problems: list[str]                       # manifest errors (unknown legs, bad mitigations)

    @property
    def has_trifecta(self) -> bool:
        return all(self.providers[leg] for leg in LEGS)

    def cheapest_leg(self) -> str | None:
        """The leg with the fewest providers. Ties go to exfil, then untrusted (outbound is usually cheapest)."""
        if not self.has_trifecta:
            return None
        return min(LEGS, key=lambda leg: (len(self.providers[leg]), LEGS.index(leg) * -1))

    def render(self) -> str:
        lines = [f"agent: {self.agent}"]
        for leg in LEGS:
            got = ", ".join(self.providers[leg]) or "-"
            lines.append(f"  {leg:9} {got}")
            if self.mitigated[leg]:
                lines.append(f"  {'':9} (mitigated: {', '.join(self.mitigated[leg])})")
        if self.has_trifecta:
            lines.append("VERDICT: LETHAL TRIFECTA PRESENT")
            if self.single_tool_trifectas:
                lines.append(f"  single-tool trifecta: {', '.join(self.single_tool_trifectas)}")
            if self.cross_server:
                lines.append("  arises only from mixing servers: no single vendor can fix this")
            leg = self.cheapest_leg()
            lines.append(f"  cheapest leg to cut: {leg} ({len(self.providers[leg])} tool(s))")
        else:
            missing = [leg for leg in LEGS if not self.providers[leg]]
            lines.append(f"VERDICT: no trifecta (missing: {', '.join(missing)})")
        for p in self.problems:
            lines.append(f"  WARNING: {p}")
        return "\n".join(lines)


def parse_manifest(data: dict) -> tuple[str, list[ToolEntry], list[str]]:
    problems: list[str] = []
    tools: list[ToolEntry] = []
    for server in data.get("servers", []):
        for t in server.get("tools", []):
            legs = set(t.get("legs", []))
            unknown = legs - set(LEGS)
            if unknown:
                problems.append(f"{server['name']}.{t['name']}: unknown legs {sorted(unknown)}")
            if "legs" not in t:
                problems.append(f"{server['name']}.{t['name']}: unlabeled (treated as all three legs)")
                legs = set(LEGS)
            mitigation = dict(t.get("mitigation", {}))
            for leg, kind in mitigation.items():
                if kind not in STRUCTURAL_MITIGATIONS:
                    problems.append(
                        f"{server['name']}.{t['name']}: mitigation {kind!r} for {leg} is not structural; ignored"
                    )
            tools.append(ToolEntry(server["name"], t["name"], legs & set(LEGS), mitigation))
    return data.get("agent", "unnamed"), tools, problems


def audit(data: dict) -> AuditReport:
    agent, tools, problems = parse_manifest(data)
    providers = {leg: [t.qualified for t in tools if leg in t.effective_legs()] for leg in LEGS}
    mitigated = {
        leg: [t.qualified for t in tools if leg in t.legs and leg not in t.effective_legs()] for leg in LEGS
    }
    single = [t.qualified for t in tools if t.effective_legs() == set(LEGS)]

    def server_has_trifecta(name: str) -> bool:
        legs = set().union(*(t.effective_legs() for t in tools if t.server == name)) if tools else set()
        return legs >= set(LEGS)

    servers = {t.server for t in tools}
    full = all(providers[leg] for leg in LEGS)
    cross = full and not any(server_has_trifecta(s) for s in servers)
    return AuditReport(agent, providers, mitigated, single, cross, problems)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python trifecta_audit.py MANIFEST.json")
        return 2
    report = audit(json.loads(Path(argv[1]).read_text()))
    print(report.render())
    return 1 if report.has_trifecta else 0  # nonzero exit so CI can gate on it


if __name__ == "__main__":
    sys.exit(main(sys.argv))
