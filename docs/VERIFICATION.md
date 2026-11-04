# CI 및 검증

## 2026-11-04 관리자 Agent 시작 거부 진단·복구

- 설치본 0.0.5의 설치 상태는 `ready`, 고정 Agent 작업은 Enabled/Ready였지만 프로세스가 없었다. 관리자 버튼의 기본 실행 경로와 같은 스케줄러 시작을 재현했으며 최근 결과는 `0x800710E0`였다. 등록 계정 SID와 로그인 계정 SID는 같고, 현재 세션은 3이었다. AC 전원 연결 및 절약 모드 OFF를 확인했으므로 관측된 실패를 배터리 조건 때문이라고 확정하지 않았다.
- 고정 작업을 `RunEx`의 명시적 사용자 세션으로 실행하자 실제 Agent 프로세스가 세션 3에서 유지됐고, 스케줄러 Running 및 로컬 `/admin/host/tray-state`의 `online`, `busy=false`를 확인했다. 서비스 재시작·작업 재등록·권한/전원 설정 변경·직접 실행 우회 없이 기존 예약 작업을 시작했다.
- `native_task_control`의 start/restart를 기본 `schtasks /run`에서 등록 계정 SID와 일치하는 단일 활성 WTS 세션을 찾는 COM `RunEx` 방식으로 수정했다. USE_SESSION_ID/USER_SID만 사용하며 AS_SELF/IGNORE_CONSTRAINTS는 사용하지 않는다. 세션 불명확·조회 실패·disabled·비대화형 계정은 차단하고, restart는 세션 확인 뒤 고정 작업만 중지·재실행한다. COM 참조를 apartment 종료 전에 해제한다.
- 실패 재현 테스트를 먼저 확인한 뒤 수정했다. `python -m unittest tests.test_native_agent_sessions tests.test_native_host tests.test_native_tray_shutdown -q` **37 PASS**. 새 세션 선택 함수를 실제 Windows에서 조회해 세션 3 일치를 확인했고, 실행 중 고정 작업에 동일 SID/세션 `RunEx`가 수락되는 것을 확인했다. 라이브 Python 점검 스크립트 종료 때 COM 참조 해제 경고가 있어 소스에서는 참조 해제 순서도 보완했다.
- 복구된 Agent Online과 소스 변경을 구분한다. 실행 중 서비스의 기존 바이너리를 교체하거나 새 installer를 빌드하지 않았다. LocalService 컨텍스트에서 새 코드가 적용된 관리자 버튼 start/stop/restart와 재부팅 후 실행은 새 빌드 배포 뒤 별도 검증해야 한다.

## 2026-11-04 Windows Agent 검증 준비 단계

- `src/verification_environment.py`와 Agent `verify` 흐름에 opt-in 로컬 준비 프로필을 추가했다. 저장소·정본 경로 바인딩을 Git 작업 전에 확인하고, 승인된 로컬 Gradle 배포본/의존성 캐시와 npm 스냅샷을 임시 worktree 내부에 복사한다. Gradle 버전·프론트엔드 잠금 파일 대사, 링크/reparse point 거부, 복사량/시간 제한, 전용 npm 설정·캐시를 적용한다.
- Gradle `help`와 Node 시작은 `codex sandbox --include-managed-config --permission-profile :workspace` 안에서 수행한다. 사전 실행 후 추적 파일과 HEAD가 유지돼야 기존 `workspace-write` Codex 검증을 시작한다. 준비/사전 실행 실패는 고정 원인 코드와 `environment_blocked`, 테스트 0건을 반환한다. 다운로드·전역 ACL/네트워크/서비스 변경은 수행하지 않는다. 설정 형식과 적용 범위는 [빌드·설정](BUILD_AND_CONFIGURATION.md)을 참조한다.
- 실제 실행: `python -m unittest tests.test_verification_environment tests.test_codex_bridge.WindowsAgentTests tests.test_codex_events tests.test_codex_presence.WindowsDiagnosticsTests -q` — **39개 중 38 PASS, 1 SKIP**. SKIP은 호스트의 실제 symlink 생성 권한 부재이며, Windows reparse 속성 거부는 별도 단위 테스트로 확인했다. 자산 복사·잠금 파일 대사·준비 실패 시 모델 실행 차단·격리 플래그 유지·프로필 바인딩·원시 출력 비노출·캐시 내 사용자 설정 혼입 거부를 검증했다. sandbox subprocess는 모의 실행이므로 실제 Windows Gradle 연결 성공의 증거가 아니다.
- `python -m compileall -q src/verification_environment.py windows_agent/agent.py tests/test_verification_environment.py` PASS. 기본 TEMP에서는 fixture 생성 권한 오류가 발생해 작업 공간의 `build/verification-tests-tmp`를 이 테스트 프로세스의 TEMP/TMP로 지정했다. 시스템 환경변수나 ACL은 변경하지 않았다.
- 확대 검사에서 기존 `BridgeTests` 6개는 `approved_repositories` 테이블이 없는 SQLite fixture 오류로 실패했다. 이 작업에서는 해당 큐 코드와 fixture를 변경하지 않았다. 기존 Presence 검사에서도 빈 프로젝트 목록 기대값 불일치와 오류를 관측했으며, 비동기 route 검사는 Python `socketpair` 초기화의 `accept`에서 멈춰 25초 제한으로 중단했다. 앞선 묶음 검사도 중단했으므로 전체 회귀 통과로 보고하지 않는다.
- 미검증: 새 Agent PyInstaller 빌드·실제 설치본 배포·승인 자산 등록·실제 샌드박스에서 Gradle/프론트엔드 전체 실행. 기존 `getsockopt` 차단 주체는 미확정이며 이 구현은 정책을 완화하지 않는다. 운영 서버·설치본·비공개 Agent 설정은 변경하지 않았다.

