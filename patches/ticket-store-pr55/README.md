# C 티켓 저장소 수정 패치 · 집 검증 (2026-10-24)

사용자 요청으로 집에서 가능한 코드 수정과 회귀 검증을 진행했다. **C PR #55의 고정 커밋에 적용해 시험한 패치**이며 C/D 원본 브랜치·PR·실행 서비스에는 적용하지 않았다. 이 인수인계 브랜치 자체에 티켓 서비스를 병합한 것도 아니다.

- 대상: [PR #55](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/55), `feat/ticket-store` → `docs/ticket-store-api`.
- 기준 head: `e8db8ecd6aa497ad75df1d89cf01653b6cb5988a` (10/24 읽기 조회 시 OPEN·동일 head).
- 패치: [0001-resource-via-cycle.patch](0001-resource-via-cycle.patch), 45,186 bytes.
- SHA-256: `85b2dcd356c114933c71e03acd07a631abd854543e973a0943cd84ff946caf9b`.
- `.gitattributes`는 이 패치 폴더에만 unified diff 문맥 줄의 공백/마지막 빈 줄 검사를 제외한다. 패치 바이트를 지우지 않기 위한 것이며 적용된 소스의 `git diff --check`는 별도 통과했다.
- 근거: [10/23 B 검토·결함 재현](../../team_docs/2026-10-23-C-티켓검토-B.md). 당시의 ‘C 구현 파일 수정 안 함’은 당시 검토 범위다. 이번에는 사용자 구현 지시로 **별도 체크아웃**에서 수정했다.

## 코드에서 바꾼 것

| 문제 | 패치 동작 | 확인한 회귀 |
| --- | --- | --- |
| A는 username, D는 IP로 묶어 같은 IP 차단을 놓침 | 기존 `/open`을 유지하고 인증된 `GET /api/v1/tickets/active?asset_id=&via=&action=&target=` 추가. 자리·묶음·봇을 넘어서 같은 자원의 활성 조치를 반환 | A/D가 서로 다른 묶음·봇이어도 함께 반환, 다른 경로/자산 제외, 닫힌 티켓의 미해제 조치도 보류 근거로 반환 |
| 과거 적용 이력이 새 적용을 중복 처리 | 중복·효과 판정을 현재 활성 조치로 제한. 상태 전진 정책을 보존하기 위해 `restored`에 새 이벤트/적용은 409로 명시 | 탐지 단계부터 새 이벤트 유입 거부, 본문·조치·키 롤백, 기존 티켓 닫기 후 동일 기록 요청 재시도로 새 티켓 생성·활성 표시, 이전 해제 이력 보존 |
| portal/pfsense 차단이 같은 조치로 처리 | `bot + via + action + target`을 일관되게 사용하고 자리 지정 check에도 via 필수 반환 | 다른 경로의 중복 오인 방지, 효과 갱신 경로 구분, 포털 해제 후 pfSense 유지, 다른 동작 유지, 남은 조치가 있으면 restored로 바꾸지 않음 |
| 날짜에 따라 기존 검사 실패 | 대시보드 테스트 시각을 고정하고 샘플 당일/다음 날을 각각 검사 | ‘오늘 종료’ 1건/0건 모두 확인; 제품 날짜 계산은 변경 안 함 |

자원 조회는 `asset_id, via, action, target` **4개를 모두** 요구한다. `bot`은 조치 식별에는 들어가지만 원복 전 조회를 특정 봇으로 좁히지 않는다. 누락·추가·중복 인자/잘못된 값은 400, 인증 실패는 401, 저장소 오류는 500이다. 정상 200·`ok:true`·요청과 일치하는 resource의 빈 tickets만 '기록상 활성 조치 없음'이다. 저장소 미가동은 티켓 0건이 아니다. 샘플은 조회 대상에서 제외한다.

해제는 동일 bot·via·target에서 짝 동작 하나만 대상으로 한다. 제안 목록은 `unblock→block`, `unlock→lock`, `restore→quarantine`, 나머지는 동일 동작명이다. 일치하는 활성 조치가 없으면 400이다. **이 동작 목록과 자산 식별표는 C/D 채택 확인 필요**다. effect도 이미 해제된 과거 줄을 갱신하지 않는다.

패치 안의 변경 파일은 11개다.

- 구현 3개: `services/ticket-store/ticket_store/core.py`, `api_n8n.py`, `validate.py`.
- 계약/예시 3개: `contracts/ticket-response.schema.json`, `ticket-record.schema.json`, `ticket-examples/responses.json`.
- 연결 문서 3개: `docs/API-CONTRACT.md`, `docs/C-티켓저장소-설계.md`, `services/ticket-store/README.md`.
- 회귀 2개: `tests/test_ticket_store_core.py`, `test_ticket_store_dashboard.py`.

## 검증 결과

실제 C/D 키·서비스·학원 DB는 사용하지 않았다. 기존 프로젝트 `.venv`의 Python 3.12, Flask test client와 pytest 임시 SQLite만 사용했다. 아래 두 테스트 묶음은 서로 다른 코드 기준이므로 건수를 합산하지 않는다.

| 대상·검사 | 실제 결과 | 의미 |
| --- | --- | --- |
| 수정 전 PR55 전체 | 106 passed, 1 failed | 기존 종료 건수 검사가 오늘 날짜에 의존해 실패 |
| 수정 전 새 회귀 5개 | 5 failed, 27 deselected | 자원 조회·via·원복 후 새 주기·동작별 해제·자산 범위 결함/부족 재현 |
| 수정 체크아웃 전체 | 121 passed | 기존 107개에 회귀 14개 추가(날짜 매개변수 포함) |
| 최종 패치 → 새 기준 체크아웃 | `git apply --check` 성공, 전체 **121 passed in 7.83s** | 작업 폴더의 우연한 파일이 아니라 배포할 패치로 재현 |
| 최종 패치 계약 검사 | `tests/test_contracts.py` **38 passed** | 합성 JSON 예시·스키마 검사; 실제 n8n 소비자 시험 아님 |
| 인수인계 브랜치 전체 | **121 passed, 1 skipped in 24.81s** | 기존 병렬 점검 CLI 포함. skip은 Windows symlink 권한 사례이며 권한 변경 없음 |
| 인수인계 AI 자산·작업 그래프 | 19 assets 일치 / DAG 19 tasks 정상 | 원본/생성물·team.py 변경 없음 |

동시 요청 회귀는 같은 티켓에 portal/pfsense 요청을 4개 스레드로 반복해 한 경로당 한 활성 줄·같은 키의 최초 응답 보존을 확인했다. **티켓 저장소 내부의 동시 기록 검사**이며 실제 대상 API의 중복 실행 방지 검증은 아니다.

로컬 확인 위치는 저장소 하위 `.local/ticket-pr55-fix-20261024/`(수정)와 `.local/ticket-pr55-final-20261024/`(최종 패치 재검증)다. Git에서 제외되며, 원본 PR 커밋 위의 detached worktree다.

## 다른 PC에서 같은 패치 검증

프로젝트 루트의 PowerShell에서 실행한다. 기존 `.venv`가 없으면 먼저 `python tools/bootstrap.py`를 실행한다. 아래 작업 폴더가 이미 존재하면 덮어쓰지 않고 새 이름을 정한다. 명령은 로컬 작업트리와 임시 시험 DB만 바꾸며 서비스를 기동하지 않는다.

```powershell
$taskRepo = (Get-Location).Path
$ticketBase = 'e8db8ecd6aa497ad75df1d89cf01653b6cb5988a'
$ticketPatch = Join-Path $taskRepo 'patches\ticket-store-pr55\0001-resource-via-cycle.patch'
$ticketCheck = Join-Path $taskRepo '.local\ticket-pr55-check-new'
$ticketPython = Join-Path $taskRepo '.venv\Scripts\python.exe'

git fetch origin refs/pull/55/head
if ($LASTEXITCODE -ne 0) { throw 'PR fetch 실패' }
git cat-file -e "$ticketBase^{commit}"
if ($LASTEXITCODE -ne 0) { throw '고정 기준 커밋 없음: 최신 PR과 수동 대조 필요' }
git worktree add --detach $ticketCheck $ticketBase
if ($LASTEXITCODE -ne 0) { throw '새 검증 작업 폴더 생성 실패' }
git -C $ticketCheck apply --check $ticketPatch
if ($LASTEXITCODE -ne 0) { throw '패치 기준 불일치: 강제 적용 금지' }
git -C $ticketCheck apply $ticketPatch
if ($LASTEXITCODE -ne 0) { throw '패치 적용 실패' }
Push-Location $ticketCheck
try {
    & $ticketPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw '회귀 실패' }
    & $ticketPython -m pytest tests/test_contracts.py -q
    if ($LASTEXITCODE -ne 0) { throw '계약 검사 실패' }
} finally { Pop-Location }
```

C가 실제 채택할 때는 최신 PR head와 패치를 대조하고 자기 작업트리가 깨끗한 상태에서 적용한다. 위 명령은 고정 기준에 대한 재현용이다. 최신 PR에 자동 병합·커밋·push하지 않는다.

## D 소비자에 남은 적용과 학원 인수 조건

**실제 D n8n JSON/노드·C 운영 DB는 수정하지 않았다.** 아래는 적용할 구체적인 분기이며 구현 완료 보고가 아니다.

1. 같은 자리의 사건 묶음 조회 `/open`과 자원 조회 `/active`를 나눈다. 중복 비교에는 via를 포함한다. 자원 조회의 `action`은 적용 동작(block 등)이며 해제 동작(unblock)이 아니다. 자산/경로/대상 표기를 정확히 통일한다. 현재 asset_id는 티켓 단위이며 같은 열린 티켓의 자산 변경은 409다. **한 티켓에 서로 다른 집행 자산을 넣어야 하면 조치별 자산 필드·DB 이행이 추가로 필요**하며 이 패치가 다중 집행 자산을 지원한다고 해석하지 않는다. 예시 이름은 합성 값이다.
2. 실제 대응 API를 부르기 **전에** restored를 분기한다. 기존 원복 확인 → 사람이 닫기 → 새 이벤트·새 논리 요청 키로 다음 주기를 시작한다. 이미 대상 반영 후 record가 실패했다면 대상 상태와 기존 요청 키를 먼저 대조하고, 대상 대응 호출을 반복하지 않는다. record의 409는 키를 바꾸거나 자동 반복하지 않는다. 원인 해결 후 같은 기록 키/본문으로만 재시도한다.
3. 원복 전 같은 자원의 모든 활성 조치를 보고 자기 **ticket_id 하나만** 제외한다. 같은 자리의 다른 티켓·다른 봇·닫혔지만 미해제인 티켓도 보류 사유다. 다른 조치가 있거나 조회 실패/불완전/형식 불일치면 해제를 보류한다. 닫힌 과거 티켓의 미해제 조치는 실제 상태를 확인해 수동 정리할 대상이며 자동 DB 삭제/해제하지 않는다.
4. **자원 조회와 실제 해제 사이의 경쟁은 미해결**이다. 이 패치는 읽기 스냅샷을 제공하며 예약/잠금/해제 허가를 제공하지 않는다. 실제 원복·신규 적용을 자원별로 직렬화하거나 소유권 예약을 대상 호출자와 함께 구현·검증하기 전 자동 해제에 연결하지 않는다.
5. C가 채택할 자원 식별·해제 짝 동작·새 주기 정책을 확정하고 별도 시험 DB로 기동한다. 이후 D↔C 인증/URL 인코딩/record/재전송/재시작 보존과 실제 대상의 효과·정상 접근·원복을 확인한다. 기존 VPN·8088 경로의 현재 상태는 확인 필요이며 새 NAT/방화벽을 이 패치가 적용하지 않는다.

학원 장비 시험·포트 개방·공격/차단/해제·팀 메시지·PR 댓글/생성·전역 모델/권한 변경은 이번 작업에서 수행하지 않았다.
