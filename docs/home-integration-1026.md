# 10/26 집 작업 · C/D 연결 수정과 학원 인수

> 10/27 갱신: 새 회차409 정책은 [최신 통합 후보](home-integration-1027.md)의 조치 전 detected 새 티켓 예약으로 대체됐다. 아래 수치·버전·정책은 10/26 작업 이력이다.

상태: **집 브랜치 구현·격리 검증 후보. 학원 미배포, 실제 n8n 엔진·장비 효과·원복 미시험.**
브랜치 `codex/home-handoff-1023`에서 main `fa2be3a`, C #62 `5d28fc0`, D #63 `d14280b`까지의 후보를 통합했다. 다른 담당의 원격 브랜치·PR은 수정하지 않았다. A #65와 B #64는 이번 수정 코드에 병합하지 않았다.

## 실제 변경

| 문제 | 집 브랜치의 처리 | 운영에서 확인할 것 |
| --- | --- | --- |
| 다른 묶음·자리의 같은 IP 차단 누락 | C 인증 `/active`가 자산·경로·적용 동작·대상 4개로 전체 live 활성 조치를 반환. 닫힌 티켓의 미해제 조치도 포함 | 자산 식별과 모든 조치 경로의 기록 참여 |
| 해제 뒤 재차단 중복·부분 원복을 전체 원복으로 표시 | 현재 활성 줄로 중복/효과/해제 판정. 마지막 활성 조치가 해제돼야 restored. restored 새 이벤트/적용은 409로 보류 | 사람이 원복 확인·기존 티켓 close 후 새 이벤트/새 티켓 시작. D는 대상 호출 전 상태 분기 |
| via 손실·fw_block 우회·S7 대상 혼동 | D가 via를 보존·비교. PF 적용은 block, 해제 기록은 unblock. C는 기존 pfsense fw_block 이력을 block 자원으로 읽되 원문을 보존. S7 group_key와 file_key 대상 분리 | C/D 같은 수정 버전 배치. 기존 mixed 이력 검토 |
| 조회 실패를 없음/진행으로 처리 | D 응답 형태 검증과 실패 보류. detected/중간 기록 실패·terminal 응답이면 다음 대상 호출 전에 Code 노드가 중단 | 실제 n8n 오류 표시·HTTP 노드 반환 봉투·중단 후 수동 복구 |
| 다른 자리만 보는 해제 보류 | D가 각 집행 경로별 `/active`를 순서대로 대조. 자기 ticket_id 외의 티켓, 같은 자리의 다른 티켓, 다른 봇, 닫힌 미해제 조치를 보류 | 조회→집행 사이 경쟁은 별개. 실제 모든 호출자의 직렬화·소유권 보장 필요 |
| 탐지/전달 시각 혼합 | 입력 detected_at(Graylog 생성)을 그대로 기록, 없거나 잘못된 날짜면 null. received_at은 n8n 입력 시각 | Graylog 실제 알림에 탐지 시각·조건 충족 시각 매핑 |
| 빠른 403을 S12 회복으로 인정 | 200 및 포털 health 본문 success=true/data.status=ok와 기준선 확인. VPN health 관측만으로 실제 effect를 기록하지 않음 | 외부 정상 출발지 경로·공격 출발지 차단·회복의 독립 증거 |

기존 [10/24 패치](../patches/ticket-store-pr55/README.md)의 잔여 수정을 C #62 위에서 통합했다. 고정 PR55 패치 파일/과거 증적은 이력으로 보존한다. 이 브랜치에는 서비스 원본이 있으므로 같은 패치를 다시 적용하지 않는다.

## 생성·검증

프로젝트 `.venv`의 Python과 Node.js를 사용한다. `.venv`가 없을 때만 `python tools/bootstrap.py`로 준비한다.

```powershell
python tools/build_n8n_workflows.py
python tools/build_n8n_workflows.py --check
python tools/build_ticket_guard.py --check
python tools/sync_ai_assets.py --check
python tools/team.py validate
python -m pytest -q
```

