# Windows Native Installer 상세 설계

**상태:** TO-BE · 아직 통합 Installer·SCM 서비스는 없음. 목표 Windows 11 Pro x64.

## 1. 단일 설치 파일·분리된 실행 역할

- 사용자 산출물: 서명·해시 검증된 `LKH-MCP-Setup.exe` 한 개. **Inno Setup** 기반 설치 마법사, 내부 PyInstaller **onedir** 서버/Tray/Agent 실행파일.
- 설치 바이너리: `%ProgramFiles%\LKH MCP\`; 상태/설정/로그/백업: `%ProgramData%\LKH-MCP\{data,config,logs,backups}`. 민감 설정에 서비스 SID/사용자별 최소 ACL.
- 기존 `scripts/build-windows.ps1`/단일 서버+트레이는 **시제품 유지** 후 I2/I4에서 대체. 버전 고정·재현 빌드, SBOM·라이선스, 릴리스 서명 및 SHA-256 제공.

## 2. 설치 마법사

1. 기존 설치/프로세스/버전/중복 포트/Oracle Thick runtime/로컬 Python·Git·Codex·Windows 빌드 진단.
2. 서비스 계정(비관리자), Codex 로그인 사용자 계정, 설치 경로, 8000/8001 주소, WARP·관리자 포트 사전 확인.
3. Naru 병행 모드 또는 승인된 cutover 모드 선택. 미승인 상황에서 Docker·Cloudflare 설정 삭제/변경 금지.
4. 설치·업데이트·복구·제거·재부팅 뒤 시작 테스트. 사용자 승인에 한해서 관리자 권한(UAC) 획득, 필요 방화벽 변경은 변경 전 상세 표시.
5. 최초 등록 시 지정 계정/호스트 신뢰 관계 생성·관리자 확인, 비밀은 DPAPI/CNG 등 Windows 보호 저장소. 관리자에게 매번 토큰 복사 요구 금지.

## 3. 서비스/Agent/트레이

| 프로그램 | 실행 주체/트리거 | 종료와 장애 |
|---|---|---|
| `LKH-MCP-Server` SCM | PC 부팅 시 자동, 제한된 서비스 계정 | 헬스·복구 정책, 서비스 stop시 작업 drain/DB 정합 |
| `LKH-Codex-Agent` Task Scheduler | Codex CLI 로그인된 저권한 사용자, UI/관리에서 **등록된 작업만** start/stop/restart | 중복 실행 금지, Busy 작업의 중단 별도 관리자 확인 |
| `LKH-MCP-Tray` | 사용자 로그인 시 시작, UI 세션 | UI 종료 시 서비스/Agent 계속 실행 |

트레이는 Session 0 서비스 UI에 포함하지 않고 IPC(Windows Named Pipe 등 인증+ACL)를 통해 상태를 조회·제어한다. 트레이에서 직접 원격 shell 명령이나 임의 경로를 받지 않는다.

## 4. Pixel Pig 상태/UX 명세

승인 원본: `branding/pig-terminal.png` (픽셀·CLI 스타일). 임의 신규 그림 대신 같은 원본 픽셀의 컬러/흑백/회색 상태 이미지 파생. Windows ICO 16/20/24/32/48/64/128/256px, 16px 실기 가독성.

| 색 | 실제 의미 |
|---|---|
| **원본 컬러** | 서버 정상 + Agent의 최근 유효 heartbeat(기본 45초) 및 스케줄러 상태 정상 |
| **흑백** | 서버 정상·Agent 작업이 실행되지 않거나 heartbeat 만료 |
| **회색** | MCP 서버 미응답·인증 실패·조회 불가(종료로 추측하지 않음) |

Tooltip·메뉴에 색과 별개로 상태(Online/Offline/Unknown/Busy/Error), 마지막 heartbeat, 작업수 표시. 메뉴: 대시보드 열기, Agent 시작/중지/재시작, 로그, 버전·진단, 트레이 종료. 오류/사용자 권한 없는 경우 조작 버튼 비활성화하고 설명 표시.

## 5. 계획 API/Windows 제어

- `GET /admin/api/host/services`: Service/TaskScheduler/Agent heartbeat/오류 요약.
- `POST /admin/api/host/agent/{start,stop,restart}`: 고정 작업 ID의 상태 변환(관리자 세션·CSRF·확인·감사·과도한 재시도 제한). **임의 command/스크립트/바이너리 경로를 입력 받지 않음**.
- `Start-ScheduledTask` 요청 성공과 Agent Online을 명확히 구분; 태스크 시작 후 heartbeat 관찰까지 UI에 Starting 표시.
- 로컬 트레이: ACL 보호된 IPC + OS 사용자 검증, 동일 권한·감사 정책; 브라우저/트레이에서 서비스 계정 권한을 무제한 승격하지 않는다.
- Server/UI가 실행 중에도 Agent가 종료된 상태에서 task start 가능. 별도 Supervisor 상주 불필요.

## 6. 릴리스/제거 계약

- Windows runner/실기: 부팅·로그오프·계정 변경·재설치·crash/recovery·서명/방화벽/ACL·다중 사용자·토큰 갱신·Agent Busy·아이콘 상태 회귀 테스트.
- 업데이트: 변경 전 백업→서비스 drain→바이너리 교체→스키마 호환 검증→헬스→실패 시 롤백.
- 제거: SC 서비스·등록 Task·트레이/바이너리 삭제, ProgramData DB/사용자 설정/감사 로그는 **기본 보존**; 완전 삭제는 별도 명시 선택. Cloudflare/Oracle 시스템 자동 삭제하지 않음.
- v1 Installer 출시 전에 Docker 동일 MCP/Admin 기능/보안 격리/Oracle/SQLite/Cloudflare를 독립 E2E로 검증하고 관리자 운영 cutover 승인 수령.

## I1 Preview implementation (refac; incomplete, no production deployment)

Current source: `src/native_server.py` + `src/native_runtime.py`; build: `scripts/build-native-server.ps1`. This is a **headless preview**, not `LKH-MCP-Server` SCM service, Installer or deployed reverse proxy.

```powershell
# Windows development machine, clean repo with initialized vendor submodule
git submodule update --init --recursive
.\scripts\build-native-server.ps1
# A bundle exists at dist\LKH-MCP-Server\LKH-MCP-Server.exe
.\dist\LKH-MCP-Server\LKH-MCP-Server.exe --check

