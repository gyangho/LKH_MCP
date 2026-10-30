"""Authenticated, audited control of one pre-installed Windows Agent task."""
from __future__ import annotations

import threading
import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from admin_auth import (AdminNotConfigured, AdminUnauthorized,
                        auth_response, valid_csrf, verify_admin_session)
from admin_console import _private
from codex_presence import agents_snapshot
from native_task_control import control_agent, task_state

_LOCK = threading.Lock()
_LAST_ACTION = 0.0


def register_native_host_routes(mcp):
    @mcp.custom_route("/admin/api/host/services", methods=["GET"])
    async def services(request: Request):
        try:
            verify_admin_session(request)
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(auth_response(exc, request))
        snapshot = agents_snapshot()
        return _private(JSONResponse({
            "agent_task_state": task_state(),
            "agents": snapshot["agents"],
            "server": "running",
        }))

    @mcp.custom_route("/admin/api/host/agent/{action}", methods=["POST"])
    async def action(request: Request):
        global _LAST_ACTION
        try:
            actor = verify_admin_session(request)
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(auth_response(exc, request))
        if not valid_csrf(request):
            return _private(JSONResponse({"error": "CSRF/origin failure"}, status_code=403))
        action_name = request.path_params.get("action", "")
        if action_name not in ("start", "stop", "restart"):
            return _private(JSONResponse({"error": "unknown action"}, status_code=404))
        raw = await request.body()
        if raw not in (b"", b"{}") or len(raw) > 2:
            return _private(JSONResponse({"error": "no arguments allowed"}, status_code=400))
        with _LOCK:
            if time.monotonic() - _LAST_ACTION < 5:
                return _private(JSONResponse({"error": "rate limited"}, status_code=429))
            try:
                snapshot = agents_snapshot()
                is_busy = any(agent["busy"] for agent in snapshot["agents"])
                result = control_agent(action_name, busy=is_busy)
            except PermissionError:
                return _private(JSONResponse({"error": "active Codex task; cancel before stop"}, status_code=409))
            except (OSError, RuntimeError):
                return _private(JSONResponse({"error": "task unavailable or access denied"}, status_code=503))
            _LAST_ACTION = time.monotonic()
        # Only operator/action/time/status, never command output or secrets.
        from runtime_state import _record
        _record("native_agent_task", "success",
                detail="action=" + action_name, actor=actor)
        return _private(JSONResponse(result))
