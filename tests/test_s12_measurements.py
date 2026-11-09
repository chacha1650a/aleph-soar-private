"""S12 normal-client comparison import: registration guards, sample isolation, backup tool."""
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import pytest

from ticket_store import db, s12_measurements as m, samples
from ticket_store.app import create_dashboard_app

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "contracts/s12-examples"
sys.path.insert(0, str(ROOT))
from tools.ticket_db_backup import copy_database  # noqa: E402

TICKET = "T-20261024-9002"


@pytest.fixture
def db_file(tmp_path):
    path = tmp_path / "tickets.db"
    c = db.connect(str(path))
    samples.load_samples(c)
    c.close()
    return path


@pytest.fixture
def conn(db_file):
    c = db.connect(str(db_file))
    yield c
    c.close()


@pytest.fixture
def files(tmp_path):
    for name in ("before.sample.csv", "after.sample.csv", "comparison.sample.json"):
        shutil.copy(EXAMPLES / name, tmp_path / name)
    return tmp_path


def meta_of(files, **changes):
    meta = json.loads((files / "comparison.sample.json").read_text(encoding="utf-8"))
    meta.update(changes)
    return meta


def load(files, conn, **changes):
    return m.import_comparison(conn, meta_of(files, **changes), files / "before.sample.csv", files / "after.sample.csv")


def count(conn):
    return conn.execute("SELECT count(*) FROM s12_comparisons").fetchone()[0]


def test_example_registers_and_counts_failures_in_denominator(conn, files):
    payload = load(files, conn)
    for phase in ("before", "after"):
        run = payload[phase]
        assert run["sample_count"] == run["success_count"] + run["failure_count"]
        assert "samples" not in run and len(run["sha256"]) == 64
    assert payload["success_delta_pp"] == round(payload["after"]["success_percent"] - payload["before"]["success_percent"], 3)


def test_duplicate_run_id_is_rejected_and_keeps_first(conn, files):
    load(files, conn)
    with pytest.raises(sqlite3.IntegrityError):
        load(files, conn)
    assert count(conn) == 1


def test_same_csv_for_before_and_after_is_rejected_without_insert(conn, files):
    with pytest.raises(ValueError, match="same CSV"):
        m.import_comparison(conn, meta_of(files), files / "before.sample.csv", files / "before.sample.csv")
    assert count(conn) == 0


def test_origin_must_match_ticket(conn, files):
    with pytest.raises(ValueError, match="origin"):
        load(files, conn, origin="live")
    assert count(conn) == 0


def test_attack_source_cannot_be_registered_as_normal_client(conn, files):
    for name in ("before.sample.csv", "after.sample.csv"):
        p = files / name
        p.write_text(p.read_text(encoding="utf-8").replace("203.0.113.100", "203.0.113.11"), encoding="utf-8")
    with pytest.raises(ValueError, match="attack source"):
        load(files, conn)
    assert count(conn) == 0


@pytest.mark.parametrize("change", [
    {"expected_status": 302}, {"route": "other"}, {"target": "http://u:p@10.250.0.2/x"},
    {"target": "http://10.250.0.2/x?token=1"}, {"interval_seconds": 0}, {"run_id": " padded"},
])
def test_invalid_metadata_is_rejected(conn, files, change):
    with pytest.raises(ValueError):
        load(files, conn, **change)
    assert count(conn) == 0


def test_extra_metadata_field_is_rejected(conn, files):
    with pytest.raises(ValueError, match="contract"):
        load(files, conn, secret_note="x")


