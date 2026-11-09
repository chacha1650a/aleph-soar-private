# R04 · Claude 유사 사이트·화면 구성안 검토 원문

수신일: 2026-10-15 (Asia/Seoul) · 실행: 로컬 Claude Code 기본 모델 · 요청: prompts/claude-reference-sites-review.md

아래는 CLI 응답의 result 본문입니다. Claude의 검토 의견이며 팀 합의·제품 동작 시험 결과와 구분합니다. 도구 오류·열람 한계는 원문에 기재된 범위를 확인합니다. 원시 실행 결과 JSON은 Git 제외된 references/local/claude-r04/result.json에 보존합니다.

---

# R04 검토: 유사 사이트와 화면 구성안 (Claude 독립 검토)

이번 검토에서는 파일을 하나도 수정하지 않았습니다. 이 응답이 결과물이고, 작업 기록 저장은 Codex가 맡습니다.

## 1. 검토 범위, 읽은 파일, 웹 확인 결과와 한계

**읽은 파일**
- AGENTS.md
- docs/17 전체, docs/14 전체, docs/16 전체
- docs/15의 4~7절
- docs/API-CONTRACT.md

**웹 자료.** 모두 2026-10-15에 페이지만 열람했습니다. 제품을 설치하거나 실제로 동작시켜 보지는 않았습니다.

