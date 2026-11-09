# 10/19 포털 독립 검증·리뷰 요청 자료

- 작업: H02/H03 독립 리뷰 준비. 사용자 요청 `검증체크리스트와 리뷰 요청 자료 부탁할께`, 담당 김명준 + Codex.
- 브랜치: 기존 `codex/haedam-portal-mvp`, [capstone Draft #18](https://github.com/NoBugs-Aleph/aleph-soar-capstone/pull/18)에 문서 추가. 앱 코드·API·계약·DB 변경은 없다.
- 산출물: [검증 체크리스트](../docs/haedam/REVIEW-CHECKLIST.md), [전달용 리뷰 요청문](../docs/haedam/REVIEW-REQUEST.md), [자료 안내](../docs/haedam/README.md).
- 기준: backend `df8bf88bbe37c6fa92ab83dfa3ae156ad1a6afb1`, frontend `cac2bed39181d7f9e6d4da82d1d4391f8a852ae2`, capstone 구현 기록 `2fe8b713328c8aac4907f6e594e7a0ce3f7ca500`. 계약 `2303265ba2ba46f6e6e5622698b1d2f141357f80`, 규칙 v3 `5e79d461d71e5f70c4daf0288572624a0962f817`.
- 실제 확인: git fetch 후 세 저장소의 원격/로컬 HEAD 일치·작업 트리 깨끗함, GitHub 앱 #1 두 개와 capstone #17/#18 Open/Draft. #18 base는 인수인계 브랜치, #17 base는 main. 자료 작성 시 #18 Ubuntu/Windows Workspace checks 성공, 앱 PR 두 개는 표시된 체크 없음.
- 문서 검증: 변경 Markdown 5개의 UTF-8, 로컬 파일/절 링크 28개, 참조 커밋 5개, PowerShell 예시 4개 구문, 실제 스크립트/참조 경로와 git diff --check를 확인했다. 예시 명령을 실행하거나 앱 테스트를 재실행한 것은 아니다. 작성자 실측 수치는 [직전 MySQL 검증](2026-10-19-mysql-browser-integration.md)의 결과이며 독립 검토 결과 칸은 미실행/미확인으로 남겼다.
- 미완료: 실제 독립 리뷰어 배정·리뷰 요청 발송·Draft 해제·리뷰 승인·병합, 서비스 VM·두 PC·외부 관제 인수. 이 자료 게시가 이를 완료했다는 뜻은 아니다.
- 다음 첫 행동: 작성자가 구현자 외 검토자와 회신 시점을 조율한 뒤 요청문을 전달한다. 검토자는 새 폴더에서 T1~T4를 재현하고 M/R/C 항목·미실행 범위·판정을 체크리스트 하단 양식에 기록한다. 정식 리뷰 및 병합은 #17→#18의 선행 관계와 앱 두 PR의 검증 조합을 확인해 별도로 진행한다.
