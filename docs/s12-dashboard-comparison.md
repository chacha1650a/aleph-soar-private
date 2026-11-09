# S12 정상 사용자 보강 전후 실측 비교

작업 ID: S12-UI-COMPARE-1029. B 김명준의 집 구현 후보이며 C 운영 화면·저장소, D S12 대응과 연결한다. 브랜치 `codex/s12-pf-integration-20261029`의 미커밋 변경이다. 학원 실측·운영 배포 완료가 아니다.

## 화면과 데이터 흐름

정상 사용자 PC의 `tools/s12_probe.py` → 보강 전/후 CSV → 로컬 등록 CLI → 기존 티켓 DB의 `s12_comparisons` → `/s12` 비교 화면 및 S12 티켓 상세. n8n record API와 기존 티켓 상태 전이는 변경하지 않는다. 웹 업로드나 추가 공개 쓰기 API는 없다.

CSV가 없는 사건은 **미측정**이다. 모든 요청이 실패하면 성공률은 0%, 응답시간은 **미측정**이다. 성공은 지정한 HTTP 2xx 코드(기본 예시 200)이며 오류가 없는 요청이다. 성공률의 분모에는 타임아웃과 연결 실패도 포함한다. 응답시간 중앙값·p95는 성공한 요청만 사용하며 p95는 nearest-rank다. probe 콘솔은 2xx/3xx 및 다른 백분위 계산을 사용하므로 발표 비교는 이 화면의 동일 계산식으로 맞춘다.

성공률은 후−전 차이를 %p로 표시한다. 응답시간 차트는 지표별 전후 동일 축이며 낮을수록 빠르다. HTTP 200이 업무 내용의 정상 처리나 차단 효과를 증명하지는 않는다. 요청 수, 실패 수, 관측 길이와 실제 시각을 같이 보여준다.

## 먼저 집에서 확인

```powershell
python tools/preview_security_dashboard.py --samples --s12-comparison --port 8100
```

`http://127.0.0.1:8100/s12?sample=1`로 연다. 예시는 **명시적 합성 데이터**이고, 기존 실제 CSV의 결과로 위장하지 않는다. 임시 DB만 사용하며 네트워크 요청·공격·차단은 실행하지 않는다.

## 학원 측정 및 등록 순서

1. C 담당이 DB를 백업하고 이 후보의 서비스 코드를 검토·재빌드한다. 기존 `ticket-data` 볼륨을 유지한다. 초기화 시 기존 표를 건드리지 않고 `s12_comparisons` 표를 추가한다. 스키마 변경이 없던 이전 UI 후보와 다르다. 서비스 전체 변경 목록과 기존 후보 차이를 검토한다.
2. 실제 S12 티켓 ID와 시험 ID를 정한다. 보강 전후에 같은 정상 출발지, 대상 URL, 요청 주기, 제한시간, 측정 길이, 부하 조건을 사용한다. 보강 전/후 버전과 주 대응 경로(portal 또는 pfsense)는 따로 기록한다. 공격 출발지를 정상 사용자 측정으로 등록할 수 없다. **이 문서는 부하 실행 명령이나 장비 시험 승인을 대신하지 않는다.**
3. 허가된 실습 창에서 정상 사용자 요청을 측정한다. 아래는 기존에 정한 `.100` 정상 출발지와 포털 health 경로의 예다. 실제 클라이언트 인터페이스·경로를 먼저 대조한다. health 결과는 health 경로 가용성이지 전체 민원 업무 성공률이 아니다. 두 측정 사이에는 담당자가 보강을 적용하고 동일 부하 조건으로 시험한다.

```powershell
python tools/s12_probe.py --url http://10.250.0.2:5000/api/v1/health --source 203.0.113.100 --interval 2 --duration 60 --timeout 3 --label S12-RUN01-before --out before.csv
# 보강 적용 후 같은 조건에서 실행. 원본 파일은 덮어쓰지 않는다.
python tools/s12_probe.py --url http://10.250.0.2:5000/api/v1/health --source 203.0.113.100 --interval 2 --duration 60 --timeout 3 --label S12-RUN01-after --out after.csv
```

