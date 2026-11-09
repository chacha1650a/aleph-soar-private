# S1-before-01 (2026-10-22, 보강 전)

실행: 다른 세션(출발지 203.0.113.10, 계정 zz_a1). A가 포털 원본 event_id로 대조.

- 입력: 로그인 실패 9회, 15:35:35~16:02:19 KST
- 조건 충족 시각: 16:02:19.205 (마지막 실패 `1e7ecb9c-…`)
- 결과: Graylog 상관 이벤트 0 · n8n 실행 0 · IP 차단 0 · 티켓 0 · 신호 도착 9/9(D). 공격 성공(미탐).
- 보강 전 고정: A PC 포털 VM(`Ubuntu 64-bit (2)`) 스냅샷 `S1_before`(2026-10-22 14:37 KST, S1·S4 실행 전 마지막 스냅샷, S4 전 추가 스냅샷 없음). 스냅샷 시점 코드: backend `47be008`(브랜치 `claude/portal-ip-block-file-key`, VM 마지막 checkout 10/21 15:49, 작업 트리 변경 없음)·frontend `a98c0e5`(10/23 VM reflog 확인). 복원 시험은 안 함.

## 들어 있는 것
- `portal-events.jsonl` — 포털 원본 `auth.login_failed` 9건 발췌

## D 대조 (10/22~23, D 회신)
- Graylog: 포털 원본 event_id 9개 모두 1건씩 도착·일치(S1·S4 합계 15/15). D Graylog 시각은 원본보다 약 0.3초 늦음(GELF 지연 + D PC 시계 오차 미측정).
- D 보관 CSV: 이 폴더 `portal-events.jsonl`의 event_id 9개와 ID 1건씩 일치.
- 보강 전 상태: Graylog 이벤트 정의는 기본 시스템 항목뿐, 15시 이후 이벤트 0, D n8n 실행 0(활성 `haedam-00`·`haedam-10`은 S1·S4 로직 없음), 상태 코드 200·401뿐, 429·잠금·IP 차단 0. 티켓 0은 114 티켓 저장소 미구축 상태라 생길 수 없는 값(C 확인).
- 재조회 조건: `rule:login-bruteforce username:zz_a1`, 구간은 위 입력 시각.

## 증적 방식
캡처 화면은 증적으로 쓰지 않고 원본 로그와 D 대조 결과로 남긴다(C S7 증적과 같은 방식). 발표 화면이 필요하면 같은 검색 조건으로 Graylog를 다시 조회한다.
