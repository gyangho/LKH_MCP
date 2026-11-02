# 빌드 및 설정

기준: 2026-11-02 저장소 소스. 빌드·설치·실행·운영 전환은 별개다. 이 문서는 실제 빌드나 설치 성공의 증거가 아니다.

## 어떤 파일을 언제 사용하는가

| 입력 / 저장소 | 사용 시점과 용도 |
|---|---|
| `%ProgramData%\LKH-MCP\config\bootstrap.json` | Native 서버 실행 시 기본 검색 경로. 설치기가 파일이 없을 때만 관리자 설정을 생성하고 기존 파일을 보존한다. `LKH_NATIVE_STATE_DIR`로 상태 디렉터리를 바꾸거나 절대 경로 `MCP_BOOTSTRAP_FILE`을 지정할 수 있다. |
| `src/settings_store.py`의 `FIELDS` | 일반 설정의 코드 기본값과 허용 키. 예: Agent 비활성, 일일 30회. Oracle 접속 항목은 별도의 연결 관리에 저장한다. |
| SQLite `settings` | 최초 초기화 시 각 미존재 항목을 환경변수 또는 코드 기본값으로 삽입. 기존 행은 덮어쓰지 않으며 실행 시 DB 값이 프로세스 환경에 적용된다. 관리자 설정 변경도 여기에 저장된다. |
| `.env` | `settings_store.initialize()`가 소스 기준 상위 경로에서 기존 환경변수를 덮어쓰지 않고 읽는다. `.env.example`은 예시일 뿐 자동 적용되지 않는다. 패키지 실행에서는 해당 경로가 배포 형태에 따라 달라지므로 Native 설정 방법으로 가정하지 않는다. |
| `windows_agent/config.example.json` | Agent 설정 예시. Native 설치기는 `agent.example.json`으로 복사하고 별도로 `config/agent.json`을 생성한다. 기존 Agent 설정은 보존한다. |

일반 설정의 초기 우선순위는 **기존 SQLite 행 > 환경변수(기존 프로세스 환경 > `.env`) > `FIELDS` 기본값**이다. 환경변수나 기본값을 나중에 바꿔도 이미 저장된 DB 행은 자동 갱신되지 않는다. `MCP_DB_PATH`는 DB 경로를 지정한다. Native 기본 DB는 `%ProgramData%\LKH-MCP\data\mcp.sqlite3`이다.

Bootstrap은 `src/settings_store.py`에 정의된 비밀/인증 키만 허용하며 각 값은 문자열이어야 한다. 읽은 키는 같은 이름의 환경변수를 덮어쓴다. 일반 설정을 bootstrap에 넣으면 초기화가 실패한다. 파일이 없으면 건너뛰지만 관리자 로그인은 초기 설정 없이는 사용할 수 없다. Oracle 암호는 연결 관리에서 별도로 저장한다. 비밀값이나 실제 파일 내용은 문서·로그·Git에 넣지 않는다.

## Windows Native 빌드와 설치

Windows, Python, Node.js/npm 22+, 초기화된 Git submodule 및 설치기 컴파일용 Inno Setup 6이 필요하다. 아래는 빌드만 하며 서비스 설치나 운영 전환을 수행하지 않는다. Python은 실행 파일의 절대 경로를 전달한다. 빌드 스크립트는 해당 Python 환경에 pip 패키지를 설치하고 `build`/`dist`, 프런트엔드 산출물을 갱신한다.

```powershell
git submodule update --init --recursive
$pythonExe = (Get-Command python).Source
.\scripts\build-native-suite.ps1 -Python $pythonExe
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' installer\LKH-MCP.iss
```

1. `build-native-server.ps1`은 submodule을 확인하고 `frontend`에서 `npm ci`와 빌드를 실행한다. `requirements/runtime.txt`, `requirements/build.txt`, `requirements/windows.txt` 설치, 아이콘 생성 후 PyInstaller onedir 서버에 웹 빌드와 vendor를 포함한다. `--check`는 번들 자산을 확인한다.
2. `build-native-suite.ps1`은 Service, Tray, Agent, 등록, 관리자 초기 설정, DB 백업 도우미를 각각 PyInstaller로 묶고 일곱 실행 파일의 존재를 확인한다.
3. Inno Setup은 이 산출물과 설치 스크립트·Agent 예시를 묶어 `dist/installer/LKH-MCP-Setup-UNSIGNED.exe`를 생성한다. 서명되지 않은 staging 산출물이다.
4. **설치 프로그램 실행 시에만** 사전 검사, 관리자 초기 설정, 장치 등록, 서비스와 작업 스케줄러 등록 등이 수행된다. 최초 관리자는 설치 마법사에서 계정과 암호(14–256자)를 입력하며 해시만 저장된다. 암호는 표준입력 파이프로 전달하고 명령행·설치 로그·중간 파일에 기록하지 않는다. 최초 무인 설치는 관리자 입력이 없어 차단되며, 기존 bootstrap이 있는 업데이트는 입력을 건너뛴다. 기존 bootstrap은 보존된다. Agent 프로젝트 정보가 없으면 Agent 작업이 비활성화된다. 실제 설치·서비스·계정·복구 동작은 대상 Windows에서 별도 검증이 필요하다.

기본 Native 리스너는 MCP `127.0.0.1:8000`, Admin `127.0.0.1:8001`이다. 기존 서비스와 병행하는 격리 시험은 `MCP_PORT=18080`, `LKH_NATIVE_ADMIN_PORT=18081`과 별도 절대경로 `LKH_NATIVE_STATE_DIR`을 명시한다. Native 기본 관리자 origin은 `http://127.0.0.1:8001`이므로 다른 origin은 인증 정책과 함께 별도 설정해야 한다. 운영 서비스와 DB를 건드리지 않는다.

