# 공통 API·이벤트 계약 초안 v1.0

별도 [공유 제어 API 후보0.2](shared-control-api-candidate.md)는 집의 합성 참조 구현/JSON Schema이며 기존 C/D API를 대체하지 않는다. 소유자 권한·운영자 취소/기록 복구·불명확한 API 저널의 조건부 종결을 로컬 test client로만 검증한다. 운영 채택/인증/TLS/배포와 실장비 인수는 미완료다.

이 파일과 `contracts/*.schema.json`은 capstone 스켈레톤의 공통 계약 초안입니다. 프로젝트 주제는 해담시청으로 정해졌으며, 별도 포털 구현과 아래 스켈레톤의 구현 상태는 구분합니다. 동작 변경 시 관련 스키마·예시·테스트를 같은 PR에서 맞춥니다.

2026-10-19 해담시청 포털의 별도 구현 계약은 [PORTAL-API.md](haedam/PORTAL-API.md)와 `contracts/portal-event.schema.json`이다. React/Flask 별도 저장소에서 구현하며, 아래 기존 capstone 스켈레톤 경로의 구현 상태를 바꾸지 않는다. 포털 이벤트는 기존 v1.0 관제 소비자와 자동 호환되지 않는다.

2026-10-24 통합 대응·원복의 구현 인수 기준은 [기획서 보완본](../team_docs/기획서_보완본_2026-10-24.md#대응원복-연결의-인수-조건), 기존 포털/C 티켓/D 소비자와의 차이는 [보완 내역](../team_docs/2026-10-24-기획서-보완내역-B.md#2-계약소비자-대조)에 있다. 사건 묶기와 실제 조치 자원·요청/주기 식별을 분리하고, 활성 조치 조회·집행 위치별 원복·해제 뒤 새 조치를 함께 검증한다. 이 연결은 새 API 경로나 JSON 필드를 확정/구현한 계약 변경이 아니며 C/D의 스키마·예시·소비자 적용이 남아 있다.

## 현재 실행 가능한 경로

| 경로 | 상태 | 결과 |
| --- | --- | --- |
| `GET /` | 구현 | 개발 환경 확인용 시작 화면 |
| `GET /api/v1/health` | 구현 | 아래 상태 응답 |

```json
{"success": true, "data": {"service": "aleph-soar", "status": "ok", "stage": "scaffold"}}
```

`stage=scaffold`는 앱 프로세스와 라우트 실행 확인을 뜻합니다. DB·SIEM 연결이나 기능 준비 완료를 뜻하지 않습니다.

## 팀이 구현할 경로 — 현재 미구현

| 후보 경로 | 담당 역할 | 설계할 내용 |
| --- | --- | --- |
| `POST /api/v1/auth/login` | backend | 인증·세션·실패 응답·이벤트 발생 |
| `POST /api/v1/events` | detection + backend | 수집 인증·중복·지연·저장·실패 응답 |
| `GET /api/v1/incidents` | detection + dashboard | 조회 권한·필터·페이지·사건 응답 |
| `GET /api/v1/incidents/{id}` | detection + dashboard | 사건과 이벤트 타임라인 연결 |
| 대응·원복 API | backend + detection | 대상 제한·권한·재시도·사전 상태·복원 결과 |

위 경로는 기능 구현을 약속한 공개 API가 아닙니다. P01 작업에서 요청·응답·오류 예시를 먼저 확정합니다. 현재 구현되지 않은 경로는 404를 반환합니다.

## n8n 대응 호출 규칙

n8n이 해담시청 포털 대응 API(111 계정 잠금, 112 IP 차단)를 부를 때의 호출 쪽 규칙이다. 경로·요청·응답의 원본은 [PORTAL-API.md](haedam/PORTAL-API.md) "자동화 경계"이고, 둘이 다르면 PORTAL-API.md가 맞다. 근거는 [대응 호출 방식 초안](../team_docs/2026-10-20%20대응호출방식-초안-A-whiteclover0542.md)·[B 답변](../team_docs/2026-10-20%20대응호출방식-초안-답변-B-myeongjundev.md)과 10/21 확정(기획서 ④ 대응 호출 방식)이다. 포털 API는 backend에 구현돼 로컬 테스트를 통과했다. n8n에서는 조회(`GET /response/ips`)만 랩에서 확인했고(10/22), 차단·잠금 호출 시험은 아직 없다.

**인증.** 아래 두 조건을 모두 만족해야 한다. 하나라도 틀리면 403 `FORBIDDEN`이고, 어느 쪽에서 막혔는지는 알려 주지 않는다.

- 출발지가 포털의 `RESPONSE_ALLOWED_CIDRS` 안이다. 대상은 D n8n의 팀 VPN 주소 `10.250.0.100`이고, A 포털 VM의 값은 `10.250.0.100/32`다(10/26 A 확인: 이 밖의 출발지는 맞는 키로도 403). D 주소가 바뀌면 이 값도 같이 바꾼다. 포털은 연결 주소만 보고 `X-Forwarded-For`는 무시한다.
- 헤더 `X-Response-Key`가 포털의 `RESPONSE_API_KEY`와 같다. 키는 n8n 자격 증명과 포털 환경 변수에만 두고, 저장소·로그·티켓에는 남기지 않는다. 대상마다 다른 키를 쓴다.

**`Idempotency-Key`.** 모든 조치 요청에 붙인다(8~100자).

- 형식은 `{ticket_id}-{봇}-{대상}-{동작}`이다. 예: `T-20261024-0001-112-203.0.113.11-block`, `T-20261024-0001-111-zz_a1-lock`. `ticket_id`(`T-YYYYMMDD-순번4자리`)는 아래 [티켓 저장소](#티켓-저장소114--집-통합-후보)가 만든다.
- 같은 키로 다시 보내면 포털은 처음 응답 전체를 그대로 돌려준다. 그래서 해제한 뒤 같은 티켓에서 다시 차단하려면 키 끝에 회차를 붙여(`…-block-2`) 새 키를 쓴다.
- 포털은 경로와 관계없이 키 하나를 요청 하나에 묶는다. 같은 키를 다른 요청에 쓰면 409다.

**재시도.** 응답 대기 시간은 5초로 둔다.

| 응답 | n8n 처리 | 결과 기록 |
| --- | --- | --- |
| 200 `changed:true` | 반영 확인(아래)으로 진행 | `applied` |
| 200 `changed:false` | 이미 그 상태. 반영 확인으로 진행 | `already_applied` |
| 400 `VALIDATION_ERROR` | 재시도 안 함 | `failed` |
| 403 `FORBIDDEN` | 재시도 안 함. 인증 설정을 점검한다. 보호망 주소 차단과 관리자 계정 잠금도 403이다 | `rejected` |
| 404 `NOT_FOUND` | 재시도 안 함(없는 계정) | `failed` |
| 409 `CONFLICT` | 같은 키로 1회만 재시도. 같은 주소 요청이 동시에 겹친 경우는 이 재시도로 풀린다. 재시도도 409면 원인을 단정하지 않고 멈춘 뒤 포털 상태와 키 생성 규칙을 확인한다 | 재시도 결과, 다시 409면 `failed` |
| 5xx·5초 초과 | 같은 키로 1회만 재시도. 또 실패하면 멈춘다 | 재시도 결과, 실패면 `failed` |

**조치 경로.** 경로는 모두 `/api/v1` 아래다. 본문에 `ticket_id`·사유를 넣지 않고, 티켓 연결은 n8n이 티켓에 기록한다.

| 케이스 | n8n 호출 | 본문 | 비고 |
| --- | --- | --- | --- |
| S1·S8·S10·S12 (112) | `POST /response/ips/block` | `{ip}` | `minutes`는 보내지 않는다. 자동 만료 없이 담당자가 원복 단계에서 해제한다 |
| S4 (111) | `POST /response/accounts/lock` | `{username}` | S4 이벤트에는 username만 남으므로 username 경로를 쓴다. 계약 capstone #34(`68a2a94`)·구현 backend #3(`c0fc320`) 병합(10/27). 랩 포털 VM은 backend `9507fce`(#3·#4 포함)로 재배포됨(10/27 17:18). n8n에서 이 경로로 잠근 시험은 아직 없다(10/28 기준 관리자 화면 수동 잠금만 확인) |

**해제(원복)는 n8n이 자동으로 하지 않는다.** 사람이 확인한 뒤 실행하고, 결과를 티켓에 남긴다.

- IP 해제는 `POST /response/ips/unblock`이다. 케이스와 관계없이 그 IP의 차단을 풀기 때문에, 같은 IP를 막고 있는 다른 자리의 열린 티켓이 있으면 해제를 보류하고 사유를 티켓에 적는다.
- 계정 해제는 두 가지다(10/22 B 결정).
  - 탈취가 의심되거나 확인되면 `POST /response/accounts/{id}/reset`으로 비밀번호를 재설정한 뒤 푼다.
  - 오탐으로 확인되면 관리자 세션의 `POST /admin/users/{id}/unlock`(`reason_code=false_positive`)으로 비밀번호를 유지한 채 푼다. 계약은 capstone #45, 구현은 backend #4이며 둘 다 10/27 병합됐고 랩 포털 VM(`9507fce`)에 배포됐다. 관리자 화면에는 이 버튼이 아직 없어 화면에서는 재설정으로만 풀린다(10/28 확인).
  - `{id}`는 잠금 응답의 `user_id`다. 두 경우 모두 회수한 세션은 되살리지 않는다.

**효과 확인 2단계.** ①만 통과한 상태를 효과 확인 완료로 적지 않는다.

1. 반영 확인(n8n): IP는 `GET /response/ips` 목록에 들어 있는지, 계정은 잠금 응답의 `locked:true`와 `auth.account_locked` 이벤트로 확인한다.
2. 실제 효과(시험 스크립트, 기획서 ⑤ 5.4): 공격 출발지가 403을 받는지, 잠긴 계정이 로그인 거부되는지, 정상 출발지는 계속 동작하는지 확인한다.

**결과 기록.** 대상별 응답을 공통 결과 형식으로 바꿔 티켓에 쓰는 서브워크플로(`haedam-10`)는 D가 만든다. 기록 대상은 아래 [티켓 저장소](#티켓-저장소114--집-통합-후보) 계약(#50, 구현 #55)이다. 위 표의 결과 값(`applied`·`already_applied`·`failed`·`rejected`)은 record 요청의 조치 결과로, 해제는 `stage: released`로 쓴다.

## 티켓 저장소(114) — 집 통합 후보

C가 맡는 별도 서비스(`services/ticket-store`, C PC 컨테이너)이며 위 스켈레톤과 다른 앱입니다. #50/#55는 10/26 main 병합, C #59에는 D 인증 조회·쓰기 성공 기록이 있습니다. 이 집 브랜치는 C #62 위에 자원 조회·새 주기·D 오류/소비자 교정을 더한 미배포 후보입니다([최신 통합·학원 인수](home-integration-1027.md)). 설계·결정 근거는 [C 티켓 저장소 설계](C-티켓저장소-설계.md)입니다(2026-10-23 D 확인 반영, 구현 10/26·가동 10/29 전 목표).

| 경로 | 상태 | 부르는 쪽 | 인증·공개 범위(예정, 미시험) |
| --- | --- | --- | --- |
| `GET /api/v1/tickets/open?seat=&group_key=` 또는 `?target=` | 구현(로컬 시험) | D n8n check | `X-Response-Key`, `10.250.0.3:8088` |
| `GET /api/v1/tickets/active?asset_id=&via=&action=&target=` | 집 구현·격리 검증, 학원 미배포 | D 자원별 원복 보류 | `X-Response-Key`, 기존 8088 |
| `POST /api/v1/tickets/record` | 구현(로컬 시험) | D n8n record | `X-Response-Key` + `Idempotency-Key`, `10.250.0.3:8088` |
| `GET /api/v1/tickets` | 구현(로컬 시험) | C 보안 대시보드 | 키 없음, `127.0.0.1:8089` |
| `GET /api/v1/tickets/{ticket_id}` | 구현(로컬 시험) | C 보안 대시보드 | 키 없음, `127.0.0.1:8089` |
| `POST /api/v1/tickets/{ticket_id}/close` | 구현(로컬 시험) | C 보안 대시보드(사람) | 키 없음, `127.0.0.1:8089`, `Origin`·요청 토큰 확인 |
| `POST /api/v1/tickets/{ticket_id}/cancel` | 구현(로컬 시험) | C 보안 대시보드(사람) | 키 없음, `127.0.0.1:8089`, `Origin`·요청 토큰 확인. 8088에는 없음 |

스키마: [ticket.schema.json](../contracts/ticket.schema.json)(티켓·조치 한 줄), [ticket-record.schema.json](../contracts/ticket-record.schema.json)(record 요청 본문), [ticket-response.schema.json](../contracts/ticket-response.schema.json)(check·record·오류 응답)

- 열린 티켓은 `(seat, group_key)`마다 하나입니다. `group_key`는 A = `username`, B·D = `src_ip`, C = `{asset_id}:{file_key}`.
- `status`(`open → responding → verified → restored → closed`)는 저장소가 기록으로 정합니다. n8n은 `status`·`ticket_id`·`dedup_key`를 보내지 않습니다. `verified`는 `effect_verified = true`일 때만 됩니다.
- record 본문의 `stage`(`detected`/`applied`/`effect`/`released`)로 줄 추가·갱신을 정합니다. `effect`는 같은 `(bot, via, action, target)` 줄을 갱신하고, `released`는 해제 줄을 새로 남겨 같은 봇·경로·대상의 조치를 해제됨으로 봅니다. `via`가 다르면 다른 조치입니다(S10: 112 `portal`과 112 `pfsense`). check의 `applied_actions`·`active_actions`에는 `via`가 들어갑니다. 해제된 뒤 같은 대상을 다시 막으면(새 이벤트) 중복이 아니라 새 회차입니다: 이전 `restored` 티켓은 `closed`(`close_note`에 이유)로 닫히고 새 티켓이 `created: true`로 만들어집니다(같은 `event_ids`의 재전송은 `duplicate: true`). 상태가 뒤로 가는 경우는 없습니다. 일부만 해제되면 `restored`가 되지 않습니다. 효과 확인(`effect`)의 `effect_verified_at`이 대상 줄의 시각보다 앞서면 409 `STALE_EFFECT`입니다.
- 원복 보류: `GET /api/v1/tickets/open?target=<대상>`(다른 값과 함께 쓰지 않음)은 모든 자리의 실제 티켓 중 그 대상에 활성 조치가 남은 것만(닫힌 미해제 티켓 포함) 돌려줍니다. `group_key`가 자리마다 달라서(A = username, B·D = src_ip) `group_key` 조회로는 다른 자리 차단을 놓칩니다. `Idempotency-Key`(예: `{n8n 실행 ID}-{stage}`)는 재전송 중복 방지에만 쓰고, 저장소는 줄을 만든 요청의 키를 `action_id`로 남깁니다. 이 집 D 후보는 실제 대상 호출 전에 `detected` 기록 성공을 요구하며, 학원 D 게시본 채택은 별도 확인합니다.
- `bot`은 문자열(`"112"`, 사람 처리 `"manual"`), `via`는 `portal`/`wazuh-ar`/`pfsense`/`manual`입니다(10/23 D 확정).
- n8n 경로 응답은 `{"ok": true, "ticket_id", "created", "duplicate", "status"}`, 오류는 `{"ok": false, "error": {"code", "message"}}`입니다(10/23 D 확정, D haedam-10과 같은 모양). 포털 대응 API의 `{"success", "data"}`와 다릅니다. 대시보드 목록(`{"ok", "count", "items", "counts", "last_record_at"}`)과 상세·닫기(`{"ok", "ticket"}`)도 같은 `ok` 모양입니다.
- 오류 코드: 400 `VALIDATION_ERROR`(본문 64KB 초과는 413), 401 `UNAUTHORIZED`(n8n 키), 403 `FORBIDDEN`(닫기의 `Origin`·화면 토큰), 404 `NOT_FOUND`, 409 `IDEMPOTENCY_CONFLICT`·`STALE_EFFECT`(record) · `INVALID_TRANSITION`(record 자산/회차 불일치, 닫기·취소: 상태가 맞지 않거나, 닫기에서 해제되지 않은 조치가 남은 티켓, 취소에서 적용·실패 줄이 있는 티켓), 500 `SERVER_ERROR`. 예상하지 못한 오류도 HTML이 아니라 이 모양으로 돌려줍니다(n8n 재시도 분기가 읽을 수 있게).
- n8n check·record는 `data_origin: live` 티켓만 보고 바꿉니다. 샘플 티켓은 화면 확인용입니다.
- 이 집 D 후보의 저장소 재시도는 5xx·응답 없음에 같은 키·본문으로 1회입니다. 기본 노드 재시도는 껐고 4xx·형식 오류는 보류합니다. 학원 실제 n8n 동작은 재확인해야 합니다.
- 기존 [incident.schema.json](../contracts/incident.schema.json) v1.0은 바꾸지 않았습니다. 티켓은 `username`이 없는 사건(S7·S12)과 5단계 상태를 담아야 해서 별도 계약입니다.
- [contracts/ticket-examples](../contracts/ticket-examples)는 `data_origin: "sample"`인 합성 예시입니다. 실제 n8n 기록이나 탐지 결과가 아닙니다.

### 10/27 통합 후보의 자원·주기·시각

- `/open`은 사건 묶음 조회다. `/active`는 `asset_id, via, action, target` 네 값이 모두 맞는 모든 live 활성 조치를 반환한다. 샘플 제외, 다른 자리/묶음/봇·닫힌 미해제 티켓 포함. 불완전/중복/추가 쿼리는400, 인증 오류401, 저장소 실패500이다. 일치하는 resource와 완전한 tickets 빈 배열만 기록상0건이다. 읽기 스냅샷이며 원복 예약/권한이 아니다.
- 적용·효과 중복은 현재 활성 `(bot, via, action, target)`로 판정한다. 해제는 `unblock→block`, `unlock→lock`, `restore→quarantine`, 그 외 동일 동작 하나에 대응한다. 일치 없음400, 다른 활성 조치가 남으면 restored가 되지 않는다. 기존 PF `fw_block` 이력은 원문 보존 후 `block` 자원으로 읽고 새 소비자는 PF에도 `block`/해제 `unblock`을 쓴다.
- 활성 조치가 없는 restored에 새 이벤트의 `detected`가 오면 이전 회차를 close하고 새 open 티켓을 먼저 만든다. 새 이벤트의 직접 `applied`도 새 회차를 만들지만 D는 detected→대상 호출→applied 순서를 쓴다. 과거 이벤트가 섞인 탐지/적용 재전송은 원래 티켓·현재 상태·duplicate=true를 반환하며 새 회차에 합치지 않는다.
- 열린 티켓의 자산 변경과 restored에 남은 활성 조치는409 `INVALID_TRANSITION`이며 본문/키 저장도 롤백한다. 성공한 같은 키/본문 재전송은 최초 응답을 보존한다. D는 terminal/오류 응답뿐 아니라 restored 조회 뒤 이전 ticket_id를 돌려준 캐시 응답도 대상 호출 전에 중단한다. 멱등 응답은 현재 상태 조회가 아니다. D 주 대응은 record ACK 뒤 같은 seat/group을 `/open`으로 재조회해 ticket_id가 같고 비종료 상태인지 대조한 뒤 대상 입력으로 간다. 현재 조회 실패·부재·다른 회차·terminal이면 중단한다. 수동 close 뒤 조회0건인 경우의 과거 open 캐시도 차단하며 읽기→집행 경쟁을 잠그는 기능은 아니다.
- D가 받는 detected_at은 Graylog 이벤트 생성 시각이다. 없으면 null이며 n8n 현재 시각으로 대체하지 않는다. received_at은 n8n 입력 시각이다. condition_met_at과 함께 원본 시간대·정의/관측 근거를 보존한다.
- S7 group_key=`asset_id:file_key`, action.target=`file_key`다. S12 D→A VPN health200/본문 정상은 그 경로의 관측이며 외부 정상 경로와 실제 차단 효과 증거를 대신하지 않는다.

## 이벤트

스키마: [event.schema.json](../contracts/event.schema.json)

- `event_id`: 출처에서 안정적으로 부여하는 중복 확인 키
- `timestamp`: 시간대가 포함된 발생 시각; 수집 순서와 구분
- `source`, `event_type`: 이벤트 출처와 종류
- `username`, `asset_id`: 사건을 연결할 사용자·자산 후보 키
- `src_ip`: 출발지 정보; 단독으로 사용자를 동일시하지 않음
- `outcome`: 성공·실패·거부 결과
- `details`: 허용한 역할 변화·자원 이름만 기록. 비밀번호·토큰·원문 조회 결과는 제외

시간대·IP 형식 검증에는 JSON Schema의 format 검사가 필요합니다. 개발 의존성의 `jsonschema[format-nongpl]`과 검사할 형식을 명시한 `FormatChecker`를 사용해 날짜 검사 누락을 방지합니다. 소스별 이벤트 매핑, 수집 시각, 시간 순서·상관 조건, 익명 이벤트와 다중 테넌트 지원은 구현 전 결정합니다.

## 사건 화면 데이터

스키마: [incident.schema.json](../contracts/incident.schema.json)

사건은 `event_ids`로 원래 이벤트를 가리킵니다. `reason`은 의심 근거, `response_state`는 대응 결과입니다. 사건 생성·대응 성공·원복을 같은 상태로 처리하지 않습니다. 이 스키마는 응답 모양의 초안이며 탐지 로직을 제공하지 않습니다.

## 예시와 검증

[contracts/examples](../contracts/examples)의 4종 이벤트와 사건은 화면·계약 테스트를 위한 합성 데이터입니다. 실제 로그인·탐지·대응 결과가 아니며 임계값 검증용 데이터 세트도 아닙니다.

```powershell
python -m pytest tests/test_contracts.py -q
```
