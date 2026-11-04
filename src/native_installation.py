"""Installer completion gate shared by native Service, Server, Tray and Agent."""
import json
import os
from pathlib import Path
import sys


def phase():
    from version import VERSION
    root = Path(os.environ.get("LKH_NATIVE_STATE_DIR") or
                str(Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "LKH-MCP"))
    marker = root / "config/installation.json"
    try:
        data = json.loads(marker.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or data.get("version") != VERSION:
            return "incomplete"
        return data.get("phase") if data.get("phase") in {"installing", "starting", "ready", "failed"} else "incomplete"
    except (OSError, ValueError, TypeError):
        return "incomplete"


def allowed(*, server_start=False):
    # Source-mode development remains separate from installed binaries.
    if not getattr(sys, "frozen", False):
        return True
    return phase() in ({"starting", "ready"} if server_start else {"ready"})
