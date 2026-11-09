# 01. 프로젝트 맥락

## 목표

국내 통신사의 실제 침해사고 5건을 근거로, 같은 유형의 위협을 우리 프로젝트망에서 안전하게 재현하고,
기본 탐지로 놓치는 지점을 찾아 탐지 규칙과 대응 절차로 보완한다. 모든 과정은 인시던트 티켓으로 기록한다.

- 기간: 2주(평일 10일)
- 핵심 질문: 기본 설정만으로는 무엇을 놓치고, 무엇을 추가해야 잡히는가?

## 근거 사례

| 사례 | 핵심 원인 | 연결 티켓 |
|---|---|---|
| SKT 유심 정보 유출 (2025) | BPFDoor 수년간 잠복, 평문 계정 정보, 키 미암호화, 로그 부족 | INC-01, INC-02 |
| SK커뮤니케이션즈 해킹 (2011) | 업데이트 서버 경유 공급망 공격, 내부 PC에서 DB 접근 | INC-03 |
| KT 고객정보 유출 (2012·2014) | 대량 조회 미탐지, 객체 단위 권한 검사 부재 | INC-04 |
| KT 불법 펨토셀 (2025) | 미인증 장비의 망 접속 | INC-05 |
| LG유플러스 (2023·2025) | 레거시 관리 미흡, 디도스, 증거 보존 미흡 | INC-04, INC-06 |

수치와 세부 경위는 공식 발표 원문으로 확인한 뒤에만 보고서에 쓴다.

## 인시던트 티켓

| 티켓 | 탐지 축 | 재현 상황 | 탐지 도구 |
|---|---|---|---|
| INC-01 | 호스트 | 숨겨진 프로세스와 패킷 감청 소켓(BPFDoor 흉내) | Wazuh 명령 모니터링 |
| INC-02 | 호스트 | MockTel 서버의 평문 비밀번호·하드코딩 키 | Wazuh 규칙, gitleaks |
| INC-03 | 호스트 | 바이너리·설정 파일 변조, 취약한 구버전 의존성 | Wazuh FIM, pip-audit |
| INC-04 | 네트워크 | MockTel 고객 조회 API 대량 조회(IDOR), 기본 관리자 계정 | Suricata |
| INC-05 | 네트워크 | 미인가 VM(rogue)의 프로젝트망 접속 | arpwatch, Suricata |
| INC-06 | 가용성 | MockTel로 HTTP 요청 폭주 | Suricata threshold, HAProxy, fail2ban |

## 프로젝트 환경

| 호스트명 | IP | 역할 |
|---|---|---|
| attacker | 10.10.10.10 | 시나리오 재현, 부하 생성 |
| lb-01 | 10.10.10.20 | HAProxy, fail2ban, Wazuh 에이전트 |
| web-01 | 10.10.10.31 | MockTel + Nginx + Wazuh 에이전트 (INC-01~03 대상) |
| web-02 | 10.10.10.32 | MockTel + Nginx + Wazuh 에이전트 (이중화) |
| monitor | 10.10.10.50 | Wazuh 올인원(4.14), Suricata, arpwatch |
| rogue | 10.10.10.99 | INC-05 때만 켜는 미인가 장비 |

- 모든 VM: Ubuntu 24.04 Server, 시간대 Asia/Seoul
- 프로젝트망 lab-net: 호스트 전용 네트워크, DHCP 끔, 인터넷 없음 (1~2일차 설치 때만 NAT 연결)
- **모든 패키지는 2일차 NAT 차단 전에 설치한다.** 차단 후에는 apt·pip가 동작하지 않는다. 설치 목록은 프로젝트 문서의 단계별 구축 가이드 1-1단계.
- pip-audit과 gitleaks는 온라인 취약점 정보가 필요하거나 저장소를 대상으로 하므로, 프로젝트망 VM이 아닌 팀원 PC에서 실행한다.
- 스냅샷: 모든 VM에 `baseline` 스냅샷. 시나리오가 꼬이면 되돌린다.

## MockTel (취약 웹앱)

가상의 통신사 고객센터. **실제 통신사 이름·로고·도메인을 쓰지 않는다.**
Python Flask + SQLite, gunicorn(127.0.0.1:8000) 앞에 Nginx(80).
환경 변수 `SECURE_MODE=0`이면 취약 버전, `1`이면 수정 버전으로 동작한다.
`requirements.txt`(수정 버전)와 `requirements-vuln.txt`(취약 버전)의 패키지는 NAT 차단 전에 `/opt/mocktel/wheels/`에 모두 받아 두고,
이후에는 `pip install --no-index --find-links wheels`로만 설치한다. 기능에 새 패키지가 필요하면 차단 전에 avail에 알린다.
뼈대(`core/`)와 기능 파일 틀은 avail이 1~2일차에 만들고, 각 기능의 취약점·수정 코드는 해당 티켓 담당이 채운다.

| 기능 파일 | 엔드포인트 | 취약점 (SECURE_MODE=0) | 수정 (SECURE_MODE=1) | 티켓 |
|---|---|---|---|---|
| `features/auth.py` | `POST /login` | 비밀번호 평문 저장 (`auth_users`) | argon2 해싱 | INC-02 |
| `features/config_leak.py` | `GET /debug/config` | DB 비밀번호·API 키 하드코딩·노출 (`LAB-FAKE-` 값) | 환경 변수로 분리, 404 | INC-02 |
| `features/customer_api.py` | `GET /api/customers/<id>` | IDOR, 횟수 제한 없음 | 소유자 검사(403), rate limit(429) | INC-04 |
| `features/admin.py` | `POST /admin/login` | 기본 계정 admin/admin | 기본 계정 제거, 5회 실패 시 잠금 | INC-04 |
| `features/search.py` | `GET /search?q=` | 제한 없는 무거운 조회 | 페이지당 20건, 60초 캐시 | INC-06 |
| `requirements-vuln.txt` | – | 취약점이 알려진 구버전 패키지 1개 (예: `Jinja2==2.10`) | 최신 버전 | INC-03 |

모든 응답에 헤더 `X-Served-By: <호스트명>`을 넣어 web-01과 web-02를 구분한다. `/health`는 `ok`를 돌려준다.
DB 파일은 `/opt/mocktel/data/mocktel.db`, 앱 코드는 `/opt/mocktel/app/`에 둔다(INC-02·03 탐지 규칙이 이 경로를 본다).

## 티켓별 상세와 결과 기준

- 티켓별 재현 명령, 탐지 규칙, 기대 결과는 프로젝트 문서의 "티켓 상세 (INC-02~06)" 탭과 메인 탭의 INC-01 상세 진행 계획을 따른다.
- 성공 여부는 메인 탭 "성공 지표" 표로 판단한다: 탐지율 6/6, 탐지 5분 이내, 오탐 2건 이하, SECURE_MODE=1에서 공격 성공 0건, INC-06 오류율 1% 이하·p95 1초 이하.
- 사고 대응 순서와 신고 기한(훈련용)은 "사고 대응 플레이북" 탭을 따른다.
