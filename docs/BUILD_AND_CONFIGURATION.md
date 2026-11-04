# 빌드 및 설정

기준: 2026-11-02 저장소 소스. 빌드·설치·실행·운영 전환은 별개다. 이 문서는 실제 빌드나 설치 성공의 증거가 아니다.

## 어떤 파일을 언제 사용하는가

| 입력 / 저장소 | 사용 시점과 용도 |
|---|---|
| `%ProgramData%\LKH-MCP\config\bootstrap.json` | Native 서버 실행 시 기본 검색 경로. 설치 시 관리자 초기 설정 프로그램이 없을 때만 생성하고 기존 파일을 보존한다. `LKH_NATIVE_STATE_DIR`로 상태 디렉터리를 바꾸거나 절대 경로 `MCP_BOOTSTRAP_FILE`을 지정할 수 있다. |
| `src/settings_store.py`의 `FIELDS` | 일반 설정의 코드 기본값과 허용 키. 예: Agent 비활성, 일일 30회, Oracle 호스트 `127.0.0.1`, 포트 `1521`, 나머지 텍스트 기본값은 빈 문자열. |
| SQLite `settings` | 최초 초기화 시 각 미존재 항목을 환경변수 또는 코드 기본값으로 삽입. 기존 행은 덮어쓰지 않으며 실행 시 DB 값이 프로세스 환경에 적용된다. 관리자 설정 변경도 여기에 저장된다. |
| `.env` | `settings_store.initialize()`가 소스 기준 상위 경로에서 기존 환경변수를 덮어쓰지 않고 읽는다. `.env.example`은 예시일 뿐 자동 적용되지 않는다. 패키지 실행에서는 해당 경로가 배포 형태에 따라 달라지므로 Native 설정 방법으로 가정하지 않는다. |
| `windows_agent/config.example.json` | Agent 설정 예시. Native 설치기는 `agent.example.json`으로 복사하고 별도로 `config/agent.json`을 생성한다. 기존 Agent 설정은 보존한다. |

일반 설정의 초기 우선순위는 **기존 SQLite 행 > 환경변수(기존 프로세스 환경 > `.env`) > `FIELDS` 기본값**이다. 환경변수나 기본값을 나중에 바꿔도 이미 저장된 DB 행은 자동 갱신되지 않는다. `MCP_DB_PATH`는 DB 경로를 지정한다. Native 기본 DB는 `%ProgramData%\LKH-MCP\data\mcp.sqlite3`이다.

Bootstrap은 `src/settings_store.py`에 정의된 비밀/인증 키만 허용하며 각 값은 문자열이어야 한다. 읽은 키는 같은 이름의 환경변수를 덮어쓴다. 일반 설정을 bootstrap에 넣으면 초기화가 실패한다. 파일이 없으면 건너뛰지만 관리자 로그인이나 Oracle 등은 필요한 자격증명이 없으면 사용할 수 없다. 비밀값이나 실제 파일 내용은 문서·로그·Git에 넣지 않는다.

## 중앙 개발 스킬 준비 (서버 전용)

MCP 서버/빌드 호스트에서 Windows는 `./scripts/install-matt-skills.ps1`, Linux는 `bash scripts/install-matt-skills.sh`를 한 번 실행해 `vendor/mattpocock-skills`에 upstream pinned Markdown을 설치한다. 별도 Codex/ChatGPT 클라이언트 플러그인은 설치하지 않는다. Native 빌드 시 해당 디렉터리를 번들에 포함하고 버전을 검사한다. 기존 운영 MCP 서버와 Windows Agent는 별도 승인 없이 재시작/교체하지 않는다. 자세한 내용은 [중앙 개발 스킬](ENGINEERING_SKILLS.md)을 참조한다.

## Windows Native 빌드와 설치

Windows, Python 3.11+, Node.js/npm 22+ 및 설치기 컴파일용 Inno Setup 6이 필요하다. 공개 스킬 원본은 설치할 때 내려받으므로 Native 빌드에 Git submodule 초기화는 필요하지 않다. 아래는 빌드만 하며 서비스 설치나 운영 전환을 수행하지 않는다. Python은 실행 파일의 절대 경로를 전달한다. 빌드 스크립트는 해당 Python 환경에 pip 패키지를 설치하고 `build`/`dist`, 프런트엔드 산출물을 갱신한다.

