# Oracle SELECT-only MCP — Windows local setup

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
.\.venv\Scripts\python.exe test_oracle.py
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
.\.venv\Scripts\python.exe test_mcp.py
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

## Warnings

- Use a separate account with only CREATE SESSION and granted SELECT on needed
  tables. `DUAL` test works even if no app tables are visible.
- This server never accepts arbitrary SQL.
- If `oracle_list_tables` returns [], check ORACLE_ALLOWED_TABLES and the
  read-only account's SELECT grants. This is NOT necessarily a connection failure.
- `.env` has secrets; do not upload/share/commit it.
- Nothing in this package can test or connect to the user's private Docker
  container from the ChatGPT runtime. Tests must run on the user's PC.
