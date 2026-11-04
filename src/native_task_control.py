"""Fixed-name Windows Task Scheduler controls for the installed Codex Agent.

Never accepts a path, argument, task name, shell command, or user-supplied
executable. The Agent runs under its pre-registered Codex-login account.
"""
from __future__ import annotations

import os
import subprocess
import time

TASK_NAME = r"\LKH-Codex-Agent"


def _windows_only() -> None:
    if os.name != "nt":
        raise RuntimeError("Windows Task Scheduler unavailable")


def task_state() -> str:
    """Query the fixed Agent task. COM initialization must be per-calling-thread."""
    _windows_only()
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
    except Exception:
        return "unavailable"
    scheduler = task = None
    try:
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        task = scheduler.GetFolder("\\").GetTask("LKH-Codex-Agent")
        return {1: "disabled", 2: "queued", 3: "ready", 4: "running"}.get(
            int(task.State), "unknown")
    except Exception:
        return "unavailable"
    finally:
        task = scheduler = None
        pythoncom.CoUninitialize()


def _user_session(principal: str) -> tuple[int, str]:
    """Match by SID, never by display name or the service's own session 0."""
    import win32security
    import win32ts

    expected = (win32security.ConvertStringSidToSid(principal) if principal.startswith("S-1-")
                else win32security.LookupAccountName(None, principal)[0])
    sid = win32security.ConvertSidToStringSid(expected)
    matches = []
    server = win32ts.WTS_CURRENT_SERVER_HANDLE
    for session in win32ts.WTSEnumerateSessions(server, 1, 0):
        ident = int(session["SessionId"])
        if ident <= 0 or session["State"] != win32ts.WTSActive:
            continue
        user = win32ts.WTSQuerySessionInformation(server, ident, win32ts.WTSUserName)
        domain = win32ts.WTSQuerySessionInformation(server, ident, win32ts.WTSDomainName)
        if not user:
            continue
        account = domain + "\\" + user if domain else user
        observed = win32security.LookupAccountName(None, account)[0]
        if win32security.ConvertSidToStringSid(observed) == sid:
            matches.append(ident)
    if len(matches) != 1:
        raise RuntimeError("Agent requires exactly one active session for its registered user")
    return matches[0], sid


def _start_interactive(*, restart: bool) -> None:
    """Run only the fixed registered task with its existing account/privileges."""
    initialized = False
    scheduler = registered = principal = None
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        initialized = True
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        registered = scheduler.GetFolder("\\").GetTask("LKH-Codex-Agent")
        if int(registered.State) == 1:
            raise RuntimeError("Agent task is disabled")
        if int(registered.State) == 4 and not restart:
            return
        principal = registered.Definition.Principal
        if int(principal.LogonType) != 3:  # TASK_LOGON_INTERACTIVE_TOKEN
            raise RuntimeError("Agent task must use its registered interactive account")
        session, sid = _user_session(str(principal.UserId))
        # Resolve the session first so a failed restart leaves a running Agent
        # intact. Stop only this task, and wait before IgnoreNew can discard RunEx.
        if restart and int(registered.State) in (2, 4):
            registered.Stop(0)
            deadline = time.monotonic() + 5
            while int(registered.State) in (2, 4):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Agent task did not stop")
                time.sleep(0.1)
        # USE_SESSION_ID | USER_SID. Never AS_SELF or IGNORE_CONSTRAINTS.
        registered.RunEx(None, 0x4 | 0x8, session, sid)
    except Exception:
        # COM/WTS errors can contain account details; return no raw exception.
        raise RuntimeError("Agent task start failed; check registered account, active session and task permissions") from None
    finally:
        principal = registered = scheduler = None
        if initialized:
            pythoncom.CoUninitialize()


def control_agent(action: str, *, busy: bool = False) -> dict:
    """Start/end only the installer-owned task; caller authenticates admin."""
    _windows_only()
    if action not in ("start", "stop", "restart"):
        raise ValueError("Unsupported task action")
    if busy and action in ("stop", "restart"):
        raise PermissionError("Agent has an active task; cancel it first")
    if action in ("start", "restart"):
        _start_interactive(restart=action == "restart")
    else:
        result = subprocess.run(["schtasks.exe", "/end", "/tn", TASK_NAME], shell=False, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=15, check=False)
        if result.returncode:
            raise RuntimeError("Agent task operation failed (not installed or access denied)")
    return {"accepted": True, "action": action,
            "note": "Task Scheduler accepted request; heartbeat confirms Agent Online"}
