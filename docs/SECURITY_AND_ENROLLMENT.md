# Agent 등록·보안·자격증명 설계

**상태:** AS-IS 인증 설명 + TO-BE 최초 등록(미구현), 2026-10-30

## 목표 / 보안 불변 조건

- 최종 제품에서는 관리자 토큰 재발급 때마다 Windows PowerShell 환경변수나 `token.json`을 수정하지 않는다.
- 미인증 Agent에 토큰을 내려주는 API **금지**. 서비스·장치 최초 등록은 신뢰 가능한 **Installer/로컬 관리자 승인**으로 시작한다.
- Windows Codex Agent는 일반 사용자 권한, MCP 서비스는 별도 저권한 서비스 계정. Agent가 서버 SQLite/Oracle 관리자·비밀정보를 직접 읽지 못한다.
- 임의 shell·임의 path/API·원격 force push/원본 checkout 자동 수정 금지. Codex는 SHA·repo allowlist·clean tree·임시 worktree·명시적 fix 승인.
- 비밀키와 Codex 로그인 사용자 자격증명은 GitHub/SQLite/서버 응답/로그에 원문 저장하지 않는다. 공개 관리 API 및 무제한 Docker socket 노출 금지.

## AS-IS (기존 운영, 자동 등록 기능 없음)

현재 Docker `secrets/bootstrap.json`의 `CODEX_AGENT_TOKEN`을 서버가 로드하고 Windows Agent는 `LKH_CODEX_AGENT_TOKEN` 환경변수로 같은 값을 전달받는다. TCP 8001의 private `/admin/agent/heartbeat|claim|complete`에 bearer 인증. 관리자 web은 Private Access + 패스워드/세션 + Origin/Host CSRF.
PR #5의 관리자 발급→Windows 로컬 token.json 수동 붙여넣기 방식은 **사용자 요구 미달로 PR #6에서 revert**되어 현재 존재하지 않는다.

## TO-BE: Windows 설치 시 기기 등록 (기본 동일 PC)

1. Installer가 관리자 승인 하에 Agent 실행 계정/Windows SID를 확인하고 **장치 전용 비공개 키쌍**을 생성한다. 비밀키는 Windows CNG 비내보내기 키(가능 시) 또는 적합한 Windows DPAPI/사용자 자격증명 보호 저장소에 보관; 일반 사용자의 다른 계정 접근 차단.
2. Windows Service는 관리자 승인된 로컬 IPC(ACL 제한 Named Pipe 후보)로 Agent ID, 공개키, OS 주체(SID), 등록 시각을 검증하여 SQLite에 등록. Agent ID만 알고 있다고 등록이 성립하지 않는다.
3. Agent는 실행 시 등록된 개인키로 서버 challenge nonce를 서명. 서버는 공개키/서명/nonce TTL/재생 여부/상태를 검증하고 **짧은 유효기간의 scoped access token**을 발급한다. 발급 토큰의 검증값·만료·scope·폐기 상태만 DB에 저장한다. 예시 TTL 15분은 구현 시 부하/보안 시험 후 확정.
4. Agent는 만료 전 자동 재인증/갱신. 관리자 UI에서 토큰·키 rotation/폐기 요청 시 기존 권한은 차단하고 Agent는 OS 보호 키로 새 토큰을 획득하므로 **수동 복사/환경변수 교체 0회**.
5. 개인키 손상·장치 교체·삭제/재설치로 정상 인증이 불가능하면 자동 무인 등록 금지; 로컬 관리자/1회 동의로 재등록·감사. 별도 기기로 분산할 경우 원격 mTLS/TLS와 승인된 pairing code가 필요하며 1차 범위 밖.

## 별도 Agent Supervisor 금지와 OS 제어

서비스는 `LKH-Codex-Agent` Task Scheduler **등록된 고정 작업**의 실행/중지/상태만 제어한다. Agent가 종료된 상태라도 Windows SCM Service는 살아 있어 시작할 수 있다. 일반 사용자에게 서비스 전역 관리자 권한·任意 PowerShell 허용 금지.

## 위협 모델 및 검증

| 위협/장애 | 대책/검증 |
|---|---|
| 무등록 PC/API | 401/403, 서명/공개키/SID 검증 |
| 토큰 replay/도청 | nonce one-time·TTL·scope·TLS 또는 로컬 IPC 보호, 금지 토큰 원문 로그 |
| 분실/폐기 후 사용 | 즉시 revoke, server restart 후에도 폐기 유지, 재등록 승인 |
| 여러 Agent 동일 ID | 장치 identity binding, 단일 작업 claim/lease·중복 인스턴스 거절 |
| 권한 상승/임의 실행 | 관리자 CSRF·작업 이름 allowlist·OS ACL·audit, 임의 command 미지원 |
| 프로세스/서버 오류 | 짧은 토큰 만료, 갱신 백오프, 서버 복구 후 재연결/무한 발급 차단 |
| Codex sandbox/파일 | MXC 호환성, 임시 worktree ACL cleanup 별도 보고, 원본 checkout 무변경 |

로그: actor/agent/action/time/status만 기록, token/password/private key/full Codex outputs 저장하지 않음. 보안·운영 변경(자격증명 교체, 서비스 중단, 방화벽/DB)은 별도 승인.
