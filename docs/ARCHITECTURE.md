# Windows Native 아키텍처

2026-11-02 · Native 구성은 staging 코드로 구현되어 있으나 실제 운영 전환을 뜻하지 않는다.

## Windows Native: staging 구현 및 목표

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
      ├─ SQLite         └─ loopback 상태───┤  + Codex CLI
      ├─ 보안 이벤트/로그                  │
      └─ 고정 Task Scheduler 작업 제어────┘
```

- 부팅 후 로그인 없이 MCP Service가 살아야 하고, 트레이만 로그인 시 표시한다. **별도 상주 Supervisor를 만들지 않는다.**
- Service에서 사전 등록된 이름의 스케줄러 작업만 제어. 원격 arbitrary command/shell 금지.
- 원본 컬러 Pixel Pig = 최근 인증된 heartbeat로 Agent Online, 흑백 = 서버 정상·Agent Offline, 회색 = 서버/상태 판별 불가. Busy/Error는 텍스트/경고로 구분. 시각 원본은 `branding/pig-terminal.png`.
- 저장 위치 목표: `%ProgramFiles%\LKH MCP\` 바이너리(사용자 쓰기 불가), `%ProgramData%\LKH-MCP\` DB/설정/로그/백업(서비스 ACL). Codex 로그인/기기 개인키는 사용자/OS 보호 저장소에 분리.
- 같은 PC 인증은 machine-DPAPI 보호 secret과 loopback 단기 토큰을 사용한다. CNG 비내보내기 키와 challenge-response는 미구현이며 원격 Agent는 범위 밖이다.
- 서버 라우팅은 8000 MCP-only, 8001 Admin-only와 동등한 방화벽/정확한 경로 필터를 실기에서 증명. 필요시 별도 listener/reverse proxy 유지하되 인터넷 공개 금지.
- Oracle 11g가 필요하면 Windows Thick driver/Instant Client 검증; 인스톨러가 Oracle 데이터베이스를 설치·변경하지 않는다.

## 실패 및 안전 조건

Agent 시작 요청 성공은 스케줄러의 수락일 뿐이며 실제 성공은 인증 Heartbeat로 판정. Offline과 Unknown 혼동 금지. 네트워크 끊김/lease 만료는 임의 재실행이 아닌 실패·관리자 검토. Codex 실행은 임시 디렉터리 ACL 실패를 결과/정리 실패로 각각 기록해야 한다.


운영 DB 및 네트워크 변경은 별도 승인과 백업·복구 검증이 필요하다.

## Oracle 연결과 설치 초기 설정

설치 마법사 → 관리자 계정·암호 검증 → 비공개 stdin 파이프 → 초기 설정 도우미 → 암호 해시 bootstrap의 순서로 최초 관리자를 구성한다. 기존 설정은 원자적 no-replace 저장으로 보존한다. Oracle 접속정보는 설치기에서 입력받지 않는다.

관리자 Oracle 화면 → 세션·CSRF 관리 API → 연결 저장소(SQLite metadata + machine-DPAPI 암호문) → connection_id로 선택한 요청별 Oracle 연결의 순서다. Client 초기화만 프로세스 공통이고 계정·DSN·조회 허용 목록은 연결별이다. 연결 풀은 공유하지 않고 요청 종료 시 닫는다.

승인 저장소는 SQLite `approved_repositories`에서 관리하며 Codex 큐와 같은 트랜잭션 경계에서 승인 변경·대기 작업 취소를 처리한다. 실행 중인 프로젝트의 승인은 변경할 수 없다. Agent의 로컬 checkout 매핑은 이 서버 목록과 독립적으로 검증한다.
