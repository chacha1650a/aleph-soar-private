# 해담시청 포털 리뷰 요청 자료

2026-10-19 작성. 구현자 김명준 + Codex가 다른 팀원에게 전달할 요청문과 검토 안내다. 실제 독립 리뷰어는 아직 배정하지 않았다. 문서 작성·게시와 정식 리뷰 요청·승인·병합은 별개다. 검토자는 [체크리스트](REVIEW-CHECKLIST.md)를 따라 결과를 남긴다.

## 복사해서 전달할 요청문

아래 인용문을 팀 채널이나 리뷰 요청에 사용할 수 있다. 받는 팀원·기한은 조율 후 추가한다.

> 해담시청 민원포털의 프론트·백엔드 독립 검증과 코드 리뷰를 부탁드립니다.
>
> 시민 신청 → 담당자 배정·답변 → 시민 결과 확인, 계정·권한·세션, 입력 오류·작성 이탈 경고·모바일 화면을 구현했습니다. 로컬 MySQL에서도 앱 서버 재시작 후 데이터와 로그인 세션 유지를 확인했습니다.
>
> 작성자 실측은 MySQL 브라우저 12건, MySQL API/동시성 28건, SQLite 브라우저 11건 통과입니다. 새 작업 폴더에서 README와 체크리스트대로 직접 재현해 주시면 됩니다. 각 결과는 DB·시험별로 구분해 주세요.
>
> [검증 체크리스트](https://github.com/NoBugs-Aleph/aleph-soar-capstone/blob/codex/haedam-portal-mvp/docs/haedam/REVIEW-CHECKLIST.md)
>
> [백엔드 PR #1](https://github.com/NoBugs-Aleph/haedam-portal-backend/pull/1) · [프론트 PR #1](https://github.com/NoBugs-Aleph/haedam-portal-frontend/pull/1) · [공통 계약·기록 PR #18](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/18)
>
> 구현 기준은 backend df8bf88 / frontend cac2bed / 계약 2303265, 세 저장소 브랜치는 codex/haedam-portal-mvp입니다. capstone #18은 선행 #17 위의 PR이라 병합 순서를 확인해야 합니다. 현재 PR은 Draft이며 정식 리뷰 요청은 작성자가 준비 상태와 리뷰어를 조율한 뒤 진행하겠습니다.
>
> 특히 타인 민원 접근 거절, 서버의 역할·소유권·CSRF 검사, 상태/버전 충돌, 저장 실패 시 입력 유지, MySQL 연결 상태의 앱 서버 재시작 검증에서 실제 프로세스 교체·DB 감사·정리 범위를 봐 주세요.
>
> 체크리스트 하단 양식에 실제 실행 환경·커밋·결과·미실행 항목을 적어 주세요. 문제는 파일/줄·재현 순서·기대/실제 결과·영향을 함께 부탁드립니다. 비밀번호·쿠키·토큰·DB URL·원본 로그는 첨부하지 말고 합성 화면이나 비밀값을 제거한 요약을 사용해 주세요.
>
> 이번 요청은 로컬 포털 기능의 독립 검증입니다. 서비스 VM·상시 MySQL 배포, DB 자체 재시작/백업 복원, 두 PC·관제·NAT·FIM·공방전은 후속 검증으로 남아 있습니다. 완료된 범위에 대해 승인 또는 수정 요청 의견을 부탁드립니다.

## 리뷰어가 볼 순서

| 순서 | 검토 대상 | 확인할 결과 |
| --- | --- | --- |
| 1 | [체크리스트 1~3절](REVIEW-CHECKLIST.md#1-검토-대상-고정), 양쪽 README·docs/VERIFICATION.md | 정확한 커밋과 환경에서 T1~T4 직접 재현 |
| 2 | [체크리스트 4절](REVIEW-CHECKLIST.md#4-직접-화면-확인--별도의-로컬-sqlite-데모) | M1~M8·R1~R3 직접 확인, MySQL 자동 시험과 구분 |
| 3 | [포털 API](PORTAL-API.md), 양쪽 계약 출처, 체크리스트 5절 | 인증·권한·상태·오류·이벤트·테스트 실행기 검토 |
| 4 | [MySQL 실측 기록](../../work-log/2026-10-19-mysql-browser-integration.md), 체크리스트 6~7절 | 작성자 근거와 독립 결과 비교, 문제·승인 범위 기록 |

필수 실행의 기대 결과는 체크리스트 표에 고정했다. 명령이 실패하거나 커밋이 바뀌면 그대로 기록하고 원인을 조율한다. 기존 개발 폴더·DB를 초기화하거나 결과 수치를 맞추려고 테스트를 끄지 않는다.

## 코드 리뷰의 주요 진입점

- 백엔드: `src/haedam_portal/auth/`, `petitions/`, `admin/`, `common.py`, `models.py`, 앱 생성·라우트, `integration/`, `tests/test_portal.py`.
- MySQL 검증: backend `tools/check_mysql_e2e.py`·`tools/e2e_server.py`·마이그레이션, frontend `playwright.config.js`·`tests/mysql-persistence.spec.js`. 재시작 제어는 소유 임시 파일이며 업무용 HTTP API가 아니다.
- 프론트: `src/api/client.js`, `src/components/UnsavedChanges.jsx`·`formFeedback.jsx`, `src/pages/NewPetition.jsx`·`PetitionDetail.jsx`·`Petitions.jsx`, 모바일 CSS와 회귀 테스트.
- 공통 계약: capstone `docs/haedam/PORTAL-API.md`, `contracts/portal-error.schema.json`·`portal-event.schema.json`·예시와 양쪽 `docs/SOURCE.json`.

자동 접근성 결과는 전체 스크린리더 수동 심사나 접근성 인증을 뜻하지 않는다. 관제 이벤트의 로컬 생성과 실제 외부 수신·탐지·대응·원복도 구분한다.

## 작성자가 리뷰 요청 전에 채울 내용

- [ ] 리뷰어 이름과 회신 시점을 팀원과 조율했다.
- [ ] 세 PR의 최신 HEAD·상태·CI와 검토할 변경 범위를 재확인했다.
- [ ] 앱 PR의 자동 체크가 없는 상태와 작성자 실측 근거를 검토자에게 알렸다.
- [ ] 정식 리뷰 요청이 준비되면 작성자가 Draft→Ready for review 전환 및 리뷰어 지정을 진행한다.
- [ ] capstone #17→#18의 순서와 #18의 base/diff 재확인 조건을 공유했다.
- [ ] 새 커밋이 올라오면 변경 내용을 알리고 필요한 항목을 다시 검토받는다.

이 자료의 체크 항목은 준비·검증 지시이며, 팀원의 실제 리뷰 결과나 승인을 미리 채운 기록이 아니다.
