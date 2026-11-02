# Phase 1–9 Implementation / Verification Ledger

**Branch:** `refac` · **Date:** 2026-10-30 · **Status:** IMPLEMENTED FOR STAGING; CI PASS, PRODUCTION E2E UNVERIFIED

This is evidence tracking for [the canonical roadmap](ROADMAP.md). It is not a
deployment approval. Production Naru, Cloudflare, Oracle, SQLite and Windows
Task Scheduler have not been modified.

| Phase | New implementation | Remaining acceptance |
| --- | --- | --- |
| 0 | Existing Agent heartbeat, queue, SHA and sandbox protections | Actual Windows verify/graphify E2E, login and MXC pending |
| 1 | Agent `codex exec --json` streaming, lease-checked `codex_task_events` in SQLite, allowlisted metadata and replay-safe cursor | Real Codex CLI JSONL compatibility and network loss/long-run E2E |
| 2 | `/admin/api/codex/events/{task_id}` and 2-second browser timeline; incremental seq cursor, per-task expansion | UI user acceptance, real job event trace |
| 3 | bounded task metadata and Windows temp worktree cleanup error handling; existing lease/timeout safeguards maintained | Windows ACL/cleanup failure, retry/offline, source checkout no-change E2E |
| 4 | `instruction_entries`, immutable `instruction_versions`, `instruction_audit`, optimistic revision + draft state | Schema migration on a staging copy of existing SQLite |
| 5 | `instructions_list`/`instructions_get`/`instructions_resolve` (read-only, published-only); tool > agent > project > global | Confirm intended scope access policy and review cross-project visibility |
| 6 | protected `/admin/api/instructions` CRUD/version/history/publish/rollback + React editor | Formal publication workflow approval, UX E2E |
| 7 | `operation_events` metadata-only SQLite logs with per-category cursor and 30d/50k retention + Admin log UI | Privacy review, operational load/retention test |
| 8 | 60-second buckets of request/error/avg latency, current CPU/RSS/threads + React view | Load and long-term metrics accuracy, host resource permissions |
| 9 | `.agents/skills/lkh-development/SKILL.md`, regression tests and deployment gate checklist | Real installer, Oracle/Graphify/Codex/Cloudflare end-to-end tests, release authorization |

## Security model

- New mutation routes are under `/admin` with a private administrator session and explicit Origin/Host/CSRF header. User-supplied arbitrary routes and commands are not accepted.
- Agent event batches require Bearer + live lease and contain only `seq`, an allowlisted event type and phase. Server never records Codex JSONL lines, prompts, command contents or environment variables.
- Instructions maintain immutable historical versions. MCP can never see a draft. Password-like strings and PEM private keys are rejected at entry, but pattern matching does not replace a data-loss-prevention review.
- Operations log records only tool name/success/failure/duration; no error message, response body, query, prompt, access token or command output.
- The current DPAPI device enrollment for Native is still **not** a complete CNG non-exportable challenge-response implementation; no Native public exposure.

## CI strategy

- Python: `python -m unittest discover -s tests -t . -p test_*.py -v`.
- React: `cd frontend && npm ci && npm run build`.
- Docker: validate active gateway/Compose on a runner, **never deploy**.
- Windows: build unsigned preview Native EXE/Installer, check loopback surfaces, DPAPI, SCM, Task Scheduler.
- Phase 9 skill: syntax, known API paths, docs reference validation and all phase-specific tests.

## Explicitly deferred

I7 live SQLite export and cutover, installation/upgrade on the real Windows host,
Cloudflare route switch, Oracle 11g Thick runtime, real Codex CLI/MXC and Graphify
are deferred until the user can grant a test/deployment window. Do not mark Phase 9
`VERIFIED` or `RELEASED` based on CI alone.

## Implementation verification checkpoint — 2026-10-30

