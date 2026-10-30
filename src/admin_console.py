"""Protected admin page alongside /mcp. Custom MCP routes are NOT auto-authenticated."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from admin_auth import (AdminNotConfigured, AdminUnauthorized, verify_admin_session as _verify_access,
                        auth_response as _auth_response, valid_csrf, login_allowed,
                        check_password, record_failure, issue_session, revoke_session, COOKIE)

from runtime_state import change_flag, flags_snapshot, telemetry
import settings_store
from version import VERSION


def _html() -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return (base / "web" / "dist" / "index.html").read_text(encoding="utf-8")


def _private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self'; "
        "style-src 'self' https://cdn.jsdelivr.net; font-src 'self' https://cdn.jsdelivr.net; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
    )
    return response


def register_routes(mcp: Any) -> None:
    register_configuration_routes(mcp)

    @mcp.custom_route("/admin/assets/{asset_path:path}", methods=["GET"])
    async def assets(request: Request):
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "web" / "dist" / "assets"
        resolved_root = root.resolve()
        requested = (root / request.path_params["asset_path"]).resolve()
        if not requested.is_relative_to(resolved_root) or not requested.is_file():
            return _private(JSONResponse({"error": "Not found"}, status_code=404))
        return _private(FileResponse(requested))

    @mcp.custom_route("/admin/login", methods=["GET"])
    async def login_page(request: Request):
        return _private(HTMLResponse(_html()))

    @mcp.custom_route("/admin/api/login", methods=["POST"])
    async def login(request: Request):
        if not valid_csrf(request):
            return _private(JSONResponse({"error": "Origin / CSRF check failed"}, status_code=403))
        try:
            if not login_allowed():
                return _private(JSONResponse({"error": "Too many attempts; try later"}, status_code=429))
            body = await request.body()
            if not 1 <= len(body) <= 1024:
                return _private(JSONResponse({"error": "Invalid login"}, status_code=400))
            import json
            data = json.loads(body)
            if not isinstance(data, dict) or set(data) != {"password"}:
                return _private(JSONResponse({"error": "Invalid login"}, status_code=400))
            if not check_password(data["password"]):
                record_failure()
                return _private(JSONResponse({"error": "Invalid credentials"}, status_code=401))
            response = JSONResponse({"ok": True})
            issue_session(response)
            return _private(response)
        except AdminNotConfigured as exc:
            return _private(_auth_response(exc, request))
        except (ValueError, TypeError, UnicodeDecodeError):
            return _private(JSONResponse({"error": "Invalid login"}, status_code=400))

    @mcp.custom_route("/admin/api/logout", methods=["POST"])
    async def logout(request: Request):
        if not valid_csrf(request):
            return _private(JSONResponse({"error": "Origin / CSRF check failed"}, status_code=403))
        revoke_session(request)
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/admin")
        return _private(response)
    @mcp.custom_route("/", methods=["GET"])
    async def home(request: Request):
        return RedirectResponse("/admin", status_code=307)

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request):
        # Public, deliberately no version/OS/secret details.
        return JSONResponse({"status": "ok"})

    @mcp.custom_route("/admin", methods=["GET"])
    async def page(request: Request):
        try:
            _verify_access(request)
            return _private(HTMLResponse(_html()))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))

    @mcp.custom_route("/admin/api/status", methods=["GET"])
    async def status(request: Request):
        try:
            user = _verify_access(request)
            data = telemetry()
            data["viewer"] = user
            return _private(JSONResponse(data))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))

    @mcp.custom_route("/admin/api/settings", methods=["GET"])
    async def settings(request: Request):
        try:
            user = _verify_access(request)
            return _private(JSONResponse({"flags": flags_snapshot(), "viewer": user,
                                          "version": VERSION}))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))

    @mcp.custom_route("/admin/api/flags", methods=["POST"])
    async def set_flag(request: Request):
        try:
            user = _verify_access(request)
            if not valid_csrf(request):
                return _private(JSONResponse({"error": "Origin / CSRF check failed"}, status_code=403))
            if int(request.headers.get("content-length", "0")) > 2048:
                return _private(JSONResponse({"error": "Payload too large"}, status_code=413))
            obj = await request.json()
            if not isinstance(obj, dict) or set(obj) != {"key", "enabled"}:
                raise ValueError("Only key and enabled are accepted.")
            result = change_flag(obj["key"], obj["enabled"], user)
            return _private(JSONResponse(result))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))
        except (ValueError, TypeError, KeyError):
            return _private(JSONResponse({"error": "Invalid flag update"}, status_code=400))


def register_configuration_routes(mcp: Any) -> None:
    """Read and mutate SQLite settings using private administrator sessions."""
    @mcp.custom_route("/admin/config", methods=["GET"])
    async def config_page(request: Request):
        try:
            _verify_access(request)
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
            return _private(HTMLResponse(_html()))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))

    @mcp.custom_route("/admin/api/config", methods=["GET"])
    async def config_get(request: Request):
        try:
            actor = _verify_access(request)
            return _private(JSONResponse({"viewer": actor, "settings": settings_store.items(),
                                          "audit": settings_store.audit_events(20), "secrets_configured": {
                                              "oracle": bool(os.environ.get("ORACLE_PASSWORD")),
                                              "local_admin": bool(os.getenv("ADMIN_PASSWORD_HASH"))
                                          }}))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))

    @mcp.custom_route("/admin/api/config", methods=["POST"])
    async def config_post(request: Request):
        try:
            actor = _verify_access(request)
            if not valid_csrf(request):
                return _private(JSONResponse({"error": "Origin or CSRF check failed"}, status_code=403))
            length = int(request.headers.get("content-length", "0"))
            if length < 1 or length > 4096:
                return _private(JSONResponse({"error": "Invalid content length"}, status_code=413))
            data = await request.json()
            if not isinstance(data, dict) or set(data) != {"key", "value", "revision"}:
                raise ValueError("Only key, value and revision are allowed")
            result = settings_store.update(data["key"], data["value"], actor, data["revision"])
            return _private(JSONResponse(result))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))
        except (ValueError, KeyError, TypeError):
            return _private(JSONResponse({"error": "Invalid or stale setting"}, status_code=400))
