# Make hooks/ importable from tests, and stop pytest collecting the hook named test_tamper_check.py.
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE / "hooks")]
collect_ignore = ["hooks/test_tamper_check.py"]
