# 해담시청 포털 독립 검증 체크리스트

작성일 2026-10-19. 구현자 외 팀원이 새 작업 폴더에서 실행하고 결과를 직접 기록한다. 모든 체크는 미확인 상태로 시작한다. 작성자 실측과 독립 리뷰 결과를 구분하며, 이 검토는 H02/H03의 로컬 포털 인수 범위다. H05의 두 PC·관제 통합 인수를 대신하지 않는다. 전달할 문구는 [리뷰 요청문](REVIEW-REQUEST.md), 기존 실측은 [MySQL 통합 기록](../../work-log/2026-10-19-mysql-browser-integration.md)을 참고한다.

## 1. 검토 대상 고정

세 저장소의 브랜치는 `codex/haedam-portal-mvp`다. 아래 커밋은 자료 작성 시 확인한 구현 기준이며, capstone에는 이후 이 검토 자료의 문서 커밋이 추가된다.

| 대상 | 구현 기준 커밋 | PR·작성 시 상태 |
| --- | --- | --- |
| 백엔드 | `df8bf88bbe37c6fa92ab83dfa3ae156ad1a6afb1` | [#1](https://github.com/NoBugs-Aleph/haedam-portal-backend/pull/1), Open/Draft, base main |
| 프론트 | `cac2bed39181d7f9e6d4da82d1d4391f8a852ae2` | [#1](https://github.com/NoBugs-Aleph/haedam-portal-frontend/pull/1), Open/Draft, base main |
| 계약·기록 | `2fe8b713328c8aac4907f6e594e7a0ce3f7ca500` | [#18](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/18), Open/Draft, base codex/haedam-handoff-1019 |
| API·스키마 원본 | `2303265ba2ba46f6e6e5622698b1d2f141357f80` | 양쪽 docs/SOURCE.json의 contract_commit |
| 공통 규칙 v3 원본 | `5e79d461d71e5f70c4daf0288572624a0962f817` | 양쪽 docs/PROJECT-RULES.md |

- [ ] 검토자·날짜·세 저장소 실제 HEAD를 하단 결과 양식에 기록했다.
- [ ] PR이 갱신됐다면 변경된 커밋과 검토 범위를 다시 확인했다. 이전 커밋의 결과를 새 HEAD의 승인으로 간주하지 않았다.
- [ ] capstone [#17](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/17)은 main 대상의 선행 인수인계 PR임을 확인했다. 작성 시 #17도 Open/Draft다.

작성 시 capstone #18의 Ubuntu/Windows Workspace checks는 성공이었고 앱 PR 두 개에는 표시된 자동 체크가 없었다. 리뷰 시점의 CI를 다시 확인하고, 체크가 없는 것을 통과로 기록하지 않는다.

## 2. 새 폴더에 준비

필요한 환경: Windows, Git, Python 3.12+, Node 22.12+와 npm, Microsoft Edge, 실행 중인 Docker의 Linux 컨테이너 엔진, 비공개 저장소 읽기 권한. 작성자 실측 버전은 Python 3.12.10 / Node 24.15.0 / npm 11.12.1 / Docker 29.6.2다.

- [ ] 새 검증 폴더·셸을 사용한다. 기존 작업의 .env·DB·비밀값은 복사하지 않는다. 셸에 서비스용 DATABASE_URL, HAEDAM_TEST_DATABASE_URL, HAEDAM_E2E_DATABASE_URL, HAEDAM_E2E_MYSQL 등 검증 동작을 바꿀 설정이 없는지 확인했다.
- [ ] 자동 시험용 5005가 비어 있다. 점유 프로세스가 있으면 소유자를 확인하고 조율하며 임의 종료하지 않는다. Docker 준비 실패는 미실행으로 기록한다.
- [ ] 각 저장소 AGENTS.md → 공통 규칙 → README와 [포털 API](PORTAL-API.md)를 읽었다.

비어 있는 상위 폴더에서 세 저장소를 형제 폴더로 받는다.

```powershell
git clone --branch codex/haedam-portal-mvp https://github.com/NoBugs-Aleph/aleph-soar-capstone.git
git clone --branch codex/haedam-portal-mvp https://github.com/NoBugs-Aleph/haedam-portal-backend.git
git clone --branch codex/haedam-portal-mvp https://github.com/NoBugs-Aleph/haedam-portal-frontend.git
Set-Location .\haedam-portal-backend
git rev-parse HEAD
python tools/bootstrap.py
Set-Location ..\haedam-portal-frontend
git rev-parse HEAD
npm ci
npm run build
```

명령이 실패하면 해당 단계에서 멈추고 원인을 기록한다. 다른 저장소가 이미 있는 폴더에 위 clone 명령을 반복하지 않는다. `.venv`·node_modules는 각 PC에서 준비한다.

## 3. 자동 검증 — 순서대로 실행

위 준비가 끝난 프론트 폴더에서 시작한다. T2와 T3는 각각 일회용 MySQL을 만들므로 동시에 실행하지 않는다.

```powershell
Set-Location ..\haedam-portal-backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools/check_mysql.py
.\.venv\Scripts\python.exe tools/check_mysql_e2e.py
Set-Location ..\haedam-portal-frontend
npm run test:e2e
```

| ID | 명령·범위 | 작성자 실측 기준 | 독립 결과 |
| --- | --- | --- | --- |
| T1 | backend pytest, SQLite API | 27 passed / MySQL 전용 1 skipped | 미실행 |
| T2 | check_mysql.py, MySQL API·동시성 | 28 passed, upgrade/check/downgrade/upgrade 성공 | 미실행 |
| T3 | check_mysql_e2e.py, MySQL 브라우저 | 12 passed, React 빌드·DB 감사·db check 성공 | 미실행 |
| T4 | frontend test:e2e, SQLite 브라우저 | 11 passed | 미실행 |

- [ ] T1~T4 각각의 실제 pass/fail/skip·실행 환경을 기록했다. 서로 다른 DB·시험의 수치를 합산하지 않았다.
- [ ] T3에서 MySQL 8.4.11, 실제 서버 PID 교체 두 번, 민원 completed/version 4/처리 이력 4건/utf8mb4 왕복/schema_drift false를 요약 파일과 콘솔로 확인했다. 각 재시작의 이전/이후 PID가 달라야 하며 작성자 기록의 PID 숫자와 일치시킬 필요는 없다.
- [ ] T3는 신청 직후와 답변 완료 후 앱 서버를 교체하며, 같은 시민·담당자 세션의 데이터·답변·이력과 타인 조회 거절·CSRF 누락 거절을 확인했다.
- [ ] T2/T3 종료 후 이번 실행의 QA 서버·컨테이너가 정리됐다. 기존 5000 서비스·DB는 유지됐다.

T3 결과는 backend `.local/mysql-e2e-report.json`과 frontend `test-results/mysql-citizen-after-restart.png`다. **T4 실행 전에** 필요한 T3 합성 화면을 검토자 로컬의 별도 폴더에 보관한다. 다음 Playwright 실행은 test-results를 바꾼다. 비밀번호·DB URL·쿠키·CSRF·원본 로그·브라우저 저장 상태 파일을 결과에 첨부하지 않는다.

5005는 QA 도구가 관리하며 기존 사용자 화면은 5000일 수 있다. 두 주소에서 보이는 DB를 혼동하지 않는다. MySQL 전용 환경변수나 재시작 제어 경로를 직접 설정하지 말고 T3 실행기를 사용한다.

## 4. 직접 화면 확인 — 별도의 로컬 SQLite 데모

자동 시험 후 프론트 폴더에서 다음을 실행한다. 준비한 새 clone의 기본 DB는 사용자 테이블이 비어 있어 SeedDemo를 한 번 사용할 수 있다. 기존 DB에 계정이 있으면 SeedDemo를 빼고 해당 검증 계정을 준비한다.

```powershell
Set-Location ..\haedam-portal-backend
.\tools\start.ps1 -SeedDemo -Port 5010
```

주소는 `http://127.0.0.1:5010`이다. 5010도 점유돼 있으면 비어 있는 로컬 포트를 합의해 사용한다. 콘솔에 표시되는 이번 실행의 임시 비밀번호로 citizen_demo / staff_demo / admin_demo를 사용한다. 임시 비밀번호는 검증 자료에 옮기지 않는다. 검증용 브라우저 프로필에서 시민 일반 창과 담당자 InPrivate 창을 사용해 로그인 세션을 분리한다. 각 항목의 역할에 맞게 로그인하고 확인한다.

| ID | 직접 확인할 동작 | 기대 결과 | 완료 |
| --- | --- | --- | --- |
| M1 | 시민 로그인, 가상 제목·본문·분야로 신청, 상세 새로고침 | 접수번호·본인 내용·접수 상태가 유지됨 | [ ] |
| M2 | 담당자 별도 세션에서 내가 담당하기→처리 시작→10자 이상 답변·완료, 시민 새로고침 | 양쪽에서 처리 완료·같은 답변·처리 이력 확인 | [ ] |
| M3 | 별도 시민 계정으로 가입·로그인 후 M1의 상세 주소·목록 확인 | 타인 민원이 목록에 없고 상세 원문도 보이지 않음 | [ ] |
| M4 | 빈 제출·짧은 제목/본문/답변으로 제출 | 한국어 항목 오류·길이 안내·첫 오류 포커스, 입력 유지 | [ ] |
| M5 | 신청 및 답변 초안 입력 후 메뉴 이동·뒤로 가기·로그아웃·새로고침 시도 | 이탈 경고, 계속 작성/Escape 선택 시 유지, 명시적 폐기 때만 이동 | [ ] |
| M6 | 검색·분야·상태를 선택하고 상세 왕복·뒤로 가기·새로고침 | URL과 선택 조건 유지. 페이지 복원은 T4로도 확인 | [ ] |
| M7 | 폭 320/390px, Tab과 Enter로 주요 화면·이탈 확인창 조작 | 가로 넘침 없이 읽힘, 레이블·오류 식별, 경고 기본 포커스는 계속 작성, 메뉴 이동 경고를 취소하면 원래 메뉴에 포커스 복원 | [ ] |
| M8 | admin_demo로 테스트 계정 생성/권한/잠금/재설정, 민원 원문 접근 확인 | 계정 업무 가능, 관리자라도 민원 원문은 접근 거절 | [ ] |

M5의 담당자 답변 초안 검사는 아직 완료하지 않은 별도 합성 민원으로 진행한다. 이미 완료한 M2 민원을 다시 열거나 실제 데이터를 지우지 않는다. 자동 임시저장은 없으며 경고 기능과 구분한다.

- [ ] R1: 위에서 직접 실행한 5010 서버를 Ctrl+C로 종료하고 아래 명령으로 재실행했다. M1/M2 결과를 새로고침해 유지되는지 확인했다. 이는 수동 SQLite 확인이며 MySQL 재시작 검증은 T3다.

```powershell
.\tools\start.ps1 -Port 5010
```

- [ ] R2: 시민으로 민원 안내 홈을 열어둔 채 본인 5010 서버를 중지하고, 화면 새로고침 대신 사이트 내 나의 민원 메뉴로 이동했다. 연결 실패·다시 시도가 표시되고, 같은 명령으로 서버 재실행 후 재시도에 성공했다.
- [ ] R3: 확인 종료 후 본인이 실행한 5010 서버를 Ctrl+C로 종료했다. QA DB 초기화·삭제를 서비스 DB에 적용하지 않았다.

## 5. 코드·계약 리뷰

아래 경로는 별도 명시가 없으면 해당 앱 저장소 기준이다. 실제 결함은 파일·줄·재현 조건·영향과 함께 기록한다.

- [ ] C1 — backend auth/·common.py·앱 before_request: 서버 역할·소유권 검사, HttpOnly 세션·CSRF·로그아웃/잠금/비밀번호 변경 시 세션 회수. 프론트의 버튼 숨김을 권한 검사로 쓰지 않는다.
- [ ] C2 — backend petitions/·models.py·tests/test_portal.py: 본인/미배정/담당자 범위, 상태 전이·version 충돌·트랜잭션, 잘못된 답변으로 완료되지 않는 동작. 테스트가 실제 실패·권한 경로를 검증하는지 확인한다.
- [ ] C3 — frontend src/api/client.js·formFeedback.jsx·UnsavedChanges.jsx·업무 페이지: 계약 오류 처리·실패 시 입력 유지·저장 성공 확인·이탈 경고·저장 중 동작. 민원 원문을 HTML로 실행하거나 브라우저 저장소에 보관하지 않는다.
- [ ] C4 — 양쪽 docs/SOURCE.json·contracts/: 계약 커밋과 UTF-8 LF 해시가 원본에 맞고, 선택적 error.fields와 기존 code/message가 호환된다. 규칙 v3·API·오류/이벤트 스키마·예시를 같은 기준으로 읽는다.
- [ ] C5 — backend integration/·앱 라우트: 민원 원문/토큰/비밀번호의 이벤트 제외, 연결 IP 사용·전달 헤더 미신뢰, 미지정 경로 실제 404. 대응 API의 키·관리망·대상·중복 제한과 프론트 미노출을 확인한다.
- [ ] C6 — backend tools/check_mysql_e2e.py·e2e_server.py, frontend Playwright 설정·mysql-persistence.spec.js: 전용 DB/프로세스 소유 확인·실제 PID 교체·독립 MySQL 감사·정리, 일반 SQLite와 MySQL 모드 구분. DB 자격 증명을 브라우저에 전달하지 않고 MySQL 트레이스를 끈다.

## 6. 결과 판정과 병합 순서

필수 자동 시험 실패, 타인 데이터 노출, 저장/재시작 후 데이터 유실, 인증·권한·CSRF 우회, 서비스 DB/타 프로세스 변경, 계약 불일치는 수정 후 재검증한다. 환경 문제로 못 한 항목은 미실행으로 남긴다. 가벼운 문구·디자인 제안은 기능 결함과 나눠 적는다.

- [ ] 작성자 검증을 독립 검증 결과로 대신 체크하지 않았다. 필수 미실행·미해결 문제가 있으면 승인 보류 이유를 적었다.
- [ ] 검토 범위와 결과를 남겼고, 작성자가 검토 준비 완료 시 Draft→Ready for review 및 리뷰어 지정을 별도로 진행한다.
- [ ] capstone은 #17→#18 순서를 확인했다. #17 병합 뒤 #18의 base를 main으로 조정할 필요와 실제 diff·CI를 재확인한 후 #18을 검토·병합한다.
- [ ] 앱 PR 두 개는 같은 프론트/백/계약 조합으로 승인한 뒤 팀 절차대로 병합하고 최종 병합 커밋을 함께 기록한다. 한쪽 결과만으로 전체 통합을 승인하지 않는다.

상시 MySQL/서비스 VM 배포, DB 서버 자체 재시작·백업 복원, 두 PC 관제·NAT·FIM·자원·공방전은 별도다. 이 체크리스트 통과만으로 해당 항목이나 H05 전체를 완료 처리하지 않는다.

2026-10-20 추가: H05의 처리량·로그 지연·누락·자원·복구 시간은 [관제 가용성 검증 계획](MONITORING-CAPACITY-PLAN.md)에 따라 별도로 측정한다. 현재는 계획 작성 상태이며 실측 미실행이다. Kafka 추가 여부는 해당 측정 후 판단한다.

## 7. 검토자 결과 양식

아래를 복사해 채운다. 값은 예시 통과로 미리 채우지 않았다.

```text
검토자 / 날짜:
OS / Python / Node / npm / Docker / Edge:
backend HEAD / frontend HEAD / capstone HEAD / 계약 커밋:
읽은 체크리스트의 capstone 커밋:
T1 결과(pass/fail/skip):
T2 결과(pass/fail/skip):
T3 결과 + MySQL 버전 + 재시작 2회 + DB 감사/정리:
T4 결과(pass/fail/skip):
M1~M8 / R1~R3 / C1~C6: 항목별 통과·실패·미실행
문제: 중요도 / 파일·줄 / 재현 순서 / 기대 결과 / 실제 결과 / 영향
증거: 비밀값을 제거한 요약 또는 합성 화면 / 검토 커밋
미실행 항목과 이유:
판정: 승인 / 수정 요청 / 환경 준비 후 재검토
승인 범위·남은 배포/통합 조건:
최종 병합 커밋(병합 후에만 작성):
```
