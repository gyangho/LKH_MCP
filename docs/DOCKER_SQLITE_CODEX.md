# Docker Compose · SQLite · Codex 승인 운영 가이드

## 환경변수 최소화

기본 Compose에서 필요한 환경변수는 MCP_HOST=0.0.0.0 하나입니다.
SQLite는 컨테이너 /app/data/mcp.sqlite3에 생성되고 Docker named volume
mcp-data에 지속됩니다. 관리자 설정 화면: /admin/config.

SQLite 저장 설정:
- Git 권한: GIT_ALLOW_COMMIT, GIT_ALLOW_PUSH, GIT_ALLOWED_REPOS, GIT_EXECUTABLE
- Graphify: GRAPHIFY_ALLOW_UPDATE, GRAPHIFY_PROJECTS, GRAPHIFY_EXECUTABLE
- Codex: CODEX_DELEGATION_ENABLED, CODEX_MAX_RUNS_PER_DAY
- Oracle: HOST, PORT, SERVICE/SID, DSN, USER, ALLOWED_TABLES, CLIENT_LIB_DIR

비밀값은 SQLite에 저장하지 않습니다. secrets/bootstrap.json
(Docker secret /run/secrets/mcp_bootstrap.json)은 아래 키만 사용합니다.
ORACLE_PASSWORD, ADMIN_CF_TEAM, ADMIN_CF_AUD, ADMIN_ALLOWED_EMAILS,
ADMIN_PUBLIC_ORIGIN.

MCP_DB_PATH와 MCP_BOOTSTRAP_FILE는 기본 경로를 바꿔야 할 때만
설정합니다. 기존 Windows .env를 가진 경우 SQLite 최초 생성 시
일반 설정을 불러옵니다. 그 이후에는 SQLite 값이 우선합니다.

## Docker 실행

Windows PowerShell에서 다음을 실행합니다.

    git status
    git pull --ff-only origin main
    git submodule update --init --recursive
    Copy-Item secrets/bootstrap.example.json secrets/bootstrap.json
    notepad secrets/bootstrap.json
    docker compose up -d --build
    docker compose ps
    docker compose logs --tail=100 mcp

bootstrap.json은 gitignore에 제외되어 있습니다. 예제 값을 실제
Cloudflare Access team, AUD, 관리자 이메일 및 Oracle 비밀번호로
교체해야 합니다. Cloudflare Tunnel은 기존의 mcp.gyangho.com
주소와 http://127.0.0.1:8000 origin을 유지합니다.

서비스 경로:
- /mcp 기존 MCP
- /healthz 공개 최소 생존 상태
- /admin 모니터링
- /admin/config SQLite 설정 페이지
- /admin/codex Codex 승인 페이지

Cloudflare Access JWT를 검증해야 관리 경로에 접근할 수 있습니다.
Cloudflare Tunnel 연결 자체는 관리자 인증을 대체하지 않습니다.

## 프로젝트 마운트

Docker는 Windows의 원본 소스 폴더를 자동으로 읽을 수 없습니다.
로컬 전용 compose.override.yaml을 생성하고 등록한 경로만 마운트하세요.

    services:
      mcp:
        volumes:
          - "C:/Projects/ITAM:/projects/ITAM:rw"
          - "C:/Projects/LKH_MCP:/projects/LKH_MCP:rw"

관리자 /admin/config 페이지에서 다음과 같이 설정합니다.

    GRAPHIFY_PROJECTS=ITAM=/projects/ITAM;LKH_MCP=/projects/LKH_MCP
    GIT_ALLOWED_REPOS=ITAM=gyangho/ITAM;LKH_MCP=gyangho/LKH_MCP

실제 저장소 이름 및 경로에 맞춰 변경하세요. Git push에는 별도의
비대화형 인증이 필요합니다. Docker socket이나 GitHub PAT를
Codex worker에 마운트해서는 안 됩니다.

Oracle 11g는 Linux용 Instant Client 19를 별도로 설치/마운트해야
연결됩니다. Windows 호스트에 Oracle DB가 있을 때는 Oracle 주소를
host.docker.internal로 지정할 수 있습니다. DB 계정은 SELECT 전용을
권장하며 Oracle 포트를 외부에 공개하지 마세요.

## Codex 디버깅 worker: 기본 비활성화

Codex가 GitHub에 직접 쓰거나 신규 기능을 개발하지 못하도록
별도 worker 컨테이너에서 승인된 소스 파일만 처리합니다.
MCP SQLite, Oracle/Cloudflare secrets, Git 작업 트리는 worker에
마운트하지 않습니다.

1. Python으로 내부 인증 토큰 파일을 생성하세요.

       python -c "import secrets,pathlib; pathlib.Path('secrets/codex_worker_token').write_text(secrets.token_hex(32),encoding='utf-8')"

2. worker를 선택적으로 실행합니다.

       docker compose -f compose.yaml -f compose.codex.yaml --profile codex up -d --build

3. worker의 codex-auth 볼륨에 Codex CLI 인증을 설정하세요.
   설치 버전의 codex login 또는 device-auth 절차를 사용합니다.
   MCP 본체와 Codex 인증 정보를 공유하지 마세요.
4. /admin/config에서 CODEX_DELEGATION_ENABLED=true, 일일 1~10회 제한을
   설정합니다.
5. ChatGPT가 codex_request_debug를 호출하면 pending 요청만 생성됩니다.
6. /admin/codex에서 실제 사용자가 분석 실행을 승인합니다.
7. 10분 이내 codex_run_approved를 호출하고 codex_get_task로 결과를
   확인합니다. Codex는 별도 worker에서 최대 12개 허용 소스를 다룹니다.
8. 최소 수정 diff가 올바르면 별도로 승인하고
   codex_apply_approved_patch를 호출합니다.
9. Git 커밋과 push는 ChatGPT와 사용자에게 다시 확인받은 후
   기존 git_stage_paths / git_preview_commit / git_commit / git_push로 처리합니다.

worker는 별도 Docker 이미지로 실행되며 포트를 호스트에 노출하지
않습니다. Docker/Codex 샌드박스가 완전한 격리 장벽을 보장하지는
않습니다. Linux sandbox 권한 문제 발생 시 우회 옵션으로 완화하지
말고 worker 로그와 격리 구성을 점검하세요.

## UI UX Pro Max 오류

UIUX 도구가 Error executing tool을 반환하면 먼저
uiux_diagnostics로 search_script_found와
python_interpreter_available을 확인하세요. vendor의 검색 스크립트가
없으면 이미 Docker 이미지 빌드에서 실패하게 설정했습니다.

    git submodule update --init --recursive
    docker compose logs --tail=200 mcp

실제 서버 traceback 없이 오류 원인을 하나로 단정하지 마세요.

## 확인·백업

    docker compose config
    docker compose build
    docker compose up -d
    docker compose exec mcp python -m compileall -q /app/src

소스 개발 환경의 테스트 명령:

    python -m unittest discover -s tests -t . -p "test_*.py" -v

운영 이미지는 테스트 모듈을 포함하지 않습니다. SQLite DB 백업은
온라인 백업 API를 사용하거나 컨테이너를 중지하고 복사하세요.
실행 중에 WAL 파일을 제외한 단순 파일 복사는 안전하지 않습니다.

이 문서는 운영 배포 절차입니다. 실제 Docker Desktop 및 Oracle,
Codex 인증, Cloudflare Access 환경에서의 통합 테스트는 별도입니다.
