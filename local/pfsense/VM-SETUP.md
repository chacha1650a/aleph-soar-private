# pfSense VM 설정 (이 PC 단독 실행)

pfSense는 컨테이너로 돌릴 수 없어 VMware Workstation VM으로 둡니다. 근거는 B의 `lab/pfsense/README.md`·`INSTALL.md`, `team_docs/2026-10-22-D-인수인계.md`, `docs/26-network-allow-table-s1-s10.md`입니다. **아래는 이 저장소의 문서를 이 PC 한 대에 옮긴 계획이며, 아직 만들어서 시험한 것은 없습니다.**

## 망 구성

> **이 PC의 사정(11/09)**: VMnet2가 이미 `172.16.50.0/24`(호스트 .1·.10)로 쓰이고 VMnet3은 없어서, 기존 망은 그대로 두고 VMnet10(`203.0.113.0/24`)·VMnet11(`10.250.0.0/24`)을 새로 만들기로 했습니다. 만들기: 관리자 권한으로 VMware → Edit → Virtual Network Editor → Change Settings → Add Network로 두 개를 Host-only로 추가하고 DHCP·Host virtual adapter 연결 설정을 끕니다. 호스트 어댑터 `VMware Network Adapter VMnet11`의 IPv4는 Windows 네트워크 설정에서 `10.250.0.100/24`로 고정합니다. 아직 만들지 않았습니다.

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
