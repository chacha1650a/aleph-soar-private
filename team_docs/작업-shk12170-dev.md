# 작업 정리 (shk12170-dev)

- 작성일: 2026-10-19 · 갱신: 2026-10-19(팀장 피드백 반영, 합의본 `docs/proposal-sections` `9f1bfbd` 기준) · 근거: [PROGRESS](../docs/PROGRESS.md), [10/19 회의 자료](2026-10-19-회의자료.md), [팀 작업공간](../docs/08-team-workspace.md)
- 이 파일은 폴더 분석 결과를 개인 작업 기준으로 정리한 것입니다. 팀 공식 현황은 `docs/PROGRESS.md`가 우선합니다.

## 1. 프로젝트 요약

| 항목 | 내용 |
| --- | --- |
| 팀 / 저장소 | 1조 NoBugs (NoBugs-Aleph/aleph-soar-capstone) |
| 주제 | 공공기관(가상 OO시청) 민원 서비스·외주 VPN 접속 보안 관제 및 자동 대응 |
| 흐름 | 공격(Kali) → 탐지(Graylog·Wazuh·Suricata) → 자동 대응(n8n: IP 차단·인시던트) → 정상 동작·원복 실측 |
| 팀원 | myeongjundev, whiteclover0542, chacha1650a, shk12170-dev(나) |
| 앱 상태 | Flask 스켈레톤(시작 화면 + `/api/v1/health`). 인증·탐지·대응·원복 미구현 |

## 2. 폴더 구조

| 경로 | 역할 |
| --- | --- |
| `src/aleph_soar/` | Flask 앱 (`portal/` 백엔드, `detection/`·`response/` 탐지·대응, `templates/`·`static/` 화면) |
| `contracts/` | 공통 이벤트·사건 스키마와 합성 예시 (`docs/API-CONTRACT.md`와 함께 수정) |
| `orchestration/` | 작업 DAG(`workplan.json`: P01 → B01·D01·U01 → I01 → V01), 인수인계 양식 |
| `ai/roles/`, `.agents/skills/` | 역할·스킬 원본 (`.claude/`, `.codex/`는 생성물 → `tools/sync_ai_assets.py`) |
| `tools/` | `bootstrap.py`(환경), `team.py`(작업 지시서), `sync_ai_assets.py` |
| `tests/` | 앱·계약·AI 자산·작업 DAG 검증 |
| `docs/` | 기획·논의 기록(01~29), `PROGRESS.md`, `devlog/members/` 개인 일지 |
| `team_docs/` | 기획서 초안·합의본, 10/19 회의 자료, S1~S10 가이드 PDF |
| `work-log/` | AI 세션 인수인계 기록 |
| `통신사 …/` | 이전 통신사 주제 제안 자료 (논의 이력, 현재 기준 아님) |

## 3. 일정

| 날짜 | 내용 |
| --- | --- |
| 10/19(월) | 자리 A~D와 PC 배치 확정 (학원 PC 4대 같은 사양, 이웃한 두 자리를 공격·서비스 PC / 관제 PC로 분리) |
| 10/19~10/23 | 사전 위험 시험 ①~③ (병행) |
| 10/21(수) | 기획서 팀원 확인 마감 |
| **10/23(금)** | **기획서 제출** |
| ~11/3 | 평가지표 종합 리포트 |
| **11/5(목)** | **리허설** (실측 시연, 녹화) |
| **11/6(금)** | **본발표·최종 제출** |

## 4. 나의 할 일

> 갱신 2026-10-19: 10/19 회의에서 자리 **C(S7 홈페이지 변조 · Wazuh · 보안 대시보드)** 로 정해졌고, 관제 PC·서비스 PC 분리로 결정됐습니다(기획서 합의본 10/19 회의 결정). S7 세부는 [작업방향-S7-shk12170-dev.md](작업방향-S7-shk12170-dev.md).

