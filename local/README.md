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

- **11/09 실제 기동 확인 (Wazuh 4.9.0 + 중계기)**: 컨테이너 4개(manager·indexer·dashboard·`wazuh-relay`)가 떴습니다. 인덱서는 GREEN, manager의 `wazuh-apid`·`wazuh-remoted`·`wazuh-authd`·`wazuh-csyslogd`가 실행 중입니다. `55000`은 인증 전 401, 대시보드 `127.0.0.1:8443`은 302로 응답합니다. manager의 실제 경보 2건이 `syslog_output` → 중계기 → `soc-graylog:5514` TCP로 넘어갔습니다(중계기 통계 `received=2 sent=2 dropped=0`).
- **확인하지 못함**: 그 경보가 Graylog 화면의 스트림에 저장·파싱되는지, A의 agent 연결, FIM, pfSense VM, n8n 워크플로 반입은 시험하지 않았습니다. Graylog 입력·스트림·파이프라인은 content pack이 없어 화면에서 직접 만들어야 합니다(`infra/graylog/README.md`).
- **메모리**: Wazuh 기동 후 호스트 여유 RAM이 약 0.4GB(총 15.8GB)였습니다. Docker VM 한도는 8GB입니다. Wazuh(약 2.2GB)+Graylog 스택(약 2.7GB)+n8n+MySQL을 함께 둘 수는 있었지만, pfSense VM까지 켜면 부족할 가능성이 큽니다.
- **Docker Desktop 오류(Windows)**: 비정상 종료로 남은 소켓 파일(`%LOCALAPPDATA%\Docker
un\sailor-ingest.sock`, `%LOCALAPPDATA%\docker-secrets-engine\engine.sock`)을 삭제할 수 없어 시작이 실패했습니다. 두 폴더를 `*.stale-*`로 이름을 바꾸고 새 빈 폴더를 만든 뒤 시작하면 됩니다. 같은 오류가 반복되면 같은 방법을 씁니다.
- **주의**: 공식 Wazuh 이미지는 기본 계정으로 시작합니다. 이 PC 안에서만 쓰더라도 처음 켠 뒤 바꾸고, 실제 값은 저장소에 넣지 않습니다.
- `local/up.ps1`은 이 새 저장소에 `infra/graylog/.env`가 있어야 합니다. 이번 시험에서는 Graylog·n8n이 capstone 폴더에서 이미 떠 있어서 Wazuh와 중계기만 직접 시작했습니다. `up.ps1` 전체 경로는 아직 시험하지 않았습니다.
