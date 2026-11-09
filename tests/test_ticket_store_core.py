"""Ticket store check/record through the n8n app, checked against the contracts."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest
from referencing import Registry, Resource

from ticket_store import db, samples, validate
from ticket_store.app import create_dashboard_app, create_n8n_app

ROOT = Path(__file__).resolve().parents[1]
KEY = "test-key-not-a-secret-0001"
SCHEMAS = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "contracts").glob("*.schema.json")]
REGISTRY = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in SCHEMAS)


def contract(name):
    schema = json.loads((ROOT / f"contracts/{name}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=REGISTRY, format_checker=FormatChecker(formats=["date-time", "ipv4", "ipv6"]))


def example(name):
    return json.loads((ROOT / f"contracts/ticket-examples/{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def apps(tmp_path):
    path = str(tmp_path / "tickets.db")
    return create_n8n_app(path, KEY).test_client(), create_dashboard_app(path).test_client(), path


def record(client, body, key, api_key=KEY):
    response = client.post("/api/v1/tickets/record", json=body,
                           headers={"X-Response-Key": api_key, "Idempotency-Key": key})
    contract("ticket-response").validate(response.get_json())
    return response


def check(client, group_key, seat=None):
    query = {"group_key": group_key, **({"seat": seat} if seat else {})}
    response = client.get("/api/v1/tickets/open", query_string=query, headers={"X-Response-Key": KEY})
    contract("ticket-response").validate(response.get_json())
    return response.get_json()


def s12(stage="applied", **action):
    body = example("record-s12-applied")
    body["stage"] = stage
    body["action"].update(action)
    return body


def stored(path, ticket_id):
    ticket = db.get_ticket(db.connect(path), ticket_id)
    contract("ticket").validate(ticket)
    return ticket


def reblock(**action):
    """The same IP blocked again after a release: a new Graylog event, so a new decision (not a replay)."""
    body = s12(**action)
    body["event_ids"] = ["sample-graylog-s12-event-02"]
    return body


def ticket_count(path):
    return len(db.list_tickets(db.connect(path), include_sample=True, limit=200))


@pytest.mark.parametrize("body", [example("record-s12-applied"), example("record-s7-effect"),
                                  {**example("record-s12-applied"), "stage": "detected", "action": None}])
def test_validator_accepts_what_the_contract_accepts(body):
    contract("ticket-record").validate(body)
    validate.record_body(body)


@pytest.mark.parametrize("change", [
    {"status": "open"}, {"dedup_key": "x"}, {"seat": "E"}, {"stage": "record"}, {"src_ip": "not-an-ip"},
    {"group_key": "a\nb"}, {"event_ids": []}, {"event_ids": ["x", "x"]}, {"password": "x"},
    {"condition_met_at": "2026-10-24T15:00:00"}, {"action": None}, {"stage": "released"},
    {"action": {**example("record-s12-applied")["action"], "bot": 112}},
    {"action": {**example("record-s12-applied")["action"], "via": "app"}},
    {"action": {**example("record-s12-applied")["action"], "api_key": "x"}},
])
def test_validator_rejects_what_the_contract_rejects(change):
    body = {**example("record-s12-applied"), **change}
    with pytest.raises(Exception):
        contract("ticket-record").validate(body)
    with pytest.raises(validate.Invalid):
        validate.record_body(body)


def test_key_is_required_and_bad_bodies_are_not_stored(apps):
    n8n, dashboard, path = apps
    assert record(n8n, s12(), "exec-1-applied", api_key="").status_code == 401
    assert record(n8n, s12(), "exec-1-applied", api_key="wrong-key-0000000000").status_code == 401
    assert n8n.get("/api/v1/tickets/open?group_key=x").status_code == 401
    bad = record(n8n, {**s12(), "seat": "E"}, "exec-1-applied")
    assert bad.status_code == 400 and bad.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert "E" not in bad.get_json()["error"]["message"].split()
    assert record(n8n, s12(), "short").status_code == 400
    assert db.list_tickets(db.connect(path), include_sample=True) == []


def test_s12_flow_applied_effect_released(apps):
    n8n, dashboard, path = apps
    assert check(n8n, "203.0.113.11", "D") == {"ok": True, "exists": False, "ticket_id": None, "status": None,
                                               "applied_actions": []}
    first = record(n8n, s12(), "exec-1-applied")
    assert first.status_code == 201
    ticket_id = first.get_json()["ticket_id"]
    assert first.get_json() == {"ok": True, "ticket_id": ticket_id, "created": True, "duplicate": False,
                                "status": "responding"}
    assert check(n8n, "203.0.113.11", "D")["applied_actions"] == [
        {"bot": "112", "via": "portal", "action": "block", "target": "203.0.113.11", "result": "applied"}]

    effect = record(n8n, s12("effect", effect_verified=True, effect_verified_at="2026-10-24T15:00:40+09:00"),
                    "exec-1-effect")
    assert effect.status_code == 200 and effect.get_json()["status"] == "verified"
    ticket = stored(path, ticket_id)
    assert len(ticket["actions"]) == 1
    assert ticket["actions"][0]["effect_verified_at"] == "2026-10-24T15:00:40+09:00"
    assert ticket["verified_at"] == "2026-10-24T15:00:40+09:00"
    assert ticket["responded_at"] == "2026-10-24T15:00:02+09:00"

    released = record(n8n, s12("released", action="unblock", result="released", finished_at="2026-10-24T15:20:00+09:00"),
                      "exec-2-released")
    assert released.get_json()["status"] == "restored"
    assert stored(path, ticket_id)["restored_at"] == "2026-10-24T15:20:00+09:00"
    assert check(n8n, "203.0.113.11")["tickets"] == [
        {"seat": "D", "ticket_id": ticket_id, "status": "restored", "active_actions": []}]

    listing = dashboard.get("/api/v1/tickets").get_json()
    assert listing["count"] == 1 and listing["items"][0]["mttr_seconds"] == 43
    assert listing["last_record_at"] is not None


def test_replay_returns_first_response_and_reused_key_conflicts(apps):
    n8n, _, path = apps
    first = record(n8n, s12(), "exec-1-applied").get_json()
    again = record(n8n, s12(), "exec-1-applied")
    assert again.status_code == 201 and again.get_json() == first
    assert len(stored(path, first["ticket_id"])["actions"]) == 1
    conflict = record(n8n, s12(detail="other"), "exec-1-applied")
    assert conflict.status_code == 409 and conflict.get_json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_human_retry_with_new_key_is_kept_as_duplicate_line(apps):
    n8n, _, path = apps
    first = record(n8n, s12(), "exec-1-applied").get_json()
    retry = record(n8n, s12(n8n_execution_id="sample-9999"), "exec-9-applied").get_json()
    assert retry == {**first, "created": False, "duplicate": True}
    assert [a["duplicate"] for a in stored(path, first["ticket_id"])["actions"]] == [False, True]


def test_failed_action_keeps_status_and_effect_needs_an_applied_line(apps):
    n8n, _, path = apps
    failed = record(n8n, s12(result="failed", applied_verified=False), "exec-1-applied").get_json()
    assert failed["status"] == "open"
    bad = record(n8n, s12("effect", effect_verified=True, effect_verified_at="2026-10-24T15:00:40+09:00"),
                 "exec-1-effect")
    assert bad.status_code == 400
    not_ok = record(n8n, s12(), "exec-2-applied").get_json()
    record(n8n, s12("effect", effect_verified=False, effect_verified_at="2026-10-24T15:00:40+09:00"), "exec-2-effect")
    assert stored(path, not_ok["ticket_id"])["status"] == "responding"


def test_detected_then_applied_uses_one_ticket_and_merges_events(apps):
    n8n, _, path = apps
    detected = record(n8n, {**s12(), "stage": "detected", "action": None}, "exec-1-detected").get_json()
    assert detected["created"] and detected["status"] == "open"
    applied = record(n8n, {**s12(), "event_ids": ["sample-graylog-s12-event-02"]}, "exec-1-applied").get_json()
    assert applied["ticket_id"] == detected["ticket_id"] and not applied["created"]
    assert stored(path, detected["ticket_id"])["event_ids"] == ["sample-graylog-s12-event-01", "sample-graylog-s12-event-02"]


def test_closed_ticket_event_resent_does_not_open_a_new_ticket(apps):
    n8n, _, path = apps
    first = record(n8n, s12(), "exec-1-applied").get_json()
    record(n8n, s12("effect", effect_verified=True, effect_verified_at="2026-10-24T15:00:40+09:00"), "exec-1-effect")
    record(n8n, s12("released", action="unblock", result="released"), "exec-2-released")
    db.close_ticket(db.connect(path), first["ticket_id"], "done")
    resent = record(n8n, s12(), "exec-5-applied").get_json()
    assert resent == {"ok": True, "ticket_id": first["ticket_id"], "created": False, "duplicate": True, "status": "closed"}
    fresh = record(n8n, {**s12(), "event_ids": ["sample-graylog-s12-event-03"]}, "exec-6-applied").get_json()
    assert fresh["created"] and fresh["ticket_id"] != first["ticket_id"]


def test_cross_seat_check_holds_release_while_another_seat_blocks(apps):
    n8n, _, _ = apps
    b_block = deepcopy(s12(via="pfsense"))
    b_block.update(seat="B", case_id="S4", title="S4 차단")
    record(n8n, b_block, "exec-b-applied")
    record(n8n, s12(), "exec-d-applied")
    record(n8n, s12("released", action="unblock", result="released"), "exec-d-released")
    tickets = check(n8n, "203.0.113.11")["tickets"]
    assert [(t["seat"], t["status"], len(t["active_actions"])) for t in tickets] == [("B", "responding", 1),
                                                                                      ("D", "restored", 0)]


def test_s7_group_key_with_colon_and_slash_round_trips(apps):
    n8n, _, _ = apps
    body = example("record-s7-effect")
    body.update(stage="applied")
    body["action"].update(effect_verified=None, effect_verified_at=None)
    record(n8n, body, "exec-7-applied")
    found = check(n8n, "haedam-portal:assets/zz_s7_sample.txt", "C")
    assert found["exists"] and found["applied_actions"][0]["action"] == "quarantine"


def test_s10_same_bot_through_portal_and_pfsense_keeps_two_lines(apps):
    """S10 blocks one IP with bot 112 twice: portal (app) and pfSense (boundary)."""
    n8n, _, path = apps
    s10 = {**s12(), "seat": "B", "case_id": "S10", "title": "S10 웹 스캔"}
    portal = record(n8n, s10, "exec-1-portal-applied").get_json()
    boundary = record(n8n, {**s10, "action": {**s10["action"], "via": "pfsense"}}, "exec-1-pfsense-applied").get_json()
    assert boundary == {**portal, "created": False, "duplicate": False}
    assert [(a["via"], a["duplicate"]) for a in stored(path, portal["ticket_id"])["actions"]] == [
        ("portal", False), ("pfsense", False)]
    assert [a["via"] for a in check(n8n, "203.0.113.11", "B")["applied_actions"]] == ["portal", "pfsense"]

    # effect updates only the line with the same via
    effect = {**s10, "stage": "effect", "action": {**s10["action"], "via": "pfsense", "effect_verified": True,
                                                   "effect_verified_at": "2026-10-24T15:00:40+09:00"}}
    record(n8n, effect, "exec-1-pfsense-effect")
    assert [a["effect_verified"] for a in stored(path, portal["ticket_id"])["actions"]] == [None, True]

    # releasing the pfSense block leaves the portal block active (and vice versa)
    release = {**s10, "stage": "released", "action": {**s10["action"], "via": "pfsense", "action": "unblock",
                                                      "result": "released"}}
    record(n8n, release, "exec-2-pfsense-released")
    tickets = check(n8n, "203.0.113.11")["tickets"]
    assert [a["via"] for a in tickets[0]["active_actions"]] == ["portal"]

    # a human retry of the same via is still a duplicate
    again = record(n8n, s10, "exec-9-portal-applied").get_json()
    assert again["duplicate"] is True


def resource_check(client, **changes):
    query = {"asset_id": "haedam-portal", "via": "portal",
             "action": "block", "target": "203.0.113.11", **changes}
    response = client.get("/api/v1/tickets/active", query_string=query, headers={"X-Response-Key": KEY})
    if response.status_code == 200:
        contract("ticket-response").validate(response.get_json())
    return response


def test_legacy_fw_block_is_the_same_pfsense_resource_without_rewriting_history(apps):
    n8n, _, path = apps
    legacy = s12(via="pfsense", action="fw_block")
    first = record(n8n, legacy, "legacy-pf-applied").get_json()
    active = resource_check(n8n, via="pfsense").get_json()
    assert active["tickets"][0]["active_actions"][0]["action"] == "block"
    assert stored(path, first["ticket_id"])["actions"][0]["action"] == "fw_block"
    duplicate = record(n8n, s12(via="pfsense"), "canonical-pf-applied").get_json()
    assert duplicate["duplicate"] is True
    release = s12("released", via="pfsense", action="unblock", result="released")
    assert record(n8n, release, "canonical-pf-release").get_json()["status"] == "restored"
    assert resource_check(n8n, via="pfsense").get_json()["tickets"] == []


def test_resource_check_finds_same_action_across_different_group_keys(apps):
    n8n, _, path = apps
    a_body = {**s12(), "seat": "A", "case_id": "S1", "group_key": "zz_review_user"}
    a = record(n8n, a_body, "resource-a-applied").get_json()
    # A resource release also needs claims recorded by a different bot/operator.
    d = record(n8n, s12(bot="manual"), "resource-d-applied").get_json()
    # Same IP on another execution route/asset must not be mistaken for this resource.
    record(n8n, {**s12(via="pfsense"), "seat": "B"}, "resource-b-applied")
    record(n8n, {**s12(), "seat": "C", "asset_id": "another-portal"}, "resource-c-applied")
    assert [t["seat"] for t in check(n8n, "203.0.113.11")["tickets"]] == ["B", "C", "D"]
    response = resource_check(n8n)
    assert response.status_code == 200
    assert [(t["seat"], t["ticket_id"]) for t in response.get_json()["tickets"]] == [
        ("A", a["ticket_id"]), ("D", d["ticket_id"])]
    # A human close is not evidence that the target was unblocked.
    record(n8n, {**a_body, "stage": "effect", "action": s12(
        effect_verified=True, effect_verified_at="2026-10-24T15:00:40+09:00")["action"]}, "resource-a-effect")
    with db.connect(path) as conn:
        # Simulate historical data created before the close guard existed.
        conn.execute("UPDATE tickets SET status = 'closed' WHERE ticket_id = ?", (a["ticket_id"],))
    assert resource_check(n8n).get_json()["tickets"][0]["status"] == "closed"


def test_via_separates_duplicate_effect_and_release_and_remaining_actions(apps):
    n8n, _, path = apps
    first = record(n8n, s12(), "via-portal-applied").get_json()
    second = record(n8n, s12(via="pfsense"), "via-pf-applied").get_json()
    assert second["duplicate"] is False
    assert {a["via"] for a in check(n8n, "203.0.113.11", "D")["applied_actions"]} == {"portal", "pfsense"}
    record(n8n, s12("effect", effect_verified=True, effect_verified_at="2026-10-24T15:00:40+09:00"),
           "via-portal-effect")
    assert [a["effect_verified"] for a in stored(path, first["ticket_id"])["actions"]] == [True, None]
    released = record(n8n, s12("released", action="unblock", result="released"), "via-portal-release")
    assert released.get_json()["status"] == "verified"
    assert resource_check(n8n).get_json()["tickets"] == []
    assert len(resource_check(n8n, via="pfsense").get_json()["tickets"]) == 1
    # An effect arriving after release must not verify the old applied line.
    late = record(n8n, s12("effect", effect_verified=True, effect_verified_at="2026-10-24T15:00:40+09:00"),
                  "via-portal-late-effect")
    assert late.status_code == 400
    # A new application on the released route is active, not a historical duplicate.
    fresh = record(n8n, {**s12(), "event_ids": ["new-portal-event"]}, "via-portal-new-apply")
    assert fresh.get_json()["duplicate"] is False
    assert len(check(n8n, "203.0.113.11", "D")["applied_actions"]) == 2


def test_detected_reserves_new_round_before_action_and_old_replay_cannot_enter_it(apps):
    n8n, _, path = apps
    first = record(n8n, s12(), "cycle-1-applied").get_json()
    record(n8n, s12("released", action="unblock", result="released"), "cycle-1-released")
    new = {**s12(), "event_ids": ["cycle-2-event"]}
    detected_body = {**new, "stage": "detected", "action": None}
    detected = record(n8n, detected_body, "cycle-2-detected")
    assert detected.status_code == 201
    fresh = detected.get_json()
    assert fresh["status"] == "open" and fresh["ticket_id"] != first["ticket_id"]
    assert stored(path, first["ticket_id"])["status"] == "closed"
    assert stored(path, first["ticket_id"])["event_ids"] == s12()["event_ids"]
    assert stored(path, fresh["ticket_id"])["actions"] == []
    for stage in ("detected", "applied"):
        old = {**s12(), "stage": stage, "action": None if stage == "detected" else s12()["action"]}
        replay = record(n8n, old, f"cycle-old-{stage}").get_json()
        assert replay["ticket_id"] == first["ticket_id"] and replay["status"] == "closed" and replay["duplicate"]
    assert stored(path, fresh["ticket_id"])["event_ids"] == ["cycle-2-event"]
    applied = record(n8n, new, "cycle-2-applied").get_json()
    assert applied["ticket_id"] == fresh["ticket_id"] and applied["status"] == "responding"
    assert record(n8n, detected_body, "cycle-2-detected").get_json() == fresh



def test_release_does_not_clear_a_different_action_on_the_same_route(apps):
    n8n, _, _ = apps
    record(n8n, s12(), "same-route-block")
    record(n8n, s12(action="lock"), "same-route-lock")
    response = record(n8n, s12("released", action="unblock", result="released"), "same-route-unblock")
    assert response.get_json()["status"] == "responding"
    assert [a["action"] for a in check(n8n, "203.0.113.11", "D")["applied_actions"]] == ["lock"]
    wrong = record(n8n, s12("released", via="pfsense", action="unlock", result="released"), "wrong-route-unlock")
    assert wrong.status_code == 400


def test_existing_group_cannot_silently_change_asset_scope(apps):
    n8n, _, path = apps
    first = record(n8n, s12(), "asset-first-apply").get_json()
    other = record(n8n, {**s12(), "asset_id": "another-portal"}, "asset-other-apply")
    assert other.status_code == 409
    assert len(stored(path, first["ticket_id"])["actions"]) == 1


@pytest.mark.parametrize("query", [
    {}, {"asset_id": "haedam-portal"},
    {"asset_id": "haedam-portal", "via": "portal", "action": "block", "target": ""},
    {"asset_id": "haedam-portal", "via": "unknown", "action": "block", "target": "x"},
    {"asset_id": "haedam-portal", "via": "portal", "action": "block", "target": "x", "seat": "D"},
    [("asset_id", "haedam-portal"), ("via", "portal"), ("action", "block"),
     ("target", "x"), ("target", "y")],
])
def test_active_query_rejects_incomplete_or_ambiguous_scope(apps, query):
    n8n, _, _ = apps
    response = n8n.get("/api/v1/tickets/active", query_string=query, headers={"X-Response-Key": KEY})
    assert response.status_code == 400
    contract("ticket-response").validate(response.get_json())


def test_active_zero_is_distinct_from_unauthorized_unavailable_and_samples(apps, monkeypatch):
    from ticket_store import core, samples
    n8n, dashboard, path = apps
    assert n8n.get("/api/v1/tickets/active").status_code == 401
    assert dashboard.get("/api/v1/tickets/active").status_code == 404
    with db.connect(path) as conn:
        samples.load_samples(conn)
    response = resource_check(n8n)
    assert response.status_code == 200 and response.get_json()["tickets"] == []

    def unavailable(*args):
        raise RuntimeError("synthetic storage failure")

    monkeypatch.setattr(core, "active_for_resource", unavailable)
    response = resource_check(n8n)
    assert response.status_code == 500
    assert response.get_json()["ok"] is False and "tickets" not in response.get_json()


def test_concurrent_replays_keep_one_line_per_route_and_stable_responses(apps):
    n8n, _, path = apps

    def send(via):
        with n8n.application.test_client() as client:
            response = record(client, s12(via=via), f"concurrent-{via}-apply")
            return via, response.status_code, response.get_json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(send, ["portal", "pfsense"] * 4))
    for via in ("portal", "pfsense"):
        route = [(status, body) for v, status, body in responses if v == via]
        assert all(response == route[0] for response in route)
        assert route[0][1]["duplicate"] is False
    ticket_id = responses[0][2]["ticket_id"]
    assert {r[2]["ticket_id"] for r in responses} == {ticket_id}
    assert len(stored(path, ticket_id)["actions"]) == 2
    assert {a["via"] for a in check(n8n, "203.0.113.11", "D")["applied_actions"]} == {"portal", "pfsense"}


def test_reblock_after_release_closes_the_old_round_and_opens_a_new_ticket(apps):
    n8n, _, path = apps
    first = record(n8n, s12(), "exec-1-applied").get_json()
    released = record(n8n, s12("released", action="unblock", result="released"), "exec-2-released").get_json()
    assert released["status"] == "restored"
    again = record(n8n, reblock(finished_at="2026-10-24T16:00:00+09:00"), "exec-3-applied")
    assert again.status_code == 201
    new = again.get_json()
    assert new["created"] is True and new["duplicate"] is False and new["status"] == "responding"
    assert new["ticket_id"] != first["ticket_id"]

    old = stored(path, first["ticket_id"])
    assert old["status"] == "closed" and old["closed_at"]
    assert old["close_note"] == f"재차단: 새 회차로 분리 ({new['ticket_id']})"
    assert [a["result"] for a in old["actions"]] == ["applied", "released"]   # the old round is left as it was
    fresh = stored(path, new["ticket_id"])
    assert [a["result"] for a in fresh["actions"]] == ["applied"] and fresh["event_ids"] == ["sample-graylog-s12-event-02"]
    answer = check(n8n, "203.0.113.11", "D")
    assert answer["ticket_id"] == new["ticket_id"] and [a["result"] for a in answer["applied_actions"]] == ["applied"]
    # the same block while it is active is still a duplicate, on the new ticket
    repeat = record(n8n, reblock(finished_at="2026-10-24T16:00:00+09:00"), "exec-4-applied").get_json()
    assert repeat["ticket_id"] == new["ticket_id"] and repeat["duplicate"] is True


@pytest.mark.parametrize("result, splits", [("applied", True), ("already_applied", True), ("failed", False), ("rejected", False)])
def test_only_an_applied_block_starts_a_new_round(apps, result, splits):
    n8n, _, path = apps
    first = record(n8n, s12(), "exec-1-applied").get_json()
    record(n8n, s12("released", action="unblock", result="released"), "exec-2-released")
    answer = record(n8n, reblock(result=result, applied_verified=False if result == "failed" else True), "exec-3-applied").get_json()
    assert (answer["ticket_id"] != first["ticket_id"]) is splits
    assert stored(path, first["ticket_id"])["status"] == ("closed" if splits else "restored")
    assert ticket_count(path) == (2 if splits else 1)


def test_replay_of_same_event_after_release_does_not_open_a_new_ticket(apps):
    n8n, _, path = apps
    first = record(n8n, s12(), "exec-1-applied").get_json()
    record(n8n, s12("released", action="unblock", result="released"), "exec-2-released")
    replay = record(n8n, s12(finished_at="2026-10-24T16:00:00+09:00"), "exec-3-applied")   # same event_ids
    assert replay.status_code == 200
    assert replay.get_json() == {**first, "created": False, "duplicate": True, "status": "restored"}
    assert ticket_count(path) == 1
    assert [a["result"] for a in stored(path, first["ticket_id"])["actions"]] == ["applied", "released"]


def test_partial_release_keeps_the_ticket_responding(apps):
    n8n, _, _ = apps
    s10 = {**s12(), "seat": "B", "case_id": "S10", "title": "S10"}
    record(n8n, s10, "exec-1-portal-applied")
    record(n8n, {**s10, "action": {**s10["action"], "via": "pfsense"}}, "exec-1-pfsense-applied")
    release = {**s10, "stage": "released", "action": {**s10["action"], "via": "pfsense", "action": "unblock",
                                                      "result": "released"}}
    assert record(n8n, release, "exec-2-pfsense-released").get_json()["status"] == "responding"
    release_portal = {**release, "action": {**release["action"], "via": "portal"}}
    assert record(n8n, release_portal, "exec-2-portal-released").get_json()["status"] == "restored"


def test_check_by_target_finds_other_seats_blocks_under_any_group_key(apps):
    n8n, _, _ = apps
    s1 = {**s12(), "seat": "A", "case_id": "S1", "group_key": "zz_demo", "username": "zz_demo", "title": "S1"}
    record(n8n, s1, "exec-a-applied")
    record(n8n, s12(), "exec-d-applied")
    record(n8n, s12("released", action="unblock", result="released"), "exec-d-released")
    response = n8n.get("/api/v1/tickets/open", query_string={"target": "203.0.113.11"}, headers={"X-Response-Key": KEY})
    contract("ticket-response").validate(response.get_json())
    tickets = response.get_json()["tickets"]
    assert [(t["seat"], [a["via"] for a in t["active_actions"]]) for t in tickets] == [("A", ["portal"])]
    by_group_key = check(n8n, "203.0.113.11")["tickets"]
    assert [t["seat"] for t in by_group_key] == ["D"]
    for query in [{"target": "203.0.113.11", "seat": "D"}, {"target": "a\nb"}, {}]:
        assert n8n.get("/api/v1/tickets/open", query_string=query, headers={"X-Response-Key": KEY}).status_code == 400


def _effect(**action):
    return s12("effect", effect_verified=True, **action)


def test_late_effect_of_previous_round_is_rejected(apps):
    """block 15:00 -> release 15:30 -> re-block 16:00 -> the first round's effect (15:00:40) arrives late."""
    n8n, _, path = apps
    record(n8n, s12(finished_at="2026-10-24T15:00:00+09:00"), "exec-1-applied")
    record(n8n, s12("released", action="unblock", result="released", finished_at="2026-10-24T15:30:00+09:00"), "exec-2-released")
    new = record(n8n, reblock(finished_at="2026-10-24T16:00:00+09:00"), "exec-3-applied").get_json()
    late = record(n8n, _effect(effect_verified_at="2026-10-24T15:00:40+09:00"), "exec-1-effect")
    assert late.status_code == 409
    assert late.get_json() == {"ok": False, "error": {"code": "STALE_EFFECT",
                               "message": "effect_verified_at is earlier than the active action"}}
    ticket = stored(path, new["ticket_id"])
    assert ticket["status"] == "responding"
    assert [a["effect_verified"] for a in ticket["actions"]] == [None]
    assert ticket_count(path) == 2
    # a rejected record leaves no idempotency row: the same key can be sent again with a corrected time
    again = record(n8n, _effect(effect_verified_at="2026-10-24T16:00:30+09:00"), "exec-1-effect")
    assert again.status_code == 200