4. `contracts/s12-examples/comparison.sample.json`을 개인 작업 폴더의 `measurement.json`으로 복사해 모든 값을 실제 시험 값으로 수정한다. `origin`은 실제 실측이면 `live`, 합성이면 `sample`; 연결 티켓의 출처와 같아야 한다. `ticket_id`, `run_id`, 대상, 시간 조건, 부하, 전후 버전을 모두 맞춘다. 메타데이터에 토큰·비밀번호를 넣지 않는다.
5. 기존 SQLite 파일을 사용하는 로컬 설치라면 다음과 같이 등록한다. DB 파일은 미리 존재해야 하며 S12 티켓이 있어야 한다. `--db`에는 운영 DB의 실제 경로를 넣는다.

```powershell
$env:PYTHONPATH='services/ticket-store'
python -m ticket_store.s12_measurements --db C:/실제경로/tickets.db --metadata measurement.json --before before.csv --after after.csv
```

Docker 설치에서는 **C PC에서** CSV·메타데이터를 컨테이너의 임시 경로로 복사하고, 운영 볼륨 `/data/tickets.db`에 등록한다. 파일명은 시험마다 바꿔 원본 혼동을 피한다. DB를 호스트로 꺼내 별도 사본에 등록한 뒤 운영 DB를 덮어쓰지 않는다.

```powershell
docker cp measurement.json ticket-store:/tmp/S12-RUN01.json
docker cp before.csv ticket-store:/tmp/S12-RUN01-before.csv
docker cp after.csv ticket-store:/tmp/S12-RUN01-after.csv
docker exec ticket-store python -m ticket_store.s12_measurements --db /data/tickets.db --metadata /tmp/S12-RUN01.json --before /tmp/S12-RUN01-before.csv --after /tmp/S12-RUN01-after.csv
```

6. 대시보드 `S12 전후 비교`에서 샘플 포함을 끄고 새로고침한다. 시험 ID를 선택한 뒤 성공률 → 중앙값/p95 → 실패 수/관측 구간 → 원본 SHA256 → 연결 티켓 순서로 발표한다. CSV 등록은 원자적이며 기존 시험 ID를 덮어쓰지 않는다. 정정은 새 ID로 등록하고 기존 오류 시험을 발표에서 제외한다.

## 입력 계약·보존·한계

- 메타데이터 형식: `contracts/s12-comparison.schema.json`. CSV 열은 기존 probe의 `ts_kst,label,source,status,ms,error`다. 출발지 없는 과거 CSV는 비교 등록을 거부한다. 하나의 라벨·출발지, 시간대가 있는 단조 증가 시각, 유한한 비음수 지연값이 필요하다.
- 전후 원본이 같거나 시간창이 겹치거나 역전되면 등록하지 않는다. CSV당 최대 10 MB/50,000 요청. 원본 파일은 보존하고 DB에는 파일명·SHA256·집계·관측 시각·선언 조건을 보존한다. 표본별 원문은 DB에 중복 저장하지 않는다.
- 대상 URL과 부하·주기·제한시간·버전은 CSV에 없으므로 **등록자의 선언**이다. 실제 실행 기록과 대조한다. 서로 다른 조건의 결과를 인과적 개선으로 설명하지 않는다. 표본 부족, 요청 수 차이, 짧은 관측 길이, 큰 주기 지연을 경고한다.
- 샘플은 기본 조회에서 제외한다. `live`도 등록자가 실측으로 선언한 자료이며 센서 연결을 자동 인증하지 않는다. 티켓 링크는 발표 증거 연결용이며 등록이 효과 확인·원복·종료 상태를 바꾸지 않는다.
- SQLite 백업에는 추가 표도 포함된다. 이전 이미지로 되돌려도 추가 표를 삭제할 필요는 없다. 실제 운영 DB 백업·재빌드·재수신 시험은 C 담당의 첫 확인이다.

## 로컬 확인

자동 테스트: 성공/실패/타임아웃 집계, 전체 실패의 응답시간 null, p95, 샘플 격리, 실제 기록 조회, HTML 이스케이프, 중복·불일치·잘못된 CSV 거부와 원자성. 브라우저: 데스크톱/390px 비교 카드, 원본 조건, 티켓 연결, 샘플 제외 빈 상태. 학원 부하·보강·실제 요청 측정은 이 작업에서 실행하지 않았다.
