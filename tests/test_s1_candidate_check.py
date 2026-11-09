"""Source packet drift and call graph failures cannot become deployment success."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tools.check_s1_candidate import check, PACKET

ROOT = Path(__file__).resolve().parents[1]
S1 = "infra/n8n/workflows/haedam-30-s1-main.json"


@pytest.fixture
def bundle(tmp_path):
    packet = json.loads((ROOT / PACKET).read_text(encoding="utf-8"))
    for relative in [PACKET, *[r["path"] for r in packet["n8n_exports"]],
                     *["services/ticket-store/ticket_store/" + n for n in packet["ticket_source_sha256"]]]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def write_packet(root, mutate):
    path = root / PACKET
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def change_workflow(root, mutate):
    path = root / S1
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value[0])
    path.write_text(json.dumps(value), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    write_packet(root, lambda p: next(r for r in p["n8n_exports"] if r["path"] == S1).update(sha256=digest))


def test_real_candidate_matches_but_auth_and_all_runtime_results_stay_pending(bundle):
    before = {p: p.read_bytes() for p in bundle.rglob("*") if p.is_file()}
    report = check(bundle)
    assert report["exit_code"] == 0 and report["state"] == "SOURCE_MATCH_RUNTIME_PENDING"
    assert report["summary"] == {"workflow_files": 19, "ticket_source_files": 6,
                                 "s1_workflow_files": 4, "s1_webhooks": 1, "auth_findings": 1}
    assert report["runtime_verified"] is False and report["deployment_ready"] is False
    assert len(report["pending"]) == 6
    assert before == {p: p.read_bytes() for p in bundle.rglob("*") if p.is_file()}


def test_integration_packet_scope_preserves_legacy_and_cannot_assert_runtime_success(bundle):
    for scope in ('integration_candidate_sources', 'home_candidate_sources'):
        write_packet(bundle, lambda p: p.update(scope=scope))
        result = check(bundle)
        assert result['exit_code'] == 0
        assert result['runtime_verified'] is result['deployment_ready'] is False
    write_packet(bundle, lambda p: p.update(scope='integration_candidate_sources', runtime_verified=True))
    assert check(bundle)['exit_code'] == 2


@pytest.mark.parametrize("relative", [S1, "services/ticket-store/ticket_store/core.py"])
def test_even_valid_content_edits_are_mismatches(bundle, relative):
    path = bundle / relative
    path.write_bytes(path.read_bytes() + b"\n")
    report = check(bundle)
    assert report["exit_code"] == 4 and any("HASH_MISMATCH" in e for e in report["errors"])
    assert report["deployment_ready"] is False


def test_extra_and_missing_exports_are_not_silently_ignored(bundle):
    (bundle / "infra/n8n/workflows/extra.json").write_text("[]", encoding="utf-8")
    assert check(bundle)["exit_code"] == 4
    (bundle / S1).unlink()
    assert check(bundle)["exit_code"] == 2


@pytest.mark.parametrize("target", ["missing-workflow", "={{ dangerous }}", 123])
def test_changed_packet_hash_cannot_hide_unresolved_calls(bundle, target):
    def mutate(workflow):
        node = next(n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.executeWorkflow")
        node["parameters"]["workflowId"] = target
    change_workflow(bundle, mutate)
    result = check(bundle)
    assert result["exit_code"] == 4 and "WORKFLOW_REFERENCE_UNRESOLVED" in result["errors"]


def test_cycles_and_incomplete_dependency_lists_are_not_a_complete_packet(bundle):
    def mutate(workflow):
        node = next(n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.executeWorkflow")
        node["parameters"]["workflowId"] = workflow["id"]
    change_workflow(bundle, mutate)
    assert "WORKFLOW_CALL_CYCLE" in check(bundle)["errors"]
    write_packet(bundle, lambda p: p["s1_workflow_dependencies"].pop())
    assert "S1_DEPENDENCY_MISMATCH" in check(bundle)["errors"]


def test_duplicate_ids_and_missing_webhook_are_rejected(bundle):
    def mutate(workflow):
        workflow["id"] = "haedamResultLog01"
    change_workflow(bundle, mutate)
    assert check(bundle)["exit_code"] == 2


def test_missing_webhook_cannot_be_declared_as_a_usable_s1_entry(bundle):
    change_workflow(bundle, lambda w: w.update(nodes=[n for n in w["nodes"] if n["type"] != "n8n-nodes-base.webhook"]))
    assert "S1_WEBHOOK_MISSING" in check(bundle)["errors"]


@pytest.mark.parametrize("change", [
    lambda p: p.update(runtime_verified=True),
    lambda p: p["n8n_exports"].append(p["n8n_exports"][0]),
    lambda p: p["n8n_exports"][0].update(path="../../sensitive.json"),
    lambda p: p["ticket_source_sha256"].update({"../../sensitive.json": "a" * 64}),
    lambda p: p.update(s1_workflow_dependencies=[]),
    lambda p: p["n8n_exports"][0].update(sha256="invalid"),
])
def test_invalid_or_unsafe_packet_is_not_a_source_match(bundle, change):
    write_packet(bundle, change)
    assert check(bundle)["exit_code"] == 2


@pytest.mark.parametrize("raw", [b"", b"[]", b"{}", b"null", b'{"a":1,"a":2}', b'{"a":NaN}'])
def test_bad_packet_cannot_be_zero_findings(bundle, raw):
    (bundle / PACKET).write_bytes(raw)
    assert check(bundle)["exit_code"] == 2


def test_cli_never_echoes_values_paths_or_parse_errors(bundle):
    canary = "synthetic-sensitive-canary-packet"
    (bundle / PACKET).write_text('{"secret":"' + canary + '", invalid', encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "tools/check_s1_candidate.py"), "--root", str(bundle)],
                            capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 2 and canary not in result.stdout + result.stderr
    assert str(bundle) not in result.stdout + result.stderr
    assert json.loads(result.stdout)["deployment_ready"] is False


def test_packet_cannot_read_outside_the_explicit_root(bundle):
    assert check(bundle, "../outside.json")["exit_code"] == 2


def test_path_resolution_failure_is_safe_and_incomplete(bundle, monkeypatch):
    original = Path.resolve

    def fail(path, *args, **kwargs):
        if path.name == "haedam-30-s1-main.json":
            raise RuntimeError("sensitive-symlink-loop-path")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fail)
    report = check(bundle)
    assert report["exit_code"] == 2
    assert "sensitive-symlink-loop-path" not in json.dumps(report)


def test_default_packet_is_current_and_legacy_packet_is_preserved_unmodified():
    from tools.check_s1_candidate import LEGACY_PACKET
    current = json.loads((ROOT / PACKET).read_text(encoding="utf-8"))
    assert "20261030" in PACKET and "20261028" in LEGACY_PACKET
    assert current["previous_packet"] == LEGACY_PACKET and (ROOT / LEGACY_PACKET).is_file()
    assert current["runtime_verified"] is False
    assert all(value is None for value in current["school_observations"].values())
    # The 10/28 record keeps the hashes that were true that day; it must not be re-pinned.
    legacy = json.loads((ROOT / LEGACY_PACKET).read_text(encoding="utf-8"))
    assert legacy["ticket_source_sha256"]["db.py"] == "7958027bcc8f9810d98d828b1506302c43413184f1accfb336ac653e8d07779d"
    # haedam-20 was edited on 10/30 (baseline_ms); the 10/28 packet pins the old export, so it also reports the workflow hash.
    # haedam-34 (S7 live copy) was added on 11/02, so the 10/28 inventory no longer matches either.
    assert sorted(check(ROOT, LEGACY_PACKET)["errors"]) == ["TICKET_SOURCE_HASH_MISMATCH", "WORKFLOW_HASH_MISMATCH",
                                                            "WORKFLOW_INVENTORY_MISMATCH"]
