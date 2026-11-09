"""Synthetic reservation trials, including independent processes and crash recovery."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sqlite3
import sys

import pytest

from tools.resource_gate import Conflict, ResourceGate, StalePermit

ROOT = Path(__file__).resolve().parents[1]
R = {"asset_id": "haedam-portal", "via": "portal", "action": "block", "target": "203.0.113.11"}


def test_same_resource_apply_release_race_has_one_owner(tmp_path):
    path = tmp_path / "gate.db"
    gate = ResourceGate(path, create=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = list(pool.map(lambda n: ResourceGate(path).reserve(R, f"request-{n}",
            "apply" if n % 2 else "release", {"seat": "A" if n % 2 else "D"}), range(24)))
    assert sum(a["state"] == "reserved" for a in answers) == 1
    assert sum(a["state"] == "busy" for a in answers) == 23
    winner = next(a["permit"] for a in answers if a["state"] == "reserved")
    gate.finish(winner, "not_called", "synthetic/no-target-call")
    assert gate.reserve(R, "next", "release", {})["state"] == "reserved"


def test_replay_is_cached_and_changed_body_or_operation_conflicts(tmp_path):
    gate = ResourceGate(tmp_path / "gate.db", create=True)
    permit = gate.reserve(R, "stable", "apply", {"b": 2, "a": 1})["permit"]
    assert gate.reserve(R, "stable", "apply", {"a": 1, "b": 2}) == {"state": "busy", "reason": "same_request_pending"}
    for op, payload in [("release", {"a": 1, "b": 2}), ("apply", {"a": 2})]:
        with pytest.raises(Conflict):
            gate.reserve(R, "stable", op, payload)
    gate.finish(permit, "recorded", "synthetic/target-and-record-checked")
    assert ResourceGate(gate.path).reserve(R, "stable", "apply", {"a": 1, "b": 2}) == {
        "state": "replayed", "result": "recorded", "evidence_ref": "synthetic/target-and-record-checked"}
    assert gate.reserve(R, "fresh-cycle", "apply", {"a": 1, "b": 2})["state"] == "reserved"


@pytest.mark.parametrize("field,value", [("via", "pfsense"), ("asset_id", "other"), ("target", "203.0.113.12"), ("action", "lock")])
def test_other_resources_remain_independent(tmp_path, field, value):
    gate = ResourceGate(tmp_path / "gate.db", create=True)
    assert gate.reserve(R, "one", "apply", {})["state"] == "reserved"
    assert gate.reserve({**R, field: value}, "two", "release", {})["state"] == "reserved"


def test_forged_or_stale_permit_cannot_clear_a_current_owner(tmp_path):
    gate = ResourceGate(tmp_path / "gate.db", create=True)
    old = gate.reserve(R, "old", "apply", {})["permit"]
    with pytest.raises(StalePermit):
        gate.finish(replace(old, token="forged"), "not_called", "synthetic/ref")
    assert gate.reserve(R, "other", "release", {})["state"] == "busy"
    gate.finish(old, "not_called", "synthetic/ref")
    gate.reserve(R, "new", "apply", {})
    with pytest.raises(StalePermit):
        gate.finish(old, "recorded", "synthetic/stale")
    assert gate.inspect("new")["state"] == "pending"


def test_crash_after_reservation_survives_process_exit(tmp_path):
    path = tmp_path / "gate.db"
    ResourceGate(path, create=True)
    script = """
import json, os, sys
from tools.resource_gate import ResourceGate
p = json.loads(sys.stdin.read())
ResourceGate(p['path']).reserve(p['resource'], 'crashed', 'apply', {})
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", script], input=json.dumps({"path": str(path), "resource": R}),
                   text=True, capture_output=True, check=True, timeout=15, cwd=ROOT)
    gate = ResourceGate(path)
    assert gate.reserve(R, "next", "release", {})["state"] == "busy"
    assert gate.inspect("crashed")["state"] == "pending"
    for missing in ("executor_stopped", "target_checked", "record_checked"):
        confirmations = dict(executor_stopped=True, target_checked=True, record_checked=True)
        confirmations[missing] = False
        with pytest.raises(ValueError):
            gate.reconcile("crashed", **confirmations, evidence_ref="synthetic/ref")
    gate.reconcile("crashed", executor_stopped=True, target_checked=True, record_checked=True,
                   evidence_ref="synthetic/crash-reconciled")
    assert gate.inspect("crashed")["result"] == "reconciled"
    assert gate.reserve(R, "next", "release", {})["state"] == "reserved"


