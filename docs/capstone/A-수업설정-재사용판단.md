# 수업 설정 재사용 판단 (A순서 207 · 환경 구축)

- 담당: whiteclover0542 (A) · 작성 2026-10-29 · 상태: **판단 완료(파일 대조).** 실제 설정·운영은 C(Wazuh)·D(Graylog) 담당 — 아래는 A의 재사용 판단과 핸드오프.
- 대상: 수업 프로젝트 `flask-board`(출처 `source-copy.json`: github.com/myeongjundev/flask-board = **B의 class repo**). 로컬 `C:\SR\NoBugs\flask-board-team\flask-board-team\flask-board`.

## 판단: 재사용 가능 — Graylog·Wazuh·MySQL은 **이미 반영됨**

수업 compose/설정의 버전·포트가 현재 캡스톤 구성과 전부 일치한다. C는 수업 compose를 직접 쓰고 있다.

| 구성 | 수업 flask-board | 캡스톤 현재 | 근거 |
|---|---|---|---|
| Graylog | 6.1 (`graylog/graylog:6.1`) | 6.1.16 | docs/22·23, 기획서 ③ |
| OpenSearch | **2.5.0** (주석 "2.15 색인 NPE—반드시 2.5.0") | 2.5.0 | [Graylog 셋팅 지시](../../team_docs/2026-10-20%20Graylog%20셋팅%20작업지시.md) L29, 기획서 |
| MongoDB | 6.0 | 6.0.28 | 위와 동일 |
| Wazuh | 4.9.0 (`wazuh-lab`) | 4.9.0 — **C가 수업 compose 직접 사용** | [C-작업순서](../C-작업순서.md) L64·L120 |
| GELF 입력 | UDP/TCP 12201 | 12201 | C-작업순서, [PORTAL-API](../haedam/PORTAL-API.md) |
| MySQL | 8.0 | 8.0 | flask-board compose, 캡스톤 |

- pfSense CE 2.7.2 VM은 B PC에 있고 사전 시험 ①에서 복제해 씀(A순서 207 원문) → 이미 재사용.
- OpenSearch **2.5.0 고정 사유(2.15 색인 오류)**는 캡스톤에 이미 기록됨 → 버전 올리면 깨지므로 유지. 추가 조치 불필요.

→ **결론: 가져올 수 있고, 핵심 스택(Graylog/Wazuh/MongoDB/OpenSearch/MySQL)은 수업 설정을 이미 재사용 중.** A순서 207의 "판단" 완료.

## C·D에 넘기는 재사용 후보 (아직 캡스톤 반영 미확인)

수업 프로젝트에 있는 아래는 캡스톤 증적·검증에 쓸 수 있다. 실제 채택은 담당이 판단.

| 파일 | 용도 | 넘길 담당 |
|---|---|---|
| `flask-board/scripts/export_graylog_alerts.py` | Graylog 경보 내보내기(증적 수집) | D |
| `flask-board/scripts/verify_wazuh_signals.py` | Wazuh 신호 검증 | C |
| `flask-board/scripts/check_wazuh.ps1` | Wazuh 상태 점검 | C |
| `flask-board/docs/WAZUH-*-GUIDE.md` | Wazuh 설치·검증 가이드 | C |

## 경계
- A는 파일 대조로 버전 일치만 판단했다. 실제 실행 중 digest·연동·로그 전달은 C·D 실측(docs/22·23의 "미확인" 항목과 같음).
- 수업 데이터·키·개인 런타임 파일은 가져오지 않는다(`source-copy.json` `private_runtime_files_copied:false`).
