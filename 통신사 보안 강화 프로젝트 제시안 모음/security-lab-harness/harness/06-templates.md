# 06. 템플릿

## claim (`.claims/INC-0X.claim`)

```yaml
ticket: INC-01
role: host
owner: 홍길동
agent: claude-code        # 사람이 직접 하면 none
started: 2026-10-20 10:00
branch: host/INC-01-packet-socket-rule
paths:
  - detection/wazuh/rules/inc01_rules.xml
  - detection/wazuh/agent/inc01_localfile.xml
  - scenarios/INC-01/
  - tickets/INC-01/
summary: 패킷 소켓, 삭제된 실행 파일 탐지 규칙 추가
```

## worklog 항목 (`tickets/INC-0X/worklog.md` 끝에 추가)

```markdown
## 2026-10-20 14:10 | owner: 홍길동 | agent: claude-code
- 바꾼 것: detection/wazuh/rules/inc01_rules.xml (규칙 100110, 100111 추가)
- 확인한 것: web-01에서 B·C 재현 → 대시보드에서 100110, 100111 알림 확인
- 못 한 것: 주기를 60초로 줄인 뒤 CPU 사용량은 측정 못 함
```

## 인시던트 티켓 (`tickets/INC-0X/ticket.md`)

```
티켓 ID     : INC-0X
제목        :
근거 사례   :
탐지 시각   :
탐지 경로   : (NIDS / HIDS / 서비스 로그, 규칙 ID)
심각도      : (치명 / 높음 / 중간 / 낮음)
영향 자산   :
ATT&CK      :
타임라인    : 탐지 → 분류 → 격리 → 증거 보존 → 제거 → 복구
증거 보존   : (무엇을, 어디에 저장했는가)
조치 내용   :
결과        : (보강 전후 비교, SECURE_MODE 0/1 비교)
상태        : (열림 / 대응 중 / 종결)
교훈        :
```

## PR 본문

```markdown
## 티켓
INC-0X

## 바꾼 것
- 

## 확인한 것 (실행한 명령과 결과)
- 

## 못 한 것 / 확인 못 한 것
- 

## 체크리스트
- [ ] claim의 paths 밖 파일을 고치지 않았다
- [ ] 번호는 03-id-registry.md 대역 안에서만 썼고, 사용 기록에 추가했다
- [ ] gitleaks 통과 (LAB-FAKE- 제외)
- [ ] 대상 주소는 모두 10.10.10.0/24
- [ ] worklog에 항목을 추가했다
```

## 시나리오 스크립트 머리말 (`scenarios/INC-0X/reproduce.sh`)

```bash
#!/usr/bin/env bash
# INC-0X 재현 스크립트 — 프로젝트망 전용
# 근거 사례:
# 실행 위치: (VM 이름)
# 정리: ./cleanup.sh
set -euo pipefail
TARGET="${TARGET:-lb-01}"
TARGET_IP=$(getent hosts "$TARGET" | awk '{print $1}')
case "$TARGET_IP" in 10.10.10.*) ;; *) echo "프로젝트망 밖 대상: $TARGET_IP"; exit 1;; esac
```

## Wazuh 규칙 파일 머리말 (`detection/wazuh/rules/inc0X_rules.xml`)

```xml
<!-- INC-0X | 대역 1001X0–1001X9 | 주인: host -->
<group name="inc0X,">
</group>
```

## Suricata 규칙 형식 (`detection/suricata/inc0X.rules`)

```
# INC-0X | SID 10000X00–10000X99 | 주인: net
alert http any any -> $HOME_NET 80 (msg:"INC-0X: <설명>"; ...; sid:10000X01; rev:1;)
```