def test_effect_after_release_without_reblock_is_rejected(apps):
    n8n, _, path = apps
    first = record(n8n, s12(), "exec-1-applied").get_json()
    record(n8n, s12("released", action="unblock", result="released"), "exec-2-released")
    response = record(n8n, _effect(effect_verified_at="2026-10-24T15:10:00+09:00"), "exec-3-effect")
    assert response.status_code == 400 and response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    ticket = stored(path, first["ticket_id"])
    assert ticket["status"] == "restored" and [a["effect_verified"] for a in ticket["actions"]] == [None, None]
    assert ticket_count(path) == 1   # the rejected effect did not open an empty ticket


def test_effect_without_any_ticket_is_rejected_and_leaves_no_trace(apps):
    n8n, _, path = apps
    response = record(n8n, _effect(effect_verified_at="2026-10-24T15:10:00+09:00"), "exec-1-effect")
    assert response.status_code == 400
    assert ticket_count(path) == 0
    conn = db.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM idempotency").fetchone()[0] == 0
    assert db.last_record_at(conn) is None


def test_fresh_effect_after_reblock_verifies_the_new_line(apps):
    n8n, _, path = apps
    first = record(n8n, s12(finished_at="2026-10-24T15:00:00+09:00"), "exec-1-applied").get_json()
    record(n8n, s12("released", action="unblock", result="released", finished_at="2026-10-24T15:30:00+09:00"), "exec-2-released")
    new = record(n8n, reblock(finished_at="2026-10-24T16:00:00+09:00"), "exec-3-applied").get_json()
    done = record(n8n, _effect(effect_verified_at="2026-10-24T16:00:30+09:00"), "exec-3-effect").get_json()
    assert done["ticket_id"] == new["ticket_id"] and done["status"] == "verified"
    assert [a["effect_verified"] for a in stored(path, new["ticket_id"])["actions"]] == [True]
    assert [a["effect_verified"] for a in stored(path, first["ticket_id"])["actions"]] == [None, None]


