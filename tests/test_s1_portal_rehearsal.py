"""Explicit opt-in to the separate backend environment; never install dependencies."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_real_portal_c_rehearsal_in_a_separate_process(tmp_path):
    selected = os.environ.get("ALEPH_S1_BACKEND_ROOT")
    if not selected:
        pytest.skip("Set ALEPH_S1_BACKEND_ROOT explicitly to run the real-portal rehearsal")
    backend = Path(selected).resolve()
    python = backend / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    assert python.is_file(), "The explicitly selected backend environment must be prepared first"
    output = tmp_path / "rehearsal"
    command = [str(python), str(ROOT / "tools/rehearse_s1_portal.py"),
               "--backend-root", str(backend), "--output", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    assert result.returncode == 0, result.stderr
    raw = (output / "report.json").read_bytes()
    report = json.loads(raw)
    assert report["scope"] == "in_process_real_flask_sqlite"
    assert report["actual_device_calls"] == 0 and report["network_transport_exercised"] is False
    assert report["deployment_ready"] is False and report["live_n8n_verified"] is False
    cases = {c["name"]: c for c in report["cases"]}
    assert len(cases) == 7 and all(c["passed"] for c in cases.values())
    assert cases["portal_ack_loss"]["portal_post_attempts"] == 3
    for name in ("normal", "portal_ack_loss", "record_failure", "record_ack_loss", "closed_ack"):
        case = cases[name]
        assert case["block_events"] == case["release_events"] == 1
        assert case["normal_login_during_block"] == case["final_attack_status"] == 200
        assert case["c_effect_recorded"] and case["c_restored"]
    assert cases["detected_failure"]["portal_post_attempts"] == 0
    assert cases["bad_portal_key"]["block_events"] == 0
    for sensitive in (b"synthetic-portal-key-not-live", b"synthetic-ticket-key-not-live", b"Synthetic-only-password"):
        assert sensitive not in raw
    second = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    assert second.returncode == 2 and (output / "report.json").read_bytes() == raw


def test_existing_output_is_refused_before_any_backend_import(tmp_path):
    command = [sys.executable, str(ROOT / "tools/rehearse_s1_portal.py"),
               "--backend-root", str(tmp_path / "not-a-backend"), "--output", str(tmp_path)]
    marker = tmp_path / "preserve.txt"
    marker.write_text("preserve", encoding="utf-8")
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 2 and marker.read_text(encoding="utf-8") == "preserve"