## 2026-11-04 Portal handshake timeout 복구

- 현재 Native 0.0.4 서버 직접 호출은 정상이나 Portal 호출은 `HandshakeTimeoutError`였다. Cloudflare의 기존 서버 `lkh-mcp`가 이전 주소 `http://192.0.1.22:8000/mcp`를 참조하는 것을 확인했다. 현재 주소 `http://192.0.57.169:8000/mcp`로 등록된 `lkh-mcp-2`는 Ready 상태였다.
- Cloudflare 편집 화면에서 기존 서버 URL은 읽기 전용이므로, 기존 Portal의 서버 대상을 `lkh-mcp-2`로 교체하고 저장했다. 기존 Portal URL, 접근 정책, Managed OAuth 및 Gateway 경유 설정을 유지했다. Portal 서버 선택 세션도 갱신했다.
- 실제 Portal 경유 검증: 지침 조회 1건, Oracle 연결 목록 2건, `itam-prod` 및 `itam-dev` 고정 DUAL 모두 `MCP_OK`(Oracle 11.2.0.2.0 / Thick), Codex 진단 enabled, Graphify 목록 정상 응답(스냅샷 0건).
- 관리자 화면에서 현재 Agent의 인증 heartbeat Online을 확인했다. Task Scheduler는 ready이고 Agent 프로세스가 별도로 실행 중이므로, 자동 시작 장애 해결이나 재부팅 후 자동 실행까지 입증한 결과는 아니다. 서버 코드 변경, 서비스 재시작, DB 변경은 수행하지 않았다.
- 다른 ChatGPT 연결 세션은 서버 선택 갱신이 필요할 수 있다. 변경된 도구 접두사는 `lkh-mcp-2`이다. 현재 IP는 Wi-Fi 주소이므로 향후 주소 변경 시 연결 대상 재점검이 필요하다.

## 2026-11-03 Portal 연결 장애 복구

