# 2026-10-19 마감 핸드오프 · 집에서 이어서 하기

다음 세션은 이 문서 → `AGENTS.md` → [작업 카드](../docs/haedam/TASKS.md) → 필요한 계약 순서로 읽는다. 자세한 수행 내역은 [오늘 작업 기록](2026-10-19-daily-work-log.md)에 있다.

## 작업 ID·상태·전달 범위

- 작업 ID: 해담시청 저장소 준비·10/19 Notion 정리·마감 기록. 기존 H00의 저장소 생성·스켈레톤 초기화 부분만 수행했다.
- 상태: **준비 산출물과 기록 완료 / 실제 웹 구현·계약 합의·외부 연동·실측은 미완료**.
- 원래 작업 폴더: `C:/SKT aleph/aleph-soar-capstone`, 브랜치 `docs/proposal-sections`, HEAD `9f1bfbdac210eda00ada25c84aa0c27dfc993339`.
- 게시 브랜치: **`codex/haedam-handoff-1019`**. 최신 `origin/main`(`3171fb4560dc1100fc9723ad7b4e72434f5b2ad8`)에서 분리해 이 작업 파일만 담았다. 초기 게시 커밋은 `bdababbd69a5f28e9f181d61dbc8bec242d55d4b`이며, 이후 기록 보완을 포함한 최종 커밋은 `git log -1`로 확인한다.
- 관련 PR: [기획서 PR #10](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/10)은 병합 완료다. 이번 준비·핸드오프는 **[PR #17](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/17), Draft·열림**으로 게시했으며 자동 병합하지 않았다. GitHub CI 최종 결과는 PR에서 확인한다.
- 다른 작업자의 기획서·피드백 내용을 이 기록 작성자가 구현·실측한 것으로 간주하지 않는다.

## 집에서 받을 저장소

| 저장소 | 받을 내용 | 현재 상태 |
| --- | --- | --- |
| [aleph-soar-capstone](https://github.com/NoBugs-Aleph/aleph-soar-capstone) | 이 핸드오프 브랜치의 문서·공통 규칙·스켈레톤·회의록 원문 | 새 웹 기능 없음 |
| [haedam-portal-frontend](https://github.com/NoBugs-Aleph/haedam-portal-frontend) | main `96102a1c80906989cac1d40760636735bda92ecd` | 13개 파일, AI 지침·빈 폴더만 있음 |
| [haedam-portal-backend](https://github.com/NoBugs-Aleph/haedam-portal-backend) | main `ec46abf6e53ab228bc777f086ff91dfd600dde74` | 13개 파일, Flask 구현 전 |

세 저장소는 비공개다. 인증된 팀 계정으로 받는다. 기존 인증 정보를 기록·복사하거나 다른 계정의 권한을 임의로 바꾸지 않는다. 팀원 쓰기 권한 추가는 이번 작업에서 하지 않았다.

집 PC에서 원하는 상위 폴더를 연 뒤:

```powershell
git clone --branch codex/haedam-handoff-1019 https://github.com/NoBugs-Aleph/aleph-soar-capstone.git
git clone https://github.com/NoBugs-Aleph/haedam-portal-frontend.git
git clone https://github.com/NoBugs-Aleph/haedam-portal-backend.git
```

이미 capstone을 받아 뒀다면 먼저 `git status --short`로 개인 수정부터 확인한다. 작업을 보존한 뒤 다음 명령을 사용한다. 미커밋 변경을 지우거나 강제로 브랜치를 바꾸지 않는다.

```powershell
git fetch origin
git switch codex/haedam-handoff-1019
git pull --ff-only
```

이 브랜치가 병합된 뒤에는 해당 문서가 main에 포함됐는지 확인하고 main을 사용한다. 새 기능은 관련 저장소의 최신 main에서 새 작업 브랜치로 시작한다.

capstone의 도구·테스트가 필요할 때만 다음을 실행한다.

```powershell
cd aleph-soar-capstone
python tools/bootstrap.py
.\.venv\Scripts\python.exe tools/team.py ready
```

**새 프론트·백엔드에는 아직 설치·실행 명령이 없다.** 현재 스켈레톤에서 `npm run dev`나 `flask --app haedam_portal`이 된다고 가정하지 않는다. `.venv`, DB, 비밀값은 다른 PC에서 가져오지 않고 새로 준비한다.

## 결정된 것과 아직 정하지 않은 것

| 결정됨 | 미완료·미확정 |
| --- | --- |
| 해담시청 민원포털, 소개 문구, 프론트·백 레포 분리, Flask 방향 | 프론트 기술·런타임·패키지 관리자, 프론트·백 작업자·리뷰어 |
| A S1·S4 / B S8·S10 / C S7 / D S12 | 새 민원·인증 API·오류·세션·CSRF 계약, 공통 이벤트·사건 확장 |
| PC 2대 분리, 관제 PC의 대시보드·티켓, pfSense의 Suricata | 실제 PC 자리·관리망 어댑터·VMnet 충돌, 자원 실측 |
| 레포 분리로 HTTP 프록시를 자동 추가하지 않음 | 프론트 빌드 결과를 Flask에서 제공하는 배포 구현·IP 보존 실측 |
| S1은 IP 차단, S4는 잠금·기존 세션 회수 후 비밀번호 재설정·해제 | S4·S8 순서 조건 최종 확인(A·B), 중복·재시도·효과·원복 실제 검증 |

기존 역할 A~D를 뒤집지 않는다. 새 레포 세부 배정은 A의 포털·대응 API 책임 아래 조율한다. 10/28 지연 시 S1·S8 확장 전환 기준과 통합 스토리라인 미실시 결정을 유지한다.

## 다음 세션의 첫 작업

**화면 목록과 최초 API 계약부터 작성한다.** 아직 프론트 기술과 작업자가 미정이므로 앱 전체를 임의 스택으로 생성하지 않는다.

1. [해담시청 안내](../docs/haedam/README.md)와 양쪽 레포 `AGENTS.md`를 읽고 프론트 기술·작업자·리뷰어·개발 환경을 맞춘다.
2. capstone `docs/API-CONTRACT.md`와 `contracts/`에서 로그인·로그아웃·현재 사용자·민원 생성/본인 조회/담당자 처리의 권한·입출력·오류를 제안한다. 이 파일에는 아직 실제 계약 변경을 하지 않았다. 변경 시 `aleph-contract-change` 스킬로 스키마·예시·소비자·검증을 함께 맞춘다.
3. 첫 구현은 **로그인 정상/실패 → 실제 출발지 이벤트 → 404 이벤트**를 작게 연결한다. 프록시 없는 초기 경로에서 연결 주소를 사용하고 임의 `X-Forwarded-For`를 무시한다. 로그인·접근 로그·차단 검사에서 같은 IP 해석을 사용한다.
4. 민원 작성 → 저장 → 새로고침 후 본인 조회 → 담당자 처리 → 시민 상태 확인을 붙인다. 타인 조회 거부·세션 만료·재시작 후 데이터 유지도 확인한다.
5. B·D는 PC 간 로그 도착, n8n→pfSense 차단·해제, Graylog·Wazuh 동시 메모리 위험 시험을 병행한다. 웹 전체 완성 뒤로 사전 위험 확인을 미루지 않는다.

완료 조건은 호출 성공과 실제 효과를 구분한다. 원격 GitHub 파일 확인이나 스키마 통과는 탐지·차단·원복 성공의 증거가 아니다.

## 다음에 특히 조심할 연결 지점

- **IP·404:** NAT/컨테이너에서도 출발지 보존을 확인한다. 없는 경로를 모두 SPA의 200 응답으로 돌려 `web-scan`을 없애지 않는다. 앱·Suricata·pfSense의 src_ip·인터페이스·방향을 대조한다. 공격 IP 차단 후 별도 정상 사용자 동작을 확인한다.
- **S7:** asset_id + 파일 키, URL↔실제 파일 경로, bind mount·realtime FIM, 정상 배포 허용, 읽기 전용 기준본·해시, 신규 파일 격리를 함께 정한다. Wazuh active response는 설계 1안이며 랩 실행 검증 전이다. 봇 117 번호 충돌도 미확인이다.
- **S12:** 출발지별 요청 이벤트로 n8n을 시작하고 n8n이 직접 헬스체크한다. 이전의 두 Webhook 결합안을 기본으로 되살리지 않는다. 후보 탐지와 최종 판정·시민 경로 회복을 구분한다.
- **중복·원복:** 티켓 저장소 유일 제약과 봇·대상별 중복 방지, 실패 후 재시도, 사전 상태·정상 사용자 영향·원복을 설계한다. S4 해제 시 회수한 세션은 되살리지 않는다.
- **수업 코드:** 필요한 기능만 이식하는 A 결정을 유지한다. 업로드 허용 여부는 강사님 확인 전이며, 과거 `src/aleph_soar` 이식 경로를 새 백엔드 작업표와 맞춘다.
- **출처 동기화:** 새 레포의 초기 `docs/SOURCE.json`은 원본 규칙 미커밋 시점의 스냅샷이다. 원본은 이제 capstone `bdababbd69a5f28e9f181d61dbc8bec242d55d4b`에서 확인할 수 있다. 양쪽 레포에서 이 원본 커밋으로 출처를 갱신할 후속 PR이 필요하다. 공통 규칙 v2의 실제 내용·해시는 이미 두 레포에서 동일하다.

## Notion·PDF·잔여 정리

- [10/19 오전·오후 모음](https://app.notion.com/p/3fe2d9cb6a30805d80f9cef5f95adf81): 오늘 현황·회의 원문 링크·후속 작업을 먼저 확인한다.
- [팀 홈](https://app.notion.com/p/e032d9cb6a3083ffa42101fb41dcf13f): 기관명·자리 담당·레포·IP 기준을 갱신했다.
- [오후 기록](https://app.notion.com/p/3fe2d9cb6a30806db529c09b52d60ef6)과 [오전 기록](https://app.notion.com/p/3fe2d9cb6a30803fb591de1afc6dbe04)은 회의 당시 사실을 보존한다. D안과 자리 D·S12를 동일한 의미로 단정하지 않는다.
- [이전 검토 PDF 첨부](https://app.notion.com/p/3fe2d9cb6a308059a54eda3ad2f3fabe)는 ef3e546 기준 9쪽이다. 최신 기획서 제출 PDF가 아니며 새 제출본은 잔여 피드백 뒤 만든다.
- Notion 업무 보드·일정·팀원 하위 페이지에는 오래된 제안이 남을 수 있다. 전체 DB 동기화나 모든 카드 상태 수정을 완료했다고 보고하지 않는다. 남은 범위는 [작업 기록 7절](2026-10-19-daily-work-log.md#7-notion-작성최신화)에 적었다.
- Notion 커넥터는 앞서 올바른 공유 팀 공간에 접근하지 못했다. 실제 작성은 로그인된 브라우저의 `NoBugs · ALEPH 팀 notion` 팀 홈을 기준으로 했다. 집에서는 먼저 실제 연결된 워크스페이스를 확인하고 개인 페이지·공유 권한을 임의로 바꾸지 않는다.
- 로컬 PDF·PNG·브라우저 핸들은 집 PC로 자동 이전되지 않는다. Notion 링크와 첨부를 사용한다. 비밀번호·토큰·세션 정보는 전달하지 않는다.

## 남겨 둔 학원 PC 작업 폴더

- `C:/SKT aleph/aleph-soar-capstone`: 원래 문서 작업 트리를 유지한다. 이 마감의 게시 작업과 분리하며 미커밋 내용을 강제로 지우지 않는다.
- `C:/SKT aleph/haedam-portal-frontend`, `C:/SKT aleph/haedam-portal-backend`: 초기 스켈레톤이 올라간 실제 레포다.
- `C:/SKT aleph/aleph-flask-portal`, `codex/flask-civic-portal`, base `63a3996`: **중단된 이전 실험 준비용 worktree**. 사용자 “잠만” 요청 때 bootstrap을 중지했다. 의존성 설치 일부만 진행됐으며 editable 앱 설치·테스트는 완료 확인하지 않았다. 소스 변경·실행 서버는 없다. 새 백엔드 레포와 혼동하거나 자동 재개하지 않는다.
- `C:/SKT aleph/aleph-handoff-1019`: 이번 게시용 worktree. 기능 개발용 폴더가 아니다.

## 검증과 전달 범위

문서 링크·UTF-8·공통 규칙 복사본·초기 레포 blob 일치, AI 생성물 검사(14개), 작업 DAG 검사(6개)를 확인했다. 마감 시 원래 capstone 작업 트리에서 `.venv/Scripts/python.exe -m pytest -q`를 실행해 **29 passed**를 확인했고, AI 생성물 14개·작업 DAG 6개 검사도 다시 통과했다. 기존 스켈레톤·도구·계약 테스트 결과이며 새 프론트·백엔드 기능이나 실제 웹·DB·탐지·대응·원복 시험의 결과가 아니다.

게시용 worktree에서도 Markdown 19개의 UTF-8·로컬 파일 링크, 공통 규칙 복사본 일치, AI 생성물 14개·작업 DAG 6개, 스테이징 공백 검사를 통과했다. 초기 커밋의 36개 파일은 모두 기록·준비 산출물이다. PR #17은 Draft이며 GitHub CI 최종 통과를 이 기록에서 주장하지 않는다.

게시 후 원래 폴더에 미커밋 작업이 남아도 이미 게시한 파일과 겹치는지 확인한 뒤 담당자가 정리한다. `git reset --hard`나 자동 삭제를 사용하지 않는다.

## 다음 채팅 시작 문장

```text
work-log/2026-10-19-end-of-day-handoff.md를 읽고 집에서 이어서 하자.
먼저 원격 브랜치와 main 상태를 확인하고, 해담시청 프론트 기술·담당·최초 API 계약부터 맞추자.
레포는 이미 생성됐으니 다시 만들지 말고, 기존 A~D 담당·IP/404 검증 기준과 미실측 상태를 유지해줘.
```
