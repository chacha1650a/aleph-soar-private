"""Reservation + real loopback GET + exported JS; no target callbacks."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import shutil
import sqlite3
import threading

from flask import Flask, jsonify
import pytest

from tools.check_ticket_guard import local_server
from tools.resource_gate import ResourceGate
from tools.ticket_http import TicketHTTP
from tools.ticket_trial import TicketTrial

R = {"asset_id": "haedam-portal", "via": "portal", "action": "block", "target": "203.0.113.11"}
EXPECTED = {"resource": R, "seat": "D", "group_key": R["target"], "bot": "112", "owner_ticket_id": "T-20261024-0001"}


@pytest.fixture
def trial(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js required to execute the exported JS in the joined trial")
    app = Flask(__name__)
    state = {"calls": 0, "status": 200, "body": {"ok": True, "exists": False,
             "ticket_id": None, "status": None, "applied_actions": []}}
    gate = ResourceGate(tmp_path / "gate.db", create=True)

    @app.get("/api/v1/tickets/<route>")
    def get(route):
        state["calls"] += 1
        if "started" in state:
            state["started"].set()
            assert state["continue"].wait(5)
        return jsonify(state["body"]), state["status"]

    with local_server(app) as url:
        yield TicketTrial(gate, TicketHTTP(url, "synthetic-trial-key-0001")), gate, state


def test_reserve_precedes_query_and_known_no_call_is_finished(trial):
    runner, gate, state = trial
    original = runner.transport.apply

    def assert_reserved(expected):
        assert gate.inspect("one")["state"] == "pending"
        return original(expected)

    runner.transport.apply = assert_reserved
    outcome = runner.run("one", "apply", EXPECTED, "synthetic/one")
    assert outcome["state"] == "completed" and outcome["reservation_state"] == "released"
    assert outcome["decision"]["decision"] == "apply_candidate"
    assert outcome["allow_target_call"] is False
    assert gate.inspect("one")["result"] == "not_called" and state["calls"] == 1


def test_replay_has_no_stale_candidate_and_new_attempt_gets_fresh_state(trial):
    runner, gate, state = trial
    runner.run("one", "apply", EXPECTED, "synthetic/one")
    state["body"].update(exists=True, ticket_id=EXPECTED["owner_ticket_id"], status="restored")
    replay = runner.run("one", "apply", EXPECTED, "synthetic/one")
    assert replay["state"] == "replayed" and replay["decision"] is None and state["calls"] == 1
    fresh = runner.run("two", "apply", EXPECTED, "synthetic/two")
    assert fresh["decision"]["reason"] == "close_restored_before_new_cycle" and state["calls"] == 2


def test_same_resource_busy_does_not_get_or_evaluate(trial):
    runner, gate, state = trial
    held = gate.reserve(R, "held", "release", {})["permit"]
    assert runner.run("other", "apply", EXPECTED, "synthetic/other")["state"] == "busy"
    assert state["calls"] == 0
    gate.finish(held, "not_called", "synthetic/held")


def test_simultaneous_apply_release_contender_has_no_query(trial):
    runner, gate, state = trial
    state.update(started=threading.Event(), **{"continue": threading.Event()})
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(runner.run, "applying", "apply", EXPECTED, "synthetic/a")
        try:
            assert state["started"].wait(5)
            other = TicketTrial(ResourceGate(gate.path), runner.transport)
            assert other.run("releasing", "release", EXPECTED, "synthetic/b")["state"] == "busy"
            assert state["calls"] == 1
        finally:
            state["continue"].set()
        assert future.result(timeout=10)["state"] == "completed"


def test_same_attempt_changed_input_is_conflict_without_query(trial):
    runner, gate, state = trial
    runner.run("one", "apply", EXPECTED, "synthetic/one")
    changed = {**EXPECTED, "bot": "manual"}
    outcome = runner.run("one", "apply", changed, "synthetic/one")
    assert outcome["state"] == "conflict" and state["calls"] == 1


def test_http_error_is_a_hold_but_known_no_target_call_can_release(trial):
    runner, gate, state = trial
    state.update(status=503, body={"ok": False})
    outcome = runner.run("unavailable", "release", EXPECTED, "synthetic/503")
    assert outcome["decision"]["reason"] == "store_query_failed"
    assert outcome["reservation_state"] == "released" and gate.inspect("unavailable")["result"] == "not_called"


@pytest.mark.parametrize("failure", ["query", "js", "unsafe_verdict", "workflow_drift"])
def test_ordinary_failures_are_cleaned_without_target_call(trial, monkeypatch, failure):
    runner, gate, state = trial

    def fail(*args):
        raise RuntimeError("synthetic-sensitive-detail")

    if failure == "query": monkeypatch.setattr(runner.transport, "apply", fail)
    elif failure == "js": monkeypatch.setattr("tools.ticket_trial.evaluate", fail)
    elif failure == "unsafe_verdict":
        monkeypatch.setattr("tools.ticket_trial.evaluate", lambda inputs: [{"allow_target_call": True}])
    else:
        hashes = iter(["before", "after"])
        monkeypatch.setattr("tools.ticket_trial._digest", lambda: next(hashes))
    outcome = runner.run("failing", "apply", EXPECTED, "synthetic/failure")
    assert outcome["state"] == "failed" and outcome["reservation_state"] == "released"
    assert outcome["decision"] is None and "sensitive" not in str(outcome)
    assert gate.inspect("failing")["result"] == "not_called"


def test_uncaught_interrupt_leaves_pending_for_reconciliation(trial, monkeypatch):
    runner, gate, state = trial

    def stop(expected):
        raise KeyboardInterrupt()

    monkeypatch.setattr(runner.transport, "apply", stop)
    with pytest.raises(KeyboardInterrupt):
        runner.run("interrupted", "apply", EXPECTED, "synthetic/interrupted")
    assert ResourceGate(gate.path).inspect("interrupted")["state"] == "pending"
    assert runner.run("next", "release", EXPECTED, "synthetic/next")["state"] == "busy"


def test_cleanup_failure_does_not_claim_released_or_retry(trial, monkeypatch):
    runner, gate, state = trial
    calls = []

    def fail(*args):
        calls.append(1)
        raise sqlite3.OperationalError("synthetic failure")

    monkeypatch.setattr(gate, "finish", fail)
    outcome = runner.run("one", "apply", EXPECTED, "synthetic/one")
    assert outcome["reason"] == "reservation_cleanup_unconfirmed" and outcome["decision"] is None
    assert outcome["reservation_state"] == "unknown" and len(calls) == 1
    assert gate.inspect("one")["state"] == "pending"


def test_gate_failure_has_no_http_request(trial, monkeypatch):
    runner, gate, state = trial

    def fail(*args):
        raise sqlite3.OperationalError("synthetic")

    monkeypatch.setattr(gate, "reserve", fail)
    assert runner.run("one", "apply", EXPECTED, "synthetic/one")["reason"] == "reservation_failed"
    assert state["calls"] == 0


def test_release_uses_applied_resource_and_remains_a_candidate(trial):
    runner, gate, state = trial
    state["body"] = {"ok": True, "resource": deepcopy(R), "tickets": [{"seat": "D",
        "ticket_id": EXPECTED["owner_ticket_id"], "status": "responding", "active_actions": [
            {"bot": "112", **{k: R[k] for k in ("via", "action", "target")}}]}]}
    outcome = runner.run("release", "release", EXPECTED, "synthetic/release")
    assert outcome["decision"]["decision"] == "release_candidate"
    assert outcome["allow_target_call"] is False and gate.inspect("release")["result"] == "not_called"
