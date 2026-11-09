# S12 실제 서비스 판정과 정상 사용자 경로 비교

11/03 소스 보강 후보다. 실제 게시·기준 측정·부하·차단·해제를 수행한 결과가 아니다. #125 최신 `0e620a5` 위의 별도 변경이며 #125 병합을 대신하지 않는다.

## health 판정

기존3414ms는 `/login` 측정에서 얻었고, D→`/api/v1/health`의 독립 기준이 아니다. 기준이 없으면 `baseline_ms`와 `baseline_source`가 null이라 `no_baseline/no_action`으로 멈춘다. timeout은5000ms로 설정했으며, 측정 후 고정할 기준보다 반드시 커야 한다.5000ms는 새 기준선 실측값이 아니다.

**11/03 고정값:** `baseline_ms=2000`, `baseline_source=S12-20261103-D-HEALTH-BASELINE01`. 근거는 D(10.250.0.100)→`http://10.250.0.2:5000/api/v1/health`, 19:32:16.374~19:37:16.372 KST, 2초 간격·timeout 5초·150회 전부 200(A 포털 원본 150건 일치), median 38.8·p95 293.8·p99 1679.8·max 1759.1ms, CSV sha256 `3f9634fd…dd39`. 계산식 `max(p95×3, p95+300)`=881.4ms는 같은 정상 구간에서 19:35:46·48·50 세 번 연속 초과(1028.3·1679.8·882.0ms)라 K=3에서 오탐이 나므로, 정상 최댓값 위인 2000ms를 D가 채택했다. 판정: 2초 간격 K=3 표본이 모두 장애 후보(2000ms 초과 성공·timeout 5000ms·연결 오류·5xx)일 때만 `exceeded`. 부하 때 health 지연이 2000ms를 넘는지는 아직 재지 않았다.

`tools/s12_health.py`를 탐지와 회복 노드가 함께 사용한다. 설정 검사는 표본 요청 전에 이뤄진다. 기준/근거 ID·timeout·K·간격이 잘못됐으면 `invalid_health_config/no_action`이다.

| 표본 | 분류 | 장애 후보 여부 |
| --- | --- | --- |
| 200, success=true, data.status=ok, 지연≤기준 | healthy | 아니오 |
| 같은 정상 응답, 지연>기준 | slow_success | 예 |
| 제한시간 초과 | timeout | 예 |
| 연결·전송 오류 | network_error | 예 |
| HTTP5xx | server_error | 예 |
| 4xx·redirect·상태 누락 | unexpected_status | 미결정 |
| 200이나 정상 응답 계약 아님/JSON 파싱 실패 | invalid_body | 미결정 |

K개 표본이 모두 장애 후보여야 `exceeded`로 간다. 모두 정상일 때만 `within_baseline/no_action`, 혼재·계약 오류는 `inconclusive/no_action`이다. 보호 출발지의 `protected_source`는 측정 전 별도 안전장치다. raw 오류 메시지·본문·인증정보 대신 고정 분류와 상태·시각·응답시간만 저장한다.

회복도 같은 상태/본문/지연 기준을 사용하고, K회 연속 정상이어야 한다. 관측 종료 시각을 넘길 수 있는 새 요청은 시작하지 않는다. D VPN health 회복은 `scope=vpn_health_only`, `effect_verified=null`, `normal_user_path_verified=null`로 남긴다. 실제 조치의 효과 완료를 이 결과만으로 티켓에 쓰지 않는다.

## 독립 기준 준비

준비된 별도 회차에서 D→health 경로를 평상시에 측정한다. 측정 URL·실제 수신 출발지·배포 버전·시간창과 응답 계약 정상 여부를 대조하고, `/login`이나 공격 중 자료를 health 기준으로 재사용하지 않는다.

기존 `tools/s12_probe.py`와 `tools/s12_baseline_calc.py`를 사용할 수 있다. probe는 기존 CSV 형식을 유지하고 `파일.csv.meta.json`을 추가한다. 여기에 URL·주기·timeout·요청한 길이·시작/종료·요청 수·CSV SHA256을 저장한다. URL의 자격 증명/쿼리는 저장하지 않고 redacted로 표시한다. 기존 CSV나 메타파일은 덮어쓰지 않는다.

