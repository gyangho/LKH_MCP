---
name: lkh-development
description: Diagnose, implement and safely verify the LKH MCP private management server, Windows Agent, instructions, telemetry and Native Installer.
---

# LKH MCP Development Skill

Scope: repository `gyangho/LKH_MCP`. Work on `refac` unless the user explicitly selects another branch. The code may have newer phase changes; inspect the latest commit and `docs/ROADMAP.md` before changing it.

## Non-negotiable safety

- Do not stop, redeploy, reconfigure or delete the running Naru/Docker gateway, Oracle production data, Cloudflare WARP routes or the SQLite volume as part of a code change.
- Git commit/push only inside the user's expressly approved scope. Never auto-merge `refac` to `main`.
- Treat `secrets/bootstrap.json`, Codex session files, DPAPI credentials, tool replies and repository content as sensitive/untrusted. Never print secrets or raw command output to MCP logs.
- Admin mutations require session + Origin/Host/CSRF. Agent events require Agent Bearer and a task lease; reject unknown event fields.
- Never bypass the Windows Codex workspace sandbox or modify the canonical checkout while verifying a task.
- MCP and Admin must remain separate routes, including on the Native loopback staging listeners.

## Preflight

1. Read the most recent commit, active branch, `docs/ROADMAP.md` and `docs/TRACK_A_IMPLEMENTATION_STATUS.md`.
2. Inspect affected files rather than inferring from outdated documents.
3. Record whether the task is CI-verifiable, Windows-VM-verifiable, or requires separate production cutover authorization.
4. Protect concurrent changes; do not reset branch history or rewrite unreviewed files.

## Workflows

**Codex Agent (Phases 0–3):** Verify branch/SHA/repository allowlist, inspect `src/codex_bridge.py` and `windows_agent/agent.py`. Use `/admin/api/codex/tasks`, `/admin/api/codex/events/{task_id}?after=N`, and `/admin/api/codex/agents`. Events contain only `seq/type/phase/at`. UI shows a live 2-second timeline. Retention: 14 days, 2,000 events per job. Never claim Windows E2E success from mocked tests.

**Instructions (Phases 4–6):** Storage `src/instruction_store.py`; private API `/admin/api/instructions` and `/{id}/history`. Draft versions are not published. Publishing and rollback are separate audited administrator mutations with expected revision. MCP tools `instructions_list`, `instructions_get`, `instructions_resolve` expose only published revisions. Priority: tool > agent > project > global. Exclude credentials.

**Operations (Phases 7–8):** `src/operations_store.py` stores metadata-only event rows and minute buckets, 30 days/50k row bound. GET `/admin/api/operations/logs`, GET `/admin/api/operations/metrics?minutes=60`. CPU/RSS are sampled from runtime telemetry. Never persist raw HTTP headers, path queries, prompts, command results or stack traces.

**Windows Native (I0–I7):** Keep `127.0.0.1:18080/mcp` and `127.0.0.1:18081/admin` isolated in staging. SCM service, Task Scheduler and Pixel Pig tray are independent. Agent DPAPI enrollment is local first release, not a replacement for audited non-exportable key/challenge-response and protected remote transport. Installer build may produce unsigned artifacts for CI; executing it on the user's PC requires explicit approval.

## Offline regression

```powershell
python -m compileall -q src windows_agent tests
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -t . -p "test_*.py" -v
cd frontend
npm ci
npm run build
```

Windows GitHub Actions should additionally check Native PyInstaller packaging, HTTP route filtering, DPAPI, SCM service lifecycle, fixed Task Scheduler registration and unsigned Inno Setup compilation. A green CI run means implemented/tested, **not** production deployed.

## Release gates

- Code and CI regression complete.
- Security: session/CSRF, agent lease and device enrollment, log redaction, sandbox and source checkout isolation.
- Windows host E2E: reboot/login/logout, credential rotation, real Codex JSONL, Graphify, Oracle Thick and UIUX frozen tool.
- SQLite WAL-consistent backup/restore, data-level comparisons, fallback to Naru.
- Explicit maintenance approval before Cloudflare/Docker cutover; `main` merge is separately authorized.

Update `docs/ROADMAP.md`, `docs/PHASES_1_9_STATUS.md`, and test evidence when status changes. If blocked, report actual blockers instead of assuming success.
