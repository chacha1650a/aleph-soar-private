# NoBugs 공통 작업 규칙

## 시작·실행·확인

- 최초 준비: `python tools/bootstrap.py` — 프로젝트 안의 `.venv`를 만들고 잠금 의존성과 앱을 설치한 뒤 검사합니다.
- 실행(Windows): `.\.venv\Scripts\python.exe -m flask --app aleph_soar:create_app run --host 127.0.0.1 --port 5000`
- 아래 `python` 명령은 설치된 `.venv` 인터프리터로 실행합니다.
- 검증: `python -m pytest -q`
- AI 파일 동기화: `python tools/sync_ai_assets.py --check`
- 작업 순서·지시서: `python tools/team.py ready`, `python tools/team.py brief P01`

## 현재 상태

4인(GitHub: myeongjundev, whiteclover0542, chacha1650a, shk12170-dev)이며 모두 Claude, 그중 2명은 Codex도 사용합니다. 팀 현황은 docs/PROGRESS.md, 합의 기록은 docs/07-topic-decision.md에 있습니다. 사용자의 명시 지시와 결정이 기본 진행 방식보다 우선합니다.

2026-10-19 팀 합의: 도메인은 **공공기관**입니다(가상 OO시청의 민원 포털·내부 업무 시스템·외주 유지보수 VPN·보안관제망). 기준은 team_docs/기획서.md(whiteclover0542 초안)와 docs/11의 검토 메모입니다. 이전의 통신사 외주 유지보수 포털(docs/20~24 등)은 논의 이력입니다. 10/19에 필수 케이스와 자리 담당(A whiteclover0542, B myeongjundev, C shk12170-dev, D chacha1650a)을 정했고, 팀원 4명은 같은 학원 PC(RAM 16GB)를 쓰며, 관제 PC와 공격·서비스 PC는 이웃한 두 자리로 정합니다.

2026-10-16 공식 공지: 기획서 10/23(금), 리허설 11/5(목), 본발표 11/6(금). 평가는 기능 개수보다 구현 완성도와 실측 검증이며, 시연에서 공격 → Graylog·Wazuh 탐지 → n8n 자동 대응 → IP 차단·인시던트 생성 → 정상 동작을 보여야 하고 자동 대응의 원복 절차가 필요합니다. 강사님 설명(필기, docs/11): 보안 3대 원칙 반영, 팀당 4케이스(각자 1개), NIDS(Snort·Suricata), 게시판 보안 대시보드, VMnet 내부망입니다. 밴드에 올라온 토폴로지는 참고용입니다(10/19 사용자 확인).

2026-10-15 사용자 확인: Wazuh, Graylog, pfSense, n8n, Kali Linux, Docker를 사용하고 이후 다른 팀 작업물과 공방전을 진행할 예정입니다. 설계는 이 도구 구성과 팀 간 공방전을 고려합니다. 각 도구의 배치·버전·연결 방식과 공방전 일정·대상·규칙·채점 기준은 미정이며, 사용 예정과 실제 설치·연동·시험 완료를 구분합니다.

앱은 시작 화면과 상태 API가 있는 스켈레톤입니다. 인증·탐지·대응·원복은 미구현이며 contracts/examples는 합성 계약 예시입니다.

## 연결 기준과 작업 경계

- 2026-10-19 사용자 결정: 가상 기관명은 **해담시청**, 프론트·백엔드는 `haedam-portal-frontend`·`haedam-portal-backend` 별도 저장소로 준비합니다. [분리 안내](docs/haedam/README.md), [공통 제약 원본](docs/haedam/PROJECT-RULES.md), [작업 카드](docs/haedam/TASKS.md)를 따릅니다. `scaffolds/`는 복사용 뼈대이며 저장소 생성·구현·기존 앱 이전 완료를 뜻하지 않습니다.
- 10/19 집 세션 사용자 결정: 민원포털의 프론트·백 구현은 김명준과 Codex가 맡으며 **React + Flask**를 선택했습니다. [구현 brief](docs/haedam/MVP-TASK-BRIEF.md), [포털 API](docs/haedam/PORTAL-API.md)를 사용합니다. 기존 A~D 보안 케이스 책임·독립 리뷰 배정·실제 두 PC 관제 연동은 별개입니다.
- API·이벤트·사건 변경은 docs/API-CONTRACT.md와 contracts/의 해당 스키마·예시·소비자를 함께 맞춥니다. 미구현 경로를 성공으로 위장하지 않습니다.
- 역할 원본은 ai/roles/, 작업 의존성과 완료 조건은 orchestration/workplan.json입니다. 수정할 담당 영역과 연결 파일을 확인합니다.
- 공통 규칙은 이 파일에 둡니다. CLAUDE.md는 이를 불러오는 진입점입니다.
- 스킬 원본은 .agents/skills/입니다. .claude/skills/, .claude/agents/, .codex/agents/는 생성물이며 원본을 고친 뒤 `python tools/sync_ai_assets.py`로 갱신합니다.
- 로컬 검증과 격리된 테스트 데이터 수정은 작업 범위 안에서 진행합니다. 모델·권한·계정의 전역 설정을 이 저장소의 규칙으로 바꾸지 않습니다.

## 필요한 작업별 스킬

- 작업 분할·인수 조건: aleph-task-plan
- 공통 API·이벤트·사건 계약 변경: aleph-contract-change
- 구현된 탐지·대응 시나리오 검증: aleph-scenario-check
- 다른 담당·세션·PR로 결과 전달: aleph-handoff
- 팀 Notion 회의록·결정 기록 작성·정리: aleph-team-notion (역할: aleph-scribe)

해당 작업에 필요한 스킬과 문서만 읽습니다. 문구 수정에 전체 계획이나 시나리오 검증을 요구하지 않습니다.

## 협업과 결과 기록

개인의 일일 작업은 `work-log/members/<GitHub 사용자명>/YYYY-MM-DD.md`에 한국 시간 기준으로 기록합니다. `work-log/TEMPLATE.md`와 `work-log/members/README.md`를 따르고 같은 날 작업은 같은 파일에 추가합니다. 기존 개발 일지·공통 인수인계는 보존하고, 다른 팀원의 미확인 작업을 대신 완료 처리하지 않습니다.

작업 브랜치와 PR 흐름은 CONTRIBUTING.md를 따릅니다. 같은 파일을 동시에 쓰는 작업은 담당을 정리합니다. 작업 조율 도구의 `--done`은 조율 담당이 제공한 선행 작업 입력이며 검증 결과나 공유 작업 상태를 대신하지 않습니다.

원본 자료의 실측과 팀의 실행 결과, 앱 로그 관찰과 DB 직접 감사, 샘플과 실제 연결 상태를 구분합니다. 비밀번호·토큰·원문 민감 데이터는 이벤트·증적에 기록하지 않습니다. 인수인계에는 실제 확인 결과와 미검증 부분을 적습니다.
