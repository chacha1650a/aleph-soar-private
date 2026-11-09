"""Deterministic comparison of bounded exports, never a live readiness authority."""

from collections import Counter
from datetime import datetime, timedelta, timezone

from . import VERSION
from .models import LabError, VANTAGES, digest, instant, policy, validate_input, validate_receipt


def compare(card, receipts, phase, input_data=None, now=None):
    selected = policy(card)
    if phase not in ("prepare", "final"):
        raise LabError("Unknown receipt phase.")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise LabError("Comparison time requires a UTC offset.")
    if input_data is not None:
        validate_input(card, input_data)
    by_seat, checks, rows, event_sets = {}, {}, [], {}
    for receipt in receipts:
        validate_receipt(card, receipt)
        if receipt["phase"] != phase:
            raise LabError("Do not mix preparation and final receipts.")
        if receipt["seat"] in by_seat:
            raise LabError("Conflicting receipts; select one attempt per seat and phase.")
        by_seat[receipt["seat"]] = receipt
        checks.update({c["check_id"]: c for c in receipt["checks"]})

    start = instant(input_data["started_at"]) if input_data else instant(card["input_start"])
    end = instant(card["observation_end"])

    def row(spec, verdict, reason, count=None, excluded=0):
        result = dict(check_id=spec["id"], seat=spec["seat"], verdict=verdict, reason_code=reason,
                      count=count, excluded_count=excluded)
        rows.append(result)
        return result

    def receipt_problem(receipt):
        if receipt["vantage_id"] != VANTAGES[receipt["seat"]]:
            return "VANTAGE_UNVERIFIED"
        if receipt["version"] != card["expected_versions"][receipt["seat"]]:
            return "VERSION_CHANGED"
        uncertainty = receipt["clock_uncertainty_seconds"]
        if uncertainty is None:
            return "CLOCK_UNKNOWN"
        margin = timedelta(seconds=uncertainty)
        observed = instant(receipt["observed_at"])
        if observed - margin > now:
            return "FUTURE_OBSERVATION"
        if phase == "prepare":
            if now - observed + margin > timedelta(seconds=card["prepare_valid_for_seconds"]):
                return "STALE_PREPARATION"
            return None
        if input_data is None:
            return "MISSING_INPUT"
        if now - margin < end or observed - margin < end:
            return "OBSERVATION_PENDING"
        if receipt["query_start"] is None or receipt["query_end"] is None:
            return "QUERY_WINDOW_UNKNOWN"
        if instant(receipt["query_start"]) > start - margin or instant(receipt["query_end"]) < end + margin:
            return "QUERY_WINDOW_INCOMPLETE"
        return None

    def in_scope(records, receipt):
        matched, excluded, boundary = [], 0, False
        margin = receipt["clock_uncertainty_seconds"]
        for record in records:
            at = instant(record["at"])
            if record["src_ip"] != card["source_ip"]:
                excluded += 1
                continue
            if margin and min(abs((at - start).total_seconds()), abs((at - end).total_seconds())) <= margin:
                boundary = True
            if start <= at < end:
                matched.append(record)
            else:
                excluded += 1
        return matched, excluded, boundary

    if phase == "final" and input_data is not None and input_data["count"] != card["expected_input_count"]:
        row({"id": "input.count", "seat": card["input_owner"]}, "fail", "INPUT_COUNT_MISMATCH", input_data["count"])

    for spec in selected["checks"]:
        check = checks.get(spec["id"])
        receipt = by_seat.get(spec["seat"])
        if receipt is None or check is None:
            row(spec, "unknown", "MISSING_RECEIPT" if receipt is None else "MISSING_CHECK")
            continue
        if receipt["vantage_id"] == "unverified" and check["reason_code"] in (
            "NOT_CONFIGURED", "SOURCE_UNAVAILABLE", "COLLECTOR_TIMEOUT", "COLLECTOR_FAILED"
        ):
            row(spec, "unknown", check["reason_code"])
            continue
        problem = receipt_problem(receipt)
        if problem:
            row(spec, "unknown", problem)
            continue
        if spec.get("absent_store_allowed") and check["availability"] == "unavailable":
            store = next((r for r in rows if r["check_id"] == "C.store"), None)
            if store and store["verdict"] == "pass":
                row(spec, "not_applicable", "STORE_NOT_RUNNING_FUNCTION_UNVERIFIED")
                continue
        if check["query_status"] != "ok" or check["coverage"] != "complete":
            row(spec, "unknown", check["reason_code"] if check["reason_code"] != "NONE" else "QUERY_INCOMPLETE")
            continue
        kind = spec["kind"]
        if kind == "availability":
            value = check["availability"]
            verdict = "unknown" if value == "unknown" else "pass" if value == spec["expected"] else "fail"
            row(spec, verdict, "EXPECTED_ENVIRONMENT_STATE" if verdict == "pass" else "STORE_AVAILABILITY")
            continue
        if check["availability"] != "available":
            row(spec, "unknown", "SERVICE_UNAVAILABLE")
            continue
        if kind == "definition":
            value = check["definition_state"]
            verdict = "unknown" if value in ("unknown", "not_applicable") else "pass" if value == spec["expected"] else "fail"
            row(spec, verdict, "DEFINITION_STATE")
            continue
        if phase == "prepare":
            row(spec, "pass", "EXPORTED_PREPARATION_METADATA_ONLY")
            continue
        if kind == "count":
            count = check["count"]
            if count is None:
                row(spec, "unknown", "COUNT_UNCONFIRMED")
            else:
                expected = card["expected_input_count"] if spec["expected"] == "input" else spec["expected"]
                row(spec, "pass" if count == expected else "fail", "COUNT_COMPARISON", count)
        elif kind == "fact":
            value = check.get("value")
            row(spec, "unknown" if value is None else "pass" if value is True else "fail", "TARGET_STATE")
        elif kind == "events":
            if "events" not in check:
                row(spec, "unknown", "EVENT_EXPORT_MISSING")
                continue
            events, excluded, uncertain = in_scope(check["events"], receipt)
            if uncertain:
                row(spec, "unknown", "CLOCK_BOUNDARY_AMBIGUOUS", excluded=excluded)
                continue
            counts = Counter(event["key"] for event in events)
            if any(value > 1 for value in counts.values()):
                row(spec, "fail", "DUPLICATE_EVENT", len(events), excluded)
                continue
            mapped = {event["key"]: event for event in events}
            if "reference" not in spec:
                verdict = "pass" if len(events) == card["expected_event_count"] else "fail"
                row(spec, verdict, "SOURCE_EVENT_COUNT", len(events), excluded)
                if verdict == "pass":
                    event_sets[spec["id"]] = mapped
                continue
            reference = event_sets.get(spec["reference"])
            if reference is None:
                row(spec, "unknown", "REFERENCE_UNCONFIRMED", excluded=excluded)
                continue
            if set(reference) != set(mapped):
                row(spec, "fail", "EVENT_ID_MISMATCH", len(events), excluded)
                continue
            if any(any(field not in event["fields"] for field in spec["fields"]) for event in reference.values()):
                row(spec, "unknown", "SOURCE_FIELDS_MISSING", excluded=excluded)
                continue
            mismatch = any(
                instant(mapped[key]["at"]) != instant(original["at"])
                or mapped[key]["src_ip"] != original["src_ip"]
                or any(mapped[key]["fields"].get(field) != original["fields"][field] for field in spec["fields"])
                for key, original in reference.items()
            )
            row(spec, "fail" if mismatch else "pass", "NORMALIZATION_MISMATCH" if mismatch else "EVENTS_MATCHED", len(events), excluded)
        elif kind == "response":
            if "executions" not in check:
                row(spec, "unknown", "EXECUTION_DETAIL_MISSING")
                continue
            executions, excluded, uncertain = in_scope(check["executions"], receipt)
            if uncertain:
                row(spec, "unknown", "CLOCK_BOUNDARY_AMBIGUOUS", excluded=excluded)
            elif len({e["key"] for e in executions}) != len(executions):
                row(spec, "fail", "DUPLICATE_EXECUTION", len(executions), excluded)
            elif spec["expected"] == "none":
                row(spec, "fail" if executions else "pass", "BASELINE_EXECUTION_COUNT", len(executions), excluded)
            elif not executions:
                row(spec, "fail", "ACTUAL_CALL_MISSING", 0, excluded)
            elif any(e["dry_run"] is None or e["http_executed"] is None for e in executions):
                row(spec, "unknown", "EXECUTION_DETAIL_MISSING", excluded=excluded)
            else:
                actual = [e for e in executions if e["dry_run"] is False and e["http_executed"] is True]
                if not actual:
                    row(spec, "fail", "DRY_RUN_OR_HTTP_NOT_EXECUTED", len(executions), excluded)
                elif any(e["http_status"] is None or e["target_effect"] is None for e in actual):
                    row(spec, "unknown", "TARGET_EFFECT_UNCONFIRMED", excluded=excluded)
                else:
                    ok = all(200 <= e["http_status"] < 300 and e["target_effect"] is True for e in actual)
                    row(spec, "pass" if ok else "fail", "ACTUAL_CALL_AND_REPORTED_EFFECT", len(actual), excluded)

    code = 4 if any(r["verdict"] == "fail" for r in rows) else 3 if any(r["verdict"] == "unknown" for r in rows) else 0
    return {
        "schema_version": 1, "engine_version": VERSION, "run_id": card["run_id"], "card_sha256": digest(card),
        "policy_sha256": digest(selected), "input_sha256": digest(input_data) if input_data is not None else None,
        "receipt_sha256": [digest(r) for r in sorted(receipts, key=lambda r: r["seat"])],
        "environment": card["environment"], "mode": "offline_exports", "phase": phase, "scope": selected["scope"],
        "generated_at": now.isoformat(), "status": {0: "matched", 3: "incomplete", 4: "mismatch"}[code],
        "exit_code": code, "ready_candidate": False, "final_complete": False,
        "readiness_reason": "REPLAY_ONLY" if card["environment"] == "fixture" else "OFFLINE_EXPORT_UNVERIFIED",
        "rows": rows,
    }
