# 03. 번호 등록부

이 표에 없는 번호는 쓰지 않는다. 새 번호가 필요하면 docs에 요청하고, 등록된 뒤에 쓴다.
대역 안에서 실제로 쓴 번호는 아래 "사용 기록"에 줄을 추가한다(해당 티켓 담당만, 덧붙이기만).

## Wazuh 규칙 ID

| 대역 | 티켓 | 파일 |
|---|---|---|
| 100100–100109 | 공통(docs) | `detection/wazuh/rules/common_rules.xml` |
| 100110–100119 | INC-01 | `detection/wazuh/rules/inc01_rules.xml` |
| 100120–100129 | INC-02 | `detection/wazuh/rules/inc02_rules.xml` |
| 100130–100139 | INC-03 | `detection/wazuh/rules/inc03_rules.xml` |
| 100140–100149 | INC-04 | `detection/wazuh/rules/inc04_rules.xml` |
| 100150–100159 | INC-05 | `detection/wazuh/rules/inc05_rules.xml` |
| 100160–100169 | INC-06 | `detection/wazuh/rules/inc06_rules.xml` |

- 규칙 파일은 monitor의 `/var/ossec/etc/rules/`에 그대로 복사한다. `local_rules.xml`은 쓰지 않는다.
- 각 파일의 `<group name="...">`은 `inc0X,`로 시작한다. 예: `<group name="inc01,">`

## Wazuh 에이전트 설정 조각

| 티켓 | 파일 | alias 접두사 |
|---|---|---|
| INC-01 | `detection/wazuh/agent/inc01_localfile.xml` | `inc01_` |
| INC-02 | `detection/wazuh/agent/inc02_localfile.xml` | `inc02_` |
| INC-03 | `detection/wazuh/agent/inc03_syscheck.xml` | – |

조각을 실제 `ossec.conf`에 합치는 일은 host만 한다.

## Suricata SID

| 대역 | 티켓 | 파일 |
|---|---|---|
| 1000001–1000099 | 공통(docs) | `detection/suricata/common.rules` |
| 1000400–1000499 | INC-04 | `detection/suricata/inc04.rules` |
| 1000500–1000599 | INC-05 | `detection/suricata/inc05.rules` |
| 1000600–1000699 | INC-06 | `detection/suricata/inc06.rules` |

- 티켓 규칙의 `msg`는 `"INC-0X: "`로, 공통 규칙(1000001–1000099)의 `msg`는 `"COMMON: "`으로 시작한다.
- monitor에서는 이 파일들을 합쳐 `/etc/suricata/rules/local.rules`로 배포한다(net만).

## 호스트명·IP (변경 금지)

| 호스트명 | IP |
|---|---|
| attacker | 10.10.10.10 |
| lb-01 | 10.10.10.20 |
| web-01 | 10.10.10.31 |
| web-02 | 10.10.10.32 |
| monitor | 10.10.10.50 |
| rogue | 10.10.10.99 |
| (호스트 PC) | 10.10.10.1 |

Suricata 주소 변수 `LAB_KNOWN`(INC-05용)은 위 표의 rogue를 뺀 6개 주소로만 구성한다. 호스트가 바뀌면 docs가 이 표와 함께 고친다.

## 포트

| 포트 | 위치 | 용도 | 주인 |
|---|---|---|---|
| 22/tcp | 전체 | SSH (lab-net에서만) | docs |
| 80/tcp | lb-01, web-01, web-02 | HTTP | avail |
| 8000/tcp | web-01, web-02 (127.0.0.1) | gunicorn | avail |
| 443/tcp | monitor | Wazuh 대시보드 | host |
| 1514, 1515/tcp | monitor | Wazuh 에이전트 | host |
| 55000/tcp | monitor | Wazuh API | host |
| 4444/tcp, 9999/udp | web-01 | INC-01 재현 전용 | host |

## 스냅샷 이름

| 이름 | 시점 |
|---|---|
| `baseline` | 단계별 구축 가이드 8단계 완료 직후 |
| `before-INC-0X` | 해당 티켓 재현 직전(필요할 때만) |

## 사용 기록

| 날짜 | 티켓 | 번호 | 설명 |
|---|---|---|---|
| (예) 2026-10-20 | INC-01 | 100110 | 삭제되었거나 임시 경로에서 실행 중인 프로세스 |
| (예) 2026-10-20 | INC-01 | 100111 | 패킷 소켓 목록 변경 |
