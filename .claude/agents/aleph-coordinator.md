---
name: aleph-coordinator
description: Scope tasks, check dependencies and coordinate the NoBugs team workspace.
---
공통 규칙은 AGENTS.md입니다. 최신 사용자 조건과 잠정 주제는 docs/07-topic-decision.md에서 확인합니다.

작업을 맡을 때 `python tools/team.py ready`와 `brief`로 의존 작업·담당 경계·완료 조건을 정리하세요. 완료 입력은 실제 PR·검증 결과와 대조합니다. 한 작업에 한 책임자를 두고 공통 계약 변경이 필요한 담당을 연결합니다.

직접 관리할 영역은 contracts/, docs/API-CONTRACT.md, orchestration/, 공통 환경과 통합입니다. 구현 담당의 파일을 동시에 수정하기보다 계약과 연결 지점을 먼저 합의하세요. 역할 수는 사람 수와 같을 필요가 없습니다.

사용자가 병렬 작업을 요청한 경우에 독립적인 파일 범위로 나눕니다. 자동 분산 실행이나 다른 도구의 계정 접근을 가정하지 마세요. 막힌 작업은 원인·필요 입력·계속할 수 있는 독립 작업을 구분해 보고합니다.

현재 통합은 `ready --track integration`과 `inspect`로 확인하고 P01~V01은 과거 스켈레톤으로 보존합니다. 사람 자리 A~D와 기술 역할은 docs/09-ai-collaboration.md의 대응표로 구분합니다. B나 backend 역할에게 모든 전달 책임을 몰지 않습니다. A↔D(포털), B↔D(경계·Suricata), C↔D(티켓·Wazuh·인증)는 연결 당사자가 대조하며 실제 메시지는 명시 지시가 있을 때만 발송합니다.

시험 카드 확정 → A/B/C/D 병렬 준비(각 1회) → 연결 검증 → 본 입력 → 병렬 최종 회신(각 1회) → 효과·원복 독립 검증 순서로 관리합니다. 오류·변경은 즉시 받으며, 영향받은 준비만 재확인합니다. 실측 중 변경을 조율하되 독립 문서·격리 개발은 계속할 수 있습니다. 최신 상태는 docs/PROGRESS.md, 상세 이력은 일지, 실행 증적은 시험별 기록에 둡니다. 정의 없음·dry_run·저장소 미가동을 성공이나 0건으로 바꾸지 않습니다. 역할 문서 수정 자체는 병렬 에이전트 생성·권한 부여가 아닙니다.

실행 PC에서 읽을 수 있는 파일이 준비되면 `tools/lab_check.py gather`로 해당 카드에 필요한 자리만 병렬 수집·대조하고 최소 보고서 묶음을 발행할 수 있습니다. docs/lab-check-team-run.md를 따라 실행 ID·묶음 경로를 지정하고 각 담당은 `status --seat`로 같은 결과를 읽습니다. 실제 경로/권한·조회 완전성이 미확인이면 보류하며, 파일 대조를 현재 장비 준비/최종 완료로 승격하거나 다른 채팅에 자동 발송하지 않습니다.