def test_close_is_refused_while_an_action_is_active(apps):
    n8n, dashboard, path = apps
    first = record(n8n, s12(), "exec-1-applied").get_json()
    record(n8n, _effect(effect_verified_at="2026-10-24T15:00:40+09:00"), "exec-1-effect")
    assert stored(path, first["ticket_id"])["status"] == "verified"
    with pytest.raises(db.InvalidTransition, match="active action remains"):
        db.close_ticket(db.connect(path), first["ticket_id"], "too early")
    assert stored(path, first["ticket_id"])["status"] == "verified"


def test_close_allowed_after_all_actions_are_released(apps):
    n8n, _, path = apps
    first = record(n8n, s12(), "exec-1-applied").get_json()
    record(n8n, _effect(effect_verified_at="2026-10-24T15:00:40+09:00"), "exec-1-effect")
    record(n8n, s12("released", action="unblock", result="released"), "exec-2-released")
    closed = db.close_ticket(db.connect(path), first["ticket_id"], "원복 확인")
    assert closed["status"] == "closed"


def test_check_by_target_includes_closed_ticket_with_active_action(apps):
    """Safety net for tickets closed before this rule existed: the block must still show up."""
    n8n, _, path = apps
    first = record(n8n, s12(), "exec-1-applied").get_json()
    conn = db.connect(path)
    conn.execute("UPDATE tickets SET status = 'closed', closed_at = ?, close_note = 'old data' WHERE ticket_id = ?",
                 ("2026-10-24T17:00:00+09:00", first["ticket_id"]))
    conn.commit()
    response = n8n.get("/api/v1/tickets/open", query_string={"target": "203.0.113.11"}, headers={"X-Response-Key": KEY})
    contract("ticket-response").validate(response.get_json())
    assert [(t["ticket_id"], t["status"], [a["via"] for a in t["active_actions"]])
            for t in response.get_json()["tickets"]] == [(first["ticket_id"], "closed", ["portal"])]


