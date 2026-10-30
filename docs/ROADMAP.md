# LKH MCP 통합 로드맵 v2.0 — Windows Installer + Phase 0–9

**계획일:** 2026-10-30 · **현재:** Naru Docker+Windows Agent · **목표:** Windows Native Installer
**상태 규칙:** NOT_STARTED / IN_PROGRESS / IMPLEMENTED(CI) / VERIFIED(Windows E2E) / RELEASED(운영) / BLOCKED.
정본 설계: [아키텍처](ARCHITECTURE.md), [설치기](WINDOWS_INSTALLER_DESIGN.md), [인증](SECURITY_AND_ENROLLMENT.md), [출시](MIGRATION_AND_RELEASE.md).

## 제품 수락 조건

1. `LKH-MCP-Setup.exe` **하나로 설치·업데이트·제거**, 프로그램은 Windows Service/Tray/Codex Agent 3개 역할로 분리. Agent용 별도 Supervisor 상주 금지.
2. Service는 부팅 후 로그인 없이 동작. Task Scheduler는 Codex 로그인 사용자의 고정 `LKH-Codex-Agent` 작업을 실행. 관리자/트레이에서 시작·중지·재시작, 실시간 상태.
3. 승인된 `branding/pig-terminal.png` Pixel Pig를 원본으로 트레이 Online **초록**, Offline **핑크**, Server 장애·상태 미확인은 **회색**. 색 외에 텍스트 상태 및 tooltip 제공.
4. Installer에서 신뢰 관계 최초 등록, OS 보호 자격증명 기반으로 Agent가 서버에 자동 인증·단기 토큰 수신·갱신. 서버에서 토큰 재발급해도 Windows PowerShell/파일 수동 수정 불필요. **무인증 토큰 발급 API 불가**.
5. 기존 MCP API/Oracle/관리자/권한/Graphify/작업 큐와 Codex CLI 이벤트 기반 콘솔·지침 관리·감사/로그/메트릭·Skill 검증.
6. 실제 Docker, Naru, Cloudflare private WARP 경계 및 SQLite 데이터는 Native 동등성/백업/롤백 검증과 별도 cutover 승인 전 유지.

## 기준선 (2026-10-30)

| 항목 | 상태 | 이미 확인된 것 / 미확인 |
|---|---|---|
| Phase 0 Heartbeat·Agent 상태 | **IMPLEMENTED, E2E UNVERIFIED** | PR #2, CI PASS, 실제 Windows 큐 claim 관측. Verify 첫 실행 임시 worktree ACL 실패, 다음 실행 MXC SystemDrive 실패. PR #3/#4 수정은 CI 성공, 이후 실제 Verify PASS는 미확인 |
| GitHub→Windows Codex 작업 큐 | **IMPLEMENTED** | 정확한 SHA/레포 allowlist/lease/fix 관리자 승인/Graphify snapshot. 실 Windows 전체 테스트 잔여 |
| 기존 PyInstaller·Tray 시제품 | **IMPLEMENTED (prototype)** | `scripts/build-windows.ps1`, `src/server_launcher.py`·`src/tray.py` 존재. 서비스·독립 트레이·Installer 아님 |
| I0–I7 | **I0–I7 IN_PROGRESS (staging code; Windows 실기·출시 미검증)** | I0 분석, I1 dual route, I2 SCM, I3 Task, I4 Pig, I5 DPAPI enrollment, I6 unsigned Inno staging, I7 SQLite backup 코드는 존재; 개별 Windows 서비스 설치·실기·보안 및 컷오버 미검증 |
| Phase 1–9 | **IN_PROGRESS (refac 코드 구현, CI·실기 검증 분리)** | 이벤트·지침·운영 로그·메트릭·React UI·Skill 작업을 refac에 추가. 각 Phase의 코드와 CI 및 현장 E2E 결과는 [진행 증빙](PHASES_1_9_STATUS.md) 참조 |
| Agent 자동 토큰 등록 | **NOT_STARTED** | 관리 UI 일회성 토큰 복사 PR #5는 요구 불일치로 PR #6 revert |

## 트랙 A 첫 구현: refac 브랜치 (I0/I1 진행 중)

