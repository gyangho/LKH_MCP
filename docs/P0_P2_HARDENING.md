# P0–P2 security, reliability and UI hardening

Status: **staging implementation; production E2E/rollout not approved**.
Base: current `main` after PR #8 was merged on 2026-11-01. Since the
`refac` branch was deleted after merge, work continues on a separate
`fix/p0-p2-hardening` branch with Draft PR #9.

## P0

- MCP instruction read tools **fail closed for scoped items**: anonymous/unverified
  project, Agent and tool selectors cannot request scoped content. Published
  `global` instructions remain visible. An authenticated principal-to-project
  authorization model must be implemented before scoped MCP reads are enabled.
- Codex metadata telemetry: only allowlisted event type/phase/seq, bounded 128
  in-memory events and batches of 16, retry on transient transport failures;
  server rejects conflicting sequence replay and allows exact idempotent replay.
  **Not durable**: process death can lose unflushed events.
- Admin+CSRF controlled `retry` decision copies a failed
  verify/diagnose/graphify task to a new ID/lease exactly once; original
  repository/branch/SHA remains fixed, queue/daily quota enforced; no
  replay of `fix` tasks. Lost response can still delay job completion;
  only manual retry is allowed, not automatic requeue.

## P1

- Instruction `revoke`: unpublish without deleting version history.
  `request_review` and `approve_review` record author/reviewer, prevent
  same actor from self-approving, and preserve audit entries.
  `LKH_REQUIRE_PEER_REVIEW=1` gates publication but MUST NOT be turned on
  with the current single-admin account; independent identities/RBAC are
  not implemented. There is no independently verified approval workflow.
- Login success/failure and logout metadata persisted without usernames,
  IP addresses, credentials, or raw headers. Monitoring alert API reports
  queue backlog, stale leases, absent Agent heartbeats and aggregate error
  rates only. No outbound notifications or automatic actions.
- Read-only `native-upgrade-preflight.ps1` checks state artifacts and SCM
  presence. Installer packages the script and CI syntax-checks it.
  **Does not perform upgrade/backup/rollback** and cannot authorize an
  operational change.

## P2

- Browser-only filters for instruction list, structured metadata logs, and
  Codex event phase; task retry button for failed non-`fix` jobs.
  Operations dashboard surfaces queue/offline/error warnings.
- Filters operate on the loaded bounded result, not across the full
  database. Server pagination, filtering, a11y and UX E2E are pending.

## Tests and deferred gates

New `tests/test_p0_p2_hardening.py` checks event replay, exact deduplication,
retry preserving SHA and idempotency, revocation/history, self-review rejection,
and event buffering/metadata validation. Run full Python/Frontend/Windows CI
against the PR commit and record actual results, not expected success.

Remaining release blockers include per-caller MCP scope ACL/identities,
durable outbox and resumption of running leases, RBAC with independent approver,
complete Windows Installer upgrade rollback, production Oracle and Codex E2E.
These changes **do not modify production Windows/Naru/Docker/Cloudflare/DB**.
