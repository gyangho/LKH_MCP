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

Add `CODEX_AGENT_TOKEN` to your existing **untracked** `secrets/bootstrap.json` while keeping existing Oracle/admin secrets. This bootstrap is read at container startup; recreate the MCP service after changing it. For legacy deployments the Agent can automatically read the same token from the local ignored `secrets/bootstrap.json`, or use `LKH_CODEX_AGENT_TOKEN` for compatibility. Do not save the token inside `windows_agent/config.json` or a tracked `.env`.

From React `/admin/config`, set:

- `GIT_ALLOWED_REPOS = ITAM=gyangho/ITAM;LKH_MCP=gyangho/LKH_MCP` (adapt to actual repos)
- `CODEX_AGENT_ENABLED = true` (default false, fail closed)
- `CODEX_MAX_RUNS_PER_DAY = 30` (allowed 1–100; set 100 if required; rolling 24-hour claim count)

Legacy `GIT_ALLOW_COMMIT`, `GIT_ALLOW_PUSH`, `GRAPHIFY_PROJECTS`, and `GRAPHIFY_ALLOW_UPDATE` no longer grant working-tree access from MCP. Old persisted keys are preserved for non-destructive migration but are hidden from the new UI; old related modules are not registered as tools. Do not enable `compose.codex.yaml` Docker Codex worker for this architecture.

## 3. Set up Windows Codex Agent

Install Python, `git`, `codex`, and the Graphify Codex skill on the **Windows machine**, for the same non-admin user who runs the agent. Authenticate the locally installed Codex CLI under that account. Use the official Graphify installation instructions for the current version; CLI commands to build a graph are not interchangeable with the assistant's `/graphify` skill.

Create a **private** `windows_agent/config.json` from `windows_agent/config.example.json` with actual absolute Windows checkout paths. Keep this file untracked. Default `server_url` is `http://127.0.0.1:8001` on the same Windows host running Naru. For a different host use **HTTPS with validated TLS**, not `http://192.0.1.22:8001` with the bearer token. Limit ingress to Private Access, no public endpoints.

The Agent now automatically discovers credentials in order: existing `LKH_CODEX_AGENT_TOKEN`, private `windows_agent/token.json`, and local `secrets/bootstrap.json` (legacy). A manual environment variable is **not required**. The following optional example remains supported:

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


## Phase 0 — Agent heartbeat and connection diagnostics

After deploying the Phase 0 server and updating `windows_agent/agent.py` on Windows,
restart the Windows Agent with the existing `--config` argument. Its heartbeat thread
uses the **same existing** `CODEX_AGENT_TOKEN` / `LKH_CODEX_AGENT_TOKEN` pair.
No new network listener, public port, or credential is required.

- The Agent sends a heartbeat to `POST /admin/agent/heartbeat` every 5–15 seconds
  (capped at 15s even if work polling is configured for 60s; default 10s), even while Codex is busy.
- The server checks the bearer token, `CODEX_AGENT_ENABLED`, allowed project aliases,
  and a strict set of boolean capabilities. It never accepts arbitrary shell commands.
- The authenticated administrator can read `GET /admin/api/codex/agents`;
  the existing `/admin/codex` page shows each Agent's last heartbeat and readiness.
- **Online** requires an authenticated heartbeat in the last 45 seconds. A registered
  Agent is **Offline** when it stops reporting; prior heartbeat history alone does not
  prove the actual process is currently running.
- `git_installed`, `codex_installed`, `codex_authenticated` (the exit status of
  `codex login status`), and `graphify_installed` are reported by the local Agent,
  not verified independently by the server. The Agent rechecks approximately every
  120 seconds. CLI stdout/stderr and credential material are never uploaded.
- `Busy` is derived from an actively claimed MCP task, not an arbitrary client flag.
  This phase does **not** stream Codex CLI execution events; that belongs to Phase 1.

### Non-destructive connection check

From the LKH_MCP checkout, verify that `windows_agent/config.json` and local
`LKH_CODEX_AGENT_TOKEN` are already configured without printing secrets:

```powershell
Test-NetConnection 127.0.0.1 -Port 8001
python .\windows_agent\agent.py --config .\windows_agent\config.json --once
```

A single-shot Agent may have a short-lived Online status; the continuous Agent
process is needed for continuous monitoring:

```powershell
python .\windows_agent\agent.py --config .\windows_agent\config.json
```

The UI may show `Offline` until both the updated MCP container and Agent are running.
A `401` heartbeat rejection means incorrect/missing agent token; `403` means
the Agent feature is disabled; `400` means invalid or unapproved Agent metadata.
No token or CLI output is returned in these diagnostics.

