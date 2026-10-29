# LKH MCP — Windows server, Git, Graphify and admin console

Designed for local testing with an existing Docker-hosted Oracle Database.
**Do not expose on public Internet without MCP-compatible authentication**.

## 0. Check Oracle container/port (PowerShell)

```powershell
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}"
docker port <YOUR_ORACLE_CONTAINER> 1521/tcp
Test-NetConnection 127.0.0.1 -Port <PUBLISHED_HOST_PORT>
```

If no host port is published, inspect the Compose configuration before changing
it; do NOT casually recreate a stateful DB container that may lack a persistent volume.
Prefer host port binding `127.0.0.1:1521:1521` over `0.0.0.0:1521:1521`.

## 1. Install (PowerShell, Python 3.12 recommended)

```powershell
cd C:\dev\oracle-mcp-select
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Fill ORACLE_USER, ORACLE_PASSWORD, host port and **actual** service name or SID.
Set only one of ORACLE_SERVICE or ORACLE_SID, unless ORACLE_DSN is provided.

**Oracle 11g:** python-oracledb Thin mode will not connect. Install Windows x64
Oracle Instant Client **19** Basic/Basic Light and set ORACLE_CLIENT_LIB_DIR to the
unzipped directory containing oci.dll. Be sure VC++ runtimes needed by Instant
Client are installed. Driver is pinned to 3.4.2 to retain 11g Thick support.

## 2. Prove Oracle SELECT without MCP

```powershell
.\.venv\Scripts\python.exe -m tests.test_oracle
```

Expect ORACLE_SELECT_PASS and status MCP_OK.

## 3. Start local MCP server

```powershell
.\.venv\Scripts\python.exe server.py
```

Leave this PowerShell window running. Local endpoint is
http://127.0.0.1:8000/mcp (Streamable HTTP, NOT a web page).

## 4. From another PowerShell window, call MCP

```powershell
cd C:\dev\oracle-mcp-select
.\.venv\Scripts\python.exe -m tests.test_mcp
```

Expect the tools listed and a response containing MCP_OK. For an additional
safe test, call oracle_list_tables in an MCP client. Preview is disabled until
ORACLE_ALLOWED_TABLES is set to table names you explicitly allow (e.g. `ITAM.ASSETS`); the database user
must separately have SELECT rights on them.

## 5. Later: connect ChatGPT

When local tests pass, provide a public HTTPS URL such as
https://mcp.gyangho.com/mcp using Cloudflare Tunnel, and secure it with
MCP-compatible authentication/authorization before enabling exposure. A Tunnel
alone is NOT authorization. Keep the Oracle DB port private.

## 6. Graphify integration (existing code graphs + incremental refresh)

The optional Graphify adapter registers **five** tools on the same LKH MCP server:

| Tool | Description |
| --- | --- |
| `graphify_list_projects` | Show configured project names and whether their graph exists |
| `graphify_query` | Query relevant code modules/functions and relationships |
| `graphify_explain` | Inspect a specific graph node/concept |
| `graphify_path` | Trace a relationship between two named graph nodes |
| `graphify_update` | Refresh the graph for code added, changed or removed (explicit opt-in) |

The original Graphify CLI comes from the **graphifyy** package (double y);
the executable is named `graphify`. This adapter does not need a separate
MCP server, a second tunnel, a new TCP port, or a Graphify API key. It invokes
only fixed local Graphify CLI subcommands, not arbitrary terminal commands.
Graphify is **not** included in requirements.txt because it is normally
installed and updated separately in its own isolated environment.

Install once if not already installed:

```powershell
uv tool install graphifyy
graphify --help
Get-Command graphify | Select-Object -ExpandProperty Source
```

Open your existing `.env` without replacing Oracle credentials. Append:

```dotenv
# Only directories you explicitly choose can be queried by ChatGPT.
GRAPHIFY_PROJECTS=ITAM=C:/Users/User/Desktop/이경호/개발/ITAM;LKH_MCP=C:/Users/User/Desktop/이경호/개발/LKH_MCP
# Leave blank if graphify is on PATH; otherwise use absolute .exe path.
GRAPHIFY_EXECUTABLE=
GRAPHIFY_ALLOW_UPDATE=false
```

Adjust paths to the real project directories. Names are case-sensitive and
limited to A-Z, a-z, 0-9, hyphen, underscore. A project must already contain
`graphify-out/graph.json`. If it does not, first run the normal Graphify
initial indexing workflow **locally** against that project; the remote MCP
tools intentionally do not trigger a full initial build.

Start the existing `server.py` and test from ChatGPT:
- `graphify_list_projects` — check graph availability
- `graphify_query(project="ITAM", question="Collector login authentication")`
- `graphify_explain(project="ITAM", concept="Collector")`
- `graphify_path(project="ITAM", source="Collector", target="Backend")`

**To permit remote graph refresh**, change `GRAPHIFY_ALLOW_UPDATE=true`
and restart `server.py`, then explicitly ask ChatGPT to call
`graphify_update(project="ITAM")`. This runs `graphify update .` with
the project's directory as its working directory. It updates Graphify-generated
files and is intended to incorporate added, changed and deleted code.
It does not modify source files; however it **does write files under
`graphify-out/`**, so review the project's Git status before committing
generated data. Only one refresh may run at a time; execution is capped at
120 seconds. Larger repositories may need a local terminal refresh.

When adding MCP tools:
1. `git pull` on the Windows host and restart the existing MCP process.
2. Cloudflare Zero Trust → MCP Portals → Servers → LKH MCP → **Sync capabilities**.
3. Allow only the Graphify tools you want visible from the portal.
4. Run `graphify_list_projects` from ChatGPT and then a scoped graph query.

**Security:** Graphify graph data can reveal internal code structure and source
details. Only allowlist projects you are authorized to expose via ChatGPT.
Your Cloudflare Access policy must remain restricted to you. The adapter
forces `GRAPHIFY_BACKEND=none` to prevent accidental Graphify LLM/provider
calls and disables Graphify query logs. It cannot enforce that the data already
inside an existing graph has no secrets. Graph updates are disabled by default,
and the tool cannot accept a filesystem path or an arbitrary command from the
remote caller. Run the MCP server under a non-admin Windows account.

Test the adapter without Oracle or installed Graphify:

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_graphify_tools
```

