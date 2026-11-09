# B S8/S10 다음 학원 첫 완주

범위: 공격 입력 → 실제 로그 수집·Graylog 조건 → n8n → 앱/PF 조치·C 티켓 → 정상 사용자 대조 → 승인 수동 원복. 집에서는 코드와 전달물까지 준비했다. 실제 학원 설치·게시·효과는 아래 순서로 확인한다.

## 1. 공통 준비와 PF 단독 인수

A는 포털·DB·VPN·실제 source .21/.22/.100과 앱 잔여 차단을, C는 컨테이너/일관 백업·활성 조치·D 실제 조회를, D는 인증·하위 호출·모드·수동 해제를 한 번에 확인한다. B는 시계·망·실제 설치본/도구 해시를 확인한다. 기존의 진행 중 시험과 충돌하지 않는 구간에서만 설치한다.

`pf-bundle/install_bundle.py --verify`는 파일 검증이다. 실제 설치·D 공개키·forced command·D→PF22·호스트 키 확인은 [PF 설치 안내](../lab/pfsense/INSTALL.md)를 따른다. 도구는 `/usr/local/sbin/haedam-pf-response` 한 파일만 게시하며 키/규칙을 자동 설정하지 않는다. 기존 다른 버전은 덮어쓰지 않는다.

PF 단독 인수는 .22로 `status → block → 대상 새 HTTP 실패/정상 .100 성공 → 동일 요청 재생 → 같은 owner의 새 unblock → .22 HTTP200` 순서다. 앱 차단이 없는 상태에서 PF 효과를 따로 확인한다. B/D가 승인한 전용 경로에서 아래 형식으로 실행한다.

```text
haedam-pf-response status 203.0.113.22 s10-pf-status-01 status
haedam-pf-response block 203.0.113.22 s10-pf-block-01 B-S10-PREFLIGHT-01
haedam-pf-response unblock 203.0.113.22 s10-pf-release-01 B-S10-PREFLIGHT-01
```

명령 성공·실제 HTTP 효과·C 기록은 별개다. exit가 없거나 JSON/대상/owner가 다르면 중단하고 현재 state·journal부터 대조한다. partial/pending은 같은 owner의 **새 unblock ID**로 검토 보상하며 journal을 지우지 않는다.

이 단계에서는 .22 ICMP를 보내지 않는다. 효과는 HTTP로만 대조해 다음 S10의 입력 ICMP와 구분한다. PF claim/pending·앱 차단을 원복한 다음 탐지 정의를 활성화한다.

## 2. D 반입 준비 — 출발지별 분리

기본 정의는 S10 입력에서 S8도 발동한다. 첫 완주는 S8 `.21`, S10 `.22`로 분리하고 프로파일이 두 정의에 각각 source 필터를 붙인다. 기존 범용 S8/S10 정의가 동시에 알림을 보내지 않도록 D가 대상 정의만 대조한다. 다른 케이스 규칙을 일괄 끄지 않는다.

S10 입력은 **default deny의 ICMP1건**이고 n8n 자동 대응은 EasyRule 차단이다. PF 출력의 `pf_tracker`, `pf_proto=icmp`, `pf_dst_ip=203.0.113.1`이 D에서 실제 정규화됐는지 확인한다. 10/26 tracker `1000000103`은 과거값이므로 오늘 읽은 값을 쓴다. 프로파일은 그 tracker만 포함해 사전 시험/자체 대응의 PF 로그가 입력 신호를 대신하지 못하게 한다.

```powershell
# 기본은 계획 파일 생성. 미확정 스트림/tracker는 missing_bindings로 남는다.
python tools/prepare_s8s10_trial.py --out trial-B-observe --mode observe

# D가 실제 ID·입력 tracker를 확보한 뒤 실행할 후보 형식.
python tools/prepare_s8s10_trial.py --out trial-B-live --mode live --allow-live --portal-stream <포털스트림ID> --pfsense-stream <PF스트림ID> --pf-tracker <입력트래커>
```

생성기는 운영을 호출하지 않는다. JSON은 `active:false`이고 정의도 D가 DISABLED 상태로 반입한다. 실제 모드는 haedam-32의 CFG(dry_run/store_real)이며 body로 바뀌지 않는다. D는 인증·C/포털/SSH 자격 증명·하위 workflow ID·게시 버전/해시를 대조한다. 미확정 `REPLACE_`가 있으면 게시하지 않는다.

## 3. 최소 실제 입력과 판정

각 케이스는 새 run_id/출력 경로를 사용하고 재시도하지 않는다. 기본 명령은 HTTP/ICMP를 보내지 않는다.

