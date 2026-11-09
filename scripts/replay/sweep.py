#!/usr/bin/env python3
"""S1·S4 임계값 스윕 — 오프라인 룰 로직 재생 (A whiteclover0542).

정상 패턴 정의서(N1~N5, 알려진 오탐 F3·F4)와 공격 입력(S1·S4 trigger/below)을
합성 이벤트로 만들고, Graylog 이벤트 정의의 판정 로직만 Python으로 재생해
임계값(>5/>8/>12)·창(10/30/60분)별 탐지·오탐을 표로 낸다.

이것은 **룰 판정 재생**이지 실시간 실측이 아니다. 여기 숫자는 "정의한 정상
패턴 기준"이며, 실시간 MTTD·검색 주기와 분리해 적는다(작업순서 지표 계산).
패턴·임계값이 바뀌면 A-S1-S4-정상패턴.md(룰 정의)·예상질문 Q1과 같이 고친다.

사용:
  python sweep.py              # S1·S4 스윕 표 출력(마크다운)
  python sweep.py --self-test  # 판정기 점검
"""
import argparse

F, S = "login-bruteforce", "login-success"  # 실패(401)·성공(200). 429는 룰 전에 제외(정상패턴 §1).


def seq(kinds, span_min):
    """kinds를 span_min(분)에 고르게 배치한 (t초, rule) 목록."""
    n = len(kinds)
    step = span_min * 60 / (n - 1) if n > 1 else 0
    return [(round(i * step), k) for i, k in enumerate(kinds)]


def seq2(kinds, span_min, offset_min):  # N5용: 뒤쪽 버스트를 offset만큼 민다
    return [(t + offset_min * 60, r) for t, r in seq(kinds, span_min)]


def fires(group_events, threshold, window_sec, count_rules, two_rules):
    """한 그룹(username+src_ip)의 (t, rule) 목록에 룰을 재생. 발동하면 True.

    count_rules에 든 rule만 센다(S1은 {login-bruteforce}=실패만, S4는 둘 다).
    각 이벤트를 창의 끝으로 보고 (end-window, end]의 count()>threshold를 본다.
    two_rules면 그 창 안 rule 종류 card()>1도 요구한다(S4). count는 strictly >.
    """
    ev = sorted((t, r) for t, r in group_events if r in count_rules)
    for end, _ in ev:
        win = [(t, r) for t, r in ev if end - window_sec < t <= end]
        if len(win) > threshold and (not two_rules or len({r for _, r in win}) > 1):
            return True
    return False


def scenario_fires(groups, threshold, window_sec, count_rules, two_rules):
    """시나리오는 그룹이 여러 개일 수 있다(N3 계정 5·N4 출발지 2). 한 그룹이라도 발동하면 발동."""
    return any(fires(ev, threshold, window_sec, count_rules, two_rules) for ev in groups.values())


# 시나리오: (이름, 라벨, {그룹키: [(t,rule)…]}). 라벨 attack=발동해야, normal=발동 안 해야.
# 공격·정상 입력 모두 정상패턴 정의서·공격 시나리오 입력표의 값을 따른다.
def one(kinds, span):  # 한 그룹 시나리오
    return {"g": seq(kinds, span)}


S1_SCENARIOS = [
    # 공격: 저속 브루트포스. 실패만. trigger 9회·below 8회를 약 24분에 분산(보강 전 실측 ~27분).
    ("S1-trigger (실패 9/약 24분)", "attack", one([F] * 9, 24)),
    ("S1-below (실패 8/약 24분)",   "normal", one([F] * 8, 24)),  # 경계 바로 아래, 발동 안 해야
    # 정상: N2 오타 뒤 성공, N5 창 밖 재로그인(30분에 N2 2회, 실패 4)
    ("N2 (실패 3+성공 1)",        "normal", one([F, F, F, S], 2)),
    ("N5 (30분에 N2 2회, 실패 4)", "normal", {"g": seq([F, F, S], 2) + seq2([F, F, S], 2, offset_min=18)}),
    # N3 사무실 공유 IP: 계정 5개가 각자 N2(실패 2) — 그룹이 계정별로 갈려 발동 안 해야
    ("N3 (계정 5개 각 실패 2)",   "normal", {f"u{i}": seq([F, F, S], 2) for i in range(5)}),
    # 알려진 오탐 F4: 30분에 N2 3회 = 실패 9 (정상패턴 정의서 F4)
    ("F4 (30분 실패 9, 알려진 오탐)", "normal", {"g": seq([F, F, F] * 3, 28)}),
]

