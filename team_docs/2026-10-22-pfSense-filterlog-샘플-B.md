# D 전달용 pfSense 실제 IPv4 차단 로그 · 10/22

작성: 김명준(B) / 2026-10-22, Asia/Seoul. 사용자 pfSense Command Prompt 출력·원문으로 확보한 실제 로그다. **D Graylog 수신 성공 증거는 아니다.**

## 실제 원문 1건

```text
Oct 22 10:37:41 pfSense filterlog[16869]: 4,,,1000000103,em0,match,block,in,4,0x0,,64,54823,0,DF,1,icmp,84,203.0.113.10,203.0.113.1,request,65230,164
```

조회 명령:

```sh
grep -F '203.0.113.10' /var/log/filter.log | tail -n 5
```

최근 500줄만 검색했을 때는 결과가 없었고 현재 파일 전체 검색에서 위 한 건이 나왔다. 최초 빈 출력만으로 로그 미생성·원격 전송 실패를 판정하지 않았다.

## 파서 대조값

| 항목 | 실제 값 | CSV 0부터 세는 위치 |
| --- | --- | --- |
| rule number | `4` | 0 |
| tracker | `1000000103` | 3 |
| interface | `em0` (WAN) | 4 |
| reason / action / direction | `match` / `block` / `in` | 5 / 6 / 7 |
| IP version | `4` | 8 |
| protocol ID / text | `1` / `icmp` | 15 / 16 |
| packet length | `84` | 17 |
| src_ip | `203.0.113.10` | 18 |
| dest_ip | `203.0.113.1` | 19 |
| ICMP type / ID / sequence | `request` / `65230` / `164` | 20 / 21 / 22 |

CSV 부분은 `4,,,1000000103,...`부터다. 빈 열을 제거하지 않는다. **ICMP ID·sequence를 TCP/UDP 포트로 파싱하지 않는다.** 위 위치는 이 IPv4 샘플용이며 IPv6·다른 프로토콜 분기까지 검증한 것은 아니다.

로컬 syslog 접두부의 `pfSense`는 호스트명이고 `filterlog[16869]`는 프로그램·PID다. 원격 BSD syslog의 접두부·Graylog message 필드는 다를 수 있으므로 `filterlog:`와 `filterlog[PID]:` 형태 및 접두부가 분리된 메시지를 실제 수신 원문과 대조한다. Syslog 전송자의 주소(예상 VPN 서버 `10.250.0.1`)와 CSV의 패킷 src_ip `203.0.113.10`도 분리한다. 실제 전송 주소는 아직 수신으로 확인하지 않았다.

## 시각·연결 검증의 범위

후속 회전 파일 검색에서 확보한 **두 번째 실제 원문**:

```text
/var/log/filter.log.0:Oct 22 10:49:17 pfSense filterlog[16869]: 4,,,1000000103,em0,match,block,in,4,0x0,,64,7724,0,DF,1,icmp,84,203.0.113.10,203.0.113.1,request,65231,164
```

신규 원문의 IP ID는 7724, ICMP ID는 65231, sequence는 164다. B의 해당 ping 실행 구간은 10:49:19.554~10:49:23.349 KST이며 시계 차이는 별도 대조 대상이다. 두 건이 filter.log.0에 남아 있어 현재 filter.log만 검색했을 때 결과가 없었던 원인은 로그 회전으로 확인됐다. D는 message:"203.0.113.10" 검색에 미수신이라고 답했으며, 새 원문의 로컬 생성과 D 실제 수신은 계속 구분한다.

- pfSense 로그 시각: `10/22 10:37:41`(해당 관리 화면의 시간대 KST). BSD 원문 자체에는 연도·시간대가 없다.
- B 호스트 기록의 단일 ping 실행 구간: KST `10:37:44.041~10:37:48.093`. 기록 시각 차이가 있어 NTP 동기화·오차 측정은 별도로 확인한다. 시간대·패킷 ID/sequence 대조 없이 두 기록을 유일한 동일 패킷으로 확정하지 않는다.
- 이 로그로 확인한 것은 WAN에서 해당 출발지의 ICMP echo request를 IPv4 block으로 기록했다는 사실이다. Suricata 경보·S8/S10 탐지·D 수신·자동 대응·원복 성공을 의미하지 않는다.

## D에게 확인 요청

1. D Windows의 UDP 514 수신 허용과 `10.250.0.100:514` 호스트 게시·Syslog 입력 활성 상태를 확인한다.
2. Graylog에서 해당 시각 전후의 `filterlog`, `203.0.113.10`, `1000000103`으로 원문을 찾고 위 필드를 대조한다. 원본 event_id가 있는 포털 로그와 달리 이 샘플은 시각·tracker·양 끝 주소·프로토콜·ICMP ID/sequence로 식별한다.
3. 수신 준비가 이 로그 생성 뒤에 끝났다면 B가 새 시험 패킷을 보내 새 로그로 검증한다. 과거 로컬 파일의 기록이 원격 syslog 설정만으로 자동 재전송된다고 가정하지 않는다.
4. 수신 시 Graylog 메시지 ID·수신 시각·전송자 주소·원문 필드 파싱 결과를 공유한다. 미수신이면 실제 패킷 전달과 입력·Windows 방화벽을 구분해 점검한다.

근거: [Netgate 공식 Raw Filter Log Format](https://docs.netgate.com/pfsense/en/latest/monitoring/logs/raw-filter-format.html). 샘플·추출값은 위 실제 출력이며, 공식 문서는 필드 순서·프로토콜별 차이·원격 BSD 접두부 특성을 대조하는 데 사용했다.
