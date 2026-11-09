# 로컬 단독 실행 (이 PC 한 대)

팀이 PC 두 대에 나눠 돌리던 관제 구성(Graylog·n8n·Wazuh·pfSense)을 이 PC 한 대에서 돌리기 위한 구성입니다. 원본은 `NoBugs-Aleph/aleph-soar-capstone`의 `infra/`·`lab/`·`team_docs/`입니다.

## 구성

| 구성요소 | 실행 위치 | 시작 방법 | 열리는 곳 |
| --- | --- | --- | --- |
| Graylog 6.1.16 + MongoDB + OpenSearch | Docker (`infra/graylog`) | `local/up.ps1` | `127.0.0.1:9000`, 로그 입력은 `BIND_IP` |
| n8n 2.39.5 | Docker (`infra/n8n`) | `local/up.ps1` | `BIND_IP:5678` |
| Wazuh 4.9.0 single-node | Docker (공식 wazuh-docker, `local/wazuh`) | `local/wazuh/setup.ps1` 후 `local/up.ps1` | 대시보드 `127.0.0.1:8443`, agent `BIND_IP:1514/1515`, API `55000` |
| Wazuh → Graylog 중계기 | Docker (`local/wazuh/relay.compose.yml`) | `local/up.ps1` | 내부(`wazuh-net`, `soc-net`) |
| pfSense CE 2.7.2 | VMware VM | [VM-SETUP.md](pfsense/VM-SETUP.md) | VMnet2·VMnet3 |

## 시작 순서

1. `infra/graylog`의 `.env`를 만듭니다(`infra/graylog/README.md`의 실행 순서 1~3).
2. Docker가 WSL2에서 `vm.max_map_count`를 올려 둔 상태여야 합니다(OpenSearch). 오류가 나면 `wsl --system -u root -e sysctl -w vm.max_map_count=262144`.
3. `.\local\wazuh\setup.ps1` (처음 한 번. 인증서 생성과 `syslog_output` 삽입)
4. `.\local\up.ps1` (중지는 `.\local\up.ps1 -Down`)
5. `local/.env`의 `BIND_IP`는 pfSense VM이 닿을 주소(VMnet3 호스트 어댑터 `10.250.0.100`)로 바꾼 뒤 다시 `up.ps1`을 실행합니다. 어댑터를 만들기 전에는 `127.0.0.1`.

## 지금까지 확인한 것과 못한 것

- **확인함**: Wazuh 덮어쓰기 설정이 공식 v4.9.0 compose와 병합되는지 `docker compose config`로 확인했습니다(포트 재배치, 인덱서 포트 제거, `wazuh-net` 연결).
- **확인하지 못함**: 컨테이너를 실제로 띄우지 않았고, Graylog 입력·스트림·파이프라인은 content pack이 없어 화면에서 직접 만들어야 합니다(`infra/graylog/README.md`). pfSense VM·A 포털 VM은 아직 없습니다. n8n 워크플로 반입과 자격 증명 연결도 하지 않았습니다.
- **주의**: 공식 Wazuh 이미지는 기본 계정(`admin`/`SecretPassword`)으로 시작합니다. 이 PC 안에서만 쓰더라도 처음 켠 뒤 바꾸고, 실제 값은 저장소에 넣지 않습니다.
- 메모리: Graylog(약 4GB) + Wazuh(약 4~6GB) + n8n이 RAM 16GB에서 pfSense VM과 함께 돌지 실측하지 않았습니다.