## Warnings

- Use a separate account with only CREATE SESSION and granted SELECT on needed
  tables. `DUAL` test works even if no app tables are visible.
- This server never accepts arbitrary SQL.
- If `oracle_list_tables` returns [], check ORACLE_ALLOWED_TABLES and the
  read-only account's SELECT grants. This is NOT necessarily a connection failure.
- `.env` has secrets; do not upload/share/commit it.
- Nothing in this package can test or connect to the user's private Docker
  container from the ChatGPT runtime. Tests must run on the user's PC.

## 7. GitHub editing + local Git workflow

The ChatGPT GitHub plugin already edits hosted GitHub repositories. This
optional LKH MCP adapter adds *local* Git status/diff and explicitly enabled
push for previously committed changes. Do NOT add a GitHub PAT to this MCP.

Local MCP tools: git_list_projects, git_status(project),
git_diff(project, staged=false), git_push(project, expected_head).
None can stage, commit, pull, reset, checkout, or run arbitrary shell commands.

Append these settings to your existing .env (do not overwrite credentials):

    GIT_ALLOWED_REPOS=ITAM=gyangho/ITAM;LKH_MCP=gyangho/LKH_MCP
    GIT_EXECUTABLE=
    GIT_ALLOW_PUSH=false

Git project names map to the absolute directories already specified in
GRAPHIFY_PROJECTS. The Git origin URL MUST match the configured GitHub repo.
The Git executable is found on PATH or via GIT_EXECUTABLE (absolute path).

Workflow:
1. Locally: git status; git add -- <specific paths>; git diff --cached;
   git commit -m 'Describe changes'; git push origin HEAD.
2. In ChatGPT: use the already connected GitHub plugin to inspect the pushed
   commit, edit GitHub files, and create/push new commits or pull requests.
3. Locally on that SAME branch: git status; git pull --ff-only origin <branch>.
   Do not overwrite uncommitted changes or silently create merge commits.

Optional MCP push: set GIT_ALLOW_PUSH=true, restart server, call git_status
to get the exact 40-character HEAD, then explicitly call git_push with that
SHA. Push refuses dirty working trees, changed HEADs, unexpected remotes, and
non-fast-forward updates; requires preexisting noninteractive Git credentials.
Use Git Credential Manager on the PC; do not store PATs in .env.

After pulling LKH_MCP, restart server.py and Cloudflare MCP Portal >
MCP servers > LKH MCP > Sync capabilities, then enable the new tools.
Local adapter tests: python -m unittest -v tests.test_git_tools.

Security: Git diffs may disclose local source. Only authorize explicitly
selected repositories; keep GIT_ALLOW_PUSH=false unless genuinely needed.
Git status is local-only and is not proof that origin is up to date.

## 8. AI-reviewed local Git commits (optional)