```powershell
$pythonExe = (Get-Command python).Source
.\scripts\build-native-suite.ps1 -Python $pythonExe
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' installer\LKH-MCP.iss
```

1. `build-native-server.ps1`은 `frontend`에서 `npm ci`와 빌드를 실행한다. `requirements/runtime.txt`, `requirements/build.txt`, `requirements/windows.txt` 설치, 아이콘 생성 후 PyInstaller onedir 서버에 웹 빌드를 포함한다. 공개 UIUX/Graphify 원본은 포함하지 않는다. `--check`는 번들 자산을 확인한다.
2. `build-native-suite.ps1`은 Service, Tray, Agent, 등록, 관리자 초기 설정, DB 백업 도우미를 각각 PyInstaller로 묶고 일곱 실행 파일의 존재를 확인한다. `prepare-skill-runtime.py`는 공개 스킬을 실행할 별도 Python 표준 런타임과 pip/packaging을 `dist/skills-python`에 준비한다. 기존 출력이 있으면 `dist` 안의 별도 임시 폴더에 새 런타임을 먼저 준비한다. 준비 완료 후 기존 출력을 백업으로 옮겨 교체하며, 교체 실패 시 기존 출력을 복구한다. 잠겨서 정리하지 못한 이전 백업은 보존하고 경고한다.
3. Inno Setup은 이 산출물과 설치 스크립트·Agent 예시를 묶어 `dist/installer/LKH-MCP-Setup-<version>-UNSIGNED.exe`를 생성한다. 서명되지 않은 staging 산출물이다.
4. **설치 프로그램 실행 시에만** 사전 검사, 관리자 초기 설정, 장치 등록, 서비스와 작업 스케줄러 등록 등이 수행된다. 최초 관리자는 콘솔에서 암호를 입력하며 해시가 저장된다. 기존 bootstrap은 보존된다. 프로젝트가 없어도 Agent는 연결 상태를 보고할 수 있다. 관리자 설정에서 Agent 활성화를 확인하고 Repository 화면에서 실행 설정을 등록한다. 실제 설치·서비스·계정·복구 동작은 대상 Windows에서 별도 검증이 필요하다.

기본 Native 리스너는 MCP `127.0.0.1:8000`, Admin `127.0.0.1:8001`이다. 기존 서비스와 병행하는 격리 시험은 `MCP_PORT=18080`, `LKH_NATIVE_ADMIN_PORT=18081`과 별도 절대경로 `LKH_NATIVE_STATE_DIR`을 명시한다. Native 기본 관리자 origin은 `http://127.0.0.1:8001`이므로 다른 origin은 인증 정책과 함께 별도 설정해야 한다. 운영 서비스와 DB를 건드리지 않는다.

Windows CI의 실제 단계는 `.github/workflows/windows-native.yaml`을 참조한다. CI 통과는 대상 PC의 설치, Oracle, Cloudflare 또는 운영 전환 검증을 뜻하지 않는다.

## Native 운영과 복구

관리자 화면은 기본 `http://127.0.0.1:8001/admin`에서 접근한다. 관리자 세션에는 암호와 Origin/Host/CSRF 검사가 적용된다. 다른 origin이나 외부 접근을 사용하기 전 인증·네트워크 정책을 별도 검토한다. 서버를 재시작하면 메모리 세션은 초기화된다.

Agent가 작업을 수행하려면 설치 시 지정한 사용자에 Git을 준비하고, Codex 실행 작업에는 Codex CLI 로그인이 필요하다. Graphify는 LKH가 관리하는 다운로드 원본과 Python 런타임을 사용하므로 사용자별 스킬 설치가 필요 없다. 관리자 설정에서 `CODEX_AGENT_ENABLED`, `CODEX_MAX_RUNS_PER_DAY`를 확인하고 Repository 화면에서 프로젝트 별칭·GitHub 저장소·실행할 Agent·로컬 절대 경로를 등록한다. 시작 요청의 성공과 인증 heartbeat Online은 별개다. 설치기와 Agent 설정은 위 빌드·설치 절차를 따른다.

장애가 발생하면 서비스와 고정 작업 상태, 포트 점유, Codex 로그인 상태를 확인한다. 임시 worktree의 `WinError 5`는 해당 작업의 ACL과 Git worktree 상태를 조사하고, MXC의 `SystemDrive` 오류는 Agent 환경변수를 확인한다. 광범위한 ACL 수정이나 무조건적인 강제 삭제는 하지 않는다.