- [I0 기준선·전환 위험 인벤토리](TRACK_A_I0_BASELINE.md)를 코드와 대조하여 작성. 실 Naru/WARP/Oracle/Windows 점검은 남아 있으며 I0는 VERIFIED가 아니다.
- I1은 `src/native_runtime.py` + `src/native_server.py`의 **loopback 전용 포트 18080 staging**과 독립 ProgramData SQLite 경로, `--check` 패키지 검증, `scripts/build-native-server.ps1`, Windows Actions 패키징 단계까지 시작.
- 현재 서버 단일 백엔드는 `/mcp`와 `/admin`을 함께 호스팅한다. Native preview를 비루프백에 노출하지 않으며, **동등한 포트·경로 격리를 구현하기 전 I1 완료/배포 판정 금지**.
- PyInstaller에서 UI UX Pro Max 툴은 외부 Python 경로가 필요한 구조이므로 완전한 Native 기능 동등성은 아직 불합격.
- Windows 실행환경에서의 설치/서비스/Oracle Thick/Cloudflare/WARP/트레이 상태 검증은 별도 미완료.

## I0–I7 refac 실행 증빙

[실제 구현·시험·출시 게이트 기록](TRACK_A_IMPLEMENTATION_STATUS.md) 참고. 현재는 Native 시제품과 unsigned installer를 빌드하는 단계로, I2–I7의 코드는 초기 구현이지만 환경 검증/서명/실제 컷오버가 필요하다. Live Naru, Cloudflare, Oracle, 생산 DB를 수정하지 않는다.

## A 트랙: Windows Native 기반 I0–I7

| 단계 | 산출물과 작업 | 수락 기준 |
|---|---|---|
| **I0** 분석 | Docker/Naru/Cloudflare·Oracle 11g Thick·Windows 11·Agent 계정·Port·SQLite WAL·기존 Pixel Pig/Tray 의존성 인벤토리, ADR | 현재 운영 영향·보안 경계·이전/롤백/테스트 매트릭스 승인 |
| **I1** Windows 서버 | React 정적 번들+Python MCP 패키징(onedir), Native 분리된 앱 리스너·ProgramData 경로, Oracle 의존성 | Windows VM에서 MCP/Admin 기능·비공개 포트·Oracle fake+real smoke, Docker 비교 |
| **I2** SCM Service | 부팅 자동 시작·실패 복구·저권한 계정·DB/log ACL·서비스의 IPC 접근 | 로그오프·재부팅·crash 후 복구, 일반 사용자 관리자 권한 불필요 |
| **I3** Agent 스케줄러 제어 | 기존 Agent를 작업으로 등록, 서버/관리자/트레이에서 고정 태스크 start/stop/restart, 중복·busy·감사 처리 | 추가 상주 Supervisor 없음, 작업 시작 수락과 heartbeat Online 별도 검증 |
| **I4** Pixel Pig Tray | 독립 Tray EXE, 기존 픽셀 돼지의 상태별 팔레트·아이콘, tooltip/menu/관리/로그 | 녹색/핑크/회색/실패별 E2E, 트레이 종료 후 MCP는 계속 실행, 16px 판독 |
| **I5** 장치 등록·자동 인증 | Installer 장치 키/OS principal 최초 등록, Named Pipe/CNG/DPAPI 보호, 단기 토큰·갱신/폐기, 서버 감사 | 최초 승인 뒤 수동 토큰 전달 0회, 재발급 자동 재연결, 위조/재생/권한 거부 |
| **I6** Installer | 서명된 Inno Setup Setup.exe, 서비스·태스크·트레이·ACL 설치, 유지보수/업그레이드/제거 | 깨끗한 Win11 VM의 설치·부팅·업데이트·제거/재설치·보존 동작, 서명·SBOM |
| **I7** 컷오버 | Docker 볼륨 SQLite 일관 백업, Native 스테이징·데이터 이전·URL/Firewall/Cloudflare 검증·롤백 리허설 | 운영 DB 건수/감사·Graph SHA 비교, Native E2E, **별도 운영 전환 승인** |

I 트랙 기본 선행: `I0→I1→I2→I3→I4→I5→I6→I7`. I5 인증 설계는 I2/I3와 병렬 검토 가능하나 완성된 Installer에는 반드시 포함.

## 트랙 B Phase 1–9 개발 변경사항

`refac`에 Phase 1 JSONL 이벤트 원장과 Phase 2 실시간 조회 UI, Phase 3 실패 격리, Phase 4–6 지침의 버전·승인 발행·MCP 조회, Phase 7–8 구조화 로그·리소스 지표, Phase 9 개발 Skill과 회귀 테스트를 단계별로 추가했다. **운영 E2E 배포는 사용자가 검증할 수 있는 시점까지 보류**하고, CI 실패는 완료로 처리하지 않는다. 자세한 구현·차단·릴리스 증거는 [PHASES_1_9_STATUS](PHASES_1_9_STATUS.md).

## B 트랙: MCP 기능 Phase 0–9

