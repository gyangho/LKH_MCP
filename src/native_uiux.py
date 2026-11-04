"""Fixed UIUX search worker bundled with Python; no arbitrary script argument."""
from pathlib import Path
import runpy
import sys


def main():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    script = root / "vendor/ui-ux-pro-max-skill/src/ui-ux-pro-max/scripts/search.py"
    # Caller supplies only search arguments; persistence/output options are prohibited.
    if any(arg.split("=", 1)[0] in {"--persist", "--output-dir", "--page", "--force"} for arg in sys.argv[1:]):
        raise ValueError("Read-only search required")
    sys.path.insert(0, str(script.parent))
    sys.argv[0] = str(script)
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
