# LKH MCP

Windows 중심 MCP/관리 서버. **현재 운영은 Naru Docker + Windows Codex Agent**이며, **목표는 Windows Native Service + Task Scheduler + Pixel Pig Tray + 단일 Installer**이다. Installer 전환은 아직 구현되지 않았다.

## 기능 및 실행 상태

- 현재: MCP Streamable HTTP `/mcp`, React 관리자 `/admin`/`/admin/config`/`/admin/codex`, Oracle SELECT-only, SQLite 설정/작업 큐, Windows Agent heartbeat, GitHub SHA 기반 검증/진단/fix 제안/Graphify.
- 계획: Windows 부팅 시 서버 자동실행, 트레이 초록(Agent Online)/핑크(Offline)/회색(판별불가), UI에서 Agent 시작/중지, 자동 기기 인증·토큰 갱신, Codex 실시간 콘솔, 지침/로그/관측, Installer.
- **Docker는 Native 전환과 DB 이관 E2E 통과 및 별도 운영 승인 전까지 유지한다.**

## 공식 문서

| 문서 | 단일 정본 |
|---|---|
| [문서 정책](docs/DOCUMENTATION_POLICY.md) | 정본·상태·정리 규칙 |
| [통합 로드맵](docs/ROADMAP.md) | Installer I0–I7 + 기존 Phase 0–9 |
| [아키텍처](docs/ARCHITECTURE.md) | 현재/목표 프로세스·포트·데이터 |
| [Windows 설치기 설계](docs/WINDOWS_INSTALLER_DESIGN.md) | EXE·서비스·트레이·스케줄러 |
| [Agent 인증·보안](docs/SECURITY_AND_ENROLLMENT.md) | 설치 승인 및 자동 토큰 갱신 |
| [현행 운영](docs/OPERATIONS.md) | Docker/Naru/Agent 실행·장애 대응 |
| [마이그레이션/출시](docs/MIGRATION_AND_RELEASE.md) | DB 백업/이전/복구/컷오버 |
| [결정 기록](docs/DECISIONS.md) | 결정 및 폐기 설계 |
| [문서 인덱스](docs/README.md) | 문서 소유권 |

웹 빌드 및 라이선스: [frontend/README.md](frontend/README.md), [NanumSquare 라이선스](frontend/NANUMSQUARE-LICENSE.md).

## 로컬 검증

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -t . -p "test_*.py" -v
cd frontend
npm ci
npm run build
```

현행 운영 배포는 [OPERATIONS](docs/OPERATIONS.md) 참조. 운영 DB·Docker volume·비밀 키를 파괴하는 배포는 금지. 사용자 승인 이미지 **[Pixel Pig](branding/pig-terminal.png)**만 EXE/Tray/Installer의 시각 원본으로 사용한다.
