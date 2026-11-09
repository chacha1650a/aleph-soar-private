from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import pytest
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]


def read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema))
    for schema in (json.loads(path.read_text(encoding="utf-8")) for path in (ROOT / "contracts").glob("*.schema.json")))


def validator(name):
    schema = read_json(f"contracts/{name}.schema.json")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=REGISTRY,
                                format_checker=FormatChecker(formats=["date-time", "ipv4", "ipv6"]))


def test_candidate_shared_control_examples_are_explicitly_synthetic():
    check = validator("candidate-shared-control")
    examples = read_json("contracts/candidate-shared-control-examples.json")
    for sample in examples.values():
        check.validate(sample)
    for change in ({"allow_target_call": True}, {"synthetic_only": False}, {"seat": "A"}):
        with pytest.raises(ValidationError):
            check.validate({**examples["waiting"], **change})


@pytest.mark.parametrize("name", ["auth-failure", "auth-success", "role-changed", "data-read"])
def test_event_examples_conform_to_shared_contract(name):
    validator("event").validate(read_json(f"contracts/examples/{name}.json"))


@pytest.mark.parametrize("change", [
    {"timestamp": "2026-10-15T01:00:00"},
    {"timestamp": "2026-13-15T01:00:00Z"},
    {"src_ip": "not-an-ip"},
    {"password": "must-not-be-logged"},
    {"details": {"access_token": "must-not-be-logged"}},
    {"event_id": ""},
])
def test_contract_rejects_invalid_time_identity_and_unapproved_fields(change):
    event = read_json("contracts/examples/auth-failure.json")
    event.update(change)
    with pytest.raises(ValidationError):
        validator("event").validate(event)


def test_incident_example_references_existing_same_subject_events():
    incident = read_json("contracts/examples/incident.json")
    validator("incident").validate(incident)
    examples = [json.loads(path.read_text(encoding="utf-8"))
                for path in (ROOT / "contracts/examples").glob("*.json") if path.stem != "incident"]
    by_id = {event["event_id"]: event for event in examples}
    assert len(by_id) == len(examples)
    for event_id in incident["event_ids"]:
        assert by_id[event_id]["username"] == incident["username"]
        assert by_id[event_id]["asset_id"] == incident["asset_id"]
    duplicate = deepcopy(incident)
    duplicate["event_ids"].append(duplicate["event_ids"][0])
    with pytest.raises(ValidationError):
        validator("incident").validate(duplicate)


def test_portal_event_contract_supports_anonymous_requests_without_private_details():
    event = read_json("contracts/portal-examples/flow.json")["event"]
    validator("portal-event").validate(event)
    for change in [{"src_ip": "invalid"}, {"details": {"password": "secret"}}, {"username": 123}, {"event_type": "unknown"}]:
        with pytest.raises(ValidationError):
            validator("portal-event").validate({**event, **change})


def test_portal_event_carries_web_root_file_keys_and_block_targets_only():
    flow = read_json("contracts/portal-examples/flow.json")
    access, block = flow["file_access_event"], flow["ip_block_event"]
    validator("portal-event").validate(access)
    validator("portal-event").validate(block)
    for key in ["assets/app.js", "index.html", "favicon.svg", "assets/a..b.js", "assets/sub/app.js", "a" * 200]:
        validator("portal-event").validate({**access, "details": {**access["details"], "file_key": key}})
    for key in ["assets/app.js?v=1", "assets/app.js#x", "/assets/app.js", "assets\\app.js", "../secret", "assets/../../x", "",
                "C:/Windows/system.ini", "assets/\n../secret", "assets/review.js\n", "assets/a\x01b.js", "assets/a\x7fb.js",
                "assets//x.js", "assets/./x.js", "assets/", "a" * 201]:
        with pytest.raises(ValidationError):
            validator("portal-event").validate({**access, "details": {**access["details"], "file_key": key}})
    with pytest.raises(ValidationError):
        validator("portal-event").validate({**block, "details": {**block["details"], "target_ip": "not-an-ip"}})


def test_portal_unlock_event_records_actor_and_false_positive_reason_only():
    unlocked = read_json("contracts/portal-examples/flow.json")["account_unlocked_event"]
    validator("portal-event").validate(unlocked)
    for change in [{"reason_code": "other"}, {"actor_user_id": "5"}, {"actor_username": "a" * 41}]:
        with pytest.raises(ValidationError):
            validator("portal-event").validate({**unlocked, "details": {**unlocked["details"], **change}})


def test_portal_error_optional_fields_remain_compatible_and_exclude_unapproved_data():
    sample=read_json("contracts/portal-examples/validation-error.json")
    validator("portal-error").validate(sample)
    validator("portal-error").validate(read_json("contracts/portal-examples/flow.json")["denied"])
    for fields in [{"unknown":"unapproved"}, {"title":123}, {}]:
        with pytest.raises(ValidationError):
            validator("portal-error").validate({**sample,"error":{**sample["error"],"fields":fields}})


