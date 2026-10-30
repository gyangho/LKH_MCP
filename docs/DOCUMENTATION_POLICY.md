# 문서 정책 v1.0

상태: **ADOPTED** · 2026-10-30 · 범위: 저장소·설계·운영·릴리스 문서

## 정본 정책

- 제품/개발 진척: `ROADMAP.md`, 운영 명령: `OPERATIONS.md`, 아키텍처: `ARCHITECTURE.md`, 설치 계약: `WINDOWS_INSTALLER_DESIGN.md`, 보안: `SECURITY_AND_ENROLLMENT.md`, 데이터 이전: `MIGRATION_AND_RELEASE.md`, 결정: `DECISIONS.md`.
- `README.md`는 진입점만 유지하고 중복 장문을 만들지 않는다. 필수 라이선스 고지는 보존.
- 모든 계획·코드·문서에 **AS-IS/TO-BE/DEPRECATED/REMOVED/UNVERIFIED**를 구분. CI PASS만으로 Windows 실환경 E2E PASS나 RELEASED 주장 금지.
- 단계 진행: NOT_STARTED → IN_PROGRESS → IMPLEMENTED(코드/CI) → VERIFIED(요구된 실기/보안 E2E) → RELEASED(운영 전환); BLOCKED는 별도 원인 기록.
- 변경 PR마다 영향 범위, 테스트/빌드·Windows 증거, 문서 수정, 배포·롤백, 비공개 정보 제외 여부를 검토한다.

## 코드/문서 제거 규칙

1. 실제 등록 경로·import·CLI·테스트·CI·배포 의존성 확인 후 **비사용이 증명된 레거시**만 관련 코드·테스트·참조와 함께 삭제.
2. Docker Codex Worker, 예전 직접 Git/Graphify MCP 도구처럼 현재 서버에 미등록된 구현은 제거한다. 설치 전환과 연계된 동작 중인 Docker `compose.yaml`/`Dockerfile`/`nginx`, Oracle, Agent 큐, Pixel Pig 원본은 유지.
3. 사용되지 않는 설정 키는 UI 및 활성 코드에서 제거. 이미 있는 SQLite 행/감사 이력은 별도의 백업·승인된 마이그레이션에서만 정리; 데이터베이스 볼륨이나 사용자 secret 삭제 금지.
4. 버전/동작과 상충되는 문서는 사실을 정본에 옮기고 원본을 제거한다. 필요하면 `git log -- <path>`에서 이력 조회.
5. 자격증명·토큰·개인정보·SQL 덤프·사용자별 민감 환경 경로를 문서·PR·CI 출력에 싣지 않는다. Git에서 파일을 삭제해도 과거 비밀이 소거되지는 않는다.

## 검증 기준

- Python `compileall` 및 단위 테스트, 웹 `npm ci && npm run build`, 현재 Docker/Nginx 분리 검증(CI).
- Windows Service/Task Scheduler/트레이/서명/윈도우 Codex MXC는 별도 Windows VM·실기 E2E. 문서 링크와 파일 삭제 후 죽은 import 점검.
- Git commit/push 승인은 운영 서비스 중단, 방화벽 변경, 자격증명 교체, DB schema/data 파괴를 자동 승인하지 않는다.
- 보고: 문서와 코드 변경·삭제, 테스트 증거, 잔여 위험 및 승인 필요한 배포 절차.
