"""Read-only monitoring summary: queue backlog, expired leases, offline Agents, errors."""
import time
import codex_bridge
import codex_presence
import operations_store


def snapshot(*, max_queued=25, max_error_ratio=0.25, min_samples=10) -> dict:
    if max_queued < 1 or not 0 < max_error_ratio <= 1 or min_samples < 1:
        raise ValueError("Invalid threshold")
    db = codex_bridge._connect()
    try:
        queue = dict(db.execute("SELECT state,COUNT(*) FROM codex_agent_jobs GROUP BY state"))
        stale = db.execute("SELECT COUNT(*) FROM codex_agent_jobs WHERE state='running' AND claimed_at<?",
                           (int(time.time()) - codex_bridge._LEASE,)).fetchone()[0]
    finally:
        db.close()
    agents = codex_presence.agents_snapshot().get("agents", [])
    online = sum(a.get("online") is True for a in agents)
    buckets = operations_store.metrics(60)["buckets"]
    requests = sum(int(b["requests"]) for b in buckets)
    errors = sum(int(b["errors"]) for b in buckets)
    alerts = []
    if queue.get("queued", 0) > max_queued:
        alerts.append("queue_backlog")
    if stale:
        alerts.append("stale_task_lease")
    if agents and not online:
        alerts.append("no_online_agents")
    if requests >= min_samples and errors / requests >= max_error_ratio:
        alerts.append("high_error_ratio")
    return {"queue": queue, "stale_leases": stale,
            "agents": {"total": len(agents), "online": online},
            "requests_60m": requests, "errors_60m": errors, "alerts": alerts}