This extension adds `git_stage_paths`, `git_preview_commit`, and `git_commit` to the same MCP
server (the existing GitHub plugin is still used for editing files on GitHub).
After pulling the new LKH_MCP code, append to the existing `.env`:

```dotenv
GIT_ALLOW_COMMIT=false
```

Set it to `true` only when allowing ChatGPT to **change the local Git index
and create commits** on registered projects. Restart MCP and Sync capabilities
in Cloudflare Portal. Existing `GIT_ALLOWED_REPOS` and `GRAPHIFY_PROJECTS`
must include the project. Push stays independently controlled by
`GIT_ALLOW_PUSH`.

Suggested workflow:
1. Ask ChatGPT to call `git_status(project="ITAM")` and review changes,
   including `git_diff(project="ITAM")` for already tracked modifications.
2. Choose **explicit individual files**, then call
   `git_stage_paths(project="ITAM", paths=["src/example.tsx"], expected_head="...")`.
   Already staged changes are rejected to avoid accidentally mixing unrelated work.
3. Call `git_preview_commit(project="ITAM")`. The MCP returns the **complete**
   staged patch, its SHA-256 fingerprint and HEAD SHA. If the patch exceeds 48 KB,
   the tool refuses remote commits rather than concealing unseen changes.
4. ChatGPT reviews the patch, drafts a meaningful commit subject/body, and calls
   `git_commit(project="ITAM", expected_head="...", expected_diff_sha256="...", subject="...", body="...")`.
   The tool re-verifies the full diff hash, HEAD, allowed file names and branch.
5. Optionally push using `git_push` after obtaining the newly created HEAD SHA
   from `git_status`. Then use the connected GitHub plugin to edit remotely;
   `git pull --ff-only` on the Windows PC afterward.

Safety:
- No `git add .`, arbitrary commands, remote edits, checkout, reset or force push.
- Secret-like filenames, symlinks, directories and large files are rejected.
- Changes to the Git index or commit require the explicit local opt-in flag.
- Repository Git hooks are disabled during the commit to reduce unintended code
  execution by hooks; commit signing is disabled for this automation.
- Repository-local Git config and Git filters are still a trust boundary. Do not
  expose this feature against untrusted repositories or under an admin account.
- It is **not** an automated secret scanner; inspect staged diff carefully.
- Only 30 files and a fully readable patch of up to 48 KB can be committed
  remotely. Larger changes should be committed locally.

Tests (do not require a live GitHub push):

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_git_commit_tools
```


## 10. Repository structure & system tray

```text
LKH_MCP/
├── server.py                 # compatible CLI entry
├── src/                      # implementation (MCP, Oracle, Git, Graphify, admin)
│   ├── server.py
│   ├── server_launcher.py    # Windows tray EXE entry
│   ├── tray.py               # native Windows tray menu
│   └── version.py            # 0.0.1
├── tests/                    # isolated unit / optional live smoke tests
├── branding/pig-terminal.png # approved CLI pig icon artwork (tracked)
├── scripts/generate_icon.py  # produce PNG and ICO from source
├── scripts/build-windows.ps1 # no-console EXE and embedded .ico
├── web/dashboard.html        # admin UI
├── docs/                     # operations guide
└── vendor/                   # UI UX Pro Max submodule
```

Run unit tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m tests.test_oracle
.\.venv\Scripts\python.exe -m tests.test_mcp
```

`python server.py` remains a supported non-tray entry point.
To launch the Windows tray and no-console process, build and run the EXE:

```powershell
.\scripts\build-windows.ps1
.\dist\LKH-MCP-v0.0.1\LKH-MCP.exe
```

The tray icon provides **대시보드 열기**, **상태 확인** and **종료**.
The tray is visible only in an interactive logged-in Windows session;
it does not appear in headless Windows services or logged-off sessions.
Both EXE and tray icons come from the approved pixel-art pig in branding/pig-terminal.png; Pillow converts that artwork into PNG and ICO without drawing a different logo.
Local secrets, build artifacts, runtime logs and generated icons are ignored.


## Docker MCP/Admin port isolation

Docker Compose uses a single backend and an unprivileged Nginx gateway.
192.0.1.22:8000 exposes only the MCP endpoint. 127.0.0.1:8001
exposes only the Cloudflare Access-protected admin endpoints.
The MCP Portal Upstream stays http://192.0.1.22:8000/mcp.
When cloudflared runs on Windows, its admin origin becomes
http://127.0.0.1:8001. The host must actually own 192.0.1.22;
a CIDR route alone does not assign this address.
Deployment details: docs/DOCKER_SQLITE_CODEX.md.
