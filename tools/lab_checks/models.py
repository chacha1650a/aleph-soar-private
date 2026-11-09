"""Strict local formats and pinned comparison policies; no network operations."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
FORMATS = ROOT / "orchestration/lab-check"
VANTAGES = {"A": "portal-vm", "B": "boundary-host", "C": "ticket-host", "D": "graylog-host"}
MAX_BYTES = 2 * 1024 * 1024


class LabError(ValueError):
    """Public messages contain no input values, credentials or raw responses."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LabError("Duplicate JSON key.")
        result[key] = value
    return result


def _constant(_value):
    raise LabError("Non-finite JSON number.")


def read_json(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    return parse_json(raw)


def parse_json(raw):
    try:
        if len(raw) > MAX_BYTES:
            raise LabError("JSON exceeds the local size limit.")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise LabError("Invalid UTF-8 JSON.") from error


def validate(kind, value):
    schema = read_json(FORMATS / f"{kind}.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    if next(validator.iter_errors(value), None) is not None:
        raise LabError(f"Invalid {kind} schema.")


def instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as error:
        raise LabError("Expected a timestamp with an explicit UTC offset.") from error


def policy(card):
    validate("card", card)
    profiles = read_json(FORMATS / "profiles.json")
    selected = profiles.get(card["profile_id"])
    if selected is None or selected["scenario_id"] != card["scenario_id"]:
        raise LabError("Unknown scenario/profile version.")
    if card["policy_sha256"] != digest(selected):
        raise LabError("Pinned policy changed; use the matching policy version and a new card.")
    if card["profile"] != selected["profile"]:
        raise LabError("Profile scope mismatch.")
    ids = [check["id"] for check in selected["checks"]]
    if len(card["required_checks"]) != len(set(card["required_checks"])) or set(card["required_checks"]) != set(ids):
        raise LabError("Required checks differ from the pinned policy.")
    seats = {check["seat"] for check in selected["checks"]}
    if set(card["expected_versions"]) != seats:
        raise LabError("Expected versions must cover exactly the required seats.")
    if card["input_owner"] == card["reviewer"]:
        raise LabError("The reviewer must be independent of the input owner.")
    if not instant(card["input_start"]) < instant(card["input_end"]) <= instant(card["observation_end"]):
        raise LabError("Invalid input/observation window.")
    return selected


def validate_input(card, data):
    validate("input", data)
    if (data["run_id"], data["card_sha256"], data["environment"]) != (card["run_id"], digest(card), card["environment"]):
        raise LabError("Input belongs to a different card or environment.")
    if data["source_ip"] != card["source_ip"] or data["target_ip"] != card["target_ip"]:
        raise LabError("Input source or target differs from the card.")
    if not instant(card["input_start"]) <= instant(data["started_at"]) <= instant(data["ended_at"]) <= instant(card["input_end"]):
        raise LabError("Input is outside the approved window.")
    if (card["environment"] == "fixture") != (data["origin"] == "synthetic"):
        raise LabError("Synthetic and lab input cannot be mixed.")


def validate_receipt(card, receipt):
    selected = policy(card)
    validate("receipt", receipt)
    if (receipt["run_id"], receipt["card_sha256"], receipt["environment"]) != (card["run_id"], digest(card), card["environment"]):
        raise LabError("Receipt belongs to a different card or environment.")
    allowed = {c["id"] for c in selected["checks"] if c["seat"] == receipt["seat"]}
    if not allowed:
        raise LabError("Seat is outside this profile scope.")
    ids = [check["check_id"] for check in receipt["checks"]]
    if len(set(ids)) != len(ids) or not set(ids) <= allowed:
        raise LabError("Unknown, duplicate or incorrectly owned check.")
    if (card["environment"] == "fixture") != (receipt["origin"] == "synthetic"):
        raise LabError("Synthetic and lab evidence cannot be mixed.")
    for check in receipt["checks"]:
        if check["count"] is not None and not (
            check["availability"] == "available" and check["query_status"] == "ok" and check["coverage"] == "complete"
            and check["definition_state"] in ("active", "not_applicable")
        ):
            raise LabError("Unconfirmed count must be null.")
    if receipt["query_start"] is not None and receipt["query_end"] is not None:
        if instant(receipt["query_start"]) > instant(receipt["query_end"]):
            raise LabError("Reversed query window.")


def placeholder(card, seat, phase, reason, now):
    selected = policy(card)
    return {
        "schema_version": 1, "receipt_id": f"{seat}-{phase}-unavailable", "run_id": card["run_id"],
        "card_sha256": digest(card), "environment": card["environment"],
        "origin": "synthetic" if card["environment"] == "fixture" else "reported",
        "seat": seat, "phase": phase, "attempt_id": "unavailable", "collector_version": "file-export-v1",
        "vantage_id": "unverified", "version": "unknown", "observed_at": now.isoformat(),
        "query_start": None, "query_end": None, "clock_uncertainty_seconds": None,
        "checks": [{"check_id": c["id"], "availability": "unknown", "definition_state": "unknown",
                    "query_status": "not_run", "coverage": "unknown", "count": None, "reason_code": reason}
                   for c in selected["checks"] if c["seat"] == seat],
    }
