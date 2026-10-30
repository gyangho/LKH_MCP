"""Bounded Windows Codex Agent presence registry.

Heartbeat is an authenticated observation, not proof of a healthy Codex execution.
Only approved project aliases and boolean capability flags are persisted.
"""
from __future__ import annotations

import json
import os
import re

import codex_bridge as bridge

ONLINE_WINDOW_SECONDS = 45
STALE_RETENTION_SECONDS = 30 * 86400
_CAPABILITIES = frozenset({
    "git_installed", "codex_installed", "codex_authenticated", "graphify_installed"
})
_AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _ensure_table(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS codex_agent_presence (
        agent_id TEXT PRIMARY KEY,
        projects TEXT NOT NULL,
        capabilities TEXT NOT NULL,
        last_seen_at INTEGER NOT NULL
    )""")


def heartbeat(agent_id: str, projects: list[str], capabilities: dict) -> dict:
    """Record an authenticated Agent heartbeat after strict payload validation."""
    bridge._enabled()
    if not isinstance(agent_id, str) or not _AGENT_ID.fullmatch(agent_id):
        raise ValueError("Invalid agent ID")
    if (not isinstance(projects, list) or not 1 <= len(projects) <= 10 or
            any(not isinstance(p, str) or not _AGENT_ID.fullmatch(p) for p in projects) or
            len(projects) != len(set(projects))):
        raise ValueError("Invalid project aliases")
    allowed = bridge._allowed()
    if any(p not in allowed for p in projects):
        raise ValueError("Unknown project alias")
    if (not isinstance(capabilities, dict) or set(capabilities) != _CAPABILITIES or
            any(type(value) is not bool for value in capabilities.values())):
        raise ValueError("Invalid capability flags")
    now = bridge._now()
    conn = bridge._connect()
    try:
        with conn:
            _ensure_table(conn)
            conn.execute(
                """INSERT INTO codex_agent_presence(agent_id, projects, capabilities, last_seen_at)
                   VALUES(?,?,?,?)
                   ON CONFLICT(agent_id) DO UPDATE SET
                     projects=excluded.projects, capabilities=excluded.capabilities,
                     last_seen_at=excluded.last_seen_at""",
                (agent_id, json.dumps(sorted(projects)),
                 json.dumps(capabilities, sort_keys=True), now),
            )
            conn.execute("DELETE FROM codex_agent_presence WHERE last_seen_at < ?",
                         (now - STALE_RETENTION_SECONDS,))
    finally:
        conn.close()
    return {"ok": True, "server_time": now}


def agents_snapshot() -> dict:
    """Administrator-only caller exposes bounded, non-secret connection metadata."""
    enabled = bool(bridge.settings_store.get("CODEX_AGENT_ENABLED"))
    configured = len(os.getenv("CODEX_AGENT_TOKEN", "")) >= 32
    now = bridge._now()
    conn = bridge._connect()
    conn.row_factory = __import__("sqlite3").Row
    try:
        _ensure_table(conn)
        rows = conn.execute(
            "SELECT agent_id,projects,capabilities,last_seen_at "
            "FROM codex_agent_presence ORDER BY last_seen_at DESC LIMIT 20"
        ).fetchall()
        running = {r["agent_id"]: {"id": r["id"], "project": r["project"], "kind": r["kind"]}
                   for r in conn.execute(
                       "SELECT id,agent_id,project,kind FROM codex_agent_jobs "
                       "WHERE state='running' AND agent_id IS NOT NULL"
                   )}
    finally:
        conn.close()
    agents = []
    for row in rows:
        age = now - row["last_seen_at"]
        online = enabled and configured and 0 <= age <= ONLINE_WINDOW_SECONDS
        task = running.get(row["agent_id"])
        agents.append({
            "agent_id": row["agent_id"],
            "last_seen_at": row["last_seen_at"],
            "seconds_since_seen": max(0, age),
            "online": online,
            "busy": bool(online and task),
            "projects": json.loads(row["projects"]),
            "capabilities": json.loads(row["capabilities"]),
            "current_task": task,
        })
    return {"enabled": enabled, "token_configured": configured,
            "online_window_seconds": ONLINE_WINDOW_SECONDS,
            "server_time": now, "agents": agents}
