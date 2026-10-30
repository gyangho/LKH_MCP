# Phase 1–9 Implementation / Verification Ledger

**Branch:** `refac` · **Date:** 2026-10-30 · **Status:** CODE UNDER CI VALIDATION

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
