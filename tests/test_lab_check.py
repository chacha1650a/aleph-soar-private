"""Offline evidence semantics, CLI isolation and immutable bundle regressions."""

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.lab_check import main
from tools.lab_checks.compare import compare
from tools.lab_checks.models import FORMATS, LabError, MAX_BYTES, ROOT, digest, instant, policy, read_json, validate_receipt
from tools.lab_checks.store import publish, receipts_from_inbox, verified_document

FIXTURES = Path(__file__).parent / "lab_check_fixtures"
NOW = instant("2026-10-23T17:00:02+09:00")


def example(name="s10"):
    path = FIXTURES / name
    return read_json(path / "card.json"), [read_json(p) for p in sorted(path.glob("*.export.json"))], read_json(path / "input.json")


def check(receipts, check_id):
    return next(c for receipt in receipts for c in receipt["checks"] if c["check_id"] == check_id)


def row(result, check_id):
    return next(r for r in result["rows"] if r["check_id"] == check_id)


def run(card, receipts, input_data=None, phase="final", now=NOW):
    return compare(card, receipts, phase, input_data, now)


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("name", ["s10", "s8-baseline", "s8-postchange"])
def test_synthetic_profiles_match_without_authorizing_live_input_or_final_completion(name):
    card, receipts, input_data = example(name)
    result = run(card, receipts, input_data)
    assert result["status"] == "matched"
    assert result["exit_code"] == 0
    assert result["ready_candidate"] is False
    assert result["final_complete"] is False
    assert result["readiness_reason"] == "REPLAY_ONLY"
    assert len(result["receipt_sha256"]) == len(receipts)
    assert result["input_sha256"] == digest(input_data)


def test_narrow_s10_scope_needs_only_b_and_d():
    card, receipts, input_data = example()
    result = run(card, receipts, input_data)
    assert {r["seat"] for r in result["rows"]} == {"B", "D"}
    assert result["scope"] == "normalization_only"
    missing_d = run(card, receipts[:1], input_data)
    assert row(missing_d, "B.raw")["verdict"] == "pass"
    assert row(missing_d, "D.received")["reason_code"] == "MISSING_RECEIPT"
    assert missing_d["exit_code"] == 3


def test_raw_receipt_and_normalization_are_independent():
    card, receipts, input_data = example()
    check(receipts, "D.normalized")["events"][0]["fields"]["action"] = "pass"
    result = run(card, receipts, input_data)
    assert row(result, "D.received")["verdict"] == "pass"
    assert row(result, "D.normalized")["reason_code"] == "NORMALIZATION_MISMATCH"
    assert result["exit_code"] == 4


@pytest.mark.parametrize("defect", ["missing", "duplicate", "extra", "source", "timestamp"])
def test_event_identity_defects_do_not_pass(defect):
    card, receipts, input_data = example()
    events = check(receipts, "D.received")["events"]
    if defect == "missing":
        events.clear()
    elif defect == "duplicate":
        events.append(copy.deepcopy(events[0]))
    elif defect == "extra":
        extra = copy.deepcopy(events[0])
        extra["key"] = "extra-synthetic"
        events.append(extra)
    elif defect == "source":
        events[0]["src_ip"] = "203.0.113.22"
    else:
        events[0]["at"] = "2026-10-23T10:00:01+09:00"
    assert run(card, receipts, input_data)["exit_code"] == 4


def test_unavailable_store_and_undefined_definition_never_become_zero_or_function_success():
    card, receipts, input_data = example("s8-baseline")
    result = run(card, receipts, input_data)
    assert row(result, "C.store")["verdict"] == "pass"
    tickets = row(result, "C.tickets")
    assert tickets["verdict"] == "not_applicable"
    assert tickets["count"] is None
    assert "UNVERIFIED" in tickets["reason_code"]
    assert row(result, "D.definition")["count"] is None
    check(receipts, "D.definition")["definition_state"] = "active"
    assert run(card, receipts, input_data)["exit_code"] == 4


def test_zero_requires_complete_available_query_and_active_or_inapplicable_definition():
    card, receipts, _ = example("s8-baseline")
    for cid, changes in [("C.tickets", {"count": 0}), ("D.definition", {"count": 0}),
                         ("B.input", {"query_status": "failed"}), ("B.input", {"coverage": "partial"})]:
        changed = copy.deepcopy(receipts)
        check(changed, cid).update(changes)
        with pytest.raises(LabError, match="Unconfirmed count"):
            for receipt in changed:
                validate_receipt(card, receipt)


def test_later_dry_run_is_excluded_from_baseline_window_but_same_window_execution_is_reported():
    card, receipts, input_data = example("s8-baseline")
    result = run(card, receipts, input_data)
    assert row(result, "D.n8n")["count"] == 0
    assert row(result, "D.n8n")["excluded_count"] == 1
    check(receipts, "D.n8n")["executions"][0]["at"] = "2026-10-23T10:01:00+09:00"
    assert run(card, receipts, input_data)["exit_code"] == 4