기준선 계산 결과의 `exceed_threshold_ms`는 후보값이다. 독립 health 경로인지, 실패/지연 표본과 관측 길이가 적절한지 검토한 뒤 CFG의 `baseline_ms`와 근거 ID `baseline_source`를 소스에서 고정한다. `baseline_ms < health_timeout_ms`가 성립하지 않으면 반입하지 않는다. 입력 본문으로 실제 기준을 활성화하지 않는다. 기존 dry-run 전용 `test_baseline_ms`는 `baseline_source=synthetic_override`로 명시돼 실측 근거와 구분된다.

## 정상 사용자 네 구간 비교

`tools/s12_compare_phases.py`는 기존 C의 엄격한 CSV 읽기 함수를 재사용하는 **오프라인 보고 도구**다. C API·DB·기존 before/after 등록 계약은 바꾸지 않는다. 운영 저장/티켓 상태 변경/자동 효과 보고도 하지 않는다.

네 구간은 `before_block`(차단 전), `after_block`(차단 직후), `recovery`(회복 관측), `after_release`(수동 해제 후)다. 같은 정상 출발지·URL·주기·timeout·요청 측정 길이를 유지한다. 실제 구간이 없으면 null로 남기며 정상 미차단 시험에 가상의 차단 구간을 만들지 않는다.

정상 사용자 출발지에서 `/login` 등 합의한 동일 경로를 probe로 측정하고 CSV와 sidecar를 모은다. 아래 로컬 메타파일을 작성한 뒤 실행한다. 수치는 합의할 예시 자리이며 실제 실행 지시/실측 결과가 아니다. `baseline_ms`는 **정상 사용자 경로의 별도 기준**을 채운다.

```json
{
  "run_id": "S12-YYYYMMDD-COMPARE01",
  "normal_source": "203.0.113.100",
  "attack_source": "203.0.113.41",
  "target": "http://10.250.0.2:5000/login",
  "expected_status": 200,
  "baseline_ms": null,
  "interval_seconds": 2,
  "timeout_seconds": 5,
  "duration_seconds": 300,
  "k": 3,
  "phases": {
    "before_block": {"csv": "before.csv", "load_running": true},
    "after_block": {"csv": "blocked.csv", "load_running": true},
    "recovery": {"csv": "recovery.csv", "load_running": true},
    "after_release": {"csv": "released.csv", "load_running": false}
  }
}
```

```powershell
python tools/s12_compare_phases.py <측정폴더>/comparison.json
```

비교 도구는 CSV의 출발지·해시·시각/구간과 probe sidecar의 실제 요청 설정을 대조한다. 공격 출발지나 D VPN 출발지를 정상 사용자로 쓰지 않는다. 다른 URL·timeout·주기·길이, 같은 CSV 재사용, 역순·겹친 구간은 거절한다. 구간/메타파일 누락·짧은 관측·주기 초과는 비교 미완료/null로 남긴다. 정상 사용자403은 회복 실패다.

출력에는 네 구간의 성공률·실패 수·상태 코드 분포·지연 p95·표본 분류·연속 장애·마지막 K회 정상·원본 해시가 있다. 실제 장애가 없던 정상 경로를 차단으로 회복시켰다고 표시하지 않는다. 부하 지속 여부는 담당자의 선언이며 probe가 직접 검증하지 못한다. 부하 종료 뒤 정상화는 부하 지속 중 회복으로 표시하지 않는다.

HTTP200으로 로그인 성공·민원 업무 전체 성공을 입증할 수 없으므로 `business_verified`, `effect_verified`, `causal_effect_verified`는 null이다. A의 업무 결과와 B 부하 시작/종료 기록을 같은 회차/구간으로 별도 대조한다. 해제 후 공격 출발지의 재접속200과 C의 해당 자원 활성 조치0도 별도 대조해야 하며, 정상 사용자 측정만으로 해제 완료를 선언하지 않는다. C 대시보드 등록이 필요하면 기존 [전후 비교 절차](s12-dashboard-comparison.md)를 사용하되, 네 구간 보고서가 기존2구간 DB 스키마에 자동 등록된 것으로 표시하지 않는다.

## 발표 설명

“요청 수는 탐지 후보 조건입니다. 서비스 상태가 기준 안이면 no_action으로 정상 이용을 유지합니다. 반복 지연·실패를 확인한 회차만 대응 대상으로 삼고, 효과는 공격자403과 별도로 정상 사용자의 접속·응답 회복과 해제 후 재접속까지 대조합니다.”

실제 입력 전 독립 기준·A/B의 부하 상한/시간창·정상 업무 경로·수동 해제 담당·실제 게시 CFG/자격 증명·C 저장·15/17 실행 보존을 확정해야 한다. 소스 검증 통과는 이 현장 확인을 대신하지 않는다.
