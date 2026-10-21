# 00-orientation code

Stdlib-only Python 3.11+. The one model call (`autonomy_dial.extract_features`) goes through `ainative_kit`.

| File | What it does |
|---|---|
| `selfmeasure_log.py` | Append-only JSONL event log, the fold that enforces the experiment's invariants, and seeded permuted-block assignment |
| `selfmeasure_stats.py` | Summary: estimate-adjusted time ratio, Welch CI on log time, permutation p, rework, perceived ratio, power and minimum detectable effect, selection warnings |
| `selfmeasure.py` | The CLI: `register`, `assign`, `start`, `merge`, `perceive`, `rework`, `abandon`, `status`, `summary` |
| `simulate_ab.py` | Writes a synthetic log with a planted true effect and a planted perception bias, so you can check the analysis |
| `autonomy_dial.py` | `recommend(Task)`: oracle strength × task properties → chat / pair / supervised_agent / loop / scheduled, with guards. Optional model-based feature extraction with a conservative fallback |
| `data/sample_log.jsonl` | **Synthetic** 40-task log (true ratio 1.19, perceived 0.80, seed 7). Not a measurement |

## Run

From the course root:

```bash
.venv/bin/python -m pytest -q 00-orientation/code          # offline, deterministic
```

From this directory:

```bash
# Inspect the synthetic sample
python selfmeasure.py --log data/sample_log.jsonl summary --outcome active
python selfmeasure.py --log data/sample_log.jsonl status

# Regenerate it, or plant your own effect
python simulate_ab.py --out data/sample_log.jsonl --tasks 40 --true-ratio 1.19 --perceived-ratio 0.80

# Autonomy dial (uses the real API if ANTHROPIC_API_KEY is set, otherwise a canned FakeClient reply)
PYTHONPATH=../../shared python autonomy_dial.py "Port 41 consumers to kafka-clients 3.7; the contract suite covers every behaviour"
```

`PYTHONPATH` is only needed if you haven't run `pip install -e .` at the course root.

## Your real experiment

```bash
export SELFMEASURE_SEED="$(openssl rand -hex 16)"   # private; the log stores only its sha256 fingerprint
export SELFMEASURE_LOG=~/selfmeasure.jsonl
python selfmeasure.py register PAY-412 --size M --est 120 --kind bugfix --title "idempotency key collision"
python selfmeasure.py register PAY-415 --size M --est 90 --kind feature --title "webhook retry budget"
python selfmeasure.py assign                          # batch-assign everything pending
python selfmeasure.py start PAY-412
python selfmeasure.py merge PAY-412 --pr "#8812" --active 95
python selfmeasure.py perceive PAY-412 --other 150    # your guess for the other arm, in active minutes
python selfmeasure.py rework PAY-412 --kind fix --minutes 40
python selfmeasure.py summary                          # --outcome active|wall, --rework-days 14
```

Any event takes `--ts` for backfilling, for example `--ts "$(gh pr view 8812 --json mergedAt -q .mergedAt)"`.

## Log format

One JSON object per line, never edited. See [05-measure-yourself.md](../05-measure-yourself.md#the-log-format) for the event types and the invariants `fold()` enforces. These include no re-assignment, no work before assignment, and estimates only at registration.
