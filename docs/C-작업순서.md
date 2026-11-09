# C 담당 작업 진행 순서 — S7 홈페이지 변조

> 담당: shk12170-dev · 자리 C (무결성) · 탐지 경로: Wazuh FIM + 포털 파일 접근 → Graylog
> 공통 기반: Wazuh manager·FIM·agent 등록, 프로젝트 보안 대시보드·티켓 (Wazuh 제품 대시보드와 별개)
> 실행 환경: C PC **Docker Desktop(WSL2)** 의 Wazuh manager. Graylog·n8n은 **D PC**, 포털·agent는 **A의 Ubuntu VM**, 연결은 B의 팀 VPN(10/21 인수인계 기준)
> 기준 문서: [기획서 합의본](../team_docs/기획서_합의본.md) ③ 117·④ S7·⑤ 5.2~5.10, [S7 작업 방향](../작업방향-S7.md), [Graylog 셋팅 작업지시](../team_docs/2026-10-20%20Graylog%20셋팅%20작업지시.md), C Wazuh 인수인계(`team_docs/2026-10-21-C-Wazuh-인수인계.md`, 10/21 현재 main에 없음), [S7 참고자료](s7-draft/README.md), [C 자리 확인](s7-draft/C자리-S7-확인.md), [토폴로지 C](../team_docs/토폴로지-C-S7-홈페이지변조.png)
> 작업 기록: `work-log/members/shk12170-dev/YYYY-MM-DD.md`
> 랩 시험은 아직 하지 않았습니다. 로컬 파일 시험과 C PC 연습 환경 결과만 ✅로 표시합니다.

## 상태 표시

| 표시 | 뜻 |
| --- | --- |
| ✅ | 완료 (직접 확인한 것만) |
| 🔄 | 진행중 |
| ⬜ | 미완료 |

## 진행 순서 한눈에 보기

```
① C 환경 점검·공유 ─▶ ② A agent 등록(첫 공동 목표) ─▶ ③ A 실제 웹 루트 realtime FIM
        ─▶ ④ C manager → D Graylog 경보 전달·필드 확인 ─▶ ⑤ 사전 시험 P1~P5
        ─▶ ⑥ 보강 전 1회 ─▶ ⑦ 상관 규칙·수동 복구 → n8n 자동 복구·티켓 ─▶ ⑧ 검증 → 시연
```

각 단계는 앞 단계가 확인돼야 시작합니다. 문서·계약(2·3번)과 C PC 연습 환경 시험은 언제든 병행합니다.
첫 공동 목표는 **A agent의 파일 변경 경보를 C가 실제로 받는 것**이고, S7 완료는 같은 자산·`file_key`의 웹 접근 상관·대응·티켓·효과·원복 확인까지입니다.

## 팀 구성 (10/21 인수인계 기준, 10/22 갱신)

```
 [A] Ubuntu VM                     [C] 내 PC (Docker Desktop)            [D] PC
 포털 dist + Wazuh agent ─1514/1515─▶ Wazuh manager 4.9.0 ─중계·TCP 5514─▶ Graylog ─▶ n8n
                                          ▲                                           │
                                          └──────────── 55000 (Wazuh API) ────────────┘
                         모든 경로는 B의 팀 VPN(터널 10.250.0.0/24)을 지남
```

