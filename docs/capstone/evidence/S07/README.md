# S7 증적 (C · shk12170-dev)

S7 홈페이지 변조 시험에서 나온 원본 증적입니다. 실측 결과만 둡니다. 비밀번호·agent 키·토큰은 넣지 않습니다.

## 파일

| 파일 | 내용 | 건수 | sha256 |
| --- | --- | --- | --- |
| `2026-10-21-agent009-wsl-alerts.jsonl` | **이관 전 기준.** A WSL 포털 agent 009 `haedam-portal-web`의 경보 전체(접속 501, rootcheck 510 ×2, 디스크 531, **FIM 554 추가·550 변경**, 중지 506). agent 009는 이 파일 저장·대조 후 10/21 16:33 삭제 | 7 | `29846ae47faf8ccc88f9d95ada5a7d639f0564a27d1d2abafbe2c8e49332c9d1` |
| `2026-10-21-agent010-vm-fim-alerts.jsonl` | **최종 포털 VM.** agent 010 `haedam-portal-vm`의 FIM 경보(`dist/zz_fimtest.txt` 554 추가 → 550 변경 → 553 삭제) | 3 | `f3996efed543cf53e4c05ad008ea0dc6314eb1970a729edcffa8ac8acf023ec4` |
| `2026-10-21-agent010-vm-restore-test-alerts.jsonl` | **복원 재시험.** `dist/zz_restoretest.txt` 554 생성 → 550 변조 → 550 복원 → 553 삭제. 복원 경보의 `sha256_after` = 생성 해시(H0 `3fea661b…`), 변조 경보의 `sha256_before` = H0 | 4 | `862eda2f0ccc7ab0d515f0b60cf844be0f86d0f4c0b24d5e4067701ec37aa553` |

## 출처와 추출 방법

- 출처: C PC Docker Desktop의 Wazuh manager 4.9.0(`wazuh-manager` 컨테이너) `/var/ossec/logs/alerts/alerts.json`
- 형식: 한 줄에 경보 하나(JSON Lines), Wazuh 원문 그대로. 시각은 UTC(`+0000`) → KST는 +9시간
- 추출 명령(PowerShell 또는 Git Bash, Git Bash는 앞에 `MSYS_NO_PATHCONV=1`):

```bash
docker exec wazuh-manager sh -c 'grep "\"agent\":{\"id\":\"009\"" /var/ossec/logs/alerts/alerts.json'
```

```bash
docker exec wazuh-manager sh -c 'grep "\"agent\":{\"id\":\"010\"" /var/ossec/logs/alerts/alerts.json | grep "\"syscheck\""'
```

```bash
docker exec wazuh-manager sh -c 'grep "\"agent\":{\"id\":\"010\"" /var/ossec/logs/alerts/alerts.json | grep "zz_restoretest"'
```

- 확인: 009는 저장 시점 manager 원본 7건과 건수 일치, JSON 파싱 정상, 비밀값 문자열 없음

## 환경 (10/21 기준)

| 구분 | 009 (WSL, 이관 전) | 010 (VMware VM, 최종) |
| --- | --- | --- |
| 호스트 | `DESKTOP-B4KEDI4` Ubuntu 24.04.1 (WSL2) | `haedam-portal` Ubuntu (커널 6.8.0-147-generic) |
| 감시 경로 | `/root/haedam/haedam-portal-frontend/dist` | `/home/haedam/haedam-portal-frontend/dist` |
| C 연결 | LAN `192.168.3.7` → `192.168.3.5:1514` | 팀 VPN `10.250.0.2` → `10.250.0.3:1514` |
| FIM 모드 | realtime | realtime |

자세한 경과는 [10/21 작업일지](../../../../work-log/members/shk12170-dev/2026-10-21.md)에 있습니다.
