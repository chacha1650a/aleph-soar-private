# 같은 자원의 적용·해제 실행 조율 · 집 구현

사람 담당 B(구현 준비)·D(호출 계층 적용)·C(기록 대조), 시험 `HOME-RESOURCE-GATE-20261024`, 브랜치 `codex/home-handoff-1023`. [resource_gate.py](../tools/resource_gate.py)는 **한 호스트의 동일한 로컬 SQLite DB를 사용하는 호출자 사이에서** 자원 예약·요청 중복·불확실한 실행 보류를 구현한다. 새 서버/포트·n8n 연결·대상 호출은 구현하지 않았다. [기존 판단 노드](../infra/n8n/guards/README.md)의 호출 허용=false를 바꾸지 않는다.

문제는 조회 시점에 다른 조치가 없었어도 해제 직전에 새 적용이 들어올 수 있다는 것이다. 이 모듈을 채택한다면 **예약 → 최신 상태 재조회 → 대상 호출 → 대상 상태/티켓 기록 대조 → 완료 저장/예약 해제** 전체를 한 자원 예약 안에 넣는다. 조회 후에 예약하는 순서로는 이 경쟁을 막지 못한다.

## 식별·상태와 구현 범위

- 자원은 기존 C 패치와 같은 `{asset_id, via, action, target}` 4개다. 자리·봇은 자원 예약 키에서 제외한다. apply와 release 모두 **적용 동작**(block 등)을 넣는다. release라고 unblock으로 키를 바꾸면 다른 예약이 되므로 금지한다. 동작 짝/자산 이름 통일은 C/D 확정 조건이다. 이름이나 IP를 임의 정규화하지 않는다.
- 논리 요청 ID와 자원·operation·payload의 정규 JSON 해시를 저장한다. payload 원문은 저장하지 않는다. 같은 ID/다른 내용은 Conflict, 진행 중 같은 요청은 busy, 끝난 같은 요청은 저장된 결과를 replayed로 반환한다. replayed를 대상 재호출 지시로 쓰지 않는다.
- `reserve`는 SQLite `BEGIN IMMEDIATE`와 자원 UNIQUE 제약으로 예약한다. 성공 결과는 reserved+Permit, 경합 결과는 busy다. DB 오류는 예외로 남으며 허가/0건으로 대체하지 않는다. 다른 자원은 독립적으로 예약할 수 있다. DB 쓰기 트랜잭션은 짧게 끝나며 외부 작업 동안 DB 전체 쓰기 잠금을 잡아두지 않는다.
- `finish(permit, result, evidence_ref)`는 현재 토큰/소유권을 확인하고 완료 저장과 예약 삭제를 한 트랜잭션으로 처리한다. 중간 실패는 둘 다 rollback한다. result는 `not_called`(대상 호출 안 함이 확실함) 또는 `recorded`(대상 결과와 기록 대조 완료)다. **record API의 ACK 하나만으로 후자를 만들지 않는다.** 증적 참조에는 키/원문을 넣지 않는다.
- 시간 초과·연결 끊김·대상 반영 후 기록 실패·실행 프로세스 중단은 pending으로 둔다. TTL·자동 만료·자동 재실행·자동 잠금 탈취가 없다. 호출했을 수 있는 예외에서 finally로 예약을 무조건 해제하지 않는다. DB를 다시 여는 것만으로는 예약이 풀리지 않는다.
- `inspect(request_id)`는 토큰 없이 상태/결과/증적 참조/시각을 반환한다. `reconcile`은 이전 실행 종료·대상 상태 확인·티켓 기록 대조를 모두 명시적으로 확인하고 증적 참조를 준 경우에만 pending을 reconciled로 끝낸다. 이 확인값은 **운영자의 선언**이지 모듈이 검증한 증거가 아니다. 이전 실행이 다시 움직일 수 있는 상태에서는 사용하지 않는다.

## 집에서 실행한 검증

```powershell
python -m pytest tests/test_resource_gate.py -q
```