def test_portal_admin_listing_has_explicit_search_scope_and_no_secret_user_fields():
    sample = read_json("contracts/portal-examples/admin-users-filtered.json")
    check = validator("portal-admin-users")
    check.validate(sample)
    summary = sample["data"]["summary"]
    assert sum(summary["roles"].values()) == summary["locked"] + summary["unlocked"] == summary["total"]
    # A filtered list can have fewer matches than the search-only summary.
    assert sample["data"]["total"] < summary["total"]
    for change in ({"summary": None}, {"page_size": 51}, {"total": -1}):
        with pytest.raises(ValidationError):
            check.validate({**sample, "data": {**sample["data"], **change}})
    secret = deepcopy(sample)
    secret["data"]["items"][0]["password_hash"] = "never-public"
    with pytest.raises(ValidationError):
        check.validate(secret)


def expected_group_key(record):
    if record["seat"] == "A":
        return record["username"]
    if record["seat"] in ("B", "D"):
        return record["src_ip"]
    return f'{record["asset_id"]}:{record["action"]["target"]}'


@pytest.mark.parametrize("name", ["record-s12-applied", "record-s7-effect"])
def test_ticket_record_examples_follow_seat_group_key_rule(name):
    record = read_json(f"contracts/ticket-examples/{name}.json")
    validator("ticket-record").validate(record)
    assert record["group_key"] == expected_group_key(record)


@pytest.mark.parametrize("change", [
    {"status": "open"}, {"ticket_id": "T-20261024-0001"}, {"dedup_key": "S12-203.0.113.11-112-block"},
    {"stage": "record"}, {"stage": None},
    {"seat": "E"}, {"case_id": "S99"}, {"src_ip": "not-an-ip"}, {"group_key": ""}, {"group_key": "a\nb"},
    {"password": "must-not-be-logged"}, {"event_ids": []},
])
def test_ticket_record_rejects_store_owned_and_unapproved_fields(change):
    record = read_json("contracts/ticket-examples/record-s12-applied.json")
    record.update(change)
    with pytest.raises(ValidationError):
        validator("ticket-record").validate(record)


@pytest.mark.parametrize("change", [
    {"bot": 112}, {"bot": "1x2"}, {"via": "ssh"}, {"result": "succeeded"}, {"requested_at": "2026-10-24T15:00:00"},
    {"action_id": "5678-applied"}, {"api_key": "must-not-be-logged"},
])
def test_ticket_record_action_uses_agreed_formats(change):
    record = read_json("contracts/ticket-examples/record-s12-applied.json")
    record["action"].update(change)
    with pytest.raises(ValidationError):
        validator("ticket-record").validate(record)
    validator("ticket-record").validate(
        {**read_json("contracts/ticket-examples/record-s12-applied.json"), "stage": "detected", "action": None})


def test_ticket_example_is_sample_and_stores_action_ids_per_stage():
    ticket = read_json("contracts/ticket-examples/ticket-s7.json")
    validator("ticket").validate(ticket)
    assert ticket["data_origin"] == "sample"
    record = read_json("contracts/ticket-examples/record-s7-effect.json")
    assert ticket["group_key"] == record["group_key"] == expected_group_key(record)
    for change in [{"status": "contained"}, {"event_ids": ["x", "x"]}, {"ticket_id": "INC-1"}]:
        with pytest.raises(ValidationError):
            validator("ticket").validate({**ticket, **change})
    for change in [{"action_id": "short"}, {"action_id": "has space-applied"}, {"duplicate": None}, {"extra": 1}]:
        with pytest.raises(ValidationError):
            validator("ticket").validate({**ticket, "actions": [{**ticket["actions"][0], **change}]})


def test_ticket_record_stage_decides_whether_action_is_required_or_updated():
    applied = read_json("contracts/ticket-examples/record-s12-applied.json")
    effect = read_json("contracts/ticket-examples/record-s7-effect.json")
    validator("ticket-record").validate(effect)
    bad = [
        {**applied, "stage": "detected"},
        {**applied, "action": None},
        {**effect, "action": {**effect["action"], "effect_verified": None}},
        {**effect, "action": {**effect["action"], "effect_verified_at": None}},
        {**applied, "stage": "released"},
    ]
    for record in bad:
        with pytest.raises(ValidationError):
            validator("ticket-record").validate(record)
    validator("ticket-record").validate(
        {**applied, "stage": "released", "action": {**applied["action"], "result": "released"}})


def test_ticket_responses_use_agreed_ok_shape_only():
    responses = read_json("contracts/ticket-examples/responses.json")
    for response in responses.values():
        validator("ticket-response").validate(response)
    created = responses["record_created"]
    none = responses["check_seat_none"]
    for response in [{"success": True, "data": {k: v for k, v in created.items() if k != "ok"}},
                     {**created, "ok": False}, {**created, "api_key": "x"}, {**created, "status": "contained"},
                     {**none, "ticket_id": "T-20261024-0002"},
                     {**responses["check_seat_open"], "ticket_id": None},
                     {**responses["error_validation"], "error": {"code": "SECRET", "message": "x"}}]:
        with pytest.raises(ValidationError):
            validator("ticket-response").validate(response)
