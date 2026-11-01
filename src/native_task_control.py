"""Fixed-name Windows Task Scheduler controls for the installed Codex Agent.

Never accepts a path, argument, task name, shell command, or user-supplied
executable. The Agent runs under its pre-registered Codex-login account.
"""
from __future__ import annotations

import os
import subprocess

TASK_NAME = r"\LKH-Codex-Agent"


def _windows_only() -> None:
    if os.name != "nt":
        raise RuntimeError("Windows Task Scheduler unavailable")


def task_state() -> str:
    """COM numeric state: 1 Disabled, 2 Queued, 3 Ready, 4 Running."""
    _windows_only()
    import win32com.client
    scheduler = win32com.client.Dispatch("Schedule.Service")
    scheduler.Connect()
    try:
        task = scheduler.GetFolder("\\").GetTask("LKH-Codex-Agent")
        return {1: "disabled", 2: "queued", 3: "ready", 4: "running"}.get(
            int(task.State), "unknown")
    except Exception:
        return "unavailable"


def control_agent(action: str, *, busy: bool = False) -> dict:
    """Start/end only the installer-owned task; caller authenticates admin."""
    _windows_only()
    if action not in ("start", "stop", "restart"):
        raise ValueError("Unsupported task action")
    if busy and action in ("stop", "restart"):
        raise PermissionError("Agent has an active task; cancel it first")
    commands = {
        "start": [["schtasks.exe", "/run", "/tn", TASK_NAME]],
        "stop": [["schtasks.exe", "/end", "/tn", TASK_NAME]],
        "restart": [["schtasks.exe", "/end", "/tn", TASK_NAME],
                    ["schtasks.exe", "/run", "/tn", TASK_NAME]],
    }
    for command in commands[action]:
        result = subprocess.run(command, shell=False, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=15, check=False)
        if result.returncode:
            raise RuntimeError("Agent task operation failed (not installed or access denied)")
    return {"accepted": True, "action": action,
            "note": "Task Scheduler accepted request; heartbeat confirms Agent Online"}
