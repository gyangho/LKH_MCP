# LKH MCP Control Center v0.0.1

## Architecture

The existing MCP endpoint at https://mcp.gyangho.com/mcp is preserved.
The same Python MCP process also serves:

| URL | Purpose | Authorization |
| --- | --- | --- |
| / | Redirect to /admin | No privileged data |
| /admin | UI UX Pro Max dark monitoring dashboard | Cloudflare Access JWT + admin email |
| /admin/api/status | Process CPU, memory, uptime and MCP tool activity | Cloudflare Access JWT + admin email |
| /admin/api/settings | Current Git and Graphify permissions | Cloudflare Access JWT + admin email |
| /admin/api/flags | Allowlisted permission updates | JWT, email, HTTPS origin and action header |
| /healthz | Minimal liveness check | Public; only status ok |
| /mcp | Existing Streamable HTTP MCP endpoint | Existing Portal/Access policy |

The dashboard uses the design references returned by UI UX Pro Max:
high-contrast dark dashboard, dense KPI cards, resource charts, live operation
table, compact settings toggles, 4.5:1 contrast target, visible keyboard focus,
reduced motion, explicit confirmation before changing a sensitive flag.
It uses bundled local HTML/CSS/JavaScript with no CDN requirement.

Only three settings can be changed in the web UI:

- GIT_ALLOW_COMMIT
- GIT_ALLOW_PUSH
- GRAPHIFY_ALLOW_UPDATE

These are effective immediately and persist at
%LOCALAPPDATA%/LKH_MCP/runtime-settings.json unless MCP_STATE_DIR is set.
Persisted values override .env on subsequent startups. No arbitrary environment
variable editing, SQL execution or terminal command is exposed in the admin UI.

The activity panel displays only instrumented MCP tool names, execution time,
success/failure and start timestamp. It never logs tool arguments or outputs.
The CPU and RSS measurements are process-level, not system-wide usage.

## Build on Windows

Run PowerShell from the existing checkout after reviewing local changes:

    git pull --ff-only origin main
    git submodule sync --recursive
    git submodule update --init --recursive

Check that the official UI UX Pro Max search.py exists at
vendor/ui-ux-pro-max-skill/src/ui-ux-pro-max/scripts/search.py.

With Python 3.12 and .venv installed:

    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\scripts\build-windows.ps1

The onedir build is placed at dist/LKH-MCP-v0.0.1/LKH-MCP.exe. It has no
console window. Keep the output directory together (it is not a single-file
portable executable). The EXE is built on Windows; no Windows binary has been
compiled or tested from ChatGPT.

IMPORTANT: the frozen EXE cannot use sys.executable as a Python interpreter
for the UI UX Pro Max script. Set UIUX_PYTHON_EXECUTABLE in the external .env
beside the EXE to the absolute path of your local Python interpreter.

Copy your existing .env file beside the EXE manually. Do not add it to Git.

Example additional settings (replace placeholders with actual values):

    ADMIN_CF_TEAM=YOUR_CLOUDFLARE_TEAM_SUBDOMAIN
    ADMIN_CF_AUD=YOUR_CLOUDFLARE_ACCESS_APPLICATION_AUDIENCE
    ADMIN_ALLOWED_EMAILS=you@example.com
    ADMIN_PUBLIC_ORIGIN=https://mcp.gyangho.com
    UIUX_PYTHON_EXECUTABLE=C:/path/to/Python312/python.exe

The executable does not bundle Git, Graphify, Oracle Instant Client or the
existing database. Those dependencies must remain available on the PC.

Version is tracked in src/version.py (0.0.1) and scripts/windows-version.txt.
When releasing 0.0.2 or later, update both to the same version before rebuilding.

## Background execution

Double-click the built EXE: it runs without a console window even when no
PowerShell window is open. Log output is written to
%LOCALAPPDATA%/LKH_MCP/logs/server.log.

For automatic startup at user sign-in, create a Windows Task Scheduler task:

