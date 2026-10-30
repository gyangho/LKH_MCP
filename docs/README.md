# 공식 문서 인덱스

기준: 2026-10-30. 계획/구현/운영 상태를 혼용하지 않는다.

1. [DOCUMENTATION_POLICY](DOCUMENTATION_POLICY.md) — 관리·삭제 정책, 상태·증거 규칙
2. [ROADMAP](ROADMAP.md) — 구현 순서, I0–I7 및 Phase 0–9, 완료 기준
3. [ARCHITECTURE](ARCHITECTURE.md) — AS-IS Docker/Agent, TO-BE Windows Native
4. [WINDOWS_INSTALLER_DESIGN](WINDOWS_INSTALLER_DESIGN.md) — 설치·서비스·Task Scheduler·트레이 상세 설계
5. [SECURITY_AND_ENROLLMENT](SECURITY_AND_ENROLLMENT.md) — 인증, 최초 등록, 자동 토큰 갱신
6. [OPERATIONS](OPERATIONS.md) — 현행 Docker+Naru+Windows Agent 실제 운영
7. [MIGRATION_AND_RELEASE](MIGRATION_AND_RELEASE.md) — 보존·검증·롤백
8. [DECISIONS](DECISIONS.md) — ADR 및 폐기 이력

`frontend/README.md`는 UI 개발 전용, `frontend/NANUMSQUARE-LICENSE.md`는 제3자 라이선스 고지이며 제거 대상이 아니다.

폐기된 중복 문서:
- `docs/DOCKER_SQLITE_CODEX.md` → `OPERATIONS` + `ARCHITECTURE` + `SECURITY_AND_ENROLLMENT`로 통합.
- `docs/WINDOWS_CODEX_AGENT.md` → `OPERATIONS` + `ROADMAP` + `SECURITY_AND_ENROLLMENT`로 통합.
- 과거 장문 `README.md` → 링크 중심 진입점으로 교체.

과거 원본은 Git 이력에서 찾을 수 있으며 현재 정본으로 취급하지 않는다.