Windows CI의 실제 단계는 `.github/workflows/windows-native.yaml`을 참조한다. CI 통과는 대상 PC의 설치, Oracle, Cloudflare 또는 운영 전환 검증을 뜻하지 않는다.

## Native 운영과 복구

관리자 화면은 기본 `http://127.0.0.1:8001/admin`에서 접근한다. 관리자 세션에는 암호와 Origin/Host/CSRF 검사가 적용된다. 다른 origin이나 외부 접근을 사용하기 전 인증·네트워크 정책을 별도 검토한다. 서버를 재시작하면 메모리 세션은 초기화된다.

Agent가 작업을 수행하려면 설치 시 지정한 사용자에 Git, Codex CLI 로그인과 필요한 Graphify skill을 준비하고, 환경 설정에서 `CODEX_AGENT_ENABLED`, `CODEX_MAX_RUNS_PER_DAY`를 확인하고 Git 메뉴의 승인 목록에 별칭·저장소를 등록한다. 시작 요청의 성공과 인증 heartbeat Online은 별개다. 설치기와 Agent 설정은 위 빌드·설치 절차를 따른다.

장애가 발생하면 서비스와 고정 작업 상태, 포트 점유, Codex 로그인 상태를 확인한다. 임시 worktree의 `WinError 5`는 해당 작업의 ACL과 Git worktree 상태를 조사하고, MXC의 `SystemDrive` 오류는 Agent 환경변수를 확인한다. 광범위한 ACL 수정이나 무조건적인 강제 삭제는 하지 않는다.

SQLite는 WAL 정합성을 보장한 백업을 사용한다. 활성 DB 파일 하나만 복사하지 않는다. `native_migration`은 승인된 SQLite 복제본을 검사하거나 새 경로에 백업한다.

```powershell
$env:PYTHONPATH = "src"
python -m native_migration --source "C:\secure-export\mcp.sqlite3"
python -m native_migration --source "C:\secure-export\mcp.sqlite3" --destination "C:\isolated-staging\mcp-backup.sqlite3" --copy
```

목적지는 존재하면 안 된다. 복원과 롤백은 복제본에서 검증하며 운영 데이터·서비스·라우팅 변경은 별도 승인 후 수행한다. [CI 및 검증](VERIFICATION.md)에 남은 검증이 기록되어 있다.

## Oracle 연결 관리

설치 후 `/admin/oracle`에서 이름, 주소·포트, Service Name 또는 SID, 계정·암호, 허용 테이블과 활성 상태를 등록한다. 암호는 다시 표시하지 않으며 수정 시 빈 값은 기존 암호를 유지한다. 저장된 연결 테스트는 고정 DUAL 조회만 수행하고, 편집 중인 미저장 값은 사용하지 않는다. 비활성 연결도 관리자 테스트는 가능하다. 최대 20개를 등록할 수 있다.

일반 연결정보는 SQLite `oracle_connections`에 저장하고 암호는 Windows machine-DPAPI 암호문으로 함께 보관한다. 저장 경로의 기존 서비스 ACL을 유지해야 한다. DB 보존 방식의 제거/재설치는 연결정보도 보존한다. 다른 PC로 DB를 옮기면 암호를 복호화할 수 없으므로 관리자 화면에서 암호를 다시 입력한다.

서버 공통 `ORACLE_CLIENT_LIB_DIR`은 환경 설정에서 관리한다. Thin/Thick 모드와 Instant Client는 프로세스 공통이므로 변경 후 서버를 재시작한다. Oracle 11g는 호환되는 Thick Client를 준비한다.

기존 단일 Oracle 설정이 완전한 경우 연결 관리의 최초 접근 때 `legacy` ID로 한 번 이전한다. 기존 SQLite 설정과 환경·bootstrap 암호를 읽으며 원본은 삭제하지 않는다. 암호 누락·잘못된 설정은 이전을 완료하지 않으므로 먼저 원본 설정을 보완한다. 이전 완료 뒤 환경변수 변경으로 연결정보를 덮어쓰거나, 삭제한 연결을 다시 생성하지 않는다.

MCP는 `oracle_list_connections`로 활성 연결의 ID와 이름을 확인한 뒤 Oracle 조회 도구마다 `connection_id`를 필수로 전달한다. 이전의 인자 없는 호출은 변경해야 하며 클라이언트 도구 목록을 다시 동기화한다. 모든 활성 연결은 기존 MCP 접근 경계 안에서 공유되며 사용자별 DB 권한 분리는 제공하지 않는다. 비활성화·삭제는 새 조회를 막지만 이미 실행 중인 조회는 완료될 수 있다.

## 승인 저장소 설정

환경 설정 → Git에서 저장소를 한 항목씩 추가·수정·삭제한다. 별칭은 Agent의 `projects` 키와, `owner/repository`는 해당 프로젝트의 repository 값과 일치해야 한다. 설치기의 초기 프로젝트 입력은 Agent의 로컬 설정을 만드는 것이며 서버 승인은 이 목록에서 별도로 등록한다.

기존 SQLite의 `GIT_ALLOWED_REPOS` 행 또는 환경변수는 첫 접근 때 `approved_repositories`로 한 번 이전한다. 이후 세미콜론 문자열은 편집에 사용하지 않고 목록만 정본으로 사용한다. 삭제한 항목은 재시작해도 자동 복구되지 않는다. 기존 원본 행과 감사 이력은 보존한다.

승인 변경·삭제는 대기 작업을 취소하므로 확인 후 실행한다. 실행 중 작업이 있으면 완료·실패 상태가 확인된 후 다시 변경한다. 서버 승인 목록을 수정해도 Agent 설정의 checkout 경로는 바뀌지 않는다.
