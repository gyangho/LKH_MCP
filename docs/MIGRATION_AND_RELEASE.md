# Docker → Native 이전·릴리스·되돌리기

**상태:** TO-BE. Installer 구현·승인 전에는 운영 데이터 변경 금지.

## 사전 기준선

Naru `mcp-data` 볼륨/SQLite WAL, `secrets/bootstrap.json`, 관리자 계정, Oracle 11g Thick client, Git/Codex 사용자 SID/세션, Cloudflare WARP/Portal private CIDR, Nginx 포트 8000/8001·portproxy/방화벽 현황을 기록한다. Agent 작업이 실행 중이면 신규 접수를 막고 종료/검증 후 시작.

## 컷오버 프로토콜 (I7에서 검증)

1. **승인:** 사전 점검 창과 운영 중단·백업·복원 담당자 확정(코드 push 승인과 별개).
2. **일관 백업:** SQLite Backup API 또는 승인된 WAL checkpoint로 일관성 확보; 활성 DB `*.sqlite3` 파일 단순 복사·Docker volume 삭제 금지. 백업 복원/암호화·접근 제어를 실제 시험한다.
3. **스테이징:** 원본 Docker DB를 건드리지 않는 **복제 DB**에서 Native 서비스 별도 포트/저권한 계정으로 실행; 두 백엔드가 한 DB를 동시에 쓰지 않는다.
4. **검증:** 설정/감사/Agent jobs/Graphify commit SHA/향후 지침·이벤트 데이터 건수와 샘플 해시, schema/version, Oracle SELECT-only, MCP/Admin 분리/Cloudflare private 정책, Windows 부팅/로그오프/Tray/Agent heartbeat/토큰 갱신.
5. **최종 이관:** 합의된 중단 시간에 Docker job 유입/쓰기 중단→최종 DB 백업→Native 실행→라우팅을 승인된 방법으로 변경. 보안 규칙·외부 접근 여부 재확인.
6. **관찰:** 승인된 기간 오류율·DB·모니터링·Windows 서비스·Agent 작업 확인. 오류가 발생하면 Native 중지→기존 라우팅/DB 스냅샷으로 Docker 복귀(이중 쓰기 금지).
7. **정리:** 운영 전환 승인 및 관찰 완료 **후에만** Naru의 이 MCP 관련 컨테이너/볼륨 정리 별도 결정. Oracle/다른 컨테이너 자동 제거 금지.

## 인수 테스트

| 영역 | 수락 시나리오 |
|---|---|
| Windows | 깨끗한 Win11 설치/업데이트/제거, UAC 취소, SCM 서비스/계정·ACL/재부팅·로그오프, 스케줄러 단일 Agent |
| 인증 | 설치 페어링, 관리자 rotation 뒤 Agent 자동 복구, 미등록/서명 위조/nonce replay 거절, 개인키 저장 분리 |
| Codex | 실제 MXC, SystemDrive, temp worktree/ACL cleanup, fix 승인, heartbeat/lease/kill/cancel, Graphify 해시 |
| 트레이 | 동일 Pixel Pig의 초록/핑크/회색·Busy/Error·툴팁·트레이만 종료 |
| DB | SQLite WAL 일관 백업/복원/롤백·audit/queue/instructions/event 누락·중복 점검 |
| 네트워크 | /mcp-only 8000, /admin-only 8001, WARP 허용/거부, 직접 backend 우회 차단 |
| 문서/Skill | 설치·장애·롤백 매뉴얼·Phase 9 LKH Development Skill |

## 릴리스 증거 템플릿

- [ ] SHA/버전, 서명·Installer 체크섬, 변경/삭제 파일 인벤토리
- [ ] Python/Frontend/현행 Gateway CI 및 Windows runner packaging/E2E 성공
- [ ] OS 서비스/트레이/Agent 실제 검증, 관리자 인증/보안 리뷰
- [ ] SQLite 백업·복구 및 Oracle/Cloudflare 실제 연결 검증
- [ ] 운영 cutover 승인과 네트워크/DB 전환 시각 및 실패 롤백 계획
- [ ] RELEASED 판정 근거·로그·감사 기록 및 Docker 폐기 별도 승인

구버전 SQLite 설정 행·감사 기록의 정리는 백업 후 별도 마이그레이션에서만 수행하고, 현재 기능 정리 과정에서 원본 운영 데이터와 볼륨을 직접 지우지 않는다.
