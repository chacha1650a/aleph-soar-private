# 2026-10-15 상세 작업 기록

기준: Asia/Seoul · 프로젝트 `NoBugs-Aleph/aleph-soar-capstone` · 작성 Codex

## 1. 오늘의 결과와 현재 위치

별도 팀 저장소와 실행 가능한 공통 스켈레톤을 준비하고, 주제 후보·팀원 의견·Claude 검토·차별화 실험을 거쳐 **생산관리·협력사 포털 + 가상 설비 데이터** 범위의 스마트팩토리 로드맵을 작성했습니다. 주제명·실제 제품·인프라·담당·평가 요건 전체가 확정된 것은 아닙니다.

- 원격: [NoBugs-Aleph/aleph-soar-capstone](https://github.com/NoBugs-Aleph/aleph-soar-capstone). 기록 세션에서 비공개 저장소이며 기본 브랜치가 `main`임을 확인했습니다.
- 작업 폴더: `C:\SKT aleph\aleph-soar-capstone`. 기존 `flask-board-team`·`flask-board` 실습 저장소와 구분됩니다.
- 오늘 마감 브랜치: `codex/smart-factory-roadmap`.
- 로드맵 커밋: [`de0b69f`](https://github.com/NoBugs-Aleph/aleph-soar-capstone/commit/de0b69f69e7cbcaf8227df9ae87846b35039e844).
- 이 기록과 핸드오프는 로드맵 다음 커밋에 함께 저장합니다. 자기 자신이 포함된 커밋 해시는 문서에 고정하지 않고 `git log -1 -- work-log/2026-10-15-daily-work-log.md`로 확인합니다.
- 다음 세션의 요약과 명령: [핸드오프](2026-10-15-handoff.md).

## 2. 사용자에게 확인한 조건과 미정 사항

| 구분 | 내용 |
| --- | --- |
| 인원·기간 | 본인 포함 4명, 2주. 정확한 제출일·하루 가용 시간은 미확인 |
| AI 사용 | 전원 Claude, 사용자와 팀원 1명은 Codex도 보유 |
| 관심 방향 | 계정 이상·자동 대응, 침해 흐름 관제, 권한·데이터 접근 추적 |
| 다른 팀 | 다섯 팀의 주제가 겹칠 수 있다는 우려. 다른 네 팀의 실제 주제·기술은 모름 |
| 후속 서비스 범위 | 사용자 선택: 생산관리·협력사 포털 + 가상 설비 데이터 |
| 수업 요건 | 4계층·SOAR·특정 제품 의무 여부 미확인. 4계층 필수는 논의상 가정으로 사용 |
| 최종 합의 | 상세 주제·제품·담당·범위 변경은 팀 합의 전 |

## 3. 참고 자료 확인과 저장소 준비

제공받은 167 HTML 슬라이드와 168 Notion을 바탕으로 엣지–네트워크–앱–데이터, 로그 수집·상관, 자동 대응·원복의 계획 문서를 작성했습니다. 별도의 Notion 협업 프로젝트 시작 가이드는 팀 공통 규칙·역할·스킬·작업 조율 구조를 설계하는 참고로 사용했습니다.

참고 문서의 설치·실행 절차를 사용자의 명령으로 취급하지 않았습니다. 자료의 실측 수치·완료 표시와 팀의 구현 상태를 구분했고, 원본의 IP·포트·버전을 우리 환경의 확정값으로 복사하지 않았습니다.

- [기획](../docs/01-project-plan.md), [아키텍처](../docs/02-architecture.md), [시나리오](../docs/03-scenarios.md), [백로그](../docs/04-backlog.md), [출처·적용 범위](../docs/05-references.md) 작성.
- 로컬 원본 사본은 `references/local/` 제외 규칙으로 Git에 올리지 않도록 구성.
- 팀원이 공동 작업할 별도 저장소, README, 협업 방법, 이슈·PR 작성 기반 준비.

## 4. Claude와 논의할 작업공간 준비

- [논의 안내](../docs/06-topic-discussion.md), [시작 프롬프트](../prompts/claude-topic-discussion.md), [시작 스크립트](../Start-ClaudeDiscussion.ps1) 준비.
- Claude 시작 요청은 ASCII 한 줄로 전달하고 계획 모드로 시작하도록 구성. PowerShell 실행 정책 때문에 스크립트가 차단될 때의 실행 방법 안내.
- [주제 결정 기록](../docs/07-topic-decision.md)에 확인된 조건, 후보, MVP·분업·일정 제안과 최종 미정 항목을 분리.
- 현재 자료를 확인하고 다음 결정을 이어갈 수 있게 문서 연결.

## 5. 공통 개발 스켈레톤과 검증 기반

### 실행 앱·계약

- Python 패키지 `src/aleph_soar/`, Flask 앱 팩토리·시작 화면·정적 파일·상태 API 구성.
- 현재 동작 경로는 `GET /`, `GET /api/v1/health`입니다. 상태의 `stage=scaffold`는 DB·SIEM·업무 기능 준비 완료를 뜻하지 않습니다.
- `portal/`, `detection/`, `response/`의 담당별 확장 위치 마련. 인증·탐지·대응·복구 로직은 미구현.
- [API 계약](../docs/API-CONTRACT.md), [이벤트 스키마](../contracts/event.schema.json), [사건 스키마](../contracts/incident.schema.json), [합성 예시](../contracts/examples/) 준비.
- 앱 이벤트 4종은 로그인 실패·성공, 권한 변경, 자료 조회. 실제 사건 탐지·임계값 검증 자료가 아닌 계약 예시입니다.
- 비밀번호·토큰 같은 추가 필드를 허용하지 않는 스키마와 날짜·IP 형식 검증 구성. 날짜 형식 검사 누락을 막기 위해 `jsonschema[format-nongpl]` 의존성 사용.

### 공통 규칙·역할·스킬

- [AGENTS.md](../AGENTS.md)를 공통 규칙으로, [CLAUDE.md](../CLAUDE.md)를 Claude 진입점으로 구성.
- `ai/roles/`에 coordinator·backend·detection·dashboard·reviewer 역할 원본 5개 준비.
- `.agents/skills/`에 task-plan·contract-change·scenario-check·handoff 스킬 원본 4개 준비.
- `tools/sync_ai_assets.py`로 Codex·Claude 어댑터 14개 생성·검사. 생성 파일의 개별 수정 대신 원본 동기화 원칙 적용.
- 모델·권한·계정의 전역 설정을 바꾸지 않고 저장소 안에서 공유하도록 설계.

### 작업 조율·환경·CI

- [작업 DAG](../orchestration/workplan.json): P01 → B01/D01/U01 → I01 → V01의 6개 작업.
- `tools/team.py`의 validate·ready·brief로 의존성과 담당 범위·완료 조건 제공. 실제 에이전트 실행·공유 상태 저장 기능은 아닙니다.
- `--done`은 조율 담당의 입력값이며 검증 완료를 자동 증명하지 않습니다.
- `tools/bootstrap.py`, 잠금 의존성, 팀원 온보딩, 인수인계 양식 준비.
- Windows·Ubuntu CI 구성. Claude가 push 트리거를 main으로 한정해 PR 브랜치의 중복 실행을 줄이고, 온보딩의 pull·브랜치 예시를 정리.
- 스켈레톤·계약·조율·AI 파일 관련 테스트 29개 구성. 실제 업무 시나리오 시험과 구분합니다.

## 6. 주제 후보·팀원 의견·Claude 검토

### 후보와 팀원 제안

[후보 8개](../docs/10-topic-candidates.md)를 만들어 쇼핑몰 관리자 보호, 문서 접근, 제조 협력사, API 키, 클라우드 계정, 운영 변경, 대응 검증, 사건 재생을 비교했습니다. 사용자 요청대로 여러 사례와 투표 양식을 제공했고 채택 결과는 가정하지 않았습니다.

Claude는 [팀원 의견 기록](../docs/11-team-feedback.md)에 whiteclover0542의 원문과 별도 검토 메모를 보관했습니다. 제안은 A를 배경으로 B·G를 MVP에 넣고 H는 여유가 있을 때 간단히 추가하는 방향입니다.

- A: 쇼핑몰 관리자 계정 보호.
- B: 고객 자료 조회·반출 탐지.
- G: 조치 후 실제 차단·해제 결과 확인.
- H: 시나리오 반복 실행.

### PR #2 · 4계층 필수 가정 검토

[추가 검토 문서](../docs/12-four-layer-topic-review.md)와 [PR #2](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/2)를 작성했습니다. 계층별 제어·증거, 기존 세션 접근 차단, 계약 보완점, 4인 분업, Claude 질문 5개를 정리했습니다.

[Claude R01 코멘트](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/2#issuecomment-6187601400)는 A+B+G에 동의하며 계층 간 실제 연결, 엣지 우회 차단, 프록시 신뢰 경계, DB 감사의 선행 검증과 권한 복구 기준을 제안했습니다.

Codex 추가 판단:

- 요청 ID는 한 요청의 계층 간 연결에 사용하며 여러 로그인·조회 요청으로 된 사건에는 계정·자산·시간 순서가 별도로 필요.
- SQL 주석의 요청 ID가 실제 감사 기록에 남는지는 제품·설정 검증 전까지 가설.
- `previous_role` 한 값으로 자동 복구를 결정하지 않고 신뢰할 변경 이력·현재 상태·후속 정상 변경을 함께 확인.
- 이벤트 중복 제거는 아직 미구현. 사건 배열의 중복 금지 스키마와 수집 중복 제거를 구분.

### PR #3 · 차별화 방향과 비교 실험

[심화 후보 문서](../docs/13-topic-differentiation-proposal.md)와 [PR #3](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/3)를 작성했습니다. 후보는 ① 대응 효과·업무 복귀 검증, ② 협력사 임시 권한, ③ 불완전한 로그의 사건 연결입니다. Codex는 ①을 중심으로 같은 IP의 정상 사용자 업무 대조를 추가하는 안을 추천했습니다.

T1~T6은 정상 업무, 기존 세션, 조치 미적용, 중복 조치, 복구 후 세션 재사용, 권한 충돌의 제안 시험입니다. 현재 실행 결과는 없습니다.

[Claude R02 코멘트](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/3#issuecomment-6187894396)는 ①에 동의하면서 명칭 통일, B 축소의 팀 합의, T4 필수화, 세션 버전, 비밀번호 재설정, 비교 조건 일치 등을 제안했습니다.

Codex 추가 판단:

- 자격 증명 유출을 가정한 시나리오에는 비밀번호 재설정과 이전 비밀번호 거부 검증 필요. 실패 후 성공 로그만으로 실제 유출을 확정하지 않음.
- 실패 주입 자체는 유효한 시험 방식. 동일 조건·정상 사례·독립적인 실제 접근 판정으로 비교를 설계.
- 같은 논리 조치의 재시도는 같은 `operation_id`, 새로운 재잠금 등에는 새 ID 필요. 사건+조치 종류만 고정하면 재대응 구분 부족.
- 현재 정상 사용자가 보이지 않는다는 이유만으로 공유 IP 차단을 안전하다고 판단하지 않음. 기본 대응은 계정 단위.
- 40인·일 배분은 Claude의 가정치이며 실제 가용 시간 확인 없이 확정 일정으로 쓰지 않음.

## 7. 스마트팩토리 범위 선택과 2주 로드맵

사용자가 서비스 배경으로 생산관리·협력사 포털과 가상 설비 데이터를 선택하여 [스마트팩토리 로드맵](../docs/14-smart-factory-roadmap.md)을 추가했습니다. README·백로그·주제 기록에 연결했습니다.

- 가상 라인 A·B, 설비 2개, 온도·생산 수량·상태·시각·순번 생성.
- 생산관리자·협력사 정비 담당자·보안/복구 담당자·별도 수집 계정의 역할 분리.
- 화면 4개: 로그인·생산 현황·자료 조회·사건 상세.
- 협력사 계정 대응 중 정상 직원의 업무와 가상 수집의 지속 여부를 기록으로 검증.
- 비밀번호 재설정, 예전 세션 폐기, 신뢰할 권한 복구, 충돌 시 자동 덮어쓰기 중단 포함.
- 실제 MES 전체·PLC 제어·물리 공정 복구는 포함하지 않고 포털과 가상 수집의 시험으로 범위를 명시.
- 2일차 세션·계층 연결 작은 실험, 3~4일차 첫 통합, 7~8일차 복구, 9~10일차 대조 시험, 나머지 재현·발표·여유 시간 제안.
- 인프라/수집, 포털/데이터, 탐지/대응, 화면/통합 검증의 4개 작업 묶음 제안. 실제 담당 배정과 인프라 역할·DAG 반영은 후속 작업.

## 8. 실제 검증 결과

아래는 **오늘 마감 기록 세션에서 직접 다시 실행한 로컬 결과**입니다. 스마트팩토리 기능이나 T1~T6 통과를 뜻하지 않습니다.

| 명령 | 결과 |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest -q` | 29 passed in 1.95s |
| `.venv\Scripts\python.exe tools/sync_ai_assets.py --check` | AI assets verified: 14 |
| `.venv\Scripts\python.exe tools/team.py validate` | Valid task DAG: 6 tasks |
| `.venv\Scripts\python.exe tools/team.py ready` | P01 준비 후보. 완료 작업 입력 없음 |
| `.venv\Scripts\python.exe -m pip check` | No broken requirements found |

로드맵 작성 시 변경 문서의 로컬 링크 34개·누락 0개를 확인했습니다. 이번 work-log 추가 후 링크와 staged diff 형식을 별도로 확인한 결과는 아래 마감 절차 기록에 남깁니다.

원격 CI 근거:

- [PR #2 CI](https://github.com/NoBugs-Aleph/aleph-soar-capstone/actions/runs/38701569168): `fc5e3e4` 기준 Windows·Ubuntu 통과.
- [PR #3 CI](https://github.com/NoBugs-Aleph/aleph-soar-capstone/actions/runs/38705502907): `de576a4` 기준 Windows·Ubuntu 통과.
- 현재 로드맵·일일 기록 브랜치의 새 커밋에 대한 원격 CI 통과를 의미하지 않습니다. workflow는 main push 또는 PR에서 실행되므로 이번 브랜치 push만으로 CI가 실행된다고 가정하지 않습니다.

## 9. 커밋·PR 이력

커밋 시각은 Git 기록의 한국 시간입니다.

| 시각 | 커밋 | 내용 |
| --- | --- | --- |
| 14:08 | `d27c530` | 초기 기획 저장소 |
| 14:19 | `a037e67` | Claude 논의 작업공간 |
| 15:08 | `a58abdd` | Claude 시작 요청·PowerShell 안내 |
| 15:18 | `fcac360` | 4인·2주 조건과 MVP 제안 |
| 15:42 | `8df89c7` | 공통 스켈레톤·AI 협업 기반 |
| 15:52 | `b0c67a8` | 후보 8개·투표 자료 |
| 16:04 | `6e88713` | Claude의 브랜치 안내·CI·논의 상태 정리 |
| 16:43 | `54dc1a0` | Claude의 팀원 원문·검토 메모 보관 |
| 16:51 | `fc5e3e4` | 4계층 검토 문서·PR #2 |
| 17:24 | `de576a4` | 심화 후보·실험 제안·PR #3 |
| 마감 세션 | `de0b69f` | 스마트팩토리 로드맵 |

원격 확인 시 PR #1·#2·#3은 모두 OPEN이며, 오늘 자동 병합하지 않았습니다.

| PR | base ← head | 내용 |
| --- | --- | --- |
| [#1](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/1) | `main` ← `codex/claude-topic-discussion` | 팀 작업공간·스켈레톤 |
| [#2](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/2) | `codex/claude-topic-discussion` ← `codex/four-layer-topic-review` | 4계층 검토 |
| [#3](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/3) | `codex/four-layer-topic-review` ← `codex/topic-differentiation-proposal` | 심화 후보·추천 |

현재 `codex/smart-factory-roadmap`은 PR #3 head의 `de576a4`에서 시작했습니다. 오늘 요청은 커밋·푸시·기록이며 이 브랜치의 새 PR은 만들지 않습니다. 기존 PR 병합 후 다음 PR을 만들 때는 base를 다시 확인합니다.

## 10. 남은 일과 미구현

- 실제 수업 요건·마감일·필수 제품·대체 수단 인정 여부·샘플 허용 범위 확인.
- 스마트팩토리 상세 주제·MVP·팀원 B 기능 범위·실제 담당·가용 시간 합의.
- 인프라 역할과 DAG, 포털·센서·보안 이벤트·조치/복구 계약 설계.
- Flask 업무 기능, DB·WAF·방화벽·Graylog·n8n·Wazuh 연동 미구현.
- 가상 생성기·수집 계정·생산 현황·계정 대응·복구·T1~T6 미구현·미실행.
- 실제 공장·실제 개인정보·실제 설비에 대한 연결이나 검증 없음.
- 주제 확정 뒤 07을 결정의 진입점으로 정리하고 과거 후보·검토는 참고 기록으로 표시.

## 11. 마감 절차 기록

로드맵을 먼저 커밋한 뒤 상세 기록·핸드오프·색인을 별도 기록 커밋으로 묶습니다. 최종 기록 커밋 해시는 이 파일의 Git 이력에서 확인합니다.

- 전체 Markdown 44개, 로컬 링크 102개 검사: 누락 0개.
- `git diff --check` 및 `git diff --cached --check`: 통과.
- 스테이징 범위: README의 작업 기록 링크, `work-log/README.md`, 상세 일일 기록, 핸드오프. 로드맵은 앞선 `de0b69f`에 포함.
- 원격 대상: `origin/codex/smart-factory-roadmap`. 최종 마감 단계에서 `git push -u origin codex/smart-factory-roadmap` 후 HEAD·원격 참조 일치와 작업 트리 상태를 확인합니다. 원격 동기화의 실제 결과는 최종 응답·Git 원격 참조로 확인할 수 있습니다.

```powershell
git log -2 --oneline
git rev-parse HEAD
git rev-parse origin/codex/smart-factory-roadmap
git status --short --branch
```

두 해시가 같으면 조회 시점에 로컬 HEAD와 원격 추적 참조가 일치합니다. 원격의 최신 상태를 다시 확인하려면 먼저 `git fetch origin`을 실행합니다.
