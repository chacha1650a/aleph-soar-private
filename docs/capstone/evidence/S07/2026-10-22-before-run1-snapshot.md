# 보강 전 #1 시작 직전 스냅샷

- 기록 시각(KST): 2026-10-22 15:05:26
- 기록자: C (shk12170-dev), C 값은 C PC에서 읽기 명령으로 수집
- 시험 ID: before-1 (시험 파일은 A가 생성 후 기록)
- 시험 정의: `team_docs/정량평가-S7-shk12170-dev.md` 3절 #1 (보강 전, 전체 조건 충족 → 공격 성공·로그만·이벤트·티켓 없음 기대)

## 1. 수집 경로

| 항목 | 값 | 출처 |
| --- | --- | --- |
| agent 010 `haedam-portal-vm` | Active, Wazuh v4.9.0, 마지막 keep alive 15:05 무렵 | `agent_control -i 010` |
| A → C | `10.250.0.2:35032 → 10.250.0.3:1514` (팀 VPN) | `Get-NetTCPConnection` |
| C → D | `10.250.0.3:54683 → 10.250.0.100:5514` TCP, 중계 `connected=true received=9 sent=9 dropped=0 queued=0` | `Get-NetTCPConnection`, `docker logs wazuh-tcp-relay` |
| manager 전송 대상 | `gl-graylog`(수업 5140), `gl-graylog`(연습 5514), `wazuh-tcp-relay`(팀 → D) | `ossec.conf` `syslog_output` |
| D 입력 | Wazuh Raw TCP 5514 켜짐, 포털 GELF UDP·TCP 12201, pfSense Syslog UDP·TCP 514 | D 확인(B 공유 표) |
| A 포털 → D | 14:50:05 포털 로그 2건(`web.request`, `web.file_access`) D Graylog 집계 | A·B 공유 |

## 2. 방어 장치 없음 (C)

| 항목 | 값 |
| --- | --- |
| C Graylog 이벤트 정의 / S7·FIM·file_key 관련 | 15 / **0** |
| Wazuh active response 대상 규칙 | `100211,100231`, `100252,100251` (로그인 계열) — **FIM 550·553·554 없음** |
| C n8n 117·S7 워크플로 | 없음(10/22 확인, 수업 워크플로는 게시판 경로·로그인 전용) |

## 3. 방어 장치 없음 (D) — D 답

| 항목 | 값 |
| --- | --- |
| D S7 이벤트 정의 | 없음 |
| D n8n 복구(117) 워크플로 | 없음 |

## 4. 시계 (표준시와 차이)

| C | A VM | D |
| --- | --- | --- |
| 표준시보다 약 0.24초 빠름(time.google.com·kr.pool.ntp.org, 15:05:34) | 시작 조건 충족(A 확인) | Windows 동기화(D 확인) |

## 5. 설정 동결

- 공지 시각: 15:05 스냅샷 직후(C 단톡 공지)
- 해제 시각: 16:14 (D 회신·A 시험 파일 삭제 553 16:05:32 확인 후)
