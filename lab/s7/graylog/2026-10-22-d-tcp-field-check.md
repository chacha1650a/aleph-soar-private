# 2026-10-22 C → D TCP 경로 필드 확인 (S7)

- 작성: C(shk12170-dev) · 확인: D(chacha1650a, D Graylog 화면 조회)
- 경로: C Wazuh manager `syslog_output`(`group syscheck`, `format json`) → C 중계 컨테이너 `wazuh-tcp-relay`(UDP 5514 → TCP) → 팀 VPN → D Graylog `10.250.0.100:5514/tcp`
- 범위: **agent 000(C manager 연습 폴더 `/tmp/zz_fim_test`) 값만 확인**. agent 010(A VM 웹 루트) 경보는 이 시험에 포함되지 않음

## 시험

- 표식: `zz_field_033200` (숫자는 UTC 시각, KST 12:32:00)
- 방법: manager 컨테이너에서 파일 생성 → 5초 뒤 내용 추가 → 5초 뒤 삭제

| 시각(KST) | 규칙 | level | 이벤트 | 경보 크기(C `alerts.json` 한 줄) |
| --- | --- | --- | --- | --- |
| 12:32:00.973 | 554 | 5 | added | 1,085B |
| 12:32:05.937 | 550 | 7 | modified | 2,040B |
| 12:32:10.934 | 553 | 7 | deleted | 1,201B |

## C 쪽 결과 (C 확인)

- 중계기 통계 12:32:48: `received=9 sent=9 dropped=0 queued=0 connected=true` (시험 전 6/6 → 3건 증가)
- 이전 사정: 12:08~12:18 중계기 재연결 반복(`ECONNREFUSED`·`tcp closed`, 누적 reconnects=47). D가 TCP 입력을 손보던 시간과 일치하며 12:18:28 이후 안정

## D 쪽 결과 (D 확인, 사용자 전달)

- 3건(554·550·553) 수신. UDP에서 빠지던 550(약 2KB)도 TCP로 도착
- 해시 연결:
  - 550의 `sha256_before` = 554의 `sha256_after`
  - 553의 `sha256_after` = 550의 `sha256_after`
  - 추가 → 변경 → 삭제의 해시가 끊기지 않고 이어짐
- 타입: `wazuh_rule_level`은 숫자로 저장됨
- 기타: `wazuh_full_log` 필드 있음. 원본 JSON 전체를 담은 별도 필드는 없음

## C 원본과 대조 (C `alerts.json`)

| 규칙 | `sha256_before` | `sha256_after` |
| --- | --- | --- |
| 554 | 없음 | `87428fc5…cf25c7` |
| 550 | `87428fc5…cf25c7` | `911169dd…aa59a2` |
| 553 | 없음 | `911169dd…aa59a2` |

D가 본 해시 연결과 C 원본이 일치함.

## 규칙 작성에 반영할 점

1. **553(삭제)은 마지막 해시를 `sha256_after`에 담고 `sha256_before`는 비어 있음.** "550이면서 `sha256_after` ∈ 기준본 해시" 제외 조건은 `wazuh_rule_id = 550`을 반드시 함께 걸어야 553이 잘못 제외되거나 섞이지 않음. (앞서 C가 D에게 보낸 필드표에서 "553에 `sha256_before` 있음"이라고 한 부분은 틀렸음 → 이 문서가 정정)
2. `wazuh_rule_level`이 숫자라서 `>= 7` 같은 범위 조건 사용 가능
3. 원본 JSON 필드가 없으므로 증적에는 필요한 필드만 남기고, 원문이 필요하면 C manager `alerts.json`에서 표식·시각으로 찾음
4. 550 경보는 2KB 안팎이고, 실제 웹 파일이 바뀌면 diff 때문에 더 커질 수 있음 → 팀 경로는 TCP를 유지

## 미확인

- agent 010(A VM) FIM 경보의 D 수신과 필드 값(`wazuh_agent_id = 010`, 웹 루트 경로). A의 보강 전 측정이 끝난 뒤 확인
- D 필드 중 `wazuh_agent_id`/`wazuh_agent_name`, `wazuh_file`, `wazuh_syscheck_event`, `wazuh_timestamp`의 값은 D 답변에 따로 적히지 않음 → 다음 대화에서 확인
- 중계기 재시작·D 입력 재시작 때 대기열이 다시 전송되는지는 11:32 시험(대기 3건 → 연결 후 전송)에서만 확인함
