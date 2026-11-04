"""Private repository configuration and leased read-only checks on the selected Agent."""
import hashlib
import hmac
import re
import secrets
import time

import repository_store as store

CODES = frozenset({"OK", "PATH_NOT_FOUND", "PATH_ACCESS_DENIED", "NOT_GIT_ROOT",
                   "ORIGIN_MISMATCH", "REMOTE_UNAVAILABLE", "GIT_UNAVAILABLE", "CHECK_FAILED"})


def _agent(ident):
    if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", ident):
        raise ValueError("Invalid Agent ID")


def request_check(ident, revision, actor):
    from codex_bridge import _enabled
    _enabled()
    with store._db() as db:
        row = store._row(db, ident)
        if type(revision) is not int or row[3] != revision:
            raise store.Conflict("Stale repository revision")
        if not row[5] or not row[6]:
            raise ValueError("Agent and local path required")
        store._expire_checks(db)
        current = db.execute("SELECT status FROM repository_checks WHERE repository_id=?", (ident,)).fetchone()
        if current and current[0] in ("pending", "running"):
            raise store.Conflict("Connection check already running")
        db.execute("DELETE FROM repository_checks WHERE repository_id=?", (ident,))
        db.execute("INSERT INTO repository_checks(id,repository_id,revision,agent_id,status,created_at) VALUES(?,?,?,?,?,?)",
                   (secrets.token_hex(16), ident, revision, row[5], "pending", int(time.time())))
        store._audit(db, actor, ident, "connection-check-requested")
        return {"status": "pending", "agent_id": row[5]}


def configuration(agent_id):
    _agent(agent_id)
    from codex_bridge import _enabled
    with store._db() as db:
        store._expire_checks(db)
        rows = db.execute("SELECT alias,repository,local_path FROM approved_repositories WHERE agent_id=?", (agent_id,)).fetchall()
        result = {"projects": {r[0]: {"repository": r[1], "path": r[2]} for r in rows},
                  "legacy_projects": [r[0] for r in db.execute("SELECT alias FROM approved_repositories WHERE agent_id='' AND local_path=''")],
                  "check": None}
        try:
            _enabled()
        except PermissionError:
            return result
        # One check per poll. A revision change/delete invalidates pending and leased results.
        row = db.execute("""SELECT c.id,r.alias,r.repository,r.local_path FROM repository_checks c
            JOIN approved_repositories r ON r.id=c.repository_id AND r.revision=c.revision AND r.agent_id=c.agent_id
            WHERE c.agent_id=? AND c.status='pending' ORDER BY c.created_at,c.id LIMIT 1""", (agent_id,)).fetchone()
        if row:
            lease = secrets.token_urlsafe(32)
            db.execute("UPDATE repository_checks SET status='running',lease_hash=?,started_at=? WHERE id=?",
                       (hashlib.sha256(lease.encode()).hexdigest(), int(time.time()), row[0]))
            result["check"] = {"id": row[0], "project": row[1], "repository": row[2], "path": row[3], "lease": lease}
        return result


def finish_check(agent_id, check_id, lease, code):
    _agent(agent_id)
    if (not isinstance(check_id, str) or not re.fullmatch(r"[0-9a-f]{32}", check_id)
            or not isinstance(lease, str) or not 1 <= len(lease) <= 128 or code not in CODES):
        raise ValueError("Invalid connection check result")
    with store._db() as db:
        store._expire_checks(db)
        row = db.execute("""SELECT c.status,c.lease_hash FROM repository_checks c JOIN approved_repositories r
            ON r.id=c.repository_id AND r.revision=c.revision AND r.agent_id=c.agent_id
            WHERE c.id=? AND c.agent_id=?""", (check_id, agent_id)).fetchone()
        if row is None or row[0] != "running" or not hmac.compare_digest(row[1], hashlib.sha256(lease.encode()).hexdigest()):
            raise PermissionError("Expired, changed or invalid repository check")
        db.execute("UPDATE repository_checks SET status=?,code=?,finished_at=? WHERE id=?",
                   ("succeeded" if code == "OK" else "failed", code, int(time.time()), check_id))
        return {"ok": True}
