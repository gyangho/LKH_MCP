# Track A I0–I7 implementation and validation ledger (refac)

Snapshot: 2026-10-30 · **Do not deploy to production from this branch**.
Official scope is [ROADMAP](ROADMAP.md). This ledger distinguishes code presence, CI and
on-host acceptance. Windows native application, private Admin/MCP routing, device
enrollment and SQLite migration are **not production released**.

## Current code deliverables

| Stage | Files / concrete implementation | Remaining acceptance |
|---|---|---|
| I0 | `TRACK_A_I0_BASELINE.md`: Naru/Docker, SQLite WAL, Oracle Thick, Cloudflare/WARP/portproxy, Agent and UIUX inventory | Host/network/Oracle evidence; I0 not fully VERIFIED |
| I1 | `native_runtime.py`, `native_server.py`, `native_gateway.py`; 127.0.0.1:18080 MCP-only, :18081 Admin-only, route guards; PyInstaller onedir bundle | Windows CLI smoke and 404 route checks; Oracle 11g, UIUX frozen parity and real host still pending |
| I2 | `native_service.py`: distinct SCM host process, child server lifecycle, service stop signal. Installed as `LKH-MCP-Server` under LocalService by Installer | Service install/start/reboot/logoff/recovery/ACL under actual Windows account |
| I3 | `native_task_control.py`, `native_host_routes.py`, `scripts/install-agent-task.ps1`; fixed task only, authenticated CSRF API, busy guard | Real LocalService task SDDL, Windows Agent repo config, interactive login, restart/stop E2E |
| I4 | `native_tray.py`, `scripts/generate_icon.py`: same approved Pixel Pig silhouette recolored green/pink/gray; server-derived authenticated-heartbeat status (not mere scheduler Running), separate tray, fixed task control | Pixel legibility at 16px, notification UI, tray autostart, offline/unknown behavior on host |
| I5 | `native_enrollment.py`, `native_enrollment_routes.py`, Agent token refresh: installer provisions machine-DPAPI device credential + SHA verifier, short-lived session API, admin-only rotate | Win11 DPAPI/ACL cross-account proof, rotation failure atomicity, binding to expected Agent ID, authenticated challenge-response upgrade and threat review |
| I6 | `installer/LKH-MCP.iss`, `scripts/build-native-suite.ps1`, Windows native dependency list, preflight + fixed task registration | Inno compilation, admin credential onboarding wizard, clean VM install/upgrade/uninstall, code signing, SBOM |
| I7 | `native_migration.py`: read-only SQLite inspect + Backup API staging copy, integrity/row counts/logical SHA-256 digest, no overwrites; dry-run first | Source Docker volume export, actual backup restore, Cloudflare/port cutover & rollback in maintenance window with **separate user approval** |

## Build a staging-only unsigned suite

```powershell
# Must be run in a Windows source checkout on the refac branch, not an active service.
git switch refac
git submodule update --init --recursive
.\scripts\build-native-suite.ps1 -Python python

# Native preview preflight; NO service installation
.\dist\LKH-MCP-Server\LKH-MCP-Server.exe --check

# Local-only staging DB and both strictly filtered ports
$env:LKH_NATIVE_STATE_DIR = Join-Path $env:TEMP "lkh-native-sandbox"
$env:MCP_HOST = "127.0.0.1"
$env:MCP_PORT = "18080"
$env:LKH_NATIVE_ADMIN_PORT = "18081"
.\dist\LKH-MCP-Server\LKH-MCP-Server.exe
```

The staging Native preview is NOT the production Naru MCP. Port 18080
accepts `/mcp` and `/mcp/` only; 18081 accepts `/admin` + subpaths
only and exposes `/admin/healthz` for non-sensitive loopback liveness.
Do not configure Cloudflare to point to the preview.

To compile the **unsigned** staging Installer:
`& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\LKH-MCP.iss`.
The setup script will modify Windows services, scheduler and ACLs **when
executed**; only compile/inspect it without explicit rollout approval.
The password/bootstrap administrator setup and service login account still
require hardening for production.

