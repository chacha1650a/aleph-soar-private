# 공유 제어 API 계약·로컬 참조 구현 · 후보0.2

사람 담당 B(집 구현/검증)·C/D(채택/운영 연결). **소유자 범위·운영자 복구 권한을 확인하는 로컬 참조 API**다. [공유 반납 정책 후보](shared-release-candidate.md)를 감싸며 기존 C API를 교체하지 않는다. 앱 팩터리/Flask test client만 구현했고 서버 포트·실대상 연결·n8n 배포는 없다. 모든 응답은 `synthetic_only:true`, `allow_target_call:false`다.

## 계약과 소비자

[JSON Schema](../contracts/candidate-shared-control.schema.json)와 [합성 예시](../contracts/candidate-shared-control-examples.json)를 함께 사용한다. 요청 본문에는 caller/seat/role/token을 넣지 않는다. 서버가 주입한 자격 증명 설정의 `Principal(identity, role, seats)`와 C의 실제 티켓/적용 action 행을 대조한다. ticket/action ID 자체는 인증이 아니다.

| 메서드·후보 경로 | 권한·입력 | 결과 |
| --- | --- | --- |
| POST `/candidate/v1/shared/intents` | owner. operation=withdraw/retain·자원4개·ticket_id·action_id | 논리 반납/유지 또는 마지막 모의 해제. 본문의 자리 위조/추가 필드 거부 |
| GET `/candidate/v1/shared/plans/{plan_id}` | recovery 또는 계획에 자기 허용 자리의 claim이 있는 owner | 상태·자원·소유권 수만. 타인의 원문/티켓/행 목록은 반환 안 함 |
| POST `/candidate/v1/shared/plans/{plan_id}/cancel` | recovery. executor_stopped=true·synthetic/ 증적 참조 | **모의 대상 미반영 증명 가능**한 준비 계획만 취소. 논리 소유권을 active로 복원하고 원래 ID는 소비 이력으로 보존 |
| POST `/candidate/v1/shared/plans/{plan_id}/repair` | recovery. 위와 같은 확인 입력 | 반영된 모의 해제의 영수증/현재 상태 확인 후 C 기록만 복구. 대상 재호출 없음 |
| GET `/candidate/v1/shared/requests/status` | 인증된 호출자의 자기 요청 키 | API journal_pending/journal_done·원래 응답 상태/계획ID. 실제 효과 완료 판정은 아님 |
| GET `/candidate/v1/shared/journals/{journal_id}` | recovery | 원래 작업/계획 상태 대조, revision·review_hash·조건부 종결 가능 여부 |
| POST `/candidate/v1/shared/journals/{journal_id}/resolve` | recovery. 종료 확인·증적·expected_revision·review_hash·새 요청 키 | 원래 작업을 재실행하지 않고 응답 불명확 저널만 종결. 원래 키는409 OPERATOR_RESOLVED로 소비 유지 |

`X-Control-Key`는 이 후보의 별도 헤더이며, 기존 C `X-Response-Key`와 혼용하지 않는다. 실제 자격 증명/발급·폐기/배포·TLS 방식은 **확인 필요**다. 참조 구현은 테스트에서만 합성 키→Principal 설정을 주입한다. 동일 identity에 다른 자리/역할 설정을 중복 주입하면 초기화를 거부한다. 운영자가 서버 설정으로 D에 다른 자리의 위임을 허용할지는 C/D가 별도로 결정한다.

변경 요청은 `Idempotency-Key`(ASCII ID 문자8~40자)가 필수다. 요청 키는 **인증된 identity별 범위**이며, 실제 gate ID는 서버가 해시로 파생한다. 같은 호출자·키·경로·본문은 저장된 응답을 반환한다. 다른 본문/동작/계획에 키를 재사용하면409다. 같은 키라도 다른 호출자는 서버 권한을 따로 확인한다. 요청 키를 URL에 넣지 않으며 status 조회에도 헤더로 보낸다.

