# A 포털 VM (이 PC 단독, 10.250.0.2)

팀 환경의 "포털 VM 10.250.0.2(Linux, Wazuh agent 010)"을 이 PC의 VMware 실습망(VMnet11) 안에 같은 주소로 재현합니다. 11/11 사용자 결정: Linux VM.

## 구성

| 항목 | 값 |
| --- | --- |
| VM | `C:\gov\team-project\_vm\haedam-portal\haedam-portal.vmx` (저장소 밖). Ubuntu 24.04 클라우드 이미지(`noble-server-cloudimg-amd64.ova`, 20261017, SHA256 `ce599f89…74a2` 공식 값과 일치), RAM 1GB, vCPU 1, 디스크 10GB |
| 네트워크 | `lan0` = VMnet11, MAC `00:50:56:2a:00:02`, `10.250.0.2/24`, 기본 경로 `10.250.0.1`(pfSense). 설치용 `prov0`(VMnet8 NAT, MAC `00:50:56:2a:00:99`)은 설치 뒤 끊고 `startConnected=FALSE` |
| 접속 | 사용자 `haedam`, 비밀번호 로그인 없음, 키 `%USERPROFILE%\.ssh\haedam_portal_vm`(저장소 밖)만 허용 |
| 초기 설정 | cloud-init을 VMware `guestinfo.metadata`·`guestinfo.userdata`(base64)로 전달. OVA 속성(`--prop:user-data`)은 Workstation에서 VM 안으로 전달되지 않아 실패했음 |
| 포털 | 백엔드 `haedam-portal-backend` `98e549c`, 프론트 `haedam-portal-frontend` `994fc45`(이 PC에서 `npm ci && npm run build`). `/home/haedam/haedam-portal-backend`(venv, `pip install -e .`), 웹 루트 `/home/haedam/haedam-portal-frontend/dist`(C의 S7 문서와 같은 경로) |
| 실행 | systemd `haedam-portal`: `waitress-serve --host=10.250.0.2 --port=5000`. 환경값은 `instance/portal.env`(0600) |
| DB | SQLite `instance/haedam.sqlite3` (**팀 계획은 MySQL** — 이 실습 VM만 다름). `seed-demo`로 합성 계정 생성, 임시 비밀번호는 VM의 `instance/demo-accounts.txt`(0600)에만 있음 |
| 이벤트 | GELF UDP → `10.250.0.100:12201`(Graylog `haedam GELF UDP`), `ASSET_ID=haedam-portal` |
| 대응 API | 11/11 켬: `RESPONSE_API_KEY` = 실습 전용 키(호스트 `%USERPROFILE%\.haedam-lab\portal-response-lab.key`와 VM `portal.env`에만 있음), `RESPONSE_ALLOWED_CIDRS=10.250.0.100/32`(n8n이 있는 이 PC) |
| Wazuh agent | 4.9.0-1(hold), ID **010**, 이름 `haedam-portal`, manager `10.250.0.100:1514`, 자동 등록 끔(키는 API `/agents/insert`로 만든 것만 사용). FIM: `dist` 실시간(`realtime="yes" check_all="yes"`) |

스크립트: `provision.sh`(포털 설치·서비스), `agent.sh`(agent 설치·FIM). 키와 비밀값은 스크립트에 없습니다.

## manager 쪽 변경

- `local/wazuh/docker-compose.agent-lan.yml`을 추가해 manager 1514·1515를 `10.250.0.100`에도 엽니다(기존 `127.0.0.1` 유지). VMnet11이 없는 PC에서는 이 파일을 빼고 올립니다.
- Docker가 출발지를 `172.24.0.1`로 바꾸기 때문에 agent 키를 `10.250.0.2` 전용으로 등록하면 `(1213) Message from '172.24.0.1' not allowed`로 거부됩니다. 그래서 ID 010을 **`ip: any`** 로 다시 등록했습니다. 이 PC의 Windows agent(001)에 반복되던 `Invalid ID 001 ... 172.24.0.1` 경고도 같은 원인으로 보입니다(미확인).