def test_independent_processes_share_one_reservation(tmp_path):
    path = tmp_path / "gate.db"
    ResourceGate(path, create=True)
    script = """
import json, sys
from tools.resource_gate import ResourceGate
p = json.loads(sys.stdin.read())
a = ResourceGate(p['path']).reserve(p['resource'], p['id'], p['operation'], {})
print(a['state'])
"""
    children = [subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT) for _ in range(4)]
    try:
        for n, child in enumerate(children):
            child.stdin.write(json.dumps({"path": str(path), "resource": R, "id": f"process-{n}",
                                         "operation": "apply" if n % 2 else "release"}))
            child.stdin.close()
            child.stdin = None
        answers = []
        for child in children:
            stdout, stderr = child.communicate(timeout=15)
            assert child.returncode == 0, stderr
            answers.append(stdout.strip())
        assert sorted(answers) == ["busy", "busy", "busy", "reserved"]
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def test_uncertain_call_is_not_completed_or_expired_automatically(tmp_path):
    gate = ResourceGate(tmp_path / "gate.db", create=True)
    permit = gate.reserve(R, "uncertain", "apply", {})["permit"]
    with pytest.raises(ValueError):
        gate.finish(permit, "unknown", "synthetic/timeout")
    with pytest.raises(ValueError):
        gate.finish(permit, "recorded", "")
    assert ResourceGate(gate.path).reserve(R, "unblock", "release", {})["state"] == "busy"


def test_payload_values_are_hashed_not_stored(tmp_path):
    path = tmp_path / "gate.db"
    gate = ResourceGate(path, create=True)
    gate.reserve(R, "private", "apply", {"do_not_persist": "synthetic-secret-abcdef"})
    for file in tmp_path.iterdir():
        assert b"synthetic-secret-abcdef" not in file.read_bytes()
    assert "token" not in gate.inspect("private")


def test_finish_failure_rolls_back_both_result_and_unlock(tmp_path):
    path = tmp_path / "gate.db"
    gate = ResourceGate(path, create=True)
    permit = gate.reserve(R, "one", "apply", {})["permit"]
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TRIGGER fail_unlock BEFORE DELETE ON reservations BEGIN SELECT RAISE(ABORT, 'synthetic'); END")
    with pytest.raises(sqlite3.IntegrityError):
        gate.finish(permit, "recorded", "synthetic/ref")
    assert gate.inspect("one")["state"] == "pending"
    assert gate.reserve(R, "two", "release", {})["state"] == "busy"


def test_missing_or_unavailable_database_is_not_permission(tmp_path):
    path = tmp_path / "gate.db"
    gate = ResourceGate(path, create=True)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE reservations")
    with pytest.raises(sqlite3.OperationalError):
        gate.reserve(R, "unknown", "apply", {})
    assert gate.inspect("unknown") is None


@pytest.mark.parametrize("bad", [{}, {**R, "seat": "A"}, {**R, "via": "unknown"}, {**R, "target": "x\ny"}])
def test_bad_resource_is_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        ResourceGate(tmp_path / "gate.db", create=True).reserve(bad, "bad", "apply", {})


def test_missing_empty_or_existing_database_is_not_silently_reinitialized(tmp_path):
    path = tmp_path / "gate.db"
    with pytest.raises(sqlite3.OperationalError):
        ResourceGate(path)
    assert not path.exists()
    path.touch()
    with pytest.raises(ValueError):
        ResourceGate(path)
    with pytest.raises(FileExistsError):
        ResourceGate(path, create=True)


def test_database_disappearing_after_open_does_not_create_a_new_store(tmp_path):
    path = tmp_path / "gate.db"
    gate = ResourceGate(path, create=True)
    gate.reserve(R, "pending", "apply", {})
    path.unlink()
    with pytest.raises(sqlite3.OperationalError):
        gate.reserve(R, "after-loss", "release", {})
    assert not path.exists()
