# Makes `import orders` work for tests run from anywhere (including temp copies).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
