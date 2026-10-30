"""Windows-native staging runtime configuration (no service or tray).

The native preview must never reuse Docker's live SQLite or expose the
combined MCP+admin ASGI application outside loopback until I2 provides
equivalent endpoint isolation.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import MutableMapping

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
_PREVIEW_PORT = "18080"


def native_state_dir(
    env: MutableMapping[str, str] | None = None, *,
    root: Path | None = None,
) -> Path:
    values = os.environ if env is None else env
    if root is not None:
        base = Path(root)
    elif values.get("LKH_NATIVE_STATE_DIR"):
        base = Path(values["LKH_NATIVE_STATE_DIR"])
    else:
        program_data = values.get("PROGRAMDATA", "")
        if not program_data:
            raise RuntimeError("PROGRAMDATA is required for a native Windows installation")
        base = Path(program_data) / "LKH-MCP"
    if not base.is_absolute():
        raise ValueError("Native state directory must be absolute")
    return base


def prepare_native_environment(
    env: MutableMapping[str, str] | None = None, *,
    root: Path | None = None,
) -> Path:
    """Configure an isolated preview without modifying Docker runtime or secrets."""
    values = os.environ if env is None else env
    base = native_state_dir(values, root=root)
    host = values.get("MCP_HOST") or "127.0.0.1"
    if host not in _LOOPBACK:
        raise ValueError("Native preview may listen only on loopback until gateway isolation is verified")
    port = values.get("MCP_PORT") or _PREVIEW_PORT
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("Invalid MCP_PORT")
    if port in {"8000", "8001"}:
        raise ValueError("Native preview cannot reuse the live Docker gateway ports 8000/8001")
    admin_port = values.get("LKH_NATIVE_ADMIN_PORT") or "18081"
    if not admin_port.isdecimal() or not 1 <= int(admin_port) <= 65535:
        raise ValueError("Invalid native admin port")
    if admin_port in {"8000", "8001"} or port == admin_port:
        raise ValueError("Preview ports must be distinct and cannot use live Docker ports")
    values["LKH_NATIVE_ADMIN_PORT"] = admin_port
    values["MCP_HOST"] = host
    values["MCP_PORT"] = port
    database = values.get("MCP_DB_PATH")
    if database:
        if not Path(database).is_absolute():
            raise ValueError("MCP_DB_PATH must be absolute for native preview")
    else:
        values["MCP_DB_PATH"] = str(base / "data" / "mcp.sqlite3")
    bootstrap = values.get("MCP_BOOTSTRAP_FILE")
    if bootstrap:
        if not Path(bootstrap).is_absolute():
            raise ValueError("MCP_BOOTSTRAP_FILE must be absolute for native preview")
    else:
        candidate = base / "config" / "bootstrap.json"
        if candidate.is_file():
            values["MCP_BOOTSTRAP_FILE"] = str(candidate)
    for name in ("data", "logs"):
        (base / name).mkdir(parents=True, exist_ok=True)
    return base


def packaged_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def required_assets(root: Path | None = None) -> dict[str, bool]:
    base = packaged_root() if root is None else Path(root)
    paths = {
        "admin_html": base / "web" / "dist" / "index.html",
        "uiux_search": base / "vendor" / "ui-ux-pro-max-skill"
                       / "src" / "ui-ux-pro-max" / "scripts" / "search.py",
    }
    return {name: file.is_file() for name, file in paths.items()}
