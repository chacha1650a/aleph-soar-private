# S7-before-01 (2026-10-22, 보강 전, 재시험)

실행: A. FIM(C)·웹(A)·D 교차 확인. **S7은 C 케이스** — C 기록: `docs/capstone/evidence/S07/2026-10-22-before-run1-result.md`(PR #36 병합).

- 입력: 변조 파일 `dist/assets/zz_s7_before_1022b.txt`(19 bytes) 생성 15:37:43 → B Kali 203.0.113.10 접근 15:39:12, HTTP 200
- 결과: S7 상관 이벤트 0 · n8n 복구 0 · active response 0 · 티켓 0. 원시 FIM 554는 생성·도착. 공격 성공(변조 파일 웹 200, 복구 안 됨).

## 들어 있는 것
- `portal-events.jsonl` — 포털 원본 `web.file_access` `e98f04b6-…`(15:39:12.183, src 203.0.113.10, 200) 1건

## D·C 대조
- FIM 554: C 15:37:44.134 → D 15:37:45.109, `wazuh_id 1792651064.1185953`·경로·sha256 앞 16자 `7d260d3421b02f69` 일치(D).
- 웹: `e98f04b6-aa72-43df-b7bb-8bb10f5f39be` D 15:39:12.468 1건 일치(D). 재조회 조건 `file_key:"assets/zz_s7_before_1022b.txt"`.
- 정리: 삭제 553 16:05:32.242(C), 동결 해제 16:14(C).

## 증적 방식
캡처 화면은 증적으로 쓰지 않고 원본 로그와 D 대조 결과로 남긴다(C S7 증적과 같은 방식). 발표 화면이 필요하면 같은 검색 조건으로 Graylog를 다시 조회한다.
