"""Run the installer-selected UIUX search script in an isolated Python runtime."""
from pathlib import Path
import runpy
import sys

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "scripts"))
    from public_skills import skill_paths
    paths = skill_paths("uiux", root=root)
    if paths is None or any(arg.split("=", 1)[0] in {"--persist", "--output-dir", "--page", "--force"} for arg in sys.argv[1:]):
        raise RuntimeError("UIUX read-only runtime unavailable")
    script = paths["source"] / "src/ui-ux-pro-max/scripts/search.py"
    sys.path.insert(0, str(script.parent))
    sys.argv[0] = str(script)
    runpy.run_path(str(script), run_name="__main__")
