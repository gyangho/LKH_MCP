# CI 및 검증

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
