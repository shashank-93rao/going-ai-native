# Module-local pytest config: make examples/ importable and keep pytest out of the toy workspace,
# whose spec_*.py files are meant to FAIL until an agent fixes the code.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "examples"))
collect_ignore_glob = ["examples/*"]
