# S7 판정 규칙 합의안 (C 제안 → D 검토, 2026-10-22)

- 상태: **제안 · 미시험.** D Graylog에 넣고 시험한 뒤 확정한다. 보강 전 #1은 10/22 완료(동결 16:14 해제)라 활성화해도 된다.
- 기준: 기획서 합의본 ④ S7(같은 자산 + 같은 `file_key`, FIM 변경·생성 + 웹 접근 2xx, 10분), 정량평가 `team_docs/정량평가-S7-shk12170-dev.md`
- 필드 근거: C 원본 `alerts.json`, D TCP 필드 확인(`lab/s7/graylog/2026-10-22-d-tcp-field-check.md`), A 포털 원본(`web.file_access` event_id `e98f04b6-…`)

## 1. 신호 두 가지

| 신호 | 스트림 | 조건 | 만들 필드 |
| --- | --- | --- | --- |
| FIM 변경·생성 | `wazuh-alerts` | `wazuh_agent_name = haedam-portal-vm`, `wazuh_file`이 웹 루트로 시작, `wazuh_rule_id ∈ {554, 550}`, **해시가 기준본 목록에 없음** | `file_key`, `asset_id = haedam-portal`, `signal_kind = fim-change` |
| 웹 접근 성공 | `haedam-portal` | `event_type = web.file_access`, `status` 200~299 | `signal_kind = web-access-2xx` (`file_key`·`asset_id`는 포털이 보냄) |

- 웹 루트: `/home/haedam/haedam-portal-frontend/dist/` (A VM, 10/21 이관 후)
- 자산 대응: agent `haedam-portal-vm` ↔ `asset_id haedam-portal`(10/22 포털 원본 값). agent 이름을 자산 ID로 자동 간주하지 않고 이 한 줄로만 연결
- 홈페이지 `/` 접근은 포털이 `file_key index.html`로 기록(기획서 ④·포털 계약 #19)

## 2. 빼는 것 (중복 티켓·반복 대응 방지)

| 제외 | 이유 | 규칙에서 |
| --- | --- | --- |
| 553 삭제 | 복구 때 새 파일 격리·시험 파일 정리로 생김. 553은 마지막 해시를 `sha256_after`에 담고 `sha256_before`는 비어 있음(D 필드 확인) | `wazuh_rule_id ∈ {554, 550}`만 받음 |
| 해시가 기준본 목록에 있는 554·550 | 117 복구 결과(10/21 복원 재시험: 복원 경보 `sha256_after` = 처음 해시)와 정상 배포 | lookup `s7_baseline_hashes`에 있으면 `signal_kind`를 달지 않음 |
| 2xx가 아닌 접근 | 격리 뒤 404 확인 요청 | `status` 200~299만 |

## 3. 파이프라인 규칙 (D `wazuh-parse` 뒤 stage)

```
rule "S7: FIM file_key"
when
  to_string($message.wazuh_agent_name) == "haedam-portal-vm"
  && starts_with(to_string($message.wazuh_file), "/home/haedam/haedam-portal-frontend/dist/")
  && (to_string($message.wazuh_rule_id) == "554" || to_string($message.wazuh_rule_id) == "550")
then
  set_field("file_key", replace(to_string($message.wazuh_file), "/home/haedam/haedam-portal-frontend/dist/", ""));
  set_field("asset_id", "haedam-portal");
end

rule "S7: FIM signal (not baseline)"
when
  has_field("file_key") && has_field("wazuh_syscheck_sha256_after")
  && is_null(lookup_value("s7_baseline_hashes", to_string($message.wazuh_syscheck_sha256_after)))
then
  set_field("signal_kind", "fim-change");
end
```

```
rule "S7: web access 2xx"
when
  to_string($message.event_type) == "web.file_access"
  && to_long($message.status) >= 200 && to_long($message.status) < 300
  && has_field("file_key")
then
  set_field("signal_kind", "web-access-2xx");
end
```

- stage 순서: `wazuh-parse`(0·1) → `S7: FIM file_key`(2) → `S7: FIM signal`(3). 웹 규칙은 `haedam-portal` 스트림 파이프라인에.
- **D 확인 필요:** 포털 GELF가 D에서 `event_type`·`status`·`file_key`·`asset_id`라는 이름으로 저장되는지(GELF `_` 접두 제거 여부), `status`가 숫자인지
- lookup `s7_baseline_hashes`: 키 = sha256, 값 = `file_key`. 원천은 A의 배포 기준본 목록(배포 때 갱신). **준비 전에는 빈 표로 두고 시작**(그동안 정상 배포·복구 재경보도 신호가 됨 → #11·중복 확인은 표가 생긴 뒤 시험)

## 4. 이벤트 정의 `S7 홈페이지 변조 (file_key)`

| 항목 | 값 |
| --- | --- |
| 스트림 | `wazuh-alerts`, `haedam-portal` |
| 검색 | `_exists_:signal_kind AND asset_id:haedam-portal` |
| 묶기 | `asset_id`, `file_key` |
| 조건 | `card(signal_kind) > 1` (두 종류 모두 있음) |
| 검색 범위 / 실행 주기 | 10분 / 1분 (MTTD 목표 중앙값 ≤ 60초) |
| 이벤트 필드 | `asset_id`, `file_key` |
| 알림 | 처음엔 없음(판정만 시험) → 117·114 준비 후 n8n 웹훅 연결 |

- 조건 충족 시각(MTTD 시작점) = 나중 신호 시각. 첫 공격 시각(파일 변경)은 따로 기록

## 5. 활성화 뒤 보강 후 시험 (정량평가 3절)

| # | 입력 | 기대 | lookup 필요 |
| --- | --- | --- | --- |
| 2~4 | 새 파일 생성 → 10분 안 접근 | 발동 1 | 아니오 |
| 5~6 | 기존 파일 변경 → 접근 | 발동 1 | 아니오(117 복구 뒤 재경보 확인은 예) |
| 7 | 변경만 | 미발동 | 아니오 |
| 8 | 접근만 | 미발동 | 아니오 |
| 9 | 변경 후 10분 넘겨 접근 | 미발동 | 아니오 |
| 10 | 파일 A 변경, 파일 B 접근 | 미발동 | 아니오 |
| 11 | 정상 배포 + 정상 업무 30분 | 이벤트 0 | **예** |

- 실행마다 다른 `zz_` 파일 경로, 접근은 C 대역 Kali(203.0.113.31~39, 위치 B 확인 중)
- 117(복구·격리)·114(티켓)는 판정 시험(#2~10) 뒤 연결해서 2~6의 대응·효과·원복까지 다시 확인
