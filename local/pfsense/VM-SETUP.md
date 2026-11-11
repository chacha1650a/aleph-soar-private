# pfSense VM 설정 (이 PC 단독 실행)

pfSense는 컨테이너로 돌릴 수 없어 VMware Workstation VM으로 둡니다. 근거는 B의 `lab/pfsense/README.md`·`INSTALL.md`, `team_docs/2026-10-22-D-인수인계.md`, `docs/26-network-allow-table-s1-s10.md`입니다. **아래는 이 저장소의 문서를 이 PC 한 대에 옮긴 계획이며, 아직 만들어서 시험한 것은 없습니다.**

## 망 구성

> **이 PC의 사정(11/09)**: VMnet2가 이미 `172.16.50.0/24`(호스트 .1·.10)로 쓰이고 VMnet3은 없어서, 기존 망은 그대로 두고 VMnet10(`203.0.113.0/24`)·VMnet11(`10.250.0.0/24`)을 새로 만들기로 했습니다. 만들기: 관리자 권한으로 VMware → Edit → Virtual Network Editor → Change Settings → Add Network로 두 개를 Host-only로 추가하고 DHCP는 끄고 "Connect a host virtual adapter"는 켠 채로 둡니다(호스트 주소 `.100`이 필요합니다). 호스트 어댑터 `VMware Network Adapter VMnet11`의 IPv4는 Windows 네트워크 설정에서 `10.250.0.100/24`로 고정합니다. 11/10에 VMnet10·11을 만들고 호스트 어댑터를 확인했습니다(VMnet10 호스트 `203.0.113.100`, VMnet11 호스트 `10.250.0.100`, VMnet1은 원래 `192.168.229.1`). VM은 아직 만들지 않았습니다.

| 이름 | 용도 | 주소 | 팀 환경과의 대응 |
| --- | --- | --- | --- |
| VMnet10 (호스트 전용, 새로 추가) | WAN 쪽. Kali·정상 클라이언트 | `203.0.113.0/24`, pfSense `.1`, Kali `.10`, 공격 출발지 `.22` | B의 WAN `em0` |
| VMnet11 (호스트 전용, 새로 추가) | LAN 쪽. 팀 VPN 터널을 대신함 | `10.250.0.0/24`, pfSense `.1`, A VM `.2`, Wazuh agent 대상, **호스트(Windows) `.100`** | 팀 VPN 터널 `10.250.0.0/24` |

- VMnet11 어댑터의 호스트 주소를 `10.250.0.100`으로 두면 `infra/n8n`·`BIND_IP`와 pfSense forced command의 `from="10.250.0.100"`이 팀 환경과 같은 값이 됩니다.
- VMware 가상 네트워크 편집기에서 VMnet10·VMnet11의 DHCP를 끕니다. pfSense가 주소를 줍니다.

## VM 사양

- pfSense CE **2.7.2-RELEASE**(B의 도구는 이 버전·WAN `em0`/`203.0.113.1`이 아니면 거부합니다). FreeBSD 64-bit, RAM 1GB, 디스크 8GB, NIC 2개(em0=VMnet10, em1=VMnet11)
- 호스트 RAM이 16GB라 Graylog(약 4GB)·Wazuh(약 4~6GB)·n8n과 합산해 여유를 먼저 확인하세요.

## 설정 순서

1. ISO로 설치 후 콘솔에서 인터페이스를 지정합니다. WAN=em0 `203.0.113.1/24`, LAN=em1 `10.250.0.1/24`. 팀 환경처럼 서비스 주소는 `.2`(A VM)·`.3`(Wazuh)로 맞춥니다.
2. 로그 전송: Status → System Logs → Settings → Remote Logging에서 원격 서버를 `10.250.0.100:514`(UDP)로 정합니다. `infra/graylog`의 입력 `pfSense Syslog UDP`가 받습니다(호스트 514 → 컨테이너 1514). `BIND_IP`가 `10.250.0.100`이어야 pfSense에서 닿습니다.
3. Suricata EVE JSON은 `10.250.0.100:5515`(TCP)로 보냅니다(`infra/graylog`의 5515 입력).
4. 방화벽 규칙은 `docs/26-network-allow-table-s1-s10.md`의 NR-xx를 기준으로 하되, 이 단독 환경에서 필요한 최소만 엽니다: 호스트 `10.250.0.100` → pfSense `10.250.0.1:22`(SSH, 차단 도구), pfSense → `10.250.0.100:514/5515`, A VM `.2` → Wazuh `10.250.0.100:1514~1515`.
5. 차단 도구 설치는 `lab/pfsense/INSTALL.md`를 따릅니다. `python lab/pfsense/install_bundle.py --verify`로 검증 후 pfSense에서 `--install`(도구 한 파일만 게시). SSH는 n8n 전용 새 키만 쓰고 forced command `command="/usr/local/sbin/haedam-pf-response",from="10.250.0.100",restrict`로 제한합니다. 개인키는 저장소에 두지 않습니다.
6. 확인: Graylog에서 `filterlog` 메시지가 들어오는지, Kali(`.10`)에서 `http://203.0.113.1/`이 열리는지 봅니다.

