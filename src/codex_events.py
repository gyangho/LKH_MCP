"""Phase 1: append-only, bounded Codex execution events (metadata only).

The server never stores raw Codex JSONL, prompts, arguments, command output,
paths or file contents. Agent events are lease-authenticated and sequence-idempotent.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import sqlite3
import time

import codex_bridge

JOB_ID = re.compile(r"^[0-9a-f]{32}$")
AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
EVENT_TYPES = frozenset({
    "started", "turn_started", "turn_completed", "item_started", "item_completed",
    "item_failed", "command_started", "command_completed", "command_failed",
    "heartbeat", "error", "finished",
})
PHASES = frozenset({"codex", "git", "build", "test", "graphify", "cleanup", "unknown"})
RETENTION_SECONDS = 14 * 86400
MAX_EVENTS_PER_JOB = 2000


def _connect():
    db = codex_bridge._connect()
    db.execute("""CREATE TABLE IF NOT EXISTS codex_task_events (
      task_id TEXT NOT NULL, seq INTEGER NOT NULL, at INTEGER NOT NULL,
      event_type TEXT NOT NULL, phase TEXT NOT NULL,
      PRIMARY KEY (task_id, seq)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS codex_event_age ON codex_task_events(at)")
    return db


def append(task_id: str, agent_id: str, lease: str, events: list[dict]) -> dict:
    if not isinstance(task_id, str) or not JOB_ID.fullmatch(task_id):
        raise ValueError("Invalid task")
    if not isinstance(agent_id, str) or not AGENT_ID.fullmatch(agent_id):
        raise ValueError("Invalid agent")
    if not isinstance(lease, str) or not 32 <= len(lease) <= 128:
        raise ValueError("Invalid lease")
    if not isinstance(events, list) or not 1 <= len(events) <= 32:
        raise ValueError("Invalid event batch")
    normalized = []
    for e in events:
        if not isinstance(e, dict) or set(e) != {"seq", "type", "phase"}:
            raise ValueError("Unexpected event fields")
        seq, kind, phase = e["seq"], e["type"], e["phase"]
        if type(seq) is not int or not 1 <= seq <= MAX_EVENTS_PER_JOB:
            raise ValueError("Invalid event sequence")
        if kind not in EVENT_TYPES or phase not in PHASES:
            raise ValueError("Invalid event metadata")
        normalized.append((seq, kind, phase))
    db = _connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("""SELECT state,agent_id,lease_token_hash,claimed_at
            FROM codex_agent_jobs WHERE id=?""", (task_id,)).fetchone()
        if (row is None or row[0] != "running" or row[1] != agent_id or
                not row[2] or
                not hmac.compare_digest(row[2], hashlib.sha256(lease.encode()).hexdigest()) or
                int(time.time()) - row[3] > codex_bridge._LEASE):
            raise PermissionError("Agent lease invalid")
        current = db.execute(
            "SELECT COUNT(*) FROM codex_task_events WHERE task_id=?", (task_id,)).fetchone()[0]
        if current + len(normalized) > MAX_EVENTS_PER_JOB:
            raise ValueError("Task event limit exceeded")
        now = int(time.time())
        db.executemany("""INSERT OR IGNORE INTO codex_task_events
            (task_id,seq,at,event_type,phase) VALUES(?,?,?,?,?)""",
            [(task_id, n, now, kind, phase) for n, kind, phase in normalized])
        db.execute("DELETE FROM codex_task_events WHERE at<?", (now - RETENTION_SECONDS,))
        db.commit()
        return {"accepted": len(normalized), "task_id": task_id}
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def read(task_id: str, after: int = 0, limit: int = 100) -> dict:
    if not isinstance(task_id, str) or not JOB_ID.fullmatch(task_id):
        raise ValueError("Invalid task")
    if type(after) is not int or after < 0 or after > MAX_EVENTS_PER_JOB:
        raise ValueError("Invalid cursor")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Invalid limit")
    db = _connect()
    db.row_factory = sqlite3.Row
    try:
        if not db.execute("SELECT 1 FROM codex_agent_jobs WHERE id=?", (task_id,)).fetchone():
            raise ValueError("Unknown task")
        rows = db.execute("""SELECT seq,at,event_type,phase FROM codex_task_events
            WHERE task_id=? AND seq>? ORDER BY seq LIMIT ?""", (task_id, after, limit)).fetchall()
        events = [{"seq": r["seq"], "at": r["at"], "type": r["event_type"],
                   "phase": r["phase"]} for r in rows]
        return {"task_id": task_id, "events": events,
                "cursor": events[-1]["seq"] if events else after}
    finally:
        db.close()