## 취소와 복구의 경계

- 취소는 이전 실행 종료 확인, 원래 예약 pending, 원래 고정 계획, **정확한 SQLite 모의 ledger에 영수증 없음**, 현재 모의 차단 유지, C 활성 소유권 집합 일치를 확인한 뒤에만 가능하다. 실제 제품의 조회0/시간 초과가 같은 미반영 증명이라는 뜻은 아니다.
- 영수증이 있거나 모의 해제가 반영됐으면 취소409이며 기록 복구로 분기한다. 완료 계획도 취소할 수 없다. 모의 해제 뒤 일부 C 기록/장부 완료/예약 완료 사이 장애에서도 같은 물리 요청ID를 다시 호출하지 않는다.
- 취소한 계획은 cancelled로 보존하며 claims를 active로 돌린다. 원래 반납 요청ID를 되살리지 않으며, 다시 반납하려면 새 요청 키를 사용한다. 취소 도중 장부/예약 정리가 불명확하면 상태를 조회한 뒤 별도 운영자 복구 시도로 대조한다. 자동 재실행은 없다.
- executor_stopped와 증적 참조는 운영자 선언이다. 실제 실행 종료를 이 API가 강제로 증명/종료하지 않는다. 이전 실행이 다시 진행할 수 있으면 취소/복구를 호출하면 안 된다. 실대상은 별도 실행 중단/펜싱·영수증 보장 계약이 필요하다.

## 오류·감사와 미완료 요청

401은 인증 실패, 403은 권한/소유권 범위 거부, 400은 잘못된 JSON/계약/키, 413은8KiB 초과, 404는 계획/자기 journal 없음, 409는 키/본문 충돌·보류·API 결과 대조 필요, 500은 내부/감사 저장 오류다. 중복 JSON 키·NaN·잘못된 UTF-8도 거부한다. HTML이나 예외 원문으로 응답하지 않는다.

`ControlAudit`는 서버 identity·정규 endpoint명·응답 상태/코드·UTC 시각을 기록한다. 변경 전 API journal을 pending으로 저장하고 요청 본문/키는 해시만 보존한다. 원문 claim/인증 토큰을 감사 로그에 쓰지 않는다. 작업 결과가 불명확하면 journal을 자동 재실행하지 않고 `RECONCILIATION_REQUIRED`로 보류한다. 감사 저장이 불가능하면 성공 ACK를 반환하지 않는다. journal_done은 API 응답 저장 완료이며 `pending` 작업의 실제 효과 완료를 뜻하지 않는다.

API journal의 **조건부 종결**을 추가했다. 원래 작업의 gate가 done이고 관련 계획이 없거나 completed/cancelled일 때만 운영자 대조 후보가 된다. 원래 작업이 pending이면 기존 계획 취소/기록 복구가 먼저다. 실행 흔적이 없는 not_seen은 ‘미호출0건’으로 추정하지 않고 보류한다. 종결은 API 응답 불명확 상태를 닫는 것이며 C/장부/대상 상태를 바꾸거나 성공 ACK를 새로 만드는 작업이 아니다.

조회 결과의 revision과 review_hash를 서버가 다시 확인한다. 늦은 ACK나 계획 복구로 상태가 바뀌면409 STALE_REVIEW다. 저널 종결·원래 키 소비 유지·운영자 증적 참조/감사 이벤트를 한 트랜잭션으로 저장하며 실패하면 모두 rollback한다. 같은 운영자 종결 키는 결과 replay, 다른 본문/저널 재사용은409이고 기존 변경 요청과 종결 요청의 키 공간도 분리하지 않는다. 종결 뒤 원래 요청은 재실행되지 않고409 OPERATOR_RESOLVED를 반환한다.

