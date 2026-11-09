# C 티켓 저장소·보안 대시보드 설계 (114 티켓)

- 담당: C (shk12170-dev) · 작성: 2026-10-23 · 확인 상대: D (chacha1650a, n8n 대응 봇)
- 상태: **설계 완료·미구현.** 1~6절 작성. 계약 초안은 `contracts/ticket.schema.json`·`contracts/ticket-record.schema.json`·`contracts/ticket-examples/`(10/23, 계약 테스트만 통과). 저장소 코드는 아직 없다.
- 이 문서가 기준이다. PR #50의 [API 초안](../team_docs/2026-10-22%20티켓저장소-API-초안-C-shk12170-dev.md)과 통합 세션의 설계 초안을 10/23에 하나로 합쳤고, D 답변 두 번(설계 질문 답, PR #50 질문 1~11 답)을 반영했다. 두 답이 다르면 나중 답(PR #50)을 따랐다.
- 기준 자료: 기획서 합의본 ③-7(게시판 보안 대시보드, C PC Docker), 정량평가 `team_docs/정량평가-S7-shk12170-dev.md`, D result-log 설계(`team_docs/n8n-결과기록-서브워크플로-설계-D-chacha1650a.md`, D 브랜치), 포털 대응 API(A 초안 2절)
- 일정: 계약 10/24 → 구현 10/26 → **10/29 전 가동**(S12 기준선 10/29~11/01 잠정, 보강 후 첫 실행부터 티켓 필요)

```
[A·B·C·D 케이스] 공격 → Graylog 판정(D) → n8n 대응 봇(D) ── check·record ──▶ 티켓 저장소(C PC)
                                                                                   │
                                                          보안 대시보드(C PC 127.0.0.1) ◀┘
```

| 절 | 질문 | 상태 |
| --- | --- | --- |
| 1 | 티켓 한 장에 무엇을 적나 | 작성 |
| 2 | 상태는 어떻게 바뀌나 | 작성 |
| 3 | n8n이 어떻게 보내나(API) | 작성(D 답 2회 반영) |
| 4 | 어디에 어떻게 띄우나(포트·DB·접근 제한) | 작성(미시험) |
| 5 | 같은 사건이 두 번 오면(중복 방지) | 작성 |
| 6 | 화면에 무엇을 보여 주나 | 작성 |

## 0. 정한 것

