"""Oracle profiles. Only DPAPI ciphertext enters the ACL-protected SQLite DB."""
from __future__ import annotations

import json
import os
import re
import secrets
from contextlib import contextmanager

import settings_store

FIELDS = {"name", "host", "port", "service", "sid", "dsn", "username", "allowed_tables", "enabled"}


class Conflict(ValueError):
    pass


class NotFound(ValueError):
    pass


def protect(password: str) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Oracle password storage requires Windows DPAPI")
    import win32crypt
    return win32crypt.CryptProtectData(password.encode("utf-8"), "LKH MCP Oracle password",
                                      None, None, None, 0x5)


def unprotect(blob: bytes) -> str:
    if os.name != "nt":
        raise RuntimeError("Oracle password storage requires Windows DPAPI")
    import win32crypt
    return win32crypt.CryptUnprotectData(blob, None, None, None, 1)[1].decode("utf-8")


def validate(data: dict) -> dict:
    if not isinstance(data, dict) or set(data) != FIELDS:
        raise ValueError("Invalid connection fields")
    result = dict(data)
    for key in FIELDS - {"port", "enabled"}:
        value = result[key]
        if not isinstance(value, str) or len(value) > (2000 if key == "allowed_tables" else 512) or any(c in value for c in "\x00\r\n"):
            raise ValueError("Invalid connection text")
        result[key] = value.strip()
    if not result["name"] or len(result["name"]) > 80 or not result["username"]:
        raise ValueError("Connection name and username required")
    if type(result["port"]) is not int or not 1 <= result["port"] <= 65535 or type(result["enabled"]) is not bool:
        raise ValueError("Invalid port or enabled state")
    if not result["dsn"]:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,253}", result["host"]):
            raise ValueError("Invalid database host")
        if bool(result["service"]) == bool(result["sid"]):
            raise ValueError("Exactly one of Service Name or SID required")
        for key in ("service", "sid"):
            if result[key] and not re.fullmatch(r"[A-Za-z0-9_.$#-]{1,128}", result[key]):
                raise ValueError("Invalid service or SID")
    elif "@" in result["dsn"] or re.search(r"(?i)(?:password|pwd|user)\s*=", result["dsn"]):
        raise ValueError("DSN must not contain credentials")
    elif result["service"] or result["sid"]:
        raise ValueError("DSN cannot be combined with Service Name or SID")
    from oracle_db import get_allowed_tables
    result["allowed_tables"] = ",".join(sorted(get_allowed_tables(result["allowed_tables"])))
    return result


