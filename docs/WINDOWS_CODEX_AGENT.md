# LKH MCP — Windows Codex Agent / GitHub / Graphify bridge

## Contract and trust boundaries

- **ChatGPT + connected GitHub**: inspect Graphify snapshots and actual GitHub source, propose edits, and commit/push **only when separately authorized**.
- **MCP Docker**: durable SQLite queue, agent token validation, status/result/Graphify snapshot access. It does not mount or modify local checkouts. Local Git/Graphify tools are no longer registered as MCP tools.
- **Windows Agent + Codex CLI**: only component with local Git checkout access. Polls MCP over **outbound** HTTP to **loopback** (or HTTPS), verifies allowlisted origin/branch and exact remote commit SHA, rejects dirty checkouts, fetches and fast-forwards, then uses a **temporary detached worktree** for Codex tests, diagnosis, fix proposals and Graphify graph generation. It never commits/pushes or auto-applies fix proposals to the canonical checkout.
- Graphify graph is generated using the **installed Graphify Codex skill** (`graphify install --platform codex`) and returned to SQLite, not stored in GitHub. The query result contains the commit SHA. Graph snapshots can contain proprietary topology; restrict MCP access accordingly.
- The bridge has no remote shell tool, no arbitrary command execution endpoint and no inbound Windows agent listener. The queue contains only `verify`, `diagnose`, `fix`, `graphify` task kinds.

## 1. Update and deploy from GitHub

Review any local pending changes, then have the Windows Codex perform the approved pull and environment verification. Never force-pull or discard user edits. The Windows Agent itself checks exact GitHub commit SHA, rejects dirty checkouts and uses fast-forward merges.

```powershell
git status --short
git pull --ff-only origin main
python -m compileall -q src windows_agent tests
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -t . -p "test_*.py" -v
docker --context naru compose -f compose.yaml up -d --build
```

Existing SQLite data and Docker named volumes must be preserved. The agent API is served on the existing private 8001 admin listener; no additional inbound port is required. Docker deployment and Windows Agent configuration are separate from GitHub push and must be verified in the user's environment.

## 2. Token provision and permissions

Generate a strong random token **locally** (never paste it into ChatGPT, code, GitHub or public logs):

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Add `CODEX_AGENT_TOKEN` to your existing **untracked** `secrets/bootstrap.json` while keeping existing Oracle/admin secrets. This bootstrap is read at container startup; recreate the MCP service after changing it. Configure **the exact same token** as the Windows Agent environment variable `LKH_CODEX_AGENT_TOKEN` (prefer Windows Credential Manager / secured OS secret handling). Do not save the token inside `windows_agent/config.json` or a tracked `.env`.

From React `/admin/config`, set:

- `GIT_ALLOWED_REPOS = ITAM=gyangho/ITAM;LKH_MCP=gyangho/LKH_MCP` (adapt to actual repos)
- `CODEX_AGENT_ENABLED = true` (default false, fail closed)
- `CODEX_MAX_RUNS_PER_DAY = 30` (allowed 1–100; set 100 if required; rolling 24-hour claim count)

Legacy `GIT_ALLOW_COMMIT`, `GIT_ALLOW_PUSH`, `GRAPHIFY_PROJECTS`, and `GRAPHIFY_ALLOW_UPDATE` no longer grant working-tree access from MCP. Old persisted keys are preserved for non-destructive migration but are hidden from the new UI; old related modules are not registered as tools. Do not enable `compose.codex.yaml` Docker Codex worker for this architecture.

## 3. Set up Windows Codex Agent

Install Python, `git`, `codex`, and the Graphify Codex skill on the **Windows machine**, for the same non-admin user who runs the agent. Authenticate the locally installed Codex CLI under that account. Use the official Graphify installation instructions for the current version; CLI commands to build a graph are not interchangeable with the assistant's `/graphify` skill.

Create a **private** `windows_agent/config.json` from `windows_agent/config.example.json` with actual absolute Windows checkout paths. Keep this file untracked. Default `server_url` is `http://127.0.0.1:8001` on the same Windows host running Naru. For a different host use **HTTPS with validated TLS**, not `http://192.0.1.22:8001` with the bearer token. Limit ingress to Private Access, no public endpoints.

In a PowerShell session, supply the token through the OS-managed secret or an existing protected bootstrap file without printing it:

```powershell
$env:LKH_CODEX_AGENT_TOKEN = (Get-Content .\secrets\bootstrap.json -Raw | ConvertFrom-Json).CODEX_AGENT_TOKEN
python .\windows_agent\agent.py --config .\windows_agent\config.json --once
# Once confirmed, run continuously under a dedicated Windows user/service:
python .\windows_agent\agent.py --config .\windows_agent\config.json
```

Agent polls every 10 seconds (configurable 5–60), and only one job may run at a time. A claimed task expires after 60 minutes; an interrupted job fails closed and must be inspected before manual resubmission. Do not run several instances with identical agent ID and token. Recommended: start via Windows Task Scheduler **at system startup** under a dedicated least-privilege user; set restart-on-failure. Verify real Windows access rights, Git authentication, and the Codex CLI session before first execution.

## 4. ChatGPT workflow

1. Search `graphify_list_projects` and `graphify_query` with a known graph commit SHA. Compare with GitHub HEAD (graph is only a structural hint).
2. Inspect source via the GitHub connector. Commit/push to approved branch **only when user explicitly authorizes**.
3. Use `codex_enqueue(project, branch, expected_sha, kind="verify", instructions="...")` to enqueue work. `expected_sha` must be the full 40-character SHA read from GitHub; Windows Agent will refuse to merge if remote SHA changed or the checkout is dirty.
4. Poll `codex_get_task(task_id)` / `codex_list_tasks()` (no automatic continuation of this ChatGPT chat). For a test failure, request `kind="diagnose"`; for local minor patch **proposal**, use `kind="fix"`, which requires login to `/admin/codex` and explicit **approve** action.
5. For graph generation use `kind="graphify"`; the agent runs the installed Graphify Codex skill in its disposable worktree and uploads a compressed graph snapshot with the expected commit SHA.
6. A fix job reports a **proposed diff** only. It never changes the canonical checkout or GitHub. Decide separately whether ChatGPT should apply the change to GitHub or the local Codex user should review a patch. Next fetch refuses dirty trees, safeguarding local changes.

## 5. Verification and limitations

```powershell
python -m compileall -q src windows_agent tests
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -t . -p "test_*.py" -v
cd frontend
npm install --no-audit --no-fund
npm run build
```

Test both a successful/failed queued task, unauthorized agent token, rejected dirty repo, changed expected SHA, expired lease, approval-gated fix, and Graphify snapshot SHA. Inspect the UI at `/admin/codex`.

**Unverified until deployment:** real Windows Codex CLI sandbox behavior, Graphify skill build output format, Naru-to-Windows loopback connectivity, Oracle, live WARP policy, and browser UI. Tests inside the ZIP use isolated fake settings and never execute Codex/Git against a user's checkout. No background orchestration or spontaneous ChatGPT notification is provided; status must be queried by a follow-up request.

The local verification workspace may lack ignored test fixtures, credentials and Python environments; Codex must report tests it could not actually execute. Windows Codex `workspace-write` sandbox guarantees vary by host/configuration; least-privilege OS account isolation remains mandatory.
