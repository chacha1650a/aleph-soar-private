"""Candidate logical withdrawal policy only; C/target integration is rehearsed separately."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3

import pytest

from tools.resource_gate import Conflict
from tools.shared_claims import ClaimBook, claim_id

R = {"asset_id": "synthetic-portal", "via": "portal", "action": "block", "target": "203.0.113.11"}


def entry(number, resource=None):
    r = resource or R
    ticket = f"T-20261024-{number:04d}"
    action = f"synthetic-apply-{number}"
    return {"claim_id": claim_id(ticket, action), "ticket_id": ticket, "action_id": action,
            "record": {"asset_id": r["asset_id"], "stage": "released", "action": {
                "via": r["via"], "target": r["target"], "action": "unblock"}}}


@pytest.fixture
def book(tmp_path):
    return ClaimBook(tmp_path / "claims.db", create=True)


def test_only_last_owner_prepares_one_frozen_plan(book):
    snapshot = [entry(1), entry(2)]
    assert book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot) == {"state": "withdrawn_waiting", "remaining_owners": 1}
    ready = book.withdraw(R, "withdraw-b", snapshot[1]["claim_id"], snapshot)
    assert ready["state"] == "plan_prepared"
    plan = book.plan(ready["plan_id"])
    assert len(plan["plan"]["claims"]) == 2 and plan["state"] == "prepared"
    snapshot[0]["record"]["asset_id"] = "changed"
    assert all(c["record"]["asset_id"] == R["asset_id"] for c in book.plan(ready["plan_id"])["plan"]["claims"])


def test_replayed_intent_does_not_reissue_old_plan(book):
    snapshot = [entry(1)]
    prepared = book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    assert book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot) == {"state": "replayed", "plan_id": None}
    assert book.plan_for_request("withdraw-a")["plan"]["plan_id"] == prepared["plan_id"]


def test_changed_owner_with_same_request_id_conflicts(book):
    snapshot = [entry(1), entry(2)]
    book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    with pytest.raises(Conflict):
        book.withdraw(R, "withdraw-a", snapshot[1]["claim_id"], snapshot)


def test_new_owner_arrival_keeps_resource_blocked_until_their_withdrawal(book):
    snapshot = [entry(1), entry(2)]
    book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    snapshot.append(entry(3))
    assert book.withdraw(R, "withdraw-b", snapshot[1]["claim_id"], snapshot)["remaining_owners"] == 1
    ready = book.withdraw(R, "withdraw-c", snapshot[2]["claim_id"], snapshot)
    assert len(book.plan(ready["plan_id"])["plan"]["claims"]) == 3


def test_missing_known_claim_is_not_silently_deleted(book):
    snapshot = [entry(1), entry(2)]
    book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    with pytest.raises(ValueError):
        book.withdraw(R, "withdraw-b", snapshot[1]["claim_id"], snapshot[1:])
    assert book.withdraw(R, "withdraw-b", snapshot[1]["claim_id"], snapshot)["state"] == "plan_prepared"


@pytest.mark.parametrize("problem", ["duplicate", "scope", "identity", "owner"])
def test_bad_claim_snapshot_rejected(book, problem):
    snapshot = [entry(1)]
    owner = snapshot[0]["claim_id"]
    if problem == "duplicate": snapshot.append(deepcopy(snapshot[0]))
    elif problem == "scope": snapshot[0]["record"]["action"]["via"] = "pfsense"
    elif problem == "identity": snapshot[0]["action_id"] = "other-action"
    else: owner = "unknown"
    with pytest.raises(ValueError):
        book.withdraw(R, "withdraw-a", owner, snapshot)


def test_prepared_plan_holds_new_mutation_and_completion_is_atomic(book):
    snapshot = [entry(1)]
    prepared = book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    with pytest.raises(ValueError):
        book.withdraw(R, "withdraw-new", entry(2)["claim_id"], snapshot + [entry(2)])
    with book.connect() as conn:
        conn.execute("CREATE TRIGGER fail_complete BEFORE UPDATE ON plans BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    with pytest.raises(sqlite3.IntegrityError):
        book.complete(prepared["plan_id"])
    assert book.plan(prepared["plan_id"])["state"] == "prepared"
    with book.connect() as conn:
        assert conn.execute("SELECT state FROM claims").fetchone()[0] == "withdrawn"


def test_completed_cycle_keeps_history_and_old_claim_cannot_reappear(book):
    snapshot = [entry(1)]
    plan = book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    book.complete(plan["plan_id"])
    book.complete(plan["plan_id"])
    with pytest.raises(ValueError):
        book.withdraw(R, "withdraw-old", snapshot[0]["claim_id"], snapshot)
    fresh = [entry(2)]
    new = book.withdraw(R, "withdraw-new", fresh[0]["claim_id"], fresh)
    assert new["plan_id"] != plan["plan_id"] and book.plan(plan["plan_id"])["state"] == "completed"


def test_concurrent_intents_prepare_one_plan(book):
    snapshot = [entry(1), entry(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(lambda n: ClaimBook(book.path).withdraw(R, f"withdraw-{n}", snapshot[n]["claim_id"], snapshot), range(2)))
    assert sorted(a["state"] for a in answers) == ["plan_prepared", "withdrawn_waiting"]
    with book.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 1


def test_resources_and_databases_are_not_implicitly_merged(book, tmp_path):
    first = [entry(1)]
    book.withdraw(R, "withdraw-a", first[0]["claim_id"], first)
    other = {**R, "via": "pfsense"}
    second = [entry(2, other)]
    assert book.withdraw(other, "withdraw-b", second[0]["claim_id"], second)["state"] == "plan_prepared"
    with pytest.raises(sqlite3.OperationalError):
        ClaimBook(tmp_path / "missing.db")


def test_explicit_retain_cancels_withdrawal_until_a_new_withdrawal(book):
    snapshot = [entry(1), entry(2)]
    book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    assert book.retain(R, "retain-a-1", snapshot[0]["claim_id"], snapshot)["state"] == "retained"
    assert book.withdraw(R, "withdraw-b", snapshot[1]["claim_id"], snapshot)["state"] == "withdrawn_waiting"
    ready = book.withdraw(R, "withdraw-a-new", snapshot[0]["claim_id"], snapshot)
    assert ready["state"] == "plan_prepared"
    assert book.retain(R, "retain-a-1", snapshot[0]["claim_id"], snapshot)["state"] == "replayed"


def test_retain_cannot_steal_prepared_release_or_reuse_withdrawal_id(book):
    snapshot = [entry(1), entry(2)]
    book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    with pytest.raises(Conflict):
        book.retain(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    book.withdraw(R, "withdraw-b", snapshot[1]["claim_id"], snapshot)
    with pytest.raises(ValueError):
        book.retain(R, "retain-after-plan", snapshot[0]["claim_id"], snapshot)


def test_retain_requires_the_same_complete_resource_snapshot(book):
    snapshot = [entry(1), entry(2)]
    book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    changed = deepcopy(snapshot)
    changed[0]["record"]["action"]["via"] = "pfsense"
    with pytest.raises(ValueError):
        book.retain(R, "retain-wrong", snapshot[0]["claim_id"], changed)
    with pytest.raises(ValueError):
        book.retain(R, "retain-incomplete", snapshot[0]["claim_id"], snapshot[:1])


def test_absent_physical_fake_block_holds_before_logical_withdrawal(book, tmp_path):
    from flask import Flask
    from tools.resource_gate import ResourceGate
    from tools.shared_release_simulation import SharedReleaseSimulation
    from tools.simulated_execution import CTestClient, SimulatedTarget
    app = Flask(__name__)
    calls = []
    app.before_request(lambda: calls.append(1))
    gate = ResourceGate(tmp_path / "gate.db", create=True)
    target = SimulatedTarget(tmp_path / "target.db", create=True)
    client = CTestClient(app.test_client(), app.test_client(), "synthetic-test-key-0001")
    simulation = SharedReleaseSimulation(gate, book, target, client)
    assert simulation.withdraw("withdraw-absent", R, "T-20261024-0001", "synthetic-apply-1")["state"] == "held"
    assert calls == [] and gate.inspect("withdraw-absent")["result"] == "not_called"
    with book.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0] == 0


def test_cancelled_plan_preserves_history_reactivates_claims_and_cannot_complete(book):
    snapshot = [entry(1), entry(2)]
    book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    ready = book.withdraw(R, "withdraw-b", snapshot[1]["claim_id"], snapshot)
    book.cancel(ready["plan_id"])
    book.cancel(ready["plan_id"])
    assert book.plan(ready["plan_id"])["state"] == "cancelled"
    with book.connect() as conn:
        assert {r[0] for r in conn.execute("SELECT state FROM claims")} == {"active"}
    with pytest.raises(ValueError):
        book.complete(ready["plan_id"])
    assert book.withdraw(R, "withdraw-a-new", snapshot[0]["claim_id"], snapshot)["state"] == "withdrawn_waiting"


def test_completed_plan_cannot_be_cancelled(book):
    snapshot = [entry(1)]
    ready = book.withdraw(R, "withdraw-a", snapshot[0]["claim_id"], snapshot)
    book.complete(ready["plan_id"])
    with pytest.raises(ValueError):
        book.cancel(ready["plan_id"])


def test_old_candidate_database_requires_explicit_migration(book):
    with book.connect() as conn:
        conn.execute("PRAGMA user_version=1")
    with pytest.raises(ValueError):
        ClaimBook(book.path)
