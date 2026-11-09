# S7 N=5 반복·경계 시험 계획 (설계만, 2026-10-30)

S7 인수 메모 4번. 10/29 수동 시험(`docs/capstone/evidence/S07/2026-10-29-manual-ar-fim-compare.md`)의 한계 "각 시험은 1회씩"을 보강하는 계획입니다. **아직 실행하지 않았습니다.** 실행에는 A(VM)·B(일정)·D(Graylog 확인)와 시간 조율, 사용자 승인이 필요합니다(S7 인수 메모 "지킬 것").

## 범위

`lab/s7/graylog/s7-rule-spec.md`의 판정 표 기준으로 두 그룹으로 나눕니다.

| 그룹 | 대상 사례 | 반복 | 쓰는 도구 |
| --- | --- | --- | --- |
| 양성(발동 기대) | #2 새 파일 생성 → 10분 안 접근 | N=5 | `s7_repeat_tamper.py new ...` |
| 양성(발동 기대) | #5 기존 파일 변경 → 접근 | N=5 | `s7_repeat_tamper.py modify ...` |
| 경계(1회, 반복 아님) | #7 변경만(접근 없음) | 1 | `s7_tamper_sim.py modify` (access 생략) |
| 경계(1회) | #8 접근만(변경 없음) | 1 | 변경 없이 기존 파일 GET만(이 저장소 도구 밖, `curl`) |
| 경계(1회) | #9 변경 후 10분 넘겨 접근 | 1 | `s7_tamper_sim.py modify` 뒤 10분 넘겨 별도 GET |

#7·#8·#9는 "발동 안 함"을 확인하는 사례라 반복이 통계적으로 의미가 적어 1회로 둡니다(N=5는 인수 메모 표현을 그대로 따름). 반복이 필요하다고 판단되면 그때 `--count`를 올립니다.

## 양성 그룹 실행 (예시, 아직 실행 안 함)

```bash
python lab/s7/attack/s7_repeat_tamper.py new \
  --run-id-prefix s7-repeat-1030-new --count 5 --gap-seconds 60 \
  --host haedam@10.250.0.2 \
  --access-url-template "http://10.250.0.2:5000/zz_s7_{run_id}.html" --source 203.0.113.31 \
  --execute \
  --label-prefix s7-repeat-1030 --log evidence-repeat.jsonl --summary-csv evidence-repeat-summary.csv
```

- `--gap-seconds 60`: #2는 "10분 안 접근"이 조건이라 반복 사이 간격은 10분보다 훨씬 짧게 둬서, 각 회차가 FIM·Graylog 시각으로 서로 구분되기만 하면 됩니다(60초면 충분하다고 보지만, 실행 전 D와 확인).
- modify(#5)는 같은 패턴으로 `--target index.html` 지정, 매회 복구(`s7_restore.py restore`)를 사이에 끼워 기준본 상태로 되돌린 뒤 다음 회차를 시작해야 합니다. 이 복구 호출은 `s7_repeat_tamper.py`가 하지 않으므로, 실행 때는 반복마다 수동 또는 별도 스크립트로 `restore` 뒤 `verify ok`를 확인하고 넘어갑니다.

## 기록할 것 (회차마다)

- `s7_repeat_tamper.py --log`가 남기는 JSON 줄(ssh 결과·접근 결과)과 `--summary-csv`의 시각·run_id·rc
- C manager FIM 경보(554 또는 550) 시각·개수
- D Graylog 수신 시각·필드(`file_key`, `signal_kind`, 중복 여부)
- (modify만) 회차 사이 `verify ok` 확인

## 집계

5회 끝나면 발동 비율(5/5 기대), FIM→Graylog 수신 지연의 분포(평균·최대, 10/29처럼 참고값으로만), 중복·누락 유무를 표로 정리합니다. 10/29 1회 결과와 같은 경향인지만 비교하고, 서로 다른 시계라는 제약은 그대로 유지합니다.

## 아직 안 한 것 / 미정

- 실제 실행(권한·일정 조율 전).
- modify 회차 사이 자동 복구(현재는 수동).
- 경계 사례(#7~#9) 1회 실행과 결과 기록.
- 이 계획을 10/29 문서처럼 증적 폴더에 결과로 옮기는 일(실행 후).
