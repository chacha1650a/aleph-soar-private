# 공격자 VM (Kali 대신 가벼운 Ubuntu, VMnet10)

11/11 사용자 결정: 호스트 여유 RAM이 0.64GB라 실제 Kali(2GB) 대신 이미 받은 Ubuntu 24.04 클라우드 이미지로 RAM 768MB 공격자 VM을 만들었습니다. 팀 환경의 Kali와 도구·주소 역할만 맞춘 실습용입니다.

| 항목 | 값 |
| --- | --- |
| VM | `C:\gov\team-project\_vm\haedam-attacker\haedam-attacker.vmx`(저장소 밖), RAM 768MB, vCPU 1 |
| 주소 | `wan0`(VMnet10, MAC `00:50:56:2a:01:0a`): `203.0.113.10/24`(팀의 Kali 주소, haedam-14 보호 목록) + `203.0.113.22/24`(차단 시험 대상, B 도구가 받는 유일한 주소). `10.250.0.0/24`는 `203.0.113.1`(pfSense)로 라우팅 |
| 도구 | nmap, curl, hydra, hping3 (첫 부팅 때 설치 NIC로 설치, 설치 뒤 NIC 끊고 `startConnected=FALSE`) |
| 접속 | 사용자 `lab`, 키 `%USERPROFILE%\.ssh\haedam_attacker_vm`만 허용 |
| 초기 설정 | `metadata.yaml`·`user-data.yaml`을 base64로 vmx의 `guestinfo.metadata`·`guestinfo.userdata`에 넣음(공개키 자리는 실제 공개키로 바꿔 넣음) |

출발지를 고르는 법: `curl --interface 203.0.113.22 ...`, `nmap -S 203.0.113.22 -e wan0 ...`.

## pfSense 규칙(11/11 추가)

WAN: `LAB WAN to portal 10.250.0.2:5000` — Pass TCP `203.0.113.0/24` → `10.250.0.2:5000`, 로그 켬. Easy Rule 차단 규칙보다 **아래**에 있어야 차단이 먼저 적용됩니다. 출발지를 바꾸는 NAT는 없습니다(팀 규칙 "출발지 IP 보존").

## 11/11 확인한 것

- `.10`·`.22` → pfSense → 포털 `10.250.0.2:5000` 모두 200. 포털 GELF `src_ip`가 `203.0.113.10`·`203.0.113.22`로 남음(출발지 보존 확인).
- B 도구로 `.22` 차단 → `.22`는 포털 접속 시간 초과, `.10`은 계속 200. 해제 → `.22` 다시 200. 도구 응답은 이번에도 `outcome_needs_reconciliation`이라 저널을 `/root/state.json.bak-1111c`로 옮겼고 `status`는 다시 `ok`.

## 못한 것

- 실제 Kali 도구 전체, 팀 S8·S10 시나리오 스크립트 실행, Suricata 팀 규칙(이 VM에는 실습 규칙 2개만).
- 호스트 RAM 여유가 0.7GB 안팎이라 이 VM과 포털 VM·pfSense·Docker 스택을 같이 오래 켜 두면 느려질 수 있습니다. Wazuh 대시보드는 메모리 때문에 꺼 두었습니다(`docker start single-node-wazuh.dashboard-1`로 다시 켬).