1. Open Task Scheduler and select Create Task.
2. Run as the intended LOW-PRIVILEGE Windows user, not SYSTEM.
3. Trigger: At log on of that user.
4. Action: Start a program, pointing to the EXE inside its release directory.
5. Start in: the same release directory (without quotes).
6. Settings: Restart on failure, and do not stop after a time limit.
7. Sign in and verify that the task is running and /healthz responds.

This is a background scheduled task rather than a Windows Service. A
user-logon task stops when the user logs off; for pre-login/service lifetime,
a dedicated Windows service wrapper with a restricted service account would
be required. Do not set up a service under SYSTEM by default.

## Cloudflare Access (required)

Before exposing the dashboard, protect mcp.gyangho.com with a Cloudflare
Access self-hosted application restricted to your administrator identity.

From Zero Trust > Access > Applications, copy the Cloudflare team subdomain,
the application's Audience (AUD) tag, and the admin email you use to sign in.
Supply those values in ADMIN_CF_TEAM, ADMIN_CF_AUD and ADMIN_ALLOWED_EMAILS.
The origin validates the signed RS256 JWT's issuer, audience, expiration
and admin email. Admin endpoints fail closed if any of these are missing.

The Access JWT must appear in the Cf-Access-Jwt-Assertion header delivered to
the origin. Do not grant admin access merely because a request traversed a
Cloudflare Tunnel. The Admin API also requires HTTPS same-origin requests
for state changes. Cloudflare application policy for /mcp must remain
compatible with your existing ChatGPT MCP Portal authentication.

Do not expose port 8000 directly on the Internet. Keep MCP_HOST=127.0.0.1,
and route the hostname through your existing authenticated Cloudflare Tunnel.

## Verification

Run these commands on the Windows host:

    .\.venv\Scripts\python.exe -m compileall server.py src
    .\.venv\Scripts\python.exe -m unittest -v test_runtime_state.py
    .\.venv\Scripts\python.exe server.py

Then verify local http://127.0.0.1:8000/healthz is healthy and, after
Cloudflare Access authentication, the /admin dashboard loads and shows live
metrics. Exercise each permission toggle, refresh the browser and restart the
service to verify persistence. The toggles do not themselves perform Git
commits, Git pushes or Graphify updates.

Security boundary: JWT authentication and local OS permission isolation are
essential. Do not treat web dashboard controls as a substitute for Cloudflare
Access policy, firewalls or Windows file ACLs.


### Source & test layout

Sources are under `src/`, unit and smoke tests under `tests/`.
The root `python server.py` launcher is still supported.

    python -m unittest discover -s tests -t . -p "test_*.py" -v
    python -m tests.test_oracle
    python -m tests.test_mcp

The PyInstaller script now targets `src/server_launcher.py` and uses
`--collect-submodules mcp.server` instead of unused `mcp.cli`.


### Windows system tray icon

The background EXE uses the **CLI-style pixel pig** selected by the user.
The approved pixel-artwork is tracked as `branding/pig-terminal.png`.
The Windows build uses Pillow (`scripts/generate_icon.py`) to convert it to
transparent PNG and multi-size ICO without changing its design.

When `LKH-MCP.exe` runs in an **interactive Windows user session**, it displays
an icon in the Windows notification area. The right-click menu offers:
- **대시보드 열기** — opens `ADMIN_PUBLIC_ORIGIN/admin` in the browser
- **상태 확인** — checks local `/healthz` and shows a Windows notification
- **종료** — quits the background server if no MCP tools are executing

Double-clicking the icon opens the dashboard. The tray process shows no console.
The server runs in a daemon thread under the tray's GUI main loop.

Before running from source without a Windows EXE, generate the icons:

    .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
    .\.venv\Scripts\python.exe scripts/generate_icon.py
    .\.venv\Scripts\python.exe src/server_launcher.py

The PyInstaller build generates `assets/lkh-mcp.ico` and `assets/lkh-mcp.png`,
embeds the .ico in the executable and bundles the PNG for the tray. Those generated
files are ignored in Git. The approved source PNG under `branding/` is tracked.
On Linux or another OS the ordinary MCP server starts without a tray.
**Windows Scheduled Tasks running without an interactive logged-in user cannot
display a tray icon.** To show it, use a normal user logon session.
