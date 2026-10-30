"""Local Windows device enrollment and short-lived Agent credentials.

Only an approved Windows installer/SCM process provisions the credential.
Persistent secret is DPAPI machine-protected in an ACL-restricted file; SQLite
contains its SHA-256 verifier, not the plaintext. The unencrypted device bearer
must never travel off loopback. This is a single-host first release.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path


def _paths(root: Path | None = None):
    if root is None:
        from native_runtime import native_state_dir
        root = native_state_dir()
    root = Path(root).resolve()
    return root / "config" / "agent-credential.bin", root / "data" / "mcp.sqlite3"


@contextmanager
def _connect(root: Path | None = None):
    _, database = _paths(root)
    database.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(database), timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS native_device (
        id INTEGER PRIMARY KEY CHECK (id=1),
        verifier TEXT NOT NULL, generation INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS native_agent_sessions (
        verifier TEXT PRIMARY KEY, expires_at INTEGER NOT NULL
    )""")
    try:
        with db:
            yield db
    finally:
        db.close()


def _protect(secret: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI enrollment requires Windows")
    import win32crypt
    return win32crypt.CryptProtectData(
        secret, "LKH MCP Agent local device", None, None, None,
        0x4)  # CRYPTPROTECT_LOCAL_MACHINE (Win32 CryptoAPI flag)


def _unprotect(blob: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI enrollment requires Windows")
    import win32crypt
    _, secret = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return secret


def read_device_secret(root: Path | None = None) -> str:
    path, _ = _paths(root)
    if not path.is_file() or path.stat().st_size > 4096:
        raise RuntimeError("Native Agent not enrolled")
    raw = _unprotect(path.read_bytes()).decode("ascii")
    if not 48 <= len(raw) <= 128 or not raw.isascii():
        raise RuntimeError("Invalid local device credential")
    return raw


def provision(root: Path | None = None, *, rotate: bool = False) -> dict:
    """Admin-only installer action; rotation writes a new local protected blob."""
    path, _ = _paths(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(root) as db:
        current = db.execute("SELECT generation FROM native_device WHERE id=1").fetchone()
        if current and not rotate:
            return {"provisioned": True, "generation": current[0], "unchanged": True}
        # Fail closed: never overwrite an unknown device key without explicit rotation.
        if path.exists() and not current:
            raise RuntimeError("Orphaned device key; operator recovery required")
        device_secret = secrets.token_urlsafe(48)
        encoded = _protect(device_secret.encode("ascii"))
        tmp = path.with_name("agent-credential-" + secrets.token_hex(8) + ".tmp")
        try:
            with tmp.open("xb") as output:
                output.write(encoded)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        generation = (current[0] + 1) if current else 1
        db.execute("""INSERT INTO native_device(id,verifier,generation,updated_at)
                      VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET
                      verifier=excluded.verifier,generation=excluded.generation,
                      updated_at=excluded.updated_at""",
                   (hashlib.sha256(device_secret.encode("ascii")).hexdigest(),
                    generation, int(time.time())))
        db.execute("DELETE FROM native_agent_sessions")
    return {"provisioned": True, "generation": generation, "unchanged": False}


def enrolled(root: Path | None = None) -> bool:
    with _connect(root) as db:
        return db.execute("SELECT 1 FROM native_device WHERE id=1").fetchone() is not None


def issue_session(device_secret: str, root: Path | None = None) -> dict:
    if not isinstance(device_secret, str) or not 48 <= len(device_secret) <= 128 or not device_secret.isascii():
        raise PermissionError("Unrecognized Agent device")
    with _connect(root) as db:
        row = db.execute("SELECT verifier FROM native_device WHERE id=1").fetchone()
        if not row or not hmac.compare_digest(
            hashlib.sha256(device_secret.encode("ascii")).hexdigest(), row[0]):
            raise PermissionError("Unrecognized Agent device")
        token = secrets.token_urlsafe(48)
        expires = int(time.time()) + 900
        db.execute("DELETE FROM native_agent_sessions WHERE expires_at <= ?",
                   (int(time.time()),))
        db.execute("INSERT INTO native_agent_sessions(verifier,expires_at) VALUES(?,?)",
                   (hashlib.sha256(token.encode("ascii")).hexdigest(), expires))
    return {"access_token": token, "expires_at": expires, "token_type": "Bearer"}


def check_access(header: str, root: Path | None = None) -> bool:
    if not isinstance(header, str) or not header.startswith("Bearer "):
        return False
    token = header[7:]
    if not 32 <= len(token) <= 128 or not token.isascii():
        return False
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    with _connect(root) as db:
        row = db.execute(
            "SELECT expires_at FROM native_agent_sessions WHERE verifier=?", (digest,)
        ).fetchone()
        return bool(row and row[0] > int(time.time()))
