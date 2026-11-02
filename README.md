# LKH MCP

Windows 중심 MCP/관리 서버. Windows Native Service·Agent·Tray 및 unsigned 설치기 staging 코드가 있다. Native 대상 PC 검증과 운영 전환은 별도다.

## 기능 및 실행 상태

MCP와 React 관리자, Oracle 조회, SQLite 설정/작업 큐, Codex Agent 및 이벤트, 지침 관리, 로그·지표를 제공한다. Native 서버·서비스·트레이·설치기 및 같은 PC의 DPAPI 기반 Agent 등록이 구현되어 있으나 실제 Windows 환경과 운영 전환의 검증 상태는 각 증빙 문서를 확인한다.


## 공식 문서

[문서 인덱스](docs/README.md)에서 [기능 명세](docs/FEATURES.md), [아키텍처](docs/ARCHITECTURE.md), [빌드 및 설정·운영](docs/BUILD_AND_CONFIGURATION.md), [로드맵](docs/ROADMAP.md), [CI 및 검증](docs/VERIFICATION.md)을 확인한다.

## 폴더 구조

- `src/`: 서버, 인증, Native 서비스와 트레이 소스
- `windows_agent/`: Codex Agent 소스와 설정 예시
- `frontend/`, `branding/`: 관리자 UI와 원본 이미지
- `installer/`, `scripts/`: 설치기와 빌드·운영 스크립트
- `requirements/`: Python 런타임·빌드·Windows 의존성
- `tests/`, `docs/`: 회귀 테스트와 문서
- `contracts/`: 관리자 API의 기계 판독 계약

## 로컬 검증

```powershell
python -m pip install -r requirements/runtime.txt
python -m unittest discover -s tests -t . -p "test_*.py" -v
cd frontend
npm ci
npm run build
```

현행 운영 배포는 [빌드 및 설정](docs/BUILD_AND_CONFIGURATION.md) 참조. 운영 DB와 비밀 키를 보호한다. 사용자 승인 이미지 **[Pixel Pig](branding/pig-terminal.png)**만 EXE/Tray/Installer의 시각 원본으로 사용한다.
