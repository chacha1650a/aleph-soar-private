"""Draft checks for the S7 contract proposal (not part of the adopted test suite).

Run from the repository root:
    python -m pytest docs/s7-draft/test_s7_contract_draft.py -q
"""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import pytest

DRAFT = Path(__file__).resolve().parent
ROOT = DRAFT.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validator(path):
    schema = read(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker(formats=["date-time", "ipv4", "ipv6"]))


EVENT = validator(DRAFT / "event.schema.v1.1-draft.json")
INCIDENT = validator(DRAFT / "incident.schema.v1.1-draft.json")
NEW_EVENTS = ["fim-file-created", "web-file-accessed", "fim-file-modified"]


@pytest.mark.parametrize("name", ["auth-failure", "auth-success", "role-changed", "data-read"])
def test_adopted_v1_0_examples_still_valid(name):
    EVENT.validate(read(ROOT / f"contracts/examples/{name}.json"))


def test_adopted_v1_0_incident_example_still_valid():
    INCIDENT.validate(read(ROOT / "contracts/examples/incident.json"))


@pytest.mark.parametrize("name", NEW_EVENTS)
def test_new_event_examples_valid(name):
    EVENT.validate(read(DRAFT / f"examples/{name}.json"))


def test_s7_incident_links_events_with_same_file_and_asset():
    incident = read(DRAFT / "examples/incident-s7.json")
    INCIDENT.validate(incident)
    events = {e["event_id"]: e for e in (read(DRAFT / f"examples/{n}.json") for n in NEW_EVENTS)}
    assert len(events) == len(NEW_EVENTS)
    for event_id in incident["event_ids"]:
        assert events[event_id]["details"]["file_path"] == incident["file_path"]
        assert events[event_id]["asset_id"] == incident["asset_id"]


def mutated(name, **change):
    event = read(DRAFT / f"examples/{name}.json")
    for key, value in change.items():
        if value is None:
            event.pop(key, None)
        else:
            event[key] = value
    return event


@pytest.mark.parametrize("name,change", [
    ("fim-file-created", {"details": None}),
    ("fim-file-created", {"details": {"sha256_after": "0" * 64}}),
    ("fim-file-created", {"details": {"file_path": "/var/www/index.html"}}),
    ("fim-file-created", {"details": {"file_path": "../etc/passwd"}}),
    ("fim-file-created", {"details": {"file_path": "static/../../etc/passwd"}}),
    ("fim-file-created", {"details": {"file_path": "static\\uploads\\x.txt"}}),
    ("fim-file-created", {"details": {"file_path": "a.txt", "file_content": "must-not-be-logged"}}),
    ("fim-file-created", {"details": {"file_path": "a.txt", "sha256_after": "XYZ"}}),
    ("fim-file-created", {"password": "must-not-be-logged"}),
    ("web-file-accessed", {"src_ip": None}),
    ("web-file-accessed", {"src_ip": "not-an-ip"}),
    ("web-file-accessed", {"details": {"file_path": "a.txt", "http_method": "GET"}}),
    ("web-file-accessed", {"details": {"file_path": "a.txt", "http_method": "GET", "http_status": 99}}),
    ("web-file-accessed", {"details": {"file_path": "a.txt", "http_method": "TRACE", "http_status": 200}}),
    ("web-file-accessed", {"timestamp": "2026-10-21T01:02:00"}),
])
def test_draft_rejects_invalid_fim_and_web_events(name, change):
    with pytest.raises(ValidationError):
        EVENT.validate(mutated(name, **change))


@pytest.mark.parametrize("event_type", ["auth.login_failed", "data.read"])
@pytest.mark.parametrize("missing", ["username", "src_ip"])
def test_existing_event_types_still_require_username_and_src_ip(event_type, missing):
    event = read(ROOT / "contracts/examples/auth-failure.json")
    event["event_type"] = event_type
    event.pop(missing)
    with pytest.raises(ValidationError):
        EVENT.validate(event)


def test_incident_needs_username_or_file_path():
    incident = deepcopy(read(DRAFT / "examples/incident-s7.json"))
    incident.pop("file_path")
    with pytest.raises(ValidationError):
        INCIDENT.validate(incident)
    incident["file_path"] = "../x"
    with pytest.raises(ValidationError):
        INCIDENT.validate(incident)
