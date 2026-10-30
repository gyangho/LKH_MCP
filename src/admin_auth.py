"""Private WARP administrator login; independent of transport and JWT headers."""
from __future__ import annotations
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import threading
import time
from collections import deque
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

COOKIE = "lkh_admin_session"
DURATION = 4 * 60 * 60
WINDOW = 15 * 60
_LOCK = threading.RLock()
_SESSIONS: dict[str, tuple[str, float]] = {}
_FAILED: deque[float] = deque()

class AdminNotConfigured(Exception):
    pass

class AdminUnauthorized(Exception):
    pass

def _origin() -> str:
    origin = os.getenv("ADMIN_PUBLIC_ORIGIN", "").strip().rstrip("/")
    try:
        parsed = urlsplit(origin)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or
                not parsed.port or parsed.path or parsed.query or parsed.fragment or
                parsed.username or parsed.password):
            raise ValueError("Invalid origin")
        if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"):
            ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise AdminNotConfigured("ADMIN_PUBLIC_ORIGIN requires an exact http(s) host:port") from exc
    return origin

def make_password_hash(password: str, iterations: int = 600000) -> str:
    if not isinstance(password, str) or not 10 <= len(password) <= 256:
        raise ValueError("Password must be 14-256 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"

def _configured() -> tuple[str, int, bytes, bytes]:
    _origin()
    username = os.getenv("ADMIN_LOGIN_USER", "admin")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username):
        raise AdminNotConfigured("Invalid ADMIN_LOGIN_USER")
    value = os.getenv("ADMIN_PASSWORD_HASH", "")
    match = re.fullmatch(r"pbkdf2_sha256\$(\d+)\$([0-9a-f]{32})\$([0-9a-f]{64})", value)
    if not match or not 300000 <= int(match.group(1)) <= 2000000:
        raise AdminNotConfigured("ADMIN_PASSWORD_HASH missing or invalid")
    return username, int(match.group(1)), bytes.fromhex(match.group(2)), bytes.fromhex(match.group(3))

def _prune(now: float) -> None:
    for k in [k for k, (_, end) in _SESSIONS.items() if end <= now]:
        _SESSIONS.pop(k, None)
    while _FAILED and _FAILED[0] <= now - WINDOW:
        _FAILED.popleft()

def login_allowed() -> bool:
    _configured()
    with _LOCK:
        _prune(time.time())
        return len(_FAILED) < 5

def check_password(password: str) -> bool:
    _, iters, salt, digest = _configured()
    if not isinstance(password, str) or not 1 <= len(password) <= 256:
        return False
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters), digest)

def record_failure() -> None:
    with _LOCK:
        now = time.time()
        _prune(now)
        _FAILED.append(now)

def issue_session(response: JSONResponse) -> None:
    username, _, _, _ = _configured()
    token = secrets.token_urlsafe(32)
    with _LOCK:
        now = time.time()
        _prune(now)
        _FAILED.clear()
        if len(_SESSIONS) >= 16:
            _SESSIONS.pop(min(_SESSIONS, key=lambda x: _SESSIONS[x][1]))
        _SESSIONS[hashlib.sha256(token.encode()).hexdigest()] = (username, now + DURATION)
    response.set_cookie(COOKIE, token, max_age=DURATION, path="/admin",
                        httponly=True, samesite="strict", secure=_origin().startswith("https"))

def verify_admin_session(request: Request) -> str:
    _configured()
    token = request.cookies.get(COOKIE, "")
    if not token or len(token) > 128:
        raise AdminUnauthorized("Login required")
    with _LOCK:
        _prune(time.time())
        entry = _SESSIONS.get(hashlib.sha256(token.encode()).hexdigest())
        if entry is None:
            raise AdminUnauthorized("Login required")
        return entry[0]

def revoke_session(request: Request) -> None:
    token = request.cookies.get(COOKIE, "")
    if token and len(token) <= 128:
        with _LOCK:
            _SESSIONS.pop(hashlib.sha256(token.encode()).hexdigest(), None)

def valid_csrf(request: Request) -> bool:
    try:
        origin = _origin()
    except AdminNotConfigured:
        return False
    headers = request.headers
    return (headers.get("origin", "").rstrip("/") == origin and
            headers.get("host", "").lower() == urlsplit(origin).netloc.lower() and
            headers.get("x-lkh-admin-action") == "1" and
            headers.get("content-type", "").split(";")[0].strip().lower() == "application/json" and
            headers.get("sec-fetch-site", "same-origin").lower() in ("same-origin", "none"))

def auth_response(exc: Exception, request: Request):
    if isinstance(exc, AdminNotConfigured):
        return JSONResponse({"error": "Admin authentication not configured"}, status_code=503)
    if request.method == "GET" and not request.url.path.startswith("/admin/api/"):
        return RedirectResponse("/admin/login", status_code=303)
    return JSONResponse({"error": "Login required"}, status_code=401)
