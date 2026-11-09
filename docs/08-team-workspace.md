# 팀원이 작업을 시작하는 방법

이 작업공간은 4명이 각자 Claude 또는 Codex를 사용해 같은 기준으로 개발하기 위한 뼈대입니다. 현재 동작하는 앱은 시작 화면과 상태 API뿐입니다.

## 저장소 받기

모든 준비 내용은 `main`에 있습니다.

```powershell
git clone https://github.com/NoBugs-Aleph/aleph-soar-capstone.git
cd aleph-soar-capstone
```

사람마다 별도 clone을 사용하며 한 로컬 폴더를 여러 작업자가 동시에 수정하지 않습니다.

## 공통 환경 준비

Python 3.12 이상이 필요하며 CI는 3.13에서 검사합니다. 아래 명령은 프로젝트 내부에만 `.venv`를 만들고 잠긴 개발 의존성·앱을 설치한 뒤 테스트합니다. Claude·Codex 계정이나 전역 설정은 변경하지 않습니다.

```powershell
python tools/bootstrap.py
```

Python이 `py` 명령으로 설치된 Windows에서는 `py -3.13 tools/bootstrap.py`를 사용해도 됩니다. 이미 있는 `.venv`가 다른 운영체제용이면 새 clone에서 준비합니다.

Windows의 이후 명령은 `.\.venv\Scripts\python.exe`, macOS·Linux는 `./.venv/bin/python`을 사용합니다. 가상 환경을 활성화했다면 `python`으로 줄여 쓸 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m flask --app aleph_soar:create_app run --host 127.0.0.1 --port 5000
```

브라우저에서 `http://127.0.0.1:5000`과 `/api/v1/health`를 확인합니다. MySQL·Graylog·Wazuh·n8n 없이 뼈대부터 실행할 수 있습니다. 해당 도구 연동은 팀 구현 작업입니다.

## 내 작업 고르기

작업 전 `main`의 최신 내용을 받고 작업 브랜치를 만듭니다. 브랜치 이름은 [협업 방법](../CONTRIBUTING.md)의 접두사를 따릅니다.

```powershell
git switch main
git pull
git switch -c feature/my-task
.\.venv\Scripts\python.exe tools/team.py ready
.\.venv\Scripts\python.exe tools/team.py brief P01
```

P01에서 주제·MVP·계약을 확인한 뒤 B01(앱), D01(탐지/대응), U01(화면)을 병렬 진행할 수 있습니다. 선행 완료가 검증됐다면 `--done P01`을 붙여 다음 후보·지시서를 출력합니다. 명령은 공유 상태를 저장하거나 AI를 실행하지 않습니다. 실제 담당·진행 상태는 연결한 GitHub 이슈·PR과 팀 합의로 관리합니다.

## 작업 경계

| 영역 | 기본 담당 역할 | 시작 위치 |
| --- | --- | --- |
| 공통 규격·조율 | coordinator | contracts/, docs/API-CONTRACT.md, orchestration/ |
| 인증·권한·조회·대응 대상 API | backend | src/aleph_soar/portal/ |
| 수집·상관·대응·원복 | detection | src/aleph_soar/detection/, response/ |
| 사건·타임라인 화면 | dashboard | src/aleph_soar/templates/, static/ |
| 통합·독립 검증 | reviewer + coordinator | tests/, docs/ |

역할은 사람 배정표가 아닙니다. 4명이 겸하거나 교환할 수 있습니다. 공통 app factory·라우트·의존성 변경은 연결 담당과 조율합니다. 해당 기능 담당은 테스트도 함께 관리합니다.

## 변경 확인과 인수인계

가상 환경의 Python으로 실행합니다.

```powershell
python -m pytest -q
python tools/sync_ai_assets.py --check
python tools/team.py validate
```

관련 기능 검증 결과와 [인수인계 양식](../orchestration/handoff-template.md)을 PR에 남깁니다. 업무 기능을 구현한 뒤에는 뼈대 검사 통과와 별도로 실제 시나리오·대응·원복을 검증합니다.

의존성 변경 시 pyproject.toml을 수정하고 깨끗한 가상 환경에서 `pip freeze --exclude-editable` 결과로 requirements-dev.lock을 갱신합니다. editable 로컬 경로·개인 패키지를 제외하고 build에 필요한 setuptools도 포함합니다.

## 파일 안내

```text
AGENTS.md                  공통 작업 규칙
CLAUDE.md                  공통 규칙을 불러오는 Claude 진입점
.agents/skills/            스킬 원본
ai/roles/                  역할 원본
.claude/skills/, agents/   Claude용 생성물
.codex/agents/             Codex용 생성물
contracts/                 공통 스키마·합성 예시
orchestration/             작업 DAG·인수인계 양식
src/aleph_soar/            앱 뼈대·역할별 작업 경계
tests/                     앱·계약·AI 자산·작업 DAG 검증
tools/                     환경 준비·AI 파일 동기화·작업 지시서
```
