# S7 수동 AR 호출 + FIM 대조 시험 (2026-10-29, C · shk12170-dev)

포털 VM의 `dist`에서 변조를 만들고, FIM 경보(C manager)와 D의 Graylog 수신을 대조한 뒤, Wazuh API로 117(`s7-restore-ar`)을 호출해 복구했습니다. 새 파일 격리(`ar-1029-01`)와 기준본 파일 복구(`ar-1029-02`)를 각각 1회 했습니다. **이 시험은 사람이 AR을 호출한 수동 검증이며 n8n 자동 복구 완주가 아닙니다.**

원본(비밀값 문자열 없음, JSON 정상, LF 기준):
- `2026-10-29-agent010-ar-1029-01-alerts.jsonl`(2건, sha256 `4a176ab820e03dafbdb5511bef3e072683805c7511895fd4836a36a0966c1727`)
- `2026-10-29-ar-1029-01-apilog.txt`(1줄, sha256 `82008fe25458a276f65294cda5dda6eabe006cd61d41d03d52182b1ef023560c`)
- `2026-10-29-agent010-ar-1029-02-alerts.jsonl`(2건, sha256 `09e46dfde7a6c335ea7fa303945986dd7ef448904e539f5abd6117eb1ee504b1`)
- `2026-10-29-ar-1029-02-apilog.txt`(1줄, sha256 `4c07593f445fe38b3e1aa18889b7a52dddaab04509e4cb72757916e5e8099a68`)

시험ID와 AR run_id는 B가 `ar-1029-01`, `ar-1029-02`로 고정했습니다(앞서 오간 `s7-1029-*` 표기는 폐기).

## 사전 조건

- 호출 계정: `n8n-s7`(역할 `n8n-s7-ar`). 정책 조회 결과 `active-response:command`가 `agent:id:010`에만 `allow`입니다(`rbac_mode: white`). 토큰은 호출 직전에 새로 받아 정책 조회로 확인했습니다(비밀값은 기록하지 않음).
- agent 010 Active, 오늘 09:59 이후 FIM 경보 0건(C 확인, 16:01·16:29). wazuh-agent는 09:58:50 이후 재시작 없음, 포털 서비스는 15:25:57 재시작 이후 없음(A 보고).
- 기준본 `verify` ok: 1회차 전 15:49:40.985(A의 VM 출력, B 회신으로 확인). 2회차 직전 근거는 1회차 정리 뒤 `verify` ok 16:26:26.342와 `index.html` 해시·`/` 응답 확인 16:28:06.844입니다(16:28:06.844는 `verify`가 아님, A 리뷰 지적). `index.html` 기준 해시 `2aca4626785b7cc94275216bd72dd09d668dcdb0e20f8d77982d4adca45a1aa9`는 A의 VM 출력이며 C가 직접 본 값은 아닙니다.
- 진행 순서(B 정리): A 변경 → C manager 경보 대조 → D Graylog 필드 확인 → C 호출 → A 복구·`verify`. 필드가 비거나 `sha256_before`가 기준 해시와 다르면 호출을 보류하는 조건이었고, 두 회차 모두 보류 사유가 없었습니다.

## 1회차 `ar-1029-01` — 새 파일 격리 (KST)

| 단계 | 시각 | 내용 | 출처 |
| --- | --- | --- | --- |
| 새 파일 생성 | 16:13:42.174 | `/home/haedam/haedam-portal-frontend/dist/zz_s7_1029_01.html`, sha256 `1c4c7f6f15b8f2de5c8b44197596e6ef4795ce510e89e4297f420598b5df030a` | A 보고 |
| 554 added | 16:13:42.602 | 같은 경로·해시, 29바이트, 권한 `rw-rw-r--` | C manager |
| D 수신 | 16:13:43.223 | `file_key=zz_s7_1029_01.html`, `signal_kind=fim-change`, `asset_id=haedam-portal`, 스트림 `wazuh-alerts` | D 보고 |
| 호출 | 16:23:18.722(C PC `Get-Date`) / api.log 16:23:20 | 200 · 0.226초 · 전달 1건·실패 0 | C, api.log |
| 격리(VM) | 16:23:20.663 | `s7-restore.log` quarantine · `ar-1029-01` · ok · 2ms · symlink false · 29바이트 | A 보고 |
| 553 deleted | 16:23:20.912 | 같은 경로·해시 | C manager |
| D 수신 | 16:23:21.253 | `file_key`·`signal_kind`·`asset_id` 없음(규칙이 554·550만 보는 설계) | D 보고 |
| 확인 | — | 격리 폴더 `/var/lib/haedam-s7/quarantine/20261029T072320Z_ar-1029-01/`, 격리 파일 해시 = 생성·554·553과 같음, `dist` 원본 부재, 포털 `/zz_s7_1029_01.html` 404, `verify` ok 16:24:29.459 | A 보고 |
| 정리 | — | C 증적 저장 뒤 `purge` ok(files=1), 폴더 비어 있음, `verify` ok 16:26:26.342 | A 보고 |

- 포털 404는 원래 내주지 않는 경로라 생성 전후 모두 404입니다. 노출 없음 확인일 뿐이고, 격리의 근거는 `dist` 원본 부재·격리 파일 해시·`verify`입니다(A 리뷰 지적).
- 호출 → VM 격리 → 553 순서가 맞습니다. 격리(VM 시계) → C 553 수신 간격은 약 0.25초로 보이지만, VM과 manager 시계가 달라 참고값입니다(한계 절 참조).
- 호출 이후 이 파일의 경보는 553 1건뿐입니다. D 보고에 따르면 최근 1시간의 FIM 경보는 554와 553 두 건뿐입니다.

