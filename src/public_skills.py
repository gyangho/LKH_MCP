"""Resolve installer-managed public skill resources without user/global installs."""
import json
import sys
from pathlib import Path


def install_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parent.parent


def skill_paths(name, root=None):
    if name not in ("uiux", "graphify"):
        raise ValueError("Unknown public skill")
    root = install_root() if root is None else Path(root).resolve()
    skills = root / "skills"
    try:
        data = json.loads((skills / "active.json").read_text(encoding="utf-8"))
        entry = data[name]
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            return None
        source = (skills / relative).resolve(strict=True)
        if not source.is_relative_to(skills.resolve()):
            return None
        python = root / "skills-python" / "python.exe"
        if not python.is_file():
            return None
        required = (source / "src/ui-ux-pro-max/scripts/search.py" if name == "uiux"
                    else source / "graphify/__main__.py")
        helper = root / "scripts" / ("native-uiux.py" if name == "uiux" else "native-graphify.py")
        if not required.is_file() or not helper.is_file() or not (source / "lkh-source.json").is_file():
            return None
        return {"root": root, "source": source, "python": python,
                "version": str(entry["version"]), "commit": str(entry["commit"])}
    except (OSError, ValueError, TypeError, KeyError):
        return None
