# S1·S4 보강 변경 목록과 설정 보관 위치

> 담당: whiteclover0542 (A) · 작성 2026-11-02 · 갱신 2026-11-03(S4 13~15줄) · 근거: 저장소 병합 기록, A 작업일지, 증적 README
> 용도: [정량평가 리포트](../../team_docs/정량평가_리포트.md) 4-6 "보강 전후 비교"의 변경 목록과 A 작업순서 7단계 "보강 적용"·"설정 내보내기". **저장소 병합 시각과 랩 반영 시각은 다르다.** 랩 반영은 일지·증적에 적힌 것만 시각을 적었다.

## 1. 기준 상태 (보강 전, 10/22)

| 구성 | 상태 | 근거 |
| --- | --- | --- |
| 포털 VM | backend `47be008` · frontend `a98c0e5` · GELF **UDP** · 스냅샷 `S1_before`(10/22 14:37) | S1·S4 보강 전 증적 README |
| Graylog(D) | 수집(입력·`haedam-portal` 스트림)만, S1·S4 이벤트 정의 없음 | PR #38(보강 전 셋팅) |
| n8n(D) | S1·S4 워크플로 없음 | — |
| 티켓 저장소(C) | 없음(114 미존재) | 리포트 S1 보강 전 줄 |

결과: S1-before-01·S4-before-01 모두 도착 15/15·이벤트 0·대응 0(공격 성공·미탐).

## 2. 변경 목록 (시간순)

한 줄 = 바꾼 항목 하나. "회차"는 그 변경이 처음 들어간 상태로 돌린 시험이다.