- 공개 소스는 tempfile 하위에서 준비 후 rename되어 관리자/소유자 전용 ACL을 유지했다. Windows 합성 폴더에서 LocalService 상속 읽기 권한 0개를 재현하고, 최종 skills 폴더 ACL을 재상속하도록 설치 코드를 수정했다. 게시 전 경로·reparse point 검사를 수행하며 기존 설치의 manifest 선택 소스만 복구하는 옵션도 제공한다.
- 실제 설치 UIUX/Graphify 소스 ACL을 복구했다. Portal UIUX `ready=true`, v2.15.0과 설치 worker의 실제 검색 JSON 1건을 확인했다. Graphify 0.9.101은 별도 합성 Git 폴더에서 모델 호출 없이 3 nodes/3 edges를 생성했다.
- Oracle 19.32 DLL과 oracledb 3.4.2는 정상 조합이었다. PyInstaller의 `_internal` DLL 검색 디렉터리를 모사하면 `DPI-1072`, Client 폴더를 프로세스 PATH에 선행하면 초기화 성공을 재현했다. `oracle_db._driver`에 Windows 프로세스 PATH 보완을 추가하고 같은 재현 조건에서 19.32 초기화를 확인했다.
- 기존 설치본에는 LKH-MCP-Server의 서비스 전용 Environment/PATH를 보완하고 유휴 확인 후 해당 서비스만 재시작했다. Portal `itam-dev` 고정 DUAL 조회는 `MCP_OK`, Oracle 11.2.0.2.0, Thick 모드로 성공했다. 시스템 전체 PATH, Docker/Cloudflare 및 운영 DB는 변경하지 않았다.
- Graphify 작업 `f23663a905744f279b172d8b4c1486fd`는 Agent가 claim했으나 승인 저장소의 미커밋 변경 검사에서 실패했다. 원본 변경을 보존했으며 실제 프로젝트 스냅샷 동기화는 미완료다. Agent의 지속 실행·재부팅 E2E와 새 설치기 빌드는 검증하지 않았다.
- ACL/Oracle/UIUX 관련 unittest 11개 PASS. 전체 회귀·새 설치기 빌드는 실행하지 않았다. 이 절의 실환경 증거가 과거의 해당 장애 미확인 기록을 보완하며 전체 Native 출시 게이트 통과를 뜻하지 않는다.

이 문서는 자동 검증 방법, 이력 증거와 미완료 실환경 게이트의 정본이다. 과거 CI 결과는 해당 커밋의 결과이며 현재 HEAD나 운영 환경의 성공을 보장하지 않는다.

## 로컬 및 CI 실행

```powershell
python -m compileall -q src windows_agent tests
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -t . -p "test_*.py" -v
Push-Location frontend
npm ci
npm run build
Pop-Location
```

`.github/workflows/ci.yaml`은 Python과 프런트엔드를 검증한다. `.github/workflows/windows-native.yaml`은 Windows runner에서 Native 테스트, unsigned 번들 및 설치기 컴파일, 격리 loopback, DPAPI, SCM, 고정 작업 등록과 SQLite 백업을 확인한다. 정확한 트리거와 단계는 워크플로를 따른다. 실제 PC 설치나 운영 전환은 포함하지 않는다.

## 확인된 과거 증거

