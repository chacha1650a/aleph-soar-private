import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import s12_baseline_calc as calc  # noqa: E402

KST = timezone(timedelta(hours=9))


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts_kst", "label", "source", "status", "ms", "error"])
        w.writerows(rows)


def make_rows(n, step=2.0, ms=100.0, start=None):
    start = start or datetime(2026, 10, 30, 9, 30, 0, tzinfo=KST)
    return [[(start + timedelta(seconds=i * step)).isoformat(timespec="milliseconds"),
             "t", "203.0.113.100", 200, ms + (i % 10), ""] for i in range(n)]


def test_summary_of_a_steady_baseline(tmp_path):
    p = tmp_path / "b.csv"
    write_csv(p, make_rows(900))
    s = calc.summarize(calc.load([p]))
    assert s["n"] == 900 and s["failed"] == 0
    assert s["p95_ms"] == 109.0 and s["max_ms"] == 109.0
    assert s["exceed_threshold_ms"] == 409.0          # max(327, 109 + 300)
    assert s["max_requests_per_60s"] == 30            # 2 s interval
    assert s["request_threshold_N"] == 90


def test_failures_are_counted_and_do_not_enter_latency(tmp_path):
    rows = make_rows(10)
    rows[3][3], rows[3][4], rows[3][5] = 0, 3000.0, "timeout"
    p = tmp_path / "b.csv"
    write_csv(p, rows)
    s = calc.summarize(calc.load([p]))
    assert s["failed"] == 1 and s["ok"] == 9 and s["max_ms"] < 1000


def test_loss_against_received_count(tmp_path):
    p = tmp_path / "b.csv"
    write_csv(p, make_rows(900))
    s = calc.summarize(calc.load([p]), received=891)
    assert s["lost"] == 9 and s["loss_pct"] == 1.0


def test_burst_sets_the_per_minute_peak(tmp_path):
    start = datetime(2026, 10, 30, 9, 30, 0, tzinfo=KST)
    rows = make_rows(5, step=10.0, start=start)
    rows += make_rows(40, step=0.5, start=start + timedelta(seconds=300))
    p = tmp_path / "b.csv"
    write_csv(p, rows)
    assert calc.summarize(calc.load([p]))["max_requests_per_60s"] == 40


def test_rejects_empty_and_all_failed(tmp_path):
    p = tmp_path / "b.csv"
    write_csv(p, [])
    with pytest.raises(SystemExit):
        calc.summarize(calc.load([p]))
    rows = make_rows(3)
    for r in rows:
        r[3] = 0
    write_csv(p, rows)
    with pytest.raises(SystemExit):
        calc.summarize(calc.load([p]))


def test_cli_prints_json(tmp_path):
    p = tmp_path / "b.csv"
    write_csv(p, make_rows(30))
    out = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "s12_baseline_calc.py"), str(p), "--received", "30"],
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out)["loss_pct"] == 0.0


def test_negative_received_is_rejected(tmp_path):
    p = tmp_path / "b.csv"
    write_csv(p, make_rows(3))
    with pytest.raises(SystemExit):
        calc.main([str(p), "--received", "-1"])


def test_slow_and_over_3000_are_listed(tmp_path):
    rows = make_rows(20)
    rows[5][4] = 3580.9               # status 200 but slower than the 3 s socket limit
    rows[8][3], rows[8][4], rows[8][5] = 0, 3037.6, "timeout"
    rows[12][4] = 1200.0
    p = tmp_path / "b.csv"
    write_csv(p, rows)
    s = calc.summarize(calc.load([p]))
    assert s["ok_over_3000ms"] == 1
    assert s["slow_ge_1000ms_or_failed"] == 3
    assert [x[1] for x in s["slow_list"]] == [200, 0, 200]


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', '-1'])
def test_invalid_latency_is_rejected(tmp_path, value):
    rows = make_rows(3)
    rows[-1][4] = value
    path = tmp_path / 'invalid.csv'
    write_csv(path, rows)
    with pytest.raises(ValueError, match='finite and nonnegative'):
        calc.load([path])


@pytest.mark.parametrize('column,value', [(1, 'other-run'), (2, '203.0.113.41')])
def test_mixed_baseline_metadata_is_rejected(tmp_path, column, value):
    rows = make_rows(3)
    rows[-1][column] = value
    path = tmp_path / 'mixed.csv'
    write_csv(path, rows)
    with pytest.raises(ValueError, match='mixed baseline'):
        calc.load([path])


