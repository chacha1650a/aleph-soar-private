#!/usr/bin/env python3
"""S1·S4 재현 스크립트 (A whiteclover0542).

해담 민원 포털 로그인(POST /api/v1/auth/login, JSON + X-CSRF-Token)에
정상/임계 미만/임계 충족 3모드로 로그인 시도를 보낸다. Hydra 대신 Python을
쓰는 이유는 포털이 JSON 본문과 로그인마다 회전하는 CSRF 토큰을 요구하기
때문이다(docs/capstone/A-S1-S4-공격시나리오.md "공격 도구").

안전: 격리 랩 전용. zz_ 테스트 계정과 문서용 대역 출발지만 사용한다.
시도한 비밀번호는 로그·표준출력에 남기지 않는다(성공/실패 결과만 센다).

출발지(src_ip)는 포털이 remote_addr로만 읽으므로(X-Forwarded-For 무시),
실행마다 다른 출발지는 이 스크립트가 아니라 **호스트(Kali)의 출발지 주소**로
만든다. 자리 A는 203.0.113.11~19에서 실행마다 바꾼다(계획값).

입력표(공격 시나리오 73행)의 각 행을 모드로 돌린다:
  정상→normal, 경계 아래→below, 전체 충족→trigger, 조건 일부만→partial-fail/partial-success(S4),
  순서 반대→reversed(S4), 시간 창 밖→--window-out, 혼합(계정 분산)→--mix N.
정상 패턴 정의서 N1~N5: N1=normal, N2=below, N3=--mix, N5=--window-out.
  N4(다른 출발지 분산)는 포털이 remote_addr만 보므로 --source로 Kali의 다른 주소를 지정해 따로 돌린다.

사용:
  python replay.py S1 --mode trigger --base-url http://10.10.10.10:5000 --user zz_a1
  python replay.py S1 --mode trigger --base-url ... --source 203.0.113.11   # Kali 추가 주소에서 보냄
  python replay.py S4 --mode trigger --base-url ... --user zz_a1 --password <정답>
  python replay.py S4 --mode reversed --base-url ...        # 성공 뒤 실패(발동)
  python replay.py S1 --mode trigger --window-out --base-url ...  # 창 밖(미발동)
  python replay.py S1 --mode trigger --mix 3 --base-url ...       # 3계정 분산(미발동)
  python replay.py S1 --mode trigger --dry-run     # 네트워크 없이 계획만 출력
  python replay.py --self-test                     # 랩 없이 모드 정의 점검
"""
import argparse
import http.client
import http.cookiejar
import http.server
import json
import sys
import threading
import time
import urllib.request
from datetime import datetime

# 모드별 (실패 횟수, 성공 횟수, 창 안 분, 기대, 순서). 임계값은 초안(6단계에서 조정).
# 순서 "ff"=실패 뒤 성공(기본), "sf"=성공 뒤 실패. 입력표(공격 시나리오 73행)의 행과 1:1.
PLANS = {
    "S1": {  # login-bruteforce count()>8 · 30분 · username+src_ip
        "normal":  (1, 1, 30, "미발동"),
        "below":   (8, 0, 30, "미발동(경계 바로 아래)"),
        "trigger": (9, 0, 30, "발동 1건"),
    },
    "S4": {  # login-* card(rule)>1 & count()>5 · 10분 · username
        "normal":          (0, 1, 10, "미발동"),
        "partial-fail":    (6, 0, 10, "미발동(종류 1개: 실패만)"),
        "partial-success": (0, 5, 10, "미발동(종류 1개: 성공만)"),
        "below":           (4, 1, 10, "미발동(합계 5)"),
        "trigger":         (5, 1, 10, "발동 1건"),
        "reversed":        (5, 1, 10, "발동(순서 반대, 순서 미요구 10/21)", "sf"),
    },
}