| 구성 | PC | 주소·이름 | 필요한 포트 | 정하는 사람 | 상태 (10/22) |
| --- | --- | --- | --- | --- | --- |
| Wazuh agent | A **VMware VM** `haedam-portal`(NAT + 팀 VPN `10.250.0.2`) | **010 `haedam-portal-vm`**, 4.9.0, 수동 키, 자동 등록 끔 | (발신) → C `10.250.0.3:1514` | A | **Active, VPN 경로** (10/21 16:24). WSL 009는 증적 저장 후 삭제 |
| 감시 폴더 | A VMware VM | `/home/haedam/haedam-portal-frontend/dist` (realtime) | — | A | 554·550·553 수신(16:30), 복원 재시험 통과(16:47, after = 처음 해시) |
| 포털 자산 | A | `asset_id haedam-portal`(10/22 포털 `web.file_access` 원본에서 확인) | — | A·D | agent `haedam-portal-vm` ↔ `haedam-portal` 대응은 D 규칙에서 확정 |
| Wazuh manager | C | 팀 VPN **`10.250.0.3`**(team-c), 유선 `192.168.3.5` | `1514/tcp`(수집), `1515/tcp`(등록) | C·B | pfSense A `10.250.0.2` → C TCP 1514~1515 허용(10/21), 010 이 경로로 Active. Windows 방화벽 출발지 제한은 미적용 |
| Wazuh API | C | 위와 같음 | `55000/tcp` | C·D | **미공개**, n8n용 계정 없음 |
| Graylog | D | **`10.250.0.100`**(team-d) | Wazuh 입력 **Raw TCP 5514**(UDP 5514는 1,400B 초과 유실로 사용 안 함) | D·B | C 중계 `wazuh-tcp-relay` → TCP 연결, pfSense `HAEDAM_C_TO_D_WAZUH_TCP` 허용(10/22). 550·553·554 수신 확인 |
| n8n | D | 미정 | — | D | — |
| 팀 VPN | B 서버 | `HAEDAM_TEAM_TRANSIT` UDP 1195, 터널 `10.250.0.0/24`(서버 `.1`) | — | B | A `.2`, C `.3`, D `.100` 연결. PC 사이 통신은 팀 VPN으로만(기획서 ③) |

### 연결할 때 주의할 점

1. **Docker 이름은 다른 PC에서 쓸 수 없습니다.** `gl-graylog` 같은 컨테이너 이름은 C PC 안에서만 통합니다. C → D는 D PC의 실제 주소와 D가 공개한 포트로 보냅니다.
2. **Wazuh `syslog_output`은 UDP로만 보내지만, 1,400B를 넘는 UDP는 C → D 경로에서 유실됩니다(10/22 크기별 시험: 1300B 3/3, 1500·2000B 0/3).** 550(약 2,078B)이 빠지는 원인이라, C PC 안에서 UDP를 받아 D에 **TCP로 넘기는 중계 `wazuh-tcp-relay`**(`lab/s7/relay/`)를 둡니다. D 입력은 Raw/Plaintext **TCP**.
3. **Windows 방화벽.** 다른 PC에서 C의 1514·1515·55000으로 들어오려면 인바운드 허용이 필요합니다. 10/21 현재 Docker Desktop 프로그램 허용(Public 프로필)만 있고 포트·출발지 규칙은 없습니다. 실제 A·D 출발지만 허용합니다(방화벽 변경은 본인이 직접).
4. **VPN 연결 ≠ 서비스 연결.** Windows에서 VPN이 붙어도 A VM이나 C의 Docker 서비스가 연결되는 것은 아닙니다. B가 경로·허용 규칙을, C가 포트 공개·방화벽·수신 주소를 맞춥니다.
5. **메모리.** C PC에는 Wazuh 전체(manager·indexer·dashboard)와 수업 Graylog, n8n, MySQL이 같이 떠 있습니다(10/21 약 5.2/7.7GiB). 팀 구성에서 C PC의 수업 Graylog를 끌지, Wazuh 제품 대시보드(agent 확인 화면)를 남길지 정합니다.
6. **시간대·시계.** 컨테이너는 `TZ=Asia/Seoul`, Wazuh syslog 머리글 시각은 UTC입니다. 판정은 `wazuh_timestamp` 또는 Graylog `timestamp`로 합니다. **10/21: C Windows 시계가 NTP보다 약 9.7초 빠름**, 시험 도중 Docker VM 시계가 약 10초 뒤로 보정되어 경보 시각 순서가 뒤바뀜 → 11:22 Windows 동기화 후 NTP 차이 ±0.005초, Docker와 0.07초. A·D PC도 같은 NTP 확인 필요.

### C PC 연습 환경 (10/20 구성, 팀 구성과 별개)

| 구성 | 값 |
| --- | --- |
| Graylog | 수업 compose `9_graylog`(`gl-*`, 6.1.16), 웹 `0.0.0.0:9000` |
| Wazuh | 수업 compose `wazuh-lab` 4.9.0(`...\Python-Lab-ALeph-T\_10_wazuh\docker.compose.yml`), 설정 볼륨 `wazuh-lab_wazuh_etc` |
| 경로 | manager 자체 FIM `/tmp/zz_fim_test` → `gl-graylog:5514`(같은 Docker 네트워크) → 입력·스트림 `wazuh-alerts` → 파이프라인 `wazuh-parse` |
| 수업 설정 보존 | 수업용 `syslog_output`(5140, rule_id 제한)은 그대로, 원본 백업 `C:\shk\ossec.conf.bak` |

