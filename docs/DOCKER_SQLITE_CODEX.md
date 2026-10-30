# LKH MCP · Docker, React Admin, WARP Private Access, SQLite, Codex

## Architecture and endpoint isolation

| Destination | Purpose | Exposure |
|---|---|---|
| `192.0.1.22:8000/mcp` | Existing Cloudflare MCP Portal upstream | Private CIDR route |
| `192.0.1.22:8000/admin` | Denied by Nginx | 404 |
| `192.0.1.22:8001/admin` | React private admin interface | WARP Private Access + password/session |
| `192.0.1.22:8001/admin/config` | Settings tab | Session required |
| `192.0.1.22:8001/admin/codex` | Codex approvals | Session required |
| `192.0.1.22:8001/mcp` | Denied by Nginx | 404 |

The backend runs on Docker port 8000 only. Nginx publishes the segregated gateway routes. Windows portproxy can forward `192.0.1.22:8001` to `127.0.0.1:8001`. The IP **must be assigned to a Windows adapter**. No external DNS hostname or public Cloudflare Tunnel is used for the admin interface. Do not add an unrestricted Windows firewall inbound rule.

## Mandatory Cloudflare access controls

1. Keep the existing CIDR Route for the MCP Portal on port 8000.
2. Create an **Access controls → Applications → Self-hosted and private** application for private IP `192.0.1.22`, TCP port `8001`. Enable client authentication via Cloudflare One Client and restrict Allow to your specific identity.
3. Set a Gateway network policy for TCP 8001 that blocks other identities and devices. Merely joining the WARP organization does **not** authenticate an administrator.
4. Remove any previous publicly reachable admin Published Application and revoke broad LAN/WAN access to 8001.
5. Verify a permitted WARP user succeeds; a nonpermitted user fails at the network policy; an unauthenticated private HTTP visitor is redirected to /admin/login.

Policies and Windows firewall configuration must be applied **on the user environment**; updating source code does not create Cloudflare policies.

## Independent admin login

The Python backend verifies a salted PBKDF2-SHA256 password hash and issues an unpredictable HttpOnly, SameSite=Strict, four-hour memory-backed cookie. Five bad logins in a 15-minute window block further attempts. Sessions are wiped on server restart; separate replicas would need shared server-side session storage.

Generate a 14+ character password hash locally:

```powershell
python -c "import sys,getpass;sys.path.insert(0,'src');from admin_auth import make_password_hash;print(make_password_hash(getpass.getpass('Admin password: ')))"
```

Merge the following into your **existing untracked** `secrets/bootstrap.json`; do not overwrite Oracle credentials:

```json
{
  "ADMIN_LOGIN_USER": "admin",
  "ADMIN_PASSWORD_HASH": "paste-generated-pbkdf2_sha256-hash",
  "ADMIN_PUBLIC_ORIGIN": "http://192.0.1.22:8001"
}
```

Avoid plain text passwords in Git, environment files or shell history. Old `ADMIN_CF_TEAM`, `ADMIN_CF_AUD` and `ADMIN_ALLOWED_EMAILS` settings are obsolete and should be removed from the local bootstrap JSON when upgrading. Secrets are never written into SQLite.

**Important:** HTTP cookies cannot use the Secure attribute. Cloudflare's private transport protection, trusted LAN segregation, server-side CSRF `Origin + Host` validation and local Windows inbound firewall rules are all required; consider internal HTTPS for higher security. Admin GET views, status/config APIs, toggles and Codex approvals require the session. POST changes require `Origin`, `Host`, JSON content type and `X-LKH-Admin-Action`.

## React frontend

- Source: `frontend/` (React + TypeScript + Vite).
- Build: `cd frontend; npm install; npm run build`.
- Generated static output: `frontend/dist/`, copied to `/app/web/dist/` by Docker's Node builder stage.
- The Python MCP server serves `/admin`, `/admin/login`, `/admin/config`, `/admin/codex` using one SPA, and `/admin/assets/*` for build assets.
- **No standalone React server** is exposed. The legacy standalone HTML dashboards were removed.
- Font: NanumSquare by NAVER, SIL Open Font License 1.1; see `frontend/NANUMSQUARE-LICENSE.md`. The CSS loads jsDelivr, with Malgun Gothic fallback.

For Windows EXE use `scripts/build-windows.ps1` which builds the React frontend before PyInstaller. Node/npm 22+ is required.

## Docker / Naru

```powershell
git status --short
git pull --ff-only origin main
git submodule update --init --recursive
docker --context naru compose -f compose.yaml config
docker --context naru compose -f compose.yaml up -d --build
docker --context naru compose -f compose.yaml ps
docker --context naru compose -f compose.yaml logs --tail=100 gateway mcp
```

Existing secrets and named volumes must be preserved. Do not run destructive `docker compose down -v`. For a clean portproxy listener check:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8001
netsh interface portproxy show all
curl.exe -i http://192.0.1.22:8001/admin
```

An unauthenticated GET to /admin should return **303 to /admin/login**, not the old Cloudflare Access JWT 403. The React frontend may require internet access for jsDelivr font, but application assets are served locally.

## Windows Codex Agent bridge (replaces the legacy Docker worker)

Local Git/Graphify tools and the Docker Codex debugging worker are no longer registered. The Docker MCP server provides a durable SQLite work queue and serves compressed Graphify snapshots without touching working trees. Windows Codex Agent alone performs local pull, tests, diagnostics and Graphify builds. Fix requests require administrator approval and are performed only in disposable worktrees.

See [Windows Codex Agent setup](WINDOWS_CODEX_AGENT.md) for token generation, private network connectivity, Windows Task Scheduler, new tools, Graphify commit SHA tracking and verification. **Never start the legacy compose.codex.yaml worker as part of the new workflow.** Existing SQLite named volume and bootstrap secrets must be preserved.