## 11/11 확인한 것

- `http://10.250.0.2:5000/api/v1/health` 200, `/` 200, 없는 경로 404.
- Graylog에 GELF 7건(`web.request`, `web.not_found` 등, `source=haedam-portal`) 저장.
- agent 010 연결(`Connected to the server`), 웹 루트에 `assets/zz_lab_fim_1111.txt`를 만들자 약 1초 뒤 Graylog에 Wazuh 554(`File added`) 1건, `wazuh_syscheck_path`·`sha256_after` 파싱, Wazuh 스트림 저장. 시험 파일은 지움.
- 설치 NIC를 끊은 뒤 VM은 인터넷 불가, 기본 경로는 pfSense.

## 확인하지 못한 것

- ~~pfSense를 거치는 접속~~ → 공격자 VM으로 확인함(`local/attacker-vm/README.md`).
- 111 계정 잠금 경로, haedam-17(토큰 발급 분리판)을 거치는 haedam-15 신판 — 이 PC의 haedam-15는 아직 스스로 로그인하는 구판입니다.

## 주의

- **주소 충돌**: 이 학원 PC에서 `10.250.0.2`로 보낸 요청이, VM이 응답하지 않을 때 기본 경로(유선 `192.168.3.1`)를 타고 외부의 다른 `10.250.0.2`로 나가 응답(TTL 55)을 받는 것을 봤습니다. 실습망 대역이 바깥 어딘가와 겹칩니다. VM이 꺼져 있으면 엉뚱한 장비에 요청이 갈 수 있으니, 시험 전 `Get-NetNeighbor -IPAddress 10.250.0.2`가 `Reachable`인지(VMnet11) 먼저 봅니다.
- RAM: pfSense 2GB + 포털 VM 1GB + Docker(Graylog·Wazuh·n8n)로 호스트 여유가 1~2GB 수준입니다.

## 11/11 S7 복구·격리 스크립트 설치와 API 호출 시험

- 설치(C의 `lab/s7/restore` 문서 순서): `/opt/haedam-s7/bin/s7_restore.py`(root 0755, SHA256 `38f238c4…`), `/var/ossec/active-response/bin/s7-restore-ar`(root:wazuh 0750, `d5ddac30…`) — 저장소 파일과 해시 일치. manager 설정은 바꾸지 않음(`!` 명령).
- 기준본: 웹 루트에 `zz_*` 없음 확인 뒤 `baseline` → `files=4 manifest_sha256=158af683…`, `verify` ok.
- 호출: `s7-ar-call.sh <file_key> <run_id>`(이 PC manager API `127.0.0.1:55000`, upstream compose의 기본 시험 계정을 실행 때 읽음, 파일에 비밀값 없음) → `PUT /active-response?agents_list=010` `{"command":"!s7-restore-ar","arguments":[...]}`.
- 결과:
  - 새 파일 `zz_s7_lab01.html` → run `S7-LAB-1111-01` → `quarantine` ok, 웹 루트에서 사라지고 `/var/lib/haedam-s7/quarantine/20261111T031859Z_S7-LAB-1111-01/`로 이동.
  - `index.html` 변조(주석 한 줄 추가, 포털이 그대로 제공함) → run `S7-LAB-1111-02` → `restore` ok, `sha256_after = sha256_expected = 2aca4626…`, 변조 내용 더 이상 제공 안 됨.
  - 시험 격리 항목 `purge`, `verify` ok.
  - Graylog(agent 010): 554 added → 553 deleted(격리) → 550 modified(변조 `6e2467c4…`) → 550 modified(복구 `2aca4626…` = 기준본). 각 단계 1초 안팎.
