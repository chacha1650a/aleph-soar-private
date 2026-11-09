# 2026-10-16 마감 · 집에서 이어서 하기

- 작성: Claude(사용자 명준 요청) · 기준 시점: 2026-10-16 저녁
- 이 문서를 먼저 읽고 이어서 작업한다. 팀 현황은 [PROGRESS](../docs/PROGRESS.md), 팀원 의견과 검토는 [팀원 의견 기록](../docs/11-team-feedback.md)에 있다.

## 1. 저장소 상태

| 위치 | 상태 |
| --- | --- |
| `main` | PR #1~#4 병합 완료(`0a27807`). 10/15~16의 주제 논의, 공지 정리, PROGRESS·개발 일지, 팀 자료가 모두 들어 있다. main CI 성공 |
| PR #5 · `docs/proposal-draft-review` | **열려 있음.** whiteclover0542의 기획서 초안 원본(`team_docs/기획서.md`)과 docs/11 검토 메모, 이 마감 기록이 있다. CI 통과, 충돌 없음. 팀 검토 후 병합 |
| 로컬 전용(원격에 없음) | `.local/`(PDF 추출본 등 검토 중간 산출물), `references/local/`(참고 HTML 원본). 집 PC에는 없으며, 필요하면 원본을 다시 받는다 |

회사 PC의 Claude 세션에서는 PR #5에 Auto-fix를 켜 두었다. 집에서 새 세션을 열면 그 감시는 이어지지 않으므로, PR 상태는 직접 확인한다.

## 2. 집에서 시작하는 방법

```powershell
git clone https://github.com/NoBugs-Aleph/aleph-soar-capstone.git
cd aleph-soar-capstone
git switch docs/proposal-draft-review
python tools/bootstrap.py
```

이미 받아 둔 저장소라면 `git fetch` 후 `git switch docs/proposal-draft-review`, `git pull`만 하면 된다. PR #5가 병합된 뒤라면 `main`에서 이어서 한다.

Claude에게는 이렇게 시작하면 된다.

```text
work-log/2026-10-16-end-of-day-handoff.md를 읽고 이어서 하자.
```

## 3. 오늘 확인된 것

- **공식 공지:** 기획서 **10/23(금)**, 리허설 11/5(목), 본발표 11/6(금). 평가는 "기능 개수보다 구현 완성도와 실측 검증", 시연 필수 장면은 공격 → Graylog·Wazuh 탐지 → n8n 자동 대응 → IP 차단·인시던트 생성 → 정상 동작이다. 요약은 [오후 작업 기록 2절](2026-10-16-claude-topic-direction.md#2-공식-공지-요약-1016-수신).
- **강사님 설명(shk12170-dev 필기):** 보안 3대 원칙 반영, 팀당 4케이스(각자 1개), NIDS(하프오픈 스캔, Snort·Suricata), 게시판 보안 대시보드, 보강 전후 비교, VMnet1~8 내부망, 밴드 토폴로지가 기준 망 구조, VPN.
- **SK 부장님·강사님 조언:** 내부망 실측, 기획과 구성이 중요, 직접 확인.
- **팀 자료:** S1~S10 진행·검증 가이드(PDF), whiteclover0542의 팀 진행 방식 제안과 기획서 초안.
- **도메인:** 공공기관(가상 OO시청)을 제안했고, whiteclover0542의 기획서 초안도 공공기관 기준으로 쓰였다. 다만 팀 전체 합의 기록은 아직 없다.

## 4. 다음 할 일 (우선순위 순)

1. **팀 회신 수합(~10/19):** 공공기관 동의 여부, 맡고 싶은 자리(A~D), PC 사양(RAM). 팀 공유 메시지를 실제로 보냈는지 확인한다(초안은 [오후 작업 기록 부록](2026-10-16-claude-topic-direction.md#부록--팀-공유-메시지-초안-사용자-발송용-미발송)).
2. **PR #5 팀 검토와 병합.**
3. **기획서 합의본 작성(10/23 제출):** 원본은 그대로 두고, [docs/11 검토 메모](../docs/11-team-feedback.md#whiteclover0542--2026-10-16--기획서-초안) 1~11번을 반영한 합의본을 만든다. 핵심은 필수 4종(1인 1종)과 확장 구분, 3대 원칙 매핑, 게시판 보안 대시보드, 보강 전후 비교, VM·RAM 배치표다.
4. **강사님 자료 확보:** 밴드에 올라온 토폴로지 그림, "Graylog 13가지 티켓" 목록, 수업에 S11이 있는지.
5. **기준 문서 갱신(합의 뒤):** `docs/07-topic-decision.md`·`AGENTS.md`의 현재 상태(아직 통신 포털 기준), `docs/08-team-workspace.md`의 "준비 브랜치에서 받기" 안내(이제 main 기준).
6. **사전 위험 시험(가능하면 기획서 전):** Graylog·Wazuh·pfSense를 한 PC에서 함께 띄울 수 있는지, n8n으로 IP 차단 1회, pfSense에서 VPN 세션을 끊는 방법.

## 5. 결정 대기

[PROGRESS 결정 대기](../docs/PROGRESS.md#결정-대기)를 기준으로 한다. 요약하면 도메인 합의, 자리 A~D(처음 제안 또는 3대 원칙 조정안), 게시판 코드(`_7_board_test`) 재사용, VPN 구성, 평가지표 진행 방식, 강사님 설명 후속 확인이다.

## 6. 오늘 작업이 남은 곳

| 기록 | 내용 |
| --- | --- |
| [오후 작업 기록](2026-10-16-claude-topic-direction.md) | 공지, 조언, team_docs, 도메인 비교, S11·S12, 팀 메시지 초안 |
| [R10 Claude 회신](2026-10-16-claude-twelve-ticket-review.md) | 12종 계획 독립 검토 |
| [팀원 의견 기록](../docs/11-team-feedback.md) | whiteclover0542(진행 방식 제안, 기획서 초안), shk12170-dev(강사님 필기), chacha1650a, 검토 메모 |
| [PROGRESS](../docs/PROGRESS.md) · [개발 일지](../docs/devlog/members/) | 팀 현황과 개인 기록 |

설치·연동·공격/부하 시험은 아직 하지 않았다. 모든 탐지·대응은 미구현 상태다.
