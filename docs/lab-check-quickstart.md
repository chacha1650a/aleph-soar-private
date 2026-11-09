# 집 구현 확인과 학원 사전 준비

**집에서도 코드 구현·합성 데이터·파일 입출력 테스트가 가능하다.** 학원 PC가 없어 못 하는 것은 실제 연결·수집·공격/대응·효과/원복 시험이다. 현재 구현은 `prepare → collect/compare`와 `gather → share → status --seat`의 **읽기 전용 파일 대조**다. 필요한 자리의 파일을 병렬 수집하고 공통 보고서를 발행한다. 원격 명령/API 수집기는 아직 없다.

설계와 범위는 [설계 문서](lab-check-design.md), 현재 시험 상태는 [PROGRESS](PROGRESS.md)를 따른다. fixture 통과는 학원 실측 통과가 아니다. **한 번에 병렬 실행하고 각 팀원/LLM이 같은 결과를 읽는 예제**는 [팀 실행 안내](lab-check-team-run.md)를 본다.

## 1. 집에서 지금 실행할 수 있는 예제

capstone 저장소 루트에서 프로젝트 .venv를 사용한다. 없을 때만 `python tools/bootstrap.py`로 준비한다. 아래 예제에는 네트워크·로그인·공격·차단·해제·티켓 생성이 없다.

학원에서도 CLI 환경은 각 Windows 호스트의 capstone 체크아웃에 준비한다. 포털 서비스/VM의 기존 환경과 구분하며, capstone bootstrap은 포털·관제 서비스 배포가 아니다.

```powershell
$labPython = '.\.venv\Scripts\python.exe'
& $labPython -m pytest tests/test_lab_check.py -q

# 1) 합성 S10 카드 고정: 기본 출력 루트는 저장소의 .local/lab-check
& $labPython tools/lab_check.py prepare --card tests/lab_check_fixtures/s10/card.json --out demo-s10

# 2) B와 D의 합성 내보내기 파일을 각각 검증해 불변 영수증으로 저장
& $labPython tools/lab_check.py collect --card .local/lab-check/demo-s10/card.json --seat B --phase final --input tests/lab_check_fixtures/s10/input.json --profile tests/lab_check_fixtures/s10/B.profile.json --out demo-s10/inbox/B
& $labPython tools/lab_check.py collect --card .local/lab-check/demo-s10/card.json --seat D --phase final --input tests/lab_check_fixtures/s10/input.json --profile tests/lab_check_fixtures/s10/D.profile.json --out demo-s10/inbox/D

# 3) 파일만 대조하고 comparison.json + report.md 생성
& $labPython tools/lab_check.py compare --card .local/lab-check/demo-s10/card.json --phase final --input tests/lab_check_fixtures/s10/input.json --receipts .local/lab-check/demo-s10/inbox --out demo-s10/final
Get-Content -Encoding UTF8 .local/lab-check/demo-s10/final/report.md
```

예상은 `matched`, 종료0이다. 동시에 `environment=fixture`, `ready_candidate=false`, `final_complete=false`여야 한다. 이 예제는 학원의 ICMP ID25265/seq164 원문을 재구성하지 않은 합성 데이터다. 재실행은 새 `--out` 이름을 쓴다. 기존 산출물은 덮어쓰지 않는다. 다른 작업 디렉터리에서는 입력 경로를 절대경로로 지정한다.

`--run-root`는 하위 명령 **앞**에 지정하고 `--out`은 그 루트 안의 상대경로를 쓴다. 프로파일의 `source_root`가 상대경로이면 프로파일 파일이 있는 디렉터리를 기준으로 한다. live endpoint·SSH·명령·자격 증명을 넣는 프로파일은 현재 버전에서 허용하지 않는다.

## 2. 학원에서 PC 전원 외에 공통으로 필요한 것

1. **필요한 자리만 가동한다.** S10 준비 표본의 B 원문↔D 정규화 대조는 B/D 자료가 필요하다. 전체 공격→탐지→대응→티켓→원복 검증에는 관련 A~D 서비스와 독립 검토자가 필요하다. 기존 내보내기 파일만 비교할 때는 원래 PC가 꺼져 있어도 되지만 현재 가동을 확인한 근거는 아니다.
2. **호스트 다음 VM/컨테이너·앱을 확인한다.** Windows가 켜져 있다는 사실과 pfSense/포털/DB/Wazuh/Graylog/n8n/티켓이 정상 가동 중인 것은 다르다. 어떤 것이 자동 시작하는지 담당별로 확인하고 미등록 상태를 자동 복구됐다고 가정하지 않는다.
3. **현재 VPN·서비스별 경로를 확인한다.** A .2·C .3·D .100은 기존 기록의 주소다. 실제 접속·반환 경로·필요 포트·리스너를 확인하며 ping만으로 서비스 경로를 통과 처리하지 않는다. 새 NAT/방화벽 규칙을 도구가 추가하지 않는다.
4. **같은 카드·코드/설정 버전을 맞춘다.** 현재 브랜치를 받을 때 각자의 작업트리 변경부터 보존한다. 입력 출발지·대상·횟수·시험/관측 구간·현재 동결을 카드에 고정하고 다른 시험이나 배포와 겹치지 않게 한다.
5. **읽을 원본과 권한을 확인한다.** 실제 파일 위치·검색/조회 조건·보존 범위·페이지네이션·제품 버전을 받는다. 키/비밀번호는 담당 PC의 로컬 설정에만 둔다. 지금 버전은 표준 JSON export와 제한된 B filterlog·D/일반 JSONL 매핑을 지원한다. 제품별 API/DB를 직접 조회하지 않으며 실제 필드·조회 완전성·메타데이터는 담당 확인이 필요하다.
6. **시각과 조회 범위를 확인한다.** 시계 오차를 모르면 unknown으로 남긴다. 관측 종료·조회 완전성이 확인되지 않으면 최종0건이나 MTTD를 산출하지 않는다. 준비 health 요청·기존 수동 시험은 본 입력과 분리한다.

