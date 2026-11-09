from tools.progress_count import PROGRESS, refresh, slug


def test_slug_matches_github_anchors():
    assert slug("1. 공통 기반 (첫 주, 10/24~)") == "1-공통-기반-첫-주-1024"
    assert slug("② B · S8·S10 스캔 → 침입 연쇄 (NIDS) — myeongjundev") == "②-b--s8s10-스캔--침입-연쇄-nids--myeongjundev"


def test_refresh_counts_nested_sections():
    text = "\n".join([
        "## 한눈에 보기",
        "| 영역 | 진행 |",
        "| --- | --- |",
        "| [전체](#전체) | old |",
        "| └ [하위](#하위) | old |",
        "## 전체",
        "| a | ✅ | 비고 ⬜ |",
        "### 하위",
        "| b | 🟡 |",
        "| c | ⬜ |",
        "| e | ⛔ |",
        "## 다른 곳",
        "| d | ✅ |",
    ])
    lines = refresh(text).split("\n")
    assert lines[3] == "| [전체](#전체) | ✅ 1/3 · 🟡 1 · ⬜ 1 · ⛔ 1 |"
    assert lines[4] == "| └ [하위](#하위) | ✅ 0/2 · 🟡 1 · ⬜ 1 · ⛔ 1 |"


def test_progress_overview_is_current():
    text = PROGRESS.read_text(encoding="utf-8")
    assert refresh(text) == text, "run python tools/progress_count.py"