## I5 current security boundary

This code is a first *same-PC* enrollment implementation: the Installer
automatically creates a 48-byte-equivalent random device secret with machine
DPAPI, ACL restricted to local Admin/SYSTEM/LocalService/selected Agent user.
Server SQLite keeps only its SHA-256 verifier and session token hashes;
the Agent automatically fetches 15-minute access tokens from loopback
`/admin/agent/enrollment/session`. Rotate invalidates existing sessions and
rewrites the DPAPI file without manual token copy. The Native gateway never
exposes that endpoint on the MCP listener or a non-loopback interface.

**Open security gates:** DPAPI machine scope is *not* a hardware-bound,
non-exportable device key; stolen machine-level secrets can be abused if OS
privileges are compromised. No challenge/nonce exists yet and token replay
within TTL is possible; scope is one host/loopback only. Credential rotation preserves the prior file DACL and attempts credential restoration on a database write error; it still uses a file+SQLite transition, not an atomic cross-resource transaction.
Do NOT expose native port 18081 over WARP/Cloudflare until enrollment and
public access policy have passed threat review. The old Docker token method
is unchanged while Native is isolated.

## I7 staged backup command

```powershell
# Pass an authorized, safely exported SQLite database path, NOT the live Docker volume.
$env:PYTHONPATH = "src"
python -m native_migration --source "C:\secure-export\mcp.sqlite3"

# Destination must not exist. Keeps source intact, uses SQLite Backup API.
python -m native_migration --source "C:\secure-export\mcp.sqlite3" `
  --destination "C:\isolated-staging\mcp-backup.sqlite3" --copy
```

The above only copies a standalone SQLite snapshot. It DOES NOT migrate
settings, expose credentials, change DNS/WARP, stop Docker or start Native
on production ports. Apply only after user authorizes source export.
A real I7 rollback includes original Naru gateway, original SQLite snapshot,
Windows service stop, and Cloudflare private route restoration.

## Criteria before I0–I7 RELEASED

1. Windows CI complete including unsigned setup compile and native route 404 tests.
2. Oracle 11g thick driver on actual host, bundled UI UX search without unmanaged Python,
   DPAPI/Service account/Agent account/TaskScheduler permission E2E.
3. Installer interactive admin bootstrap completed securely and installer rollback
   on partial failures, signed binary and update/uninstall data retention.
4. On isolated Win11 VM: reboot/no-login SCM, logged-in Agent task, Pig color
   changes, automatic token refresh/rotation, HTTP MCP and Admin parity.
5. Backup/restore of a **copy** of Naru data, compare audited rows and Graphify
   state, Cloudflare/WARP private gate validation. Explicit maintenance approval
   required for real cutover. Until then **retain Docker**.

These code deliverables are checkpoints, not user authorization to deploy.

## Subsequent hardening (2026-10-30)

- **I4 Pig state bug corrected:** Windows task `Running` alone is insufficient for green. A native **loopback-only** `GET /admin/host/tray-state` reports only `online/offline/unknown` and `busy`, calculated from authenticated Agent presence and Task Scheduler status. Missing heartbeat yields pink, unavailable service/task yields gray. Does not expose token or Agent ID.
- **I5 rotation robustness:** reissued machine-DPAPI file retains the previous encrypted file's Windows DACL (including selected Agent account read ACE), and recovers previous encrypted file if its SQLite update raises. Power loss between file update and DB commit is still a separate recovery case, not fully atomic.
- **I7 content validation:** logical SHA-256 of streamed SQLite dump, including schema and row contents, is compared in addition to table counts and `PRAGMA integrity_check`. Equal counts but different data are rejected.
- CI success only establishes isolated Windows Runner behavior. Installer UAC/silent/upgrade/uninstall, real Corp Windows login, Oracle Thick and Naru/Cloudflare switch remain unverified.
