# n8n 공통 "결과 기록" 서브워크플로 설계 (D · chacha1650a)

- 상태: **설계 초안.** 이 문서 작성 시점에는 n8n에 만든 워크플로가 없었다. 이후 초안 `haedam-10`(PR #43, 티켓 저장소는 워크플로 정적 데이터 자리표시)이 만들어졌고 티켓 저장소 API 확정 뒤 교체한다. 작업은 10/24부터(대응 호출 방식 초안 6절 5번 "D 수락 대기").
- 근거: [대응 호출 방식 초안 5절](2026-10-20%20대응호출방식-초안-A-whiteclover0542.md)의 공통 결과 형식, B→D 인수인계(10/22) 6절 1번. 계약(`contracts/`)은 바꾸지 않는다.

## 역할

각 케이스 워크플로(S1·S4·S7·S8·S10·S12)가 차단·잠금·복구를 호출한 뒤, **결과를 한 모양으로 바꿔 티켓 저장소(114)에 넣는 공통 하위 워크플로**다. 호출 노드와 "대상 응답 → `result` 대응표"는 B·C가 넘기고, 변환·중복 방지·기록은 D가 맡는다.

```text
[케이스 워크플로] --Execute Workflow--> [result-log] --HTTP--> 티켓 저장소(C, 계약 10/24 예정)
```

## 입력 (호출하는 쪽이 넘기는 값)

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `event_id` | 예 | Graylog/포털 **원본 이벤트의 ID. 바꾸거나 새로 만들지 않고 그대로 유지** |
| `asset_id` | 예 | 원본 값 유지(GELF `host`가 아닌 `_asset_id` 기준인지는 실제 수신 뒤 확인) |
| `src_ip` | 예 | 원본 출발지. n8n이 본 발신 주소로 바꾸지 않는다 |
| `case_id` | 예 | 예 `S12` |
| `bot` | 예 | 111·112·113·114·116·117 |
| `target` | 예 | 차단 IP, 잠금 계정 등 |
| `via` | 예 | `portal` / `pfsense` / `wazuh` |
| `action` | 예 | `block` / `unblock` / `lock` / `reset` / `restore` / `none` |
| `raw_status`, `raw_body` | 아니오 | 대상 응답 상태 코드·`changed` 등. 키·헤더·요청 본문은 받지 않는다 |
| `requested_at` | 예 | 조치 요청 시각 |

## 출력 (티켓에 남기는 결과, 초안 5절 형식)

```json
{"event_id": "...", "asset_id": "...", "src_ip": "...", "case_id": "S12",
 "bot": 112, "target": "...", "via": "portal", "action": "block",
 "result": "applied", "applied_verified": true, "effect_verified": null,
 "requested_at": "...", "finished_at": "...", "n8n_execution_id": "...",
 "dedup_key": "...", "detail": "..."}
```

- `result`: `applied` / `already_applied` / `failed` / `rejected` / `released` (포털 200 `changed:true` → `applied`, `changed:false` → `already_applied`, 403 자기 차단 방지 → `rejected`, 5xx·시간 초과 후 재시도 실패 → `failed`).
- `effect_verified`: S12는 n8n이 헬스체크로 직접 재므로 회복 확인 단계에서 채운다. 그 전에는 `null`이며 `applied_verified`만 통과한 상태를 "효과 확인 완료"로 쓰지 않는다.
- `incident.schema.json`의 `response_state`와의 대응은 계약 변경(PROGRESS 1-3) 때 같이 맞춘다. 지금 맞추지 않는다.

## 중복 방지

중복 입력(Graylog 재전송, n8n 재시도, 사람이 다시 누름)이 **중복 조치·중복 티켓**을 만들지 않게 한다.

| 규칙 | 내용 |
| --- | --- |
| 키 | `dedup_key = {case_id}-{src_ip}-{bot}-{action}` (같은 자리·같은 출발지의 같은 조치). 포털 `Idempotency-Key`는 별도로 `{ticket_id}-{봇}-{대상}-{block\|unblock}`(A가 API-CONTRACT에 확정 예정)를 쓴다 |
| 조회 | 기록 전에 같은 `dedup_key`의 **열린 티켓**을 조회. 있으면 새 티켓 대신 그 티켓에 실행 결과 한 줄을 덧붙이고 `result`에 `duplicate=true` 표시 |
| 조치 | 같은 티켓에서 이미 `applied`인 조치는 다시 호출하지 않는다(호출 쪽 워크플로가 이 서브워크플로의 조회 결과를 먼저 받는다: 모드 `check` → 호출 → 모드 `record`) |
| 원복 | `unblock`은 `dedup_key`가 다르고, 같은 IP를 막은 다른 자리의 열린 티켓이 있으면 해제 보류(A 초안 "해제 범위") |
| 저장소 | 이 서브워크플로는 자체 상태를 두지 않는다. 열린 티켓 조회는 티켓 저장소 API에 의존하므로 **그 API가 정해지기 전에는 중복 방지가 검증되지 않는다**(아래 질문) |

## 호출 모드 두 개

1. `check`: 입력의 `dedup_key`로 열린 티켓을 조회해 `{exists, ticket_id, already_applied}`를 돌려준다.
2. `record`: 위 출력 형식으로 티켓 생성 또는 추가 기록 후 `{ticket_id, created}`를 돌려준다.

## 기록하지 않는 것

비밀번호·`X-Response-Key`·토큰·요청 본문·세션 값. 자격 증명은 n8n 자격 증명에만 둔다. 원본 이벤트에 개인정보가 있으면 `src_ip`·`event_id`·`asset_id`만 옮긴다.

## 시험 계획 (만든 뒤)

| 시험 | 기대 |
| --- | --- |
| 같은 payload 2회 | 티켓 1건, 두 번째 실행은 `duplicate=true`, 대상 호출 1회 |
| `event_id`·`asset_id`·`src_ip` 대조 | 입력과 티켓 값이 문자열 그대로 같음 |
| 대상 5xx → 재시도 실패 | `result: failed`, 티켓 생성, 키 없음 |
| 자기 차단 방지 403 | `result: rejected` |

## 하지 않은 것·미정

- n8n에 워크플로를 만들지 않았다. 티켓 저장소 API(C), 포털 응답 형식의 실제 배포 여부(A)가 확인되지 않았다.
- Webhook 인증 방식과 호출자 주소 허용은 팀 VPN 연결과 Webhook 주소 확정 뒤 정한다(S12 설계 문서의 질문 목록 참고).
