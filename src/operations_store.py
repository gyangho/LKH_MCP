"""Phases 7/8: bounded persistent metadata-only operations log and metrics.

Never persist raw HTTP paths with query parameters, headers, prompts, tool
arguments, DB rows, command outputs or exception messages.
"""
from __future__ import annotations

import re
import sqlite3
import time

import settings_store

_MAX_ROWS = 50000
_RETENTION = 30 * 86400
_LABEL = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def _db():
    db = settings_store._connect()
    db.execute("""CREATE TABLE IF NOT EXISTS operation_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at INTEGER NOT NULL, category TEXT NOT NULL, name TEXT NOT NULL,
        result TEXT NOT NULL, duration_ms INTEGER NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS operation_events_at ON operation_events(at)")
    return db


def record(category: str, name: str, result: str, duration_ms: int = 0) -> None:
    for label in (category, name, result):
        if not isinstance(label, str) or not _LABEL.fullmatch(label):
            raise ValueError("Unsafe telemetry label")
    if type(duration_ms) is not int or not 0 <= duration_ms <= 3600000:
        raise ValueError("Invalid duration")
    db = _db()
    try:
        with db:
            now = int(time.time())
            db.execute("INSERT INTO operation_events(at,category,name,result,duration_ms) VALUES(?,?,?,?,?)",
                       (now, category, name, result, duration_ms))
            db.execute("DELETE FROM operation_events WHERE at<?", (now - _RETENTION,))
            db.execute("""DELETE FROM operation_events WHERE id IN (
                SELECT id FROM operation_events ORDER BY id DESC LIMIT -1 OFFSET ?)""",
                       (_MAX_ROWS,))
    finally:
        db.close()


def read_events(*, cursor: int = 0, limit: int = 100, category: str = "") -> dict:
    if type(cursor) is not int or cursor < 0:
        raise ValueError("Invalid cursor")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Invalid limit")
    if category and (not isinstance(category, str) or not _LABEL.fullmatch(category)):
        raise ValueError("Invalid category")
    db = _db()
    db.row_factory = sqlite3.Row
    try:
        conditions, args = ["id>?"], [cursor]
        if category:
            conditions.append("category=?")
            args.append(category)
        rows = db.execute("""SELECT id,at,category,name,result,duration_ms
            FROM operation_events WHERE """ + " AND ".join(conditions) +
            " ORDER BY id ASC LIMIT ?", (*args, limit)).fetchall()
        data = [dict(row) for row in rows]
        return {"events": data, "cursor": data[-1]["id"] if data else cursor,
                "retention_days": 30}
    finally:
        db.close()


def metrics(window_minutes: int = 60) -> dict:
    if type(window_minutes) is not int or not 1 <= window_minutes <= 1440:
        raise ValueError("Invalid window")
    db = _db()
    try:
        start = int(time.time()) - window_minutes * 60
        rows = db.execute("""SELECT (at / 60) * 60 AS minute,
                        COUNT(*) total,
                        SUM(CASE WHEN result='error' THEN 1 ELSE 0 END) failed,
                        ROUND(AVG(duration_ms),1) avg_ms
                        FROM operation_events WHERE at>=?
                        GROUP BY minute ORDER BY minute""", (start,)).fetchall()
        return {"window_minutes": window_minutes,
                "buckets": [{"minute": at, "requests": total,
                             "errors": failed, "avg_duration_ms": avg}
                            for at, total, failed, avg in rows]}
    finally:
        db.close()
