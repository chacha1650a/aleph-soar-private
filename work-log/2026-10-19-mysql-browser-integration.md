# 10/19 MySQL 브라우저 통합·재시작 검증

독립 재현을 시작할 팀원은 [검증 체크리스트](../docs/haedam/REVIEW-CHECKLIST.md)와 [리뷰 요청 자료](../docs/haedam/REVIEW-REQUEST.md)를 사용한다.

- 작업: H02/H03 MySQL 정상 업무·영속성 검증. 사용자 `1번 진행하자`, 담당 김명준 + Codex. [작업 brief](../docs/haedam/MYSQL-E2E-TASK-BRIEF.md).
- 상태: 구현·로컬 실측 완료. 기존 `codex/haedam-portal-mvp`에 프론트·백엔드를 푸시했다. 관련 Draft PR을 갱신하며 독립 리뷰·main 병합·팀 서비스 배포 전이다.
- 범위: backend `tools/check_mysql_e2e.py`·`tools/e2e_server.py`, frontend `playwright.config.js`·`tests/mysql-persistence.spec.js`, 양쪽 README/VERIFICATION. 업무 API·DB 스키마·계약은 변경하지 않았다. 계약 원본은 `2303265ba2ba46f6e6e5622698b1d2f141357f80`을 유지한다.

## 실제 실행과 결과

환경: Windows, Python 3.12.10, Node 24.15.0, Edge/Playwright 1.64.1, Docker 29.6.2. 실제 조회한 MySQL은 **8.4.11**. 이미지 `mysql@sha256:24989179f58856db763f418010c1169fecc944e3ec1ea7e921572d83eb070f70`를 고정했다. 합성 정보만 사용했다.

| 실행·관찰 | 결과 |
| --- | --- |
| backend `python tools/check_mysql_e2e.py` | React/Vite 빌드 + 실제 MySQL/Waitress/Edge 브라우저 **12 passed (35.6s)** |
| 시민 신청→앱 서버 재시작→같은 세션 재조회 | 실제 PID 40384→43492, 민원·본문·상태·버전·이력 동일 |
| 담당자 배정/답변→앱 서버 재시작→시민·담당자 재조회 | 실제 PID 43492→35744, 답변·완료 상태·이력 동일 |
| 권한·문자·CSRF | 타인 목록/상세 거절과 원문 미노출, 한글/🌱 왕복, CSRF 누락 403, 브라우저 저장소 비어 있음 |
| 별도 MySQL 읽기 감사 | 합성 민원 id 1, completed, version 4, 접수/배정/처리 중/완료 4건, utf8mb4 확인 |
| MySQL 마이그레이션·ORM 비교 | revision `04440ce16125`, `db check` 차이 없음 |
| backend `python tools/check_mysql.py` | **28 passed (72.36s)**, upgrade/check/downgrade/upgrade와 동시 중복 계정 대응 포함 |
| frontend `npm run test:e2e` | 기본 SQLite 경로 **11 passed (30.3s)**, MySQL 전용 테스트 제외 확인 |
| 실행기 검증 | 비허용 DB는 연결 전 거절·입력한 자격 증명 미노출. Prettier·Python 구문 검사·diff check 통과 |

DB 직접 감사는 화면/HTTP 성공과 별도로 실행했다. 서버는 실제 프로세스를 종료·재생성했다. 브라우저 페이지와 쿠키는 메모리에 유지하고 저장 상태 파일에 쓰지 않았다. Windows의 venv 실행기와 실제 Python PID가 다른 점을 처리했다. 콘솔 UTF-8 출력과 실행 종료 시 자체 프로세스 트리·임시 런타임 정리를 검증했다.

## 재현과 증적

양쪽 레포를 형제 폴더로 준비하고 프론트 `npm ci`, 백엔드 `.venv` 준비, Docker/Edge 실행 환경을 갖춘 뒤 백엔드에서:

```powershell
.\.venv\Scripts\python.exe tools/check_mysql_e2e.py
```

실행기는 고유 이름·랜덤 루프백 DB 포트·생성 비밀번호·768MB/1 CPU의 일회용 MySQL을 만들고, 비어 있는 5005에서 QA Waitress를 실행한다. 기존 5000·SQLite·다른 컨테이너를 변경하지 않는다. 재시작은 소유 임시 파일로만 제어하며 업무용 HTTP 재시작 API를 추가하지 않았다. DB 자격 증명은 브라우저에 전달하지 않고 MySQL Playwright 트레이스를 끈다. 성공·실패 모두 자체 서버·컨테이너·임시 런타임을 정리한다.

Git 제외 결과는 backend `.local/mysql-e2e-report.json`, frontend `test-results/mysql-citizen-after-restart.png`. 이 PC의 보존본은 `C:/Users/dora2/.codex/visualizations/2026/10/19/01a153c2-75dc-7ff1-b080-0f6b9e9ca3c0/mysql-integration/`의 같은 이름 두 파일이다. 요약에는 DB 비밀번호·URL·세션·토큰·민원 원문이 없다. 화면에는 합성 민원만 있다. 다른 PC로 자동 이전되지 않으므로 명령으로 재현한다.

## 전달 버전

- backend `df8bf88bbe37c6fa92ab83dfa3ae156ad1a6afb1`.
- frontend `cac2bed39181d7f9e6d4da82d1d4391f8a852ae2`.
- 계약 `2303265ba2ba46f6e6e5622698b1d2f141357f80`, 공통 규칙 v3 원본 `5e79d461d71e5f70c4daf0288572624a0962f817`.
- 두 앱 저장소 push 성공, 변경 UTF-8/Markdown 로컬 링크·diff check 통과. QA 포트 5005와 두 검증용 MySQL 컨테이너는 정리됐고, 기존 5000 서버 PID 25452·헬스 200을 재확인했다.

## 남은 경계와 다음 담당

이번 결과는 **로컬의 일회용 MySQL 정상 업무 통합**이다. 기존 5000 미리보기는 SQLite로 유지한다. MySQL 서버 자체 재시작·백업 복원·상시 DB/서비스 VM 배포·두 PC 망·실제 관제·NAT·FIM·자원/공방전은 미검증이다. H05 전체 인수나 팀 합의 완료로 표시하지 않는다.

다음은 [프론트 Draft #1](https://github.com/NoBugs-Aleph/haedam-portal-frontend/pull/1)·[백엔드 Draft #1](https://github.com/NoBugs-Aleph/haedam-portal-backend/pull/1)을 다른 팀원이 README대로 독립 재현·리뷰하는 것이다. [capstone Draft #18](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/18)은 #17의 인수인계 브랜치를 base로 유지한다. 서비스 VM 배포 시에는 망 담당의 허용표·실제 DB 계정/비밀값·백업·C의 dist/FIM 기준본을 별도로 맞춘다.