### 완료
- [x] S7 작업 방향 정리, FIM 이벤트 계약 확장 제안, 기획서 피드백·C 자리 확인 (PR #14 병합)
- [x] C 수정 필요 1~4 전달: PR #10 코멘트 → 합의본 `ebae483`에 반영(자산 + 파일 키, 정상 배포 해시 목록, 복구 1안 Wazuh active response / 2안 포털 API)

### 10/21까지 (기획서 팀원 확인)
- [ ] 수업 대응 봇 번호 확인 → 117(가칭) 사용 여부 회신
- [ ] `ebae483` 기준 C 체크리스트에 "동의" 남기기 (근거: [C자리-S7-확인](../docs/s7-draft/C자리-S7-확인.md))
- [ ] 개발 일지 `docs/devlog/members/shk12170-dev.md`에 첫 기록
- [ ] 강사님께 물을 것 4·5번 답변 확인: "Graylog 13가지 티켓"·봇 번호(117 충돌 여부 포함), 보안 대시보드 위치 (합의본 `9f1bfbd`)
  - 밴드 토폴로지는 참고용으로 확인됨(`5433d69`)

### 10/24~10/28 (공통 기반·사전 시험)
- [ ] 서비스 VM에 Wazuh 에이전트, realtime FIM 경보 시간·파일 키 확인
- [ ] A(whiteclover0542)와 포털 Docker 웹 디렉터리 bind mount 구조 합의
- [ ] (참관) 관제 PC Graylog·Wazuh 동시 구동 메모리 — 사전 위험 시험 ③, **담당 D(chacha1650a)**, 10/19~10/23. 통과 기준: 정상 부하 30분 OOMKilled 0회, 표식 로그 유실 0건, 재시작 뒤 수집 회복. S7은 Wazuh가 필수라 결과를 함께 확인
- [ ] 복구 수단 1안(n8n → Wazuh API → active response) 동작 확인, 안 되면 2안(포털 API)
- [ ] 해시 목록에 있는 정상 배포가 S7을 발동하지 않는지 확인

### 이후
- [ ] S7 구현 → 입력표 시험(정상 / 조건 일부 / 경계 / 전체 충족 / 창 밖 / 혼합) → 결과표 기록
- [ ] 자동 복구 원복 절차 작성·검증, 보강 전후 비교

## 4-1. 서기 업무: 일일 회의록

매일 회의록을 작성해 보고하고, Notion에 올려 팀원이 부재 중에도 회의·작업 내용을 볼 수 있게 합니다.

- 흐름: 회의 중 메모 → 이 파일 아래 양식으로 정리 → Notion에 게시 → 팀 채널에 링크 공유
- 원본 기준: 합의·결정은 `docs/07-topic-decision.md`, 현황은 `docs/PROGRESS.md`와 대조해 어긋나지 않게 기록
- 보관: Notion은 팀원 공유용입니다. **결정 사항은 `docs/07-topic-decision.md`에도 남겨** GitHub만 보는 AI 세션과 리뷰어가 따라올 수 있게 합니다. 회의록 원본을 저장소에도 둘지는 팀에서 정합니다(미정)
- 비밀번호·키·토큰은 회의록에 적지 않음
- 확정된 것과 제안·미정을 구분해 표기

### 회의록 양식

```markdown
# YYYY-MM-DD 회의록 — 1조 NoBugs

- 일시 / 장소(방식):
- 참석: / 부재:
- 서기: shk12170-dev

## 1. 안건
-

## 2. 논의 내용
-

## 3. 결정 사항 (확정)
-

## 4. 미정·보류
-

## 5. 담당별 진행 현황
| 담당 | 한 일 | 할 일 | 막힌 점 |
| --- | --- | --- | --- |

## 6. 액션 아이템
| 할 일 | 담당 | 기한 | 상태 |
| --- | --- | --- | --- |

## 7. 부재자 참고 (3줄 요약)
-

## 8. 다음 회의
-
```

## 5. 작업 규칙 (요약)

- `main` 직접 push 금지, 브랜치 + PR (`CONTRIBUTING.md` 접두사 따름)
- 계약(API·이벤트·사건) 변경 시 `docs/API-CONTRACT.md`와 `contracts/` 스키마·예시·소비자를 함께 수정
- 스킬 원본은 `.agents/skills/`만 수정 후 `python tools/sync_ai_assets.py`
- 비밀번호·토큰·원문 민감 데이터는 이벤트·증적에 기록하지 않음
- 테스트 계정은 `zz_` 접두사, IP는 격리된 실습 대역만 사용
- 실측과 샘플, 사용 예정과 설치·연동 완료를 구분해 기록. 인수인계에는 미검증 부분도 적기

## 6. 자주 쓰는 명령

```powershell
python tools/bootstrap.py
.\.venv\Scripts\python.exe -m flask --app aleph_soar:create_app run --host 127.0.0.1 --port 5000
python -m pytest -q
python tools/sync_ai_assets.py --check
python tools/team.py ready
python tools/team.py brief P01
```

## 7. 미결정·주의

- 망 구성(합의본 ③): VMnet2 외부 / VMnet3 DMZ / VMnet4 업무망 / **관리망은 두 PC 사이 전용 연결(브리지, 10.10.30.0/24)** / VPN 10.10.40.0/24
- 남은 결정: 외부 구역 VMnet 번호(VMnet2를 수업 pfSense VM이 LAN으로 쓰고 있어 동시에 켜지 않거나 빈 번호로 옮김, 담당 B)
- 도구는 "사용 예정"이며 실제 설치·연동·시험 완료 아님
- 공방전(타 팀과 교차 공격) 일정·규칙·채점은 미정
- `docs/20~24` 등 통신사 주제 문서는 이력용