@pytest.mark.parametrize("changes,expected", [
    ({"dry_run": True, "http_executed": False}, 4),
    ({"dry_run": None}, 3),
    ({"http_executed": False}, 4),
    ({"http_status": 200, "target_effect": None}, 3),
    ({"http_status": 503}, 4),
    ({"target_effect": False}, 4),
])
def test_postchange_dry_run_http_and_effect_are_separate(changes, expected):
    card, receipts, input_data = example("s8-postchange")
    check(receipts, "D.n8n")["executions"][0].update(changes)
    assert run(card, receipts, input_data)["exit_code"] == expected


def test_postchange_requires_actual_target_and_restoration_evidence():
    card, receipts, input_data = example("s8-postchange")
    check(receipts, "A.restored")["value"] = None
    result = run(card, receipts, input_data)
    assert row(result, "D.n8n")["verdict"] == "pass"
    assert row(result, "A.restored")["verdict"] == "unknown"
    assert result["exit_code"] == 3


@pytest.mark.parametrize("change,reason", [
    ({"vantage_id": "boundary-host"}, "VANTAGE_UNVERIFIED"),
    ({"version": "changed-v2"}, "VERSION_CHANGED"),
    ({"clock_uncertainty_seconds": None}, "CLOCK_UNKNOWN"),
    ({"query_end": "2026-10-23T10:01:00+09:00"}, "QUERY_WINDOW_INCOMPLETE"),
    ({"observed_at": "2026-10-23T10:00:03+09:00"}, "OBSERVATION_PENDING"),
])
def test_wrong_vantage_versions_and_partial_timing_hold_only_affected_results(change, reason):
    card, receipts, input_data = example()
    receipts[1].update(change)
    result = run(card, receipts, input_data)
    assert row(result, "B.raw")["verdict"] == "pass"
    assert row(result, "D.received")["reason_code"] == reason
    assert row(result, "D.received")["count"] is None
    assert result["exit_code"] == 3


def test_input_count_mismatch_observation_pending_missing_input_and_boundary_uncertainty():
    card, receipts, input_data = example()
    assert run(card, receipts)["exit_code"] == 3
    assert run(card, receipts, input_data, now=instant("2026-10-23T10:01:00+09:00"))["exit_code"] == 3
    input_data["count"] = 2
    assert row(run(card, receipts, input_data), "input.count")["reason_code"] == "INPUT_COUNT_MISMATCH"
    input_data["count"] = 1
    for receipt in receipts:
        receipt["clock_uncertainty_seconds"] = 1
        receipt["query_start"] = "2026-10-23T09:59:00+09:00"
    assert row(run(card, receipts, input_data), "B.raw")["reason_code"] == "CLOCK_BOUNDARY_AMBIGUOUS"


@pytest.mark.parametrize("defect", ["card", "environment", "origin", "duplicate", "phase", "input_source"])
def test_cross_run_environment_phase_and_conflicting_receipts_fail_validation(defect):
    card, receipts, input_data = example()
    if defect == "card":
        receipts[0]["card_sha256"] = "0" * 64
    elif defect == "environment":
        receipts[0]["environment"] = "lab"
    elif defect == "origin":
        receipts[0]["origin"] = "direct"
    elif defect == "duplicate":
        receipts.append(copy.deepcopy(receipts[0]))
    elif defect == "phase":
        receipts[0]["phase"] = "prepare"
    else:
        input_data["source_ip"] = "203.0.113.22"
    with pytest.raises(LabError):
        run(card, receipts, input_data)


def test_profile_minima_and_card_dates_cannot_be_weakened():
    card, _, _ = example()
    for changed in [dict(card, required_checks=["B.raw"]), dict(card, profile_id="unknown-v1"),
                    dict(card, policy_sha256="0" * 64),
                    dict(card, reviewer="B"), dict(card, input_end=card["input_start"]),
                    dict(card, observation_end="2026-10-23T10:00:00"), dict(card, run_id="../outside")]:
        with pytest.raises(LabError):
            policy(changed)