## 카테고리별 진행 현황

| 카테고리 | 상태 | ✅ 완료 | 🔄 진행중 | ⬜ 미완료 | 전체 |
| --- | --- | --- | --- | --- | --- |
| 1. 준비 | ✅ | 3 | 0 | 0 | 3 |
| 2. 기획서 확인 | 🔄 | 4 | 2 | 0 | 6 |
| 3. 계약·설계 | 🔄 | 1 | 2 | 2 | 5 |
| 4. Docker Desktop 기반 (관제 PC) | 🔄 | 0 | 4 | 2 | 6 |
| 5. 경보 경로 (agent → manager → Graylog) | 🔄 | 4 | 1 | 0 | 5 |
| 6. S7 탐지·대응 구현 | 🔄 | 0 | 3 | 6 | 9 |
| 7. 사전 시험 (합의본 5.10) | 🔄 | 0 | 1 | 4 | 5 |
| 8. 검증 (9단계·보강 전후) | ⬜ | 0 | 0 | 9 | 9 |
| 9. 시연 준비 | ⬜ | 0 | 0 | 4 | 4 |
| **합계** | | **12** | **13** | **27** | **52** |

> 카테고리 상태: 모두 ⬜이면 ⬜, 하나라도 ✅·🔄가 있으면 🔄, 모두 ✅이면 ✅. 하위 표를 바꾸면 이 표도 같이 고칩니다.

## 1. 준비

