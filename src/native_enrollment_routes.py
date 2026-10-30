"""Windows native same-host enrollment API.

Enrollment uses a DPAPI-protected machine-bound device credential created by
the installer. The bootstrap endpoint is deliberately available only via the
loopback-only native admin listener and never exposed by Docker or MCP surface.
"""
from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse

from admin_auth import (AdminNotConfigured, AdminUnauthorized, auth_response,
                        valid_csrf, verify_admin_session)
from admin_console import _private
from native_enrollment import enrolled, issue_session, provision


def register_native_enrollment_routes(mcp):
    @mcp.custom_route("/admin/agent/enrollment/session", methods=["POST"])
    async def session(request: Request):
        headers = {"Cache-Control": "no-store"}
        # Native gateway requires loopback. Do not accept forwarded remote calls.
        if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
            return JSONResponse({"error": "localhost only"}, status_code=403, headers=headers)
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return JSONResponse({"error": "JSON required"}, status_code=400, headers=headers)
        raw = await request.body()
        if not 1 <= len(raw) <= 256:
            return JSONResponse({"error": "invalid body"}, status_code=400, headers=headers)
        try:
            payload = json.loads(raw)
            if payload != {}:
                raise ValueError("Unexpected fields")
            device = request.headers.get("authorization", "")
            if not device.startswith("Device "):
                raise PermissionError("Device not enrolled")
            result = issue_session(device[len("Device "):])
            return JSONResponse(result, headers=headers)
        except (ValueError, PermissionError, TypeError):
            return JSONResponse({"error": "device authentication rejected"},
                                status_code=401, headers=headers)

    @mcp.custom_route("/admin/api/host/enrollment", methods=["GET"])
    async def status(request: Request):
        try:
            verify_admin_session(request)
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(auth_response(exc, request))
        return _private(JSONResponse({"enrolled": enrolled(),
                                      "mode": "local-dpapi"}))

    @mcp.custom_route("/admin/api/host/enrollment/rotate", methods=["POST"])
    async def rotate(request: Request):
        try:
            actor = verify_admin_session(request)
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(auth_response(exc, request))
        if not valid_csrf(request):
            return _private(JSONResponse({"error": "CSRF/origin failure"}, status_code=403))
        raw = await request.body()
        try:
            if len(raw) > 100 or json.loads(raw) != {"confirm": "ROTATE"}:
                raise ValueError()
        except (ValueError, TypeError):
            return _private(JSONResponse({"error": "explicit ROTATE required"}, status_code=400))
        try:
            result = provision(rotate=True)
        except (OSError, RuntimeError):
            return _private(JSONResponse({"error": "rotation failed; inspect local service log"},
                                         status_code=503))
        from runtime_state import _record
        _record("native_device_rotate", "success", actor=actor)
        return _private(JSONResponse(result))
