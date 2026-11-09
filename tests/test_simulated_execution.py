"""Synthetic effects/record failures. MemoryTickets is a test double, not C storage."""
from copy import deepcopy
import json
import shutil
import sqlite3
from pathlib import Path
import subprocess
import sys

import pytest

from tools.resource_gate import ResourceGate, Conflict
from tools.simulated_execution import SimulatedExecution, SimulatedTarget

R = {"asset_id": "haedam-portal", "via": "portal", "action": "block", "target": "203.0.113.11"}


def body(mode="apply"):
    return {"seat": "D", "case_id": "S12", "group_key": R["target"], "asset_id": R["asset_id"],
            "title": "synthetic-only", "event_ids": ["synthetic-event-01"],
            "stage": "applied" if mode == "apply" else "released", "action": {
                "bot": "112", "via": R["via"], "target": R["target"], "action": "block" if mode == "apply" else "unblock"}}


class MemoryTickets:
    def __init__(self):
        self.item, self.cache, self.active = None, {}, []
        self.fail_record = False
        self.lose_ack = False
        self.other_claim = False

    def observe(self, mode, expected):
        query = {"seat": expected["seat"], "group_key": expected["group_key"]} if mode == "apply" else expected["resource"]
        if mode == "apply":
            data = {"ok": True, "exists": self.item is not None, "ticket_id": self.item["ticket_id"] if self.item else None,
                    "status": self.item["status"] if self.item else None, "applied_actions": deepcopy(self.active)}
        else:
            items = ([{"seat": "D", "ticket_id": self.item["ticket_id"], "status": self.item["status"],
                       "active_actions": deepcopy(self.active)}] if self.active else [])
            if self.other_claim:
                items.append({"seat": "A", "ticket_id": "T-20261024-0002", "status": "responding", "active_actions": deepcopy(self.active)})
            data = {"ok": True, "resource": expected["resource"], "tickets": items}
        return {"mode": mode, "expected": expected, "observation": {"status": 200, "query": query, "body": data}}

    def record(self, payload, key):
        if self.fail_record:
            raise RuntimeError("synthetic record unavailable")
        wire = json.dumps(payload, sort_keys=True)
        if key in self.cache:
            old, ack = self.cache[key]
            assert old == wire, "record replay body changed"
            return deepcopy(ack)
        if self.item is None:
            self.item = {k: payload[k] for k in ("seat", "group_key", "asset_id", "event_ids")}
            self.item.update(ticket_id="T-20261024-0001", status="open", actions=[])
        action = deepcopy(payload["action"])
        if payload["stage"] == "effect":
            self.item["actions"][-1].update(effect_verified=True, effect_verified_at=action["effect_verified_at"])
            self.item["status"] = "verified"
        else:
            self.item["actions"].append({**action, "action_id": key, "duplicate": False})
            if payload["stage"] == "released":
                self.active, self.item["status"] = [], "restored"
            else:
                self.active = [{k: action[k] for k in ("bot", "via", "target", "action", "result")}]
                self.item["status"] = "responding"
        ack = {"ok": True, "ticket_id": self.item["ticket_id"], "status": self.item["status"]}
        self.cache[key] = wire, deepcopy(ack)
        if self.lose_ack:
            self.lose_ack = False
            raise RuntimeError("synthetic ACK loss after commit")
        return ack

    def ticket(self, ticket_id):
        return deepcopy(self.item)


@pytest.fixture
def simulation(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js required for actual exported guard JS")
    return SimulatedExecution(ResourceGate(tmp_path / "gate.db", create=True),
                              SimulatedTarget(tmp_path / "target.db", create=True), MemoryTickets())


def count(target):
    with target.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]


def test_fake_apply_effect_release_and_replay(simulation):
    sim = simulation
    assert sim.run("apply-0001", "apply", body(), R)["state"] == "recorded"
    assert sim.target.active(R) and sim.tickets.item["status"] == "verified"
    assert sim.run("apply-0001", "apply", body(), R)["state"] == "replayed"
    assert count(sim.target) == 1
    answer = sim.run("release-0001", "release", body("release"), R)
    assert answer["state"] == "recorded" and answer["allow_target_call"] is False
    assert not sim.target.active(R) and sim.tickets.item["status"] == "restored"
    assert count(sim.target) == 2


@pytest.mark.parametrize("fault", ["after_target", "after_record", "record_unavailable", "ack_loss"])
def test_after_possible_effect_keeps_pending_and_record_only_repair_survives_restart(simulation, fault):
    sim = simulation
    sim.tickets.fail_record = fault == "record_unavailable"
    sim.tickets.lose_ack = fault == "ack_loss"
    answer = sim.run("unknown-0001", "apply", body(), R, fault=fault if fault.startswith("after_") else None)
    assert answer["state"] == "pending" and sim.target.active(R)
    assert sim.run("release-0001", "release", body("release"), R)["state"] == "busy"
    assert count(sim.target) == 1
    sim.tickets.fail_record = False
    reopened = SimulatedExecution(ResourceGate(sim.gate.path), SimulatedTarget(sim.target.path), sim.tickets)
    with pytest.raises(ValueError):
        reopened.repair_records("unknown-0001", "apply", body(), R)
    assert reopened.repair_records("unknown-0001", "apply", body(), R, executor_stopped=True)["state"] == "reconciled"
    assert count(sim.target) == 1 and sim.tickets.item["status"] == "verified"
    assert reopened.run("unknown-0001", "apply", body(), R)["state"] == "replayed"


