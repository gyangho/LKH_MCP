"""Protected admin page alongside /mcp. Custom MCP routes are NOT auto-authenticated."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from runtime_state import change_flag, flags_snapshot, telemetry
import settings_store
from version import VERSION


class AdminNotConfigured(Exception):
    pass


class AdminUnauthorized(Exception):
    pass


def _verify_access(request: Request) -> str:
    """Verify Cloudflare Access signed JWT: RS256 + issuer + audience + email."""
    team = os.getenv("ADMIN_CF_TEAM", "").strip().lower()
    aud = os.getenv("ADMIN_CF_AUD", "").strip()
    emails = {x.strip().lower() for x in os.getenv("ADMIN_ALLOWED_EMAILS", "").split(",") if x.strip()}
    if not re.fullmatch(r"[a-z0-9-]{1,63}", team) or not aud or not emails:
        raise AdminNotConfigured("Cloudflare Access 관리자 인증 설정이 없습니다.")
    token = request.headers.get("cf-access-jwt-assertion", "")
    if not token:
        raise AdminUnauthorized("Cloudflare Access JWT가 없습니다.")
    try:
        import jwt
        issuer = f"https://{team}.cloudflareaccess.com"
        client = jwt.PyJWKClient(f"{issuer}/cdn-cgi/access/certs", cache_jwk_set=True, lifespan=3600)
        key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"],
                            audience=aud, issuer=issuer,
                            options={"require": ["exp", "iat", "iss", "aud", "email"]},
                            leeway=10)
        email = claims.get("email", "").strip().lower()
        if email not in emails:
            raise AdminUnauthorized("관리자 이메일이 허용 목록에 없습니다.")
        return email
    except AdminUnauthorized:
        raise
    except Exception as exc:
        raise AdminUnauthorized("Cloudflare Access JWT 검증 실패") from exc


def _auth_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, AdminNotConfigured):
        return JSONResponse({"error": "Admin authentication not configured"}, status_code=503)
    return JSONResponse({"error": "Access denied"}, status_code=403)


def _html() -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return (base / "web" / "dashboard.html").read_text(encoding="utf-8")


def _private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
    )
    return response


def register_routes(mcp: Any) -> None:
    register_configuration_routes(mcp)
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
            return _private(_auth_response(exc))

    @mcp.custom_route("/admin/api/status", methods=["GET"])
    async def status(request: Request):
        try:
            user = _verify_access(request)
            data = telemetry()
            data["viewer"] = user
            return _private(JSONResponse(data))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc))

    @mcp.custom_route("/admin/api/settings", methods=["GET"])
    async def settings(request: Request):
        try:
            user = _verify_access(request)
            return _private(JSONResponse({"flags": flags_snapshot(), "viewer": user,
                                          "version": VERSION}))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc))

    @mcp.custom_route("/admin/api/flags", methods=["POST"])
    async def set_flag(request: Request):
        try:
            user = _verify_access(request)
            # Browser cross-site requests must not be able to toggle privileged tools.
            origin = os.getenv("ADMIN_PUBLIC_ORIGIN", "").rstrip("/")
            if (not origin.startswith("https://") or request.headers.get("origin") != origin
                    or request.headers.get("x-lkh-admin-action") != "1"
                    or request.headers.get("content-type", "").split(";")[0].strip() != "application/json"):
                return _private(JSONResponse({"error": "Origin / CSRF check failed"}, status_code=403))
            if int(request.headers.get("content-length", "0")) > 2048:
                return _private(JSONResponse({"error": "Payload too large"}, status_code=413))
            obj = await request.json()
            if not isinstance(obj, dict) or set(obj) != {"key", "enabled"}:
                raise ValueError("Only key and enabled are accepted.")
            result = change_flag(obj["key"], obj["enabled"], user)
            return _private(JSONResponse(result))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc))
        except (ValueError, TypeError, KeyError):
            return _private(JSONResponse({"error": "Invalid flag update"}, status_code=400))


def register_configuration_routes(mcp: Any) -> None:
    """Read and mutate only validated SQLite settings; require Access JWT."""
    @mcp.custom_route("/admin/config", methods=["GET"])
    async def config_page(request: Request):
        try:
            _verify_access(request)
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
            return _private(HTMLResponse((base / "web" / "config.html").read_text(encoding="utf-8")))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc))

    @mcp.custom_route("/admin/api/config", methods=["GET"])
    async def config_get(request: Request):
        try:
            actor = _verify_access(request)
            return _private(JSONResponse({"viewer": actor, "settings": settings_store.items(),
                                          "audit": settings_store.audit_events(20), "secrets_configured": {
                                              "oracle": bool(os.environ.get("ORACLE_PASSWORD")),
                                              "cloudflare_access": all(os.environ.get(k) for k in (
                                                  "ADMIN_CF_TEAM", "ADMIN_CF_AUD", "ADMIN_ALLOWED_EMAILS"))
                                          }}))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc))

    @mcp.custom_route("/admin/api/config", methods=["POST"])
    async def config_post(request: Request):
        try:
            actor = _verify_access(request)
            expected_origin = os.environ.get("ADMIN_PUBLIC_ORIGIN", "").rstrip("/")
            if (not expected_origin.startswith("https://") or
                    request.headers.get("origin") != expected_origin or
                    request.headers.get("x-lkh-admin-action") != "1" or
                    request.headers.get("content-type", "").split(";")[0].strip() != "application/json"):
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
            return _private(_auth_response(exc))
        except (ValueError, KeyError, TypeError):
            return _private(JSONResponse({"error": "Invalid or stale setting"}, status_code=400))
