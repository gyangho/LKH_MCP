"""LKH MCP 0.0.1 — bounded, argument-free operational telemetry and runtime flags."""
from __future__ import annotations

import asyncio
import functools
import inspect
import json
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from version import VERSION
import settings_store

FLAGS = ("GIT_ALLOW_COMMIT", "GIT_ALLOW_PUSH", "GRAPHIFY_ALLOW_UPDATE")
_FLAG_META = {
    "GIT_ALLOW_COMMIT": ("Git commit", "로컬 코드 스테이징과 커밋"),
    "GIT_ALLOW_PUSH": ("Git push", "원격 GitHub 브랜치에 push"),
    "GRAPHIFY_ALLOW_UPDATE": ("Graphify update", "프로젝트 그래프 갱신"),
}
_START = time.monotonic()
_LOCK = threading.RLock()
_ACTIVE: dict[str, dict] = {}
_HISTORY = deque(maxlen=60)
_COUNTERS = {"total": 0, "failed": 0}
_LAST_ERROR = ""
_PROC = None
_LAST_SAMPLE = (time.monotonic(), time.process_time())


def state_dir() -> Path:
    override = os.environ.get("MCP_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "LKH_MCP"


def _config_path() -> Path:
    return state_dir() / "runtime-settings.json"


def initialize_state() -> None:
    """Initialize persistent SQLite configuration before tool registration."""
    settings_store.initialize()


def flags_snapshot() -> list[dict[str, Any]]:
    return [{"key": item["key"], "label": item["label"],
             "description": item["description"], "enabled": item["value"]}
            for item in settings_store.items() if item["type"] == "bool"]


def change_flag(key: str, value: bool, actor: str) -> dict:
    """Persist a known boolean with revision and audit tracking."""
    if type(value) is not bool or key not in settings_store._BOOL_FIELDS:
        raise ValueError("Only known boolean settings are allowed")
    item = next(x for x in settings_store.items() if x["key"] == key)
    result = settings_store.update(key, value, actor, item["revision"])
    _record("settings", "success", detail=f"{key}={'ON' if value else 'OFF'}", actor=actor)
    return {"key": key, "enabled": value, "saved": True, "revision": result["revision"],
            "applies_immediately": True}


def _record(tool: str, status: str, *, duration_ms: int = 0,
            detail: str = "", actor: str = "") -> None:
    global _LAST_ERROR
    with _LOCK:
        entry = {"time": datetime.now(timezone.utc).isoformat(), "tool": tool,
                 "status": status, "duration_ms": duration_ms}
        if detail:
            entry["detail"] = detail
        if actor:
            entry["actor"] = actor
        _HISTORY.appendleft(entry)
        if status == "error":
            _LAST_ERROR = f"{tool} failed at {entry['time']}"


def _begin(name: str) -> str:
    ident = uuid.uuid4().hex
    with _LOCK:
        _COUNTERS["total"] += 1
        _ACTIVE[ident] = {"id": ident, "tool": name,
                          "started_at": datetime.now(timezone.utc).isoformat(),
                          "start": time.monotonic()}
    return ident


def _finish(ident: str, name: str, result: Any = None, error: bool = False) -> None:
    with _LOCK:
        item = _ACTIVE.pop(ident, None)
        millis = round((time.monotonic() - item["start"]) * 1000) if item else 0
        if isinstance(result, dict) and result.get("success") is False:
            error = True
        if error:
            _COUNTERS["failed"] += 1
        _record(name, "error" if error else "success", duration_ms=millis)


def instrument_tools(mcp: Any) -> None:
    """Wrap existing decorator before registration; no sensitive arguments/results logged."""
    original = mcp.tool

    def monitored_tool(*args: Any, **kwargs: Any):
        decorator = original(*args, **kwargs)

        def register(fn):
            name = fn.__name__
            if inspect.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def tracked(*a, **kw):
                    ident = _begin(name)
                    try:
                        result = await fn(*a, **kw)
                    except BaseException:
                        _finish(ident, name, error=True)
                        raise
                    _finish(ident, name, result=result)
                    return result
            else:
                @functools.wraps(fn)
                def tracked(*a, **kw):
                    ident = _begin(name)
                    try:
                        result = fn(*a, **kw)
                    except BaseException:
                        _finish(ident, name, error=True)
                        raise
                    _finish(ident, name, result=result)
                    return result
            return decorator(tracked)
        return register
    mcp.tool = monitored_tool


def telemetry() -> dict[str, Any]:
    global _PROC, _LAST_SAMPLE
    with _LOCK:
        now, cpu = time.monotonic(), time.process_time()
        elapsed = max(0.001, now - _LAST_SAMPLE[0])
        cpu_percent = max(0.0, round(100 * (cpu - _LAST_SAMPLE[1]) / elapsed, 1))
        _LAST_SAMPLE = (now, cpu)
        memory_mb = None
        threads = threading.active_count()
        try:
            import psutil
            if _PROC is None:
                _PROC = psutil.Process(os.getpid())
            memory_mb = round(_PROC.memory_info().rss / 1024 / 1024, 1)
            threads = _PROC.num_threads()
        except (ImportError, OSError):
            pass
        uptime = round(time.monotonic() - _START)
        active = [
            {"id": entry["id"], "tool": entry["tool"],
             "started_at": entry["started_at"],
             "elapsed_seconds": round(time.monotonic() - entry["start"], 1)}
            for entry in _ACTIVE.values()
        ]
        return {
            "version": VERSION, "status": "healthy", "pid": os.getpid(),
            "uptime_seconds": uptime, "cpu_percent": cpu_percent,
            "memory_mb": memory_mb, "threads": threads,
            "active_count": len(active), "active": active,
            "recent": list(_HISTORY), "requests": dict(_COUNTERS),
            "flags": flags_snapshot(), "last_error": _LAST_ERROR,
            "server_time": datetime.now(timezone.utc).isoformat(),
        }