The agent uses the same private port `127.0.0.1:8001` as before. If Naru does not
forward that loopback port to Windows, fix the private forwarding path first.
Do **not** expose the Agent endpoints over a public tunnel or use plaintext HTTP
to a non-loopback host. Preserve the existing SQLite Docker volume during upgrades.

### Windows MXC `SystemDrive` compatibility

On Windows 11 with Codex 0.165.0, the native MXC sandbox may fail before
command execution with `MXC requires nonempty Unicode host SystemDrive`.
The Windows Agent must propagate the existing Windows `SystemDrive` variable
(usually `C:`) to its **allowlisted** subprocess environment. This is supported
by `windows_agent/agent.py`; it still strips agent tokens and other secrets.

If you enable MXC with `[features] prefer_mxc = true` in your local
`%USERPROFILE%\.codex\config.toml`, update the Windows Agent code to include
the `SystemDrive` fix before re-running queued verification. Installing MXC or
configuring it does not by itself fix an old Agent that strips the environment.
The server still only receives the final bounded verification report.

### Missing `SystemDrive` in PowerShell or Task Scheduler

An Agent launched from a shell without `SystemDrive` previously forwarded an
empty value to Codex even when the allowlist included the variable. The Agent now
reconstructs the drive from the Windows installation directory `SystemRoot`
(or `WINDIR`), validating the drive letter and refusing to guess or weaken the
sandbox. If none of these values is valid, fix the Windows session environment.

Before restarting an updated Agent, verify without exposing credentials:

```powershell
python -c "from windows_agent.agent import safe_env; print('SystemDrive:', safe_env().get('SystemDrive'))"
```

A correct result is the actual Windows installation drive (often `C:`).
Restart the existing Windows Agent after updating its code; the running Python
process does not automatically reload modifications from Git.

### Windows environment key casing

On Windows, `os.environ` may normalize the key name to `SYSTEMDRIVE`. The
older `safe_env()` copied that key without changing its case. Therefore a
diagnostic such as `safe_env().get('SystemDrive')` can misleadingly show
`None` even though the child process receives `SYSTEMDRIVE=C:`. Inspect
the filtered keys case-insensitively before concluding the value is missing:

```powershell
python -c "from windows_agent.agent import safe_env; print([(k,v) for k,v in safe_env().items() if k.upper() == 'SYSTEMDRIVE'])"
```

This patch also normalizes the allowed key to `SystemDrive` on Windows,
so the earlier diagnostic returns the actual system drive. A running Agent
must be restarted for any source change to take effect.

## Codex Agent token lifecycle — administrator-managed

`/admin/codex` now includes **Codex Agent 인증 토큰 관리**.
It is protected by the existing administrator session and same-origin CSRF checks.

- **Issue / Rotate**: generate a cryptographically random token, store only its
  SHA-256 fingerprint (full verifier hash) in the persistent SQLite volume, and
  show the plaintext exactly **once** to the authenticated administrator.
- **Revoke**: invalidate the managed token immediately without deleting the
  persistent revoke marker. Neither rotation nor revocation exposes token text in
  status, audit logs, or subsequent reads.
- **Legacy compatibility**: before first use of token management, the existing
  `CODEX_AGENT_TOKEN` from `secrets/bootstrap.json` still works. After issuing
  or revoking a managed token, the old bootstrap token is intentionally invalid,
  including after server restart. Do **not** rotate during a running task.
- **Deployment**: maintain the `mcp-data` Docker volume. Removing it destroys
  the credential verifier and job history. A normal container rebuild preserves it.
  The new token becomes active immediately; no Docker rebuild is required to
  activate later rotations.
- **Security**: no unauthenticated Agent token download endpoint exists.
  Deliver the one-time token from the administrator to the specific Windows host
  over a trusted channel; an unauthenticated Agent cannot ask the server for its key.

For the Windows Agent to start **without manually setting an environment variable**,
create an ignored local file `windows_agent/token.json`:

```json
{"token":"PASTE_ONE_TIME_ADMIN_TOKEN_HERE"}
```

Use the actual one-time token shown by the administrator console, not the
placeholder. This file is ignored by Git but still must be restricted to the
dedicated Windows Agent account using filesystem permissions. Do not paste the
token in chats, CI, logs, or checked-in configuration. Existing
`secrets/bootstrap.json` also works for legacy tokens when no newer token file
exists. For generated/rotated tokens use `windows_agent/token.json` to avoid
editing the Docker bootstrap file.

With the token file present, start the Agent normally:

```powershell
python .\windows_agent\agent.py --config .\windows_agent\config.json
```

For new managed tokens the server cannot issue keys to unauthenticated clients.
A future device enrollment protocol would require a separate trusted
bootstrap/approval step and is outside this change.