- 2026-10-30: [Actions 41037611656](https://github.com/gyangho/LKH_MCP/actions/runs/41037611656) Python·프런트엔드·게이트웨이 PASS, [Actions 41037387950](https://github.com/gyangho/LKH_MCP/actions/runs/41037387950) Windows Native Suite PASS로 기록됨.
- `9742a8c5`: [Actions 41032060220](https://github.com/gyangho/LKH_MCP/actions/runs/41032060220) Windows Native Suite PASS로 기록됨. SCM, DPAPI, 고정 작업, Agent 설정, Native HTTP, SQLite 및 unsigned Inno 패키징을 포함한다.
- 초기 I1 [Actions 41022366248](https://github.com/gyangho/LKH_MCP/actions/runs/41022366248): 당시 Windows 구성 테스트, PyInstaller 자산 검사 및 격리 HTTP smoke PASS. 후속 변경을 검증하는 결과는 아니다.
- 2026-10-30 read-only Portal 검사: 서버 enabled, UIUX 일반 실행 `ready=true`, Graphify 프로젝트 빈 목록. Oracle DUAL은 오류 코드 없는 실행 오류로 **미확인**. 대상 Windows, Oracle 또는 frozen 기능의 성공 증거가 아니다.
- 과거 실제 Agent Verify 두 차례는 각각 임시 worktree ACL 정리, MXC `SystemDrive` 문제로 실패했다. 이후 수정이 있어도 실제 Verify 최종 PASS는 확인되지 않았다.

## Phase 구현과 남은 검증

| Phase | New implementation | Remaining acceptance |
| --- | --- | --- |
| 0 | Existing Agent heartbeat, queue, SHA and sandbox protections | Actual Windows verify/graphify E2E, login and MXC pending |
| 1 | Agent `codex exec --json` streaming, lease-checked `codex_task_events` in SQLite, allowlisted metadata and replay-safe cursor | Real Codex CLI JSONL compatibility and network loss/long-run E2E |
| 2 | `/admin/api/codex/events/{task_id}` and 2-second browser timeline; incremental seq cursor, per-task expansion | UI user acceptance, real job event trace |
| 3 | bounded task metadata and Windows temp worktree cleanup error handling; existing lease/timeout safeguards maintained | Windows ACL/cleanup failure, retry/offline, source checkout no-change E2E |
| 4 | `instruction_entries`, immutable `instruction_versions`, `instruction_audit`, optimistic revision + draft state | Schema migration on a staging copy of existing SQLite |
| 5 | `instructions_list`/`instructions_get`/`instructions_resolve` (read-only, published-only); tool > agent > project > global | Confirm intended scope access policy and review cross-project visibility |
| 6 | protected `/admin/api/instructions` CRUD/version/history/publish/rollback + React editor | Formal publication workflow approval, UX E2E |
| 7 | `operation_events` metadata-only SQLite logs with per-category cursor and 30d/50k retention + Admin log UI | Privacy review, operational load/retention test |
| 8 | 60-second buckets of request/error/avg latency, current CPU/RSS/threads + React view | Load and long-term metrics accuracy, host resource permissions |
| 9 | `.agents/skills/lkh-development/SKILL.md`, regression tests and deployment gate checklist | Real installer, Oracle/Graphify/Codex/Cloudflare end-to-end tests, release authorization |


## Native 단계별 검증

| Stage | Files / concrete implementation | Remaining acceptance |
|---|---|---|
| I0 | SQLite WAL, Oracle Thick, Cloudflare/WARP/portproxy, Agent and UIUX inventory | Host/network/Oracle evidence; I0 not fully VERIFIED |
| I1 | `native_runtime.py`, `native_server.py`, `native_gateway.py`; 기본 127.0.0.1:8000 MCP-only, :8001 Admin-only (병행 staging은 18080/18081 명시 오버라이드), route guards; PyInstaller onedir bundle | Windows CLI smoke and 404 route checks; Oracle 11g, UIUX frozen parity and real host still pending |
| I2 | `native_service.py`: distinct SCM host process, child server lifecycle, service stop signal. Installed as `LKH-MCP-Server` under LocalService by Installer | Service install/start/reboot/logoff/recovery/ACL under actual Windows account |
| I3 | `native_task_control.py`, `native_host_routes.py`, `scripts/install-agent-task.ps1`; fixed task only, authenticated CSRF API, busy guard | Real LocalService task SDDL, Windows Agent repo config, interactive login, restart/stop E2E |
| I4 | `native_tray.py`, `scripts/generate_icon.py`: same approved Pixel Pig pixels recolored green/pink/gray, separate tray, start/stop via fixed task | Pixel legibility at 16px, notification UI, tray autostart, offline/unknown behavior on host |
| I5 | `native_enrollment.py`, `native_enrollment_routes.py`, Agent token refresh: installer provisions machine-DPAPI device credential + SHA verifier, short-lived session API, admin-only rotate | Win11 DPAPI/ACL cross-account proof, rotation failure atomicity, binding to expected Agent ID, authenticated challenge-response upgrade and threat review |
| I6 | `installer/LKH-MCP.iss`, `scripts/build-native-suite.ps1`, Windows native dependency list, preflight + fixed task registration | Inno compilation, admin credential onboarding wizard, clean VM install/upgrade/uninstall, code signing, SBOM |
| I7 | `native_migration.py`: read-only SQLite inspect + backup API staging copy, integrity/row counts, no overwrites; dry-run first | Actual backup restore, Cloudflare/port cutover & rollback in maintenance window with **separate user approval** |


## 릴리스 및 실환경 게이트

- 대상 Windows: 설치·업데이트·세 가지 제거 모드와 재설치, UAC 취소, SCM 계정/ACL·재부팅/로그오프, Agent 스케줄러 및 트레이 상태를 격리 VM에서 확인. 기존 Inno 제거 이력 호환성과 부분 실패 롤백도 포함.
- 보안: Native DPAPI 계정 간 ACL·회전 실패·재생 위험, 관리자 Origin/Host/CSRF, Agent lease, MCP scope 권한과 독립 승인자 모델을 검토한다. 현재 DPAPI 공유 secret은 CNG 비내보내기 키와 nonce challenge-response가 아니다.
- 실제 Codex CLI JSONL, MXC, 작업 lease/재시도, worktree ACL 정리 및 원본 무변경, Graphify와 Oracle 11g Thick 동작을 대상 환경에서 검증한다. frozen UIUX는 외부 `UIUX_PYTHON_EXECUTABLE`이 필요하다.
- SQLite WAL 일관 백업과 복제본 복원, 설정·감사·작업·지침·이벤트 및 Graphify 비교; 동시 쓰기 방지와 롤백을 검증한다.
- MCP/Admin 포트 분리, Cloudflare/WARP 정책 및 backend 우회 차단을 확인한다. 서명, 체크섬, SBOM 및 배포 검토가 남아 있다.
- 운영 전환은 별도 승인 후 수행한다. CI PASS만으로 Windows E2E 또는 RELEASED로 표시하지 않는다.

P0–P2 관련 회귀는 `tests/test_p0_p2_hardening.py`에 있으며 독립 RBAC, scope ACL, 내구성 있는 이벤트 outbox와 실행 중 lease 복구는 잔여 과제다. 대상 PC의 실제 트레이 종료·제거·재설치 검증은 확인되지 않았다.

## 2026-11-02 설치 입력·Oracle 연결·승인 저장소 로컬 검증

- Python 전체 회귀 **163개 PASS** (프로젝트 가상환경, 격리 임시 SQLite, 승인된 로컬 실행). 기존 제한 실행 환경에서는 비동기 루프가 멈췄으나 승인된 실행에서 완료했다.
- Oracle: 실제 관리자 세션/CSRF로 HTTP CRUD·빈 암호 유지·revision 충돌·비활성 처리, 암호 비노출, 연결별 허용 목록, 일회성 이전과 삭제 후 재생성 방지, 드라이버 선택·오류 마스킹. Oracle 드라이버 I/O는 mock 검증이며 실제 DB 접속 증거가 아니다.
- Windows DPAPI의 실제 합성 암호 roundtrip PASS. LocalService와 다른 사용자 간 ACL·복호화 및 다른 PC 복원은 별도 검증이 필요하다.
- 설치 관리자: 실제 도우미 프로세스의 stdin 파이프·유니코드 암호 입력, 추가 필드 거부·해시 저장·동시 생성 시 기존 설정 보존 테스트. 설치 마법사 및 Inno Setup 컴파일/실행은 미검증.
- 승인 저장소: CRUD·중복/형식/개수·revision, 초기 문자열 이전, 승인 변경 시 대기 작업 취소, 실행 중 변경 차단, enqueue/claim/retry의 현재 승인 재검사, 관리자 HTTP 세션/CSRF 테스트.
- TypeScript `tsc --noEmit` PASS, Python compileall 및 공백 오류 검사 PASS. UI 시각·실제 설치·Oracle Thin/Thick 실DB 연결 및 배포는 미검증. 이번 구현에서는 설치파일·프런트엔드 번들을 빌드하지 않았다.

## 2026-11-02 Inno Setup 6.7.4 컴파일 수정

`JsonString`의 미지원 `IntToHex` 호출로 실패한 컴파일을 재현한 뒤 `Format('%.4x', [Ord(...)])`로 교체했다. `ISCC.exe /O- installer/LKH-MCP.iss`로 전체 스크립트 컴파일 PASS. 출력 파일 생성은 비활성화했으며 설치·마법사 실행은 검증하지 않았다. 기존 Windows CI의 Inno 컴파일 단계도 이 오류를 검사한다.

## 2026-11-02 트레이 종료 안내 수정

- 서버 연결/작업 상태/Agent 제어/서비스 실행 실패를 구분하고 종료 결과를 Windows 대화상자로 표시한다. 확인 문구는 작업 실행·상태 미확인 시 종료 차단 정책에 맞췄다.
- `PYTHONPATH=src python -m unittest tests.test_native_tray_shutdown -v`: 14개 PASS. 연결 거부 시 대화상자와 종료 미실행, 작업 상태별 안내, 오류 비노출, 실행 요청과 중지 완료 구분을 mock으로 검증했다.
- 빌드·설치·실제 Windows 대화상자/UAC/서비스 중지는 실행하지 않았다. 서비스 등록 실행 파일의 오류는 이번 수정 범위 밖이다.

## 2026-11-02 서비스 등록 실패 수정

- 설치된 EXE에서 관측된 함수 로컬 서비스 클래스 탐색 실패를 수정: `LkhMcpService`를 모듈 수준으로 이동하고 pywin32 CLI 결과를 프로세스 종료 코드로 전달한다.
- 설치기의 필수 등록 단계를 종료 코드 검사로 전환하고 서비스 시작은 `--wait 30`으로 실행 상태를 기다린다. 실패 단계와 종료 코드를 표시한다.
- 서비스/트레이 회귀 18개 PASS. 실제 pywin32 클래스 탐색 및 install 명령 파싱을 실행하고 SCM I/O만 mock으로 대체하여 등록 인자와 실패 코드 반환을 검증했다. 수정 전 새 서비스 회귀 3개는 클래스/모듈 속성 부재로 실패했다.
- 추가 Native runtime 테스트는 sandbox 임시 폴더 접근·삭제 권한 오류로 실패했다. 빌드·Inno 컴파일·설치·실제 SCM 등록/시작은 실행하지 않았다.

## 2026-11-02 원격 브랜치 통합

- `fix/native-tray-background-shutdown`의 COM 초기화·실제 중지 확인·제거 옵션 UI를 종료 안내 및 서비스 등록 수정과 통합. main에서 통합 삭제한 구 문서는 복원하지 않았다.
- 통합 후 서비스/트레이/제거 계약 테스트 25개 및 host 테스트 8개 PASS. 성공 시 SCM STOPPED 확인 후 트레이를 종료하며 실패 시 원인별 전면 대화상자를 유지한다. 이전 종료 요청 성공 안내는 이 동작으로 대체된다. 빌드·설치·실제 UAC/SCM 및 제거 UI는 미검증.

## 2026-11-03 후속 수정 (미배포)

- Oracle 이름→ID 선택, 미선택/중복 차단, 저장 ID 테스트 POST 명시 및 ORA/DPY/DPI 코드만 노출.
- 트레이 단계별 진행창, 제거 시 설치 소유 프로세스 정리와 보존 경로/제거 로그 안내.
- 설치 시 선택 프로젝트의 서버 승인/Agent 설정 동기화, heartbeat 고정 원인 코드, Codex 등록 오류 및 진단 도구. UIUX 전용 frozen worker 빌드/설치 경로 추가.
- 사용자의 테스트·빌드 중단 요청 이후 실행하지 않았다. 요청 전 23개 트레이/제거/오류코드 테스트와 frontend build는 통과했으나 이후 추가 수정은 검증되지 않았다. HTTP 포함 테스트와 설치기 컴파일은 중단되어 성공으로 간주하지 않는다.
- Oracle 재접속은 여전히 일반 연결/조회 오류였으며 실제 Oracle 원인, 현장 heartbeat 400 원인, SCM/UAC/제거 E2E는 미확정이다. 새 원인 코드는 재빌드/재설치 후 확인 필요.

### 트레이의 외부 서버 중지 감지

- HTTP 상태 갱신은 아이콘만 바꾸고 종료하지 않아 외부에서 서비스를 중지해도 트레이가 남았다. SCM에서 LKH-MCP-Server의 STOPPED를 확인하면 다음 3초 폴링에서 트레이도 종료하도록 수정했다. HTTP 실패·Agent 오프라인·SCM 조회 실패는 중지로 판단하지 않는다.
- 우클릭 종료 중에는 자동 감지가 진행창보다 먼저 트레이를 종료하지 않도록 잠금을 공유한다. 진행창 작업의 완료 이벤트를 finally에서 보내 예외 시 무한 대기를 방지했고, ShellExecuteW의 Windows 포인터 크기 반환형/인수형을 명시했다.
- 코드 경로만 확인했다. 사용자 요청에 따라 테스트·빌드·설치본 실행 확인을 하지 않았다. 실제 설치본에서 기존 종료 무반응을 유발한 원인은 확정하지 않았다.

### Repository 실행 바인딩 및 공개 스킬 설치 방식 변경

Repository DB/관리자 API/UI에 agent_id/local_path와 revision 기반 연결 확인을 추가했다. Agent는 인증 API로 설정을 받고 지정된 Agent만 작업을 claim한다. 연결 확인은 별도 lease와 180초 만료를 가지며 폴더/Git root/origin/GitHub 접근의 고정 결과 코드만 반환한다.

공개 스킬 소스는 installer에 포함하지 않고 설치 시 최신 정식 GitHub release를 커밋 SHA로 고정해 다운로드하도록 변경했다. Python 런타임은 installer에 포함하고 Graphify 의존성 wheel은 설치 시 준비한다. Graphify의 사용자별 스킬/CLI 존재 확인과 Codex 스킬 호출을 관리 런타임의 AST-only 분석으로 대체했으며, 기존 graph.json을 새 결과로 게시하는 경로를 차단했다. 이전 UIUX 전용 frozen worker 패키징은 공용 Python 런타임 방식으로 대체됐다.

사용자 요청에 따라 이번 변경에 대해 테스트·빌드·실설치·공개 스킬 다운로드·저장소 연결 확인을 실행하지 않았다. 코드와 API 계약만 수정했다. 기존 테스트 중 변경된 스키마/패키징/Graphify 실행 방식을 전제한 항목의 후속 정비와 Windows 검증이 남아 있다. 최신 release/다운로드 크기/wheel 호환성과 실제 설치 동작은 미확인이다.

### 공개 스킬 설치 오류 및 트레이 진행 표시 후속 수정

- 공개 GitHub 메타데이터만 읽어 원인을 확인했다. UIUX v2.15.0 release 응답은 5,838 bytes였고 `/commits/v2.15.0` 응답은 1,048,576-byte 제한을 초과했다. 설치 코드가 커밋 diff까지 받아 ValueError를 내면서도 단계를 latest-release로 기록한 문제였다. 커밋 diff 조회를 tag ref/annotated tag의 SHA 해석으로 대체하고 단계/고정 오류 코드를 분리했다.
- 트레이 확인창을 메뉴 메시지 루프에서 분리했다. Tcl/Tk 진행창을 Windows 기본 창/ProgressBar로 대체하고 현재 종료 단계와 진행 막대를 표시한다. 완료 전 UI 실패 시 중복 종료 요청을 보내지 않으며, 초기화 실패 시에도 종료 시도와 오류 안내를 제공한다.
- 사용자별 `%LOCALAPPDATA%/LKH-MCP/logs/tray.log`에 시작 revision, 메뉴 선택, 확인 결과, 각 종료 단계, 안전한 오류 유형을 회전 로그로 남긴다. 현재 설치본에서 무반응을 일으킨 실제 단계는 아직 확인하지 못했다.
- 테스트·빌드·설치기 실행·트레이/서비스 종료는 실행하지 않았다. GitHub 응답 조회는 원인 조사를 위한 읽기 전용 조회이며 수정된 설치 코드의 실행 검증은 아니다.

### Python 런타임 반복 빌드 수정

기존 `dist/skills-python` 존재만으로 RuntimeError를 내는 경로를 제거했다. 저장소의 고정 dist 경로 아래에서 새 런타임 준비 → 기존 출력 백업 → 교체 순서로 수행하며, 교체 실패 시 기존 출력을 복구한다. 이동/재귀 삭제 전에 경로가 dist의 지정 하위 출력인지 확인하고 링크·junction을 거부한다. 새 준비 실패 시 기존 출력은 유지한다. 테스트·빌드는 사용자 요청에 따라 실행하지 않았다.

### UIUX archive-files 실패 수정

공식 UIUX v2.15.0의 공개 Git tree를 읽어 `gallery/data/styles.csv`가 mode 120000 심볼릭 링크임을 확인했다. 필요한 `src/ui-ux-pro-max/scripts/search.py`와 LICENSE는 존재했다. 기존 설치 코드는 설치 대상 필터보다 먼저 압축 전체의 심볼릭 링크를 거부해, 사용하지 않는 gallery 링크 때문에 중단됐다. 설치 대상 선별 후 안전성 검사를 수행하도록 순서를 수정했으며 선택된 소스 내부의 링크·경로 이탈 차단은 유지한다. 압축 제한·선택 항목 안전성·필수 소스·라이선스에 고정 오류 코드를 부여하고 필수 파일 확인 단계를 분리했다. 테스트·빌드·압축 해제·실설치는 실행하지 않았다.

### 실행 진입점·실패한 설치의 시작 차단·빌드 버전

- 시작 메뉴 LKH MCP를 서버 시작 + 트레이 진입점으로 변경했다. 서버 중지 시 트레이 자동 종료를 유지하고 SCM 1060을 missing으로 구분했다. 시작/종료 모두 단계 표시를 제공하고 세션별 중복 트레이를 mutex로 제한한다.
- 설치 시작 전 기존 소유 프로세스/작업을 중지하고 서비스를 비활성화하며, 설치 성공 후에만 자동 시작과 작업을 활성화한다. 버전별 installation.json gate를 Service/Server/Tray/Agent와 native gateway에 추가했다. 서비스와 healthz 앱/버전/PID/부모 PID까지 확인한 뒤 ready로 전환하며 실패 시 시작 차단과 중지 정리를 수행한다. 기존 활성 작업 또는 소유권 불명 상태에서는 업그레이드 시작을 차단한다.
- 빌드 진입점에서 버전을 한 번 증가시키는 스크립트, 공통 버전 리소스/ISPP include 및 빌드 전체 잠금을 추가했다. 버전 증가 스크립트를 실행하지 않았으므로 이번 수정 자체로 버전은 증가시키지 않았다.
- 사용자 요청에 따라 테스트·빌드·설치·서비스 조작을 실행하지 않았다. 설치기/PS/Win32/실행 gate의 실제 동작과 기존 테스트 계약 갱신은 미검증이다.

### Service activation preparation 오류 후속 수정

실제 설치 상태 JSON은 installing/version 0.0.2였고 서비스 registry ImagePath는 해당 설치의 서비스 EXE와 일치했으며 StartType은 3(수동)이었다. 현재 오류창은 하위 PowerShell 오류를 숨겨 실제 실패 작업은 확정하지 못했다. 상태 파일 File.Replace의 null 백업 인수를 명시적인 고유 백업 경로로 변경하고 이미 수동 시작인 서비스의 중복 설정을 생략했다. 각 phase에서 작업 단계·안전한 오류 유형/식별자·HRESULT·해당 시 Windows 오류 코드를 logs/installer-<phase>.json에 남기고, 실패 정리가 원래 오류를 덮어쓰지 않도록 구분했다. 설치 상태/registry 읽기만 수행했으며 테스트·빌드·설치·서비스 조작은 하지 않았다.
## 2026-11-04 서버 중앙형 개발 스킬 (Matt Pocock)

- 개발 브랜치 `codex/feature/mcp-central-skills-20261104`, upstream `mattpocock/skills@4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`. 클라이언트별 플러그인 설치 없이 서버에만 pinned 자료를 둔다.
- [Python CI](https://github.com/gyangho/LKH_MCP/actions/runs/41811191421) 성공: Python compileall, 단위·회귀 테스트 **187개 PASS**, 프런트엔드 빌드 성공. 통합 테스트에는 등록/경로 제한/우선 정책/큐 자동 주입/미설치 시 큐 보류/구버전 Agent 거부/Windows prompt 전달이 포함된다.
- [Windows Native CI](https://github.com/gyangho/LKH_MCP/actions/runs/41811191728) 성공: pinned upstream 서버 설치, PowerShell 구문 검사, Native 테스트 **72개 PASS**, unsigned 실행 파일 번들/설치기 빌드, loopback 포트 분리·DPAPI·SCM·작업 스케줄러·복구 테스트 PASS. 실제 Native 서버로 MCP 조회 스모크 실행: `CENTRAL_MCP_SKILLS_SMOKE_OK 27 4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`.
- CI runner의 격리된 Windows 가상 머신 기준이며 운영 MCP 서버, Portal 실제 연결, 실제 사용자 Codex CLI의 수락 테스트나 배포 성공을 증명하지 않는다. 서버/Agent를 운영 전환하거나 생산 DB/라우팅을 변경하지 않았다.
- 실제 단계별 검증과 권한 제약은 [중앙 개발 스킬](ENGINEERING_SKILLS.md)의 수락 테스트 절차를 따를 것.
