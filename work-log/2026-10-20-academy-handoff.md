# 2026-10-20 집 → 학원 핸드오프

다음 세션은 이 문서 → [기획서-제출전-확인](../team_docs/기획서-제출전-확인.md) → 필요한 PR 순서로 읽는다.

## 작업·상태

| 작업 | 상태 |
| --- | --- |
| 기획서 제출본 | 공지 6개 항목 양식으로 다시 썼다. 미결 7개 결정과 10/19 포털 결정을 반영했다. **팀원 확인 전**, 강사님 답은 가정 |
| 포털 앱 IP 차단 API(봇 112)·S7 파일 키 이벤트 | 구현 완료, Codex 리뷰 반영 완료. Draft PR 상태이며 **병합 전** |

## 브랜치·커밋·PR

| 저장소 | 브랜치 | 커밋 | PR |
| --- | --- | --- | --- |
| aleph-soar-capstone | `docs/proposal-submission-cleanup` (origin/main `3171fb4`에서 분기) | `99c56c1` 내부 표시 정리, `25cdb95` 양식 재구성·결정 반영, 이 문서 | 없음 |
| aleph-soar-capstone | `claude/portal-ip-block-file-key-contract` | `8cbd4ab` 계약 추가, `f42de82` 리뷰 반영 | [#19](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/19) Draft, base `codex/haedam-portal-mvp` |
| haedam-portal-backend | `claude/portal-ip-block-file-key` | `f03c8c1` 구현, `87182e9` MySQL 스냅숏 회귀 수정, `e439681` 리뷰 반영, `983dad6` 테스트 수정 | [#2](https://github.com/NoBugs-Aleph/haedam-portal-backend/pull/2) Draft, base `codex/haedam-portal-mvp` |

두 PR은 아직 병합되지 않은 `codex/haedam-portal-mvp`(capstone #18, backend #1) 위에 쌓았다. Auto-fix는 꺼 두었다. 리뷰 답글과 PR 설명은 최신이다.

## 변경 요약

**기획서** (`team_docs/기획서_합의본.md`, `team_docs/기획서-제출전-확인.md`, 토폴로지 그림 5장)
- 목차를 공지 순서로 맞췄다: ② 위협, ③ 아키텍처, ④ 탐지 규칙·이벤트 조건, ⑥ 일정·역할·위험.
- 10/20 결정을 반영했다: 봇 117, 외부 구역 VMnet5, USB 이더넷 어댑터, 5.9 기본안 채택, MVP S1, S4·S8 순서 요구 안 함, 강사님 질문 담당 김명준.
- 10/19 포털 사실을 반영했다: 해담시청, React + Flask + MySQL, 401 잠금 응답, `request-observed`.
- 결정마다 근거와 강사님 답의 가정은 `기획서-제출전-확인.md`에 있다.
- 그림 스크립트 `team_docs/make_topology_figures.py`는 Windows에서도 PNG를 쓰도록 고쳤다. 실행 명령: `python team_docs/make_topology_figures.py --chrome "<Edge 경로>"`

**포털**
- IP 차단 API: `/api/v1/response/ips/block`·`/unblock`·`GET /ips`, 차단된 출발지는 403 `IP_BLOCKED`
- 같은 키 재전송은 처음 응답을 재생하고, 동시 충돌은 서버가 새 트랜잭션으로 다시 처리한다.
- 보호망 주소: block은 거부하고, unblock은 허용한다.
- `web.file_access` 이벤트에 `file_key`를 남긴다. 계약 규칙을 어기는 파일은 서빙하지 않는다(404).
- 출발지 해석은 `client_ip` 하나로 통일했다.
- 마이그레이션 `7c2e9a41d5b3`(`blocked_ips` 테이블)

## 실행한 확인

- 백엔드: SQLite 39 passed / 3 skipped(MySQL 전용)
- 백엔드 `tools/check_mysql.py`(일회용 MySQL 8.4): 마이그레이션 정상, 42 passed. 같은 키 동시 요청 테스트는 수정 전 코드에서 실패하는 것을 확인했다.
- capstone: `pytest -q` 32 passed, AI assets 14 verified
- 기획서: 공지 항목 제목 23개 존재, 내부 표시 0건, 로컬 링크 끊김 0건

## 미실행·미연결

- 랩 구성, Graylog·Wazuh·n8n·pfSense 연동, 사전 위험 시험 ①~③(0건)
- 프론트 계약 사본 갱신(아직 `2303265` 기준, 배포·인수 체크 항목)
- 제출용 PDF
- 실제 DB 장애·부하 시험

## 필요한 입력

- 강사님 답 1~6. 특히 1번 제출 형식(파일 형식·분량·양식·제출 방법).
- 10/20 결정 7개에 대한 팀원 의견(10/21까지)

## 학원 PC에서 받기

학원 PC의 capstone 폴더(`C:/SKT aleph/aleph-soar-capstone`)에는 미커밋 작업이 남아 있을 수 있다. 먼저 `git status --short`로 확인하고, 강제로 지우거나 브랜치를 바꾸지 않는다. 깨끗하지 않으면 `git worktree add`로 새 폴더에서 연다.

```powershell
git fetch origin
git worktree add ..\aleph-proposal-cleanup docs/proposal-submission-cleanup
```

포털을 시험하려면 backend를 `claude/portal-ip-block-file-key`, capstone을 `claude/portal-ip-block-file-key-contract`로 받는다. `.venv`·DB·비밀값은 학원 PC에서 새로 준비한다.

## 다음 첫 작업 (마감 순서)

1. **강사님께 질문 1~6** (10/21까지)
2. **기획서 PR을 팀원에게 공유하고 확인 받기** (10/21 마감)
3. **기획서 진행 현황 표 고치기:** IP 차단 API와 파일 키는 backend #2로 구현됐다(미병합). "10/24~10/28에 추가" 문구를 바꾼다.
4. **PR #19 CI 결과 확인**
5. **사전 위험 시험:** 학원 PC에서만 할 수 있다. VMnet3·4·5와 수업 VM의 충돌, USB 이더넷 어댑터, n8n → pfSense 차단, Graylog·Wazuh 동시 구동 `docker stats`.
6. **10/22~23 제출본 PDF 만들고 제출**

## 다음 채팅 시작 문장

```text
work-log/2026-10-20-academy-handoff.md를 읽고 학원에서 이어서 하자.
먼저 학원 PC의 git 상태를 확인하고 docs/proposal-submission-cleanup 브랜치를 받아줘. 미커밋 작업은 지우지 마.
```