def build_attempts(case, mode, user, mix=1, window_out=False):
    """각 시도를 (ok, user)로 만든다. ok=실패 False/성공 True.

    mix>1: 실패를 user, user_2, … user_mix 계정에 번갈아 나눠 계정별 판정(미발동)을 시험한다.
           출발지(src_ip)는 포털이 remote_addr로만 읽어 이 스크립트가 못 바꾼다 → 다른 출발지
           분산(정상 패턴 N4)은 호스트(Kali) 주소를 바꿔 실행마다 따로 돌린다.
    window_out: 전체 시도 간격을 창보다 길게 벌려 '시간 창 밖'(미발동)을 시험한다.
    """
    plan = PLANS[case][mode]
    fails, successes, window_min, expect = plan[:4]
    order = plan[4] if len(plan) > 4 else "ff"
    users = [user] + [f"{user}_{k}" for k in range(2, mix + 1)]
    fail_attempts = [(False, users[i % len(users)]) for i in range(fails)]
    succ_attempts = [(True, user)] * successes  # 성공은 진짜 비번이 필요해 기준 계정만
    attempts = (succ_attempts + fail_attempts) if order == "sf" else (fail_attempts + succ_attempts)
    n = len(attempts)
    # 창 안에 고르게 나누되, S1은 짧은 창 규칙(2분 6회)에 걸리지 않게 간격을 벌린다.
    interval = (window_min * 60) / n if n > 1 else 0.0
    if case == "S1" and not window_out and interval < 150:
        interval = 150.0  # ponytail: 고정 하한 150초(2분당 6회 미만 보장), 임계값 바뀌면 재검토
    if window_out and n > 1:
        # 전체 span = interval*(n-1)이 창을 1.3배 넘게. 마지막 시도가 창 밖으로 떨어진다.
        interval = (window_min * 60) * 1.3 / (n - 1)
        expect = f"미발동(시간 창 밖: 총 {window_min*1.3:.0f}분 > {window_min}분)"
    if mix > 1:
        expect = f"미발동(계정별 판정, 실패를 {mix}개 계정에 분산)"
    return attempts, interval, expect


def login_once(opener, base_url, user, ok):
    """GET /auth/me로 CSRF·세션을 받고 로그인 1회. HTTP 상태만 돌려준다."""
    me = json.load(opener.open(base_url + "/api/v1/auth/me", timeout=5))
    csrf = me.get("csrf_token") or me.get("data", {}).get("csrf_token", "")
    # 성공 시도만 진짜 비밀번호를 쓴다. 실패는 버릴 값(실제 계정 비밀번호 아님).
    password = login_once.password if ok else "zz_wrong_pw"
    body = json.dumps({"username": user, "password": password}).encode()
    req = urllib.request.Request(
        base_url + "/api/v1/auth/login", data=body, method="POST",
        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
    )
    try:
        resp = opener.open(req, timeout=5)
        return resp.status
    except urllib.error.HTTPError as e:
        return e.code


login_once.password = ""  # --password로 채움


class SourceHTTPHandler(urllib.request.HTTPHandler):
    """요청을 지정한 출발지 주소에서 보낸다(Kali 추가 주소 .11~.19 등). 포털은 연결 주소만 src_ip로 쓴다."""

    def __init__(self, source):
        super().__init__()
        self.source = source

    def http_open(self, req):
        return self.do_open(
            lambda host, **kw: http.client.HTTPConnection(host, source_address=(self.source, 0), **kw), req)


def build_opener(source=None):
    handlers = [urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())]
    if source:
        handlers.append(SourceHTTPHandler(source))
    return urllib.request.build_opener(*handlers)


def run(case, mode, base_url, user, dry_run, interval_override=None, mix=1, window_out=False, source=None):
    attempts, interval, expect = build_attempts(case, mode, user, mix, window_out)
    if interval_override is not None:  # 로컬 기능 검증용. 랩 실측은 기본 간격을 쓴다.
        interval = interval_override
    fails = sum(1 for ok, _ in attempts if not ok)
    print(f"[{case}/{mode}] 시도 {len(attempts)}건 "
          f"(실패 {fails} + 성공 {len(attempts) - fails}), "
          f"간격 {interval:.0f}s, 출발지 {source or '기본'}, 기대: {expect}")
    if dry_run:
        for i, (ok, u) in enumerate(attempts):
            print(f"  {i+1}/{len(attempts)} {'성공' if ok else '실패'} user={u}")
        print("  (dry-run: 네트워크 호출 안 함)")
        return
    opener = build_opener(source)
    for i, (ok, u) in enumerate(attempts):
        status = login_once(opener, base_url, u, ok)
        kind = "성공" if ok else "실패"
        # 응답 받은 시각(로컬, ms). 9번째 실패 시각이 S1 조건 충족 시각의 근거가 된다(포털 원본과 대조).
        at = datetime.now().astimezone().isoformat(timespec="milliseconds")
        print(f"  {i+1}/{len(attempts)} {at} {kind} user={u} → HTTP {status}")
        if i < len(attempts) - 1:
            time.sleep(interval)