## 2회차 `ar-1029-02` — `index.html` 변조와 기준본 복구 (KST)

| 단계 | 시각 | 내용 | 출처 |
| --- | --- | --- | --- |
| 변경 전 확인 | 16:28:06.844 | `index.html` sha256 = 기준 해시, 응답에 시험 주석 없음 | A 보고 |
| 주석 1줄 추가 | 16:34:36.214 | `2aca4626…a1aa9` → `7ad68dd98b024be5ba586310ec7e0e7f68324c9d5e1ad67b62fa77f040ba1b71` | A 보고 |
| 550 modified | 16:34:36.541 | 691 → 720바이트, 권한 644, 위 두 해시 일치, realtime | C manager |
| D 수신 | 16:34:36.874 | 규칙 550 level 7, `file_key=index.html`, `signal_kind=fim-change`, `asset_id=haedam-portal`, 중복 없음 | D 보고 |
| 호출 | 16:37:26.216(C PC `Get-Date`) / api.log 16:37:27 | 200 · 0.029초 · 전달 1건·실패 0 | C, api.log |
| 복구(VM) | 16:37:27.212 | `s7-restore.log` restore · `ar-1029-02` · ok · 2ms · `sha256_before` `7ad68dd9…` → `sha256_after` = 기준본 | A 보고 |
| 550 modified | 16:37:27.623 | 720 → 691바이트, `7ad68dd9…` → `2aca4626785b7cc94275216bd72dd09d668dcdb0e20f8d77982d4adca45a1aa9`, 권한 644, inode `922535` → `922537`, realtime | C manager |
| 확인 | — | `index.html` 691바이트·644·mtime 16:37:27.213, 포털 `/` 응답에서 시험 주석 제거, `verify` ok 16:39:03.954 | A 보고 |

- 복구 550의 `sha256_after`가 기준 해시와 전체 일치하고 크기도 691바이트로 돌아왔습니다. 복구가 임시 파일 후 이름 변경 방식이라 inode가 바뀝니다(10/28 `ar-02`·`ar-04`와 같은 패턴).
- 16:34 이후 이 agent의 FIM 경보는 위 550 두 건뿐입니다. `.s7restore.*` 임시 파일 경보는 없었습니다. 격리본이 없는 회차라 purge도 없습니다.
- API 처리 시간 0.029초는 전체 복구 시간이 아닙니다(B 기록 기준). 복구 자체는 VM 로그상 2ms입니다.
- **D의 복구 550 신호 판정(D 보고):** 복구 550은 Graylog 수신 16:37:28.233(Wazuh 16:37:27.623)이고 `file_key=index.html`, `asset_id=haedam-portal`이 있으며 `signal_kind`는 **없습니다**("기준본 아님" 신호가 나오지 않음). `sha256_after`는 기준 해시와 일치하고 `before`는 변조 해시 `7ad68dd9…`입니다. 이 시간대 FIM 경보는 변조 550과 복구 550 두 건뿐입니다.
- 같은 규칙이 변조 550에서는 `signal_kind=fim-change`를 붙이고 복구 550에서는 붙이지 않았습니다. `file_key`·`asset_id`가 복구 550에도 있으므로 필드를 붙이는 규칙은 적용됐고, 신호만 기준 해시 일치로 억제된 것으로 읽힙니다. 이 해석은 D가 보고한 필드 값에 근거한 것이며, 규칙 정의 자체를 C가 본 것은 아닙니다.

## 한계와 미검증

- **수동 호출입니다.** n8n 워크플로 경유 호출과 Wazuh manager의 `<active-response>` 자동 실행 경로는 시험하지 않았습니다. Graylog 규칙이 n8n을 거쳐 AR로 이어지는 완주도 이번 범위가 아닙니다.
- **Graylog 이벤트 정의가 없습니다.** D가 확인한 것은 메시지 필드(`file_key`, `signal_kind`, `asset_id`)까지이며 이벤트 필드는 확인하지 못했습니다. D 보고(15:50)에 따르면 시험 시작 때 S7 Graylog 규칙은 저장소 밖에서 화면·API로 먼저 넣은 상태였고, 이번 1회차가 그 필드들의 첫 실제 확인이었습니다. 그 뒤 PR #88이 병합됐지만, 병합된 정의와 Graylog의 현재 상태가 같은지는 이번 시험에서 대조하지 않았습니다.
- 새 파일 554와 기준본 변조 550 모두 `signal_kind=fim-change`로 같은 값입니다. 둘을 구분하는 별도 신호는 이 기록에서 확인하지 않았습니다. 기준 해시와 일치하는 복구 550에서 신호가 없는 것은 확인했습니다(1회).
- 기준본 해시는 A의 VM `verify` 출력이며 C가 직접 본 값이 아닙니다. VM 쪽 로그·격리 폴더·`verify`·포털 응답은 모두 A 보고입니다.
- 각 시험은 1회씩입니다. 반복 재현성, 동시 변조 같은 경합, 대량 변조는 확인하지 않았습니다.
- 시각은 C PC(`Get-Date`), C manager(경보), VM(`s7-restore.log`), D Graylog의 서로 다른 시계입니다. 포털 VM은 NTP 동기이고 offset +2.5ms(A 보고, 14:18)였지만 C PC와 manager 컨테이너 시계는 측정하지 않았습니다. 순서는 모든 단계에서 유지되나, 호출 → 실행의 정확한 지연 비교에는 쓰지 않습니다.
- 이 구간(16:00~16:40)에는 포털·VPN 재시작과 n8n·Graylog 설정 변경이 없었습니다(A·D 보고). TCP 전환 배포와 R2·b8은 이 시험 뒤로 미뤘습니다.