종결 API는 이전 실행 종료를 독립적으로 증명하지 않는다. 실제 실행 종료/권한 검증이 없는 운영 환경에서 강제로 호출하면 안 된다. 아무 작업 흔적이 없는 저널의 폐기·운영 DB 이행·감사 변조 방지/보존은 여전히 미구현이다. 실제 장비 상태를 재검증한 것으로 표시하지 않는다.

D 소비자는 후보 DTO를 기존 haedam-16의 C 조회 응답으로 직접 넣지 않는다. withdraw/retain/계획 상태와 C의 물리 조치/효과 기록을 나눈다. 200 withdrawn_waiting/retained는 반납/유지 ACK, 202 pending은 계획 조회/운영자 대조 대상이다. 409 RECONCILIATION_REQUIRED·500의 불명확한 결과는 자기 requests/status에서 journal_id를 얻고 대상 호출을 반복하지 않는다. OPERATOR_RESOLVED는 원래 키가 소비됐다는 뜻이며 새 키로 같은 조치를 강행하라는 지시가 아니다. 401/403/400은 자격 증명/권한/본문 수정 대상이다. 취소/복구/종결의 새 시도는 운영자 검토 후 별도 요청 키를 쓰되 원래 계획/물리 요청ID는 유지한다.

## 재현과 채택 조건

```powershell
python -m pytest tests/test_control_resolution.py tests/test_shared_control_api.py tests/test_shared_claims.py tests/test_contracts.py -q
python tools/rehearse_control_api.py --ticket-source .local/ticket-pr55-final-20261024 --output .local/control-api-new
```

고정 C PR55 패치 체크아웃과 개발 .venv/Node가 필요하다. 리허설은 기본6+공유정책6+API9 **총21종**을 임시 DB·합성 키·로컬 Flask test client로 실행한다. 기존 API5종에 작업 완료 후 응답 유실 종결·작업 pending의 복구 선행/새 조회·실행 흔적 없음의 보류·늦은 ACK의 stale 조회 거부4종을 추가했다. 실제 네트워크 서버·n8n·장비를 기동하지 않으며 기존 output을 덮어쓰지 않는다.

구현: [API 팩터리](../tools/shared_control_api.py), [감사/journal](../tools/control_audit.py), [리허설](../tools/rehearse_control_api.py), [종결 회귀](../tests/test_control_resolution.py). ClaimBook은 v2이며 감사/journal DB도 **v2**로 올려 관련 작업 참조·revision·종결 감사를 추가했다. 이전 후보 v1 DB는 자동 변환하지 않고 거부한다. 과거 v1에는 관련 작업 참조가 없어 임의 보충하지 않는다. C 운영 DB는 변경하지 않았고 데이터 이행/롤백은 C/D 채택 작업이다. API 계약 URN은0.2이며 기존0.1 소비자의 추가 응답 필드 검증도 조정해야 한다.

과거0.1의17종 [합성 증적](capstone/evidence/control-api-candidate-20261024/report.md)은 이전 구현의 이력으로 보존한다.0.2의21종 보고서는 새 출력 폴더에 생성하며 실제 키/타인 claim 원문 없이 실제 장비0·n8n 미검증을 명시한다.

0.2 직접 실행 결과: [21종 요약](capstone/evidence/control-journal-candidate-20261024/report.md), [JSON·실행 코드 해시](capstone/evidence/control-journal-candidate-20261024/report.json), [manifest](capstone/evidence/control-journal-candidate-20261024/manifest.json). 원본 합성 출력과 바이트가 같으며 운영 완료 증적이 아니다.

C/D는 실제 권한 발급/위임, 정책/경로 채택, 운영 API 서버 위치/통신 보호, 모든 적용/중복 생략/반납/유지 경로의 동일 조율 참여, 실제 대상의 멱등성/상태 확인과 현장 효과·정상 접근·원복을 확정·검증해야 한다. 기존 C/D 서비스와 전역 모델/권한 설정·학원 방화벽/VPN은 변경하지 않았다.
