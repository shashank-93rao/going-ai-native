# Makes `import ainative_kit` work in every module's tests without installing.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "shared"))
