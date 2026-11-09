# S7 FIM 이벤트 계약 확장안 (초안)

- 작성: shk12170-dev · 2026-10-19 · 상태: **제안. 팀 합의 전이며 `contracts/`와 `docs/API-CONTRACT.md`는 바꾸지 않았습니다.**
- 목적: 합의본 ④가 "첫 구현 작업"으로 둔 이벤트 계약 확장([검토 메모 11](../11-team-feedback.md))에서 S7(파일 변조 → 웹 접근)에 필요한 부분을 먼저 제안합니다.
- 채택하려면 `aleph-contract-change` 절차대로 조율 담당과 맞춘 뒤 이 폴더의 파일을 `contracts/`로 옮기고 `tests/test_contracts.py`를 고칩니다(아래 4절).

## 1. 왜 확장이 필요한가

현재 [event.schema.json](../../contracts/event.schema.json) v1.0은 다음 때문에 S7 신호를 받을 수 없습니다.

| 현재 | S7에서의 문제 |
| --- | --- |
| `event_type`이 인증·권한·조회 4종뿐 | FIM(파일 생성/변경/삭제)과 웹 파일 접근을 표현할 수 없음 |
| `username`·`src_ip` 필수 | Wazuh FIM 알림에는 접속자 IP가 없고, 사용자는 `www-data` 같은 감사 계정일 뿐 |
| `details`에 `resource`·`previous_role`·`new_role`만 허용 | 파일 경로·해시·권한 값을 담을 곳이 없음 |
| 사건 `username` 필수 | S7의 묶기 기준은 사용자가 아니라 **자산 + 파일 경로**([03-scenarios](../03-scenarios.md): 원본 묶기 없음, 경로 기준 필요) |

## 2. 제안 내용

파일: [event.schema.v1.1-draft.json](event.schema.v1.1-draft.json), [incident.schema.v1.1-draft.json](incident.schema.v1.1-draft.json)

### 이벤트

| 변경 | 내용 |
| --- | --- |
| `schema_version` | `1.0`과 `1.1` 모두 허용 (기존 데이터 호환) |
| 새 `event_type` | `fim.file_created`, `fim.file_modified`, `fim.file_deleted`, `web.file_accessed` |
| 필수 필드 | 공통: `event_id`·`timestamp`·`source`·`event_type`·`asset_id`·`outcome`. 기존 4종은 `if/then`으로 `username`·`src_ip` 필수 유지 |
| FIM 이벤트 | `details.file_path` 필수. `src_ip` 불필요 |
| 웹 접근 이벤트 | `src_ip`, `details.file_path`·`http_method`·`http_status` 필수 |
| 새 `details` 필드 | `file_path`, `sha256_before/after`, `mode_before/after`, `audit_user`, `process_name`, `http_method`, `http_status` |

### 묶기 키: `asset_id` + `details.file_path`

- `file_path`는 **웹 루트 기준 상대 경로**입니다. 예: `static/uploads/zz_s7_marker.txt`
- Wazuh는 파일시스템 경로(`/var/www/portal/static/...`), 웹 로그는 URL 경로(`/static/...`)를 줍니다. **수집 단계에서 같은 상대 경로로 정규화**해야 두 신호가 같은 키로 묶입니다. 정규화 규칙은 미정이며 아래 5절에 둡니다.
- 스키마가 막는 경로: 앞의 `/`, `..` 구간, 역슬래시 (경로 이탈·표기 혼용 방지)

### 사건

- `username` 필수를 풀고 `username` 또는 `file_path` 중 하나를 요구합니다(`anyOf`).
- `file_path` 선택 필드를 추가합니다. 기존 사건 예시는 그대로 유효합니다.

### 민감 정보 규칙 (기존 원칙 유지)

- `additionalProperties:false`를 `details`에도 유지합니다. 파일 **내용**은 담을 필드가 없고, 변조 여부는 해시로만 표시합니다.
- 비밀번호·토큰·`password` 같은 미허용 필드는 계속 거부됩니다.
- 합성 예시는 `zz_` 접두사와 문서용 IP 대역(192.0.2.0/24)만 씁니다.

## 3. 합성 예시

[examples/](examples/): `fim-file-created`, `web-file-accessed`(같은 경로), `fim-file-modified`, `incident-s7`. 실제 탐지·수집 결과가 아닌 계약 확인용 데이터입니다.

## 4. 검증한 것과 채택 시 바꿀 것

실행 결과 (임시 가상환경에 `requirements-dev.lock` 설치):

```text
python -m pytest docs/s7-draft/test_s7_contract_draft.py tests/test_contracts.py -q
40 passed
```

- 확인한 것: 기존 4종 이벤트·기존 사건 예시가 초안 스키마에서도 유효, 새 예시 유효, 잘못된 입력(경로 이탈·절대 경로·역슬래시·내용 필드·잘못된 해시·IP·상태코드·시간대 없는 시각·기존 타입의 필수 필드 누락) 거부
- **확인하지 않은 것:** 실제 Wazuh 알림 필드와의 대응, Graylog 정규화, 실제 앱 연동. 스키마와 합성 예시의 일관성만 검증했습니다.

채택할 때 함께 바꿔야 하는 곳:

1. `contracts/event.schema.json`, `contracts/incident.schema.json` 교체 또는 병합, 예시 이동
2. `tests/test_contracts.py`: 사건 예시 검사가 `contracts/examples/*.json` 전체를 모아 `username`을 비교하므로, S7 사건 예시를 넣으면 `username` 키가 없어 실패합니다. 사건 종류별로 비교 키를 나누도록 고쳐야 합니다.
3. `docs/API-CONTRACT.md` 이벤트·사건 절 갱신 (새 타입, `file_path` 정규화 규칙)
4. 사건을 소비하는 쪽(U01 화면, D01 상관)이 `username` 없는 사건을 처리하는지 확인 — 현재 구현이 없어 영향은 설계 단계에서 합의해야 합니다.

## 5. 팀과 정해야 할 것

| 항목 | 질문 | 제안 |
| --- | --- | --- |
| 필드 의미 변경 | 사건의 `username` 필수 해제는 의미 변경(조율 담당 연결 필요) | `anyOf`로 호환 유지 |
| 경로 정규화 위치 | 파일시스템 경로 → 웹 루트 상대 경로 변환을 Wazuh 쪽(디코더)에서 할지 Graylog 파이프라인에서 할지 | Graylog 파이프라인 (한 곳에서 FIM·웹 모두 처리) |
| 웹 접근 출처 | 웹 접근 신호를 앱이 직접 GELF로 보낼지, 웹 서버 로그를 수집할지 | 앱이 보내는 쪽이 필드 통제가 쉬움 (포털 담당과 합의) |
| `outcome` 의미 | FIM에서 `success`는 "변경이 실제 발생" | 문서에 명시 |
| 다른 확장과 충돌 | 경계(pfSense)·VPN·가용성 신호 확장과 `src_ip`·`username` 완화 방식이 겹침 | 같은 `if/then` 틀로 추가, 담당자와 한 번에 조율 |
| 버전 | `1.1`로 올릴지, `1.0` 안에서 확장할지 | `1.1`, 1.0 호환 유지 |
| 4종 외 변경 유형 | 권한 변경(`mode`)만 바뀐 경우를 별도 타입으로 둘지 | 일단 `fim.file_modified`에 `mode_*`로 표현 |
