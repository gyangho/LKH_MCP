"""Admin-gated idempotent retry for failed non-mutating Codex jobs.

The retry gets a new lease; old SHA and repository remain unchanged.
Fix jobs cannot be replayed, even by an administrator.
"""
import re
import uuid
import codex_bridge as bridge

_ID = re.compile(r"^[0-9a-f]{32}$")


def retry_failed(task_id: str, actor: str) -> dict:
    bridge._enabled()
    if not isinstance(task_id, str) or not _ID.fullmatch(task_id):
        raise ValueError("Invalid task ID")
    if not isinstance(actor, str) or not 1 <= len(actor) <= 128:
        raise ValueError("Invalid actor")
    db = bridge._connect()
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS codex_job_retries(
            source_id TEXT PRIMARY KEY, retry_id TEXT NOT NULL UNIQUE,
            actor TEXT NOT NULL, created_at INTEGER NOT NULL)""")
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("""SELECT project,repository,branch,expected_sha,kind,instructions,state
            FROM codex_agent_jobs WHERE id=?""", (task_id,)).fetchone()
        if old is None or old[6] != "failed" or old[4] not in ("verify", "diagnose", "graphify"):
            raise ValueError("Only failed non-fix tasks can be retried")
        if bridge._allowed(db).get(old[0]) != old[1]:
            raise PermissionError("Repository no longer allowlisted")
        prior = db.execute("SELECT retry_id FROM codex_job_retries WHERE source_id=?",
                           (task_id,)).fetchone()
        if prior:
            row = db.execute("SELECT state FROM codex_agent_jobs WHERE id=?", (prior[0],)).fetchone()
            db.commit()
            return {"id": prior[0], "retry_of": task_id,
                    "state": row[0] if row else "unknown", "reused": True}
        count = db.execute("SELECT COUNT(*) FROM codex_agent_jobs WHERE state IN ('queued','pending_approval','running')").fetchone()[0]
        if count >= 100:
            raise RuntimeError("Queue full")
        now = bridge._now()
        limit = bridge.settings_store.get("CODEX_MAX_RUNS_PER_DAY")
        used = db.execute("SELECT COUNT(*) FROM codex_agent_jobs WHERE claimed_at>=?",
                          (now - 86400,)).fetchone()[0]
        if used >= limit:
            raise RuntimeError("Daily quota reached")
        new_id = uuid.uuid4().hex
        db.execute("""INSERT INTO codex_agent_jobs
            (id,project,repository,branch,expected_sha,kind,instructions,state,actor,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (new_id, old[0], old[1], old[2], old[3], old[4], old[5], "queued", actor, now))
        db.execute("INSERT INTO codex_job_retries VALUES(?,?,?,?)",
                   (task_id, new_id, actor, now))
        db.commit()
        return {"id": new_id, "retry_of": task_id, "state": "queued", "reused": False}
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
