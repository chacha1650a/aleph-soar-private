---
name: aleph-contract-change
description: Change the shared API, event or incident contract and its consuming examples in the NoBugs project.
---
API 입력·출력이나 공통 이벤트·사건 필드를 바꿀 때 사용합니다.

[API 계약](../../../docs/API-CONTRACT.md)의 구현 상태와 `contracts/`의 스키마·예시를 확인합니다. 기존 소비자에게 미치는 영향을 설명하고, 필요한 계약·예시·구현·검증을 같은 작업에 맞춥니다. 필드 제거·의미 변경은 조율 담당에게 연결해 관련 작업의 기준을 함께 갱신합니다.

`python -m pytest tests/test_contracts.py -q`를 실행합니다. 이는 스키마와 예시의 일관성 검사이며, 실제 API·시간 순서 상관·대응 동작은 해당 구현 테스트로 별도 확인합니다. 미구현 경로를 구현된 것처럼 문서화하지 마세요.

공통 계약이 실제로 바뀔 때만 이 절차를 적용합니다. 준비·회신 양식이나 역할 문구 변경만으로 API 변경을 만들지 않습니다. A↔D 포털 이벤트/대응, B↔D 경계·Suricata, C↔D 티켓/Wazuh 소비자를 확인하고 측정 중 변경은 영향받은 버전·준비 조건만 다시 맞춥니다. 원문 필드와 정규화 필드, 미정의/null과 조회 0건의 의미를 보존합니다.
