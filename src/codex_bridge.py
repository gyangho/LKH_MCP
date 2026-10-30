"""Durable GitHub->Windows Codex task queue. This module never touches local repositories.

All local Git, Graphify and test work happens in windows_agent/agent.py.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
import zlib
from typing import Any

import settings_store

_NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH = re.compile(r"^(?![-/.])(?!.*(?:\.\.|//|@\{|\.lock(?:/|$)))[A-Za-z0-9_.\-/]{1,120}$")
_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_ID = re.compile(r"^[0-9a-f]{32}$")
_KINDS = {"verify", "diagnose", "fix", "graphify"}
_RETENTION = 30 * 86400
_LEASE = 60 * 60
_MAX_GRAPH_COMPRESSED = 4_000_000
_MAX_GRAPH_JSON = 32_000_000


def _now() -> int:
    return int(time.time())


def _allowed() -> dict[str, str]:
    raw = settings_store.get("GIT_ALLOWED_REPOS")
    mapping = {}
    if not raw:
        return mapping
    for part in raw.split(";"):
        if "=" not in part:
            raise ValueError("GIT_ALLOWED_REPOS must be PROJECT=owner/repo;...")
        name, repo = (v.strip() for v in part.split("=", 1))
        if not _NAME.fullmatch(name) or not _REPO.fullmatch(repo) or name in mapping:
            raise ValueError("Invalid Git repository allowlist")
        mapping[name] = repo
    if len(mapping) > 10:
        raise ValueError("Maximum 10 repositories")
    return mapping


def _enabled() -> None:
    if not settings_store.get("CODEX_AGENT_ENABLED"):
        raise PermissionError("Enable CODEX_AGENT_ENABLED in private admin settings")


def _connect() -> sqlite3.Connection:
    conn = settings_store._connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS codex_agent_jobs (
        id TEXT PRIMARY KEY, project TEXT NOT NULL, repository TEXT NOT NULL,
        branch TEXT NOT NULL, expected_sha TEXT NOT NULL, kind TEXT NOT NULL,
        instructions TEXT NOT NULL, state TEXT NOT NULL, actor TEXT NOT NULL,
        created_at INTEGER NOT NULL, approved_at INTEGER, claimed_at INTEGER,
        finished_at INTEGER, agent_id TEXT, lease_token_hash TEXT,
        report TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT ''
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS codex_job_state_idx ON codex_agent_jobs(state, created_at)")
    conn.execute("""CREATE TABLE IF NOT EXISTS codex_graphs (
        project TEXT PRIMARY KEY, repository TEXT NOT NULL, commit_sha TEXT NOT NULL,
        graph_zlib BLOB NOT NULL, published_at INTEGER NOT NULL,
        nodes INTEGER NOT NULL, edges INTEGER NOT NULL
    )""")
    return conn


def _public(row: sqlite3.Row) -> dict[str, Any]:
    allowed = ("id", "project", "repository", "branch", "expected_sha", "kind", "state",
               "actor", "created_at", "approved_at", "claimed_at", "finished_at",
               "agent_id", "report", "error")
    return {k: row[k] for k in allowed}


def enqueue(project: str, branch: str, expected_sha: str, kind: str = "verify",
            instructions: str = "", actor: str = "chatgpt") -> dict:
    _enabled()
    allowed = _allowed()
    if not isinstance(project, str) or project not in allowed:
        raise ValueError("Project not in GIT_ALLOWED_REPOS")
    if not isinstance(branch, str) or not _BRANCH.fullmatch(branch) or branch.endswith(("/", ".")):
        raise ValueError("Invalid branch")
    if not isinstance(expected_sha, str) or not _SHA.fullmatch(expected_sha):
        raise ValueError("Expected 40-character GitHub commit SHA")
    if kind not in _KINDS:
        raise ValueError("Unsupported task type")
    if not isinstance(instructions, str) or len(instructions) > 2000 or "\x00" in instructions:
        raise ValueError("Instructions must be under 2000 characters")
    if not isinstance(actor, str) or not 1 <= len(actor) <= 128:
        raise ValueError("Invalid actor")
    if kind == "fix" and len(instructions.strip()) < 12:
        raise ValueError("Fix tasks need a specific change request")
    # Fixes remain gated; a queued verification cannot run arbitrary write requests.
    state = "pending_approval" if kind == "fix" else "queued"
    task_id = uuid.uuid4().hex
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT COUNT(*) FROM codex_agent_jobs WHERE state IN ('queued','pending_approval','running')").fetchone()[0] >= 100:
            raise RuntimeError("Job queue full")
        conn.execute("""INSERT INTO codex_agent_jobs
          (id,project,repository,branch,expected_sha,kind,instructions,state,actor,created_at)
          VALUES(?,?,?,?,?,?,?,?,?,?)""",
          (task_id, project, allowed[project], branch, expected_sha.lower(), kind, instructions,
           state, actor, _now()))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return {"id": task_id, "state": state, "project": project, "repository": allowed[project],
            "branch": branch, "expected_sha": expected_sha.lower(), "kind": kind,
            "note": "Windows Agent handles local Git; fix requires admin approval"}


def decide(task_id: str, action: str, actor: str) -> dict:
    _enabled()
    if not _ID.fullmatch(task_id or "") or action not in {"approve", "reject", "cancel"}:
        raise ValueError("Invalid task or decision")
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT state FROM codex_agent_jobs WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown task")
        if action == "approve" and row[0] == "pending_approval":
            state = "queued"
        elif action in ("reject", "cancel") and row[0] in ("pending_approval", "queued"):
            state = "cancelled"
        else:
            raise ValueError("Task cannot be changed in its current state")
        conn.execute("UPDATE codex_agent_jobs SET state=?, approved_at=? WHERE id=?",
                     (state, _now() if action == "approve" else None, task_id))
        conn.execute("COMMIT")
        return {"id": task_id, "state": state, "actor": actor}
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def list_tasks(limit: int = 30) -> dict:
    limit = max(1, min(50, limit))
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM codex_agent_jobs ORDER BY created_at DESC,id DESC LIMIT ?", (limit,)).fetchall()
        return {"tasks": [_public(r) for r in rows]}
    finally:
        conn.close()


def get_task(task_id: str) -> dict:
    if not _ID.fullmatch(task_id or ""):
        raise ValueError("Invalid job ID")
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM codex_agent_jobs WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown task")
        return _public(row)
    finally:
        conn.close()


def check_agent_token(header: str) -> bool:
    if os.getenv("LKH_NATIVE_MODE") == "1":
        from native_enrollment import check_access
        return check_access(header)
    stored = os.getenv("CODEX_AGENT_TOKEN", "")
    if len(stored) < 32 or not stored.isascii():
        return False
    prefix = "Bearer "
    if not isinstance(header, str) or not header.startswith(prefix):
        return False
    token = header[len(prefix):]
    return len(token) <= 256 and hmac.compare_digest(token, stored)


def claim(agent_id: str, projects: list[str]) -> dict:
    _enabled()
    if not isinstance(agent_id, str) or not _NAME.fullmatch(agent_id):
        raise ValueError("Invalid agent ID")
    if not isinstance(projects, list) or not projects or len(projects) > 10 or any(
            not isinstance(p, str) or not _NAME.fullmatch(p) for p in projects):
        raise ValueError("Invalid project aliases")
    projects = sorted(set(projects).intersection(_allowed()))
    if not projects:
        return {"job": None}
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        now = _now()
        # Do not silently requeue a job after an agent crash. Pull/fix may have run.
        conn.execute("""UPDATE codex_agent_jobs SET state='failed',finished_at=?,error='Agent lease timed out; inspect local state before retry'
                        WHERE state='running' AND claimed_at<?""", (now, now - _LEASE))
        if conn.execute("SELECT COUNT(*) FROM codex_agent_jobs WHERE state='running'").fetchone()[0]:
            conn.execute("COMMIT")
            return {"job": None, "reason": "busy"}
        quota = settings_store.get("CODEX_MAX_RUNS_PER_DAY")
        used = conn.execute("SELECT COUNT(*) FROM codex_agent_jobs WHERE claimed_at>=?", (now - 86400,)).fetchone()[0]
        if used >= quota:
            conn.execute("COMMIT")
            return {"job": None, "reason": "daily_limit", "used": used, "limit": quota}
        placeholders = ",".join("?" for _ in projects)
        row = conn.execute(f"SELECT * FROM codex_agent_jobs WHERE state='queued' AND project IN ({placeholders}) ORDER BY created_at,id LIMIT 1", projects).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return {"job": None}
        lease = secrets.token_urlsafe(32)
        conn.execute("""UPDATE codex_agent_jobs SET state='running',claimed_at=?,agent_id=?,lease_token_hash=?
                        WHERE id=? AND state='queued'""",
                     (now, agent_id, hashlib.sha256(lease.encode()).hexdigest(), row["id"]))
        conn.execute("COMMIT")
        return {"job": {k: row[k] for k in ("id", "project", "repository", "branch", "expected_sha", "kind", "instructions")},
                "lease": lease, "deadline_seconds": _LEASE}
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def _graph_details(raw: bytes) -> tuple[bytes, int, int]:
    if len(raw) > _MAX_GRAPH_COMPRESSED:
        raise ValueError("Compressed graph too large")
    dec = zlib.decompressobj()
    payload = dec.decompress(raw, _MAX_GRAPH_JSON + 1)
    if len(payload) > _MAX_GRAPH_JSON or not dec.eof or dec.unused_data or dec.unconsumed_tail:
        raise ValueError("Graph decompression limit exceeded")
    obj = json.loads(payload)
    nodes = obj.get("nodes") if isinstance(obj, dict) else None
    edges = obj.get("links", obj.get("edges")) if isinstance(obj, dict) else None
    if not isinstance(nodes, list) or not isinstance(edges, list) or len(nodes) > 100000 or len(edges) > 250000:
        raise ValueError("Not a supported Graphify node-link graph")
    return raw, len(nodes), len(edges)


def complete(task_id: str, lease: str, agent_id: str, success: bool,
             report: str, error: str = "", graph_base64: str = "") -> dict:
    import base64
    _enabled()
    if not _ID.fullmatch(task_id or "") or not isinstance(lease, str) or len(lease) > 128:
        raise ValueError("Invalid task identity")
    if not isinstance(agent_id, str) or not _NAME.fullmatch(agent_id) or type(success) is not bool:
        raise ValueError("Invalid result")
    if any(not isinstance(x, str) for x in (report, error, graph_base64)) or len(report) > 16000 or len(error) > 2000:
        raise ValueError("Oversized result")
    if len(graph_base64) > 5_400_000:
        raise ValueError("Graph upload too large")
    graph = None
    if graph_base64:
        if not success:
            raise ValueError("Cannot publish graph on failed job")
        graph = _graph_details(base64.b64decode(graph_base64, validate=True))
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM codex_agent_jobs WHERE id=?", (task_id,)).fetchone()
        if row is None or row["state"] != "running" or row["agent_id"] != agent_id or not row["lease_token_hash"] or not hmac.compare_digest(row["lease_token_hash"], hashlib.sha256(lease.encode()).hexdigest()):
            raise PermissionError("Job lease mismatch or already finished")
        if _now() - row["claimed_at"] > _LEASE:
            raise PermissionError("Expired lease")
        if graph is not None and row["kind"] != "graphify":
            raise ValueError("Only graphify tasks can publish graph data")
        if graph is not None:
            conn.execute("""INSERT INTO codex_graphs (project,repository,commit_sha,graph_zlib,published_at,nodes,edges)
                            VALUES (?,?,?,?,?,?,?)
                            ON CONFLICT(project) DO UPDATE SET repository=excluded.repository,
                            commit_sha=excluded.commit_sha,graph_zlib=excluded.graph_zlib,
                            published_at=excluded.published_at,nodes=excluded.nodes,edges=excluded.edges""",
                         (row["project"], row["repository"], row["expected_sha"], graph[0], _now(), graph[1], graph[2]))
        conn.execute("UPDATE codex_agent_jobs SET state=?,finished_at=?,report=?,error=? WHERE id=?",
                     ("completed" if success else "failed", _now(), report, error, task_id))
        conn.execute("COMMIT")
        return {"id": task_id, "state": "completed" if success else "failed", "graph_published": graph is not None}
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def graph_list() -> dict:
    conn = _connect()
    try:
        return {"projects": [{"project": p, "repository": r, "commit_sha": s, "published_at": at,
                              "nodes": n, "edges": e}
                             for p, r, s, at, n, e in conn.execute("SELECT project,repository,commit_sha,published_at,nodes,edges FROM codex_graphs ORDER BY project")]}
    finally:
        conn.close()


def graph_query(project: str, term: str, limit: int = 12) -> dict:
    allowed = _allowed()
    if project not in allowed:
        raise ValueError("Unknown project")
    if not isinstance(term, str) or not 2 <= len(term) <= 120:
        raise ValueError("Search term must be 2-120 characters")
    if type(limit) is not int:
        raise ValueError("limit must be an integer")
    limit = min(25, max(1, limit))
    conn = _connect()
    try:
        row = conn.execute("SELECT repository,commit_sha,graph_zlib FROM codex_graphs WHERE project=?", (project,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"project": project, "error": "No graph synced yet; queue graphify task"}
    repo, sha, blob = row
    if repo != allowed[project]:
        raise ValueError("Repository mapping changed; graph must be refreshed")
    data = json.loads(zlib.decompress(blob))
    nodes = data.get("nodes", [])
    edges = data.get("links", data.get("edges", []))
    needle = term.casefold()
    matches = [node for node in nodes if isinstance(node, dict) and needle in " ".join(
        str(node.get(k, "")) for k in ("id", "label", "source_file", "node_type")).casefold()][:limit]
    ids = {str(n.get("id")) for n in matches}
    linked = [e for e in edges if isinstance(e, dict) and (
        str(e.get("source", e.get("_src", ""))) in ids or str(e.get("target", e.get("_tgt", ""))) in ids)][:limit * 4]
    keys_n = ("id", "label", "source_file", "source_location", "file_type", "node_type")
    keys_e = ("source", "target", "_src", "_tgt", "relation", "confidence")
    return {"project": project, "repository": repo, "graph_commit_sha": sha,
            "matches": [{k: str(n[k])[:300] for k in keys_n if k in n} for n in matches],
            "edges": [{k: str(e[k])[:300] for k in keys_e if k in e} for e in linked],
            "note": "Graph is a structural hint only; check current GitHub source and SHA"}


def register_codex_tools(mcp: Any) -> None:
    @mcp.tool()
    def codex_enqueue(project: str, branch: str, expected_sha: str,
                      kind: str = "verify", instructions: str = "") -> dict:
        """Queue Windows-only Codex: verify, diagnose, graphify, or approval-gated fix. No local repository access here."""
        return enqueue(project, branch, expected_sha, kind, instructions)

    @mcp.tool()
    def codex_list_tasks() -> dict:
        """List Windows Codex queue task states and brief results."""
        return list_tasks()

    @mcp.tool()
    def codex_get_task(task_id: str) -> dict:
        """Read Windows Codex build/test/diagnosis results."""
        return get_task(task_id)

    @mcp.tool()
    def graphify_list_projects() -> dict:
        """List Graphify graph snapshots synced from Windows; includes commit SHA."""
        return graph_list()

    @mcp.tool()
    def graphify_query(project: str, term: str, limit: int = 12) -> dict:
        """Search synced Graphify node-link graph without opening Windows files."""
        return graph_query(project, term, limit)

    @mcp.tool()
    def graphify_explain(project: str, concept: str) -> dict:
        """Locate a concept in the synced graph and show direct relationships."""
        found = graph_query(project, concept, 8)
        if not found.get("matches"):
            return found
        found["neighbors"] = graph_neighbors(project, str(found["matches"][0]["id"]), 16)["edges"]
        return found

    @mcp.tool()
    def graphify_neighbors(project: str, node_id: str, limit: int = 20) -> dict:
        """Return bounded relationships for a Graphify node ID."""
        return graph_neighbors(project, node_id, limit)

    @mcp.tool()
    def graphify_path(project: str, source: str, target: str, max_depth: int = 7) -> dict:
        """Bounded BFS between Graphify nodes on the synced graph."""
        return graph_path(project, source, target, max_depth)


def graph_neighbors(project: str, node_id: str, limit: int = 20) -> dict:
    """Inspect immediate edges of one node in the synced graph."""
    if not isinstance(node_id, str) or not 1 <= len(node_id) <= 160:
        raise ValueError("Invalid node ID")
    graph = _graph_for(project)
    node_ids = {node_id}
    if type(limit) is not int:
        raise ValueError("limit must be an integer")
    neighbors = [e for e in graph["edges"] if isinstance(e, dict) and
                 (str(e.get("source", "")) in node_ids or str(e.get("target", "")) in node_ids)][:max(1, min(50, limit))]
    return {"project": project, "graph_commit_sha": graph["sha"],
            "edges": [{k: str(v)[:300] for k, v in e.items()
                       if k in ("source", "target", "relation", "confidence")} for e in neighbors]}

def _graph_for(project: str) -> dict:
    allowed = _allowed()
    if project not in allowed:
        raise ValueError("Unknown project")
    conn = _connect()
    try:
        row = conn.execute("SELECT repository,commit_sha,graph_zlib FROM codex_graphs WHERE project=?", (project,)).fetchone()
    finally:
        conn.close()
    if row is None or row[0] != allowed[project]:
        raise ValueError("No current graph snapshot")
    graph = json.loads(zlib.decompress(row[2]))
    return {"sha": row[1], "nodes": graph.get("nodes", []),
            "edges": graph.get("links", graph.get("edges", []))}

def graph_path(project: str, source: str, target: str, max_depth: int = 7) -> dict:
    """Bounded BFS over Graphify node-link IDs; not a live source lookup."""
    from collections import deque
    if not isinstance(source, str) or not isinstance(target, str) or not 1 <= len(source) <= 160 or not 1 <= len(target) <= 160:
        raise ValueError("Invalid node IDs")
    if type(max_depth) is not int or not 1 <= max_depth <= 10:
        raise ValueError("Depth must be 1-10")
    g = _graph_for(project)
    adj = {}
    for e in g["edges"]:
        if not isinstance(e, dict):
            continue
        a, b = str(e.get("source", "")), str(e.get("target", ""))
        if a and b:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    queue = deque([(source, [source])]); seen = {source}
    while queue:
        node, path = queue.popleft()
        if node == target:
            return {"project": project, "graph_commit_sha": g["sha"], "path": path}
        if len(path) > max_depth:
            continue
        for next_id in sorted(adj.get(node, [])):
            if next_id not in seen:
                seen.add(next_id); queue.append((next_id, path + [next_id]))
    return {"project": project, "graph_commit_sha": g["sha"], "path": [], "note": "No path within depth limit"}
