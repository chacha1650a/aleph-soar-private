# 04. 작업 절차

사람과 LLM 에이전트 모두 이 순서를 그대로 따른다. 단계를 건너뛰지 않는다.

## 1. 시작 전 확인

```bash
git checkout main && git pull
ls .claims/
```

- 내 티켓의 claim 파일이 이미 있고 주인이 다르면 **멈춘다.**
- 내 작업이 수정할 경로를 다른 claim이 이미 적어 두었으면 **멈춘다.**

## 2. 선점 (claim)

`.claims/INC-0X.claim` 파일을 만든다. 하위 작업이면 `INC-0X-<설명>.claim`.
형식은 `harness/06-templates.md`의 claim 템플릿을 따른다.

claim은 **main에서 직접** 커밋·푸시한다. 이것이 R5의 유일한 예외이며, 이 커밋에는 `.claims/` 파일 외에 다른 변경을 넣지 않는다.

```bash
git add .claims/INC-01.claim
git commit -m "[INC-01] claim: 패킷 소켓 탐지 규칙 작업 시작"
git push
```

- 파일 이름이 작업마다 다르므로 claim끼리는 충돌하지 않는다.
- 푸시가 거절되면(다른 사람이 먼저 같은 이름으로 올림) `git pull` 후 1단계부터 다시 한다.

## 3. 브랜치

```
<역할>/<티켓>-<짧은-영문-설명>
```

예: `host/INC-01-packet-socket-rule`, `net/INC-04-idor-threshold`, `avail/INC-06-haproxy-failover`

```bash
git checkout -b host/INC-01-packet-socket-rule
```

## 4. 작업

- claim의 `paths`에 적은 경로만 수정한다.
- 범위가 늘면 먼저 claim을 고쳐 커밋하고 나서 작업한다.
- 번호(규칙 ID, SID, 포트)는 `03-id-registry.md`의 내 대역에서만 고른다.

## 5. 커밋

```
[INC-0X] <종류>: <한국어 한 줄 설명>

<필요하면 본문>

Agent: <도구 이름, 사람이면 생략>
```

| 종류 | 언제 |
|---|---|
| `claim` | 선점, 선점 해제 |
| `detect` | 탐지 규칙, 에이전트 설정 |
| `scenario` | 재현·정리 스크립트 |
| `app` | MockTel 코드 |
| `infra` | HAProxy, Nginx, fail2ban 등 설정 |
| `ticket` | 티켓, worklog, 증거 |
| `docs` | 규약, 보고서, 플레이북 |

한 커밋에는 한 종류만 담는다.
저장소 초기 설정처럼 티켓이 없는 작업은 `[INC-0X]` 대신 `[SETUP]`을 쓴다(docs만). 예: `[SETUP] docs: 하네스 추가`

## 6. worklog 기록

`tickets/INC-0X/worklog.md` **끝에** 항목을 추가한다. 기존 줄은 고치지 않는다. 형식은 템플릿을 따른다.

## 7. PR

```bash
git fetch origin && git rebase origin/main
git push -u origin host/INC-01-packet-socket-rule
```

- PR 제목은 첫 커밋 제목과 같은 형식을 쓴다.
- PR 본문은 템플릿을 따른다.
- rebase 중 **내 소유가 아닌 파일**에서 충돌이 나면 직접 해결하지 않는다. `git rebase --abort` 후 그 파일 주인에게 알린다.
- 머지는 사람만 한다. 최소 1명(다른 역할)의 리뷰가 필요하다.

## 8. 종료

PR이 머지된 뒤 claim을 main에서 직접 지운다(R5 예외, `.claims/` 변경만 담는다).

```bash
git checkout main && git pull
git rm .claims/INC-01.claim
git commit -m "[INC-01] claim: 패킷 소켓 탐지 규칙 작업 완료"
git push
```

그리고 프로젝트 문서의 로드맵 상태 칸을 갱신한다.

## 충돌이 났을 때 판단표

| 상황 | 할 일 |
|---|---|
| 같은 티켓을 두 사람이 claim | 먼저 푸시된 쪽이 가진다. 늦은 쪽은 claim을 지우고 다른 작업을 받는다. |
| 내 파일인데 rebase 충돌 | 직접 해결하고 worklog에 남긴다. |
| 남의 파일에서 rebase 충돌 | 중단하고 주인에게 넘긴다. |
| 같은 규칙 ID를 두 곳에서 씀 | 등록부 대역을 확인한다. 대역 밖을 쓴 쪽이 고친다. |
| 잠긴 파일을 고쳐야 함 | docs에 요청하고, 승인 전에는 기대는 작업을 멈춘다. |
| 에이전트가 범위 밖 수정을 제안 | 적용하지 말고 제안 내용만 worklog에 남긴다. |