관리자 Agent start/restart는 등록된 대화형 계정의 SID와 일치하는 단일 활성 Windows 세션을 찾아 고정 작업을 `RunEx`로 시작한다. 서버 서비스의 세션 0이나 다른 로그인 사용자의 세션을 임의로 사용하지 않는다. 해당 계정의 활성 세션이 없거나 여러 개이면 계정·세션 상태를 먼저 확인한다. 작업 실행 요청 수락과 인증 heartbeat Online은 계속 구분한다. `0x800710E0`만으로 배터리·권한 원인을 단정하지 말고 작업 조건과 실제 세션 실행 결과를 함께 확인한다.

SQLite는 WAL 정합성을 보장한 백업을 사용한다. 활성 DB 파일 하나만 복사하지 않는다. `native_migration`은 승인된 SQLite 복제본을 검사하거나 새 경로에 백업한다.

### Windows Agent 검증 환경 준비

Gradle 또는 프론트엔드 검증을 준비하려면 **Agent 로컬의 비공개 `agent.json`**에 `verification_environments`를 설정한다. 빈 객체 또는 항목 생략 시 기존 실행 방식을 유지한다. 서버의 작업 지침이나 저장소 파일로 준비 경로·권한을 지정할 수 없다. 프로젝트 별칭, GitHub 저장소와 정본 로컬 경로가 모두 일치해야 적용된다. Repository 화면에서 Agent/경로를 바꾸면 로컬 프로필도 별도로 검토해야 한다.

아래는 설정 구조 예시다. `C:/approved-assets`는 관리자가 미리 준비한 로컬 스냅샷 경로로 교체한다. 실제 설치본 설정은 자동으로 변경하지 않는다.

```json
{
  "verification_environments": {
    "ITAM": {
      "repository": "gyangho/ITAM",
      "path": "C:/Users/User/Desktop/이경호/개발/ITAM",
      "gradle": {
        "project_dir": "spring-itam-server",
        "distribution": "C:/approved-assets/gradle-9.5.1",
        "dependency_cache": "C:/approved-assets/modules-2",
        "java_executable": "C:/Program Files/Java/jdk-26.0.1/bin/java.exe"
      },
      "frontend": {
        "project_dir": "itam-frontend",
        "snapshot": "C:/approved-assets/itam-frontend",
        "node_executable": "C:/Program Files/nodejs/node.exe"
      }
    }
  }
}
```

- `gradle`과 `frontend`는 필요한 항목만 등록할 수 있다. Gradle 배포본은 wrapper에 고정된 버전과 같은 Gradle 9 CLI 형식의 압축 해제 디렉터리여야 한다. `dependency_cache`는 해당 버전으로 준비한 `modules-2` 디렉터리이며 Gradle 모듈 캐시 구조만 허용한다. 인증정보가 있는 사용자 홈·`gradle.properties`·`.npmrc`를 통째로 준비하지 않는다.
- 프론트엔드 스냅샷에는 대상 커밋과 바이트가 동일한 `package.json`, `package-lock.json` 및 완성된 `node_modules`가 필요하다. npm lockfile의 `packages` 형식과 숨김 `.package-lock.json`의 버전·integrity를 대조한다. 없는 optional 패키지는 허용한다. 이 대조는 설치 파일 전체의 암호학적 무결성 검증이 아니므로 승인된 스냅샷을 사용한다. 링크 기반 workspace/pnpm 설치와 symlink/junction/reparse point는 지원하지 않는다.
- `verify` 작업에서만 준비한다. Agent가 임시 worktree의 `.lkh-verification` 아래에 배포본·캐시를 복사하고, 프론트엔드 프로젝트 내부에 `node_modules`를 복사한다. 캐시의 `*.lock`, `gc.properties`는 제외한다. 원본 ACL·캐시·저장소는 수정하지 않으며 다운로드나 설치 명령을 실행하지 않는다. 복사는 총 20만 파일/8 GiB/300초로 제한한다. 예약된 준비 경로나 `node_modules`가 이미 있으면 덮어쓰지 않고 중단한다.
- 준비 후 `codex sandbox --include-managed-config --permission-profile :workspace`로 실제 Gradle `help --offline --no-daemon`과 Node 시작을 확인한다. 프로젝트 코드는 이 단계부터 샌드박스 안에서만 실행한다. 사전 실행 후 추적 파일과 HEAD가 유지되는지 확인한다. 보안 정책을 완화하거나 루프백을 자동 허용하지 않는다. 준비·사전 실행 실패는 `environment_blocked`, `tests_executed: 0` 및 비밀정보를 제거한 고정 원인 코드로 반환하고 Codex 검증을 시작하지 않는다. Codex CLI가 해당 sandbox 명령을 지원해야 한다.
- 성공하면 준비된 Gradle 명령 토큰, 경로·버전·사전 실행 결과를 Codex 프롬프트로 전달한다. Gradle은 배치 셸 대신 승인된 Java와 복사한 CLI JAR로 실행한다. 모델 실행에는 기존 `workspace-write`를 유지하고 전용 Gradle/임시 경로, 승인된 Java/Node 경로 및 npm 설정을 정리된 환경에 추가한다. npm은 worktree 내부의 빈 사용자·전역 설정과 전용 캐시를 사용하며 offline 모드를 적용한다. 사전 실행 성공은 테스트 통과가 아니다.