## 3. 자리별 첫 준비

| 자리 | 켜고 확인할 서비스 | 먼저 준비할 읽기 자료·담당 확인 |
| --- | --- | --- |
| A | 포털 VM·backend·VPN·B DB 연결 | 실제 배포 버전·health/DB 상태, 원본 JSONL 위치·event_id/출발지, 반환 경로·현재 차단 상태 |
| B | pfSense·DB·필요 시 Kali·전송기 | 기존 입력 증적, filterlog/EVE 원본/커서·tracker·인터페이스/방향, 전송기 가동·대기. CLI는 B Windows의 프로젝트 .venv에서 실행하고 pfSense에 Python 패키지를 설치하지 않음 |
| C | Wazuh·중계, 전체 대응 시험이면 티켓 저장소·DB/볼륨 | 010 Active·Wazuh/티켓 버전, 가동/미가동, 전체 시험 조건으로 조회할 방법·읽기 권한. 열린 티켓 목록 일부0을 전체0으로 쓰지 않음 |
| D | Graylog 입력/파서, n8n·관련 저장소 | B 표본의 고유 수신/정규화 필드·파서 버전, 정의 활성 상태, 실행 ID/dry_run/실제 HTTP 노드 상세를 읽을 방법 |

기존 기록의 서비스 포트는 [문서 기반 포트 검토](../team_docs/2026-10-23-팀-AI-통합개선-집작업-인수인계.md#8-추가-검토--필요한-포트-3개-포워딩-제안)를 참고한다. 학원에서 지금 가동/허용된 값이라고 가정하지 않는다. 필요한 위치의 실제 경로를 검사해야 하며 B PC의 접속 성공으로 A→D 경로를 대신하지 않는다.

## 4. 학원 첫 연결 작업과 현재 한계

먼저 B/D의 **기존 S10 준비 표본 원문과 D 검색 결과**를 파일 어댑터에 연결한다. [팀 실행 안내의 설정표](lab-check-team-run.md#3-학원에서-채울-설정)에 실제 경로·연도/시간대·정규화 필드·메타데이터를 맞춘다. D가 확인되지 않았다고 패킷을 재전송하거나 .22 본 시험을 자동 시작하지 않는다. 그다음 A 포털·C 티켓/Wazuh·D n8n의 실제 내보내기 형식을 연결한다.

현재 지원하는 고정 프로파일은 `s10-normalization-v1`, `s8-baseline-v1`, `s8-postchange-v1`이다. S1/S4/S7/S12 및 지원 범위 밖의 제품별 원문 파서는 별도 구현/검증이 필요하다. export/메타데이터에는 실제 run_id·카드 해시·자리·관찰 위치·버전·조회 시각·범위·근거 종류가 있어야 한다. 예제의 environment만 lab으로 바꿔 실제 증적으로 사용하지 않는다.

프로파일은 최소 검사와 예상 환경도 고정한다. 예를 들어 현재 s8-baseline-v1은 티켓 저장소 미가동 기준선 사례다. 저장소가 가동된 새로운 시험 계획은 해당 환경의 정책 버전·새 카드로 정하며 기존 증적의 기대 조건을 사후 변경하지 않는다.

`collect`는 파일에서 읽기 결과를 추출·검증·포장하며 현재 장비의 가동 상태를 조회하지 않는다. 따라서 lab export가 일치해도 **OFFLINE_EXPORT_UNVERIFIED**, 준비 후보/최종 완료는 false다. `gather`는 필요한 자리의 로컬 수집기만 최대4개 병렬 실행하고 수집기별 시간 제한을 적용한다. 실제 입력 시작·효과·원복 판정과 PROGRESS 반영은 담당/독립 검토자의 근거 확인 뒤에 한다. 버전별 API/DB·원격 어댑터와 학원 경로 검증은 후속이다.

종료 코드는0=해당 범위 성공,2=형식/해시/경로/충돌 오류,3=자료 부족·부분 수집,4=충분한 자료에서 불일치다. 일부 수집이 실패해도 다른 자리의 결과는 보존한다. 원본·설정·일지·서비스를 변경하는 기능은 없다.
