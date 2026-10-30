# LKH MCP 설계 결정 기록

기준: 2026-10-30

| ID | 결정 | 상태/근거 |
|---|---|---|
| D01 | 기존 `branding/pig-terminal.png` Pixel Pig를 아이콘 정본으로 유지 | ADOPTED. 다른 돼지 일러스트로 변경 금지 |
| D02 | 현재 Naru Docker를 Native 검증·DB 이전까지 유지 | ADOPTED. 활성 포트/데이터 유지 |
| D03 | 최종 Windows Native Service + Task Scheduler Agent + 독립 Tray + 단일 Setup.exe | ADOPTED / TO-BE |
| D04 | 별도 상주 Agent Supervisor를 만들지 않음 | ADOPTED. 기존 Windows 스케줄러의 고정 작업만 관리 |
| D05 | 수동 PowerShell/JSON 토큰 재배포 없이 설치 승인 후 Agent 자동 인증·갱신 | ADOPTED / TO-BE. 무인증 token API는 금지 |
| D06 | PR #5 수동 token.json 전달 방식 폐기, PR #6으로 revert | REVERTED (2026-10-30) |
| D07 | 서버에 등록되지 않는 구형 Docker Codex Worker/직접 Git·Graphify 실행 API 제거 | ADOPTED. 기존 Windows Agent 경로 유지 |
| D08 | 핑크=Agent Offline, 초록=Online, 회색=판별 불가, 픽셀 돼지 공통 원본 | ADOPTED / TO-BE |
| D09 | 코드/문서의 완료와 실운영 배포·Windows E2E를 분리 | ADOPTED |
| D10 | GitHub commit/push/Agent 사용 승인은 진행 단계에 유효; 운영 DB·서비스·네트워크 변경 별도 승인 | ADOPTED |

## 미결정 및 게이트

- Windows 서비스 계정: virtual service account 대안/보안 경계 실기 검증 필요.
- 앱 라우팅: Nginx 제거 후에도 8000은 MCP만, 8001은 Admin만 접근되도록 동등성 검증.
- 기기 신뢰: Windows CNG 비내보내기 키 + ACL Named Pipe 제안; 구현/키 복구 검토 필요.
- 장치 간 원격 Agent는 1차 출시 범위 외. TLS/mTLS 별도 설계.
- 기존 Docker 데이터/작업/감사 삭제 및 최종 종료는 I7 승인 전 금지.