| 자료 | 결과 |
| --- | --- |
| [Claroty xDome SA](https://www.claroty.com/industrial-cybersecurity/xdome-secure-access) | 열람 성공. 확인한 내용: 내부·제3자 접근, 기기 단위 정책, 접근 요청 승인·거부, 실시간 로깅·감사, SaaS·온프레미스 배치 |
| [Claroty 데모 허브](https://demohub.claroty.com/hub/Industrial) | 열지 않았습니다. 데모 안의 화면은 확인하지 못했습니다 |
| [BeyondTrust PRA](https://www.beyondtrust.com/products/privileged-remote-access) | **HTTP 403으로 확인 실패** |
| BeyondTrust 대체 자료: [세션 관리](https://www.beyondtrust.com/products/password-safe/features/privileged-session-management), [PRA 문서](https://docs.beyondtrust.com/pra/v25.1/docs/pf-security) | 검색 결과 요약으로만 봤습니다. 세션 기록, 활성 세션 일시정지·종료, 명령 차단 시 세션 잠금이 나옵니다. 공급업체 포털·승인 관련 설명은 비공식 Q&A에서만 나와 근거로 쓰지 않았습니다 |
| [Defender 공격 중단 결과](https://learn.microsoft.com/en-us/defender-xdr/autoad-results) (ms.date 2026-05-13) | 열람 성공. 확인한 내용: 사건 태그, 차단된 사용자 라벨, **enable user / release from containment** 버튼, Action center, Activities 탭의 **Policy status(Active/Inactive/Not applicable/No status)**, 해제 전 위험을 평가하라는 경고 |
| [Graylog Investigations](https://go2docs.graylog.org/current/what_more_can_graylog_do_for_me/investigations.htm) | 열람 성공. Graylog Security의 **별도 라이선스** 기능이며 증거·타임라인 기능이 있습니다 |
| [Graylog Events & Alerts](https://graylog.org/feature/events-and-alerts/) | 열람 성공. Event Definitions와 HTTP 알림은 무료인 Open 에디션에도 있습니다. **Correlation Engine은 Security·Enterprise 전용**입니다 |
| [SAP Business Network](https://www.sap.com/sea/products/business-network/suppliers/overview.html) | **HTTP 403으로 확인 실패.** docs/17에 적힌 "소개·데모 영상"은 검증하지 못했습니다 |
| [ThingsBoard 탱크 수위 사례](https://thingsboard.io/use-cases/tank-level-monitoring/) | 열람 성공. 연결 상태, 추이 차트, 알람 패널, 라이브 데모 링크가 있습니다. 라이브 데모는 열지 않았고, Community Edition 라이선스도 이 페이지에서는 확인하지 못했습니다 |
| [Wazuh Active Response](https://documentation.wazuh.com/current/user-manual/capabilities/active-response/index.html) | 열람 성공. 탐지 규칙에 맞으면 에이전트가 스크립트를 실행합니다. 일회성 실행과, 일정 시간 뒤 자동으로 원래대로 되돌리는 방식이 있고, 사용자 정의 스크립트도 됩니다 |
| [pfSense 원격 syslog](https://docs.netgate.com/pfsense/en/latest/monitoring/logs/remote.html), [pfREST](https://gittrend.io/repo/pfrest/pfSense-pkg-RESTAPI) | 검색 결과 요약만 봤습니다. 원격 syslog는 공식 기능이고, REST API는 Netgate와 무관한 **비공식** 패키지입니다 |

**한계.** 데모나 로그인 뒤의 화면은 하나도 확인하지 않았습니다. 버전 호환성도 시험하지 않았습니다. "(일반 지식)"이라고 표시한 판단은 이번에 출처를 확인하지 않은 내용입니다.

## 2. 최종 판정: **수정 권고**

- **수용**
  - 사이트를 화면 참고용으로만 쓰고 제품과 같은 수준이라고 주장하지 않는 원칙
  - "역할 4개 ≠ 앱 4개"라는 단서
  - Graylog Investigations가 유료 라이선스라는 주의
  - 중심 시연의 순서
- **수정 권고**
  - ① 참고 순위: 상위 2개(Claroty·BeyondTrust)가 같은 범주(OT 원격 접근·특권 접근 관리)입니다. 생산 현황 화면에 쓸 참고는 없습니다.
  - ② 포털 사용자 화면과 보안 운영 화면의 경계가 흐립니다.
  - ③ 화면에 보이는 것과 공방전 증거가 구분되어 있지 않습니다.
  - ④ "업무 복귀 검증 시스템"이라는 표현이 차별점을 과장합니다.
- **판단 보류**: 공방전 규칙(공격 범위, 자동 IP 차단 허용 여부, NAT 여부, 채점 기준), 도구 배치·버전, Graylog 에디션, 평가 필수 요건

## 3. 우선순위별 지적

| 중요도 | 위치·주장 | 이유 | 수정안 |
| --- | --- | --- | --- |
| **P1** | docs/17 30행 "Claroty → BeyondTrust → Defender" | Claroty와 BeyondTrust는 원격 접속(RDP·SSH) 세션을 중계하는 게이트웨이입니다. 우리 대상은 웹 앱의 세션과 자료 접근 권한이라 성격이 다릅니다. 이 둘을 앞에 두면 세션 녹화나 자격 증명 금고처럼 2주 범위를 넘는 기능으로 끌려갑니다. 게다가 BeyondTrust 공식 페이지는 403이었습니다 | **Defender → Claroty → ThingsBoard**로 바꿉니다. BeyondTrust는 Claroty를 대신할 참고로, SAP는 제외로 내립니다 |
| **P1** | docs/17 36~39행 역할 4개와 docs/14 24~29행 화면 4개 | docs/14 17행은 "보안·복구 담당자"를 한 역할로 봅니다. docs/17은 이를 둘로 나눴는데 복구 담당자용 화면이 없습니다. 또 "기존 세션 거부·정상 업무 재개 확인"을 사람이 하는 일처럼 적었지만, 실제로는 자동 재시험이 낸 결과입니다 | 화면은 4개로 유지합니다. **사건 상세** 화면 안에 대응 패널과 복귀 패널을 두고 권한으로 나눕니다(잠금 실행자와 복귀 승인자를 다르게). 복구 담당자 문구는 "재시험 결과를 보고 복귀를 승인"으로 고칩니다 |
| **P1** | docs/17 38행 "보안 담당자: 사건·로그·계정 대응" | 로그 검색은 Graylog·Wazuh가 맡을 일입니다. 우리 사건 화면이 이를 복제하면 시간 낭비이고, 포털 앱에 운영 기능이 섞입니다 | 사건 상세에는 근거 요약, 조치 상태, 효과 재시험 결과, 복귀 상태만 둡니다. 로그 원문은 Graylog 검색 링크(쿼리와 시간 범위)로 대신합니다. 운영 화면은 경로·권한·네트워크 허용을 따로 둡니다 |
| **P1** | docs/17 43행 중심 시연, 질문 5 | 공방전에서 화면의 "차단됨" 표시는 증거가 아닙니다 | pfSense 허용·거부 로그, 요청 ID가 찍힌 앱 인증·인가 로그, Graylog 수신 기록, 재시험의 401/403 응답 기록, 수집 순번 대조를 따로 남깁니다. 화면은 이 증거들의 ID를 가리키기만 합니다 |
| **P1** | 질문 6: Graylog 에디션 | Open 에디션에는 Event Definitions와 HTTP 알림만 있고 Correlation Engine이 없습니다([출처](https://graylog.org/feature/events-and-alerts/)). 그래서 "실패 → 성공 → 담당 외 자료 조회" 같은 순서 탐지를 Open만으로 하기는 어렵습니다 | 기본안: Graylog Open은 수집·검색·단일 조건 이벤트까지 맡고, HTTP 알림으로 n8n 웹훅에 넘깁니다. 순서 탐지는 앱의 Python 규칙이, 사건과 타임라인은 우리 사건 화면이 맡습니다. 유료 라이선스나 평가판을 쓸 수 있는지는 판단 보류 |
| **P1** | 질문 6: 세션 폐기와 대응 범위 | 앱 세션은 앱만 폐기할 수 있습니다(`session_version` 방식, docs/14 76행). Wazuh Active Response는 호스트에서 스크립트를 돌리는 방식입니다. 일정 시간 뒤 자동으로 되돌리는 방식을 쓰면 "승인된 복귀" 원칙과 충돌합니다([출처](https://documentation.wazuh.com/current/user-manual/capabilities/active-response/index.html)). pfSense에는 공식 REST API가 없습니다 | 자동 대응은 계정 단위 하나로 고정하고, 경로도 n8n → 앱 대응 API 하나만 둡니다. Wazuh 경로와 겹치지 않게 합니다. pfSense는 트래픽 경유·거부의 증거로만 씁니다. IP 차단은 수동으로 하거나 공방전 규칙이 확정된 뒤로 미룹니다 |
| **P2** | 질문 6: 배치 | (일반 지식) pfSense는 보통 Docker가 아닌 VM으로 배치합니다. Wazuh와 Graylog를 노트북 한 대에 같이 올리면 둘 다 검색 엔진을 쓰므로 메모리 부담이 큽니다. docs/14 56행대로 Docker 네트워크를 나누는 것만으로는 트래픽 경유를 증명할 수 없습니다 | 1~2일차에 "어느 PC·VM에서 무엇을 돌리는지, 메모리, 우회 시험" 표를 만듭니다. Wazuh가 필수로 확인되기 전에는 핵심 흐름 뒤에 둡니다 |
| **P2** | docs/17 5행 "업무 복귀 검증 **시스템**" | Defender에는 이미 enable user / release 버튼과 Policy status 표시가 있어, "예전에 조치했지만 지금은 해제됨"을 구분합니다([출처](https://learn.microsoft.com/en-us/defender-xdr/autoad-results)). Claroty에는 접근 승인·거부가 있습니다. 복귀를 통제하는 기능 자체는 새롭지 않습니다 | 차별점을 "자체 포털에서 조치 뒤 실제 접근 결과를 재시험해 증거로 남기는 검증 랩"으로 좁힙니다. "시스템" 대신 "검증 랩"을 씁니다 |
| **P2** | docs/17 23행 Defender 행 | 가장 중요한 참고 요소가 빠져 있습니다 | "조치 이력과 현재 효과 상태를 따로 표시"를 추가합니다. docs/14 85행의 "조치와 효과 검증의 별도 상태"와 정확히 대응합니다 |
| **P3** | docs/17 21·25·26행 데모 언급 | 이번 검토에서 해당 데모를 열지 않았거나 403이었습니다 | 각 행에 "안내 링크만 확인, 데모 안은 미확인"이라고 표시합니다 |

## 4. 우선 참고할 사이트 상위 3개

**질문 1: 범주별로 겹치는 범위와 다른 범위**

| 범주 | 사이트 | 우리와 겹치는 부분 | 다른 부분 |
| --- | --- | --- | --- |
| 업무 포털 | SAP | 협력사 로그인 후 업무·자료 목록 | 거래·청구 중심. 페이지도 403 |
| OT 원격 접근·특권 접근 관리 | Claroty, BeyondTrust | 협력사별 허용 자산, 승인, 세션 종료, 감사 | 원격 접속을 중계하는 게이트웨이. 우리는 웹 앱 세션과 자료 접근 권한 |
| 보안 사건 관리 | Defender, Graylog Investigations | 사건, 계정, 조치 상태, 해제 | 회사 전체 계정·단말을 다루는 운영 콘솔. Graylog Investigations는 유료 |
| 설비 시각화 | ThingsBoard | 연결 상태, 마지막 값, 추이 | 장치 관리 플랫폼. 우리는 수집이 끊기지 않았다는 증거만 필요 |

**상위 3개**

| 순위 | 사이트 | 가져올 요소 | 2주 범위에서 제외 |
| --- | --- | --- | --- |
| 1 | **Defender 사건 페이지** | 대상 계정의 상태 라벨, 조치 요약 카드, **조치 이력과 현재 효과 상태 분리**, 해제 버튼 옆의 "조사 완료 후 해제" 경고 | 사건 그래프, 고급 헌팅, 예측 차단, 기기 격리 |
| 2 | **Claroty xDome SA** | 협력사별 허용 라인·설비 목록, 승인·거부 패턴(복귀 승인에 적용), 감사 목록 | 세션 중계·녹화, 모바일 승인, 규제 매핑, 자격 증명 금고 |
| 3 | **ThingsBoard** | 설비 연결 상태, **마지막 수집 시각**, 추이 차트, 오프라인 알람 | 지도, 위젯 편집기, 장치 등록, 규칙 엔진 |

Graylog는 참고 사이트가 아니라 실제로 쓸 도구라서 순위에서 뺐습니다. BeyondTrust는 공식 문서를 다시 확인한 뒤에만 인용하는 것을 권합니다.

## 5. 2주 범위의 화면·역할·도구 책임과 공방전 증적

**화면별 책임**

| 화면(docs/14) | 역할 | 보여줄 것 | 보여주지 않을 것 |
| --- | --- | --- | --- |
| 로그인·재인증 | 전 역할 | 로그인, 잠금 안내, 복귀 후 재인증 | 잠금 사유 상세(공격자에게 정보가 됨) |
| 생산 현황 | 생산관리자는 전체 라인, 협력사는 배정 라인 | 설비 상태, 마지막 수집 시각, 추이 | 보안 사건 |
| 자료 조회 | 협력사, 생산관리자(권한 관리 포함) | 허용된 자료, 거부 응답 | 다른 라인이 있다는 사실 |
| 사건 상세(운영 경로) | 보안 담당자는 조치, 복구 담당자는 승인 | 근거 요약, 조치 이력과 효과 재시험 결과(분리), 정상 대조와 수집 순번, 복귀 점검(옛 세션·옛 비밀번호 거부, 새 인증 성공) | 로그 원문(Graylog 링크로 대신) |

**도구별 책임.** 사용 예정 기준이며 실제 연동은 검증하지 않았습니다.
- **pfSense**: 트래픽이 반드시 거쳐 가게 하고 허용·거부 로그를 남깁니다. 로그는 syslog로 Graylog에 보냅니다.
- **Graylog Open**: 로그를 수집·검색하고, 단일 조건 이벤트를 HTTP로 n8n에 알립니다.
- **n8n**: 앱 대응 API를 호출하고 재시험을 실행합니다. 재시도에는 같은 `operation_id`를 씁니다.
- **앱**: 순서 탐지, 사건, 계정 잠금과 세션 폐기, 복귀를 맡습니다.
- **Wazuh**: 호스트 신호와 파일 무결성 감시를 보조합니다. Active Response는 쓰지 않거나 앱 경로와 겹치지 않게 씁니다.
- **Kali**: 통제된 공격 입력을 만듭니다.
- **Docker**: 앱, 수집기, Graylog, n8n을 돌립니다. pfSense는 별도 VM으로 둡니다(일반 지식).

**공방전 증적.** 화면과 별도로 남깁니다.
1. pfSense를 거쳐 간 기록(출발지·목적지·시각)
2. 같은 요청 ID가 찍힌 앱 인증·인가 로그
3. Graylog가 받은 시각
4. 조치 기록(`operation_id`)과 그와 별개인 재시험 결과(HTTP 상태와 시각)
5. 같은 시간대의 정상 계정 성공 기록과 수집 순번 대조

사건 화면과 대응 API는 공방전에서 그 자체로 공격 대상이 됩니다. 운영 경로는 인증을 요구하고 관리망에서만 열리게 해야 합니다. 이 점은 규칙이 확정되지 않아도 지켜야 합니다.

**판단 보류**: 공격 허용 범위, 상대 팀 출발지가 NAT 때문에 IP 하나로 보이는지, 자동 IP 차단 허용 여부, 서비스 가용성 채점 여부, 증거 제출 형식.

## 6. 추천하는 한 문장 주제, 최소 시연 흐름, 남은 결정

**한 문장 주제(제안)**
"스마트팩토리 협력사 포털에서 의심 계정을 잠근 뒤, 실제 자료 접근이 끊겼는지와 정상 직원·가상 설비 수집이 계속되는지를 재시험하고, 승인된 재인증으로만 업무에 복귀시키는 대응 검증 랩."

**최소 시연 흐름**
1. 정상 생산관리자와 협력사 B가 자료를 조회하고, 가상 수집의 순번이 기록되고 있음을 보여 줍니다.
2. Kali에서 협력사 A 시험 계정으로 반복 실패 → 성공 → 담당 외 라인 조회를 실행합니다. 이 트래픽은 pfSense를 거쳐 갑니다.
3. 앱 규칙이 사건을 만들고, Graylog에서 같은 요청 ID를 검색해 보여 줍니다.
4. n8n이 A 계정을 잠그고 세션을 폐기합니다. 별도 재시험으로 기존 세션과 새 로그인이 모두 401/403으로 거부되는지 확인합니다.
5. 같은 시간대에 같은 IP를 쓰는 협력사 B의 요청이 성공하고 수집 순번에 누락이 없는지 대조합니다.
6. 복구 담당자가 승인한 뒤 비밀번호를 재설정합니다. 옛 비밀번호와 옛 세션은 거부되고, 새 인증과 허용 자료 조회는 성공해야 합니다.
7. 사건 상세 화면에서 조치, 효과, 복귀가 각각 따로 표시되고 증거 ID로 연결되는지 보여 줍니다.

권한 복구 충돌과 중복 재시도 시험은 최소 시연에서 빼고, 시간이 남으면 추가합니다.

**남은 결정**
- 공방전 규칙과 채점 기준
- Graylog 에디션
- Wazuh 필수 여부와 Active Response 사용 여부
- pfSense VM을 어디서 돌릴지와 PC별 메모리 배치
- 복구 담당자를 별도 계정으로 둘지
- 평가 필수 요건
- 팀 채택 여부

이 응답은 문서와 공개 페이지를 읽고 판단한 검토입니다. 구현, 제품 연동, 공방전은 하지 않았고, 팀이 이 주제를 채택했다는 뜻도 아닙니다.