```bash
# Kali, 계획만 생성
python3 tools/s8s10_input.py --case S8 --run-id B-S8-NEXT-01 --out S8-plan.json
python3 tools/s8s10_input.py --case S10 --run-id B-S10-NEXT-01 --out S10-plan.json

# 준비 인수·D 시작 신호 후, 케이스별 새 결과 파일로 실행
python3 tools/s8s10_input.py --case S8 --run-id B-S8-NEXT-01 --out S8-input.json --execute
python3 tools/s8s10_input.py --case S10 --run-id B-S10-NEXT-01 --out S10-input.json --execute
```

기본 대상은 보강 전 사용했던 `http://203.0.113.1`(80 포트 전달)이다. 오늘도 같은 경로인지 먼저 확인한다. D/B가 `http://10.250.0.2:5000` 직접 경로를 선택하면 `--target`으로 명시하고 PF WAN/센서 통과·A src_ip를 새로 확인한다. 전달 헤더로 출발지를 위조하지 않는다.

- **S8 입력:** 없는 경로 GET404 1회 → CSRF 준비 GET200 1회 → 존재하지 않는 합성 zz_ 계정 로그인401 1회. S1의 9실패/S4의 성공 결합 조건과 섞이지 않는다.429·403·timeout 등 예상 밖 응답은 추가 입력을 중단한다.
- **S10 입력:** 위 HTTP3회 뒤 `.22 → 203.0.113.1` echo request1회. ping 실패만으로 PF 차단 로그 도착을 성공 처리하지 않는다. B 원문 tracker/ICMP ID·seq·시각과 D 수신을 대조한다.
- **수집 대조:** A 원본 event_id, B 입력/원문, D 고유·중복·정규화 → Graylog event_id → n8n 부모/하위 실행 → C ticket/action을 연결한다. JSONL에 없는 rule을 원본에 덧쓰기하지 않는다.
- **S8 통과:** 앱 차단 목록·새 요청403, 정상 `.100 /login`·업무 정상, C 실제 applied/효과, PF 호출0.
- **S10 통과:** 앱 차단과 PF 별도 조치/현재 state·대상 state 제거, PF 차단 동안 새 연결 실패·정상 .100 유지, 두 via의 C 기록. 앱403만으로 PF 효과를 증명하지 않는다.

양성 시험은 실제 발동·효과가 확인되면 다음 단계로 간다. 15분 창 전체를 무조건 기다릴 필요는 없다. 미발동이면 **다음60초 실행 + 실제 수집/색인 지연**을 보존하고 원인을 확인하며 입력부터 반복하지 않는다. 같은 source의 음성·경계·재발동 시험에는 기존15분/grace가 적용된다.

## 4. 원복과 완료

1. 승인 수동 해제 경로를 사용한다. haedam-50 live_release_enabled는 이번에 켜지 않는다.
2. S10은 실제 ticket_id를 PF owner로 확인하고 **PF부터 unblock**한다. 설정/table·pending/claim과 같은 자원 다른 티켓을 대조하고 C released를 기록한다. 이 시점 앱 차단이 남아 403이면 두 집행 위치를 분리해 설명할 수 있다.
3. 다음 포털 unblock, S8은 포털만 unblock. .21/.22 재접근200·정상 .100 유지·해당 자원의 활성 조치0을 확인하고 C 티켓을 닫는다.
4. 실패한 조치는 실패로 남긴다. 대상 조치 성공 뒤 기록 실패이면 원래 키로 기록만 복구한다. PF 부분 적용은 실제 보상·state 확인과 C 실패 이력을 함께 보존한다.
5. 회신은 `run_id / 실제 버전·해시 / event·실행·ticket ID / 실제 두 via 적용·정상 영향 / 해제·재접근·활성0 / 증적 / 남은 문제` 한 번으로 묶는다.

## NIDS 확인 범위

현재 S8/S10 상관 조건은 포털 로그·PF 로그이고 Suricata 경보가 필수 입력은 아니다. 별도로 기존 SID9901022의 `.10 → .1` ICMP 센서 표식1회로 EVE→D `suricata-alerts` 수신을 공통 준비 때 대조할 수 있다. 기존 SID 로드/주소가 오늘도 맞는지 읽고 진행한다. 이 표식 경보는 센서 경로 확인이며 실제 S8/S10 공격 탐지율이 아니다. 실제 케이스의 IDS 탐지를 발표하려면 그 입력에 대응하는 signature/flow_id·시각을 별도로 확보한다.