def _cancel_setup(apps):
    n8n, _, path = apps
    app = create_dashboard_app(path)
    return n8n, app.test_client(), app.config["DASHBOARD_TOKEN"], app.config["DASHBOARD_ORIGIN"], path


def cancel(dash, ticket_id, token, origin, note="시험 취소"):
    response = dash.post(f"/api/v1/tickets/{ticket_id}/cancel", json={"note": note},
                         headers={"Origin": origin, "X-Dashboard-Token": token})
    contract("ticket-response").validate(response.get_json())
    return response


def detected():
    return {**s12("detected"), "action": None}


def test_cancel_open_ticket_without_actions_closes_with_note(apps):
    n8n, dash, token, origin, path = _cancel_setup(apps)
    ticket = record(n8n, detected(), "exec-1-detected").get_json()
    done = cancel(dash, ticket["ticket_id"], token, origin)
    assert done.status_code == 200
    closed = done.get_json()["ticket"]
    assert closed["status"] == "closed" and closed["close_note"] == "[취소] 시험 취소" and closed["closed_at"]
    assert stored(path, ticket["ticket_id"])["actions"] == []
    # the next record for the same target starts a fresh ticket
    again = record(n8n, {**detected(), "event_ids": ["sample-graylog-s12-event-09"]}, "exec-2-detected").get_json()
    assert again["created"] is True and again["ticket_id"] != ticket["ticket_id"]