@pytest.mark.parametrize("bad_row", [
    "2026-10-24T14:00:04,SAMPLE-before,203.0.113.100,200,10,",
    "2026-10-24T14:00:04+09:00,SAMPLE-before,203.0.113.100,200,-5,",
    "2026-10-24T14:00:04+09:00,SAMPLE-before,203.0.113.100,200,nan,",
    "2026-10-24T14:00:04+09:00,SAMPLE-before,203.0.113.100,0,3000,",
    "2026-10-24T14:00:04+09:00,SAMPLE-before,not-an-ip,200,10,",
    "2026-10-24T14:00:04+09:00,OTHER-label,203.0.113.100,200,10,",
    "2026-10-24T14:00:04+09:00,SAMPLE-before,203.0.113.100,200",
], ids=["no-timezone", "negative-ms", "nan-ms", "status0-no-reason", "bad-ip", "mixed-label", "missing-column"])
def test_malformed_csv_row_is_rejected_atomically(conn, files, bad_row):
    p = files / "before.sample.csv"
    p.write_text(p.read_text(encoding="utf-8").rstrip("\n") + "\n" + bad_row + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load(files, conn)
    assert count(conn) == 0


def test_out_of_order_timestamps_are_rejected(conn, files):
    p = files / "before.sample.csv"
    lines = p.read_text(encoding="utf-8").splitlines()
    lines[1], lines[2] = lines[2], lines[1]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="out-of-order"):
        load(files, conn)


def test_csv_without_source_column_is_rejected(conn, files):
    p = files / "before.sample.csv"
    rows = [line.split(",") for line in p.read_text(encoding="utf-8").splitlines()]
    p.write_text("\n".join(",".join(c for i, c in enumerate(r) if i != 2) for r in rows) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="normal-client source"):
        load(files, conn)
    assert count(conn) == 0


def test_all_failures_give_zero_percent_and_null_latency(tmp_path):
    p = tmp_path / "f.csv"
    p.write_text("ts_kst,label,source,status,ms,error\n"
                 "2026-10-24T14:00:00+09:00,L,203.0.113.100,0,3000,timeout\n"
                 "2026-10-24T14:00:02+09:00,L,203.0.113.100,0,3000,timeout\n", encoding="utf-8")
    run = m.read_run(p)
    assert run["success_percent"] == 0 and run["successful_latency_ms"]["median"] is None
    assert run["successful_latency_ms"]["p95"] is None and run["longest_failure_streak_samples"] == 2


def test_percentile_is_nearest_rank():
    assert m.percentile([], .95) is None
    assert m.percentile([1, 2, 3, 4, 5], .95) == 5
    assert m.percentile(list(range(1, 21)), .95) == 19


def test_sample_runs_hidden_unless_requested(db_file, files):
    c = db.connect(str(db_file))
    load(files, c)
    assert m.comparisons(c) == []
    assert len(m.comparisons(c, include_sample=True)) == 1
    c.close()
    client = create_dashboard_app(str(db_file), "http://127.0.0.1:8089").test_client()
    assert "S12-SAMPLE-COMPARE-01" not in client.get("/s12").get_data(as_text=True)
    assert "S12-SAMPLE-COMPARE-01" in client.get("/s12?sample=1").get_data(as_text=True)


def test_registration_does_not_change_ticket_status(conn, files):
    before = db.get_ticket(conn, TICKET)["status"]
    load(files, conn)
    assert db.get_ticket(conn, TICKET)["status"] == before


def test_cli_requires_existing_database(tmp_path, files, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["x", "--db", str(tmp_path / "missing.db"),
                                      "--metadata", str(files / "comparison.sample.json"),
                                      "--before", str(files / "before.sample.csv"),
                                      "--after", str(files / "after.sample.csv")])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2 and not (tmp_path / "missing.db").exists()


def test_backup_copies_to_new_file_and_never_overwrites(db_file, tmp_path):
    out = tmp_path / "backup.db"
    report = copy_database(db_file, out)
    assert report["ok"] and report["integrity"] == "ok" and report["counts"]["tickets"] == 6
    assert report["live_restore_performed"] is False
    with pytest.raises(ValueError, match="already exists"):
        copy_database(db_file, out)
    with pytest.raises(ValueError, match="does not exist"):
        copy_database(tmp_path / "nope.db", tmp_path / "other.db")
    assert not (tmp_path / "other.db").exists()


def test_backup_rejects_non_ticket_database_and_cleans_up(tmp_path):
    src = tmp_path / "other.db"
    sqlite3.connect(src).close()
    with pytest.raises(ValueError, match="not a ticket-store"):
        copy_database(src, tmp_path / "out.db")
    assert not (tmp_path / "out.db").exists() and src.exists()
