# S1 실제 포털 코드 연결 리허설 · 집 격리 시험

작업 경계: 사람 자리 B·Codex, 기술 역할 backend/detection. capstone의 새 리허설/회귀·인수 문서만 수정하며 backend는 명시한 로컬 소스를 읽기만 한다. 기존 운영/미리보기·DB·학원 장비·n8n 서비스·키·망·PROGRESS를 변경하지 않는다. 기존 PR55 고정 리허설은 이력으로 보존한다.

시험 ID는 home-s1-portal-20261027, 출발지는 합성 REMOTE_ADDR, DB/사용자/키/로그는 새 임시 폴더의 시험 전용 값이다. 주 경로는 포털 IP 차단과 C 티켓이며 pfSense·Wazuh·메시지 발송은 없다. Graylog 탐지는 실행하지 않고 포털 로그인 실패 로그에서 합성 탐지 이벤트를 만든다. 실제 생성 Code는 Node에서 평가하며 n8n 엔진·HTTP 노드의 실제 전송/식 연결은 검증하지 않는다.

인수 조건: 실제 포털 DB 차단/해제와 공격 시험 출발지403·정상 로그인200, C detected/applied/effect/released·현재 티켓 대조; 중복/응답 유실·기록 실패에서 추가 조치 없이 대조/기록 복구. 원복은 격리 시험의 명시적 수동 호출이며 자동 원복 인수로 보고하지 않는다. 실제 검증 결과와 실행 방법은 아래와 같다.


## 실행과 격리

capstone 루트에서 **준비된 별도 backend 가상환경**을 명시한다. capstone 가상환경에는 SQLAlchemy 등 포털 의존성을 자동 설치하지 않는다. Node.js와 두 저장소가 필요하며 backend 소스 HEAD는 버전 묶음의 dea42c1과 같고 src 작업트리가 깨끗해야 한다. 후보의 n8n/C 파일 해시도 먼저 검사한다. 버전이 다르면 새 인수 묶음을 검토한 뒤 사용한다.

```powershell
& '..\haedam-portal-backend\.venv\Scripts\python.exe' tools/rehearse_s1_portal.py --backend-root '..\haedam-portal-backend' --output '.local/s1-portal-next'
```

이미 있는 출력 폴더는 거절한다. 재실행에는 새 이름을 사용하고 과거 결과/DB를 삭제하지 않는다. DB/세션/로그는 TemporaryDirectory에 만들고 끝나면 정리한다. 보고서만 명시한 새 폴더에 남긴다. 앱 생성기가 config 적용 전 instance 디렉터리를 만들기 때문에 포털 모듈의 instance 기준 ROOT도 시험 폴더로 돌린다. 이 변경은 리허설 자식 프로세스 메모리에만 있고 backend 원본은 바꾸지 않는다.

GELF는 끄고 포털 DB URI·로그·정적 경로·키·허용 CIDR·쿠키 설정은 합성값으로 고정한다. Python socket connect/connect_ex/sendto/create_connection은 프로세스 안에서 거절한다. Node Code 평가기의 HTTP helper도 실제 호출을 허용하지 않는다. Git은 로컬 버전/변경 조회만 하고 fetch·학교 호출·서버 기동은 하지 않는다. 기존5005/8089 미리보기·운영 DB는 사용하지 않는다.

n8n HTTP 노드/표현식의 실행을 흉내 내 완전 검증했다고 보지 않는다. Code 노드의 요청 경로·키를 읽고 알려진 API 본문을 Flask test client에 전달하는 **명시적인 시험 어댑터**다. 실제 엔진의 분기·HTTP 반환 봉투·자격 증명 연결·식 바인딩은 학원 인수 대상이다. Discord/다른 장비 흐름은 실행하지 않는다.

## 확인한 연결

매 시도에서 실제 로그인 API로 서로 다른 event_id를 가진401 실패9개를 만들고 JSONL에서 대조한다. Graylog 알림은 그 뒤 **합성 판정 이벤트**로 주입하므로 실제 탐지 시각 detected_at은 null이다. threshold/window/활성 정의의 시험으로 세지 않는다. 출발지는 test client의 REMOTE_ADDR이며 실제 NAT/물리 경로 시험이 아니다.

