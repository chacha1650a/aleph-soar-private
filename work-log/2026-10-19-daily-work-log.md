# 2026-10-19 작업 기록 · 해담시청·저장소·Notion

- 작성: Codex, 사용자 김명준의 작업 마감·집 PC 인수인계 요청.
- 기준: 2026-10-19, Asia/Seoul. 이 채팅에서 수행한 작업과 마지막에 재확인한 저장소 상태를 구분해 기록한다.
- 다음 세션은 [집에서 이어서 하기](2026-10-19-end-of-day-handoff.md)를 먼저 읽는다.

## 1. 이번 작업의 결론

서비스 이름을 **해담시청 민원포털**로 정하고 프론트·백엔드 저장소를 별도로 만들었다. 초기 AI 지침과 폴더 구조를 올렸으며, 실제 웹 기능은 아직 구현하지 않았다. 팀 Notion에는 오늘 오전·오후 회의 모음을 만들고 팀 홈의 현황을 갱신했다.

기획서의 이전 통신사 배경, 오전 회의 당시의 담당 배정 대기, 이전 검토 PDF를 현재 구현 상태로 해석하지 않는다.

## 2. 결정 사항

| 구분 | 현재 기준 | 근거·확인 범위 |
| --- | --- | --- |
| 이름 | 해담시청 민원포털 / 시민의 목소리를 담다, 해담시청 | 사용자 확정 |
| 저장소 | `haedam-portal-frontend`, `haedam-portal-backend` 분리 | 사용자 요청, GitHub 실제 생성 |
| 백엔드 | Flask | 사용자와의 진행 방향, 스켈레톤만 준비 |
| 프론트 | 프레임워크·런타임·패키지 관리자 미정 | React 등으로 임의 확정하지 않음 |
| 담당 | A 반소람(whiteclover0542) S1·S4, B 김명준(myeongjundev) S8·S10, C 김상혁(shk12170-dev) S7, D 김대훈(chacha1650a) S12 | 10/19 오후 회의 기록과 기획서 |
| 개발 배정 | 프론트·백엔드별 실제 작업자·리뷰어는 별도 배정 전 | 기존 A~D의 책임은 유지 |
| 배치 | 인접한 공격·서비스 PC(VMware)와 관제 PC(Docker/WSL2), Suricata는 pfSense 패키지 | 팀 설계, 실제 자리·연결·자원 시험 완료 아님 |
| 대시보드 | 관제 PC Docker에 티켓과 함께 두고 포털 관리자 메뉴에서 링크 제공 | 팀 결정, 강사님 허용 여부는 질문 목록에 남음 |
| 토폴로지 | 밴드 그림은 참고용 | 사용자 확인. 그대로 복제하는 목표가 아님 |

필수 4종·ID 6개를 유지하고 10/28에 밀리면 S1·S8을 확장으로 전환한다. 통합 스토리라인 시연은 추가하지 않는다.

## 3. 만든 문서·스켈레톤

- [저장소 분리 안내](../docs/haedam/README.md)
- [공통 제약 원본 v2](../docs/haedam/PROJECT-RULES.md)
- [H00~H05 작업 카드](../docs/haedam/TASKS.md)
- [프론트 스켈레톤](../scaffolds/haedam-portal-frontend/README.md)
- [백엔드 스켈레톤](../scaffolds/haedam-portal-backend/README.md)
- [Codex 보조 진입 문서](../CODEX.md), 루트 `AGENTS.md`·`README.md`의 연결 안내.

각 스켈레톤에는 `AGENTS.md`·`CLAUDE.md`·`CODEX.md`, `.gitignore`, 계약 출처 안내, 공통 규칙 복사본, 출처·SHA-256을 담은 `docs/SOURCE.json`, 빈 작업 폴더가 있다. 공통 규칙 원본은 capstone이며 복사본을 별도 원본으로 발전시키지 않는다.

API·이벤트·사건 스키마 자체는 변경하지 않았다. 기존 `docs/API-CONTRACT.md`와 `contracts/`에는 미구현 후보·합성 예시가 있으며, 익명·FIM·경계·가용성 신호를 받기 위한 계약 확장은 후속 작업이다.

## 4. GitHub 저장소 생성·확인

