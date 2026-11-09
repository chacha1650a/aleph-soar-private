# B Suricata 준비 · A 없이 진행할 관측·로그 점검

작성: 2026-10-22 / 김명준(B). 준비 절차와 후속 실제 결과를 함께 기록한다. **WAN ICMP 시험 경보 1건까지 확인했으며 S8/S10·자동 대응 완료 기록은 아니다.**

## 1. 이번 작업의 끝점

A 포털이 꺼져 있어도 B Kali의 패킷을 B pfSense에서 관측하고, 시험 경보를 D Graylog에서 원본과 대조할 준비를 한다. 처음에는 탐지 전용으로 확인하고 IPS 자동 차단·S8/S10 전체 공격·부하 시험은 별도 단계로 둔다.

최신 확인: Suricata 패키지 `7.0.8_1` 설치, WAN IDS 실행, 시험 SID `9901022`의 실제 ICMP 경보 1건까지 확인했다. 사용자는 Low 선택을 보고했고 오프로딩 Disable 세 항목 체크 화면과 재부팅 후 재로그인을 전달했다. 실제 NIC 플래그 조회·S8/S10 시나리오·D 경보 수신·자동 대응은 미검증이다. 최초 관리 화면 인증서 처리는 사용자가 직접 완료했다.

## 2. 읽기 점검 순서

pfSense 관리 화면에 접근한 뒤 다음을 확인한다. 기존 서비스·설정을 저장하거나 재시작하지 않고 먼저 기록한다.

| 위치 | 읽을 항목 | 확인값 |
| --- | --- | --- |
| System → Package Manager → Installed Packages | Suricata 설치 유무·패키지 버전 | 이후 설치 성공 화면 확인, 설치 선택 버전 7.0.8_1·엔진 7.0.8 |
| Status → Dashboard | pfSense 버전·메모리·CPU·디스크 | 오늘 재부팅 후 CE 2.7.2·관리 화면 복귀 확인. 자원은 센서 실행 전 재확인 |
| Services → Suricata | 실행 인터페이스·IDS/IPS·자동 차단·규칙·로그 설정 | WAN 실행 녹색 체크·Blocking DISABLED 확인. 시험 SID 9901022 실제 경보 확인. Low 선택은 사용자 보고 |
| Status → Interfaces | WAN em0 `203.0.113.1`, LAN em1, WORK em3, TRANSIT em4 현재 연결 | 마지막 토폴로지와 대조 필요 |
| Status → OpenVPN | 팀 서버·실제 접속자·주소 | 재부팅 후 C .3·D .100 연결 화면 확인. A 복귀 후 현재 연결은 별도 확인 |
| Status → System Logs → Settings | 기존 원격 syslog 목적지·포트·전송 범주 | 기존 대상을 지우지 않고 D 정보와 대조 |

설치가 안 되어 있으면 호환 패키지 저장소·업데이트 통신·여유 자원을 먼저 확인한다. pfSense 전체 업그레이드·NIC 변경·광범위 방화벽 허용을 설치 준비에 섞지 않는다. 09시 B 호스트 여유 RAM은 약 0.46GiB였으므로 신규 부하 전 수업 스택의 오늘 사용 여부를 정리한다.

## 3. 첫 관측 지점과 네트워크 변수

```text
Kali 203.0.113.10 → WAN(em0) 203.0.113.1:80
                            ↓ 목적지 NAT
                        VPN → A 10.250.0.2:5000
```

- 첫 센서 후보는 **WAN(em0)**. 실제 패킷 캡처로 관측 위치를 확인한 뒤 확정한다.
- WAN 관측 예상 목적지는 공개 주소 `203.0.113.1:80`이다. A VPN 주소와 port 5000은 NAT 이후 값이므로 같은 튜플로 가정하지 않는다.
- HOME_NET은 설치된 패키지가 실제로 감시하는 주소와 일치하는지 확인한다. 과거 `10.10.10.10`만 보호 대상으로 남기면 현재 공개 경로의 규칙이 맞지 않을 수 있다.
- EXTERNAL_NET·PASS_LIST·SUPPRESS 설정에서 실제 Kali 출발지가 제외되는지 확인한다. 처음부터 전체 대역을 바꾸지 말고 기존 규칙 범위와 시험 규칙 매치를 대조한다.

이는 현재 토폴로지에 근거한 설정 검토 항목이다. 실제 패키지 옵션명·자동 생성값·캡처 방식은 설치 버전 화면을 보고 기록한다.