def test_preparation_staleness_and_lab_exports_never_authorize_live_input():
    card, receipts, _ = example()
    for receipt in receipts:
        receipt["phase"] = "prepare"
    stale = run(card, receipts, phase="prepare", now=instant("2026-10-23T17:02:00+09:00"))
    assert all(r["reason_code"] == "STALE_PREPARATION" for r in stale["rows"])
    card["environment"] = "lab"
    for receipt in receipts:
        receipt.update(environment="lab", origin="reported", card_sha256=digest(card))
    result = run(card, receipts, phase="prepare")
    assert result["status"] == "matched"
    assert result["ready_candidate"] is False
    assert result["readiness_reason"] == "OFFLINE_EXPORT_UNVERIFIED"


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{bad'])
def test_noncanonical_json_inputs_are_rejected_without_echoing_values(tmp_path, text):
    path = tmp_path / "unsafe.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(LabError):
        read_json(path)


def test_oversized_json_schema_and_extra_secret_fields_are_rejected(tmp_path, capsys):
    path = tmp_path / "large.json"
    path.write_bytes(b" " * (MAX_BYTES + 1))
    with pytest.raises(LabError, match="size limit"):
        read_json(path)
    card, _, _ = example()
    card["password"] = "do-not-print-this-test-value"
    write(path, card)
    assert main(["--run-root", str(tmp_path / "out"), "prepare", "--card", str(path), "--out", "bad"]) == 2
    captured = capsys.readouterr()
    assert "do-not-print" not in captured.err + captured.out
    assert not (tmp_path / "out").exists()


def test_store_manifest_integrity_overwrite_partial_attempt_and_path_escape(tmp_path):
    card, receipts, _ = example()
    saved = publish(tmp_path, "card", {"card.json": card})
    original = (saved / "card.json").read_bytes()
    with pytest.raises(LabError, match="already exists"):
        publish(tmp_path, "card", {"card.json": {}})
    assert (saved / "card.json").read_bytes() == original
    for relative in ("../outside", "/outside", "C:/outside", "one/../outside", "one\\outside"):
        with pytest.raises(LabError):
            publish(tmp_path, relative, {"card.json": card})
    (saved / "card.json").write_bytes(original + b" ")
    with pytest.raises(LabError, match="checksum"):
        verified_document(saved, "card.json")
    inbox = tmp_path / "inbox"
    (inbox / "unfinished").mkdir(parents=True)
    write(inbox / "unfinished/receipt.json", receipts[0])
    assert receipts_from_inbox(inbox) == []


def test_output_symlink_is_rejected_when_platform_supports_it(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "root/link"
    link.parent.mkdir()
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires local OS support/permission")
    with pytest.raises(LabError, match="Symlinks"):
        publish(link.parent, "link/new", {"card.json": {}})
    assert not list(outside.iterdir())


def test_full_cli_from_another_directory_uses_file_exports_and_preserves_source_bytes(tmp_path):
    root = tmp_path / "runs"
    fixture = FIXTURES / "s10"
    before = {p: p.read_bytes() for p in fixture.iterdir() if p.is_file()}

    def cli(*arguments, expected=0):
        result = subprocess.run([sys.executable, str(ROOT / "tools/lab_check.py"), "--run-root", str(root), *arguments],
                                cwd=tmp_path, capture_output=True, encoding="utf-8")
        assert result.returncode == expected, result.stderr
        return result

    cli("prepare", "--card", str(fixture / "card.json"), "--out", "s10")
    card = str(root / "s10/card.json")
    for seat in "BD":
        cli("collect", "--card", card, "--seat", seat, "--phase", "final", "--input", str(fixture / "input.json"),
            "--profile", str(fixture / f"{seat}.profile.json"), "--out", f"s10/inbox/{seat}")
    cli("compare", "--card", card, "--phase", "final", "--input", str(fixture / "input.json"),
        "--receipts", str(root / "s10/inbox"), "--out", "s10/final")
    result = verified_document(root / "s10/final", "comparison.json")
    assert result["status"] == "matched" and not result["ready_candidate"]
    assert "읽기 전용" in (root / "s10/final/report.md").read_text(encoding="utf-8")
    assert all(path.read_bytes() == content for path, content in before.items())
    cli("prepare", "--card", str(fixture / "card.json"), "--out", "s10", expected=2)


def test_missing_collector_configuration_emits_incomplete_receipt_not_zero(tmp_path):
    card, _, input_data = example()
    prepared = publish(tmp_path, "prepared", {"card.json": card})
    input_path = write(tmp_path / "input.json", input_data)
    result = main(["--run-root", str(tmp_path), "collect", "--card", str(prepared / "card.json"),
                   "--seat", "D", "--phase", "final", "--input", str(input_path), "--out", "inbox/D"])
    assert result == 3
    receipt = verified_document(tmp_path / "inbox/D", "receipt.json")
    assert all(c["count"] is None and c["reason_code"] == "NOT_CONFIGURED" for c in receipt["checks"])


def test_schemas_are_self_contained_and_valid():
    from jsonschema import Draft202012Validator

    for path in FORMATS.glob("*.schema.json"):
        schema = read_json(path)
        Draft202012Validator.check_schema(schema)
        assert "$ref" not in json.dumps(schema)  # No remote schema retrieval during validation.