`VERIFICATION_LOOPBACK_DENIED`는 같은 샌드박스 안의 Gradle 루프백 연결이 차단됐다는 신호다. 실제 적용된 Windows 샌드박스·조직 네트워크 정책을 확인해야 하며, 이 준비 기능만으로 차단 정책이 해결되지는 않는다. 새 Agent 바이너리 배포, 자산 준비 및 실제 대상 Windows E2E는 별도 단계다.

```powershell
$env:PYTHONPATH = "src"
python -m native_migration --source "C:\secure-export\mcp.sqlite3"
python -m native_migration --source "C:\secure-export\mcp.sqlite3" --destination "C:\isolated-staging\mcp-backup.sqlite3" --copy
```

목적지는 존재하면 안 된다. 복원과 롤백은 복제본에서 검증하며 운영 데이터·서비스·라우팅 변경은 별도 승인 후 수행한다. [CI 및 검증](VERIFICATION.md)에 남은 검증이 기록되어 있다.

## Repository 연결과 공개 구성요소

- Repository 화면의 연결 확인은 선택한 Agent에 비동기로 전달된다. 해당 폴더가 Git 최상위 경로인지, origin이 승인된 GitHub 저장소인지, `git ls-remote origin HEAD`가 가능한지 확인한다. fetch/pull/checkout은 수행하지 않는다. Agent가 응답하지 않으면 180초 후 실패로 표시된다.
- 저장한 실행 설정은 Agent가 다음 폴링 때 받아 메모리에 적용한다. 기존 agent.json의 프로젝트는 서버에서 아직 실행 Agent를 지정하지 않은 기존 승인 항목에만 호환용으로 사용한다. 삭제하거나 다른 Agent로 배정한 설정은 기존 로컬 경로로 계속 실행하지 않는다.
- 설치 시 `install-public-skills.py`가 공식 GitHub 저장소의 latest 정식 release를 확인하고 태그가 가리키는 커밋으로 소스를 다운로드한다. Graphify는 현재 0.9.30 이상 0.10 미만을 지원한다. 지원 범위를 벗어난 최신 버전, 필수 파일/라이선스 누락, 네트워크 또는 wheel 설치 실패 시 설치를 중단한다. Graphify 의존성 wheel은 설치 시 PyPI에서 별도 다운로드한다. 인터넷 연결이 필요하다.
- 공개 원본은 `{app}/skills`, 공용 Python은 `{app}/skills-python`에 둔다. 라이선스·출처·release·커밋과 다운로드 SHA-256을 보존한다. SHA-256은 로컬 다운로드 기록이며 upstream 서명 검증을 의미하지 않는다. 두 구성요소가 준비된 뒤 active.json을 교체하므로 실패 시 이전 활성 버전 선택은 유지한다. 실패 단계는 `{app}/skills/install-status.json`에 비밀정보 없이 기록한다.
- Graphify는 선택한 Agent 계정으로 설치 패키지의 Python/분석 코드를 실행한다. 서비스 계정으로 사용자 저장소를 열거나 별도 모델 API를 호출하지 않는다. 기본 모드는 코드 AST 분석이며 문서/이미지 의미 분석은 포함하지 않는다. 고정 SHA의 임시 worktree에서 기존 graph.json을 제거하고 새 결과만 게시한다.
- Repository 화면에서 설치된 UIUX/Graphify 버전을 표시한다. 다운로드한 원본 버전 폴더는 제거 시 함께 삭제하며 사용자 저장소는 삭제하지 않는다. Python/실행 코드 준비 성공, 실제 설치, Windows SCM/UAC와 외부 시스템 검증은 별개다.