## 아직 모르는 것

- A의 포털 VM(`10.250.0.2:5000`)을 이 PC에서 어떻게 띄울지는 정하지 않았습니다. 앱은 `src/`·`haedam-portal-*` 저장소에 있고, VM 또는 Docker 중 선택해야 합니다.
- pfSense VM의 실제 규칙 수와 Suricata 패키지 설정은 B의 장비 설정에 있고 이 저장소에는 없습니다. B에게 설정 내보내기(`config.xml`, 비밀 제거)를 받아야 같은 규칙을 재현할 수 있습니다.

## 11/10 실제 확인한 것

- pfSense VM(`haedam-pfsense-2.7.2`, em0=VMnet10 WAN `203.0.113.1/24` static, em1=VMnet11 LAN `10.250.0.1/24`)을 만들어 설치했습니다. 호스트에서 LAN ping과 웹 화면(80)이 열립니다.
- WAN 업스트림 게이트웨이가 `255.255.255.0`으로 잘못 들어가 있어 `None`으로 바꾸고 `WANGW` 항목을 지웠습니다. WAN의 "Block bogon networks"가 켜져 있으면 `203.0.113.0/24`(문서용 대역)가 막히므로 해제해야 합니다.
- 원격 로그(`10.250.0.100:514` UDP, Firewall Events)가 Graylog에 도착합니다. 호스트에서 보낸 시험 패킷과 pfSense `filterlog` 메시지가 저장소에서 확인됩니다(수신 시각 `gl2_receive_timestamp` 기준 59건).
- **주의:** pfSense가 보내는 시각에는 시간대가 없어 Graylog(`Asia/Seoul`)가 9시간 앞서 `timestamp`로 저장합니다(수신 09:29 UTC → 메시지 시각 00:29 UTC). 검색은 수신 시각으로 하거나 시간 범위를 넓혀야 합니다. 탐지 규칙의 시간 조건에 미치는 영향은 확인하지 않았습니다.
- 아직 안 한 것: Suricata EVE 전송(5515), forced command SSH 키와 B의 `haedam-pf-response` 설치, 차단·해제 시험.

## 11/10 차단 도구 설치와 첫 시험 (확인한 것과 못한 것)

- B의 번들을 `tools/build_pfsense_bundle.py`로 만들고 `--verify` 통과(도구 SHA `f0eea297...3553ed`). pfSense에 `scp`로 복사해 `--install`하고, `/usr/local/sbin/haedam-pf-response`의 해시·권한(root, 0750)을 확인했습니다.
- n8n 전용 ed25519 키를 만들고(개인키는 `%USERPROFILE%\.ssh\haedam_pf_n8n`, 저장소 밖) `admin`의 Authorized SSH Keys에 `from="10.250.0.100",restrict,command="/usr/local/sbin/haedam-pf-response"` 제한으로 등록했습니다. 명령은 `haedam-pf-response ...`로 시작해야 합니다(아니면 `invalid_ssh_command`).
- 확인됨: 키 로그인, `.22` `status` 성공(`rule_present:false`), `id` 같은 임의 명령은 거부, 다른 대상(`.50`)은 `target_not_approved`.
- **불확실한 결과**: `block` 요청이 `outcome_needs_reconciliation`으로 끝나(설정 반영·실행 규칙 미반영), 같은 ID 재전송은 `replay_needs_reconciliation`, 새 ID `unblock`도 불확실로 끝났습니다. 이후 pfSense에는 빈 `EasyRuleBlockHostsWAN` 대상의 `block drop in` 규칙만 남은 것으로 보이며(콘솔 확인), 저널에는 pending이 남아 `status`가 `pending_needs_reconciliation`을 반환합니다. 원인은 확인하지 못했습니다(규칙 반영 지연 추정).
- **하지 못한 것**: 차단 후 `.22` 접속 실패·해제 후 복구 확인(이 PC에 `.22` 주소·시험 출발지 없음), pending 정리, n8n haedam-14 연결.

## 11/10 차단·해제 두 번째 시험 (같은 결과 재현, 실제 적용은 확인)

