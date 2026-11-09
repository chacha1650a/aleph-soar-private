# S7 공격 재현 (`s7_tamper_sim.py`)

Kali(203.0.113.31~39, 위치는 B 확인)에서 포털 VM(A)의 웹 루트에 무해한 `zz_` 변경을 ssh로 만들고, 선택적으로 접근(GET)까지 한 번에 하는 스크립트입니다. 복구 쪽 `lab/s7/restore/s7_restore.py`의 공격측 대응물입니다.

## 두 동작

- `new`: `<web_root>/zz_s7_<run-id>.html` 새 파일 생성 → FIM 554 기대
- `modify`: 기준본 목록(`baseline.sha256`)에 있는 기존 파일에 주석 한 줄 추가(기본 `index.html`) → FIM 550 기대. `--target`이 원격 기준본 목록에 없으면 거부합니다.

## 안전장치

- **기본은 dry-run**입니다. `--execute`를 줘야 실제로 ssh 명령이 나갑니다. dry-run은 보낼 ssh 명령 문자열만 보여 줍니다.
- `new`의 파일명은 항상 `zz_s7_<run-id>.html`이며 호출자가 이름을 고를 수 없습니다.
- `--target`은 웹 루트 기준 상대 경로만 받고 `..`·절대경로는 스크립트 단계에서 바로 거부합니다(원격 기준본 대조 전에).
- `--run-id`는 `s7_restore.py`와 같은 문자 집합(영문·숫자·`.`·`_`·`-`, 1~64자)만 허용합니다.
- 비밀값은 읽지도 저장하지도 않습니다. 키가 필요하면 `--ssh-opt`로 OpenSSH 옵션을 그대로 넘깁니다(예: `--ssh-opt -i --ssh-opt /path/key`).
- `--access-url`을 주면 `tools/s12_probe.py`와 같은 방식으로 `--source`에 소켓을 바인딩해 포털에 공격망 IP로 접근 기록을 남깁니다.
- 매 실행(dry-run 포함, 성공·실패 모두)을 `--log`에 JSON 한 줄로 남깁니다.

## 예시

```bash
# 1) 새 파일 생성, dry-run으로 먼저 확인
python s7_tamper_sim.py new --run-id ar-1030-01 --host haedam@10.250.0.2 \
  --label s7-attack-1030-01 --log evidence.jsonl

# 2) 확인 후 실제 실행 + 10분 내 접근까지
python s7_tamper_sim.py new --run-id ar-1030-01 --host haedam@10.250.0.2 \
  --execute --access-url http://10.250.0.2:5000/zz_s7_ar-1030-01.html --source 203.0.113.31 \
  --label s7-attack-1030-01 --log evidence.jsonl
```

## 아직 안 한 것

- 실제 VM 대상 실행(이 저장소에는 ssh 접근 권한이 없어 dry-run 로직만 단위 시험했습니다, `tests/test_s7_tamper_sim.py`).
- Wazuh FIM 경보·Graylog 수신과의 대조 — 실행은 A(VM)·B(일정)·D(Graylog 확인)와 시간을 맞추고, 사용자 승인 뒤에 한다(S7 인수 메모의 지킬 것).
- N=5 반복·경계 시험 계획(핸드오프 4번 항목)은 이 스크립트가 1회 실행 단위라 반복 호출로 짜야 하며, 아직 짜지 않았습니다.