합성 DB·메모리 자료만 쓰며 19개 사례를 확인한다. 같은 자원 apply/release의 24개 스레드 경쟁, 4개 독립 프로세스 경쟁, 다른 자원의 독립 진행, 같은 요청 재전송/다른 본문 충돌, 오래된/위조 토큰, 프로세스 강제 종료 뒤 pending 보존, 조건 없는 정리 거부, 완료/잠금 해제 중 실패의 원자적 rollback, DB 분실/빈 DB/조회 불가 시 실패, payload 원문 비저장을 포함한다. 실제 대응 API·티켓 운영 DB·학원 장비를 사용하지 않는다.

수명 주기를 직접 볼 최소 합성 예시는 다음과 같다. 임시 DB만 만들고 자동 삭제하며 대상 호출은 없다.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from tools.resource_gate import ResourceGate

r = {"asset_id": "synthetic-portal", "via": "portal", "action": "block", "target": "203.0.113.11"}
with TemporaryDirectory() as temp:
    gate = ResourceGate(Path(temp) / "gate.db", create=True)
    first = gate.reserve(r, "synthetic-apply", "apply", {"event_id": "synthetic-1"})
    print(first["state"])  # reserved
    print(gate.reserve(r, "synthetic-release", "release", {})["state"])  # busy
    # This example never called a target, so not_called is known.
    gate.finish(first["permit"], "not_called", "synthetic/no-target-call")
    print(gate.reserve(r, "synthetic-apply", "apply", {"event_id": "synthetic-1"})["state"])  # replayed
