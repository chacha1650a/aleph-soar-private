"""s7_repeat_tamper.py: run-id/count validation only (no subprocess, no network)."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "lab/s7/attack/s7_repeat_tamper.py"
spec = importlib.util.spec_from_file_location("s7_repeat_tamper", MOD_PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_build_run_ids_numbers_from_01():
    assert m.build_run_ids("s7-repeat-1030", 3) == [
        "s7-repeat-1030-01", "s7-repeat-1030-02", "s7-repeat-1030-03",
    ]


def test_build_run_ids_rejects_bad_prefix_charset():
    with pytest.raises(SystemExit):
        m.build_run_ids("has space", 3)
    with pytest.raises(SystemExit):
        m.build_run_ids("slash/no", 3)


@pytest.mark.parametrize("count", [0, -1, 21, 100])
def test_build_run_ids_rejects_out_of_range_count(count):
    with pytest.raises(SystemExit):
        m.build_run_ids("s7-repeat-1030", count)


@pytest.mark.parametrize("count", [1, 5, 20])
def test_build_run_ids_accepts_in_range_count(count):
    ids = m.build_run_ids("s7-repeat-1030", count)
    assert len(ids) == count
    assert ids[-1] == f"s7-repeat-1030-{count:02d}"
