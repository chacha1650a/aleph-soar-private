# Wazuh API 인증·기존 계정 확인 안내 (C·D 전달용)

- 작성: B 김명준 · 2026-10-23 / Asia/Seoul
- 대상: C Wazuh manager 관리자, D n8n 연동 담당
- 목적: 인증과 기존 `n8n-ar` 계정 존재 여부를 먼저 확인한다.
- 범위: 토큰 발급과 사용자 목록 조회. 계정·정책·역할을 생성하거나 변경하는 명령은 포함하지 않는다.
- 확인 상태: 명령의 Bash 구문 검사는 통과했다. 실제 C/D 환경의 인증·HTTP 응답은 실행 후 확인해야 한다.

## 1. 현재 설명에서 확정할 수 있는 범위

`H` 배열에 옵션이 들어 있지 않으면 조용한 출력·인증 헤더·자체 서명 인증서 처리 옵션이 함께 빠질 수 있다. 다만 원래 실행 명령과 HTTP 응답 없이 “세 요청이 모두 실패했고 아무것도 생성되지 않았다”고 확정할 수는 없다. 기존 계정·역할·정책이 있는지 조회한 뒤 이어간다.

- `H=(...)`는 **Bash 배열**이다. PowerShell이나 `sh`에서 실행하지 않는다.
- 컨테이너를 나갔다가 다시 들어오거나 다른 터미널을 쓰면 `TOKEN`·`H`가 이어지지 않는다. 아래 과정을 같은 Bash 세션에서 실행한다.
- `TOKEN=$(curl ...)`는 변수 할당이다. `echo TOKEN=$(curl ...)`는 토큰을 화면에 출력하고 변수에는 저장하지 않을 수 있다. 코드 블록의 줄바꿈을 유지한다.
- JWT 길이는 고정 400자가 아니다. 아래의 모양 검사는 기본 확인이며, 인증된 조회의 HTTP 응답으로 실제 사용 가능 여부를 확인한다.
- URL은 아래 코드의 평문을 복사한다. Markdown 링크의 대괄호·괄호·중복 따옴표를 명령에 넣지 않는다.

## 2. 실행 위치

**C PC에서**, Wazuh manager 컨테이너의 Bash로 들어간다. 현재 컨테이너 이름이 다르면 C가 확인한 실제 이름을 사용한다.

```powershell
docker exec -it wazuh-manager bash
```

아래의 `127.0.0.1:55000`은 **그 Wazuh manager 컨테이너 안의 API**다. D n8n 컨테이너 안에서 실행하면 D 자신의 loopback을 가리킨다. 이번 로컬 인증 확인 결과와 이후 D→C VPN 연결 시험은 별도로 기록한다.

비밀번호는 **Wazuh 서버 API 관리자 계정**의 것이다. 계정명 기본값은 `wazuh`이며, 실제 계정명이 다르면 아래 `-u`의 `wazuh` 부분을 바꾼다. 대시보드·Indexer 계정과 같다고 가정하지 않는다.

## 3. 인증 후 사용자 목록 조회

컨테이너 안 Bash에 아래 블록을 그대로 붙여 넣는다. 토큰 값은 출력하지 않는다.

```bash
set +x
unset TOKEN
H=()

read -r -s -p 'Wazuh API 관리자 비밀번호: ' ADM
printf '\n'

TOKEN=$(curl -fksS --connect-timeout 5 --max-time 15 \
  -u "wazuh:$ADM" -X POST \
  'https://127.0.0.1:55000/security/user/authenticate?raw=true')
AUTH_RC=$?
unset ADM

if (( AUTH_RC == 0 )) && [[ "$TOKEN" =~ ^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$ ]]; then
  H=(-ksS -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json')
  printf 'H 원소 수=%s\n' "${#H[@]}"

  curl "${H[@]}" --connect-timeout 5 --max-time 15 \
    -w '\nHTTP=%{http_code}\n' \
    'https://127.0.0.1:55000/security/users?pretty=true'
else
  unset TOKEN
  H=()
  printf '인증 실패: 계정·정책 생성은 진행하지 마세요.\n'
fi
```