| 저장소 | 공개 범위·브랜치 | 초기 커밋 | 확인 |
| --- | --- | --- | --- |
| [프론트](https://github.com/NoBugs-Aleph/haedam-portal-frontend) | 비공개 / main | `96102a1c80906989cac1d40760636735bda92ecd` | 13개 파일 원격 blob과 로컬 파일 일치, 작업 트리 깨끗함 |
| [백엔드](https://github.com/NoBugs-Aleph/haedam-portal-backend) | 비공개 / main | `ec46abf6e53ab228bc777f086ff91dfd600dde74` | 13개 파일 원격 blob과 로컬 파일 일치, 작업 트리 깨끗함 |

생성 시 기존 capstone과 같은 `NoBugs-Aleph` 조직·비공개 범위를 사용했다. 팀원 초대·쓰기 권한 추가·브랜치 보호 설정은 이 작업에서 하지 않았다. 집에서 다른 계정으로 작업할 경우 접근·쓰기 권한은 별도 확인한다.

처음 원본 규칙은 capstone의 미커밋 작업 트리에 있었다. 따라서 새 저장소의 `SOURCE.json`에는 `source_rules_commit: null`, 초기 기준 HEAD `9f1bfbd...`, 실제 원본 SHA-256을 기록했다. 원본이 해당 HEAD에 포함돼 있다고 표시하지 않았다. 이 인수인계 브랜치로 원본을 게시한 뒤에도 새 저장소의 초기 출처 기록은 자동으로 갱신되지 않는다.

## 5. 출발지 IP 피드백 반영

팀원의 프록시·전달 헤더·계층 간 IP·404 로그 누락 우려를 검토했다. 레포 분리와 요청 경로 변경을 구분하고, 기존 기획서의 **HTTP 프록시 없는 경로**를 초기 기준으로 삼았다. 프론트 빌드 결과를 Flask 앱에서 함께 제공하는 안을 먼저 검증한다. 프론트 기술이나 배포 구현이 확정·완료된 것은 아니다.

추가한 인수 조건:

1. 로그인·접근 로그·차단 검사에 공통 IP 해석을 사용한다. 초기 배치에서는 연결 주소를 사용하고 임의 `X-Forwarded-For`를 믿지 않는다.
2. 실제 NAT·컨테이너 경로에서 출발지가 보존되는지 확인한다.
3. 없는 경로의 실제 404와 `web-scan` 이벤트를 확인한다. 모든 미지정 경로를 화면의 200 응답으로 바꾸지 않는다.
4. 앱·Suricata·pfSense의 관측 위치·방향·필드를 맞춰 S1·S8·S10의 출발지를 연결한다.
5. 공격 IP 차단 뒤 별도 정상 출발지의 서비스 이용을 확인한다.

원본 게시판 코드의 헤더 처리 차이는 이 채팅에서 코드를 직접 대조하지 않았다. 게시판 기능 이식 대상 경로도 기존 `src/aleph_soar`에서 새 백엔드 경로로 조율해야 한다. 수업 코드 업로드 가능 여부는 강사님 확인 전이다.

참고한 공식 문서: [Flask 프록시 신뢰 설정](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/), [nginx 전달 헤더](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header), [pfSense 포트 포워딩](https://docs.netgate.com/pfsense/en/latest/nat/port-forwards.html). 공식 문서 확인은 우리 랩의 성공 증거가 아니다.

## 6. 기획서 검토·PDF

이 채팅에서 교차검토 PDF를 만들고 팀 Notion에 공유했다. 최종 공유 파일은 **표 2개·그래프 2개, 9쪽**인 `NoBugs_기획서_교차검토_표그래프_ef3e546.pdf`다. 당시 검토 항목은 문서 반영 9 / 추가 확인 5 / 제출본 정리 대기 1로 정리했다. 구현 완료율이 아니다.

그 뒤 A·C·D 피드백이 추가됐다. Notion 최신화 때 확인한 기획서 작업본은 `docs/proposal-sections`의 `9f1bfbdac210eda00ada25c84aa0c27dfc993339`다. 마지막 GitHub 재확인에서 [PR #10](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/10)은 **병합 완료**였고, 병합 커밋은 `e3b26d1f5a597908398169c2836fd11507b73989`다. 이 기록을 마감할 때 fetch한 `origin/main`은 `3171fb4560dc1100fc9723ad7b4e72434f5b2ad8`이며 9f1bfbd를 포함한다.

ef3e546 PDF는 이전 시점 검토본이다. 9f1bfbd 이후까지 반영한 최신 제출용 PDF는 아직 만들지 않았다. 최신 변경과 기한은 기획서·팀원 피드백 문서를 확인한다.

## 7. Notion 작성·최신화

| 위치 | 결과 |
| --- | --- |
| [팀 홈](https://app.notion.com/p/e032d9cb6a3083ffa42101fb41dcf13f) | 해담시청 이름, A~D 확정, 새 레포 링크·준비 상태, IP/404 검증 기준, 이전 PDF 표시, 일일 회의 모음 링크, 일부 후속 체크리스트 갱신 |
| [10/19 오전·오후 모음](https://app.notion.com/p/3fe2d9cb6a30805d80f9cef5f95adf81) | 두 회의 링크·시점 비교·현재 담당/환경/레포·피드백 반영·담당별 할 일·일정·근거 정리 |
| [오후 회의록](https://app.notion.com/p/3fe2d9cb6a30806db529c09b52d60ef6) | 15:00~15:20, 전원 참석, 8개 항목·표 작성. 회의 당시 예정과 미확인을 보존 |
| [오전 기록](https://app.notion.com/p/3fe2d9cb6a30803fb591de1afc6dbe04) | 기존 기록을 보존하고 모음에 연결 |
| [회의록과 결정](https://app.notion.com/p/7172d9cb6a30833693ba8149bc37b1a6) | 일일 모음 연결, 현재 기관명·담당 확정, 결정 표 날짜·상태 갱신 |
| [이전 공유 검토본](https://app.notion.com/p/3fe2d9cb6a308059a54eda3ad2f3fabe) | ef3e546 PDF 첨부 유지. 팀 홈에서 이전 검토본이라고 안내 |

서기 인수인계 원문은 [회의록 인수인계 MD](../team_docs/2026-10-19%20회의록%20인수인계%20—%201조%20NoBugs.md)다. 원문의 서기 계정 비공개 페이지는 수정하거나 공유 설정을 바꾸지 않았다. 기존 팀 공유 공간을 사용했으며 오후 페이지의 상속된 팀/워크스페이스 권한을 확인했다. 밴드·이메일·팀 채널 메시지는 전송하지 않았다.

**Notion 전체 동기화는 하지 않았다.** 업무 보드의 옛 담당 배정·PC 사양 수합 카드, 일정의 10/20 옛 제목, 팀원·자료실 등 하위 페이지는 이번 최신화에서 전체 대조하지 않았다. 팀 홈의 이전 10/20 담당 배정 제안 링크도 이력으로 남아 있다. 다음 편집에서는 일일 모음의 현재 상태를 기준으로 중복·오래된 카드를 조율한다. 오전의 미배정 기록은 역사적 사실이므로 삭제하지 않는다.

## 8. 실제 확인과 확인하지 않은 것

- 전달: 준비 파일·회의록 원문·마감 기록을 `codex/haedam-handoff-1019`에 게시했다. 초기 커밋은 `bdababb`, [PR #17](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/17)은 Draft다. 원래 기획서 작업 폴더는 그대로 보존했다.
- 수행: Markdown 로컬 링크·UTF-8·두 규칙 복사본의 바이트 일치·빈 폴더 10개 확인, `git diff --check`, `tools/sync_ai_assets.py --check`(14개), `tools/team.py validate`(6개 작업), 새 원격 레포 파일별 blob 확인.
- 수행: Notion 작성 결과·오전/오후 연결·새 탭에서 팀 홈 저장 상태 확인, 화면 캡처 저장.
- 마감 시 검사 결과와 게시 브랜치는 [핸드오프의 검증·전달 범위](2026-10-19-end-of-day-handoff.md#검증과-전달-범위)에 덧붙인다.
- 미수행: 로그인·민원 API 구현, 실제 DB 연결, Graylog·Wazuh·Suricata·n8n·pfSense 연동, 공격·차단·원복·부하·메모리 실측.

캡처·PDF는 학원 PC의 `C:/Users/user/.codex/visualizations/2026/10/19/01a151a5-a87c-76e1-b9e4-a96c82315167/`에 있다. 이 로컬 폴더는 집 PC로 자동 복사되지 않는다. PDF는 Notion 첨부에서 받을 수 있다. 스크린샷에는 `NoBugs-1019-meetings-combined.png`, `NoBugs-team-home-updated-1019.png`, `NoBugs-1019-afternoon-meeting.png`가 있다. 이번 마감에서는 이미지·PDF를 Git에 추가하지 않는다.