| # | 결정 | 이유 |
| --- | --- | --- |
| 1 | 계약은 **새 스키마** `contracts/ticket.schema.json`로 둔다. 기존 `incident.schema.json`(v1.0)은 고치지 않는다 | 기존 사건 계약은 `username`이 필수이고 상태가 3개뿐이라 S7·S12 티켓과 5단계 흐름을 담지 못한다. 고치면 기존 예시·테스트가 같이 흔들린다 |
| 2 | 열린 티켓은 `(seat, group_key)`마다 하나. 열린 동안 들어오는 기록은 계속 덧붙인다 | D 동의(PR #50 1번). 30분 창으로 나누면 경계 처리가 늘고, S7 복구가 FIM 경보를 다시 내면 새 티켓이 생겨 같은 복구를 또 실행할 위험이 있다 |
| 3 | n8n 경로(check·record)만 VPN에 열고 키를 요구한다. 대시보드 경로는 127.0.0.1 전용, 키 없음 | D 제안과 같음. 브라우저에 키를 넣지 않는다 |
| 4 | 저장소·대시보드는 **C PC**에 둔다 | D 답(PR #50 8·9번): D PC는 OpenSearch가 2GiB 한도라 여유가 적다. 대시보드도 C PC |
| 5 | 키는 **하나**(티켓 저장소 키), 헤더 이름 `X-Response-Key`. 포털 대응 키와 다른 값 | D 요청(PR #50 10번). 전달은 디스코드 말고 직접 |
| 6 | `bot`은 문자열(예: `"112"`) | 사람이 직접 처리한 기록을 `"manual"`로 남겨야 해서 숫자로는 담을 수 없다 |
| 7 | `asset_id`는 `haedam-portal` | 포털 GELF와 S7 규칙이 쓰는 값. `haedam-portal-vm`은 Wazuh agent 이름(D 지적) |
| 8 | 응답 모양은 `{"ok", "ticket_id", "created", "duplicate", "status"}` | D 확정(10/23 2차). D haedam-10이 이미 이 모양이라 교체가 쉽다 |
| 9 | record 본문에 `stage`(`detected`/`applied`/`effect`/`released`)를 둔다. `Idempotency-Key`는 중복 방지에만 쓴다 | D 제안(10/23 2차). 키 끝 글자로 줄 갱신을 판단하면 키 형식이 조금만 달라도 잘못 판단한다 |

## 1. 티켓 항목

티켓만 보고 "무슨 일이, 왜, 언제, 어떻게 대응됐는지"를 설명할 수 있어야 한다. 정량평가의 MTTD·MTTR과 원복 시간을 티켓에서 바로 계산할 수 있게 시각을 남긴다.

### 1-1. 티켓

| 칸 | 필수 | 뜻·값 규칙 | S7 예시 |
| --- | --- | --- | --- |
| `ticket_id` | 저장소가 만듦 | `T-YYYYMMDD-<순번4자리>` | `"T-20261024-0001"` |
| `seat` | 예 | `A` / `B` / `C` / `D` | `"C"` |
| `case_id` | 예 | `S1` / `S4` / `S7` / `S8` / `S10` / `S12` | `"S7"` |
| `group_key` | 예 | 묶는 키. A = `username`, B·D = `src_ip`, C = `{asset_id}:{file_key}` | `"haedam-portal:assets/zz_s7_1024.txt"` |
| `title` | 예 | 케이스 이름 + 대상 | `"S7 홈페이지 변조: assets/zz_s7_1024.txt"` |
| `status` | 저장소가 정함 | 2절 | `"responding"` |
| `asset_id` | 예 | 자산 ID | `"haedam-portal"` |
| `src_ip` | 선택 | 공격 출발지 | `"203.0.113.10"` |
| `username` | 선택 | 관련 계정. 계정이 없는 사건(S7·S12)은 `null` | `null` |
| `event_ids` | 예(1개 이상) | 판정 근거 ID 목록. 새 근거는 뒤에 추가, 같은 값은 한 번만 | `["<Graylog 이벤트 ID>"]` |
| `reason` | 선택 | 판정 조건을 문장으로 | `"같은 자산·파일 키에서 FIM 추가(554)와 웹 접근 200이 10분 안에 발생"` |
| `first_attack_at` | 선택 | 첫 공격 시각. n8n이 모를 수 있어 시험 기록자가 채움 | |
| `condition_met_at` | 선택 | 조건 충족 시각(나중 신호) = Graylog 이벤트 `timestamp`. **MTTD 시작점** | |
| `detected_at` | 선택 | 판정 이벤트 생성 시각 = Graylog `timestamp_processing` | |
| `received_at` | 선택 | n8n이 판정을 받은 시각 | |
| `responded_at` · `verified_at` · `restored_at` | 저장소가 채움 | 첫 조치 완료(`finished_at`), 효과 확인(`effect_verified_at`), 원복 완료 시각 | |
| `actions` | 저장소가 쌓음 | 조치 기록 목록(1-2) | |
| `data_origin` | 저장소가 정함 | `live` / `sample`. 화면에서 샘플을 구분(workplan U01) | `"live"` |
| `created_at` · `updated_at` | 저장소가 채움 | | |

- 시각은 모두 ISO 8601, 시간대 포함(`+09:00`). 화면은 KST.
- **MTTD = `detected_at − condition_met_at`**, **MTTR = `verified_at − detected_at`**, 원복 소요 = `restored_at − verified_at`.
- 넣지 않는 것: 키, 비밀번호, 요청 본문 원문, 세션 값, 민원·파일 내용.

### 1-2. 조치 한 줄 (`actions`)

D result-log 설계의 출력 형식을 그대로 쓴다. `event_id`·`asset_id`·`src_ip`·`case_id`는 티켓 최상위로 옮기고, `dedup_key`는 받지 않는다(D 동의, PR #50 5번).

| 칸 | 뜻 | 예시 |
| --- | --- | --- |
| `bot` | 대응 봇 번호(문자열) 또는 `"manual"` | `"117"` |
| `target` | 조치 대상 | `"assets/zz_s7_1024.txt"` / `"203.0.113.11"` |
| `via` | 조치 경로. `portal` / `wazuh-ar` / `pfsense` / `manual` (D 확정, D 쪽 `app` → `portal`) | `"wazuh-ar"` |
| `action` | 한 일. `block` / `unlock` / `restore` / `quarantine` / … | `"restore"` |
| `result` | `applied` / `already_applied` / `failed` / `rejected` / `released` | `"applied"` |
| `applied_verified` | 조치가 실제 걸렸는지(차단 목록 조회 등) | `true` / `false` / `null` |
| `effect_verified` | 효과 확인 결과. 처음엔 `null` | `null` → `true` |
| `requested_at` · `finished_at` | 요청·완료 시각 | |
| `effect_verified_at` | 효과 확인 시각. **MTTR 끝점**(D 요청, PR #50 4번) | |
| `n8n_execution_id` | n8n 실행 ID | `"1234"` |
| `detail` | 설명(비밀값·파일 내용 없이) | `"원래 URL 404, 정상 화면 200"` |
| `action_id` | 저장소가 저장. 이 줄을 처음 만든 요청의 `Idempotency-Key` 값 | `"1234-applied"` |
| `duplicate` · `recorded_at` | 저장소가 채움 | |

## 2. 상태 흐름

`status`는 저장소가 기록 내용으로 정한다. n8n은 `status`를 보내지 않는다.

```
[open] ──조치 applied──▶ [responding] ──effect_verified=true──▶ [verified] ──released──▶ [restored] ──사람──▶ [closed]
```

| 기록 | `status` | 채우는 시각 |
| --- | --- | --- |
| 조치 없이 생성(탐지만) | `open` | `created_at` |
| `result = applied`·`already_applied` | `responding` | `responded_at` |
| `result = failed`·`rejected` | 그대로 | — (줄만 남김) |
| 같은 조치 줄의 `effect_verified = true` | `verified` | `verified_at` |
| 같은 조치 줄의 `effect_verified = false` | 그대로 | — |
| `result = released`(원복) | 남은 활성 조치가 없을 때만 `restored` | `restored_at` |
| 원복 뒤 새 이벤트 `detected` | 이전 티켓은 `closed`, **새 티켓**이 `open` | 새 티켓의 `created_at` |
| 원복 뒤 다시 `applied`(재차단, 새 이벤트) | 이전 티켓은 `closed`, **새 티켓**이 `responding` | 새 티켓의 `responded_at` |
| 사람이 닫음 | `closed` | — (닫기 경로는 6절과 함께 정함) |

- **`verified`는 `effect_verified = true`일 때만** 간다(`responding`에서만). `restored`는 `responding`·`verified`에서만 간다. 대응 API가 "성공"이라고 답한 것과 실제 효과(S7: 원본 해시·404, S12: 헬스체크 회복)가 확인된 것은 다르다.
- 상태는 앞으로만 간다. 뒤로 가는 예외는 없다. **재차단은 회차 분리**(10/27 B 결정): `restored` 티켓에 같은 대상을 다시 막는 `applied`(결과가 `applied`·`already_applied`)가 **새 이벤트**와 함께 오면, 같은 요청 안에서 이전 티켓을 `closed`(`close_note`: `재차단: 새 회차로 분리 (T-새번호)`)로 닫고 새 티켓을 만든다. 이전 회차의 줄은 그대로 남는다. 10/27 집 통합 후보는 D의 조치 전 기록 순서에 맞춰 새 이벤트의 `detected`에서도 새 open 티켓을 먼저 만든다(활성 조치가 남은 restored는409로 보류). 직접 applied 호환은 유지하지만 D는 detected→대상 호출→applied 순서다. 과거 `event_ids`가 섞인 탐지/적용 재전송은 원래 티켓과 현재 상태·`duplicate: true`를 돌려주며 새 회차에 합치지 않는다. 같은 키/본문의 캐시는 최초 응답을 보존하므로 현재 상태와 다를 수 있다. D는 restored 조회 뒤 이전 ticket_id를 받은 캐시도 대상 호출 전에 중단한다. `failed`·`rejected` 결과는 회차를 나누지 않는다.
- 늦게 온 효과 확인은 새 회차에 붙을 수 있으므로 `effect_verified_at`이 대상 줄의 시각보다 앞서면 409 `STALE_EFFECT`로 막는다(3-1 ②).
- 해제가 일부만 되면 `restored`로 가지 않는다. S10에서 `pfsense`만 풀고 `portal` 차단이 남아 있으면 `responding`이다.
- 해제 뒤 같은 `(bot, via, action, target)`을 다시 막으면 **중복이 아니라 새 조치**다. 중복은 아직 해제되지 않은(활성) 조치와 같을 때만이다.
- `closed` 전까지는 같은 `(seat, group_key)`의 기록이 이 티켓에 붙고, `closed` 뒤에 오면 새 티켓이 된다.

### 2-1. 이상한 경우

| 경우 | 처리 |
| --- | --- |
| ① 대응 실패 | `failed` 줄을 남기고 상태는 그대로. n8n이 다시 요청하거나, 수동 처리(C가 VM에서 복구 스크립트 실행, A가 기준본 복사)한 뒤 `bot: "manual"` 줄로 기록 |
| ② 효과 확인 실패 | `effect_verified = false`로 갱신, 상태는 `responding` 유지. 원인(기준본 오래됨, 경로 오류)을 `detail`에 남기고 ①처럼 처리 |
| ③ 오탐 | 조치를 되돌리고(`released`) `restored`. `reason` 끝에 `"오탐: <사유>"`. 정량평가 오탐 수에 넣음 |
| ④ 원복할 IP를 다른 자리도 막고 있음 | n8n이 `/active`의 정확한 자원으로 조회하고 자기 ticket_id 외의 활성 소유권이 있으면 해제를 보류한다. 같은 자리·다른 묶음·닫힌 미해제 티켓도 포함한다. 읽기 후 집행 경쟁은 별도 보호가 필요하다([집 후보](home-integration-1026.md)). |

- 정량평가 판정: C(대응·효과)는 `verified`까지, E(원복)는 `restored`까지 가야 통과로 센다.

## 3. API (n8n result-log ↔ C 저장소)

D의 공통 하위 워크플로(result-log, `haedam-10`)는 **check → 대응 호출 → record** 순서다(D 동의, PR #50 2번).

### 3-1. 경로

| # | 경로 | 부르는 쪽 | 키 | 열리는 곳 |
| --- | --- | --- | --- | --- |
| ① | `GET /api/v1/tickets/open?seat=&group_key=` | D n8n(check) | `X-Response-Key` | `10.250.0.3:8088` |
| ② | `POST /api/v1/tickets/record` | D n8n(record) | `X-Response-Key` + `Idempotency-Key` | `10.250.0.3:8088` |
| ③ | `GET /api/v1/tickets` | 대시보드 | 없음 | `127.0.0.1:8089` |
| ④ | `GET /api/v1/tickets/{ticket_id}` | 대시보드 | 없음 | `127.0.0.1:8089` |

**공통 응답 모양 (D 확정)** — D 임시 저장소(haedam-10)가 이미 쓰는 `ok` 모양이다. 포털 대응 API의 `{"success", "data"}`와 다르다. 계약: `contracts/ticket-response.schema.json`.

```json
{"ok": true, "ticket_id": "T-20261024-0001", "created": true, "duplicate": false, "status": "responding"}
{"ok": false, "error": {"code": "VALIDATION_ERROR", "message": "seat must be one of A, B, C, D"}}
```

**① check**

- `seat`를 주면: 그 자리의 열린 티켓 하나.

```json
{"ok": true, "exists": true, "ticket_id": "T-20261024-0001", "status": "responding",
 "applied_actions": [{"bot": "117", "action": "restore", "target": "assets/zz_s7_1024.txt", "result": "applied"}]}
```

  - 없으면 404가 아니라 200 + `{"ok": true, "exists": false, "ticket_id": null, "status": null, "applied_actions": []}`
  - `applied_actions`에는 `applied`·`already_applied`이면서 아직 `released`되지 않은 조치만 담는다. n8n은 같은 `(bot, via, action, target)`이 있으면 대응을 다시 부르지 않는다. 각 항목에 `via`가 들어 있다(10/26 추가).
- `seat`를 빼면: 모든 자리의 열린 티켓 중 이 `group_key`의 것.
- **원복 보류 확인은 `?target=<대상>`(단독)으로 한다.** 모든 자리의 열린 실제 티켓 중 그 대상에 아직 활성 조치가 있는 것만 돌려준다. A(S1)는 IP를 `group_key = username` 티켓에서 막기 때문에 `group_key`로 찾으면 다른 자리 차단을 놓친다(10/27 B 지적). 응답 모양은 `seat` 없는 check와 같다(`tickets[].active_actions`).

```json
{"ok": true, "tickets": [
  {"seat": "B", "ticket_id": "T-20261024-0002", "status": "responding",
   "active_actions": [{"bot": "112", "action": "block", "target": "203.0.113.11", "via": "pfsense"}]}]}
```

- `group_key`의 `:`·`/`는 URL 인코딩해서 보낸다. n8n Query Parameters 칸이 자동 인코딩하는지는 **미확인**(D, PR #50 7번). 안 되면 check를 POST 본문으로 바꾼다.

**② record**

```
X-Response-Key: <티켓 저장소 키>
Idempotency-Key: {n8n 실행 ID}-{stage}     중복 방지에만 씀(8~100자)
Content-Type: application/json
```

| `stage` | 언제 | `action` |
| --- | --- | --- |
| `detected` | 대응 전에 티켓만 먼저 만들 때(**쓸지 D 확인 중**) | `null` |
| `applied` | 대응 결과 기록 | 필수 |
| `effect` | 효과 확인 결과. 같은 `(bot, via, action, target)`의 **해제되지 않은 줄**만 갱신. 그 줄의 시각(`finished_at` → `requested_at` → 기록 시각)보다 `effect_verified_at`이 앞서면 이전 회차의 늦은 결과로 보고 409 `STALE_EFFECT`(아무것도 바꾸지 않음) | 필수, `effect_verified`가 `true`/`false` |
| `released` | 원복(해제) 결과 | 필수, `result = released` |

```json
{
  "seat": "D", "case_id": "S12", "group_key": "203.0.113.11", "stage": "applied",
  "title": "포털 요청 폭주로 응답 지연",
  "asset_id": "haedam-portal", "src_ip": "203.0.113.11", "username": null,
  "event_ids": ["<Graylog 이벤트 ID>"],
  "condition_met_at": "<ISO>", "detected_at": "<ISO>", "received_at": "<ISO>",
  "action": {
    "bot": "112", "target": "203.0.113.11", "via": "portal", "action": "block",
    "result": "applied", "applied_verified": true, "effect_verified": null,
    "requested_at": "2026-10-24T15:00:00+09:00", "finished_at": "2026-10-24T15:00:02+09:00",
    "effect_verified_at": null, "n8n_execution_id": "5678", "detail": "portal changed:true"
  }
}
```

- `action`은 `null`이어도 된다(탐지만 기록).
- 한 실행에서 record를 두 번 부른다(D, PR #50 3·4번): `stage: applied`(대응 결과) → `stage: effect`(효과 확인). `effect`는 **새 줄이 아니라 같은 `(bot, via, action, target)` 줄의 `effect_verified`·`effect_verified_at`을 갱신**한다. 줄 갱신은 `stage`로만 판단하고 키 모양은 보지 않는다.
- 응답: 새 티켓 201 `created: true`, 덧붙임 200 `created: false`, 같은 조치가 이미 applied면 200 `duplicate: true`(줄은 남김).
- S12 "요청 수만 초과(대응 없음)"에 record를 부를지는 **팀 확인 전**(D, PR #50 6번). 기본안은 부르지 않음.

**③ 목록·④ 상세** — 대시보드용. 목록은 `?status=open,responding&seat=C&case_id=S7&limit=50`, 결과 없음도 200 + 빈 목록. 상세는 티켓 전체(1-1)와 `actions`, 없는 번호는 404 `NOT_FOUND`.

### 3-2. 오류와 재시도

| HTTP | `code` | 뜻 | n8n |
| --- | --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 값 오류(`seat`·`case_id`·`group_key`·`stage`·`Idempotency-Key` 형식) | 재시도 안 함, 워크플로 오류로 기록 |
| 401 | `UNAUTHORIZED` | 키 없음·틀림 | 재시도 안 함, 설정 점검 |
| 404 | `NOT_FOUND` | 없는 티켓(④) | 해당 없음 |
| 409 | `IDEMPOTENCY_CONFLICT` | 같은 `Idempotency-Key`를 다른 본문에 씀 | 재시도 안 함(워크플로 오류) |
| 500·503 / 응답 없음(10초) | `SERVER_ERROR` | 저장소 문제 | **같은 키로** 최대 3회(2·4·8초) |

- 오류 `message`에는 틀린 칸 이름만 쓰고, 받은 값 전체나 키는 넣지 않는다. 400이면 본문을 저장하지 않는다.
- 재시도 규칙은 D 확정(10/23 2차). n8n HTTP 노드의 기본 재시도는 간격이 고정이고 400·401·409에도 재시도하므로(n8n 문서 기준, 미시험) **D가 오류 분기로 따로 만든다.** 최악이면 약 54초(시간 초과 10초 × 4번 + 대기 2·4·8초).
- 재시도해도 MTTR은 늘지 않는다. `finished_at`·`effect_verified_at`은 n8n이 보낸 값으로 채우고, 저장소가 받은 시각(`recorded_at`)은 MTTR 계산에 쓰지 않는다.

## 4. 배치 (C PC, 미시험)

| 항목 | 값 |
| --- | --- |
| 형태 | 컨테이너 하나(Flask + SQLite), compose 파일로 실행. 데이터는 이름 있는 볼륨 |
| n8n 포트 | `10.250.0.3:8088` → 컨테이너 8088. **① check·② record만** 응답, 나머지는 404 |
| 대시보드 포트 | `127.0.0.1:8089` → 컨테이너 8089. **③·④와 화면만** 응답 |
| 키 | 컨테이너 환경 변수(파일은 저장소에 커밋하지 않음). n8n 쪽은 자격 증명(Header Auth)에만 |
| 출발지 제한 | Windows 방화벽 인바운드 TCP 8088, 원격 주소 `10.250.0.100`만 + pfSense 규칙(B에게 D→C TCP 8088 요청) |
| 메모리 | 10/23 C 실행 중 컨테이너 합계 약 5.7 / 7.7GiB. 저장소는 100MB 안팎 예상(**미측정**, 가동 뒤 `docker stats`) |

- **포트를 둘로 나누는 이유:** Docker Desktop에서는 앱이 보는 출발지가 실제 PC 주소가 아니라 Docker 게이트웨이 주소일 수 있다(10/22 C→D 시험 때 D가 C 트래픽을 `172.23.0.1`로 봄). 그래서 앱이 출발지 IP로 경로를 나누지 않고, 공개 주소(VPN 주소 / 127.0.0.1)와 포트로 나눈다.
- 피한 포트: C에서 쓰는 1514·1515·3306·443·5678·9000·12201.
- **방화벽 주의(D 확인, 10/23):** D PC에는 Docker 백엔드(`com.docker.backend.exe`)의 수신 허용 규칙이 원격 주소 제한 없이 이미 있었다. C PC도 같으면 8088을 10.250.0.100만 허용하는 규칙을 만들어도 이 규칙 때문에 다른 주소가 들어올 수 있다. 첫 연결 시험 때 **허용하지 않은 주소에서 실제로 막히는지** 확인하고, 막히지 않으면 Docker 백엔드 규칙의 범위를 줄이거나 pfSense 규칙과 키에 기대는 것으로 기록한다.
- **VPN 주소 묶기(D 경험):** D Graylog가 10.250.0.100에 묶여 동작하므로 방식은 된다. 다만 VPN이 끊긴 상태에서는 컨테이너가 뜨지 않을 수 있고, 재생성 직후 `docker port`에는 보이는데 Windows에서 실제로 안 열린 적이 있다(재시작으로 해결). 띄운 뒤 `docker port`만 믿지 말고 D에서 실제 접속으로 확인한다.
- **미확인:** n8n 요청이 C에서 어떤 출발지로 보이는지. 첫 연결 시험 때 D와 같이 C 로그를 본다.

## 5. 중복 방지

| 순서 | 검사 | 같으면 |
| --- | --- | --- |
| 1 | 같은 `Idempotency-Key` | 처음 응답을 그대로 돌려줌(새 줄 없음). 본문이 다르면 409 |
| 2 | 같은 `(seat, group_key)`의 열린 티켓(`closed` 아님) | 새 티켓 대신 그 티켓에 덧붙임. 새 `event_ids`는 목록에 추가 |
| 3 | 같은 티켓 안에 같은 `(bot, via, action, target)`가 이미 applied | `stage: effect`면 그 줄 갱신, `applied`면 `duplicate: true` 줄로 남김. `released`는 해제 조치(예: `unblock`)를 새 줄로 남기고, 같은 봇·경로·대상의 applied 조치를 "해제됨"으로 봄. **`via`가 다르면 다른 조치다**: S10은 112가 `portal`(앱)과 `pfsense`(경계)로 같은 IP를 두 번 막고, 따로 해제한다(10/26 D 조치 줄 표에서 발견) |
| 4 | 열린 티켓이 없거나 `restored`인데, **같은 자리·같은 `group_key`**의 (닫힌 것을 포함한) 티켓에 이미 있는 `event_id` | 새 티켓을 만들지 않고 그 티켓을 `duplicate: true`로 돌려줌(같은 판정 재전송 대비, D 요청). 다른 자리는 같은 이벤트를 따로 기록할 수 있어서 범위를 좁힘(10/23 구현 시험에서 발견) |

- n8n 노드 재시도는 실행 ID가 같아 1에서 걸린다. 사람이 Retry execution을 누르면 새 실행 ID라서 3에서 걸린다(D 설명, n8n 문서 기준, **미시험**).
- 저장소가 마지막 방어선이다. n8n check가 먼저 막더라도 저장소에서 한 번 더 막는다.
- 1~4는 모두 `data_origin: live` 티켓에만 적용한다. 샘플을 켠 채로 시연해도 실제 기록이 샘플 티켓에 붙지 않는다(10/23 구현 시험에서 발견).

## 6. 화면 (보안 대시보드)

기획서 합의본 ③-7·428행: 티켓 목록과 상태(열림 → 대응 중 → 효과 확인 → 원복 → 종료)를 보여 주고 원본 이벤트로 갈 수 있게 한다. workplan U01 완료 조건: 사건·원본 이벤트·대응·원복 상태를 구분, 샘플/실제 연결 상태 표시, 빈 결과·실패·좁은 화면 확인. 꾸미기보다 **표 하나와 타임라인 하나**로 시작한다.

- 주소: `http://127.0.0.1:8089/` (C PC 브라우저에서만). 포털 관리자 메뉴의 링크도 이 주소이며, 포털 서버는 대시보드를 부르지 않는다.
- 화면은 저장소와 같은 컨테이너의 Flask 템플릿 + 작은 JS(10초마다 목록 다시 읽기). 외부 CDN 없이 정적 파일만 쓴다(관제망에서 인터넷이 안 될 수 있음).
- 시각은 KST로 보여 주고, 마우스를 올리면 원래 ISO 값을 보여 준다.

### 6-1. 목록 화면 `/`

| 영역 | 내용 |
| --- | --- |
| 머리 | 제목, **연결 상태 배지**(아래 6-3), 마지막 갱신 시각, 자동 갱신 켜기/끄기 |
| 요약 줄 | 상태별 열린 티켓 수(열림·대응 중·효과 확인·원복), 오늘 종료 수 |
| 필터 | 자리(A~D), 케이스(S1·S4·S7·S8·S10·S12), 상태(기본: `closed` 제외), 샘플 포함 여부 |
| 표 | 티켓 번호, 자리, 케이스, 제목, **상태 배지**, 대상(`group_key`), 마지막 조치 결과, MTTD, MTTR, 갱신 시각. 행을 누르면 상세로 |

- 상태 배지는 색과 **글자를 함께** 쓴다(색만으로 구분하지 않음): 열림 / 대응 중 / 효과 확인 / 원복 / 종료.
- 마지막 조치가 `failed`·`rejected`면 행에 "대응 실패" 표시를 붙인다(상태는 그대로, 2-1 ①).
- `data_origin = sample`인 행에는 "샘플" 표시를 붙인다. 샘플은 기본으로 숨긴다.
- MTTD·MTTR은 값이 없으면 `—`. 계산은 1-1의 식을 그대로 쓰고, 화면이 따로 계산 규칙을 만들지 않는다.

### 6-2. 상세 화면 `/tickets/{ticket_id}`

| 영역 | 내용 |
| --- | --- |
| 개요 | 자리·케이스·상태·자산·대상·출발지·계정(없으면 "계정 없음 사건"), 판정 근거(`reason`) |
| 시각 타임라인 | 첫 공격 → 조건 충족 → 판정 → n8n 수신 → 조치 완료 → 효과 확인 → 원복 → 종료. 빈 단계는 회색 "아직 없음". MTTD·MTTR·원복 소요를 단계 사이에 표시 |
| 조치 표 | `actions` 한 줄씩: 봇·경로·조치·대상·결과·적용 확인·효과 확인·요청·완료·효과 확인 시각·`n8n_execution_id`·`detail`. `duplicate` 줄은 흐리게 |
| 원본 이벤트 | `event_ids` 목록과 복사 버튼, Graylog 검색어 예시(`_id:<ID>`) |
| 닫기 | 상태가 `verified`·`restored`이고 해제되지 않은 조치가 없을 때만 "티켓 닫기" 버튼(6-4) |

- **원본 이벤트로 바로 이동하는 링크는 두지 않는다.** Graylog는 D PC의 127.0.0.1에서만 열리므로 C PC 브라우저에서 링크가 동작하지 않는다(합의본 258행). ID를 복사해서 D Graylog에서 찾는 방식으로 두고, 시연 때는 D 화면과 나란히 보여 준다.
- 사건(티켓)·원본 이벤트·대응 줄·원복을 서로 다른 영역으로 나눠서 U01 "구분" 조건을 지킨다.

### 6-3. 연결 상태·빈 결과·실패

| 경우 | 화면 |
| --- | --- |
| 티켓 0건 | "아직 티켓이 없습니다" + 마지막 record 수신 시각(없으면 "수신 기록 없음") |
| 목록 읽기 실패(저장소 오류) | 표를 지우지 않고 마지막 목록을 남긴 채 위에 "갱신 실패 HH:MM:SS" 경고 |
| n8n 기록이 한동안 없음 | 배지 "n8n 수신 없음 N분" (마지막 record 수신 시각 기준, 판정 오류가 아니라 정보) |
| 샘플만 있음 | 배지 "샘플 데이터" |
| 실제 기록 있음 | 배지 "실제 연결" + 마지막 수신 시각 |

- S12(포털 장애) 중에도 대시보드는 C PC에서 따로 돌기 때문에 계속 보여야 한다. 포털 상태를 대시보드가 확인하지는 않는다.

### 6-4. 사람이 하는 일: 티켓 닫기

- 경로: `POST /api/v1/tickets/{ticket_id}/close` (`127.0.0.1:8089`만, 키 없음). 본문 `{"note": "<닫는 이유, 200자 이내>"}`.
- `verified`·`restored`만 닫을 수 있다. 다른 상태면 409 `INVALID_TRANSITION`.
- **해제되지 않은 조치가 남아 있으면 `verified`도 닫을 수 없다**(409 `INVALID_TRANSITION`, "active action remains"). 닫힌 티켓이 켜진 차단을 가리지 않게 한다. 화면은 "해제 전에는 닫을 수 없습니다"를 보여 준다(문구는 B의 #67 템플릿이 맡고, 이 PR은 `active_action` 변수만 넘긴다). `?target=` 조회는 티켓이 닫혔어도 활성 조치가 있으면 돌려준다(이전 데이터 안전망).
- **다른 웹페이지가 몰래 닫기 요청을 보내지 못하게** `Origin`이 `http://127.0.0.1:8089`인 요청만 받고, 화면이 넣어 주는 요청 토큰을 확인한다(127.0.0.1 전용이어도 C PC 브라우저의 다른 탭은 같은 주소로 요청을 보낼 수 있다).
- 닫은 시각과 이유는 티켓에 남긴다(`closed_at`, `close_note`). 출처·토큰이 틀리면 403 `FORBIDDEN`.

### 6-4-1. 시험 티켓 취소 (서버 쪽, 버튼은 B)

n8n `dry_run`이 `detected`로 만든 "열림" 티켓은 닫기 조건(`verified`·`restored`)을 못 채워 계속 열려 있다. 그래서 **실제 대응이 없었다고 확인된 경우에만** 사람이 이유를 남기고 취소한다.

- 경로: `POST /api/v1/tickets/{ticket_id}/cancel` (`127.0.0.1:8089`만, 키 없음, `n8n` 8088에는 만들지 않는다). 닫기와 같은 `Origin`·`X-Dashboard-Token` 확인. 본문 `{"note": "..."}`, 1~195자(저장되는 `close_note`가 접두사 `[취소] `를 포함해 200자 이내여야 한다). 성공 응답은 닫기와 같은 `{"ok": true, "ticket": ...}`.
- 허용 조건: `data_origin = live`, `status = open`, 조치 줄 중 결과가 `applied`·`already_applied`·`failed`인 것이 없다(줄이 없거나 `rejected`만). `failed`는 대상이 반쯤 바뀌었을 수 있어 불확실로 본다. 아니면 409 `INVALID_TRANSITION`.
- 결과: `status = closed`, `closed_at`, `close_note = "[취소] " + 이유`. 조치 줄을 지우지 않고, 가짜 `effect`·`released`를 기록하지 않는다. 샘플 티켓은 취소할 수 없다.

### 6-5. 좁은 화면

- 폭 700px 아래에서는 표 대신 카드(티켓 번호·상태·케이스·제목·갱신 시각)로 바꾼다. 상세 타임라인은 세로로 쌓는다.
- 시험: 브라우저 폭 375px에서 가로 스크롤 없이 목록·상세를 볼 수 있는지 확인한다.

### 6-6. 대시보드 응답 모양 (계약: `contracts/ticket-response.schema.json`의 `list_ok`·`ticket_ok`)

n8n 경로와 같은 `ok` 모양을 쓴다.

```json
{"ok": true, "count": 1, "items": [{"ticket_id": "T-20261024-0001", "seat": "C", "case_id": "S7", "title": "…", "status": "verified",
  "group_key": "haedam-portal:assets/zz_s7_sample.txt", "last_result": "applied", "mttd_seconds": 8, "mttr_seconds": 50,
  "data_origin": "sample", "updated_at": "…"}],
 "last_record_at": "…"}
{"ok": true, "ticket": { …1-1의 티켓 전체… }}
```

### 6-7. 화면 시험 항목 (구현 완료 조건)

| # | 확인 | 기대 |
| --- | --- | --- |
| 1 | 티켓 0건 | 빈 화면 안내, 오류 없음 |
| 2 | 샘플 티켓만 | "샘플 데이터" 배지, 기본 필터에서 숨김 |
| 3 | 상태 5가지 티켓 | 배지 글자·색 구분, 종료는 기본 필터에서 숨김 |
| 4 | 대응 실패 줄이 있는 티켓 | "대응 실패" 표시, 상태는 그대로 |
| 5 | 저장소 중지 후 자동 갱신 | 마지막 목록 유지 + 갱신 실패 경고 |
| 6 | 닫기: `verified` / `responding` | 닫힘 / 409, 화면에 이유 표시 |
| 6-1 | 닫기: `verified`인데 차단이 아직 해제되지 않음 | 409, "해제 전에는 닫을 수 없습니다" 표시 |
| 6-2 | 취소: 조치 없는 `open` 실제 티켓 / 적용·실패 줄이 있거나 `open`이 아니거나 샘플 | 닫힘(`[취소] ` 접두사) / 409 |
| 7 | 다른 Origin에서 닫기 요청 | 거부 |
| 8 | 폭 375px | 가로 스크롤 없음 |
| 9 | 8089를 VPN 주소에서 접속 | 연결 안 됨(127.0.0.1 전용) |

## 미확인·남은 확인

| 항목 | 누구 |
| --- | --- |
| `stage: detected`(대응 전 티켓 먼저 생성)를 쓸지 | D(n8n 흐름 다시 보고 알려 줌) |
| S12 "요청 수만 초과" record 여부 | 팀(D 기본안: 안 부름) |
| n8n query 인코딩, 실행 ID 동작, 오류 분기 재시도 | D(구현 뒤 시험) |
| VPN 주소 공개·방화벽(Docker 백엔드 규칙)·출발지 | C·D(첫 연결 시험), B(pfSense D→C TCP 8088, D가 요청) |
| 저장소 메모리 | C(가동 뒤 측정) |

## 10/26 집 통합 후보의 추가 규칙

[API-CONTRACT의 자원·주기·시각](API-CONTRACT.md#1026-집-후보의-자원주기시각)과 [인수 안내](home-integration-1026.md)가 이 브랜치의 추가 기준이다. `/open`의 같은 group_key 전체 조회는 원복 보류를 완전히 보장하지 않는다. `/active`는 자산/경로/적용 동작/대상을 모두 요구하며 봇·자리·묶음을 넘어서 조회한다. restored 재적용은409 후 기존 티켓 close/새 주기로 처리하고, 효과/해제는 현재 활성 줄에만 연결한다. 현재 D 후보는 명시적 오류 분기 1회 재시도이며 위 3-2의 과거 최대3회 계획과 구분한다. 이번 구현의 실장비 채택·배치는 미확인이다.
