"""Backward-compatible entry point; implementation lives in src/."""
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from src.server import mcp, run  # noqa: E402,F401

if __name__ == "__main__":
    run()
