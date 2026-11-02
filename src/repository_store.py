"""Structured repository approvals, migrated once from the legacy setting."""
from __future__ import annotations
import json
import os
import re
import secrets
import time
from contextlib import contextmanager
import settings_store


class Conflict(ValueError): pass
class NotFound(ValueError): pass


def validate(alias, repository):
    if not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", alias):
        raise ValueError("Invalid project alias")
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,38}/[A-Za-z0-9_.-]{1,100}", repository) or repository.split("/")[1] in (".", ".."):
        raise ValueError("Use GitHub owner/repository")
    return alias, repository


def _prepare(db):
    db.execute("""CREATE TABLE IF NOT EXISTS approved_repositories (
        id TEXT PRIMARY KEY, alias TEXT NOT NULL UNIQUE, repository TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL)""")
    db.execute("CREATE TABLE IF NOT EXISTS repository_migrations (name TEXT PRIMARY KEY)")
    if db.execute("SELECT 1 FROM repository_migrations WHERE name='semicolon-v1'").fetchone():
        return
    has_settings = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'").fetchone()
    old = db.execute("SELECT value FROM settings WHERE name='GIT_ALLOWED_REPOS'").fetchone() if has_settings else None
    raw = json.loads(old[0]) if old else os.environ.get("GIT_ALLOWED_REPOS", "")
    if not isinstance(raw, str): raise ValueError("Invalid legacy repository approvals")
    entries = []
    for entry in raw.split(";") if raw else []:
        if "=" not in entry: raise ValueError("Invalid legacy repository approvals")
        alias, repository = (x.strip() for x in entry.split("=", 1))
        entries.append(validate(alias, repository))
    if len(entries) > 10 or len({alias for alias, _ in entries}) != len(entries):
        raise ValueError("Invalid legacy repository approvals")
    for alias, repository in entries:
        db.execute("INSERT INTO approved_repositories(id,alias,repository,updated_at) VALUES(?,?,?,?)",
                   (secrets.token_hex(12), alias, repository, settings_store._timestamp()))
    db.execute("INSERT INTO repository_migrations(name) VALUES('semicolon-v1')")


@contextmanager
def _db():
    settings_store.initialize()
    db = settings_store._connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        _prepare(db)
        yield db
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    finally: db.close()


def mapping(db=None):
    if db is not None:
        _prepare(db)
        return dict(db.execute("SELECT alias,repository FROM approved_repositories"))
    with _db() as conn:
        return mapping(conn)


def _row(db, ident):
    if not isinstance(ident, str) or not re.fullmatch(r"[0-9a-f]{24}", ident): raise NotFound()
    row = db.execute("SELECT id,alias,repository,revision,updated_at FROM approved_repositories WHERE id=?", (ident,)).fetchone()
    if row is None: raise NotFound()
    return row


def _public(row):
    return dict(zip(("id", "alias", "repository", "revision", "updated_at"), row))


def list_repositories():
    with _db() as db:
        return [_public(row) for row in db.execute("SELECT id,alias,repository,revision,updated_at FROM approved_repositories ORDER BY alias")]


def _audit(db, actor, ident, action):
    if not isinstance(actor, str) or not 1 <= len(actor) <= 256: raise ValueError("Invalid actor")
    db.execute("INSERT INTO audit(at,actor,name,old_value,new_value) VALUES(?,?,?,?,?)",
               (settings_store._timestamp(), actor, "repository:"+ident, "", action))


def _revoke_jobs(db, alias):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='codex_agent_jobs'").fetchone(): return 0
    if db.execute("SELECT 1 FROM codex_agent_jobs WHERE project=? AND state='running'", (alias,)).fetchone():
        raise Conflict("A job is running for this project")
    return db.execute("UPDATE codex_agent_jobs SET state='cancelled',finished_at=?,error='Repository approval changed' WHERE project=? AND state IN ('queued','pending_approval')", (int(time.time()), alias)).rowcount


def create(alias, repository, actor):
    alias, repository = validate(alias, repository)
    with _db() as db:
        if db.execute("SELECT COUNT(*) FROM approved_repositories").fetchone()[0] >= 10: raise Conflict("Maximum 10 approvals")
        if db.execute("SELECT 1 FROM approved_repositories WHERE alias=?", (alias,)).fetchone(): raise Conflict("Duplicate alias")
        ident = secrets.token_hex(12)
        db.execute("INSERT INTO approved_repositories(id,alias,repository,updated_at) VALUES(?,?,?,?)", (ident, alias, repository, settings_store._timestamp()))
        _audit(db, actor, ident, "create")
        return _public(_row(db, ident))


def update(ident, revision, alias, repository, actor):
    alias, repository = validate(alias, repository)
    with _db() as db:
        row = _row(db, ident)
        if type(revision) is not int or revision != row[3]: raise Conflict("Stale revision")
        if db.execute("SELECT 1 FROM approved_repositories WHERE alias=? AND id<>?", (alias, ident)).fetchone(): raise Conflict("Duplicate alias")
        cancelled = _revoke_jobs(db, row[1]) if (alias, repository) != (row[1], row[2]) else 0
        db.execute("UPDATE approved_repositories SET alias=?,repository=?,revision=revision+1,updated_at=? WHERE id=?", (alias, repository, settings_store._timestamp(), ident))
        _audit(db, actor, ident, "update")
        return {**_public(_row(db, ident)), "cancelled_jobs": cancelled}


def delete(ident, revision, actor):
    with _db() as db:
        row = _row(db, ident)
        if type(revision) is not int or revision != row[3]: raise Conflict("Stale revision")
        cancelled = _revoke_jobs(db, row[1])
        db.execute("DELETE FROM approved_repositories WHERE id=?", (ident,))
        _audit(db, actor, ident, "delete")
        return {"deleted": True, "cancelled_jobs": cancelled}