- 참고: 이 포털은 `dist` 최상위의 임의 `.html`(`zz_s7_lab01.html`)을 처음부터 404로 냈습니다(명시한 정적 파일·라우트만 제공). 공격이 실제로 보이는지는 팀 S7처럼 `assets/` 아래 파일로 시험해야 합니다.
- 팀 차이: 팀은 `n8n-s7` 전용 API 계정(권한 `agent:id:010`의 AR만)을 쓰지만, 이 PC는 기본 관리 계정으로 호출했습니다. n8n 연결 전에 같은 제한 계정을 만들어야 합니다.

## 11/11 대응 API·n8n 연결 시험 (LAB 자격 증명)

사용자 결정: 팀 자격 증명 값과 워크플로 코드는 그대로 두고, **실습용 자격 증명을 따로 만들어 시험하는 동안만 노드 연결을 바꾼 뒤 되돌린다.**

- n8n 자격 증명(이 PC n8n에만, 값은 저장소에 없음):
  - `haedam-portal-response LAB` — Header Auth `X-Response-Key` = 실습 키
  - `wazuh-api LAB (n8n-s7)` — Basic Auth, Wazuh 제한 계정 `n8n-s7`
- Wazuh 제한 계정(팀과 같은 모양): 사용자 `n8n-s7` → 역할 `n8n-s7-ar` → 정책 `n8n-s7-ar-010`(`active-response:command`, `agent:id:010`만). 확인: 이 계정으로 agent 001 AR은 403, 010은 허용.
- 워크플로가 C의 Wazuh API를 `https://10.250.0.3:55000`으로 고정해 부르므로 VMnet11에 `10.250.0.3` 별칭을 붙이고 `local/wazuh/docker-compose.c-alias.yml`로 manager API를 그 주소에도 열었습니다(워크플로는 바꾸지 않음).
- 시험은 n8n CLI로 임시 워크플로를 실행해 Execute Workflow로 팀 워크플로를 불렀습니다: `docker exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n n8n execute --id=<임시 ID> --rawOutput`(서버가 떠 있으면 5679 충돌이라 포트 지정 필요).

결과:

| 경로 | 결과 |
| --- | --- |
| haedam-12 차단(`203.0.113.22`) | 포털 API 성공, `.22`에서 포털 요청 403, `.10`은 200 |
| haedam-12 해제 | `released`, `applied_verified: true`, `.22` 다시 200 |
| haedam-15 격리 `assets/zz_s7_lab02.txt` (run `S7-20261111-LAB01`) | n8n `ok: true, result: applied` → VM 로그 `quarantine ok`(5ms), 공격자에서 404 |
| haedam-15 복구 `index.html` 변조 (run `S7-20261111-LAB02`) | `restore ok`, `sha256_after = sha256_expected = 2aca4626…`, 공격자 응답에서 변조 줄 사라짐 |
| 뒷정리 | 격리 항목 `purge`, `verify` ok(files=4) |

처음 haedam-15 실행은 `wazuh_auth_failed`였습니다. 이 PC의 haedam-15는 haedam-17로 분리되기 전 구판이라 자체 `Wazuh 로그인` 노드가 팀 자격 증명을 쓰고 있었기 때문이며, 그 노드도 LAB으로 바꾼 뒤 성공했습니다.

되돌림: haedam-12·15·17을 시험 전 백업(`%USERPROFILE%\.haedam-lab\n8n-backup\*-before-lab-1111.json`)으로 다시 반입하고 12·15를 다시 게시함. 확인: haedam-12 → `haedam-portal-response`, haedam-15 → `wazuh-api (n8n-s7)`, 둘 다 활성, haedam-17 비활성.

정리: 임시 워크플로 5개(`tmpLab1111H12Blk`·`H12Unb`·`H15Q`·`H15R`·`WzLogin`)는 n8n 화면 세션으로 보관 → 삭제함(남은 것 0개, 팀 워크플로 상태 그대로). LAB 자격 증명 2개는 다음 시험용으로 남겨 둠(어느 노드에도 연결 안 됨).

