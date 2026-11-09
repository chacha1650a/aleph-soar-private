# 10/19 집 세션 · 해담시청 포털 구현

후속 사용성 개선과 최신 검증은 [개선 핸드오프](2026-10-19-portal-usability-improvements.md)를 확인한다. 아래 커밋·검증 수치는 최초 구현 시점의 기록이다.

- 작업 ID: H01~H03, H00 로컬 환경·H04 이벤트/계정 대응 API 경계.
- 담당: 김명준 + Codex. 사용자가 민원포털의 프론트·백 구현을 맡고 React + Flask를 선택했다. 기존 A~D의 보안 케이스 책임은 유지한다. 독립 리뷰어 별도 배정.
- 세 저장소 브랜치: `codex/haedam-portal-mvp`. capstone은 핸드오프 d236221에서, 프론트/백은 각 main 스켈레톤에서 시작했다.
- 구현: React 시민 홈·로그인/가입·민원 신청/본인 목록/상세·담당자 배정/처리/답변·관리자 계정/권한/잠금/재설정·내 비밀번호. Flask는 실제 저장·소유권/역할·세션/CSRF·회수·낙관 잠금·처리 이력·이벤트·관리망/키/중복 제한 계정 대응을 제공한다.
- 게시판 기준 `74fbb64`를 참고하되 공개 글 조회·전달 헤더 신뢰·localStorage 토큰·학원 PC 설정·포털 내 티켓 서비스는 가져오지 않았다.
- 원본 계약: docs/haedam/PORTAL-API.md, contracts/portal-event.schema.json, contracts/portal-examples/flow.json. 기존 event/incident v1.0을 변경하지 않았다. D의 소비자는 별도 매핑이 필요하다.
- 검증: capstone 30 passed/AI 14개/DAG 6개. 백엔드 SQLite 25 passed + MySQL 전용 1 skip, 실제 일회용 MySQL 26 passed(마이그레이션 upgrade/check/downgrade/upgrade·동시 중복 대응). 프론트 build와 실제 Flask/Edge Playwright 6 passed, 홈/로그인 자동 접근성 포함.
- 검증 중 수정: 잘못된 로그인 401 후 CSRF 재시도, MySQL 외래키 인덱스 downgrade 순서, 초기 본문 포커스·텍스트 대비.
- 실행: 두 레포를 나란히 두고 백엔드 `tools/start.ps1 -Setup -SeedDemo`. 기존 DB는 SeedDemo 없이 실행. 상세·환경·실측 한계는 각 레포 README/docs/VERIFICATION.md.
- 비밀값·실제 DB·로그·데모 임시 비밀번호·스크린샷은 Git 제외. 원본 게시판은 수정하지 않았다. 웹 공개 배포와 main 병합은 하지 않았다.

## 게시된 구현 버전

- 계약·규칙 원본: `5e79d461d71e5f70c4daf0288572624a0962f817`, [Draft PR #18](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/18). #17을 선행으로 하는 stacked PR이다.
- 백엔드: `f452a00`, [Draft PR #1](https://github.com/NoBugs-Aleph/haedam-portal-backend/pull/1).
- 프론트: `f761f8b`, [Draft PR #1](https://github.com/NoBugs-Aleph/haedam-portal-frontend/pull/1).
- 세 원격의 `codex/haedam-portal-mvp`로 푸시했다. 각 PR은 열림·Draft이며 독립 리뷰·main 병합 전이다. GitHub CI 결과와 로컬 검증 결과를 구분한다.

## 미완료와 다음 담당의 첫 작업

H05의 독립 재현·두 PC 통합, 실제 Graylog/Wazuh/n8n/pfSense·FIM·NAT·자원/공방전 측정은 미완료다. MySQL 백엔드와 SQLite 브라우저 시험을 구분한다. 계정 대응 API는 실제 pfSense 차단이나 인시던트 생성을 제공하지 않는다.

다음은 팀원이 양쪽 README로 설치·정상 업무를 독립 재현하고 D가 portal-event v1.0과 n8n 계정 대응을 연결하는 것이다. B는 출발지·경계 차단/원복, C는 실제 dist 배포 경로·FIM 정상 배포/변조/원복을 맞춘다. 테스트 합격은 팀 합의·관제 연동·실측 완료 표시가 아니다.
