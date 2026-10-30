"""Persistent one-time Codex Agent credentials.

Managed credentials are high-entropy random bearer tokens. Persist only SHA-256
of the token in the private SQLite volume; never persist the bearer token itself.
Bootstrap CODEX_AGENT_TOKEN is supported only until a managed token is issued or
explicitly revoked. After management begins, bootstrap cannot silently reactivate.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time

import settings_store

_TOKEN_HASH = re.compile(r"^[a-f0-9]{64}$")


def _connect():
    conn = settings_store._connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS codex_token_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        token_hash TEXT,
        updated_at INTEGER NOT NULL,
        updated_by TEXT NOT NULL
    )""")
    return conn


def status() -> dict:
    """Non-secret status for the protected admin page and agent presence UI."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT token_hash,updated_at,updated_by FROM codex_token_state WHERE id=1"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        legacy = os.getenv("CODEX_AGENT_TOKEN", "")
        configured = len(legacy) >= 32 and legacy.isascii()
        return {"configured": configured, "source": "bootstrap" if configured else "none",
                "updated_at": None, "updated_by": None}
    return {"configured": row[0] is not None, "source": "managed" if row[0] else "revoked",
            "updated_at": row[1], "updated_by": row[2]}


def check_token(header: str) -> bool:
    if not isinstance(header, str) or not header.startswith("Bearer "):
        return False
    raw = header[len("Bearer "):]
    if not 32 <= len(raw) <= 256 or not raw.isascii():
        return False
    presented_hash = hashlib.sha256(raw.encode("ascii")).hexdigest()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT token_hash FROM codex_token_state WHERE id=1"
        ).fetchone()
    finally:
        conn.close()
    if row is not None:
        return bool(row[0] and _TOKEN_HASH.fullmatch(row[0]) and
                    hmac.compare_digest(presented_hash, row[0]))
    legacy = os.getenv("CODEX_AGENT_TOKEN", "")
    return bool(len(legacy) >= 32 and legacy.isascii() and
                hmac.compare_digest(raw, legacy))


def _write_state(token_hash: str | None, actor: str) -> None:
    if not isinstance(actor, str) or not 1 <= len(actor) <= 128:
        raise ValueError("Invalid admin actor")
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""INSERT INTO codex_token_state (id,token_hash,updated_at,updated_by)
                        VALUES (1,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET
                        token_hash=excluded.token_hash,
                        updated_at=excluded.updated_at,
                        updated_by=excluded.updated_by""",
                     (token_hash, int(time.time()), actor))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def rotate(actor: str) -> dict:
    """Reveal the generated credential exactly once in this protected response."""
    token = secrets.token_urlsafe(48)
    _write_state(hashlib.sha256(token.encode("ascii")).hexdigest(), actor)
    return {"token": token, "status": status()}


def revoke(actor: str) -> dict:
    """Explicit revocation; persists across restarts, even with bootstrap present."""
    _write_state(None, actor)
    return {"status": status()}