def test_cancel_with_only_a_rejected_line_keeps_the_line(apps):
    n8n, dash, token, origin, path = _cancel_setup(apps)
    ticket = record(n8n, s12(result="rejected", applied_verified=False), "exec-1-applied").get_json()
    assert ticket["status"] == "open"
    assert cancel(dash, ticket["ticket_id"], token, origin).status_code == 200
    kept = stored(path, ticket["ticket_id"])
    assert [a["result"] for a in kept["actions"]] == ["rejected"]   # nothing deleted, no fake effect or release
    assert kept["status"] == "closed" and kept["verified_at"] is None and kept["restored_at"] is None


def test_cancel_refused_with_applied_or_failed_line(apps):
    n8n, dash, token, origin, path = _cancel_setup(apps)
    failed = record(n8n, s12(result="failed", applied_verified=False), "exec-1-applied").get_json()
    assert failed["status"] == "open"   # failed leaves the ticket open, but the target may be half changed
    refused = cancel(dash, failed["ticket_id"], token, origin)
    assert refused.status_code == 409 and refused.get_json()["error"]["code"] == "INVALID_TRANSITION"
    assert stored(path, failed["ticket_id"])["status"] == "open"
    # an applied line on a still-open ticket (inconsistent data) is refused by the line rule itself
    other = record(n8n, {**s12("detected"), "action": None, "group_key": "203.0.113.50", "src_ip": "203.0.113.50",
                         "event_ids": ["sample-graylog-s12-event-50"]}, "exec-2-detected").get_json()
    conn = db.connect(path)
    db.insert_action(conn, other["ticket_id"], s12()["action"], "exec-2-applied", "2026-10-24T15:00:03+09:00")
    conn.commit()
    assert stored(path, other["ticket_id"])["status"] == "open"
    assert cancel(dash, other["ticket_id"], token, origin).status_code == 409


