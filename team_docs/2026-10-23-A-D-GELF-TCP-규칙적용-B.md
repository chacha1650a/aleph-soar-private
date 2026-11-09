# A → D GELF TCP 규칙 정정·적용 결과 · B · 2026-10-23

- 작업: A 요청의 포털 GELF TCP 전환을 위한 VPN 허용 경로.
- 담당: B pfSense 규칙. backend 송신·배포는 A, D 입력·Windows/Docker 수신은 D가 담당한다.
- 상태: **B 규칙 정정·실행 필터 적용 완료. A VM→D 접속과 GELF 수신은 아직 미검증**.
- 변경 위치: B pfSense 기존 OpenVPN 필터 규칙 1개. 코드·공통 API/이벤트 계약·D 서비스·A 배포는 수정하지 않았다.

## 변경 전 확인

15:17:51 KST 직접 읽기 조회에서 `HAEDAM_A_TO_D_GELF_TCP`(tracker **1792636677**)가 이미 있었지만 실제 출발지는 **10.250.0.100**이었다. 목적지도 D `.100:12201/TCP`라 A `.2`를 허용하는 규칙이 아니었다. 기본 차단 위에 있어도 A의 연결에는 매치하지 않는 구성이었다. 오전 timeout의 유일한 원인까지 확정하지는 않는다.

기존 UDP 규칙은 A `.2 → D .100:12201/UDP`, tracker1792632888로 존재했다. 현재 실제 C→D Wazuh TCP5514 허용도 확인됐으며 이번 작업에서 변경하지 않았다.

## 실제 변경·검증

**15:19:25.247855 KST** pfSense 기본 설정 함수로 기존 규칙의 출발지를 **10.250.0.2**로 정정하고 Log를 켠 뒤 실행 필터에 적용했다.

```text
pass in log quick on openvpn inet proto tcp
  from 10.250.0.2 to 10.250.0.100 port = 12201
  flags S/SA keep state
  USER_RULE: HAEDAM_A_TO_D_GELF_TCP
  tracker: 1792636677
```

- IPv4/TCP, A `.2`만 → D `.100` 목적지12201만.
- 기존 규칙 tracker 유지, VPN 기본 차단1792488292보다 앞임을 실행 필터에서 확인.
- `filter_configure_sync(false)` 결과 **0**, `pfctl -sr` 실제 pass/log/source/destination/port 확인.
- 해당 tracker를 제외한 다른 필터 규칙 전후 일치. 기존 UDP·C→D Wazuh·A→C·DB·D NTP·기본 차단 유지.
- OpenVPN 설정·프로세스 PID 전후 일치. 전체 재부팅·VPN 재시작·수동 state flush 없음.
- D 9000/TCP는 변경하지 않았다. 새 측정·포털/GELF 시험 메시지·A 서비스 배포는 실행하지 않았다.

원복이 필요하면 측정 종료·담당 조율 뒤 해당 tracker의 변경 부분만 되돌린다. 원래 출발지 `.100` 규칙으로 복귀하면 A의 TCP 경로는 다시 막힌다는 점을 명시한다. 다른 규칙이나 전체 설정 백업을 덮어쓰지 않는다.

## A·D 다음 확인

> [B→A·D] **A10.250.0.2 → D10.250.0.100:12201/TCP 허용 적용 완료**했습니다(15:19:25 KST, tracker1792636677). 기존 TCP 규칙의 출발지가 D `.100`으로 들어 있어 A `.2`로 정정했고 로그를 켰습니다. 실행 필터에서 기본 차단 위의 pass를 확인했으며 기존 UDP와 다른 팀 경로는 유지했습니다. D의 입력·Windows/Docker 수신 허용 확인 후 A VM에서 접속 시험 부탁드립니다. A 접속과 실제 GELF 도착은 아직 B가 확인하지 않았습니다. D 확인 전에는 현재 UDP를 유지하는 A 계획대로 진행하면 됩니다.

접속 실패 시 A의 시험 시각·목적지·오류와 D 실제 리스너/게시 상태를 받아 해당 tracker의 pass/block과 패킷을 대조한다. B 호스트나 pfSense 자체에서 연결되는 것을 A `.2` 연결 증거로 대신하지 않는다. 400건 도착률·중복 및 장애 시 포털 지연은 전환 후 A/D가 원본 event_id로 검증할 별도 단계다.

## A 구현 보고의 범위

A는 `claude/portal-gelf-tcp` 미배포 브랜치, `GELF_TRANSPORT=tcp` 선택·기본UDP, 요청 큐/별도 송신 스레드, 연결 대기2초·실패 후1회 재연결 뒤 폐기, 테스트45건 통과를 보고했다. 이는 A 보고이며 B가 해당 head/테스트·랩 배포를 검증한 결과는 아니다. 유한 재시도 뒤 폐기하는 정책에서는 TCP도 장애 중 누락이 가능하므로 무손실·장애 후 전량 복구로 보고하지 않는다. 로컬 JSONL 대조와 미관측 분류·재측정 기준은 계속 필요하다.

## 증적

- 변경 전: `C:/Users/user/Documents/Haedam-Handoff/gelf-tcp-rule-before-2026-10-23.json`
- 변경·실행 규칙·보존 확인: `C:/Users/user/Documents/Haedam-Handoff/gelf-tcp-rule-applied-2026-10-23.json`
- 실행 스크립트: `C:/Users/user/Documents/Haedam-Handoff/fix-a-d-gelf-tcp-rule-1023.py`

SSH 키·호스트 검증을 유지한 기존 B 관리 연결을 사용했으며 비밀값·전체 pfSense 설정 백업 원문은 증적에 복사하지 않았다. 팀 메시지는 도구로 발송하지 않았다.
