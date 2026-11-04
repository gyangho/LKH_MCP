# LKH MCP 통합 로드맵 v2.0 — Windows Installer + Phase 0–9

2026-11-04 Agent 시작 복구: 설치본 0.0.5에서 기본 예약 작업 시작이 `0x800710E0`으로 거부되는 것을 재현했다. 등록 계정의 활성 세션을 명시한 시작으로 실제 Agent Running/heartbeat Online을 확인했다. 관리자 start/restart 소스에 같은 계정 SID·세션 선택을 추가했으며 관련 37개 테스트가 통과했다. 새 서비스 바이너리 배포 및 관리자 버튼 E2E는 별도 미검증이다. [검증 기록](VERIFICATION.md)을 참조한다.

2026-11-04 검증 준비 단계: Agent 로컬에 저장소·정본 경로로 묶인 opt-in 프로필을 추가했다. 임시 worktree에 승인된 Gradle/npm 자산을 준비하고 관리 정책이 적용된 workspace 샌드박스 사전 실행이 성공해야 Codex 검증을 시작한다. 루프백 정책 자동 완화·다운로드·운영 배포는 포함하지 않는다. 실제 설치본 반영 및 대상 PC E2E는 미검증이며 [빌드·설정](BUILD_AND_CONFIGURATION.md)의 준비 절차를 따른다.

2026-11-04 현장 복구: Portal이 이전 IP의 서버를 참조해 발생한 handshake timeout을 현재 주소의 기존 등록 서버로 교체해 복구했다. 실제 Portal에서 지침·Oracle 두 연결·Codex 진단·Graphify 조회가 정상 응답했다. Agent heartbeat Online을 확인했으나 스케줄러 자동 시작은 별도 미검증이다. 상세 증거는 [검증](VERIFICATION.md)을 참조한다.

2026-11-03 현장 보완: 공개 스킬 소스 ACL을 복구해 UIUX 실제 검색과 Graphify 합성 AST 생성을 확인했다. Oracle의 frozen DLL 검색/PATH 문제를 재현·수정하고 서비스 전용 PATH 보완 후 `itam-dev` 실제 조회가 성공했다. Graphify 프로젝트 동기화는 승인 저장소의 미커밋 변경 검사로 차단된 상태다. 새 설치기 빌드와 전체 Native E2E는 미검증이며 상세 증거는 [검증](VERIFICATION.md)을 참조한다.

**계획일:** 2026-10-30 · **범위:** Windows Native Installer
**상태 규칙:** NOT_STARTED / IN_PROGRESS / IMPLEMENTED(CI) / VERIFIED(Windows E2E) / RELEASED(운영) / BLOCKED.
정본: [기능](FEATURES.md), [아키텍처](ARCHITECTURE.md), [빌드·운영](BUILD_AND_CONFIGURATION.md), [검증](VERIFICATION.md).

## 제품 수락 조건

1. `LKH-MCP-Setup.exe` **하나로 설치·업데이트·제거**, 프로그램은 Windows Service/Tray/Codex Agent 3개 역할로 분리. Agent용 별도 Supervisor 상주 금지.
2. Service는 부팅 후 로그인 없이 동작. Task Scheduler는 Codex 로그인 사용자의 고정 `LKH-Codex-Agent` 작업을 실행. 관리자/트레이에서 시작·중지·재시작, 실시간 상태.
3. 승인된 `branding/pig-terminal.png` Pixel Pig를 원본으로 트레이 서버+인증 Agent Online **원본 컬러**, 서버만 Online **흑백**, 서버 장애·상태 미확인은 **회색**. 색 외에 텍스트 상태 및 tooltip 제공.
4. Installer에서 신뢰 관계 최초 등록, OS 보호 자격증명 기반으로 Agent가 서버에 자동 인증·단기 토큰 수신·갱신. 서버에서 토큰 재발급해도 Windows PowerShell/파일 수동 수정 불필요. **무인증 토큰 발급 API 불가**.
5. 기존 MCP API/Oracle/관리자/권한/Graphify/작업 큐와 Codex CLI 이벤트 기반 콘솔·지침 관리·감사/로그/메트릭·Skill 검증.
6. Cloudflare private WARP 경계 및 SQLite 데이터의 백업·복구·보안 검증 후 별도 운영 승인.
7. Native Pig 트레이에는 서버 종료 및 서버+Agent 동시 종료 메뉴를 제공하되, Windows SCM/UAC 확인과 활성 작업 차단을 적용한다. 사용자 환경의 UAC/서비스 실제 종료는 별도 E2E 검증이 필요하다.

## 기준선 (2026-10-30)