def self_test():
    for case, modes in PLANS.items():
        for mode in modes:
            attempts, _, _ = build_attempts(case, mode, "zz_a1")
            fails, succ = PLANS[case][mode][:2]
            assert sum(1 for ok, _ in attempts if not ok) == fails
            assert sum(1 for ok, _ in attempts if ok) == succ
    # 임계 충족이 미만보다 1건 많아야 한다.
    assert len(build_attempts("S1", "trigger", "u")[0]) == len(build_attempts("S1", "below", "u")[0]) + 1
    assert len(build_attempts("S4", "trigger", "u")[0]) == len(build_attempts("S4", "below", "u")[0]) + 1
    # S1 간격 하한
    assert build_attempts("S1", "trigger", "u")[1] >= 150
    # 순서 반대: 첫 시도가 성공
    assert build_attempts("S4", "reversed", "u")[0][0][0] is True
    # 창 밖: 전체 span이 창(10·30분)을 넘는다
    att, iv, _ = build_attempts("S1", "trigger", "u", window_out=True)
    assert iv * (len(att) - 1) > 30 * 60
    # 섞기: 실패가 여러 계정에 흩어지고, 어느 계정도 trigger 임계(S1 8·S4 5)에 못 미친다
    att, _, _ = build_attempts("S1", "trigger", "u", mix=3)
    per = {}
    for ok, u in att:
        if not ok:
            per[u] = per.get(u, 0) + 1
    assert len(per) == 3 and max(per.values()) <= 3
    # 출발지 지정: 로컬 서버가 본 연결 주소가 --source 값이어야 한다
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.client_address[0])
            self.send_response(204)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    build_opener("127.0.0.1").open(f"http://127.0.0.1:{srv.server_port}/", timeout=5)
    srv.server_close()
    assert seen == ["127.0.0.1"], seen
    print("self-test ok")


def main():
    p = argparse.ArgumentParser(description="S1·S4 재현")
    p.add_argument("case", nargs="?", choices=["S1", "S4"])
    all_modes = sorted(set(m for c in PLANS.values() for m in c))
    p.add_argument("--mode", choices=all_modes, default="trigger",
                   help="S1: normal/below/trigger. S4: +partial-fail/partial-success/reversed")
    p.add_argument("--base-url", default="http://10.10.10.10:5000")
    p.add_argument("--user", default="zz_a1")
    p.add_argument("--password", default="", help="성공 시도용 비밀번호(로그에 남기지 않음)")
    p.add_argument("--mix", type=int, default=1, metavar="N",
                   help="실패를 N개 계정(user, user_2…user_N)에 분산해 계정별 판정(미발동) 시험. 계정이 미리 있어야 함")
    p.add_argument("--window-out", action="store_true",
                   help="전체 간격을 창보다 길게 벌려 '시간 창 밖'(미발동) 시험")
    p.add_argument("--source", default=None, metavar="IP",
                   help="이 출발지 주소에서 요청(Kali에 붙인 주소, 예: 203.0.113.11). http만 지원")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--interval", type=float, default=None,
                   help="시도 간격(초) 강제. 로컬 기능 검증용이며 랩 실측에는 쓰지 않는다.")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.case:
        p.error("case(S1|S4)가 필요합니다 (또는 --self-test)")
    if args.mode not in PLANS[args.case]:
        p.error(f"{args.case}에는 --mode {args.mode}가 없습니다: {sorted(PLANS[args.case])}")
    if args.mix < 1:
        p.error("--mix는 1 이상")
    if args.source and not args.base_url.startswith("http://"):
        p.error("--source는 http:// 주소에만 적용됩니다")
    login_once.password = args.password
    run(args.case, args.mode, args.base_url.rstrip("/"), args.user,
        args.dry_run, args.interval, args.mix, args.window_out, args.source)


if __name__ == "__main__":
    main()
