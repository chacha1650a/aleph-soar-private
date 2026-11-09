# security-lab 하네스

팀원과 LLM 에이전트가 같은 규칙으로 일하도록 만든 규약 묶음이다.
이 폴더의 파일을 프로젝트 저장소 루트에 그대로 복사해서 쓴다.

## 파일 구성

| 파일 | 누가 읽나 | 내용 |
|---|---|---|
| `AGENTS.md` | 모든 LLM, 팀원 | 공통 규칙의 원본. 절대 규칙 R1~R10 |
| `CLAUDE.md`, `GEMINI.md`, `.cursorrules`, `.github/copilot-instructions.md` | 각 도구 | `AGENTS.md`를 읽으라는 포인터. 여기에 규칙을 추가하지 않는다 |
| `harness/01-project-context.md` | 전원 | 목표, 사례, 티켓, 프로젝트 환경, MockTel |
| `harness/02-ownership.md` | 전원 | 역할과 경로별 주인, 잠긴 파일 |
| `harness/03-id-registry.md` | 전원 | 규칙 ID, SID, IP, 포트, 스냅샷 이름 |
| `harness/04-workflow.md` | 전원 | claim → 브랜치 → 커밋 → worklog → PR → 종료 |
| `harness/05-safety.md` | 전원 | 대상 제한, 비밀값, 증거 보존 |
| `harness/06-templates.md` | 전원 | claim, worklog, 티켓, PR, 스크립트 머리말 |
| `security-lab-harness.pdf` | 전원 | 위 내용을 한 파일로 모은 인쇄용 |

## 처음 세팅하는 사람(docs)이 할 일

1. 이 폴더 내용을 저장소 루트에 복사하고 `.claims/` 폴더를 만든다.
2. `harness/02-ownership.md`의 담당자 칸을 채운다.
3. 첫 커밋: `[SETUP] docs: 하네스 추가` (티켓이 없는 초기 설정용 접두사, `harness/04-workflow.md` 참고)
4. 각 팀원은 자기 LLM 도구로 세션을 열 때 "AGENTS.md를 읽고 INC-0X를 <역할>로 진행해"라고 시작한다.

## 규칙을 바꾸고 싶을 때

`AGENTS.md`와 `harness/`는 docs만 수정한다. 다른 사람은 PR로 제안한다.
pdf는 md를 고친 뒤 다시 만든다. 내용이 다르면 md가 기준이다.