| 항목 | 상태 | 이미 확인된 것 / 미확인 |
|---|---|---|
| Phase 0 Heartbeat·Agent 상태 | **IMPLEMENTED, E2E UNVERIFIED** | PR #2, CI PASS, 실제 Windows 큐 claim 관측. Verify 첫 실행 임시 worktree ACL 실패, 다음 실행 MXC SystemDrive 실패. PR #3/#4 수정은 CI 성공, 이후 실제 Verify PASS는 미확인 |
| GitHub→Windows Codex 작업 큐 | **IMPLEMENTED** | 정확한 SHA/레포 allowlist/lease/fix 관리자 승인/Graphify snapshot. 실 Windows 전체 테스트 잔여 |
| I0–I7 | **I0–I7 IN_PROGRESS (staging code; Windows 실기·출시 미검증)** | I0 분석, I1 dual route, I2 SCM, I3 Task, I4 Pig, I5 DPAPI enrollment, I6 unsigned Inno staging, I7 SQLite backup 코드는 존재; 개별 Windows 서비스 설치·실기·보안 및 컷오버 미검증 |
| Phase 1–9 | **IN_PROGRESS (refac 코드 구현, CI·실기 검증 분리)** | 이벤트·지침·운영 로그·메트릭·React UI·Skill 작업을 refac에 추가. 각 Phase의 코드와 CI 및 현장 E2E 결과는 [진행 증빙](VERIFICATION.md) 참조 |
| Native Agent 자동 토큰 등록 | **IN_PROGRESS** | 같은 PC DPAPI 기반 등록·단기 토큰 코드가 있으며 대상 PC 검증 및 강화된 장치 증명은 남음. |

## 트랙 A 구현 현황

Native 서버·분리 리스너·서비스·작업 스케줄러·트레이·DPAPI 등록 및 unsigned 설치기 코드가 있다. 코드, CI와 대상 Windows 검증은 아래 증빙에서 구분한다. 빌드 및 설정 경로는 [빌드와 설정](BUILD_AND_CONFIGURATION.md)을 참조한다.

## A 트랙: Windows Native 기반 I0–I7

| 단계 | 산출물과 작업 | 수락 기준 |
|---|---|---|
| **I0** 분석 | Cloudflare·Oracle 11g Thick·Windows 11·Agent 계정·Port·SQLite WAL·기존 Pixel Pig/Tray 의존성 인벤토리, ADR | 현재 운영 영향·보안 경계·이전/롤백/테스트 매트릭스 승인 |
| **I1** Windows 서버 | React 정적 번들+Python MCP 패키징(onedir), Native 분리된 앱 리스너·ProgramData 경로, Oracle 의존성 | Windows VM에서 MCP/Admin 기능·비공개 포트·Oracle fake+real smoke |
| **I2** SCM Service | 부팅 자동 시작·실패 복구·저권한 계정·DB/log ACL·서비스의 IPC 접근 | 로그오프·재부팅·crash 후 복구, 일반 사용자 관리자 권한 불필요 |
| **I3** Agent 스케줄러 제어 | 기존 Agent를 작업으로 등록, 서버/관리자/트레이에서 고정 태스크 start/stop/restart, 중복·busy·감사 처리 | 추가 상주 Supervisor 없음, 작업 시작 수락과 heartbeat Online 별도 검증 |
| **I4** Pixel Pig Tray | 독립 Tray EXE, 기존 픽셀 돼지의 상태별 팔레트·아이콘, tooltip/menu/관리/로그 | 원본 컬러/흑백/회색/실패별 E2E, 트레이 종료 후 MCP는 계속 실행, 16px 판독 |
| **I5** 장치 등록·자동 인증 | Installer 장치 키/OS principal 최초 등록, Named Pipe/CNG/DPAPI 보호, 단기 토큰·갱신/폐기, 서버 감사 | 최초 승인 뒤 수동 토큰 전달 0회, 재발급 자동 재연결, 위조/재생/권한 거부 |
| **I6** Installer | 서명된 Inno Setup Setup.exe, 서비스·태스크·트레이·ACL 설치, 3모드 제거·SQLite 보존/검증 백업, 유지보수/업그레이드/제거 | 깨끗한 Win11 VM의 설치·부팅·업데이트·제거/재설치·보존 동작, 서명·SBOM |
| **I7** 컷오버 | SQLite 일관 백업, Native 스테이징·복구·URL/Firewall/Cloudflare 검증·롤백 리허설 | 운영 DB 건수/감사·Graph SHA 비교, Native E2E, **별도 운영 전환 승인** |

I 트랙 기본 선행: `I0→I1→I2→I3→I4→I5→I6→I7`. I5 인증 설계는 I2/I3와 병렬 검토 가능하나 완성된 Installer에는 반드시 포함.

## 트랙 B Phase 1–9 개발 변경사항

`refac`에 Phase 1 JSONL 이벤트 원장과 Phase 2 실시간 조회 UI, Phase 3 실패 격리, Phase 4–6 지침의 버전·승인 발행·MCP 조회, Phase 7–8 구조화 로그·리소스 지표, Phase 9 개발 Skill과 회귀 테스트를 단계별로 추가했다. **운영 E2E 배포는 사용자가 검증할 수 있는 시점까지 보류**하고, CI 실패는 완료로 처리하지 않는다. 자세한 구현·차단·릴리스 증거는 [검증](VERIFICATION.md).

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

**구현된 지침 우선순위:** `tool > agent > project > global`; 공개 범위 정책의 최종 검토는 남아 있다. Draft는 MCP 조회에 노출하지 않는다.

## 권장 시행 순서와 독립 승인 게이트

