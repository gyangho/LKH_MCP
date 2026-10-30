# 현재 운영 가이드 — Naru Docker + Windows Codex Agent

**상태:** AS-IS (Native Installer 출시 전까지 정본). 2026-10-30

## 포트 및 접근

- 현재 설정 예: Cloudflare MCP Portal private CIDR `192.0.1.22:8000/mcp`; 관리자 WARP Private Access+로그인 `192.0.1.22:8001/admin`(Windows portproxy와 실제 IP 확인 필요).
- Nginx 8000에서 `/mcp` 외 차단, 8001에서 `/admin` 외 차단. Docker MCP backend 직접 접근 금지.
- 관리자 세션은 독립 패스워드 인증·Origin/Host/CSRF. 8001 공개 Tunnel이나 광범위한 Windows inbound 방화벽 금지.

## Docker 업데이트 (운영 승인/진행 작업 확인 후)

```powershell
git status --short
git pull --ff-only origin main
git submodule update --init --recursive
docker --context naru compose -f compose.yaml config
docker --context naru compose -f compose.yaml up -d --build
docker --context naru compose -f compose.yaml ps
docker --context naru compose -f compose.yaml logs --tail=100 gateway mcp
```

기존 볼륨 `mcp-data`와 무추적 `secrets/bootstrap.json` 보존. **`docker compose down -v` 금지**. Oracle 컨테이너는 본 Compose의 관리 대상이 아님. 업데이트는 Windows Agent 프로세스를 자동 재시작하지 않는다.

## 관리자 bootstrap/설정

`secrets/bootstrap.json`에 `ORACLE_PASSWORD`, `ADMIN_LOGIN_USER`, `ADMIN_PASSWORD_HASH`, `ADMIN_PUBLIC_ORIGIN`, `CODEX_AGENT_TOKEN` 등 승인된 secret을 유지한다. 일반 설정은 SQLite/`/admin/config`, 웹은 `/admin/codex`. 비밀 원문을 Git/채팅/로그에 노출하지 않는다.

관리자 비밀번호 해시 생성(입력 비표시):

```powershell
python -c "import sys,getpass;sys.path.insert(0,'src');from admin_auth import make_password_hash;print(make_password_hash(getpass.getpass('Admin password: ')))"
```

Cloudflare WARP Private Access 정책으로 본인 계정만 8001에 접근하도록 하고 독립 관리자 세션 사용. 서버 재시작 시 메모리 세션은 초기화된다.

## Windows Agent (현행, 자동 enrollment 미구현)

1. `windows_agent/config.example.json`을 복사해 무추적 `config.json`에 repo/Windows checkout 절대경로/`server_url`을 지정.
2. 같은 PC에서 실행 계정에 Git, Codex CLI 로그인, Graphify Codex skill 준비. 서버 설정 `CODEX_AGENT_ENABLED=true`, `GIT_ALLOWED_REPOS`, `CODEX_MAX_RUNS_PER_DAY` 확인.
3. 현재는 보호된 부트스트랩에서 환경변수를 전달한다. **최종 Installer I5가 이를 자동화할 계획**.

```powershell
$env:LKH_CODEX_AGENT_TOKEN = (Get-Content .\secrets\bootstrap.json -Raw | ConvertFrom-Json).CODEX_AGENT_TOKEN
python .\windows_agent\agent.py --config .\windows_agent\config.json --once
python .\windows_agent\agent.py --config .\windows_agent\config.json
```

Agent는 아웃바운드 `/admin/agent/heartbeat|claim|complete` 사용. API 401=token, 403=비활성/승인, 404=서버 이미지/라우트 구버전 가능성. Online=인증 heartbeat 45초, Busy=서버 작업 claim. `verify`/`diagnose`/`fix`(승인된 임시 worktree 패치 제안만)/`graphify` 지원. `expected_sha` 40자·dirty tree 보호, 원본 checkout 자동 수정/commit/push 불가.

## 장애 진단

```powershell
Get-NetIPAddress -IPAddress 192.0.1.22 -ErrorAction SilentlyContinue
Get-NetTCPConnection -State Listen -LocalPort 8000,8001 -ErrorAction SilentlyContinue
netsh interface portproxy show all
Test-NetConnection 127.0.0.1 -Port 8001
codex --version
codex login status
git status --short
python -c "from windows_agent.agent import safe_env; print([(k,v) for k,v in safe_env().items() if k.upper() == 'SYSTEMDRIVE'])"
```

- `HTTP 404` Heartbeat: Naru MCP 이미지가 새 API로 재빌드됐는지 확인(재빌드 후 증상 해소 보고됨).
- `WinError 5` 임시 `frontend/node_modules`: 해당 **한 작업의** temp worktree ACL과 Git worktree 상태를 조사. 광범위한 Temp ACL 수정/무조건 강제 삭제 금지.
- `MXC requires nonempty Unicode host SystemDrive`: Agent `safe_env` 버전/윈도우 환경변수 확인(PR #3/#4). `SystemDrive` vs `SYSTEMDRIVE` 딕셔너리 키 대소문자 주의.
- Windows 11 Codex MXC는 `prefer_mxc = true` 지원·테스트 가능. 기본 `danger-full-access` 금지.
- 이전 두 번의 실제 Verify는 ACL cleanup 및 MXC SystemDrive로 실패했으므로 **Phase 0 Windows E2E 최종 PASS는 미확인**.

## 테스트·데이터 보존

```powershell
python -m compileall -q src windows_agent tests
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -t . -p "test_*.py" -v
cd frontend
npm ci
npm run build
```

운영 DB는 `mcp-data` named volume에 있고 SQLite WAL 정합성 없이 활성 DB 파일만 복사하면 안 된다. 이력/설정/Graphify 손실 없이 전환하려면 [마이그레이션](MIGRATION_AND_RELEASE.md) 절차와 별도 운영 승인이 필요. Cloudflare Portal 도구 등록 변경 시 capabilities 동기화 확인.
