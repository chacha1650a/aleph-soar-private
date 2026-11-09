# 2026-10-20 관제 사전 점검·GELF 소량 수신 확인

- 작업 ID·역할: H05 사전 점검([계획](../docs/haedam/MONITORING-CAPACITY-PLAN.md) 3절·5절 1단계) / 김명준 + Claude.
- 기준: capstone `1e94433`(`codex/monitoring-capacity-plan-1020`), backend `983dad6`(PR #2 `claude/portal-ip-block-file-key`).
- 상태: **부분 실행.** 한 PC 루프백 소량 확인만 했다. 두 PC 수집, 정상 기준선, 단계 부하, 복구 시험은 미실행이다.

## 장비·자원 (2026-10-20 09:0x KST, 1회 표본)

| 항목 | 값 |
| --- | --- |
| PC | DESKTOP-TKLBES7, i7-10700(8코어/16스레드), RAM 15.8GB, C: 여유 201GB, D: 여유 399GB |
| 호스트 RAM | 여유 0.9GB(사용 약 94%). `vmmemWSL` 5.7GB, 그 외 ChatGPT·Discord·Chrome·Claude 등 데스크톱 앱 실행 중 |
| WSL | `.wslconfig` memory=6GB, swap=4GB. Docker Desktop 29.8.2, 엔진 메모리 5.785GiB |
| 컨테이너 메모리 | gl-opensearch 1.64GiB, wazuh-indexer 1.26GiB, gl-graylog 819MiB, n8n 327MiB, wazuh-manager 280MiB, wazuh-dashboard 155MiB, flask_mysql 59MiB, gl-mongo 54MiB. 모두 컨테이너 메모리 제한 없음 |
| JVM 힙 | gl-opensearch·wazuh-indexer 각각 `-Xms1g -Xmx1g`. Graylog 힙은 환경값 미설정, 실제 값 미확인 |
| 디스크 | Graylog 저널 24KB. OpenSearch 할당 디스크 사용 8%(WSL 가상 디스크 기준이며 호스트 여유와 다름). Docker 이미지 18.9GB, 볼륨 7.6GB |

**판단:** 부하 없이도 호스트 RAM이 계획의 중단 기준 후보(90% 이상 30초)를 넘는다. 기준선을 잡기 전에 시험과 무관한 데스크톱 앱을 정리하고 다시 표본을 기록해야 한다. 이번 값은 1회 표본이며 30초 유지 여부는 측정하지 않았다.

## 실제 버전·기동 상태

| 구성 | 버전 | 상태·연결 |
| --- | --- | --- |
| Graylog | 6.1.16+4a05695 (`graylog/graylog:6.1`) | healthy, 재시작 0회 |
| OpenSearch(Graylog용) | 2.5.0, 단일 노드, 보안 플러그인 비활성 | cluster green, 미할당 샤드 0 |
| MongoDB | 6.0.28 | 기동 |
| Wazuh manager·indexer·dashboard | 4.9.0 (indexer 내부 OpenSearch 2.13.0) | 기동. manager가 Graylog Docker 네트워크에 붙어 `gl-graylog:5140`으로 level 5 이상 경보를 JSON syslog 전송 |
| n8n | 2.37.7 (태그 없는 이미지) | 기동. 기본 `bridge` 네트워크, restart=no |
| MySQL(flask_mysql) | 8.0.46 | 기동. 다른 실습 프로젝트(`C:\lhs\...\_7_test_class`) 소속 |

compose 위치: Graylog 묶음은 `C:\Users\user\Desktop\Aleph\python\_9_graylog`, Wazuh는 `C:\SKT aleph\flask-board\wazuh`. **수업 실습 구성이며 팀 기획서용 관제 구성으로 정리·합의된 것이 아니다.** 이 PC가 팀의 관제 PC 자리인지도 확인하지 않았다.

Graylog 입력: GELF UDP 12201(제목 "hping3 lab"), Raw UDP 5140(Wazuh 경보), Syslog UDP 1514(pfSense). 컨테이너가 12201/tcp도 공개하지만 GELF TCP 입력은 없다. 5140/udp는 호스트에 공개되지 않아 같은 Docker 네트워크 안에서만 받는다. 인덱스 세트 3개 모두 30~40일 시간 기반 회전, 최대 20개 인덱스 보존 후 삭제. 이벤트 정의 13개(hping3, S1, S11, Wazuh 100211/100220~100222 등)는 실습 규칙이며 포털 필드와의 일치는 확인하지 않았다. 최근 7일 Default Stream에는 board-host·suricata·snort-kali·pfSense filterlog 등 실습 로그가 섞여 있다.

## GELF 소량 수신 (계획 5절 1단계 일부)

- 방법: backend PR #2 HEAD를 임시 worktree에 설치하고 Flask test client로 `GET /api/v1/auth/me`(200), 없는 경로 GET(404)을 1회씩 보냈다. 임시 SQLite·임시 JSONL, `GELF_HOST=127.0.0.1:12201`. 같은 PC 루프백이며 Waitress 서버·pfSense·두 번째 PC를 거치지 않았다.
- 발신(JSONL) 고유 ID 3건: `web.request` 2, `web.not_found` 1. 404 요청 하나가 두 이벤트를 만든다.
- 수신: OpenSearch `graylog_*`에서 `event_id`로 3건 모두 1건씩 검색됨. 누락 0, 중복 0. 원본 timestamp → 최초 검색까지 1.5~1.7초(1초 간격 조회라 상한값).
- 필드 매핑: `_event_id`→`event_id`, GELF host→`source`=`haedam-portal`, `_rule`→`rule`(404는 `web-scan`), `_portal_event`에 원본 JSON. Default Stream에만 들어감. 저장 timestamp는 UTC.
- 임시 worktree·DB·JSONL은 확인 후 삭제했다. Graylog에 남은 시험 문서 3건은 그대로다.

## Graylog 이벤트 정의 13개와 포털 필드 대조

- 방법: MongoDB `graylog.event_definitions`의 조회식·그룹·조건·필드 템플릿을 읽기만 했고, backend `983dad6`의 `emit()` 호출과 GELF 필드를 대조했다. **설정은 바꾸지 않았다.** 정의를 실제로 발동시키는 이벤트는 보내지 않았다. n8n 워크플로가 IP 차단·계정 잠금을 실행할 수 있기 때문이다.
- 포털이 보내는 GELF 필드: `rule`, `event_id`, `event_type`, `src_ip`, `username`(익명이면 `anonymous`), `asset_id`, `status`, `path`, `portal_event`, `file_key`, `target_ip`, `source=haedam-portal`. `details`의 다른 값은 `portal_event` JSON 문자열 안에만 있어 검색 필드가 아니다.
- 포털 rule 값: 로그인 실패(401, 속도 제한 429 모두) `login-bruteforce`, 로그인 성공 `login-success`, 404 `web-scan`, 요청 `request-observed`, 파일 제공 `file-access`. 나머지 이벤트는 event_type 그대로(예: `auth.account_locked`, `iam.role_changed`, `web.ip_blocked`).
- 로그인 실패 이벤트는 존재하지 않는 계정이어도 입력한 username(소문자)을 남긴다. 잠긴 계정의 로그인 실패도 일반 실패와 같은 401 `auth.login_failed`이며 잠김 여부 필드가 없다. 포털 속도 제한은 출발지 IP당 5분 20회다.

| 정의(Graylog 제목 번호) | 조건 | 포털 이벤트로 | 판정 |
| --- | --- | --- | --- |
| 시스템 알림 | 내장 | — | 해당 없음 |
| 자동 회수봇 | `rule:priv-unauthorized-admin`, 필드 `granted_by`·`user` | 포털은 이 rule을 보내지 않음. 권한 변경은 `iam.role_changed`, 필드명은 `username` | **동작 안 함** |
| hping3 SYN | `rule:hping3-synflood` | 네트워크 경로 | 해당 없음 |
| 3-IP 반복 로그인 실패 | `rule:login-bruteforce`, src_ip별 2분 5회 이상 | `auth.login_failed`가 같은 rule·src_ip로 들어옴 | **필드상 동작** |
| 4-계정 스프레이 | 같은 조회, src_ip별 username 종류 5개 이상 | 없는 계정도 입력값으로 기록되므로 종류 수가 셈 | **필드상 동작** |
| 5-복합 상관 | `rule:login-bruteforce OR rule:portscan`, src_ip별 rule 2종 이상 | 포털 쪽은 맞음. `portscan`은 `netsensor` 출처에만 있고 Snort는 `snort-portscan`이라 빠짐. 포털 404(`web-scan`)는 포함 안 됨 | **부분**: 네트워크 쪽 rule과 같은 src_ip 필요 |
| 6-잠긴 계정 지속 시도 | `rule:login-bruteforce AND locked:1` | 포털 GELF에 `locked` 필드 없음 | **동작 안 함** |
| 7-Wazuh 100211 | Wazuh 스트림 `wazuh_rule_id` | Wazuh 경로 | 해당 없음 |
| 8-Wazuh FIM 100220~2 | Wazuh 스트림, `file=wazuh_file` | 포털 `web.file_access`(`file-access`, `file_key`)와 묶는 정의 없음. `wazuh_file`은 절대 경로라 `file_key`와 값이 다름 | S7 연결 **미구성** |
| 9-웹 스캐너 404 | `rule:web-scan`, src_ip별 30초 30회 초과 | `web.not_found`가 같은 rule·src_ip로 들어옴 | **필드상 동작** |
| 10-Suricata | `rule:ids-alert` | 네트워크 경로 | 해당 없음 |
| 11-S1 저속 브루트포스 | `rule:login-bruteforce`, username별 30분 8회 이상 | 같은 rule·username | **필드상 동작**, 아래 창 주의 |
| 12-심야 로그인 | `night_login:yes` | 포털은 `night_login`을 보내지 않음(성공은 `login-success`만) | **동작 안 함** |
| 13-Snort 포트스캔 | `rule:snort-portscan` | 네트워크 경로 | 해당 없음 |

사용자 정의 13개와 내장 시스템 알림 1개, 모두 14개다. 아래 번호는 Graylog 제목에 붙은 번호다.

공통 주의:

- 포털과 관련된 정의(3·4·5·6·9·11번)는 출처 조건 없이 전체 스트림을 본다. 실습 게시판(`source=board`)도 같은 rule 값을 써서 합산된다. 현재 인덱스에 board의 `login-bruteforce` 328건, `web-scan` 20,129건이 있다. 팀 시연에서는 출처를 나누거나 실습 앱 발신을 멈춰야 한다(변경 안 함).
- 11번은 조회 창과 실행 간격이 모두 30분이라 창이 겹치지 않는다. 8회가 두 창에 나뉘면(예: 4+4) 발동하지 않는다.
- 3·11번은 속도 제한에 걸린 429 실패도 함께 센다.
- 필드 템플릿(`${source.src_ip}`, `${source.username}`, `${source.rule}`)은 포털 필드명과 같다. 404 같은 익명 이벤트의 username은 `anonymous`다.
- 알림 9개는 모두 HTTP로 `host.docker.internal:5678/webhook/...`(n8n)을 부른다. Graylog 컨테이너에서 n8n `/healthz`가 200을 반환해 경로는 열려 있다. n8n 워크플로는 16개 중 6개가 활성이다. 웹훅은 호출하지 않았고, 워크플로가 실습 게시판과 해담 포털의 대응 API 중 어디를 부르는지는 확인하지 않았다.

## 미검증·다음 작업

- 팀 확인: 관제 PC 자리, 실습 compose를 팀 구성으로 쓸지 새로 정리할지. 결정 전에는 이 PC 결과를 팀 관제 실측으로 보고하지 않는다.
- 기준선 전에: 무관한 앱 정리 후 호스트·WSL·컨테이너 RAM 재표본, Graylog 힙 확인, 시계 오차 기록.
- 두 PC: 서비스 PC의 포털이 pfSense를 거쳐 관제 PC 12201/udp로 보내는 경로, 실제 출발지 주소, 방화벽 허용표(B·D 담당).
- 탐지 규칙(D 담당과 조율): 자동 회수봇·6번·12번을 포털 필드에 맞출지(예: `auth.account_locked` 이후 실패, 로그인 성공 시각), 포털 정의에 `source:haedam-portal` 조건을 둘지, S7 `file_key` 연결을 만들지 정한다. 정한 뒤 격리된 시험으로 실제 발동·n8n 처리·원복을 확인한다.
- n8n: 활성 워크플로의 대상 API와 해담 포털 대응 API(`RESPONSE_API_KEY`) 연결 여부 미확인.
- 계획 5절 2~6단계(정상 30분 기준선, 단계 부하, 회복, 수집기 중단·재연결, 반복)는 미실행.