def test_other_claim_blocks_release_and_restored_blocks_new_cycle(simulation):
    sim = simulation
    sim.run("apply-0001", "apply", body(), R)
    sim.tickets.other_claim = True
    assert sim.run("release-0001", "release", body("release"), R)["state"] == "not_called"
    assert count(sim.target) == 1 and sim.target.active(R)
    sim.tickets.other_claim = False
    assert sim.run("release-0002", "release", body("release"), R)["state"] == "recorded"
    fresh = body()
    fresh["event_ids"] = ["synthetic-new-cycle"]
    assert sim.run("apply-0002", "apply", fresh, R)["state"] == "not_called"
    assert count(sim.target) == 2


def test_target_ledger_is_atomic_idempotent_and_conflicts(simulation):
    target = simulation.target
    first = target.perform("target-0001", R, "apply")
    assert target.perform("target-0001", R, "apply") == first
    assert count(target) == 1
    with pytest.raises(Conflict):
        target.perform("target-0001", R, "release")


def test_repair_missing_request_or_receipt_does_not_call_target(simulation):
    sim = simulation
    assert sim.repair_records("missing-0001", "apply", body(), R, executor_stopped=True)["state"] == "held"
    assert sim.gate.inspect("missing-0001") is None
    payload = sim._input("pending-0001", "apply", body(), R)
    sim.gate.reserve(R, "pending-0001", "apply", payload)
    assert sim.repair_records("pending-0001", "apply", body(), R, executor_stopped=True)["state"] == "held"
    assert count(sim.target) == 0


def test_repair_with_different_body_cannot_release_reservation(simulation):
    sim = simulation
    sim.run("unknown-0001", "apply", body(), R, fault="after_target")
    changed = body()
    changed["event_ids"] = ["other-event"]
    with pytest.raises(Conflict):
        sim.repair_records("unknown-0001", "apply", changed, R, executor_stopped=True)
    assert sim.gate.inspect("unknown-0001")["state"] == "pending"


def test_missing_target_database_is_not_a_fresh_empty_target(simulation):
    sim = simulation
    sim.target.path.unlink()
    with pytest.raises(sqlite3.OperationalError):
        SimulatedTarget(sim.target.path)


def test_record_readback_failure_retains_reservation(simulation, monkeypatch):
    sim = simulation
    monkeypatch.setattr(sim.tickets, "ticket", lambda ticket_id: {"seat": "A", "group_key": "wrong", "asset_id": "wrong"})
    assert sim.run("readback-0001", "apply", body(), R)["state"] == "pending"
    assert sim.gate.inspect("readback-0001")["state"] == "pending"


def test_invalid_scope_stops_before_reservation(simulation):
    with pytest.raises(ValueError):
        simulation.run("invalid-0001", "release", body(), R)
    assert simulation.gate.inspect("invalid-0001") is None


def test_abrupt_process_exit_preserves_target_receipt_and_pending_gate(simulation):
    sim = simulation
    program = """
import json, os, sys
from tools.resource_gate import ResourceGate
from tools.simulated_execution import SimulatedTarget, SimulatedExecution
p = json.loads(sys.stdin.read())
ResourceGate(p['gate']).reserve(p['resource'], 'crashed-0001', 'apply',
    SimulatedExecution._input('crashed-0001', 'apply', p['body'], p['resource']))
SimulatedTarget(p['target']).perform('crashed-0001', p['resource'], 'apply')
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", program], input=json.dumps({"gate": str(sim.gate.path),
        "target": str(sim.target.path), "resource": R, "body": body()}), text=True, capture_output=True,
        check=True, timeout=15, cwd=Path(__file__).resolve().parents[1])
    assert sim.gate.inspect("crashed-0001")["state"] == "pending" and count(sim.target) == 1
    assert sim.repair_records("crashed-0001", "apply", body(), R, executor_stopped=True)["state"] == "reconciled"
    assert count(sim.target) == 1


def test_changed_current_target_state_blocks_record_only_repair(simulation):
    sim = simulation
    sim.run("unknown-0001", "apply", body(), R, fault="after_target")
    sim.target.perform("manual-bypass", R, "release")
    assert sim.repair_records("unknown-0001", "apply", body(), R, executor_stopped=True)["state"] == "pending"
    assert count(sim.target) == 2 and not sim.target.active(R)


def test_pre_target_cleanup_failure_is_not_retried(simulation, monkeypatch):
    calls = []

    def fail(*args):
        calls.append(1)
        raise sqlite3.OperationalError("synthetic")

    monkeypatch.setattr(simulation.gate, "finish", fail)
    assert simulation.run("release-0001", "release", body("release"), R)["state"] == "held"
    assert len(calls) == 1 and count(simulation.target) == 0