# Use a scratch state folder, not the Docker named volume:
$env:LKH_NATIVE_STATE_DIR = Join-Path $env:TEMP "lkh-mcp-native-staging"
.\dist\LKH-MCP-Server\LKH-MCP-Server.exe
```

Default bind is `127.0.0.1:8000` for MCP and `127.0.0.1:8001` for Admin after the old Naru listeners are stopped. Do not set `MCP_HOST=0.0.0.0`; the runtime rejects non-loopback. Server state is separate in `%ProgramData%\LKH-MCP\data` unless `LKH_NATIVE_STATE_DIR` specifies an absolute staging directory. `MCP_DB_PATH` and `MCP_BOOTSTRAP_FILE` can be explicit absolute paths, but avoid pointing at operational data. If no bootstrap is configured, admin remains unconfigured; the preview **does not create or retrieve administrator secrets**.

The check command validates packaged React `web/dist/index.html` and vendor UI/UX script, **not** actual authentication/Oracle/Cloudflare or Windows service startup. Existing `src/uiux_tools.py` requires an externally installed Python interpreter via `UIUX_PYTHON_EXECUTABLE` when frozen; parity remains blocked until a future audited solution. Oracle 11g needs compatible local Instant Client/Thick mode and real tests. Keep Docker gateway running.

Windows CI builds this unsigned preview and smoke-tests asset inclusion/loopback HTTP. **Do not distribute this as an approved Installer**; I1 completion still needs cross-port ACL/HTTP route isolation and Oracle/UIUX parity verification.

## I2–I7 staged components (refac, Windows 실운영 미검증)

- 서비스 `src/native_service.py` → 독립 `LKH-MCP-Server.exe` 실행·종료·오류 감지, SCM 서비스 `LKH-MCP-Server` 준비. 로그인된 트레이 세션과 분리.
- Agent Task `LKH-Codex-Agent` → `scripts/install-agent-task.ps1`로 사용자 로그인 계정 등록, 서비스의 허용 작업 제어만 수행.
- Pig Tray `src/native_tray.py` → 승인된 `branding/pig-terminal.png`의 픽셀 구조 보존, 초록/핑크/회색 배색만 파생. 서버·Agent와 별도 EXE.
- 자동 인증 → Installer 장치용 DPAPI 암호화 키, 서버 SQLite SHA 검증, 15분 scoped bearer, Windows Agent 자동 수령·주기적 갱신. **비내보내기 CNG 키/challenge-response와 실제 서비스 계정 ACL E2E는 향후 보안 게이트**.
- Installer `installer/LKH-MCP.iss` + `scripts/build-native-suite.ps1`: 명시적 UAC, 서비스/스케줄러/트레이 등록, 관리자 초기 비밀번호는 별도 숨김 콘솔 입력으로 salted hash만 생성. **현재 unsigned preview**, 제품 서명·업그레이드 실패 롤백 검증 없음.
- I7 `src/native_migration.py`: 기존 SQLite를 읽기 전용으로 열어 새로운 staging DB에 Backup API 복사, integrity/테이블 건수 비교, 기존 파일 덮어쓰기 거부. Docker 원본 DB 수출과 라우팅 전환은 수행하지 않음.

현재 모든 설치·제거 명령은 실제 Windows 서비스/파일/ACL을 변경한다. **CI의 Installer compile과 실제 설치는 다르며, 사용자 승인 없이 운영 PC에 설치하지 않는다.**


## Native same-PC Naru replacement / Pixel Pig UI update (2026-11-02)

- Native loopback defaults: MCP `127.0.0.1:8000/mcp`, Admin `127.0.0.1:8001/admin`. They **reuse the existing Cloudflare destination ports only after Naru/old Docker port listeners are stopped**. Both route guards remain separate; never bind the combined app on `0.0.0.0`.
- Existing Naru container/port proxy may still own the sockets; Native must fail the bind in that case. This software does **not** stop Naru, edit Cloudflare, remove data, or change Windows firewall rules.
- Installer initializes `ADMIN_PUBLIC_ORIGIN=http://127.0.0.1:8001` for **local** administration. Remote administration under a Cloudflare hostname requires a separately reviewed origin/host/cookie/Access policy; MCP 8000 alone may be routed through Cloudflare. Do not expose 8001 without that review.
- Pixel Pig icon: `branding/pig-terminal.png` stays full color when the server responds and Agent has a fresh authenticated heartbeat. Server online + Agent offline → true monochrome; server unavailable → dim gray. Color no longer indicates Agent busy state.
- Web admin: original Pig artwork, shared rectangular pixel-theme fields and text area, fixed form/layout alignment. Operations logs/metrics/alerts have **no automatic polling** while being reviewed; explicit manual refresh buttons and fixed-height scroll table. Global status refresh is suspended while editing instructions or reading operations.
- Shutdown UI: session + Origin/Host/CSRF-protected Native-only `POST /admin/api/host/shutdown/{server,both}` with exact confirmation body, active-job refusal, 5-second rate limit. `both` stops the fixed Agent task first; the Native server returns acknowledgement, then drains gateways and exits. Windows SCM supervisor treats zero-exit as a deliberate stop. This does not shut down Naru or unrelated services.
- New staging CI tests verify port isolation, shutdown conditions, and Pig palette. Signed Installer, real Cloudflare/WARP routing and corporate Windows Agent/SCM shutdown remain host-specific acceptance tests.

