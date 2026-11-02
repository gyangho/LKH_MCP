# 현재 기능 명세

기준: 2026-11-02 소스. 구현과 실제 운영 배포는 별도이며 검증 증거는 [CI 및 검증](VERIFICATION.md)을 따른다.

## 서버와 관리자

- MCP Streamable HTTP와 React 관리자 화면을 제공한다. Oracle 기능은 허용된 테이블에 대한 제한적 조회이며 접속 자격증명과 허용 목록이 필요하다. UI UX Pro Max 검색은 vendor 자산을 사용한다.
- 설정은 SQLite에 저장하고 허용된 비밀 설정은 bootstrap/환경에서 읽는다. 관리자 변경에는 세션, Origin/Host와 CSRF 검사를 사용한다. 세부 경로는 [빌드 및 설정](BUILD_AND_CONFIGURATION.md).
- Codex Agent는 heartbeat와 lease 기반 큐를 사용한다. 승인된 저장소, 정확한 SHA, clean checkout과 임시 worktree를 검사하며 verify·diagnose·graphify 및 승인된 fix 제안을 지원한다. 원본 checkout에 자동 commit/push하지 않는다. 실패한 비-fix 작업의 수동 재시도는 새 작업으로 생성한다.
- Codex 이벤트는 허용된 종류·단계·순서 등 메타데이터만 저장하며 관리자 화면에서 조회한다. 버퍼는 내구성이 없어 프로세스 종료 시 미전송 이벤트가 유실될 수 있다.
- 지침은 draft, 버전 이력, 발행·철회·롤백 및 revision 충돌 검사를 제공한다. MCP에는 발행된 지침만 제공하며 확인되지 않은 project/agent/tool 범위 조회는 fail closed다. 독립 승인자/RBAC는 완성되지 않았다.
- 운영 화면은 제한된 메타데이터 로그, 분 단위 지표, 큐·Agent 등 경고를 제공한다. 자동 외부 알림은 없다. 화면 필터는 로드된 결과 범위에서만 동작한다.

## Native Windows staging

- SCM 서비스가 서버를 실행하고 로그인 사용자의 고정 `LKH-Codex-Agent` 및 `LKH-MCP-Tray` 작업이 별도로 동작한다. 별도 Agent Supervisor는 없다. MCP와 Admin은 서로 다른 loopback 포트에서 경로를 제한한다.
- 설치 시 같은 PC의 machine-DPAPI 보호 장치 secret으로 Agent가 단기 토큰을 자동 획득한다. 이는 CNG 비내보내기 키나 challenge-response가 아니며 원격 등록용이 아니다.
- Pixel Pig 트레이는 서버 정상 및 최근 인증 heartbeat에 원본 컬러, Agent 오프라인에 흑백, 상태 불명에 회색을 표시한다. `종료`는 확인과 UAC를 거쳐 Agent와 서버를 종료하며 busy/상태 불명 시 차단한다.
- unsigned 설치기는 서비스·고정 작업·초기 관리자 설정·등록을 구성한다. 제거는 프로그램만, 기본 설정 제거(DB 보존), 전체 제거의 세 모드를 제공하며 전체 제거는 검증된 별도 SQLite 백업을 요구한다. Windows 실환경에서의 설치·제거 보장은 아직 검증되지 않았다.

## 보안 경계

Agent 장치 secret과 토큰 원문, 관리자 암호, Codex 원문 출력은 로그에 기록하지 않는다. 임의 원격 shell이나 임의 스케줄러 명령은 제공하지 않는다. Native Admin 및 등록 엔드포인트를 외부에 노출하려면 별도 보안 설계와 검토가 필요하다.

## Oracle 다중 연결 계약

`/admin/oracle`에서 연결 추가·수정·삭제·활성/비활성 및 저장된 연결 테스트를 제공한다. 수정과 삭제는 revision으로 동시 변경 충돌을 거부한다. 삭제는 저장된 정보만 제거하며 실제 Oracle DB를 변경하지 않는다. 암호 원문과 드라이버 오류는 응답·감사 기록에 포함하지 않는다.

| API | 계약 |
|---|---|
| `GET /admin/api/oracle/connections` | 암호를 제외한 관리자 연결 목록 |
| `POST /admin/api/oracle/connections` | 연결 생성 |
| `PUT /admin/api/oracle/connections/{id}` | 전체 항목·revision으로 수정, 빈 암호는 유지 |
| `DELETE /admin/api/oracle/connections/{id}` | revision으로 삭제 |
| `POST /admin/api/oracle/connections/{id}/test` | 빈 JSON으로 저장된 설정의 고정 DUAL 연결 시험 |

모든 API는 관리자 세션을 요구하며 변경과 테스트는 Origin/Host·CSRF 검사를 적용한다. 잘못된 입력은 400, 미인증 401, CSRF 403, 없는 연결 404, revision 충돌 409, 크기 초과 413, 연결·암호화·저장 실패는 비밀을 제거한 503 응답이다. 기계 판독 계약은 [OpenAPI](../contracts/admin.openapi.json).

MCP 연결 목록은 활성 연결 ID·이름만 제공한다. `oracle_select_dual(connection_id)`, `oracle_list_tables(connection_id, limit)`, `oracle_preview_table(connection_id, table_name, limit)`은 해당 연결의 계정과 허용 목록만 사용한다. SQL 직접 입력은 제공하지 않는다.

## 승인 저장소 목록 관리

환경 설정의 Git 메뉴에서 프로젝트 별칭과 GitHub `owner/repository`를 항목별로 추가·수정·삭제한다. 최대 10개이며 별칭은 유일해야 한다. 원격 URL이나 로컬 경로를 승인 대상으로 받지 않는다. Agent가 관리하는 별칭·저장소·로컬 checkout 설정과 서버의 승인 목록은 별개다.

| API | 계약 |
|---|---|
| `GET /admin/api/repositories` | 승인 목록 |
| `POST /admin/api/repositories` | alias·repository로 추가 |
| `PUT /admin/api/repositories/{id}` | alias·repository·revision으로 수정 |
| `DELETE /admin/api/repositories/{id}` | revision으로 승인 삭제 |

관리자 세션과 변경 시 Origin/Host·CSRF를 요구한다. 별칭 중복·최대 개수·실행 중 작업·동시 수정 충돌은 409로 거부한다. 변경·삭제는 같은 SQLite 트랜잭션에서 해당 별칭의 대기 작업을 취소한다. 큐 생성과 Agent claim 시점에도 정확한 저장소 승인 쌍을 다시 검사한다. 저장소 파일과 GitHub 원격에는 변경을 가하지 않는다.