def _password(value: str) -> bytes:
    if not isinstance(value, str) or not 1 <= len(value) <= 1024 or "\x00" in value:
        raise ValueError("Password required (up to 1024 characters)")
    return protect(value)


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS oracle_connections (
        id TEXT PRIMARY KEY, profile TEXT NOT NULL, password BLOB NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL)""")
    db.execute("CREATE TABLE IF NOT EXISTS oracle_migrations (name TEXT PRIMARY KEY)")


def _migrate(db):
    marker = "single-profile-v1"
    if db.execute("SELECT 1 FROM oracle_migrations WHERE name=?", (marker,)).fetchone():
        return
    previous = {key: json.loads(value) for key, value in db.execute("SELECT name,value FROM settings")}
    def old(key, default=""):
        return previous.get(key, os.environ.get(key, default))
    user, password = old("ORACLE_USER"), os.environ.get("ORACLE_PASSWORD", "")
    # Leave incomplete legacy settings intact; never invent or erase credentials.
    if user and password and password != "CHANGE_ME":
        dsn = old("ORACLE_DSN")
        profile = validate({"name": "기존 Oracle 연결", "host": old("ORACLE_HOST", "127.0.0.1"),
                            "port": int(old("ORACLE_PORT", 1521)), "service": "" if dsn else old("ORACLE_SERVICE"),
                            "sid": "" if dsn else old("ORACLE_SID"), "dsn": dsn, "username": user,
                            "allowed_tables": old("ORACLE_ALLOWED_TABLES"), "enabled": True})
        db.execute("INSERT INTO oracle_connections(id,profile,password,updated_at) VALUES(?,?,?,?)",
                   ("legacy", json.dumps(profile, ensure_ascii=False), _password(password), settings_store._timestamp()))
    elif user:
        # Retry on a later startup once missing legacy credentials are supplied.
        return
    db.execute("INSERT INTO oracle_migrations(name) VALUES(?)", (marker,))


@contextmanager
def _db():
    settings_store.initialize()
    db = settings_store._connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        _schema(db)
        _migrate(db)
        yield db
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    finally:
        db.close()


def _row(db, ident):
    if not isinstance(ident, str) or not re.fullmatch(r"[a-z0-9-]{1,40}", ident):
        raise NotFound("Unknown Oracle connection")
    row = db.execute("SELECT id,profile,password,revision,updated_at FROM oracle_connections WHERE id=?", (ident,)).fetchone()
    if row is None:
        raise NotFound("Unknown Oracle connection")
    return row


def _public(row):
    return {"id": row[0], **json.loads(row[1]), "password_configured": bool(row[2]),
            "revision": row[3], "updated_at": row[4]}


def list_connections(*, mcp=False):
    with _db() as db:
        rows = db.execute("SELECT id,profile,password,revision,updated_at FROM oracle_connections ORDER BY id").fetchall()
    profiles = [_public(row) for row in rows]
    if mcp:
        return [{"id": p["id"], "name": p["name"]} for p in profiles if p["enabled"]]
    return profiles


def credentials(ident, *, allow_disabled=False):
    with _db() as db:
        row = _row(db, ident)
        profile = _public(row)
        if not profile["enabled"] and not allow_disabled:
            raise PermissionError("Oracle connection is disabled")
        try:
            profile["password"] = unprotect(row[2])
        except Exception:
            raise RuntimeError("Oracle credential could not be decrypted on this Windows host") from None
        return profile


def _audit(db, actor, ident, action):
    if not isinstance(actor, str) or not 1 <= len(actor) <= 256:
        raise ValueError("Invalid actor")
    # No profile content or passwords in audit rows.
    db.execute("INSERT INTO audit(at,actor,name,old_value,new_value) VALUES(?,?,?,?,?)",
               (settings_store._timestamp(), actor, "oracle:" + ident, "", action))


def create(data, password, actor):
    profile, blob = validate(data), _password(password)
    ident = secrets.token_hex(12)
    with _db() as db:
        if db.execute("SELECT COUNT(*) FROM oracle_connections").fetchone()[0] >= 20:
            raise ValueError("At most 20 Oracle connections")
        db.execute("INSERT INTO oracle_connections(id,profile,password,updated_at) VALUES(?,?,?,?)",
                   (ident, json.dumps(profile, ensure_ascii=False), blob, settings_store._timestamp()))
        _audit(db, actor, ident, "create")
        return _public(_row(db, ident))


def update(ident, revision, data, password, actor):
    profile = validate(data)
    with _db() as db:
        row = _row(db, ident)
        if type(revision) is not int or revision != row[3]:
            raise Conflict("Connection changed; reload before saving")
        blob = row[2] if password == "" else _password(password)
        db.execute("UPDATE oracle_connections SET profile=?,password=?,revision=revision+1,updated_at=? WHERE id=?",
                   (json.dumps(profile, ensure_ascii=False), blob, settings_store._timestamp(), ident))
        _audit(db, actor, ident, "update")
        return _public(_row(db, ident))


def delete(ident, revision, actor):
    with _db() as db:
        row = _row(db, ident)
        if type(revision) is not int or revision != row[3]:
            raise Conflict("Connection changed; reload before deleting")
        db.execute("DELETE FROM oracle_connections WHERE id=?", (ident,))
        _audit(db, actor, ident, "delete")
    return {"deleted": True}