트레이 종료 진행창은 시간 비율 대신 상태 확인·Agent 중지·UAC 대기·SCM 중지 확인의 단계 진행을 표시한다. 트레이 자체 로그는 서비스 전용 ProgramData 로그와 별도로 `%LOCALAPPDATA%/LKH-MCP/logs/tray.log`에 기록한다. 시작 기록의 `2026-11-03-native-progress` revision으로 새 진행창 코드가 실행 중인지 구분할 수 있다. 설치 오류 상태에는 `latest-release`, `resolve-release-tag`, `resolve-annotated-tag` 단계를 구분하고 고정 원인 코드를 기록한다.

## Native 실행·설치 완료·버전

- 시작 메뉴의 **LKH MCP** 실행은 서버를 시작하고 관리자 리스너 준비를 확인한 뒤 트레이를 표시한다. 별도 서버 시작 바로가기는 만들지 않는다. 서비스가 이미 실행 중이면 중복 시작하지 않으며, 같은 로그인 세션에 트레이를 중복 표시하지 않는다. 서버가 STOPPED 또는 미설치(1060)이면 트레이도 종료한다. 상태 조회 실패는 로그와 상태 불명으로 구분한다.
- 설치 시작 전에 기존 설치 소유 서비스·작업·프로세스를 확인하고 실행 중 작업이 없는 경우 중지한다. 설치 중에는 서비스를 비활성화하고 작업도 비활성 상태로 등록한다. 진행/실패/완료는 ProgramData 설정 폴더의 installation.json에 기록한다. 서비스·서버·트레이·Agent는 설치 버전과 완료 상태가 맞아야 실행할 수 있다.
- 서비스의 최초 기동 확인 동안에는 starting 상태로 healthz만 허용한다. 관리자 리스너의 앱·버전·PID와 SCM 서비스 자식 프로세스가 맞는지 확인하고 ready로 전환한다. ready 전에 MCP 및 Agent 요청은 허용하지 않는다. 실패·취소 시 실패 상태로 남기고 해당 설치 소유 서비스/작업을 중지·비활성화한다. 설치 후 트레이 실행은 성공 조건으로 제한하며 Restart Manager의 자동 재실행은 사용하지 않는다.
- build-native-suite.ps1을 호출할 때 patch 버전을 한 번 증가시킨다. server 단독 빌드도 한 번 증가시키지만 suite 내부 호출은 중복 증가하지 않는다. 실패한 빌드도 증가한 번호를 유지한다. src/version.py, 모든 EXE의 Windows 버전 리소스, installer/version.iss를 같은 버전으로 생성한다. 설치기 파일명에도 버전을 넣는다. ISCC만 실행하면 이미 준비한 바이너리 버전을 사용한다.
- 이 동작은 코드 구현이며 실제 UAC·설치 실패 복구·재기동·중복 실행과 빌드는 별도 검증 대상이다.

## 공개 소스 ACL 및 Windows Oracle 로딩 복구

설치 소스가 tempfile의 관리자/소유자 전용 ACL을 유지하지 않도록 게시 전 최종 skills 폴더 ACL로 재설정한다. 이미 설치된 소스는 관리자 권한으로 설치 Python에서 `scripts/install-public-skills.py --repair-permissions "설치 루트 절대 경로"`를 실행해 manifest에 등록된 두 공개 소스 폴더만 복구할 수 있다. 부모 skills 폴더는 설치기가 설정한 관리자/SYSTEM 쓰기, LocalService/Users 읽기·실행 ACL이어야 한다.

Windows frozen 서버에서 올바른 Client DLL에도 DPI-1072가 발생할 수 있다. `_driver`는 설정된 Oracle Client 디렉터리를 프로세스 PATH 앞에 추가하고 명시적인 lib_dir로 초기화한다. 기존 설치본의 현장 복구에는 서비스 전용 Environment/PATH를 보완하고 유휴 확인 후 LKH-MCP-Server만 재시작했다. 시스템 PATH 변경이나 DB Client 교체는 필요하지 않았다. 실제 검증 결과는 [검증](VERIFICATION.md)의 2026-11-03 Portal 복구 항목을 참조한다.