생성 원본은 `tools/gen_n8n_workflows.py`, `gen_n8n_cases.py`, `gen_n8n_stage2.py`와 최종 교정 원본 `tools/n8n_hardening.py`다. **기본 생성기 한 개만 실행하면 교정이 빠지므로 build_n8n_workflows.py를 사용한다.** `--check`는 임시 폴더로 생성해 14개 내보내기를 바이트 대조하고 저장소 파일을 덮어쓰지 않는다. 기존 haedam-00과 집 haedam-16은 각각 원본/전용 생성기를 유지한다.

`tests/test_n8n_workflow_integration.py`는 실제 생성된 Code 코드를 Node에서 실행하고 C Flask test client/임시 SQLite 응답을 넣는다. 합성 S1 적용·효과·해제·새 주기 보류, 다른 계정/같은 자리/닫힌 티켓의 자원 보류, 오류·형식·시각·회복 경계를 확인한다. 대상은 합성 상태이며 **n8n 엔진·네트워크·학원 장비를 실행한 시험이 아니다.** Node가 없으면 해당 코드 실행 검사는 skip으로 나타나므로 건수를 완료로 세지 않는다.

## 배치 전 주의할 차이

- 학원 C의 기록된 운영 버전은 `2ffc1e4`다. #62만 재빌드하면 이 집 수정의 `/active`·새 주기 조건이 생기지 않는다. C가 diff·계약·회귀를 검토한 뒤 정확한 소스 버전으로 별도 시험 DB에서 재빌드해야 한다.
- HTTP 키 두 개(포털/C)는 별도 n8n 자격 증명으로 연결한다. 키를 JSON·프롬프트·일지에 넣지 않는다. 8088은 기존 VPN 경로를 재사용하고 8089 대시보드는 C loopback을 유지한다. 실제 규칙 적용은 이 집 작업 범위가 아니다.
- 모든 내보내기는 `active:false`, 동작 설정은 `dry_run:true`다. haedam-50에는 `live_release_enabled:false`도 있다. 단순 dry_run 해제로 실해제를 허용하지 않는다. 승인자 문자열은 인증이 아니며, 소유자 인증·동시 적용/해제 직렬화·독립 원복 확인을 인수하기 전 실제 해제 경로를 열지 않는다.
- `/active`는 읽기 스냅샷이며 잠금/원복 허가가 아니다. 집 ResourceGate·공유 제어 API 후보와 실제 D 워크플로의 운영 연결은 이번 작업에서 구현하지 않았다.
- 이미 restored이지만 활성 줄이 남은 과거 티켓은 D가 불일치로 보류한다. DB/영수증을 지우거나 키를 바꿔 자동 재시도하지 말고 실제 대상과 기록을 대조한다.
- PF/Wazuh 실제 실행 노드는 여전히 자리표시다. B #64 도구의 채택·전용 SSH 경계와 C 117 연결은 별도다. 실제 대상 성공 뒤 C 기록이 실패하면 대상 호출을 반복하지 않고 원래 요청/현재 상태부터 대조한다.
- n8n 저장소 HTTP의 기본 노드 재시도(3회)를 끄고, 명시적 5xx/응답 없음 분기의 같은 키·본문 1회 재시도만 유지했다. 4xx·형식 오류는 재시도하지 않는다.

## 다음 학원 작업

[S1 단독 시험 카드](school-s1-card-1026.md)의 빈 조건을 채운 뒤 실행한다. 먼저 C/D의 오후 실제 연결 결과를 최신 현황과 맞추고, C/D 수정 채택·버전·격리 연결 검사를 끝낸다. S1 한 번의 효과/정상 사용자/원복을 확인한 뒤 PF 단독·S10 결합, S7 수동 복구, S12 외부 기준선으로 확장한다.

학원 현황은 C #59·A #66·B #64의 담당 기록을 대조했다. 15:20 S10은 B 문서상 보강 전 #1이므로 해당 구간 티켓0을 보강 후 실패로 바꾸지 않는다. 학원 절대 경로의 원본 증적은 여기서 열람하지 못했다.
