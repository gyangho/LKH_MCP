# Track A I0 — Current-state inventory and cutover blockers

Snapshot date: 2026-10-30; source: refac branch derived from main 99b03566.
Status: **IN_PROGRESS**. Static source inspection performed; live Windows/Naru/WARP/Oracle verification pending.
This is an implementation-evidence appendix to [ARCHITECTURE](ARCHITECTURE.md), not a replacement runbook.

## Code inventory (observed, not inferred)

| Component | Current concrete source | Behavior / risk |
|---|---|---|
| Docker MCP | `compose.yaml`, `Dockerfile` | Python 3.12, app binds container 8000, no mcp published port, SQLite named volume `mcp-data:/app/data`, bootstrap secret |
| Docker gateway | `nginx/nginx.conf` | Host publishes **loopback 127.0.0.1:8000, :8001**. Nginx 8000 only /mcp, 8001 only /admin*. Cloudflare/WARP and Windows portproxy managed separately |
| Backend | `server.py`, `src/server.py` | One `MCPServer` object serves BOTH MCP+admin+agent paths on one internal port; exposing it directly on network would expose admin |
| Admin UI | `frontend/`, `src/admin_console.py` | React/Vite builds `frontend/dist`; backend expects `web/dist/index.html`; Docker COPY populates it. Packaged EXE must include frontend build in `web/dist` |
| Settings DB | `src/settings_store.py`, `src/codex_bridge.py`, `src/codex_presence.py` | SQLite WAL, settings/audit/agent jobs/graphs/heartbeats; `MCP_DB_PATH` default relative `data/mcp.sqlite3`. No destructive migration allowed |
| Secrets | `secrets/bootstrap.example.json`, `src/settings_store.py` | Docker secret `/run/secrets/mcp_bootstrap` or `MCP_BOOTSTRAP_FILE`. Admin password/session + shared Agent token. No automatic enrollment |
| Oracle 11g | `src/oracle_db.py`, requirements `oracledb==3.4.2` | Oracle Thick mode requires an appropriate Instant Client 19 Windows x64, correct `ORACLE_CLIENT_LIB_DIR` and VC++ runtimes; not bundled |
| Agent | `windows_agent/agent.py` | Outbound private /admin/agent/* calls, Git allowlist SHA, Codex CLI under current Windows user. Unattended Task Scheduler and SCM integration not yet implemented |
| Windows EXE prototype | `src/server_launcher.py`, `src/tray.py`, `scripts/build-windows.ps1` | Server starts INSIDE pystray-backed process; tray session lifecycle conflated with server, cannot run as Session 0 service. Script incorrectly feeds `web` directory despite React output `frontend/dist` |
| UI UX Pro Max | `src/uiux_tools.py`, git submodule `vendor/ui-ux-pro-max-skill` | In a frozen PyInstaller EXE, UI UX search explicitly requires `UIUX_PYTHON_EXECUTABLE` pointing to a real external python.exe. I1 full feature-parity **BLOCKER** until embedded runner or controlled runtime |
| Pixel Pig | `branding/pig-terminal.png`, `scripts/generate_icon.py` | Existing source approved and tracked. Original image MUST remain unchanged; status palette variants I4 |
| CI | `.github/workflows/ci.yaml` | Linux Python/Frontend/Nginx gateway; no Windows PyInstaller/SCM/Installer real test in initial baseline |

## Top migration risks (severity / mitigation)

1. **P0 admin/MCP boundary:** A Native MCP+admin single ASGI app on a public 8000 would break the Nginx split. I1 preview must be **loopback-only** and run on isolated port 18080. I2 must add equivalent dual listener/proxy and test HTTP 404 for forbidden cross-routes before cutover.
2. **P0 SQLite loss/corruption:** Two live backends may never share SQLite WAL files. Native preview must use separate `%ProgramData%\\LKH-MCP\\data` (or isolated override) and never access Docker `mcp-data`; backup with SQLite Backup API in I7.
3. **P0 credentials/registration:** No auto-provision of a bearer token to an unauthenticated Agent. I5 needs Windows protected key+authenticated enrollment and rotation; current token bootstrap remains unchanged until then.
4. **P1 service/tray accounts:** Windows Service cannot show Session 0 tray. SCM process, Task Scheduler Codex-login user, and tray must use distinct entrypoints/process ownership (I2/I3/I4).
5. **P1 UIUX frozen dependency:** Native PyInstaller currently cannot execute the bundled vendor Python search without externally supplied Python. I1 must report degraded features; I1 is not VERIFIED until resolved or consciously accepted.
6. **P1 Docker/Naru host collision:** Docker gateway currently binds 127.0.0.1:8000/:8001, and Windows portproxy routes may exist. Preview must not use these ports or rewrite Naru/Cloudflare settings.
7. **P1 Oracle 11g Thick DLL:** Linux Docker and Windows native Instant Client paths differ; validate architecture/version/oci.dll & driver in a Windows runner or VM.
8. **P1 Codex MXC and temporary worktree ACL:** Existing verify jobs previously failed on protected node_modules cleanup / SystemDrive. Native program does not solve this automatically; Phase 3 needs Windows E2E.
9. **P2 build reproducibility:** Node 22 `npm ci`, Python 3.12, PyInstaller, git submodule and Windows runner artifact checks required before Installer I6.
10. **P2 telemetry:** Existing `runtime_state` is in-process memory and not fully persistent; Phase 7/8 must add structured log/metrics before operational release.

## Decisions for I1 safe starting slice

- Introduce a **dedicated headless native entrypoint**, no tray or service registration.
- Enforce fail-closed `MCP_HOST` loopback-only; default **18080**; no public network ingress, no automatic Windows firewall changes.
- Use independent `%ProgramData%\\LKH-MCP` DB/log folders; only read `config/bootstrap.json` if it already exists; do not generate secrets. Installer ACL ownership belongs to I2/I6.
- Fix packaging path `frontend/dist → web/dist`; require bundled vendor search script; use Windows CI to test packaging and `--check`.
- Explicitly defer cross-route isolation, UIUX Python runner, Oracle real runtime, SCM registration, auto-token issuance, and cutover until relevant acceptance tests.
- Preserve existing Docker, original source/Tray prototype, secret and SQLite rows.

## I0 completion gate (still open)

- [x] Static repo component inventory + code references.
- [x] Target process/port/data security risk and no-downtime preflight documented.
- [x] Safe I1 preview design chosen; no live system mutations.
- [ ] Inspect actual host OS account permissions, Naru docker context/portproxy, Cloudflare policy + backend bypass.
- [ ] Verify Oracle Instant Client / thick mode and current DB data counts/backup restore in approved non-production staging.
- [ ] Approve cutover preconditions/ADR after evidence; **I0 cannot be marked VERIFIED from CI alone**.

## Portal read-only probe (2026-10-30, tool results; no live host inspection)

| Probe | Observation | Interpretation |
|---|---|---|
| `portal_list_servers` | LKH MCP enabled | Connector selection only; not a host health guarantee |
| `uiux_diagnostics` | `ready=true`, `packaged_exe=false`, `search_script_found=true` | Existing Docker/Python endpoint UIUX working; **does not validate frozen Windows bundle** |
| `graphify_list_projects` | `projects=[]` | No synced project graphs visible to this connector at inspection time |
| `oracle_select_dual` | MCP tool returned an execution error without Oracle error code | **UNVERIFIED/BLOCKED**: cannot infer whether Oracle DB, client, credentials, or upstream tool is at fault |

No Naru restart, DB query beyond the fixed DUAL check, Cloudflare policy modification, file mutation on the Windows host, or secret download was performed. Before I0 VERIFIED, investigate the DUAL execution failure through authorized redacted server logs and Windows-side Oracle client checks.

## Refac I1 test evidence

- PR draft #8, Windows Actions run `41022366248`: Windows 3.12 native config tests **PASS**, PyInstaller build/asset `--check` **PASS**, live isolated `127.0.0.1:18080/healthz` HTTP **200**, isolated staging SQLite creation **PASS**. Unsigned preview bundle uploaded as a CI artifact.
- PR Python/frontend/gateway run on initial refac commit **PASS**; next changes require their own CI checks.
- These checks prove the staging executable **starts** on the GitHub-hosted Windows runner. They do not prove actual corporate PC Oracle, Cloudflare private WARP, Windows SCM service/Agent Task Scheduler, UIUX external interpreter or rollout.