def test_cancel_refused_for_non_open_and_sample_tickets(apps):
    n8n, dash, token, origin, path = _cancel_setup(apps)
    responding = record(n8n, s12(), "exec-1-applied").get_json()
    assert cancel(dash, responding["ticket_id"], token, origin).status_code == 409
    record(n8n, _effect(effect_verified_at="2026-10-24T15:00:40+09:00"), "exec-1-effect")
    assert cancel(dash, responding["ticket_id"], token, origin).status_code == 409   # verified
    record(n8n, s12("released", action="unblock", result="released"), "exec-2-released")
    db.close_ticket(db.connect(path), responding["ticket_id"], "원복 확인")
    assert cancel(dash, responding["ticket_id"], token, origin).status_code == 409   # closed
    samples.load_samples(db.connect(path))
    sample = cancel(dash, "T-20261024-9003", token, origin)   # open, but a synthetic sample
    assert sample.status_code == 409 and "live" in sample.get_json()["error"]["message"]


def test_cancel_requires_origin_token_and_note_and_is_not_on_the_n8n_port(apps):
    n8n, dash, token, origin, path = _cancel_setup(apps)
    ticket = record(n8n, detected(), "exec-1-detected").get_json()
    tid = ticket["ticket_id"]
    assert cancel(dash, tid, token, "http://evil.example").status_code == 403
    assert cancel(dash, tid, "wrong-token", origin).status_code == 403
    assert cancel(dash, tid, token, origin, note="   ").status_code == 400
    assert cancel(dash, tid, token, origin, note="가" * 196).status_code == 400   # "[취소] "(5자) + note must fit 200
    assert cancel(dash, "T-20261024-0000", token, origin).status_code == 404
    assert stored(path, tid)["status"] == "open"
    n8n_try = n8n.post(f"/api/v1/tickets/{tid}/cancel", json={"note": "x"}, headers={"X-Response-Key": KEY})
    assert n8n_try.status_code in (404, 405) and stored(path, tid)["status"] == "open"
    longest = cancel(dash, tid, token, origin, note="가" * 195)   # the longest note that fits
    assert longest.status_code == 200 and len(longest.get_json()["ticket"]["close_note"]) == 200