### 11/11 111 계정 잠금(haedam-13) 시험

같은 방식(시험 동안만 `포털 호출 1·2` 노드를 `haedam-portal-response LAB`에 연결, 백업 `haedam-13-before-lab-1111.json`)으로 n8n에서 haedam-13을 불렀습니다. haedam-13은 **잠금만 자동**이고 해제는 사람이 `POST /accounts/<id>/reset`(새 비밀번호 필요)으로 하는 설계입니다.

| 입력 | n8n 결과 | 포털 DB `users.locked` |
| --- | --- | --- |
| `citizen_demo`, `dry_run` 생략(기본 true) | `dry_run`, 포털 호출 안 함 | 0 그대로 |
| `citizen_demo`, ticket `T-LAB-1111-111`, `dry_run:false` | `applied`(`200 changed:true`), 키 `T-LAB-1111-111-111-citizen_demo-lock` | **1** |
| 같은 입력 다시 | `applied` — 포털이 같은 Idempotency-Key의 저장된 응답을 돌려줌(새 처리 없음) | 1 |
| 다른 ticket `T-LAB-1111-112` | `already_applied`(`changed:false`) | 1 |
| `admin_demo` | `rejected`(`403`, 관리자 계정은 자동 대응 제외) | 0 |

원복: 시험 계정의 비밀번호를 바꾸지 않으려고 `reset` API 대신 VM의 SQLite에서 `citizen_demo`의 `locked`만 0으로 되돌림(실습 VM 한정 조치). haedam-13은 백업으로 다시 반입·게시해 `haedam-portal-response`로 되돌렸고 활성 확인, 임시 워크플로 4개는 삭제함.

확인하지 못한 것: 잠긴 계정으로 실제 로그인이 401이 되는지(시험 계정 비밀번호를 쓰지 않았음 — 코드상 `user.locked`면 401), 기존 세션 회수(시험 때 열린 세션 없음), ~~Graylog의 `auth.account_locked` 이벤트~~ → 아래에서 확인.

## 11/11 오후 확인 (Graylog 실측·재부팅 자동 시작)

Graylog 검색은 OpenSearch에 직접 읽기 질의(`docker exec soc-opensearch curl localhost:9200/graylog_*/_search`, `gl2_receive_timestamp` 기준)로 했습니다.

- n8n S7 시험 경보(agent 010, Wazuh 스트림): 553 격리 삭제 `sha256_after 170b4b6a…`(격리 전 해시와 같음) → 550 변조 `2aca4626…→debaf8dc…` → 550 복구 `debaf8dc…→2aca4626…`(기준본). n8n 실행 뒤 1초 안팎.
- 111 시험: 포털 GELF `auth.account_locked` `username=citizen_demo` 2건(잠금 실행 2번, 같은 키 재요청은 포털이 저장된 응답만 돌려줘 이벤트 없음).
- **포털 VM 재부팅**: `haedam-portal`·`wazuh-agent` 둘 다 enabled, 부팅 직후 agent `Connected to the server`, 포털 health 200(NRestarts=0), `s7_restore.py verify` ok, 공격자 → pfSense → 포털 200.
- **pfSense 재부팅**(Diagnostics에서 `/etc/rc.reboot`, 약 1분): 공격자 → 포털 200, 공격자 SYN → `203.0.113.1:80`에 Suricata `9901102` 경보가 Graylog `suricata Raw TCP`에 들어옴(= Suricata와 `haedam_eve_forward.sh` 자동 시작), 방화벽 로그 Graylog 수신 계속, 차단 도구 SSH 응답. 재부팅 뒤 화면 세션은 끊겨 프로세스 목록은 직접 보지 않음.
- 남은 것: 잠긴 계정 로그인 401 실측(시험 계정 비밀번호 필요), 호스트(Windows) 재부팅 뒤 Docker·VM 자동 시작은 시험 안 함.
