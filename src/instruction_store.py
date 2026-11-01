"""Phase 4-6: revisioned, audited, published-only MCP instruction registry.

SQLite is the source of truth. Drafts are never served by MCP tools; edits
require optimistic revision matching and a separate publish action.
"""
from __future__ import annotations

import re
import sqlite3
import time
import uuid

import settings_store

_KEY = re.compile(r"^[a-z][a-z0-9_-]{1,59}$")
_CONTEXT = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_SCOPES = ("global", "project", "agent", "tool")
_SECRET = re.compile(r"(?i)(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
                     r"(?:password|secret|api[_-]?key|authorization)\s*[:=]\s*\S{6,})")


def _db():
    conn = settings_store._connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS instruction_entries(
        id TEXT PRIMARY KEY, name TEXT NOT NULL, scope TEXT NOT NULL,
        scope_key TEXT NOT NULL, revision INTEGER NOT NULL,
        published_revision INTEGER, created_at INTEGER NOT NULL,
        UNIQUE(name,scope,scope_key)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS instruction_versions(
        entry_id TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL,
        author TEXT NOT NULL, created_at INTEGER NOT NULL,
        PRIMARY KEY(entry_id,revision)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS instruction_audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id TEXT NOT NULL,
        actor TEXT NOT NULL, action TEXT NOT NULL, revision INTEGER NOT NULL,
        at INTEGER NOT NULL
    )""")
    return conn


def _check_scope(scope, scope_key):
    if scope not in _SCOPES or not isinstance(scope_key, str):
        raise ValueError("Invalid instruction scope")
    if scope == "global":
        if scope_key != "":
            raise ValueError("Global scope cannot have key")
    elif not _CONTEXT.fullmatch(scope_key):
        raise ValueError("Invalid instruction scope key")


def _check_body(body):
    if not isinstance(body, str) or not 1 <= len(body) <= 4000 or "\x00" in body or _SECRET.search(body):
        raise ValueError("Invalid instruction content or potential secret")


def _check_actor(actor):
    if not isinstance(actor, str) or not 1 <= len(actor) <= 128:
        raise ValueError("Invalid author")


def _audit(conn, ident, actor, action, rev):
    conn.execute("INSERT INTO instruction_audit(entry_id,actor,action,revision,at) VALUES(?,?,?,?,?)",
                 (ident, actor, action, rev, int(time.time())))


def create(name: str, scope: str, scope_key: str, body: str, actor: str) -> dict:
    if not isinstance(name, str) or not _KEY.fullmatch(name):
        raise ValueError("Invalid instruction name")
    _check_scope(scope, scope_key)
    _check_body(body)
    _check_actor(actor)
    ident, now = uuid.uuid4().hex, int(time.time())
    db = _db()
    try:
        with db:
            db.execute("INSERT INTO instruction_entries VALUES(?,?,?,?,?,?,?)",
                       (ident, name, scope, scope_key, 1, None, now))
            db.execute("INSERT INTO instruction_versions VALUES(?,?,?,?,?)",
                       (ident, 1, body, actor, now))
            _audit(db, ident, actor, "create", 1)
    finally:
        db.close()
    return {"id": ident, "revision": 1, "status": "draft"}


def _entry(db, ident: str):
    if not isinstance(ident, str) or not re.fullmatch("[0-9a-f]{32}", ident):
        raise ValueError("Invalid instruction identifier")
    row = db.execute("""SELECT id,name,scope,scope_key,revision,published_revision
                          FROM instruction_entries WHERE id=?""", (ident,)).fetchone()
    if row is None:
        raise ValueError("Unknown instruction")
    return row


def save(ident: str, body: str, revision: int, actor: str) -> dict:
    _check_body(body)
    _check_actor(actor)
    if type(revision) is not int or revision < 1:
        raise ValueError("Invalid revision")
    db = _db()
    try:
        with db:
            row = _entry(db, ident)
            if row[4] != revision:
                raise ValueError("Stale instruction revision")
            rev = revision + 1
            db.execute("UPDATE instruction_entries SET revision=? WHERE id=?", (rev, ident))
            db.execute("INSERT INTO instruction_versions VALUES(?,?,?,?,?)",
                       (ident, rev, body, actor, int(time.time())))
            _audit(db, ident, actor, "save", rev)
    finally:
        db.close()
    return {"id": ident, "revision": rev, "status": "draft"}


def publish(ident: str, revision: int, actor: str) -> dict:
    _check_actor(actor)
    if type(revision) is not int:
        raise ValueError("Invalid revision")
    db = _db()
    try:
        with db:
            row = _entry(db, ident)
            if row[4] != revision:
                raise ValueError("Stale instruction revision")
            db.execute("UPDATE instruction_entries SET published_revision=? WHERE id=?",
                       (revision, ident))
            _audit(db, ident, actor, "publish", revision)
    finally:
        db.close()
    return {"id": ident, "published_revision": revision, "status": "published"}


def rollback(ident: str, target_revision: int, current_revision: int, actor: str) -> dict:
    _check_actor(actor)
    if any(type(v) is not int or v < 1 for v in (target_revision, current_revision)):
        raise ValueError("Invalid revision")
    db = _db()
    try:
        with db:
            row = _entry(db, ident)
            if row[4] != current_revision:
                raise ValueError("Stale instruction revision")
            found = db.execute("SELECT 1 FROM instruction_versions WHERE entry_id=? AND revision=?",
                               (ident, target_revision)).fetchone()
            if not found:
                raise ValueError("Unknown rollback revision")
            db.execute("UPDATE instruction_entries SET published_revision=? WHERE id=?",
                       (target_revision, ident))
            _audit(db, ident, actor, "rollback", target_revision)
    finally:
        db.close()
    return {"id": ident, "revision": current_revision,
            "published_revision": target_revision, "status": "published"}


def list_entries(published_only: bool = True, limit: int = 100) -> dict:
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Invalid limit")
    db = _db()
    db.row_factory = sqlite3.Row
    try:
        where = "WHERE e.published_revision IS NOT NULL" if published_only else ""
        rows = db.execute(f"""SELECT e.id,e.name,e.scope,e.scope_key,e.revision,
              e.published_revision, v.body FROM instruction_entries e
              LEFT JOIN instruction_versions v
                ON v.entry_id=e.id AND v.revision=e.published_revision
              {where} ORDER BY e.scope,e.name LIMIT ?""", (limit,)).fetchall()
        return {"instructions": [dict(r) for r in rows]}
    finally:
        db.close()


def get_entry(ident: str, published_only: bool = True) -> dict:
    db = _db()
    db.row_factory = sqlite3.Row
    try:
        row = _entry(db, ident)
        rev = row[5] if published_only else row[4]
        if rev is None:
            raise ValueError("Instruction not published")
        body = db.execute("SELECT body FROM instruction_versions WHERE entry_id=? AND revision=?",
                          (ident, rev)).fetchone()[0]
        return {"id": row[0], "name": row[1], "scope": row[2], "scope_key": row[3],
                "revision": row[4], "published_revision": row[5],
                "body": body}
    finally:
        db.close()


def history(ident: str) -> dict:
    db = _db()
    try:
        _entry(db, ident)
        rows = db.execute("""SELECT revision,author,created_at,body FROM instruction_versions
                             WHERE entry_id=? ORDER BY revision DESC LIMIT 50""",
                          (ident,)).fetchall()
        return {"versions": [{"revision": v, "author": a, "at": at, "body": b}
                             for v, a, at, b in rows]}
    finally:
        db.close()


def resolve(name: str, *, project: str = "", agent: str = "", tool: str = "") -> dict:
    if not isinstance(name, str) or not _KEY.fullmatch(name):
        raise ValueError("Invalid instruction name")
    for key in (project, agent, tool):
        if key and (not isinstance(key, str) or not _CONTEXT.fullmatch(key)):
            raise ValueError("Invalid scope key")
    candidates = [("tool", tool), ("agent", agent), ("project", project), ("global", "")]
    db = _db()
    try:
        for scope, key in candidates:
            if scope != "global" and not key:
                continue
            row = db.execute("""SELECT e.id,e.published_revision,v.body
                FROM instruction_entries e JOIN instruction_versions v
                  ON e.id=v.entry_id AND e.published_revision=v.revision
                WHERE e.name=? AND e.scope=? AND e.scope_key=? AND e.published_revision IS NOT NULL""",
                (name, scope, key)).fetchone()
            if row:
                return {"found": True, "name": name, "id": row[0],
                        "scope": scope, "scope_key": key, "revision": row[1], "body": row[2]}
        return {"found": False, "name": name}
    finally:
        db.close()