### Native Tray shutdown menu (post-cutover staging)

- Right-click offers **MCP 서버 종료 (UAC 승인)** and **서버 + Agent 모두 종료 (UAC 승인)** in addition to existing Agent and tray-only controls.
- Native tray has no browser administrator cookie: it does **not** call the browser-only shutdown HTTP API or add a new unauthenticated endpoint. Instead it launches the installer-owned, fixed `LKH-MCP-Service.exe stop` action through Windows UAC/SCM, with confirmation and no arbitrary executable/argument input.
- The loopback Native server must confirm Agent state and `busy=false`. Unavailable state, missing busy metadata, or active Codex task blocks shutdown; combined stop requires a known fixed Task Scheduler state and stops that Agent first. If UAC is cancelled after Agent stop, the Agent may remain stopped; check both states and restart explicitly.
- UAC launch success does **not** prove the SCM service finished stopping. Inspect Windows Services and Agent Task Scheduler on the actual machine. Tray-only exit still leaves both running. Naru/Docker is not affected.
- Existing `%ProgramData%\\LKH-MCP\\config\\bootstrap.json` is deliberately preserved. For local login CSRF errors, check only `ADMIN_PUBLIC_ORIGIN` against the browser's exact scheme/host/port (`http://127.0.0.1:8001`). Do not disable Origin/CSRF checks or expose credential hashes.

## Native Uninstaller: implemented staging modes

| Mode | Installed binaries, owned SCM and tasks | ProgramData config / origin / DPAPI | SQLite, WAL, logs, backups |
|---|---|---|---|
| program | Remove | Preserve | Preserve |
| settings (default) | Remove | Remove | Preserve |
| all (double confirmation) | Remove | Remove | Remove only after validated recovery snapshot |

The interactive uninstaller defaults to settings removal; silent removal also chooses settings, never all. The guarded `scripts/native-uninstall.ps1` validates the service executable and the **exact executable actions** of only `LKH-Codex-Agent` and `LKH-MCP-Tray`. A running service must return `busy=false` from the loopback endpoint. Any mismatched task/service, invalid path, reparse point, unreadable state, or failed stop blocks further removal; no Naru/Docker, other scheduled tasks, Cloudflare, Oracle, external profile or repo is touched. Reinstallation after settings reset uses a local one-time marker in the retained `data` directory to rotate the orphaned device verifier without wiping SQLite rows; missing credentials without that marker still fail closed. Full removal retains a verified WAL-aware SQLite snapshot *outside* the removed state under ACL-restricted `%ProgramData%\LKH-MCP-RemovalBackups\<unique-id>`. This retained copy needs a later, separately authorized deletion decision. Upgrades from old Inno uninstall logs and on-host UAC/SCM/ACL behavior require dedicated Windows VM E2E; CI alone is not production approval.

- Final Native Pig tray menu is **종료** (combined Agent + server shutdown behind UAC and confirmation). A separate tray-only exit and the server-only action are intentionally not present in the context menu. Tray stays available to report state until it is explicitly closed by Windows session termination; UAC request acceptance alone does not prove SCM stop completion.
