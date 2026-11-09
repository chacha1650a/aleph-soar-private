"""s7_tamper_sim.py: path/run-id validation and remote command construction only
(no network, no ssh -- this tool's whole point is to not touch anything
without --execute, so the test stays at that level)."""
import argparse
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "lab/s7/attack/s7_tamper_sim.py"
spec = importlib.util.spec_from_file_location("s7_tamper_sim", MOD_PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_run_id_accepts_the_documented_charset():
    assert m.RUN_ID_RE.match("ar-1030-01_test.1")
    assert not m.RUN_ID_RE.match("has space")
    assert not m.RUN_ID_RE.match("slash/in/id")
    assert not m.RUN_ID_RE.match("")
    assert not m.RUN_ID_RE.match("x" * 65)


@pytest.mark.parametrize("bad", ["../escape.html", "/abs/path", "a/../../b", ".."])
def test_to_web_relpath_rejects_escapes(bad):
    with pytest.raises(ValueError):
        m.to_web_relpath(bad)


def test_to_web_relpath_keeps_plain_relative_paths():
    assert m.to_web_relpath("index.html") == "index.html"
    assert m.to_web_relpath("sub/dir/file.js") == "sub/dir/file.js"


def _args(action="new", **over):
    base = dict(action=action, run_id="t-1", host="h", web_root="/web",
                manifest="/opt/baseline.sha256", target="index.html")
    base.update(over)
    return argparse.Namespace(**base)


def test_new_always_uses_the_zz_s7_run_id_filename_never_caller_input():
    cmd, touched = m.build_remote_command(_args(action="new", run_id="weird.id_1"), None)
    assert touched == "zz_s7_weird.id_1.html"
    assert "/web/zz_s7_weird.id_1.html" in cmd
    assert "chmod 644" in cmd and "sha256sum" in cmd


def test_modify_checks_the_baseline_manifest_before_writing():
    cmd, touched = m.build_remote_command(_args(action="modify", target="index.html"), "index.html")
    assert touched == "index.html"
    assert "/web/index.html" in cmd
    assert "grep -qF" in cmd and "not_in_baseline" in cmd
    assert "before=" in cmd and "after=" in cmd