def test_repeated_file_and_renamed_duplicate_are_rejected(tmp_path):
    a, b = tmp_path / 'a.csv', tmp_path / 'b.csv'
    write_csv(a, make_rows(30))
    b.write_bytes(a.read_bytes())
    with pytest.raises(ValueError, match='duplicate CSV'):
        calc.load([a, a])
    with pytest.raises(ValueError, match='duplicate or out-of-order'):
        calc.load([a, b])


def test_same_run_nonoverlapping_parts_still_work(tmp_path):
    rows = make_rows(30)
    a, b = tmp_path / 'a.csv', tmp_path / 'b.csv'
    write_csv(a, rows[:15])
    write_csv(b, rows[15:])
    result = calc.summarize(calc.load([b, a]))
    assert result['n'] == 30 and result['request_threshold_N'] == 90


def test_success_status_with_error_counts_as_failure(tmp_path):
    rows = make_rows(3)
    rows[-1][5] = 'source_mismatch'
    path = tmp_path / 'error.csv'
    write_csv(path, rows)
    result = calc.summarize(calc.load([path]))
    assert result['ok'] == 2 and result['failed'] == 1
    assert result['slow_ge_1000ms_or_failed'] == 1


def test_fast_http_error_is_in_failed_list(tmp_path):
    rows = make_rows(3)
    rows[-1][3] = 503
    path = tmp_path / 'error.csv'
    write_csv(path, rows)
    result = calc.summarize(calc.load([path]))
    assert result['failed'] == 1
    assert result['slow_ge_1000ms_or_failed'] == 1
    assert result['slow_list'][0][1] == 503


@pytest.mark.parametrize('column,value', [
    (0, '2026-10-30T09:30:05'),
    (0, '2026-10-30T09:29:59+09:00'),
    (0, '2026-10-30T09:30:00+09:00'),
    (1, ''),
    (2, '.100'),
    (3, 99),
    (3, 600),
    (3, '200.5'),
])
def test_malformed_metadata_and_status_are_rejected(tmp_path, column, value):
    rows = make_rows(3)
    rows[-1][column] = value
    path = tmp_path / 'invalid.csv'
    write_csv(path, rows)
    with pytest.raises(ValueError):
        calc.load([path])


@pytest.mark.parametrize('kind', ['missing_header', 'duplicate_header', 'missing_value', 'extra_value'])
def test_invalid_csv_structure_is_rejected(tmp_path, kind):
    path = tmp_path / 'invalid.csv'
    write_csv(path, make_rows(3))
    with path.open(newline='', encoding='utf-8') as f:
        content = list(csv.reader(f))
    if kind == 'missing_header':
        content[0][-1] = 'unknown'
    elif kind == 'duplicate_header':
        content[0][-1] = 'ms'
    elif kind == 'missing_value':
        content[-1].pop()
    else:
        content[-1].append('unexpected')
    with path.open('w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows(content)
    with pytest.raises(ValueError):
        calc.load([path])


def test_utf8_bom_and_legacy_csv_without_source_are_supported(tmp_path):
    path = tmp_path / 'legacy.csv'
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['ts_kst', 'label', 'status', 'ms', 'error'])
        writer.writerows([row[:2] + row[3:] for row in make_rows(3)])
    result = calc.summarize(calc.load([path]))
    assert result['n'] == 3 and result['ok'] == 3


def test_received_count_at_each_bound_is_valid(tmp_path):
    path = tmp_path / 'baseline.csv'
    write_csv(path, make_rows(3))
    rows = calc.load([path])
    assert calc.summarize(rows, received=0)['loss_pct'] == 100.0
    assert calc.summarize(rows, received=3)['loss_pct'] == 0.0


@pytest.mark.parametrize('received', [-1, 31, True])
def test_invalid_unique_received_count_is_rejected(tmp_path, received):
    path = tmp_path / 'count.csv'
    write_csv(path, make_rows(30))
    with pytest.raises(SystemExit, match='unique request count'):
        calc.summarize(calc.load([path]), received)


def test_invalid_cli_emits_no_result_json(tmp_path):
    rows = make_rows(3)
    rows[-1][4] = 'Infinity'
    path = tmp_path / 'invalid.csv'
    write_csv(path, rows)
    result = subprocess.run([sys.executable, str(ROOT / 'tools/s12_baseline_calc.py'), str(path)],
                            capture_output=True, text=True)
    assert result.returncode != 0 and not result.stdout.strip()