| # | 랩 반영 | 구성 | 변경 | 근거 | 영향 | 회차 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 10/26 | 티켓 저장소(C) | 저장소·API·대시보드 화면 신설 | #50·#55 | 114 티켓 생성 가능 | S1-after-01 |
| 2 | 10/27 | n8n(D) | S1 `haedam-30`·S4 `haedam-31`·공통 하위(`haedam-10` 기록·`haedam-12` IP 차단·`haedam-13` 잠금) 추가, 전부 dry_run | #57 | 대응 경로 생김(실제 조치 없음) | — |
| 3 | 10/27 17:18 | 포털 backend | `47be008` → `9507fce`: username 잠금(backend #3)·오탐 unlock(backend #4) | 작업일지 10/27 | S4 잠금을 이벤트 username으로 요청 가능 | S1-after-01 |
| 4 | 10/27~28 | n8n(D) | `haedam-12` 본문 전송 수정(10/27 400 3회 원인), 티켓 저장소 본문·via, 기록·조치 플래그 분리(store_real / dry_run) | #80·#71·#73 | 112 차단 실제 호출 성공 | S1-after-01 |
| 5 | 10/28 10:51 이후 | Graylog(D) | **S1 이벤트 정의 반입**: `count()>8`·30분·username+src_ip·1분 실행·grace 30분 | #65 | S1 탐지 시작 | S1-after-01 |
| 6 | 10/28 | Graylog(D) | S1 알림 → n8n `haedam-30`, 본문에 `detected_at` | #81·#86 | 탐지 → 대응 연결, MTTD 종점 기록 | S1-after-01 |
| 7 | 10/28 | n8n(D) | S1만 실제 조치 스위치(알림 본문으로 dry_run 해제) | #82 | S1 자동 차단 실제 실행 | S1-after-01 |
| 8 | 10/28 | 티켓 저장소(C) | 활성 조치만 중복 비교, 해제 뒤 재차단 = 새 티켓(#62), C 재빌드 | #67(`87997dd`) | 재공격 티켓 분리(T-0002 → T-0003) | S1-after-01 |
| 9 | 10/28 16:15 | 포털 frontend | `a98c0e5` → `2836a42`: 관리자 화면 오탐 해제(unlock) 버튼 | frontend #3 | S4 오탐 해제를 비밀번호 유지로 | S4-after-01 (버튼 표시만, 해제는 재설정 경로) |
| 10 | 10/30 | n8n(D) | 중복 판정에서 dry_run 기록은 30분 안의 것만 처리됨으로 셈 | #114 | 오래된 dry_run 기록이 실제 조치를 막지 않음 | (다음 S1) |
| 11 | 10/30 | 포털 backend·pfSense(B) | `9507fce` → `f3faa1c`: GELF **TCP** 옵션(backend #8), `GELF_TRANSPORT=tcp` 전환, pfSense A→D TCP 12201 허용 | 작업순서 5단계, 리포트 6-1 | UDP 유실 대책(11/02 대조 유실 0) | (다음 S1) |
| 12 | 11/02 10:38 | 포털 `.env` | `DASHBOARD_URL` 입력(대시보드 링크) | 작업일지 11/02 | 탐지·대응 무관 | — |
| 13 | 11/03 (10:37 병합, 랩 반영 시각 미기재) | n8n(D) | S1·S4·S8/S10·S12 티켓 실기록(`store_real:true`)·웹훅 헤더 인증 | #125 | 전 케이스 실제 티켓 저장 | S4-after-01 |
| 14 | 11/03 (15:13 병합, 15:40 회차 전 반영) | n8n(D) | S4 실제 잠금 스위치: haedam-31 → haedam-13 `dry_run:false` 본문(대상 `zz_` 시험 계정만) | #127(`7e82557`) | S4 자동 잠금·세션 회수 실제 실행 | S4-after-01 |
| 15 | 11/03 15:37 | Graylog(D) | **S4 이벤트 정의 반입·활성**: `card(rule)>1 & count()>5`·10분·username+src_ip·1분 실행·grace 10분 | #65 | S4 탐지 시작 | S4-after-01 |

- **S1-after-01·02(10/28·10/29)는 1~8까지 반영, UDP 상태**다. 다음 S1 회차(S1-after-03·S1-edge-01)는 10·11·13이 더해져 수집 조건이 다르다. 결과표에서 두 묶음을 나눠 읽는다.
- **S4-after-01(11/03)은 1~15 반영, TCP 상태**다(S4 첫 보강 후 회차). 14·15의 랩 게시본과 저장소 파일 대조는 D 내보내기 전(3절).
- 해제는 아직 승인 해제 워크플로(`haedam-50`, `live_release_enabled=false`)가 아니라 수동 연결이다(리포트 S1 한계).

## 3. 설정 보관 위치 (설정 내보내기)

| 설정 | 저장소 파일 | 랩에 든 것과 같은지 |
| --- | --- | --- |
| S1 이벤트 정의 | [`lab/s1s4/graylog/s1-login-bruteforce.json`](../../lab/s1s4/graylog/s1-login-bruteforce.json) | 미확인. D 반입 때 스트림 ID 교체(README 반입 1단계) — Graylog에서 내보낸 JSON과 대조 필요 |
| S4 이벤트 정의 | [`lab/s1s4/graylog/s4-fail-then-success.json`](../../lab/s1s4/graylog/s4-fail-then-success.json) | 11/03 15:37 반입(D). 내보낸 JSON과 대조는 미확인 |
| S1 알림(→ n8n) | [`infra/graylog/notifications/s1-n8n-haedam-s1.json`](../../infra/graylog/notifications/s1-n8n-haedam-s1.json) | 미확인 |
| S1 메인·S4 메인 | [`infra/n8n/workflows/haedam-30-s1-main.json`](../../infra/n8n/workflows/haedam-30-s1-main.json) · [`haedam-31-s4-main.json`](../../infra/n8n/workflows/haedam-31-s4-main.json) | 저장소 해시는 [`s1-candidate-20261030/versions.json`](evidence/s1-candidate-20261030/versions.json)에 고정(`runtime_verified: false`) |
| 112 IP 차단·111 잠금 | [`haedam-12-portal-ip-block.json`](../../infra/n8n/workflows/haedam-12-portal-ip-block.json) · [`haedam-13-portal-account-lock.json`](../../infra/n8n/workflows/haedam-13-portal-account-lock.json) | 위와 같음 |
| 114 결과 기록·티켓 | [`haedam-10-result-log.json`](../../infra/n8n/workflows/haedam-10-result-log.json) | 위와 같음 |
| 해제 흐름 | [`haedam-50-release.json`](../../infra/n8n/workflows/haedam-50-release.json) | 위와 같음. 실제 시험 해제는 이 흐름이 아니라 D 임시 워크플로 → haedam-12 |
| 오프라인 점검 | [`lab/s1s4/graylog/check.py`](../../lab/s1s4/graylog/check.py) · `python tools/check_s1_candidate.py` | 저장소 소스 일치만 확인(실행 환경 아님) |

**남은 일(D):** 다음 S1 회차 직전에 Graylog S1 정의·알림과 n8n `haedam-30`·`10`·`12`를 내보내 위 파일과 대조(또는 내보낸 파일의 SHA-256을 기록표 0절에 적기). 그 전까지 "설정 내보내기"는 저장소 원본 보관까지만 된 상태다.