| 작업 | 상태 | 비고 |
| --- | --- | --- |
| 저장소 환경 준비(`tools/bootstrap.py`)·pytest | ✅ | 완료 기록 참고 |
| 자리 C·담당 범위 확인 | ✅ | 10/19 확정 |
| S7 작업 방향 문서 | ✅ | [작업방향-S7.md](../작업방향-S7.md) (PR #14) |

## 2. 기획서 확인

| 작업 | 상태 | 비고 |
| --- | --- | --- |
| 합의본 S7 점검(②③④⑤) | ✅ | [합의본-S7-점검](s7-draft/합의본-S7-점검.md) |
| C 수정 필요 1~4 전달·반영 | ✅ | PR #10 코멘트 → `ebae483` |
| 기획서 피드백 문서 | ✅ | [기획서-피드백](s7-draft/기획서-피드백-shk12170-dev.md) |
| 제출본(PR #20) S7 검토 | ✅ | 보완 5건 코멘트(홈페이지 `/`→`index.html` 키, `file-access` 표, 2xx만 집계, 복구 재경보 근거, 해시 목록 전달) |
| PR #20 반영 확인·C "동의" | 🔄 | 보완 반영 여부 확인 뒤 동의 |
| 117 번호 | 🔄 | 제출본은 "수업 가이드 번호(108·111~114)와 구분한 팀 번호"로 정리. 강사님 확정 답은 없음 |

## 3. 계약·설계

| 작업 | 상태 | 비고 |
| --- | --- | --- |
| S7 FIM 이벤트·사건 계약 확장안 | ✅ | [s7-draft](s7-draft/README.md), 40 passed (제안, 미채택) |
| 포털 `web.file_access`·`file_key` 이벤트 | 🔄 | B 작성 backend #2·capstone #19, 미병합. 파일 키 규칙이 S7 스크립트와 같은지 확인 |
| 홈페이지(`/`) 접근의 파일 키 | 🔄 | `/` → `index.html`로 기록할지 B와 합의 |
| 계약 채택(조율 담당과 사건 `username` 없는 경우 포함) | ⬜ | `aleph-contract-change` |
| 해시 목록 전달 경로(A VM → D Graylog) | ⬜ | D와 합의. GELF 12201/udp 재사용 또는 lookup 파일 |

## 4. Docker Desktop 기반 (관제 PC)

| 작업 | 상태 | 완료 기준 |
| --- | --- | --- |
| Graylog 기준 확인(팀 Graylog는 D PC) | 🔄 | C PC는 수업 Graylog로 연습(6.1.16·KST 일치). 팀 Graylog 입력·파이프라인은 D에게 전달(완료 기록 참고) |
| WSL 상한·`vm.max_map_count`·시계 확인 | 🔄 | `wsl -d docker-desktop sysctl vm.max_map_count` ≥ 262144, 컨테이너 시각 = Windows 시각(KST). `.wslconfig` 변경은 D 결정 따름. 10/20 시계 일치 확인(컨테이너 KST), WSL 상한 7.7GiB, `vm.max_map_count` 미확인 |
| Wazuh manager 정리(버전·`mem_limit`·`TZ`·수업 데이터 보존) | 🔄 | 4.9.0 유지(B와 같음, A agent는 4.9.0 이하). 인덱서·대시보드 유지 여부 결정. 10/20 연습 환경: 수업 `wazuh-lab`(4.9.0, 인덱서·대시보드 포함, `mem_limit` 없음)이 Graylog와 같은 네트워크 `9_graylog_default`에 있음 |
| 포트 공개: `1514/tcp`·`1515/tcp`, API `55000` | 🔄 | 10/21 1514·1515 공개 확인, 55000 미공개. 허용 출발지·VPN 경로는 B와 결정 |
| Windows 방화벽 인바운드 1514·1515(A 출발지만) | ⬜ | A VM에서 `nc -zv <C 주소> 1514` 성공 |
| Graylog + Wazuh 동시 구동 30분 메모리(사전 위험 ③) | ⬜ | D와 같이. `docker stats --no-stream`·호스트 RAM 기록 |

## 5. 경보 경로 (agent → manager → Graylog)

| 작업 | 상태 | 완료 기준 |
| --- | --- | --- |
| A Ubuntu VM Wazuh agent 설치·등록 | ✅ | 10/21 009 `haedam-portal-web` Active(WSL2, 4.9.0). 처음 등록은 IP 조건(`10.250.0.0/24`)이 Docker Desktop 출발지 `172.21.0.1`과 달라 거부 → 자동 재등록으로 ID 003~008 생성 → 모두 지우고 manager에서 `manage_agents -a any -n haedam-portal-web` 키 생성·A 수동 가져오기, A 자동 등록 끔 |
| agent FIM(`syscheck`) 설정 | 🔄 | 10/20 manager 자체(agent 000)에 `/tmp/zz_fim_test` realtime 감시로 경로 시험 완료. A VM 설정은 미실행. 초안 `lab/s7/wazuh/` — **10/20 이 PC 저장소에 없음, 파일 위치 확인 필요**. A의 실제 `dist` 호스트 경로(컨테이너면 마운트 대응)를 `realtime`·`check_all`·`report_changes` |
| Graylog 입력 `wazuh-alerts`(UDP, 호스트 미공개) + 스트림 | ✅ | 10/20 Raw/Plaintext UDP 5514, 스트림 `wazuh-alerts`(match input, Default Stream에서 제외). 수업용 입력(5140)·스트림 `Wazuh 경보`는 그대로 둠 |
| manager `syslog_output`(JSON) → Graylog (연습: `gl-graylog:5514`, 팀: D 주소·포트 미정) | ✅ | 10/20 `gl-graylog:5514`, `format json`, `group syscheck`(FIM만). 설정은 볼륨 `wazuh-lab_wazuh_etc` 안 `ossec.conf` → `docker cp`로 수정. 수업용 블록(5140, rule_id 제한)은 유지 |
| 실제 필드 이름 기록·JSON 파싱 파이프라인 | ✅ | 파일 경로·agent·변경 종류·해시 필드 이름을 이 문서 완료 기록에 남김. 10/20 파이프라인 `wazuh-parse`(stage 0 `wazuh: parse alert json`, stage 1 `wazuh: fim path safe`, 수업 규칙 재사용). 필드 이름은 아래 "Wazuh FIM 경보 필드" |

### Wazuh FIM 경보 필드 (2026-10-20 실측, 연습 환경)

시험: manager 컨테이너에서 `/tmp/zz_fim_test/zz_test4.html` 생성 → Graylog `wazuh-alerts` 스트림. 파이프라인이 `message`는 `[Wazuh <rule_id>] <설명>`으로, `source`는 agent 이름으로 바꿉니다(원래 JSON 문장은 남지 않음).

| 필드 | 값 예시 | S7 용도 |
| --- | --- | --- |
| `wazuh_rule_id` | `554` (추가) · `550` (변경) · `553` (삭제) | 변경 종류 |
| `wazuh_rule_level` | `5` (숫자) | |
| `wazuh_rule_groups` | `["ossec","syscheck","syscheck_entry_added","syscheck_file"]` | |
| `wazuh_agent_id` · `wazuh_agent_name` | `000` · `wazuh-manager` | 어느 서버인지 |
| `wazuh_syscheck_path` | `/tmp/zz_fim_test/zz_test4.html` | 원래 경로 |
| `wazuh_file` | 위와 같음(`\` → `/`) | **묶기 키 원천** (웹 루트 상대 경로로 바꾸는 규칙은 미작성) |
| `wazuh_syscheck_mode` | `realtime` | |
| `wazuh_syscheck_sha256_after` · `md5_after` · `sha1_after` | 해시 | P5 해시 목록 대조 |
| `wazuh_syscheck_size_after` · `perm_after` · `uid_after` · `uname_after` · `inode_after` · `mtime_after` | `6` · `rw-r--r--` · `0` · `root` · … | 증적 |
| `wazuh_full_log` · `wazuh_decoder_name` · `wazuh_location` | `File '...' added` · `syscheck_new_entry` · `syscheck` | |
| `wazuh_timestamp` | `2026-10-20 15:46:29.311` | 경보 시각 |

- `wazuh_syscheck_event` = `added` 확인(10/20). `modified` 확인(rule 550, level 7, `*_before` 해시·크기·mtime 생김, `changed_attributes`). `deleted` 확인(rule 553, 사용자 확인). `gid_after`·`gname_after`도 있음
- `wazuh_syscheck_diff`(바뀐 내용) 없음: manager 컨테이너(Amazon Linux 2023)에 `diff` 명령이 없어 `ossec.log`에 `(6714) Command diff output an error`. 연습 환경 한정 문제이며, A Ubuntu agent에서 다시 확인. 해시 비교로 판정하므로 S7 탐지에는 영향 없음
- 시각(1회): 파일 mtime 15:46:29.000 → Wazuh 경보 29.311 → Graylog 수신 30.487 (약 1.5초). P1 정식 측정(10회)은 미실행

## 6. S7 탐지·대응 구현

| 작업 | 상태 | 비고 |
| --- | --- | --- |
| Graylog 파이프라인·lookup·이벤트 정의 | 🔄 | 초안(`lab/s7/graylog/`, 위치 확인 필요), 미시험. 5번에서 기록한 실제 필드 이름으로 고침. 웹 접근은 2xx만 |
| 117 복구·격리 스크립트(`s7_restore.py`) | 🔄 | 로컬 구현·시험 22 passed. 미커밋(`feature/s7-restore-deploy`, 이 PC에 브랜치 없음). 10/21 연습 환경 **수동** 복구·격리 시험 통과(아래 "수동 복구·격리 시험") |
| 정상 배포 스크립트(`s7_deploy.py`, 기준본·해시 목록) | 🔄 | 위와 같음 |
| Wazuh API 계정(n8n용, 최소 권한) | ⬜ | active response 실행 권한만. 토큰은 n8n 자격 증명에만 |
| n8n 117 워크플로(Wazuh API → 효과 확인 → 114 티켓) | ⬜ | n8n은 D PC. 호출 주소 `https://<C 주소>:55000`(포트 공개·방화벽·자체 서명 인증서 처리 확인). 자동화 전 C·A 수동 복구·격리 먼저 |
| 보안 대시보드 컨테이너(티켓 목록·상태) | ⬜ | 합의본 ④ 인시던트 관리 |
| 포털 관리자 메뉴 링크(`DASHBOARD_URL`) 연결 | ⬜ | B와 연결 확인 |
| Kali 재현 스크립트(무해한 `zz_` 시험 파일) | ⬜ | 출발지 203.0.113.31~39 |
| 결과표·증적 폴더(`docs/capstone/evidence/S07/`) | ⬜ | |

### 수동 복구·격리 시험 (2026-10-21, 연습 환경)

manager 컨테이너의 감시 폴더 `/tmp/zz_fim_test`에서 진행. 기준본·격리 폴더는 감시 밖 `/opt/zz_s7/baseline`(읽기 전용 444), `/opt/zz_s7/quarantine`.

| 단계 | 동작 | 결과 | Wazuh 경보 |
| --- | --- | --- | --- |
| 1 원본 배포 | 기준본 → `zz_index.html` | sha256 `f92a731c…` | 554 added |
| 2 공격 | `zz_index.html` 변조 + `zz_shell.php`(무해) 생성 | 변조본 `c7c4652f…` | 550 modified(before 원본 → after 변조), 554 added |
| 3 복구 | 기준본 복사 + 웹셸을 격리 폴더로 이동(`.타임스탬프` 접미사) | 해시가 기준본과 같음, 웹 폴더에 웹셸 없음 | 550 modified(**after = 기준본 해시**), 553 deleted |

- 5건 모두 Graylog 수신.
- **복구 재경보 확인**: 복구 자체가 550·553 경보를 만듭니다. 상관 규칙은 ① 550이고 `sha256_after`가 기준본 해시 목록에 있으면 "복구·정상 배포"로 보고 발동하지 않으며(P5와 같은 판정), ② 553(삭제)은 S7 발동 조건에서 뺍니다.
- 원복(격리 파일을 되돌리기·삭제)은 미시험.
- 연습 컨테이너에 `cmp`·`diff` 명령이 없음 → 복구 스크립트는 해시(`sha256sum`)로 비교.

## 7. 사전 시험 (합의본 5.10)

| 작업 | 상태 | 할 수 있는 시점 | 통과 기준 |
| --- | --- | --- | --- |
| P1 realtime 경보 지연 | 🔄 | 5번 끝 | 파일 변경 → Graylog 수신까지 실측값이 10분 창보다 충분히 짧음. UDP 유실 건수도 기록. 10/21 연습 환경 20회: 20/20 수신, 대부분 0.35~1.25초, 1회 11.0초(시계 보정 영향 추정). A agent·VPN 경유 재측정 필요 |
| P2 FIM·접근 파일 키 일치 | ⬜ | 5번 끝 + 포털 `file_key` | 같은 파일에서 같은 키 |
| P3 bind mount 호스트 경로 감시 | ⬜ | 5번 끝 | 포털 컨테이너 안 변경이 호스트 경로로 잡힘 |
| P4 Wazuh API → active response 실행 | ⬜ | API 계정 뒤 | 안 되면 2안 포털 API |
| P5 정상 배포 미발동 | ⬜ | 6번 이벤트 정의 뒤 | 해시 목록 일치 → 허용 표시 |

## 8. 검증 (9단계·보강 전후)

| 작업 | 상태 | 비고 |
| --- | --- | --- |
| 보강 전 1회(규칙·117 넣기 전, 스냅샷 고정) | ⬜ | 나중에 다시 할 수 없음. 5번 끝·6번 시작 전에 실행 |
| 전체 조건 충족 5회(변경·신규 파일 각각 포함) | ⬜ | 실행마다 다른 파일 경로 |
| 경계: 변경만(접근 없음) | ⬜ | 미발동 |
| 조건 일부: 접근만 | ⬜ | 미발동 |
| 시간 창 밖(10분 초과) | ⬜ | 미발동 |
| 혼합(다른 파일 변경·접근) | ⬜ | 파일별 따로 |
| 정상 업무 30분(정상 배포 포함) | ⬜ | 이벤트 0건 |
| 중복 확인(복구 경보·404 확인으로 재발동 없음) | ⬜ | 6단계 |
| 정량평가 표 기록 | ⬜ | [S7 정량평가](../team_docs/정량평가-S7-shk12170-dev.md) |

## 9. 시연 준비

| 작업 | 상태 | 비고 |
| --- | --- | --- |
| 공격 → Wazuh 경보 → Graylog → n8n → 복구 → 원본 응답 캡처 | ⬜ | 합의본 5.7 |
| 원복(격리 파일 삭제, 원본 해시) 캡처 | ⬜ | |
| 다른 자리 케이스 교차 재현 1회 | ⬜ | 합의본 ⑥ |
| PPT용 결과 한 줄 요약 | ⬜ | |

## 완료 기록 표

결과 분류는 합의본 5.2(통과 / 미입력 / 미관측 / 미탐 / 오탐 / 조치 실패 / 효과 검증 실패 / 효과 미확인 / 정상 업무 영향 / 원복 실패), 문서·설정은 `통과` 또는 `보류`.

| 작업 | 날짜·시각 (KST) | 한 일 | 결과 | 증적 | 막힌 점·다음 할 일 |
| --- | --- | --- | --- | --- | --- |
| 1. 환경 준비 | 2026-10-19 | bootstrap, pytest 29 passed | 통과 | 터미널 출력 | 없음 |
| 1. S7 작업 방향 | 2026-10-19 | 작업방향-S7.md, PR #14 병합 | 통과 | `작업방향-S7.md` | team_docs 이동은 PR #16 |
| 2. 합의본 S7 점검·피드백 | 2026-10-19 | 점검 9건·피드백·C 확인 문서 | 통과 | `docs/s7-draft/` | 없음 |
| 2. C 수정 필요 전달 | 2026-10-19 | PR #10 코멘트 → `ebae483` 반영 | 통과 | PR #10 코멘트 | 없음 |
| 3. 계약 확장안 | 2026-10-19 | FIM 스키마·예시·테스트 | 통과 | `docs/s7-draft/`, 40 passed | 채택은 조율 후 |
| 6. 117·배포 스크립트 | 2026-10-19 | 로컬 구현, 22 passed | 보류 | 로컬 `lab/s7/`(미커밋) | 10/20 이 PC 저장소에 없음 → 위치 확인 |
| 2. 제출본 S7 검토 | 2026-10-20 | PR #20 보완 5건 코멘트 | 통과 | PR #20 코멘트 | 반영 확인 |
| 작업순서 재구성 | 2026-10-20 | Docker Desktop(Graylog) 환경 기준으로 4~6번 재구성 | 통과 | 이 문서 | Wazuh syslog UDP·포트 배치는 시험으로 확인 |
| 5. 경보 경로(연습 환경) | 2026-10-20 15:46 | manager 자체 FIM → `syslog_output` → Graylog 5514 → 파이프라인 필드 분리 | 통과 | Graylog 캡처(zz_test2~4) | 포털 VM agent·웹 경로 감시, 팀 compose 전환 |
| 4. C 환경 점검(인수인계 7절) | 2026-10-21 | Docker 29.7.2, Wazuh 4.9.0, agent 000·001 Active, 1514·1515 공개·55000 미공개, 사용자 규칙 15개(100220~100222 포함), 메모리 약 5.2GiB | 통과 | `work-log/members/shk12170-dev/2026-10-21.md` | B·A·D 입력 대기 |
| 작업순서 팀 구성 반영 | 2026-10-21 | 인수인계 기준(C·D 분리, A agent, VPN)으로 구성·순서 수정 | 통과 | 이 문서 | 인수인계 원문 main 미반영 |
| 7. P1 연습 측정 | 2026-10-21 11:13 | 연습 환경 FIM 생성 → Graylog 20회 | 통과(연습) | `work-log/members/shk12170-dev/2026-10-21.md` | A agent·VPN 경유 재측정, 시계 동기화 |
| 6. 수동 복구·격리 | 2026-10-21 11:15 | 변조 복구·웹셸 격리, 복구 재경보 확인 | 통과(연습) | 위 "수동 복구·격리 시험" | 원복 미시험, A VM에서 재시험 |
| 5. A agent 첫 FIM (첫 공동 목표) | 2026-10-21 14:44 | A `dist/zz_fimtest.txt` 추가(554)·변경(550), realtime | 통과 | manager `alerts.json`, C Graylog(OpenSearch) 수신 2건 | 복원·삭제 경보, D Graylog 전달, 웹 접근 상관 |
| 5. 포털 VM 이관·agent 010 | 2026-10-21 16:24 | VM agent 010 등록, VPN 경로(10.250.0.2→10.250.0.3) Active, 009 증적 저장 후 삭제 | 통과 | `docs/capstone/evidence/S07/2026-10-21-agent009-wsl-alerts.jsonl`, 작업일지 | VM FIM 4단계, D 연동은 010 기준 |
| 5. VM FIM 추가·변경·삭제 | 2026-10-21 16:31 | `dist/zz_fimtest.txt` 554→550→553, realtime, diff 있음, C Graylog 3/3 수신(0.5~1.0초) | 통과(복원 단계 제외) | `docs/capstone/evidence/S07/2026-10-21-agent010-vm-fim-alerts.jsonl` | 복원 단계 재시험, D Graylog 수신 |
| 5. VM FIM 복원 재시험 | 2026-10-21 16:47 | `dist/zz_restoretest.txt` 554→550(H0→H1)→550(H1→H0)→553, C Graylog 4/4 | 통과 | `docs/capstone/evidence/S07/2026-10-21-agent010-vm-restore-test-alerts.jsonl` | D Graylog 수신, A VM 시계 확인 |
