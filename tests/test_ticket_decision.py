"""Execute the actual exported n8n Code node under Node, with synthetic API receipts."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from tools.build_ticket_guard import build, TARGET
from tools.check_ticket_guard import evaluate

NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parents[1]
R = {"asset_id": "haedam-portal", "via": "portal", "action": "block", "target": "203.0.113.11"}
T1, T2 = "T-20261024-0001", "T-20261024-0002"


def execute(inputs):
    if NODE is None:
        pytest.skip("Node.js required to execute the actual n8n JavaScript")
    results = evaluate(inputs)
    assert all(x["allow_target_call"] is False and x["automatic_retry"] is False for x in results)
    return results


def apply_input():
    return {"mode": "apply", "expected": {"resource": deepcopy(R), "seat": "D", "bot": "112", "group_key": R["target"]},
            "observation": {"status": 200, "query": {"seat": "D", "group_key": R["target"]},
                            "body": {"ok": True, "exists": False, "ticket_id": None, "status": None, "applied_actions": []}}}


def claim(ticket=T1, seat="D", status="responding", bot="112"):
    return {"seat": seat, "ticket_id": ticket, "status": status,
            "active_actions": [{k: R[k] for k in ("via", "action", "target")} | {"bot": bot}]}


def release_input(tickets=None):
    return {"mode": "release", "expected": {"resource": deepcopy(R), "seat": "D", "owner_ticket_id": T1},
            "observation": {"status": 200, "query": deepcopy(R),
                            "body": {"ok": True, "resource": deepcopy(R), "tickets": tickets if tickets is not None else [claim()]}}}


def record_input(status=201, body=None):
    return {"mode": "record_response", "expected": {"ticket_id": None}, "observation": {"status": status,
            "body": body if body is not None else {"ok": True, "ticket_id": T1, "created": True, "duplicate": False, "status": "responding"}}}


def test_workflow_matches_source_and_has_no_execution_or_credentials():
    workflows = json.loads(TARGET.read_text(encoding="utf-8"))
    assert workflows == build()
    wf = workflows[0]
    assert wf["active"] is False
    assert [n["type"] for n in wf["nodes"]] == ["n8n-nodes-base.executeWorkflowTrigger", "n8n-nodes-base.code"]
    assert not any("credentials" in n for n in wf["nodes"])


def test_apply_none_active_other_route_and_restored_are_distinct():
    none = apply_input()
    active = deepcopy(none)
    active["observation"]["body"].update(exists=True, ticket_id=T1, status="responding",
        applied_actions=[claim()["active_actions"][0] | {"result": "applied"}])
    other_route = deepcopy(active)
    other_route["observation"]["body"]["applied_actions"][0]["via"] = "pfsense"
    restored = deepcopy(active)
    restored["observation"]["body"].update(status="restored", applied_actions=[])
    answers = execute([none, active, other_route, restored])
    assert [a["decision"] for a in answers] == ["apply_candidate", "skip_active", "apply_candidate", "hold"]
    assert answers[-1]["reason"] == "close_restored_before_new_cycle"


@pytest.mark.parametrize("change", ["missing_via", "wrong_query", "false_exists_with_ticket", "non_boolean", "closed", "missing_body"])
def test_bad_open_receipts_never_become_candidates(change):
    data = apply_input()
    b = data["observation"]["body"]
    if change == "missing_via":
        b.update(exists=True, ticket_id=T1, status="responding", applied_actions=[{"bot": "112", "action": "block", "target": R["target"], "result": "applied"}])
    elif change == "wrong_query": data["observation"]["query"]["seat"] = "A"
    elif change == "false_exists_with_ticket": b["ticket_id"] = T1
    elif change == "non_boolean": b["exists"] = "false"
    elif change == "closed": b.update(exists=True, ticket_id=T1, status="closed")
    else: data["observation"].pop("body")
    assert execute([data])[0]["decision"] == "hold"


def test_release_keeps_same_seat_other_bot_and_closed_claims():
    inputs = [release_input(), release_input([]), release_input([claim(), claim(T2, "A", bot="manual")]),
              release_input([claim(), claim(T2, "D", "closed")]), release_input([claim(status="closed")])]
    answers = execute(inputs)
    assert [a["reason"] for a in answers] == ["owner_only_snapshot_requires_serialization", "no_recorded_claims",
        "other_active_claims", "other_active_claims", "closed_claim_needs_reconciliation"]
    assert answers[2]["blocking_ticket_ids"] == [T2]


@pytest.mark.parametrize("change", ["asset", "route", "action", "target", "missing_via", "duplicate", "empty_actions", "owner_seat", "legacy_open"])
def test_release_rejects_mixed_or_incomplete_receipts(change):
    data = release_input()
    b = data["observation"]["body"]
    if change in ("asset", "route", "action", "target"):
        field = {"asset": "asset_id", "route": "via"}.get(change, change)
        b["resource"][field] = "different"
    elif change == "missing_via": b["tickets"][0]["active_actions"][0].pop("via")
    elif change == "duplicate": b["tickets"].append(deepcopy(b["tickets"][0]))
    elif change == "empty_actions": b["tickets"][0]["active_actions"] = []
    elif change == "owner_seat": b["tickets"][0]["seat"] = "A"
    else: b.pop("resource")
    assert execute([data])[0]["decision"] == "hold"


@pytest.mark.parametrize("status", [None, 401, 404, 500, 503, "200"])
def test_query_failure_is_not_zero(status):
    data = release_input([])
    data["observation"]["status"] = status
    answer = execute([data])[0]
    assert answer["decision"] == "hold" and answer["reason"] != "no_recorded_claims"


def test_record_ack_conflict_transport_and_ticket_mismatch():
    key_conflict = record_input(409, {"ok": False, "error": {"code": "IDEMPOTENCY_CONFLICT"}})
    cycle = record_input(409, {"ok": False, "error": {"code": "INVALID_TRANSITION"}})
    mismatch = record_input()
    mismatch["expected"]["ticket_id"] = T2
    answers = execute([record_input(), key_conflict, cycle, record_input(None), record_input(503), mismatch])
    assert [a["reason"] for a in answers] == ["effect_not_inferred", "resolve_key_body_conflict",
        "resolve_cycle_or_asset_scope", "reconcile_record_same_request", "reconcile_record_same_request", "invalid_record_response"]


def test_invalid_inputs_do_not_throw_or_echo_secrets():
    answers = execute([None, [], {}, {"mode": "unknown", "secret": "do-not-echo"},
                       {"mode": "apply", "expected": None, "observation": {}},
                       {"mode": "release", "expected": {}, "observation": {}}])
    assert all(a["decision"] == "hold" for a in answers)
    assert "do-not-echo" not in json.dumps(answers)