- Python/unit/API security, frontend TypeScript/Vite and Nginx/Compose: **PASS** at [GitHub Actions 41037611656](https://github.com/gyangho/LKH_MCP/actions/runs/41037611656).
- Windows Native Suite (unsigned packaging, real DPAPI/SCM/Task Scheduler and isolated loopback smoke): **PASS** at [GitHub Actions 41037387950](https://github.com/gyangho/LKH_MCP/actions/runs/41037387950). This is an ephemeral GitHub runner and does not establish host-specific E2E.
- Phase 1/3 test evidence: reject invalid Agent leases, deduplicate sequence cursors, restrict event payloads to enums, prevent worktree cleanup exceptions from masking completed task results. Actual Codex CLI `--json` output and Windows sandbox ACL cleanup remain unverified.
- Phase 4–6 test evidence: unpublished drafts never resolve from MCP, optimistic revision rejects stale updates, published scope precedence and rollback are test-covered; management API denies unauthenticated and CSRF-invalid requests.
- Phase 7–8 test evidence: metadata-only events and request correlation IDs, response status and duration, bounded retention, minute metrics, default denial for untrusted admin requests. API trace response header is an opaque ID, not credentials.
- Phase 9: repository-local `.agents/skills/lkh-development/SKILL.md`, tests for documented gates and audit boundaries, `refac` Draft PR. Real cutover remains deferred as explicitly requested.

**Release classification:** the above features are staged code, not deployed product. Phase 3, 6 and 9 require live Codex, UI, Oracle and Windows security E2E before their full acceptance criteria can be marked VERIFIED; Gate G5 requires a separate user approval. No `main` merge, production service restart, database export or Cloudflare routing change took place.


## Native same-PC Naru replacement / Pixel Pig UI update (2026-11-02)

- Native loopback defaults: MCP `127.0.0.1:8000/mcp`, Admin `127.0.0.1:8001/admin`. They **reuse the existing Cloudflare destination ports only after Naru/old Docker port listeners are stopped**. Both route guards remain separate; never bind the combined app on `0.0.0.0`.
- Existing Naru container/port proxy may still own the sockets; Native must fail the bind in that case. This software does **not** stop Naru, edit Cloudflare, remove data, or change Windows firewall rules.
- Installer initializes `ADMIN_PUBLIC_ORIGIN=http://127.0.0.1:8001` for **local** administration. Remote administration under a Cloudflare hostname requires a separately reviewed origin/host/cookie/Access policy; MCP 8000 alone may be routed through Cloudflare. Do not expose 8001 without that review.
- Pixel Pig icon: `branding/pig-terminal.png` stays full color when the server responds and Agent has a fresh authenticated heartbeat. Server online + Agent offline → true monochrome; server unavailable → dim gray. Color no longer indicates Agent busy state.
- Web admin: original Pig artwork, shared rectangular pixel-theme fields and text area, fixed form/layout alignment. Operations logs/metrics/alerts have **no automatic polling** while being reviewed; explicit manual refresh buttons and fixed-height scroll table. Global status refresh is suspended while editing instructions or reading operations.
- Shutdown UI: session + Origin/Host/CSRF-protected Native-only `POST /admin/api/host/shutdown/{server,both}` with exact confirmation body, active-job refusal, 5-second rate limit. `both` stops the fixed Agent task first; the Native server returns acknowledgement, then drains gateways and exits. Windows SCM supervisor treats zero-exit as a deliberate stop. This does not shut down Naru or unrelated services.
- New staging CI tests verify port isolation, shutdown conditions, and Pig palette. Signed Installer, real Cloudflare/WARP routing and corporate Windows Agent/SCM shutdown remain host-specific acceptance tests.

- Native tray follow-up: right-click SCM/UAC server stop and combined stop actions (separate from tray-only exit); fail closed on missing heartbeat/busy state, with regression coverage. Login troubleshooting remains exact `ADMIN_PUBLIC_ORIGIN` comparison; existing bootstrap secrets are not auto-migrated. SCM stop and UAC on the target PC remain **not E2E verified**.

- Native uninstall implementation staging: 3 modes (default settings reset but SQLite/WAL retained), exact task/SCM ownership checks, busy/reparse fail closed, verified separate SQLite backup for full deletion, and explicit re-enrollment marker for preserved DB. CI and isolated Windows uninstall/reinstall E2E pending.

- Pig tray right-click context menu label simplified to one **종료** action (Agent + server), with no separate tray-only exit. The previous server-only API remains available from the authenticated Admin UI; tray does not bypass CSRF.

- Native tray silent-stop repair (2026-11-02): `CoInitialize`/`CoUninitialize` on worker scheduler COM calls, foreground shutdown error dialog, confirmed Agent task stop and Windows SCM `STOPPED` before tray closes. Windows real-host UAC/SCM E2E remains unverified; CI/mocks cover failure paths.

- Native Uninstaller choice UX: checkbox `완전 삭제` off by default (`settings` with SQLite/WAL/logs/backups retained), checking it requires explicit OK/Cancel before `all`; fixed LKH SCM service and owned Scheduler tasks are removed in both modes, subject to ownership/idle-state safety checks. Windows Inno Setup compile and real host uninstall E2E are separate release gates.