정상 흐름은 실제 생성된 S1 Code→C detected→현재 티켓 재조회→포털112 준비/응답 분류/실제 목록 대조→C applied→다른 출발지의 정상 로그인/공격 출발지403과 DB 차단 행→C effect→수동 포털 unblock→C released/restored·활성 소유권 없음→접근200·DB 차단 행 제거다. effect는 이 격리 앱의 독립 조회를 근거로 하며 실제 장비/학원 효과가 아니다.

| 사례 | 관찰 조건 | 포털 변경 POST 시도 / 실제 차단·해제 이벤트 |
| --- | --- | --- |
| normal | 중복 탐지는 duplicate_no_action, 정상 로그인200·차단403·해제 뒤200, C1개 적용 줄과 효과/원복 | 2 / 차단1·해제1 |
| portal_ack_loss | 실제 차단 커밋 후 응답을 버리고 같은 키로 다시 요청. 최초 응답 재생, 중복 DB 변경 없음 | 3 / 차단1·해제1 |
| record_failure | 포털 조치 뒤 C 기록 전 경계에500 주입. 다음 조치 입력 중단, 원래 키/본문의 기록만 복구 | 2 / 차단1·해제1 |
| record_ack_loss | C에 실제 기록한 뒤 ACK를 버림. 다음 조치 중단·기록 재전송에 최초 응답, 적용 줄1개 | 2 / 차단1·해제1 |
| closed_ack | 원복·사람 close 뒤 같은 detected 키가 옛 open ACK를 반환해도 현재 조회가 조치 전에 중단 | 2 / 차단1·해제1 |
| bad_portal_key | 잘못된 시험 키는403/rejected·retry=false, 공격 출발지200, C 적용 줄 없음 | 1 / 차단0 |
| detected_failure | detected 기록 전500 주입. 포털 호출0·티켓0·시험 출발지200 | 0 / 차단0 |

500/ACK 유실은 **시험 어댑터의 의도적 경계 주입**이며 서비스/망 장애를 실제 일으킨 것이 아니다. 복구도 시험 조율 코드가 기록만 재전송하며 n8n 자동 재개가 완성됐다고 보고하지 않는다. bad_portal_key/detected_failure의 통과는 거부/보류가 기대대로 됐다는 뜻이고 S1 완주가 아니다.

## 회귀와 증적

회귀 `tests/test_s1_portal_rehearsal.py`는 ALEPH_S1_BACKEND_ROOT를 명시했을 때 해당 backend .venv의 별도 프로세스로7개 사례를 실행한다. 설정이 없으면 이 외부 저장소 통합 시험은 skip이며 성공으로 세지 않는다. 명시한 환경이 없거나 실패하면 실패한다. 기존 출력 거절·보고서의 키/비밀번호 미포함도 대조한다. 일반 capstone 환경만으로 기존 출력 거절 검사는 실행할 수 있다.

리허설7개와 회귀2개가 통과했다. 실제 backend 환경을 명시한 최종 전체 **507 passed,1 skipped(99.97초)**. skip은 Windows symlink 생성 OS/권한 조건1건이며 실제 포털 리허설은 skip하지 않았다. n8n builder15개·AI19개·DAG19개·diff 검사를 통과했다. [최소 결과 보고서](capstone/evidence/s1-portal-20261027/report.json)와 [파일 일관성 manifest](capstone/evidence/s1-portal-20261027/manifest.json)를 함께 남겼다. 해시는 작성자 인증 서명이 아니다. 보고서는 사용자/토큰/원문 로그/PC 경로/실행 환경 값을 복사하지 않고 상태·건수·소스 SHA/해시만 남긴다. 실제 source/API 코드·운영 설정을 변경하지 않았다.

남은 것은 실제 Graylog 수집/정의·Webhook 인증, n8n 엔진/HTTP 식 연결, VPN/NAT 출발지·물리 정상 클라이언트, 운영 MySQL·학교 배포·독립 수동 원복이다. 이 리허설이나 포털200만으로 학원 통합 성공을 선언하지 않는다. [학원 S1 카드](school-s1-card-1026.md)로 이어간다.