- **Wave A:** Phase 0 실제 Verify, Phase 3의 ACL cleanup 문제 선조치, I0 환경·설계 위험 검증.
- **Wave B:** I1→I2→I3→I5 서버/Agent/인증 기반; Phase 1 JSONL은 별도 브랜치에서 병행 가능.
- **Wave C:** I4 Tray + Phase 2 CLI 콘솔 + Phase 3 Windows E2E + I6 Installer.
- **Wave D:** Phase 4→5→6 지침, Phase 7→8 로그·관측.
- **Wave E:** I7 DB/네트워크 이관 리허설 → Phase 9 Skill·전면 회귀 → **사용자 운영 승인** → 배포/롤백 관찰.

| 게이트 | 통과 요건 |
|---|---|
| **G0** 계약 | 포트/DB/계정·등록/복구 보안 설계 합의 |
| **G1** PR CI | Python/Frontend 및 Windows 패키지 빌드 PASS |
| **G2** Windows E2E | MXC, 서비스/스케줄러, Agent/트레이, Cloudflare/Oracle 테스트 |
| **G3** 보안 | 미인증/재생/토큰 탈취·CSRF/임의 명령 차단, 로그 마스킹 |
| **G4** 데이터 | SQLite WAL 포함 일관 백업·복원, 마이그레이션/롤백 |
| **G5** 컷오버 | 명시적 별도 사용자 승인, 백업 복구 및 롤백 경로 검증 |

**범위 제외:** 별도 상주 Supervisor, Agent 임의 원격 shell, 미인증 토큰 다운로드, 광역 공개 Tunnel, 승인 없는 자동 commit/push/fix 적용, 검증 전 운영 DB 파괴. 모든 완료 표시는 PR/커밋/CI와 실 Windows 테스트 증거를 분리해 기록한다.

## 설치 입력과 Oracle·저장소 목록 관리 (2026-11-02)

1. 설치 마법사의 관리자 계정·암호 입력과 기존 설정 보존. 암호는 명령행·로그에 전달하지 않는다. Oracle은 설치 항목에서 제외한다.
2. 연결 ID 기반 Oracle CRUD·활성 상태·revision·연결 테스트와 관리자 UI. 비밀번호는 Windows machine-DPAPI로 암호화해 ACL 보호 SQLite에 보관한다.
3. 기존 단일 설정의 일회성 이전과 연결별 테이블 허용 목록. MCP는 connection_id를 필수로 받으며 비활성 연결을 거부한다.
4. 승인 저장소의 목록 CRUD·일회성 이전 및 작업 큐의 승인 재검사·변경 시 대기 작업 취소.
5. 회귀·계약·보안 검증 및 문서 갱신. 설치파일 빌드는 사용자가 수행한다.

상태: 소스 구현 완료. 실제 검증 증거와 잔여 실환경 항목은 [검증](VERIFICATION.md)에 기록한다.

### 2026-11-02 트레이 종료 피드백

종료 차단·실패 이유를 지속적인 대화상자로 안내하도록 수정. 관련 mock 회귀 14개 통과. Native 빌드와 실제 Windows 종료 동작 검증은 별도이며 기존 출시 게이트 상태는 유지한다.

### 2026-11-02 서비스 등록 오류 처리

서비스 클래스 탐색과 CLI 종료 코드 전달을 수정하고 설치기가 필수 단계 실패를 검사하도록 변경. 서비스/트레이 회귀 18개 통과. 빌드 및 실제 SCM 설치·시작은 미검증으로 기존 Native 출시 게이트는 유지한다.

## 2026-11-03 연결·Native 후속 수정

연결 이름 선택과 안전한 오류 코드, 트레이 종료 진행창, 제거 로그/설치 소유 프로세스 정리, 설치 프로젝트 서버 승인 및 UIUX 전용 worker 패키징을 수정했다. 상태는 IN_PROGRESS이며 재빌드·설치·Windows E2E 및 Oracle 실접속 성공은 확인되지 않았다.

SCM에서 서버 서비스 STOPPED 확인 시 트레이 자동 종료를 추가했다. 우클릭 종료의 진행창 완료 처리와 UAC 호출 형식을 보완했으며, 테스트·빌드 중단 요청에 따라 코드 확인만 진행했다.

Repository에 실행 Agent/로컬 경로와 비동기 연결 확인을 추가하고 해당 Agent로 작업을 라우팅하도록 수정했다. 공개 스킬 원본은 설치 시 GitHub latest 정식 release의 커밋에서 다운로드하며, Python 런타임은 설치기에 포함한다. Graphify는 사용자별 설치 없이 Agent가 관리 런타임으로 로컬 AST 분석을 수행한다. 현재 코드는 미빌드·미설치·미검증이다.

Native 진입점은 LKH MCP 실행 시 서버 시작 후 트레이 표시로 통합했다. 서버 중지 시 트레이 자동 종료를 유지하고, 설치 실패/미완료 버전의 기동을 gate로 차단한다. 빌드마다 patch 버전을 자동 증가시키되 suite 전체에서는 한 번만 증가한다. 구현 상태이며 테스트·빌드·실설치는 사용자 요청으로 실행하지 않았다.
