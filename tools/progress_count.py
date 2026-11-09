"""Recount status emojis in docs/PROGRESS.md and refresh its overview table."""

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PROGRESS = ROOT / "docs" / "PROGRESS.md"
STATUSES = ("✅", "🟡", "🔵", "⬜", "⛔")
OVERVIEW_ROW = re.compile(r"^(\|[^|]*\]\(#([^)]+)\)\s*\|)\s*[^|]*\|\s*$")


def slug(heading):
    """GitHub-style heading anchor."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def section_lines(lines, anchor):
    for i, line in enumerate(lines):
        match = re.match(r"^(#+) (.*)", line)
        if match and slug(match[2]) == anchor:
            level = len(match[1])
            end = next(
                (j for j in range(i + 1, len(lines))
                 if (m := re.match(r"^(#+) ", lines[j])) and len(m[1]) <= level),
                len(lines),
            )
            return lines[i + 1:end]
    raise ValueError(f"Overview links to a missing heading: #{anchor}")


def summary(rows):
    counts = dict.fromkeys(STATUSES, 0)
    for row in rows:
        if not row.startswith("|"):
            continue
        found = [(row.find(s), s) for s in STATUSES if s in row]
        if found:
            counts[min(found)[1]] += 1
    total = sum(counts.values()) - counts["⛔"]  # 막힘·보류는 분모에서 뺌
    parts = [f"✅ {counts['✅']}/{total}"]
    parts += [f"{s} {counts[s]}" for s in STATUSES[1:] if counts[s]]
    return " · ".join(parts)


def refresh(text):
    lines = text.split("\n")
    in_overview = False
    for i, line in enumerate(lines):
        if line.startswith("## "):
            in_overview = line.strip() == "## 한눈에 보기"
        elif in_overview and (match := OVERVIEW_ROW.match(line)):
            lines[i] = f"{match[1]} {summary(section_lines(lines, match[2]))} |"
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the overview is stale")
    args = parser.parse_args()
    text = PROGRESS.read_text(encoding="utf-8")
    new = refresh(text)
    if args.check:
        if new != text:
            print("PROGRESS overview is stale; run python tools/progress_count.py")
            return 1
        print("PROGRESS overview is current")
        return 0
    PROGRESS.write_text(new, encoding="utf-8", newline="")
    print("PROGRESS overview refreshed" if new != text else "PROGRESS overview already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