## 4. A 없이 가능한 최소 시험안

패키지·관측 인터페이스·탐지 전용 상태를 확인한 뒤, **Kali → pfSense WAN ICMP echo 1개**로 센서 경로를 확인한다. 포털·DB·팀 VPN 대상에는 요청을 보내지 않는다.

1. 패킷 캡처를 WAN(em0), 호스트 `203.0.113.10`, ICMP로 제한한다.
2. 아래 시험 규칙의 sid가 기존 규칙과 충돌하지 않는지 확인하고 로컬 규칙에 넣어 문법·로드 결과를 확인한다. 기존 공급자 규칙 파일을 덮어쓰지 않는다.
3. Kali에서 `ping -n -c 1 -W 2 203.0.113.1` 한 번만 실행한다.
4. 패킷 캡처의 echo request와 Suricata 경보의 시각·src_ip·목적지·sid를 대조한다.
5. ICMP 응답이 없더라도 패킷 수신·경보 발생을 따로 판정한다. 현재 방화벽이 echo를 허용한다고 가정하지 않는다. 경보가 없으면 캡처·로드·실행 상태부터 확인한다.
6. 시험 후 시험 규칙·캡처를 정리하고 기존 센서 상태와 부작용 유무를 확인한다.

**아래는 미적용 시험 규칙 후보다. 설치 버전의 구문 검사 전에는 동작 보장하지 않는다.**

```text
alert icmp 203.0.113.10 any -> 203.0.113.1 any (msg:"HAEDAM LAB B SENSOR PATH CHECK"; itype:8; sid:9901022; rev:1;)
```

이 규칙은 정상 ICMP로 센서가 동작하는지 확인하는 용도다. 공격 탐지·스캔 탐지·S8/S10 성공 증거로 세지 않는다. n8n 자동 대응 대상에서도 시험 경보를 제외하고 수신 확인에만 사용한다.

## 5. D에게 전달할 실제 로그 정보

| 제공 항목 | B 확인·D 대조 내용 |
| --- | --- |
| 송신 경로 | pfSense가 실제로 내보내는 방식·출발지 주소·D 목적지·UDP/TCP·호스트 포트 |
| 원본 구분 | Suricata 경보와 pfSense filterlog는 다른 소스. 방화벽 pass/block 로그를 NIDS 경보로 바꾸지 않음 |
| EVE 사용 시 | `timestamp`, `event_type`, `src_ip`, `dest_ip`, `proto`, `alert.signature_id`, `alert.signature`, `alert.action`, 있으면 `flow_id`·포트·인터페이스 |
| 실제 포맷 | EVE JSON/Suricata syslog/fast.log 중 무엇인지 확인하고 샘플 구조에 맞춰 D가 파싱 |
| 시험 식별 | 시험 sid·메시지·KST/UTC 시각·공격 아님 표시 |
| 완료 증거 | B의 원본 경보 1건과 D 검색의 동일 경보. UDP 송신·포트 게시만으로 수신 성공 표시하지 않음 |

pfSense 기본 원격 syslog는 UDP이며 `주소:포트`를 사용할 수 있다. 포트 생략 기본값은 514다. **D의 실제 호스트 수신 포트를 사용**한다. B 수업 Graylog의 오늘 게시값은 1514/UDP, 12201/TCP·UDP, 9000/TCP지만 D 구성의 값이 아니다. pfSense Firewall Events 원격 전송만 켜면 Suricata EVE도 전달된다고 가정하지 않는다.

## 6. 차단·해제 준비와 분리할 것

- 나중에 n8n→pfSense 자동 대응 시험을 할 때는 실제 호출자·기존 권한·보호 대상·차단 대상 `/32`·해제 경로부터 확인한다.
- EasyRule 후보는 `easyrule block wan <시험 IP>` → `easyrule showblock wan` → 효과 확인 → `easyrule unblock wan <같은 IP>`다. 오늘 실행하지 않았다.
- `unblock`은 EasyRule이 만든 차단만 해제하므로 다른 수단으로 만든 차단의 공통 해제 명령으로 사용하지 않는다.
- 기존 state가 있으면 차단 규칙만 추가해도 기존 연결이 이어질 수 있다. 대상 연결만 골라 처리할 방법과 관리·정상 사용자 연결 보존을 검토한다. 전체 state 초기화는 시험 기본 동작으로 삼지 않는다.

## 7. 완료 기록 양식