| Phase | 작업 범위 및 산출물 | 단계별 수락 기준 |
|---|---|---|
| **0** 연결/Heartbeat | Windows Agent private API, 45초 Online, Offline/Busy, Codex 설치·로그인 상태 | 401/403/404, restart, dirty repo 차단, 실제 Windows verify PASS/clean worktree |
| **1** Codex JSONL | `codex exec --json` 스트리밍, 안전한 이벤트 정규화, `codex_task_events` SQLite, seq/cursor·크기·보존·secret redaction | 실행 중 점진 이벤트 도착, 중복·끊김·timeout·정보 노출 테스트 |
| **2** 실시간 CLI 콘솔 | 기존 `/admin/codex` 내 터미널형 이벤트 뷰, task timeline/필터/과거 이력, 승인·상태·재연결 | 1~2초 polling 또는 검토된 SSE, 페이지 재접속 후 커서, 상태/권한·접근성 |
| **3** 실기 통합 안정화 | Windows MXC, ACL/temp worktree cleanup, claim/lease/offline/재시도, Graphify 출력/보호·실패 분리 | 실제 verify+diagnose 성공, 원본 git 변경 0, 실패/취소/서버·Agent 재시작 검증 |
| **4** 지침 영속 저장 | SQLite 지침/versions, scope(global/project/agent/tool), draft/published/revoked, 충돌/감사/DB migration | 동시 수정/optimistic revision/백업·권한·수명 테스트 |
| **5** 지침 MCP 읽기 | `instructions_list`, `instructions_get`, 적용 scope resolve, 버전 provenance, read-only | 승인된 published만 조회, 범위 우선순위/불허 scope·비밀 제외 |
| **6** 지침 관리 UI | 지침 생성·수정·diff/preview·발행 승인·검색·rollback·감사 | 관리자 세션·CSRF/충돌/인증/복구 E2E |
| **7** 서버 로그 | 구조화 API/도구/에이전트/인증/감사 log, correlation ID, 마스킹·보존·검색 UI | token/원문 프롬프트 미저장, 보존기간·용량·권한/검색 검증 |
| **8** 리소스 계측 | CPU/RSS, 요청수/실패율/지연·큐/agent, 차트/시간 버킷/집계 보존 | 재시작·부하/오류 케이스, 시각화·접근제어·집계 정확성 |
| **9** Skill·전체 릴리스 | LKH Development Skill, 사용 예·환경별 API, 회귀/보안·Installer 통합 검증/운영 runbook | G0–G5 Gate PASS, 사용성/실기/보안/롤백 증빙 및 운영 승인 |

**지침 우선순위(미확정 초안):** `tool > agent > project > global`; 충돌 정책은 Phase 4 계약 테스트 전에 최종 승인한다. Draft는 MCP 조회에 노출하지 않는다.

## 권장 시행 순서와 독립 승인 게이트

- **Wave A:** Phase 0 실제 Verify, Phase 3의 ACL cleanup 문제 선조치, I0 환경·설계 위험 검증.
- **Wave B:** I1→I2→I3→I5 서버/Agent/인증 기반; Phase 1 JSONL은 별도 브랜치에서 병행 가능.
- **Wave C:** I4 Tray + Phase 2 CLI 콘솔 + Phase 3 Windows E2E + I6 Installer.
- **Wave D:** Phase 4→5→6 지침, Phase 7→8 로그·관측.
- **Wave E:** I7 DB/네트워크 이관 리허설 → Phase 9 Skill·전면 회귀 → **사용자 운영 승인** → 배포/롤백 관찰.

| 게이트 | 통과 요건 |
|---|---|
| **G0** 계약 | 포트/DB/계정·등록/복구 보안 설계 합의 |
| **G1** PR CI | Python/Frontend/gateway 및 Windows 패키지 빌드 PASS |
| **G2** Windows E2E | MXC, 서비스/스케줄러, Agent/트레이, Cloudflare/Oracle 테스트 |
| **G3** 보안 | 미인증/재생/토큰 탈취·CSRF/임의 명령 차단, 로그 마스킹 |
| **G4** 데이터 | SQLite WAL 포함 일관 백업·복원, 마이그레이션/롤백 |
| **G5** 컷오버 | 명시적 별도 사용자 승인, Naru/Docker 롤백 경로 검증 |

**범위 제외:** 별도 상주 Supervisor, Agent 임의 원격 shell, 미인증 토큰 다운로드, 광역 공개 Tunnel, 승인 없는 자동 commit/push/fix 적용, 검증 전 Docker/운영 DB 파괴. 모든 완료 표시는 PR/커밋/CI와 실 Windows 테스트 증거를 분리해 기록한다.
