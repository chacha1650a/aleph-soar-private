---
name: aleph-dashboard
description: Build the incident timeline and response-state interface from the shared view contract.
---
AGENTS.md와 작업 brief, docs/API-CONTRACT.md를 읽습니다. 기본 작업 영역은 src/aleph_soar/templates/, src/aleph_soar/static/와 관련 화면 검증입니다.

contracts/examples/의 합성 데이터를 계약 예시로 활용할 수 있습니다. 실제 API가 없는 화면에는 샘플·미연결 상태를 표시하고 탐지 완료 수치나 대응 성공을 꾸며내지 않습니다.

사건의 타임라인·의심 근거·원본 이벤트 연결·대응 결과·원복 결과를 구분해 보여주세요. 실패·빈 결과·로딩 상태와 좁은 화면에서의 사용도 확인합니다. API 경로와 스키마를 임의로 바꾸지 말고 계약 담당과 맞춥니다.

사용자에게 보여줄 변화, 실제 확인한 화면과 아직 미연결인 기능을 인수인계합니다.

사람 C의 보안 대시보드/티켓 책임과 기술 역할을 구분합니다(docs/09-ai-collaboration.md). 현재 티켓 구현은 PR #50 위의 #55 후보이며 이 브랜치에 services/ticket-store/가 있다고 가정하지 않습니다. 포털 프론트는 별도 NoBugs-Aleph/haedam-portal-frontend의 src/이며 기존 templates/static 범위는 과거 스켈레톤입니다. brief에 실제 저장소·파일 소유자·제공 API/화면 인터페이스를 명시합니다.

준비 회신에는 가동·DB/볼륨·API 인증·조회 범위를, 최종 회신에는 시험 ID/시간창·티켓 키·생성/중복/효과 기록을 각 1회 적습니다. 저장소 미가동과 가동 중 0건, 샘플 화면과 실제 D n8n 연결을 구분합니다. C↔D 직접 연결 결과와 미검증 조건을 넘깁니다.
