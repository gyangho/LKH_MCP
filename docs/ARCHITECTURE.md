# 아키텍처 — AS-IS / TO-BE

2026-10-30 · 목표 아키텍처는 **계획**이며 실제 배포가 아니다.

## AS-IS: Naru + Windows Agent

```text
ChatGPT → Cloudflare MCP Portal/Private CIDR → Naru Nginx :8000 (/mcp만)
관리자 WARP Private Access → Windows :8001 → Naru Nginx :8001 (/admin만)
                                            ↓
                                 Python MCP (Docker :8000)
                                 SQLite mcp-data volume
                                            ↑
Windows Agent.py (Codex 로그인 사용자) → loopback outbound /admin/agent/*
    ├─ allowlisted Git checkout + exact expected SHA / clean tree
    └─ detached temporary worktree → Codex CLI / Graphify skill
```

- Nginx 8000은 `/mcp`, `/mcp/` 외 404, 8001은 `/admin`/`/admin/*` 외 404. 단일 Python backend의 내부 포트에 직접 접근하면 분리 보장이 사라지므로 **게이트웨이 우회 불허**.
- 관리자 세션·Origin/Host CSRF·WARP 개인 정책과 Windows Agent token은 별도 인증 계층이다.
- Queue 상태/Graphify 결과는 SQLite, Agent는 저장소를 임시 worktree에서만 읽고 수정안은 제안만 한다.
- `src/server_launcher.py`/`src/tray.py`는 기존 서버+트레이 결합 **시제품**이다. 서비스/독립 트레이 Installer가 아니다.

## TO-BE: Windows Native

```text
       LKH-MCP-Setup.exe [서명/설치/업데이트/제거]
                       │
      ┌────────────────┼──────────────────┐
      │                │                  │
LKH-MCP-Server.exe  LKH-MCP-Tray.exe  LKH-Codex-Agent.exe
Windows SCM         사용자 로그인     Windows Task Scheduler
저권한 서비스 계정  세션 트레이 UI     Codex 로그인 계정
      │                │                  │
      ├─ MCP / Admin    │                  ├─ Git SHA/Repo allowlist
      ├─ SQLite         └─ ACL IPC────────┤  + Codex CLI
      ├─ 보안 이벤트/로그                  │
      └─ 고정 Task Scheduler 작업 제어────┘
```

- 부팅 후 로그인 없이 MCP Service가 살아야 하고, 트레이만 로그인 시 표시한다. **별도 상주 Supervisor를 만들지 않는다.**
- Service에서 사전 등록된 이름의 스케줄러 작업만 제어. 원격 arbitrary command/shell 금지.
- 초록 Pixel Pig = 최근 인증된 heartbeat로 Agent Online, 핑크 = 서버 정상·Agent Offline, 회색 = 서버/상태 판별 불가. Busy/Error는 텍스트/경고로 구분. 시각 원본은 `branding/pig-terminal.png`.
- 저장 위치 목표: `%ProgramFiles%\LKH MCP\` 바이너리(사용자 쓰기 불가), `%ProgramData%\LKH-MCP\` DB/설정/로그/백업(서비스 ACL). Codex 로그인/기기 개인키는 사용자/OS 보호 저장소에 분리.
- 한 PC 내 인증은 Windows Named Pipe ACL·OS identity + CNG/DPAPI 키 활용을 검토. 원격 Agent는 범위 밖.
- 서버 라우팅은 8000 MCP-only, 8001 Admin-only와 동등한 방화벽/정확한 경로 필터를 실기에서 증명. 필요시 별도 listener/reverse proxy 유지하되 인터넷 공개 금지.
- Oracle 11g가 필요하면 Windows Thick driver/Instant Client 검증; 인스톨러가 Oracle 데이터베이스를 설치·변경하지 않는다.
- Native 스테이징은 원본 Docker SQLite 볼륨을 공유하지 않는다. 백업한 **복제본**에서 검증하고 별도 컷오버 승인 전 원본과 동시 쓰기 금지.

## 실패 및 안전 조건

Agent 시작 요청 성공은 스케줄러의 수락일 뿐이며 실제 성공은 인증 Heartbeat로 판정. Offline과 Unknown 혼동 금지. 네트워크 끊김/lease 만료는 임의 재실행이 아닌 실패·관리자 검토. Codex 실행은 임시 디렉터리 ACL 실패를 결과/정리 실패로 각각 기록해야 한다.

현재 Docker 제거/Cloudflare 라우팅 변경/운영 DB 스키마 파괴는 이 설계 문서의 승인 범위에 포함되지 않는다.
