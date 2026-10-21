## Consumer lag triage: <group> on <topic>

- **Alert:** <name, fired at>
- **Lag now / 30m ago / direction:** <n> / <n> / growing | draining | flat
- **Shape:** single_partition (p<n>) | uniform | unassigned | none  (from `lag_summary.py`)
- **Cause (from references/causes.md):** <cause>; confidence high | medium | low
- **Evidence:**
  - <command or query> → <one-line result>
  - <command or query> → <one-line result>
- **Recommended next action (for a human):** <action>, risk: <what could go wrong>
- **Unknowns:** <what you could not check, and why>
