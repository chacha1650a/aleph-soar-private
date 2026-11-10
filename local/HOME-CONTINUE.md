# 집에서 이어서 작업하기 (11/09 작업 기준)

이 문서는 11/09 학원 PC에서 한 일과, 집 PC에서 이어갈 때 필요한 것을 적습니다. 비밀값(비밀번호·웹훅 주소·키)은 이 저장소에 없으며, 아래 "저장소에 없는 것"은 집 PC에서 새로 만들거나 직접 옮겨야 합니다.

## 11/09에 한 일과 확인한 것

| 항목 | 상태 |
| --- | --- |
| capstone main 전체 복사 + 로컬 실행 구성(`local/`) | 푸시됨 |
| Wazuh 4.9.0 Docker 기동, `syslog_output` → 중계기 → Graylog 5514 | **실제 기동·수신 확인** (중계기 `sent=330` = Graylog 저장 330건, `wazuh_*` 필드 파싱) |
| n8n에 haedam-17 반입(비활성) | 학원 PC n8n에서만 함. 집 PC n8n에는 없음 |
| pfSense VM | **11/10 설치·확인함**(VMnet10/11, WAN `203.0.113.1`, LAN `10.250.0.1`, 방화벽 로그 → Graylog 수신). VM 파일은 저장소 밖 `C:\gov	eam-project\_vm\pfsense`라 집으로 따라가지 않음. 절차·결과는 `local/pfsense/VM-SETUP.md` |
| pfSense 차단 도구(B) | 11/10 설치·전용 SSH 키·`status` 응답 확인. 차단·해제는 실제 적용만 확인(도구 자체 판정은 불확실). n8n haedam-14의 SSH 접속은 인증 로그로 확인, `status` 본문은 미확인 |
| Discord 웹훅 | 학원 PC n8n 자격 증명 `Discord Webhook account`에 직접 입력함. 주소가 채팅에 노출되어 재생성 권장 |
| 시험하지 않음 | `local/up.ps1` 전체 경로, A agent 연결, FIM, 차단 후 `.22` 접속 실패·해제 후 복구, Suricata EVE 전송, n8n에서 block·unblock 호출 |

## 저장소에 없는 것 (집에서 따로 준비)

- `local/.env` — `local/.env.example`을 복사 (`BIND_IP=127.0.0.1`)
- `infra/graylog/.env` — `.env.example`을 복사하고 `GRAYLOG_PASSWORD_SECRET`(64자 이상 무작위)과 관리자 비밀번호 해시를 새로 만든다 (`infra/graylog/set-admin-password.ps1`). 학원 PC의 값을 옮기지 않아도 된다.
- Wazuh 인증서·`local/wazuh/upstream/` — `local/wazuh/setup.ps1`이 만든다 (git 제외)
- n8n 데이터 — 학원 PC 볼륨 `n8n_data`(자격 증명·암호화 키 포함)는 저장소에 없다. 집에서는 새 n8n이 비어 있으므로 워크플로는 `infra/n8n/workflows/`에서 반입하고 자격 증명을 다시 만든다. 반입하면 노드의 자격 증명 연결이 지워지니 `infra/n8n/README.md`의 "반입 뒤 자격 증명 재연결"을 따른다.
- pfSense ISO — `pfSense-CE-2.7.2-RELEASE-amd64.iso`(학원 PC Downloads). 집에서 다시 받는다.
- 학원 PC 백업 `n8n-workflows-backup-1109.json`(워크플로 82개)은 임시 폴더에만 있다. 필요하면 학원 PC에서 직접 복사해 간다.

## 집 PC 준비 순서

1. `git clone https://github.com/chacha1650a/aleph-soar-private.git` 후 `python tools/bootstrap.py`
2. Docker Desktop 설치·실행 (Docker VM 메모리 8GB 이상 권장). Windows에서 소켓 오류가 나면 `local/README.md`의 Docker 오류 대처를 본다.
3. `local/.env`, `infra/graylog/.env`를 만든다 (위 참고).
4. `.\local\up.ps1` — Graylog → n8n → Wazuh → 중계기 순서로 시작한다. **이 스크립트는 전체 경로를 아직 시험하지 않았다.** 막히면 `local/README.md`의 개별 명령을 쓴다.
5. Graylog 화면에서 Wazuh용 Raw TCP 5514 입력과 스트림을 만든다 (학원 PC에서는 기존 설정이 있었음). 입력 설정은 `infra/graylog/README.md`.

## 다음 작업 후보

1. (집에서 pfSense를 쓰려면) VMnet10·11 추가 → pfSense VM 설치 → 차단 도구 설치 (`local/pfsense/VM-SETUP.md`). 이 PC에 전용 SSH 키는 `%USERPROFILE%\.ssh\haedam_pf_n8n`이라 집에서는 새로 만든다
2. n8n 워크플로 반입과 자격 증명 연결 (집 n8n은 비어 있음)
3. A의 포털을 이 PC에서 띄울 방법 결정 (VM 또는 Docker)
4. `local/up.ps1` 전체 경로 시험, Wazuh 기본 계정 변경
5. 원래 capstone 저장소의 PR #142(문서 병합)는 팀 쪽에서 열려 있음

## 주의

- 이 저장소는 공개입니다. 비밀번호·토큰·웹훅 주소·SSH 개인키를 넣지 않습니다.
- RAM이 부족하면 Wazuh dashboard를 먼저 끕니다(`docker stop single-node-wazuh.dashboard-1`).
- n8n·Graylog의 큰 변경은 팀 저장소에서 D 승인 뒤 병합합니다(개인 저장소 변경이 팀 PC에 자동 반영되지 않습니다).
