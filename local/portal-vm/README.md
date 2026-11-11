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
| 대응 API | `RESPONSE_API_KEY`·`RESPONSE_ALLOWED_CIDRS` 비움 = **꺼짐**. n8n 112·111 연결 시 키를 VM과 n8n 자격 증명에만 넣고 관리망 CIDR을 정해야 함 |
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

- **pfSense를 거치는 접속**: 이 PC는 VMnet11에 직접 붙어 있어서 호스트에서 포털로 가는 요청은 pfSense를 거치지 않습니다. WAN 쪽 출발지(예: Kali VM, 203.0.113.10, 게이트웨이 203.0.113.1)에서 `10.250.0.2:5000`으로 가는 경로와 pfSense WAN 허용 규칙(팀 NR-xx)은 아직 만들지도 시험하지도 않았습니다.
- n8n haedam-15/17에서 S7 AR 호출(이 PC n8n의 Wazuh 자격 증명·주소는 팀 환경 값이라 아직 맞추지 않음).
- 포털 대응 API(112 IP 차단·111 계정 잠금)와 n8n 연결.
- VM 재부팅 뒤 자동 시작(포털·agent).

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