```text
날짜·시각(KST/UTC):
pfSense / Suricata 패키지·엔진 버전:
감시 NIC / IDS·IPS / 시험 전 자동 차단 상태:
시험 출발지·목적지 / 명령·횟수:
WAN 캡처 관측: 미실행 / 관측 / 미관측
규칙 로드·sid / 실제 경보:
원본 경보 필드 / D 수신·검색 ID:
자원 사용·누락/오류:
시험 규칙 정리·기존 설정 유지 확인:
미검증·다음 작업:
```

현재 기록: 아래 후속 결과처럼 최소 센서 시험 경보 1건을 확인했다. pfSense filterlog의 D 수신 성공과 Suricata 경보의 D 수신은 별도이며, 후자는 미검증이다.

### 후속 실제 시험 결과 · 11:56

- custom.rules가 빈 상태에서 위 시험 규칙 1개를 입력·Save했다. 별도 성공 배너는 없었고 실제 경보로 적용을 확인했다.
- B의 실제 Kali 203.0.113.10에서 `ping -n -c 1 -W 2 203.0.113.1` 1회를 실행했다. B 호스트 KST 실행 구간은 11:56:29.934~11:56:33.555이며 ping 응답은 없었다.
- 사용자 Alerts 화면에서 WAN HAEDAM_WAN_IDS, **11:56:26 / ICMP / 203.0.113.10 → 203.0.113.1 / 1:9901022 / HAEDAM LAB B SENSOR PATH CHECK** 1건을 확인했다. 센서 경로·해당 규칙의 탐지 확인이다. 방화벽 ping 차단과 IDS 경보는 별도다.
- 입력 증적: `C:/Users/user/Documents/Haedam-Handoff/suricata-probe-1022.txt`. 경보 캡처: `C:/Users/user/Documents/Haedam-Handoff/suricata-alert-9901022-1022.png`.
- 시계 차이로 MTTD는 계산하지 않는다. S8/S10 공격·다중 신호 상관·D Suricata 수신·n8n 자동 대응·정상/부정 대조는 미검증이다.
- 시험 규칙 한 줄을 제거한 빈 custom.rules 화면과 저장 후 Interfaces 화면을 사용자에게 받았다. WAN(em0) 센서 실행 녹색 표시·Blocking Mode DISABLED 유지를 확인해 시험 규칙 정리를 완료했다. 삭제 뒤 새 입력의 미발동 대조는 수행하지 않았다.
- 마무리 화면 증적: `C:/Users/user/Documents/Haedam-Handoff/suricata-after-rule-cleanup-1022.png`. 완료 범위는 시험 규칙 적용·실제 경보·규칙 삭제/저장·센서 상태 유지다. 공격 대응·원복 완료를 의미하지 않는다.

설치 전 확인 이력: 사용자 Available Packages 캡처에 `suricata 7.0.8_1`, 의존 엔진 `suricata-7.0.8`과 Install 버튼이 보였다. 당시 B 호스트 여유 RAM은 약 0.81GiB, pfSense VMX는 RAM 2048MB·vCPU 2였다. 이후 센서 시험 준비 때의 호스트 여유 RAM 재측정은 약 2.19GiB였다.

## 근거

- [Netgate IDS/IPS](https://docs.netgate.com/pfsense/en/latest/packages/snort/index.html): pfSense의 Snort·Suricata 패키지와 설정 참고 범위.
- [Netgate 원격 syslog](https://docs.netgate.com/pfsense/en/latest/monitoring/logs/remote.html): UDP·목적지 포트·전송 범주.
- [Suricata 공식 EVE 포맷](https://github.com/OISF/suricata/blob/main/doc/userguide/output/eve/eve-json-format.rst): 경보의 필드·signature 식별. 현재 upstream 문서이며 설치 버전의 출력과 대조한다.
- [Suricata 7.0.12 규칙 형식](https://docs.suricata.io/en/suricata-7.0.12/rules/intro.html)·[ICMP 키워드](https://docs.suricata.io/en/suricata-7.0.12/rules/icmp-keywords.html): 시험 규칙 후보의 형식. 실제 설치 버전에서 별도 로드 검증한다.
- [Netgate EasyRule](https://docs.netgate.com/pfsense/en/latest/firewall/easyrule.html): 차단·목록·해제의 범위.
- [Netgate 방화벽 진단](https://docs.netgate.com/pfsense/en/latest/troubleshooting/firewall.html): state·로그·패킷을 구분한 진단.
