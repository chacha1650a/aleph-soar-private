# 02. 소유권

파일마다 주인은 **한 역할**뿐이다. 주인이 아닌 사람·에이전트는 수정하지 않고, 필요하면 주인에게 요청한다.

## 역할

| 역할 키 | 이름 | 담당 티켓 | 담당자 |
|---|---|---|---|
| `host` | 호스트 탐지 | INC-01, INC-02, INC-03 | (팀에서 기입) |
| `net` | 네트워크 탐지 | INC-04, INC-05 | (팀에서 기입) |
| `avail` | 가용성·LB | INC-06, MockTel 뼈대 | (팀에서 기입) |
| `docs` | 티켓·문서 | 전체 티켓 검토, 규약, 보고서 | (팀에서 기입) |

역할 키는 브랜치 이름 앞부분과 claim 파일에 그대로 쓴다.

## 경로별 주인

| 경로 | 주인 | 잠금 | 다른 사람이 할 수 있는 것 |
|---|---|---|---|
| `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursorrules`, `.github/` | docs | 잠금 | PR로 제안 |
| `harness/` | docs | 잠금 | PR로 제안 |
| `docs/` (보고서, 플레이북) | docs | – | PR로 제안 |
| `app/mocktel/core/` (앱 생성, DB 연결, 공통 레이아웃) | avail | 잠금 | 수정 금지 |
| `app/mocktel/features/auth.py`, `config_leak.py` | host | – | 수정 금지 |
| `app/mocktel/features/customer_api.py`, `admin.py` | net | – | 수정 금지 |
| `app/mocktel/features/search.py` | avail | – | 수정 금지 |
| `app/requirements.txt`, `app/requirements-vuln.txt` | avail | – | INC-03은 host가 avail에 요청 |
| `detection/wazuh/` | host | – | 수정 금지 |
| `detection/suricata/` | net | – | INC-06 규칙은 avail이 net에 요청 |
| `infra/netplan/`, `infra/ufw/`, `infra/hosts` | docs | 잠금 | 수정 금지 |
| `infra/haproxy/`, `infra/fail2ban/`, `infra/nginx/` | avail | – | 수정 금지 |
| `scenarios/INC-01/` ~ `INC-03/` | host | – | 수정 금지 |
| `scenarios/INC-04/`, `INC-05/` | net | – | 수정 금지 |
| `scenarios/INC-06/` (k6 `load.js` 포함) | avail | – | 수정 금지 |
| `tests/postman/` (MockTel 보안 테스트 컬렉션, secure0·secure1 환경) | net | – | 다른 역할은 테스트 추가를 net에 요청 |
| `tickets/INC-0X/ticket.md`, `evidence/` | 해당 티켓 담당 | – | 수정 금지 |
| `tickets/INC-0X/worklog.md` | 해당 티켓 담당 | – | **덧붙이기만** 허용 |
| `.claims/<티켓>.claim` | claim을 만든 사람 | – | 수정·삭제 금지 |

## 기능 추가 규칙 (MockTel)

- 1~2일차에 avail이 `core/`와 모든 기능 파일의 빈 틀을 만든다. 틀이 main에 머지된 순간부터 각 기능 파일의 소유권은 위 표의 주인에게 넘어간다.
- 새 기능은 `features/` 아래 **새 파일**로 만든다. 기존 파일에 끼워 넣지 않는다.
- 기능 파일은 `core/`가 제공하는 `register(app)` 방식으로만 등록한다. 등록 목록 파일(`core/registry.py`)은 avail만 고친다.
  다른 역할은 "이 파일을 등록해 달라"고 avail에 요청한다.
- DB 테이블은 기능별 접두사를 쓴다. `auth_users`, `cust_customers`, `admin_accounts`, `search_logs`.
  같은 테이블을 두 기능이 같이 쓰지 않는다.

## 잠금 파일을 바꿔야 할 때

1. 바꿀 내용과 이유를 PR 설명이나 메시지로 docs에 보낸다.
2. docs가 직접 바꾸거나 승인한다.
3. 승인 전에는 그 변경에 기대는 작업을 진행하지 않는다.