- 저널(`/cf/conf/haedam-pf-response/state.json`)과 Easy Rule 규칙·alias를 정리한 뒤 새 소유자·새 요청 ID로 다시 시험했습니다.
- `block`: 도구는 `outcome_needs_reconciliation`(`rule_present:false`)으로 답했지만, 직후 pfSense 콘솔에서 `pfctl -sr | grep EasyRule`에 `block drop in quick on em0 ... from <EasyRuleBlockHostsWAN>` 규칙이 있고 `pfctl -t EasyRuleBlockHostsWAN -T show`에 `203.0.113.22`가 있음을 확인했습니다. **실제 차단은 적용됐고, 도구가 EasyRule 직후 너무 일찍 읽어 불확실로 판정한 것으로 보입니다(추정).** 첫 시험과 같은 결과여서 이 VM(RAM 1GB, 단독 구성)에서 재현됩니다.
- `unblock`(새 요청 ID, 같은 소유자): 도구는 다시 불확실로 답했지만 테이블에서 `.22`가 빠진 것을 콘솔에서 확인했습니다. 빈 규칙은 남아 있고, 도구 상태는 `configured:false, rule_present:true, table_present:false`, `status`는 `pending_needs_reconciliation`입니다.
- 못한 것: 차단 후 `.22`에서의 접속 실패·해제 후 복구 확인(이 PC에 `.22` 주소가 없음), 도구가 일찍 읽는 원인 확정, n8n haedam-14 연결. 도구의 `applied_verified`는 두 번 모두 `false`였으므로, 이 도구 자체의 성공 판정으로는 시험이 통과하지 못했습니다.
- 시험 뒤 정리(운영자 작업): Easy Rule 규칙·alias 삭제, 저널 `state.json`을 `/root`로 이동. 이 VM에서만 쓴 방법이며 팀 환경에서는 도구 문서대로 대조합니다.

## 11/10 n8n(haedam-14) → pfSense SSH 연결

- n8n SSH 자격 증명 `haedam-pf-response D`(Private Key, host `10.250.0.1:22`, user `admin`, passphrase 없음)를 만들어 haedam-14에 연결했습니다. 개인키는 저장소에 없습니다.
- 첫 실행은 n8n이 키를 해석하지 못해 실패했습니다(n8n 로그 `USERAUTH_FAILURE`, pfSense 로그 `[preauth]` 끊김, 접속 출발지는 `10.250.0.100`으로 보여 `from=` 제한은 문제가 아니었음). 키를 다시 붙여 넣은 뒤 pfSense 로그에 `Accepted publickey for admin from 10.250.0.100 ... ED25519 SHA256:v2k32W0Li9...`가 기록됐습니다.
- 위 성공은 pfSense 인증 로그로 확인했고, 도구의 `status` 응답 본문(`stdout`)은 n8n 화면에서 직접 보지 못했습니다. 같은 시각에 `[preauth]` 실패 줄이 하나 있어(재시도 또는 이전 실행 추정) 정확한 원인은 확인하지 못했습니다.
- 이 시험은 `status`(읽기)만 했고 `block`·`unblock`은 n8n에서 호출하지 않았습니다. 시험용으로 고정한 입력 데이터는 해제해야 합니다.

## 11/11 `.22` 차단·해제 효과 시험 (실제 접속으로 확인)

- 준비: 이 PC의 VMnet10 어댑터에 시험 출발지 `203.0.113.22`를 별칭으로 추가하고, pfSense WAN에 임시 허용 규칙 `TEMP effect test 1111`(TCP, 출발지 `203.0.113.0/24`, 목적지 This Firewall:80)을 Easy Rule 차단 규칙 **아래**에 두었습니다. 처음에 맨 위에 들어가 순서를 바꿨습니다(위에 있으면 차단해도 통과함).
- 기준선: `.22` → `203.0.113.1:80` 접속됨, 대조 `.100`도 접속됨.
- `block`(새 요청 ID): `.22` 접속 **실패**, `.100` 접속 **유지**. 도구 응답은 다시 `outcome_needs_reconciliation`.
- `unblock`(같은 소유자, 새 요청 ID): `.22` 접속 **복구**, `.100` 유지. 도구 응답은 다시 불확실, `status`는 `pending_needs_reconciliation`.
- 결론: 차단·해제의 **실제 효과와 대조 출발지 무영향은 확인됨**. 도구의 자체 판정(`applied_verified`)은 세 번의 시험 모두 `false`로, 적용 직후 읽기 시점 문제로 보이며(추정) B와 공유가 필요합니다.
- 정리: 임시 규칙은 비활성화(Disabled)만 했습니다(이 브라우저 창에서 삭제 확인 창이 열리지 않음). WAN은 다시 닫힘(`.100` 접속 불가 확인). 남은 일: 임시 규칙 삭제, `.22` 별칭 제거(관리자 권한), 도구 저널 `state.json` pending 정리(root 쉘).
- 참고: pfSense 시계가 실제 UTC보다 약 9시간 빠르게 표시됩니다(VM 재부팅 뒤 확인, 원인 미확인). `admin` 기본 비밀번호 경고가 떠 있습니다.

