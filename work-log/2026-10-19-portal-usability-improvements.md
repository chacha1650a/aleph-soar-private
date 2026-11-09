# 10/19 민원포털 사용성 개선·핸드오프

후속 [MySQL 브라우저 통합 검증](2026-10-19-mysql-browser-integration.md)을 완료했다. 아래 MySQL 미검증 표시는 사용성 개선을 마친 당시의 경계다.

- 작업: H01~H03 사용성 회귀 개선. 담당 김명준 + Codex. 사용자 요청 `개선하자`에 따라 실제 시민 신청→담당자 답변→시민 확인에서 재현한 문제를 수정했다.
- 상태: 로컬 구현·검증 완료. 기존 `codex/haedam-portal-mvp`에 프론트·백엔드를 푸시했다. 관련 Draft PR을 갱신하며 독립 리뷰·main 병합 전이다.
- 범위·인수 조건: [사용성 brief](../docs/haedam/USABILITY-TASK-BRIEF.md).

## 변경한 동작과 파일

1. 프론트 `UnsavedChanges.jsx`와 신청·답변 화면: 링크·뒤로 가기·로그아웃에 이탈 확인창, 새로고침에는 브라우저 경고를 제공한다. 계속 작성·Escape는 내용을 유지하고, 확인창에서 기본 포커스는 계속 작성이다. 닫으면 원래 버튼으로 포커스를 돌린다. 저장 중에는 폐기를 막고 성공한 결과 화면으로 이동한다.
2. 프론트 `formFeedback.jsx`·`NewPetition.jsx`·`PetitionDetail.jsx`, 백엔드 `common.py`·오류 핸들러: 항목별 한국어 오류·항상 보이는 길이 안내·aria 연결·첫 오류 포커스, 실패 시 입력 유지. API의 기존 code/message에 선택적 fields만 추가했다.
3. `Petitions.jsx`·상세 화면: 검색·분야·상태·페이지를 URL로 유지하고 목록 링크·뒤로 가기·새로고침에서 복원한다. 초기화 버튼도 제공한다.
4. `main.css`: 모바일 목록 제목 14px·상태 12px 이상, 입력 16px와 줄바꿈·버튼 크기를 조정했다. 320/390px에서 목록 가로 넘침이 없다.

## 계약과 영향

- 원본 [API](../docs/haedam/PORTAL-API.md), [오류 스키마](../contracts/portal-error.schema.json), [합성 예시](../contracts/portal-examples/validation-error.json), `tests/test_contracts.py`와 양쪽 소비자·복사본·SOURCE.json을 함께 갱신한다. 기존 fields 없는 오류도 유효하다.
- DB·마이그레이션·이벤트 스키마·권한 범위 변경은 없다. 민원 원문을 브라우저 저장소에 보관하지 않는다. 이탈 경고는 자동 임시저장 기능이 아니며 앱 강제 종료에서 복구를 보장하지 않는다.
- C의 FIM 기준본은 변경된 dist를 승인한 정상 배포로 별도 갱신한다. D의 기존 event/incident 매핑과 A~D 보안 케이스 책임은 유지한다.

## 실제 실행한 검증

- 프론트 `npm run build` 통과. `npm run test:e2e` **11 passed**: 기존 업무 흐름 6건과 추가 사용성 5건. 이탈 계속/폐기·기본/복원 포커스·뒤로 가기·새로고침·로그아웃·저장 중 이동, 클라이언트/서버 필드 오류·입력 유지, 검색/상태/분야/페이지 복원, 담당자 답변 후 시민 재조회, 320/390px·axe 자동 검사 포함.
- 백엔드 `.venv/Scripts/python.exe -m pytest -q` **27 passed, 1 skipped**. 오류 envelope/한국어/입력 미노출·잘못된 답변으로 완료되지 않는 동작을 추가 검증했다. skip은 MySQL 행 잠금 전용이며 이번 UX 변경에서는 MySQL 시험을 재실행하지 않았다. 이전 초기 구현의 일회용 MySQL 26 passed와 구분한다.
- capstone pytest **31 passed**, AI 생성물 **14개** 일치, 작업 DAG **6개** 유효.
- 실제 IAB `127.0.0.1:5000`에서 빈 제출의 항목별 오류와 분야 포커스, 계속 작성 후 제목 유지, 명시적 테스트 초안 폐기, 분야·검색 상세 왕복 복원, 390px 목록을 확인했다. DB를 유지한 채 Waitress를 재시작했다.
- 스크린샷은 이 PC의 `C:/Users/dora2/.codex/visualizations/2026/10/19/01a153c2-75dc-7ff1-b080-0f6b9e9ca3c0/ux-improvements/`에 있다. 01 오류 안내, 02 이탈 경고, 03/04 모바일 목록. 합성 데이터만 사용했으며 Git에 포함하지 않는다.

## 전달 버전

- 계약 원본: `2303265ba2ba46f6e6e5622698b1d2f141357f80`. 양쪽 SOURCE.json에 API·오류/이벤트 스키마·예시 5개를 UTF-8 LF SHA-256과 함께 기록했다. 공통 규칙 v3의 원본은 `5e79d461d71e5f70c4daf0288572624a0962f817`을 유지한다.
- 백엔드: `af72dfd28024e5053932ce9daf4a4d9f59379ba7`.
- 프론트: `e874a78e4c900793f385130930a6a88877d43d70`.
- 계약 복사본·해시·규칙 내용 일치, 변경 Markdown의 UTF-8/로컬 링크, git diff --check·Prettier를 확인했다. QA 포트 5005 서버는 종료됐다.

## 다음 담당의 첫 작업

기존 Draft PR [프론트 #1](https://github.com/NoBugs-Aleph/haedam-portal-frontend/pull/1)·[백엔드 #1](https://github.com/NoBugs-Aleph/haedam-portal-backend/pull/1)·[계약 #18](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/18)을 독립 리뷰한다. #18은 #17의 인수인계 브랜치를 base로 유지한다. 다른 PC는 양쪽 README로 설치하고 기존 DB가 있으면 SeedDemo 없이 시작한다.

전체 스크린리더 수동 심사·실제 모바일 OS 강제 종료·MySQL 브라우저 통합·두 PC 관제 연결은 미검증이다. Graylog/Wazuh/n8n/pfSense·NAT·FIM·자원·공방전 실측을 완료로 표시하지 않는다. 로컬 서버는 사용자가 확인할 수 있도록 127.0.0.1:5000에서 유지한다.