- 정상적으로 구성되면 `H 원소 수=5`가 출력된다. 이것만으로 API 권한까지 확인된 것은 아니다.
- `-sS`는 진행률을 숨기고 오류는 보여 준다. `-k`는 이 고정 loopback HTTPS 요청의 인증서 검증만 생략하며 전역 설정을 바꾸지 않는다.
- 인증 실패 시 토큰과 배열을 비운다. 오류 메시지를 지우거나 계정 생성 명령으로 넘어가지 않는다.
- 이 블록을 파일에 저장해서 실행할 때 이후 같은 셸에서 `H`를 사용하려면 `source 파일명.sh`로 불러온다. `bash 파일명.sh`로 실행한 자식 셸의 변수는 부모 셸에 남지 않는다.

## 4. 결과 판독

| 결과 | 해석·다음 확인 |
| --- | --- |
| `H 원소 수=5`, 사용자 조회 `HTTP=200` | 인증된 조회 성공. JSON의 오류·결과도 확인하고 `n8n-ar` 사용자 객체의 존재 여부와 ID를 읽는다. |
| 인증 curl 오류 `(22)` / 조회 `HTTP=401` | API 계정·비밀번호 또는 토큰을 확인한다. 토큰 만료·새 셸 진입 시 3절을 다시 실행한다. |
| 조회 `HTTP=403` | 인증 계정의 사용자 조회 권한을 확인한다. |
| 연결 오류 / `HTTP=000` | 실행 컨테이너, API 수신 여부, curl 오류를 확인한다. 인증서 오류와 연결 거절·timeout을 구분한다. |
| HTTP 응답은 있으나 JSON 오류·실패 항목이 있음 | HTTP 코드와 JSON 오류를 함께 기록한다. 응답 일부를 grep으로 제거하지 않는다. |

`n8n-ar`가 이미 있으면 계정을 다시 만들지 않는다. ID는 `username: n8n-ar`와 **같은 사용자 객체**의 `id`를 읽는다. 목록의 다른 사용자나 역할 ID를 섞지 않는다.

`n8n-ar`가 없더라도 먼저 이번 조회 결과를 공유한다. 계정 생성 성공 여부와 기존 역할·정책을 확인한 뒤 필요한 항목만 이어서 만든다. 원래 정책 두 개의 이름·권한 본문이 확인되지 않은 상태에서 재생성하지 않는다.

## 5. 회신할 내용

아래 항목만 전달하면 다음 단계를 판독할 수 있다. 비밀번호·JWT·Authorization 헤더 전체는 공유하지 않는다.

```text
실행 위치: C PC / Wazuh manager 컨테이너 / Bash
H 원소 수:
인증 curl 오류: 없음 또는 오류 번호·설명
사용자 조회 HTTP:
JSON 오류: 없음 또는 error/message/실패 항목
n8n-ar 존재 여부:
n8n-ar 사용자 ID: 존재하는 경우에만
```

다음 순서는 **기존 역할·정책 조회 → 필요한 항목만 생성/연결 → n8n-ar 권한 확인 → D n8n의 실제 연결 시험**이다. 계정·역할 생성만으로 A agent의 실제 복구나 S7 자동 대응이 확인된 것은 아니다.

## 공식 근거

- [Wazuh 서버 API 인증 시작](https://documentation.wazuh.com/current/user-manual/api/getting-started.html)
- [Wazuh RBAC 구성](https://documentation.wazuh.com/current/user-manual/api/rbac/configuration.html)

작성 지원: Codex. 전달된 오류 설명과 공식 문서를 대조해 안내를 작성했으며, 원격 인증·계정 변경·팀 메시지 발송은 실행하지 않았다.
