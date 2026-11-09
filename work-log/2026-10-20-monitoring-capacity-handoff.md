# 2026-10-20 관제 가용성 검증 인수인계

- 작업 ID·역할: H05 검증 계획 보강 / 김명준 + Codex, 조율·문서.
- 브랜치: `codex/monitoring-capacity-plan-1020`.
- 작업 시작 커밋: `f42de82281ecbdb2cedeb322c038a6d7e66d77ca`. 계약 PR #19의 변경 위에서 문서만 추가했다. 새 PR은 생성하지 않았다.
- 이 인수인계가 포함된 커밋은 `git log -1 --format="%H %s" -- work-log/2026-10-20-monitoring-capacity-handoff.md`로 확인한다.
- 상태: 문서 보강 완료, 실제 관제 처리량·복구 시험 미실행.

## 변경 내용

- [관제 처리량·가용성·복구 검증 계획](../docs/haedam/MONITORING-CAPACITY-PLAN.md): Kafka 설명, 실제 RPS/EPS·검색 지연·누락·적체·자원·정상 시민 영향·복구 시간, 시험 순서·중단 기준·결과 양식.
- [독립 체크리스트](../docs/haedam/REVIEW-CHECKLIST.md)와 [H05 작업 카드](../docs/haedam/TASKS.md)에서 새 계획으로 연결.
- 계약·이벤트·API·포털 코드·방화벽·컨테이너 설정은 변경하지 않았다. Kafka도 설치하지 않았다.

## 학원에서 시작

기존 capstone 저장소에서 미커밋 작업을 확인한 뒤 실행한다. 변경이 있으면 먼저 별도 보존·커밋하고 브랜치를 전환한다. 강제 초기화는 하지 않는다.

```powershell
git status --short --branch
git fetch origin
git switch codex/monitoring-capacity-plan-1020
git pull --ff-only
git log -1 --oneline
```

로컬 브랜치가 없다면 switch 줄 대신 `git switch --track origin/codex/monitoring-capacity-plan-1020`을 사용한다. 브랜치가 원격과 갈라져 pull이 실패하면 중단하고 차이를 확인한다.

다음 세션 시작 문구:

> work-log/2026-10-20-monitoring-capacity-handoff.md와 docs/haedam/MONITORING-CAPACITY-PLAN.md를 읽고 이어서 하자. Kafka 추가보다 현재 관제의 처리량과 복구를 먼저 검증한다. 실제 두 PC 배포·수집 연결과 자원을 확인하고, 준비된 항목만 측정하며 미연결 항목은 미실행으로 남겨줘.

## 실제 확인과 남은 작업

- 실행 확인: 문서 UTF-8 읽기, 코드 펜스 짝, 로컬 링크 대상 존재, 측정·중단·미실행 표기, `git diff --check`. 이번 문서 변경으로 앱 회귀 시험이나 실제 부하 시험을 실행하지 않았다.
- 다음 첫 작업: 관제 PC의 Graylog/OpenSearch/MongoDB/Wazuh/n8n 실제 버전·자원·기동 상태와 포털 GELF 수신을 소량 확인한다. 확인 후 정상 업무 기준선과 수치 판정 기준을 기록하고 단계 부하 시험을 준비한다.
- 현재 포털 GELF는 UDP이며 수신 확인·자동 재전송이 없다. JSONL 보존과 Graylog 수신·재수신을 구분한다. 설치·설정·보강 후보가 실제 적용됐다고 간주하지 않는다.
- A 포털, B 망·pfSense, C Wazuh·호스트, D Graylog·n8n 연결 담당과 실측 범위를 조율하고 독립 재현자를 배정한다. 문서의 시간·배수·중단 기준 후보는 실행 전에 장비와 팀 기준으로 확정한다.
- 선행 계약 리뷰는 [capstone #19](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/19), 포털 리뷰는 [backend #2](https://github.com/NoBugs-Aleph/haedam-portal-backend/pull/2)를 확인한다. 이전 리뷰 결과로 최신 HEAD의 수정 완료를 판단하지 않는다.
- 미검증: 실제 두 PC 수집·탐지·자동 대응, 처리 한계, 로그 유실·복구, 정상 시민 영향, 제안한 방화벽·보존·외부 관측 설정. 로컬 기획서 검토 브랜치의 존재나 학원 PC 동기화도 이 푸시만으로 보장하지 않는다.