```

## 예약·HTTP·판단을 연결한 읽기 전용 시험

[ticket_trial.py](../tools/ticket_trial.py)의 `TicketTrial`로 기존 예약과 loopback GET·생성 JS 판단을 하나로 연결했다. 시험 ID는 `HOME-TICKET-TRIAL-20261024`다. **예약 획득 → 최신 HTTP 조회 → JS 판단 → not_called 완료/예약 정리** 순서이며 실제 대상 호출 함수나 실행 허용 스위치는 없다. 후보 판단이어도 실제 호출 허용은 false다.

```powershell
python -m pytest tests/test_ticket_trial.py -q
python tools/check_ticket_guard.py --ticket-source .local/ticket-pr55-final-20261024 --reserved-trial
```

두 번째 명령은 [C 패치가 적용된 체크아웃](../patches/ticket-store-pr55/README.md#다른-pc에서-같은-패치-검증)이 필요하다. 임시 DB/합성 키/127.0.0.1 임시 포트만 사용하고 끝나면 정리한다. 8개 대조 중6개는 예약 안에서 실제 loopback GET→JS→not_called를 수행하고, record ACK/409 2개는 기존 Flask test client 응답이다. 각 조회 시험ID를 다시 실행해 fresh query나 오래된 후보 판단이 발생하지 않는 것도 확인한다. 기존 `--loopback-http`/소켓 없는 모드는 유지한다.

| 결과/상황 | 동작·의미 |
| --- | --- |
| busy / conflict | 예약 미획득. HTTP 조회와 JS를 실행하지 않는다 |
| completed + released | 읽기 전용 시험의 완료. 실제 조치·효과·팀 준비 완료가 아니다. DB 결과는 not_called |
| HTTP 오류·형식 불일치 | 판단은 hold. 대상 호출이 없으므로 not_called로 예약 정리 가능. 0건으로 추정하지 않는다 |
| 조회/JS의 일반 예외·실행 중 워크플로 변경·허용=true 출력 | failed. 후보 출력은 버리고 대상 호출 없음을 기록해 정리한다. 예외 원문/키는 반환하지 않는다 |
| 완료 정리 실패 | failed + reservation_state=unknown. 예약 해제됐다고 말하거나 정리를 자동 재시도하지 않는다. inspect로 확인 |
| 중단/프로세스 종료 | BaseException을 잡아 무조건 정리하지 않는다. durable pending은 기존 gate의 확인/reconcile 절차를 따른다 |
| 같은 완료된 시험ID 재실행 | replayed·decision=null. 과거 후보를 최신 관찰로 재사용하지 않는다. 새 최신 조회는 새 시험ID |

`TicketTrial.run(request_id, mode, expected, evidence_ref)`의 request_id는 **읽기 시험의 시도 ID**이며 미래 실제 대상 호출의 논리 요청 키와 별개다. expected는 기존 판단 노드와 같은 범위(자리/묶음/bot/자원4개/원복 시 자기 ticket_id)를 준다. 같은 시도 ID의 예상 범위·operation·워크플로 해시·로컬 포트/timeout·증적 참조가 바뀌면 충돌로 처리한다. 입력은 복사해서 사용하며 DB에는 지문/상태/증적 참조만 저장한다. 인증 키·원문 응답·후보 판단은 DB에 저장하지 않는다. 증적 참조는 호출자가 실제 남긴 합성 결과의 위치로 주며 함수가 증적 파일을 생성하는 것은 아니다.

이 시험은 목표 시스템에 영향을 주는 경로가 없으므로 query 실패에도 안전하게 not_called로 끝낼 수 있다. **미래 실제 호출 흐름에 이 정리 규칙을 복사하면 안 된다.** 실제 호출이 가능해지면 반영 여부가 불명확한 실패는 pending을 유지하고, 적용/해제의 전체 구간을 같은 예약 안에 넣어야 한다.

## 학원 연결 전에 결정·검증할 것

1. D의 모든 적용/해제 호출이 **하나의 조율 지점과 동일한 로컬 DB**를 사용하도록 배치한다. n8n Code 노드마다 별도 임시 DB를 만들면 보호되지 않는다. 공유 폴더/SMB/NFS/클라우드 동기화 DB는 지원하지 않으며, 여러 PC에 복사한 DB는 별도 잠금이다. UNC 경로는 거부하지만 매핑 드라이브의 실체까지 자동 판별하지는 않는다.
2. C/D가 자원/요청 ID·동작 짝을 맞춘 뒤, 집의 읽기 시험과 별도로 실제 호출 전후를 포함하는 실행 어댑터를 구현한다. allow_target_call=false는 그대로다. 실제 대상의 원자적 멱등성·허용 대상·실제 효과·정상 접근·원복 검증을 마친 뒤에야 호출 계층의 정책을 결정한다. 이 모듈의 Permit은 대상 시스템이 검사하는 fencing 토큰이 아니며 실제 실행 권한도 아니다.
3. 사람이 수동 실행하거나 별도 워크플로/프로세스가 조율을 우회하면 보호할 수 없다. 최초 준비만 `create=True`를 사용하며, 이미 파일이 있으면 거부한다. 평소 생성자는 기존 DB를 mode=rw로만 열어, 분실/빈 DB/다른 스키마를 자동 초기화하지 않고 보류한다. 배포에서는 경로가 같은 다른 정상 DB를 잘못 선택하는 문제까지 막을 DB 식별/백업·복원 절차가 추가로 필요하다. 이 모듈을 운영 배포 완료로 해석하지 않는다.
4. 불확실한 요청은 재시도/잠금 삭제 전에 이전 실행이 완전히 멈췄는지 확인한다. 대상 상태·원래 요청 키·C 기록을 대조하고 증적을 남긴 뒤 reconcile한다. DB 파일 삭제나 백업 복원으로 pending을 없애면 중복 실행 위험이 있으므로 금지한다. 실제 호출 프로세스 종료 확인·대상 상태 대조·재시작 운용은 아직 미검증이다.

SQLite 예약 코어와 읽기 전용 loopback HTTP·판단·정리 흐름을 집에서 구현·검증했다. 실제 n8n HTTP 노드/대상 호출 어댑터 연결, 네트워크 분할·다중 호스트 제어, 대상별 요청 멱등성·소유권 강제, 학원 시험과 통합 속도 측정은 남아 있다. C PR·D 원본 워크플로·학원 설정·팀 메시지/PR 댓글은 변경하지 않았다.

후속으로 [모의 적용·해제·C 기록·장애 복구 리허설](home-rehearsal.md)을 추가했다. 예약 후 모의 반영이 가능해진 뒤에는 실패 시 pending을 유지하고, 영수증/현재 상태 대조 후 같은 키로 기록만 복구한다. 실대상 어댑터나 n8n 운영 배포로 해석하지 않는다.
