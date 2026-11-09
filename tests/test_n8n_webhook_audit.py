"""Static auth inventory boundaries; no n8n engine, HTTP or credential lookup."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.check_n8n_webhooks import audit

ROOT = Path(__file__).resolve().parents[1]


def webhook(**changes):
    return {"type": "n8n-nodes-base.webhook", "parameters": {}, **changes}


def write(folder, nodes, **changes):
    source = folder / "input.json"
    source.write_text(json.dumps({"active": False, "nodes": nodes, **changes}), encoding="utf-8")
    return source


@pytest.mark.parametrize("active,disabled", [(False, False), (True, False), (False, True)])
def test_inactive_and_disabled_nodes_still_need_inbound_auth(tmp_path, active, disabled):
    write(tmp_path, [webhook(disabled=disabled, parameters={"options": {"ipWhitelist": "127.0.0.1"}}),
                     {"type": "n8n-nodes-base.httpRequest", "parameters": {"authentication": "genericCredentialType"},
                      "credentials": {"httpHeaderAuth": {"id": "outbound-key"}}}], active=active)
    report = audit(tmp_path, expected_webhooks=1)
    assert report["exit_code"] == 1
    assert report["webhooks"][0]["status"] == "AUTH_NOT_CONFIGURED"
    assert report["summary"]["webhooks"] == 1


@pytest.mark.parametrize("mode,credential", [("headerAuth", "httpHeaderAuth"),
                                             ("basicAuth", "httpBasicAuth"), ("jwtAuth", "jwtAuth")])
def test_correct_reference_is_only_a_declaration_not_runtime_verification(tmp_path, mode, credential):
    write(tmp_path, [webhook(parameters={"authentication": mode}, credentials={credential: {"id": "local-ref"}})])
    report = audit(tmp_path)
    assert report["exit_code"] == 0 and report["runtime_verified"] is False
    assert report["summary"]["declared_unverified"] == 1
    assert report["webhooks"][0]["status"] == "DECLARED_UNVERIFIED"


@pytest.mark.parametrize("credentials", [None, {}, {"httpBasicAuth": {"id": "wrong-type"}},
    {"httpHeaderAuth": {}}, {"httpHeaderAuth": {"name": "unresolved-name"}},
    {"httpHeaderAuth": {"id": ""}}, {"httpHeaderAuth": {"id": "={{ $env.ID }}"}}])
def test_auth_mode_alone_or_wrong_credential_never_passes(tmp_path, credentials):
    write(tmp_path, [webhook(parameters={"authentication": "headerAuth"}, credentials=credentials)])
    report = audit(tmp_path)
    assert report["exit_code"] == 1
    assert report["webhooks"][0]["status"] == "CREDENTIAL_REFERENCE_UNRESOLVED"


@pytest.mark.parametrize("mode", [None, "", "none", "={{ 'headerAuth' }}", "n8nOAuth2", [], {}])
def test_absent_dynamic_or_unreviewed_auth_is_not_assumed_safe(tmp_path, mode):
    write(tmp_path, [webhook(parameters={"authentication": mode})])
    assert audit(tmp_path)["exit_code"] == 1


@pytest.mark.parametrize("raw", [b"", b"\xff", b"not-json", b"[]", b"{}", b"null",
    b'{"nodes":[]}', b'{"nodes":[null]}', b'{"nodes":[{"type":"n8n-nodes-base.webhook","parameters":null}]}',
    b'{"nodes":[],"nodes":[]}', b'{"nodes":[],"value":NaN}'])
def test_invalid_or_empty_exports_are_incomplete_even_beside_a_valid_export(tmp_path, raw):
    write(tmp_path, [webhook(parameters={"authentication": "headerAuth"},
                           credentials={"httpHeaderAuth": {"id": "valid-declaration"}})])
    (tmp_path / "bad.json").write_bytes(raw)
    report = audit(tmp_path)
    assert report["exit_code"] == 2 and report["summary"]["input_errors"] > 0


def test_missing_folder_empty_folder_no_webhooks_and_partial_inventory_are_not_zero_findings(tmp_path):
    assert audit(tmp_path / "absent")["exit_code"] == 2
    assert audit(tmp_path)["exit_code"] == 2
    write(tmp_path, [{"type": "n8n-nodes-base.executeWorkflowTrigger"}])
    assert audit(tmp_path)["exit_code"] == 2
    write(tmp_path, [webhook()])
    assert audit(tmp_path, expected_webhooks=2)["exit_code"] == 2


def test_bom_multi_workflow_exports_include_every_webhook(tmp_path):
    source = tmp_path / "exports.json"
    source.write_text(json.dumps([{"nodes": [webhook(), webhook()]}, {"nodes": [webhook()]}]), encoding="utf-8-sig")
    report = audit(tmp_path, expected_webhooks=3)
    assert report["exit_code"] == 1
    assert [n["workflow_index"] for n in report["webhooks"]] == [1, 1, 2]
    assert report["files"][0]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_cli_reports_only_ordinals_hashes_and_codes_and_never_modifies_input(tmp_path):
    canary = "synthetic-sensitive-canary-1027"
    node = webhook(name=canary, id=canary, parameters={"path": canary, "authentication": canary},
                   credentials={canary: {"id": canary, "name": canary, "value": canary}})
    source = tmp_path / (canary + ".json")
    source.write_text(json.dumps({"name": canary, "nodes": [node], "pinData": {canary: canary}}), encoding="utf-8")
    before = source.read_bytes()
    result = subprocess.run([sys.executable, str(ROOT / "tools/check_n8n_webhooks.py"), "--folder", str(tmp_path)],
                            capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 1 and canary not in result.stdout + result.stderr
    assert str(tmp_path) not in result.stdout + result.stderr
    assert json.loads(result.stdout)["runtime_verified"] is False
    assert source.read_bytes() == before
    source.write_bytes(b'{"sensitive-key": "' + canary.encode() + b'", invalid')
    result = subprocess.run([sys.executable, str(ROOT / "tools/check_n8n_webhooks.py"), "--folder", str(tmp_path)],
                            capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 2 and canary not in result.stdout + result.stderr


def test_audit_accepts_a_configured_copy_without_editing_the_repository_exports(tmp_path):
    exported = json.loads((ROOT / "infra/n8n/workflows/haedam-30-s1-main.json").read_text(encoding="utf-8"))
    source = deepcopy(exported)
    hooks = [n for w in source for n in w["nodes"] if n["type"] == "n8n-nodes-base.webhook"]
    assert hooks
    for node in hooks:
        node["parameters"]["authentication"] = "headerAuth"
        node["credentials"] = {"httpHeaderAuth": {"id": "synthetic-credential-ref"}}
    (tmp_path / "candidate.json").write_text(json.dumps(source), encoding="utf-8")
    report = audit(tmp_path, expected_webhooks=len(hooks))
    assert report["exit_code"] == 0 and report["runtime_verified"] is False
    assert exported != source  # Only the isolated copy acquired an auth declaration.