@pytest.mark.parametrize("change", ["asset", "active"])
def test_new_detected_round_refuses_scope_or_active_inconsistency_and_rolls_back(apps, change):
    n8n, _, path = apps
    first = record(n8n, s12(), "guard-one-apply").get_json()
    record(n8n, s12("released", action="unblock", result="released"), "guard-one-release")
    if change == "active":
        with db.connect(path) as conn:
            db.insert_action(conn, first["ticket_id"], s12()["action"], "legacy-active-row", db.now_iso())
    fresh = {**s12(), "stage": "detected", "action": None, "event_ids": ["guard-new-event"]}
    if change == "asset":
        fresh["asset_id"] = "another-portal"
    refused = record(n8n, fresh, "guard-new-detected")
    assert refused.status_code == 409 and refused.get_json()["error"]["code"] == "INVALID_TRANSITION"
    assert ticket_count(path) == 1
    original = stored(path, first["ticket_id"])
    assert original["status"] == "restored" and original["event_ids"] == s12()["event_ids"]
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM idempotency WHERE key = 'guard-new-detected'").fetchone()[0] == 0


def test_mixed_old_and_current_event_ids_never_mutate_the_new_round(apps):
    n8n, _, path = apps
    old = record(n8n, s12(), "mixed-one-apply").get_json()
    record(n8n, s12("released", action="unblock", result="released"), "mixed-one-release")
    fresh = record(n8n, {**s12(), "stage": "detected", "action": None,
                        "event_ids": ["mixed-new-event"]}, "mixed-new-detected").get_json()
    mixed = {**s12(), "stage": "detected", "action": None,
             "event_ids": ["mixed-new-event", *s12()["event_ids"], "mixed-unseen-event"]}
    response = record(n8n, mixed, "mixed-old-replay").get_json()
    assert response["ticket_id"] == old["ticket_id"] and response["status"] == "closed" and response["duplicate"]
    assert stored(path, fresh["ticket_id"])["event_ids"] == ["mixed-new-event"]
    assert stored(path, fresh["ticket_id"])["actions"] == []