S4_SCENARIOS = [
    # 공격: 실패 뒤 성공. trigger 실패5+성공1(합계6)·below 실패4+성공1(합계5)을 약 8분에.
    ("S4-trigger (실패 5+성공 1/약 8분)", "attack", one([F] * 5 + [S], 8)),
    ("S4-below (실패 4+성공 1/약 8분)",   "normal", one([F] * 4 + [S], 8)),  # 합계 5, 발동 안 해야
    # 정상: N1 바로 성공(종류 1개), N2 오타 뒤 성공(합계 ≤5)
    ("N1 (성공 1)",                "normal", one([S], 0)),
    ("N2 (실패 3+성공 1)",         "normal", one([F, F, F, S], 2)),
    # 알려진 오탐 F3: 오타 5회 뒤 성공(합계 6)을 2분 안에 — 비번 변경 직후·Caps Lock
    ("F3 (실패 5+성공 1/2분, 알려진 오탐)", "normal", one([F] * 5 + [S], 2)),
]


def sweep(scenarios, windows_min, thresholds, count_rules, two_rules, title):
    out = [f"### {title}", "",
           "| 창\\임계 | " + " | ".join(f">{t}" for t in thresholds) + " |",
           "| --- | " + " | ".join("---" for _ in thresholds) + " |"]
    attacks = [s for s in scenarios if s[1] == "attack"]
    normals = [s for s in scenarios if s[1] == "normal"]
    for w in windows_min:
        cells = []
        for t in thresholds:
            det = sum(scenario_fires(g, t, w * 60, count_rules, two_rules) for _, _, g in attacks)
            fp = sum(scenario_fires(g, t, w * 60, count_rules, two_rules) for _, _, g in normals)
            cells.append(f"탐지 {det}/{len(attacks)}, 오탐 {fp}/{len(normals)}")
        out.append(f"| {w}분 | " + " | ".join(cells) + " |")
    # 오탐을 낸 정상 시나리오를 임계·창별로 밝힌다(어느 패턴이 경계인지).
    out.append("")
    for w in windows_min:
        for t in thresholds:
            hit = [name for name, lbl, g in normals if scenario_fires(g, t, w * 60, count_rules, two_rules)]
            if hit:
                out.append(f"- {w}분/>{t} 오탐: {', '.join(hit)}")
    return "\n".join(out)


def self_test():
    S1R, S4R = {F}, {F, S}
    # S1: 실패만 센다. 창 안 count>threshold
    assert fires(seq([F] * 9, 24), 8, 30 * 60, S1R, False) is True       # 9>8, 30분 창에 다 들어옴
    assert fires(seq([F] * 9, 24), 8, 10 * 60, S1R, False) is False      # 10분 창엔 일부만 → 9 못 채움
    assert fires(seq([F] * 8, 24), 8, 30 * 60, S1R, False) is False      # 8은 >8 아님
    # S1은 성공을 세지 않는다: 실패 4+성공 2는 >5가 안 됨(성공 제외)
    assert fires(seq([F, F, S], 2) + seq2([F, F, S], 2, 18), 5, 30 * 60, S1R, False) is False
    # S4: 둘 다 세고 card(rule)>1 필요
    assert fires(seq([F] * 6, 8), 5, 10 * 60, S4R, True) is False        # 실패만 → 종류 1개
    assert fires(seq([F] * 5 + [S], 8), 5, 10 * 60, S4R, True) is True   # 6>5, 종류 2개
    assert fires(seq([F] * 4 + [S], 8), 5, 10 * 60, S4R, True) is False  # 합계 5
    # 그룹 분리: 두 계정이 각자 적게 → 발동 안 함
    g = {"a": seq([F, F, F], 2), "b": seq([F, F, F], 2)}
    assert scenario_fires(g, 5, 30 * 60, S1R, False) is False
    print("self-test ok")


def main():
    p = argparse.ArgumentParser(description="S1·S4 임계값 스윕(오프라인 룰 재생)")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--windows", default="10,30,60", help="창(분) 콤마구분")
    p.add_argument("--thresholds", default="5,8,12", help="count() 임계 콤마구분")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    windows = [int(x) for x in args.windows.split(",")]
    thresholds = [int(x) for x in args.thresholds.split(",")]
    print("# S1·S4 임계값 스윕 (오프라인 룰 로직 재생, 실시간 MTTD 아님)\n")
    print("> 셀: 탐지(공격 발동/공격 전체), 오탐(정상 발동/정상 전체). count는 strictly >.\n")
    print(sweep(S1_SCENARIOS, windows, thresholds, {F}, False,
                "S1 (login-bruteforce 실패만, username+src_ip)"))
    print()
    print(sweep(S4_SCENARIOS, windows, thresholds, {F, S}, True,
                "S4 (login-* card(rule)>1, username+src_ip)"))


if __name__ == "__main__":
    main()
