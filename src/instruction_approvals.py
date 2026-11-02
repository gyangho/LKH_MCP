"""Optional two-person instruction publication review ledger.

Enforce LKH_REQUIRE_PEER_REVIEW only with distinct authenticated administrators.
Single-admin deployments may record review requests but cannot self-approve.
"""
import sqlite3
import time
import instruction_store as store


def _connect():
    db = store._db()
    db.execute("""CREATE TABLE IF NOT EXISTS instruction_reviews (
        entry_id TEXT NOT NULL, revision INTEGER NOT NULL, author TEXT NOT NULL,
        reviewer TEXT, state TEXT NOT NULL, submitted_at INTEGER NOT NULL,
        reviewed_at INTEGER, PRIMARY KEY(entry_id, revision)
    )""")
    return db


def request_review(ident: str, revision: int, actor: str) -> dict:
    store._check_actor(actor)
    db = _connect()
    try:
        with db:
            row = store._entry(db, ident)
            if type(revision) is not int or row[4] != revision:
                raise ValueError("Stale revision")
            saved = db.execute("SELECT author FROM instruction_versions WHERE entry_id=? AND revision=?",
                               (ident, revision)).fetchone()
            if not saved or saved[0] != actor:
                raise PermissionError("Only author may request review")
            db.execute("""INSERT INTO instruction_reviews
                (entry_id,revision,author,reviewer,state,submitted_at,reviewed_at)
                VALUES(?,?,?,NULL,'pending',?,NULL)
                ON CONFLICT(entry_id,revision) DO UPDATE SET
                reviewer=NULL,state='pending',submitted_at=excluded.submitted_at,reviewed_at=NULL""",
                (ident, revision, actor, int(time.time())))
            store._audit(db, ident, actor, "request_review", revision)
        return {"id": ident, "revision": revision, "review_state": "pending"}
    finally:
        db.close()


def approve_review(ident: str, revision: int, actor: str) -> dict:
    store._check_actor(actor)
    db = _connect()
    try:
        with db:
            row = store._entry(db, ident)
            if type(revision) is not int or row[4] != revision:
                raise ValueError("Stale revision")
            pending = db.execute("SELECT author,state FROM instruction_reviews WHERE entry_id=? AND revision=?",
                                 (ident, revision)).fetchone()
            if not pending or pending[1] != "pending":
                raise ValueError("Review not pending")
            if pending[0] == actor:
                raise PermissionError("Author cannot self-approve")
            db.execute("""UPDATE instruction_reviews
                SET reviewer=?,state='approved',reviewed_at=?
                WHERE entry_id=? AND revision=?""",
                (actor, int(time.time()), ident, revision))
            store._audit(db, ident, actor, "approve_review", revision)
        return {"id": ident, "revision": revision, "review_state": "approved"}
    finally:
        db.close()


def is_approved(ident: str, revision: int, *, db=None) -> bool:
    own = db is None
    db = db or _connect()
    try:
        try:
            row = db.execute("SELECT state FROM instruction_reviews WHERE entry_id=? AND revision=?",
                             (ident, revision)).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return False
            raise
        return bool(row and row[0] == "approved")
    finally:
        if own: db.close()
