"""Authenticated local reference API for the synthetic shared-release candidate.

App factory only: no listen port, production identity provider or live target wiring.
"""
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re

from flask import Flask, g, jsonify, request
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

from tools.control_audit import ControlAudit
from tools.resource_gate import Conflict
from tools.shared_release_simulation import SharedReleaseSimulation
from tools.ticket_http import _unique, _nonfinite

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Principal:
    identity: str
    role: str
    seats: frozenset


def create_shared_control_api(simulation, audit, credentials):
    if type(simulation) is not SharedReleaseSimulation or type(audit) is not ControlAudit:
        raise ValueError("exact synthetic coordinator and local audit store required")
    if not credentials:
        raise ValueError("explicit candidate credentials required")
    identities = {}
    for token, principal in credentials.items():
        if (not isinstance(token, str) or not re.fullmatch(r"[!-~]{16,200}", token)
                or not isinstance(principal, Principal) or principal.role not in ("owner", "recovery")
                or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", principal.identity)
                or not isinstance(principal.seats, frozenset) or not principal.seats <= {"A", "B", "C", "D"}):
            raise ValueError("invalid server-side candidate credential configuration")
        if principal.identity in identities and identities[principal.identity] != principal:
            raise ValueError("one principal identity cannot have conflicting grants")
        identities[principal.identity] = principal
    configured = tuple(credentials.items())
    schema = json.loads((ROOT / "contracts/candidate-shared-control.schema.json").read_text(encoding="utf-8"))
    registry = Registry().with_resource(schema["$id"], Resource.from_contents(schema))

    def validate(kind, value):
        Draft202012Validator({"$ref": schema["$id"] + "#/$defs/" + kind}, registry=registry).validate(value)

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 8192

    def error(code, status):
        return {"ok": False, "synthetic_only": True, "allow_target_call": False, "error": {"code": code}}, status

    def success(outcome):
        data = {"ok": True, "synthetic_only": True, "allow_target_call": False,
                "result": {k: v for k, v in outcome.items() if k in ("state", "plan_id", "resource", "claims_count", "operation_status",
                    "journal_id", "revision", "related_state", "plan_state", "resolution_allowed", "review_hash")}}
        status = 202 if outcome["state"] in ("pending", "cleanup_unconfirmed") else 200
        if outcome["state"] in ("held", "busy"):
            return error("PRECONDITION_FAILED", 409)
        return data, status

    def body(kind):
        if not request.is_json:
            raise ValueError("JSON required")
        parsed = json.loads(request.get_data().decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite)
        validate(kind, parsed)
        return parsed

    @app.before_request
    def authenticate():
        given = request.headers.get("X-Control-Key", "").encode("utf-8")
        g.principal = None
        for token, principal in configured:
            if hmac.compare_digest(given, token.encode("ascii")):
                g.principal = principal
        if g.principal is None:
            return error("UNAUTHORIZED", 401)

    @app.after_request
    def audit_response(response):
        data = response.get_json(silent=True)
        try:
            validate("response", data)
            principal = getattr(g, "principal", None)
            code = data.get("error", {}).get("code", data.get("result", {}).get("state", "unknown"))
            audit.event(principal.identity if principal else None, request.endpoint or "unmatched", response.status_code, code)
        except Exception:
            payload, status = error("SERVER_ERROR", 500)
            response = jsonify(payload)
            response.status_code = status
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(Exception)
    def failures(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return error("NOT_FOUND" if exc.code == 404 else "VALIDATION_ERROR", exc.code)
        if isinstance(exc, (ValueError, ValidationError, UnicodeError)):
            return error("VALIDATION_ERROR", 400)
        return error("SERVER_ERROR", 500)

    def mutate(payload, operation, *, related_request_id=None, plan_id=None):
        key = request.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{8,40}", key):
            return error("VALIDATION_ERROR", 400)
        principal = g.principal.identity
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        fingerprint = hashlib.sha256(json.dumps([request.endpoint, request.view_args, payload], sort_keys=True).encode()).hexdigest()
        synthetic_id = "api-" + hashlib.sha256(json.dumps([principal, key]).encode()).hexdigest()[:32]
        context = {"request_ref": synthetic_id, "related_request_id": related_request_id or synthetic_id,
                   "operation": request.endpoint, "plan_id": plan_id}
        state, cached = audit.begin(principal, key_hash, fingerprint, context)
        if state == "conflict":
            return error("IDEMPOTENCY_CONFLICT", 409)
        if state == "pending":
            return error("RECONCILIATION_REQUIRED", 409)
        if state == "cached":
            status, data = cached
            return data, status
        try:
            data, status = success(operation(synthetic_id))
        except Conflict:
            data, status = error("IDEMPOTENCY_CONFLICT", 409)
        except Exception:
            # Unknown coordinator result: keep API journal pending, never re-execute automatically.
            return error("SERVER_ERROR", 500)
        validate("response", data)
        audit.finish(principal, key_hash, status, data)
        return data, status

    @app.post("/candidate/v1/shared/intents")
    def intent():
        if g.principal.role != "owner":
            return error("FORBIDDEN", 403)
        data = body("intent")
        try:
            ticket = simulation.tickets.ticket(data["ticket_id"])
            allowed = ticket["seat"] in g.principal.seats and ticket["asset_id"] == data["resource"]["asset_id"] and any(
                a["action_id"] == data["action_id"] and not a["duplicate"] and a["result"] in ("applied", "already_applied")
                and all(a[k] == data["resource"][k] for k in ("via", "action", "target")) for a in ticket["actions"])
        except Exception:
            allowed = False
        if not allowed:
            return error("FORBIDDEN", 403)
        method = simulation.withdraw if data["operation"] == "withdraw" else simulation.retain
        return mutate(data, lambda identity: method(identity, data["resource"], data["ticket_id"], data["action_id"]))

    @app.get("/candidate/v1/shared/requests/status")
    def request_status():
        key = request.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{8,40}", key):
            return error("VALIDATION_ERROR", 400)
        result = audit.inspect(g.principal.identity, hashlib.sha256(key.encode()).hexdigest())
        return success(result) if result else error("NOT_FOUND", 404)

    def stored_plan(plan_id):
        if not re.fullmatch(r"shared-[0-9a-f]{32}", plan_id):
            return None
        return simulation.book.plan(plan_id)

    @app.get("/candidate/v1/shared/plans/<plan_id>")
    def plan_view(plan_id):
        stored = stored_plan(plan_id)
        if stored is None:
            return error("NOT_FOUND", 404)
        plan = stored["plan"]
        if g.principal.role != "recovery" and not any(c["record"]["seat"] in g.principal.seats for c in plan["claims"]):
            return error("FORBIDDEN", 403)
        return success({"state": stored["state"], "plan_id": plan_id, "resource": plan["resource"], "claims_count": len(plan["claims"])})

    def recover(plan_id, action):
        if g.principal.role != "recovery":
            return error("FORBIDDEN", 403)
        data = body("recovery")
        stored = stored_plan(plan_id)
        if stored is None:
            return error("NOT_FOUND", 404)
        plan = stored["plan"]
        if action == "cancel":
            return mutate(data, lambda identity: simulation.cancel_plan(plan_id, **data),
                          related_request_id=stored["request_id"], plan_id=plan_id)
        owner = next(c for c in plan["claims"] if c["claim_id"] == plan["trigger_owner_id"])
        return mutate(data, lambda identity: simulation.repair_records(stored["request_id"], plan["resource"],
            owner["ticket_id"], owner["action_id"], **data), related_request_id=stored["request_id"], plan_id=plan_id)

    def journal_review(journal_id):
        row = audit.journal(journal_id)
        if row is None:
            return None
        reference = row["context"].get("related_request_id")
        related = simulation.gate.inspect(reference) if reference else None
        plan = simulation.book.plan_for_request(reference) if reference else None
        ready = row["state"] == "pending" and related is not None and related["state"] == "done" and (
            plan is None or plan["state"] in ("completed", "cancelled"))
        summary = {"state": "review_ready" if ready else "review_held", "plan_id": plan["plan"]["plan_id"] if plan else row["context"].get("plan_id"),
            "journal_id": journal_id, "revision": row["revision"], "related_state": related["state"] if related else "not_seen",
            "plan_state": plan["state"] if plan else "none", "resolution_allowed": ready}
        summary["review_hash"] = hashlib.sha256(json.dumps([summary, related, row["context"]], sort_keys=True).encode()).hexdigest()
        return summary

    @app.get("/candidate/v1/shared/journals/<journal_id>")
    def review_journal(journal_id):
        if g.principal.role != "recovery":
            return error("FORBIDDEN", 403)
        review = journal_review(journal_id)
        return success(review) if review else error("NOT_FOUND", 404)

    @app.post("/candidate/v1/shared/journals/<journal_id>/resolve")
    def resolve_journal(journal_id):
        if g.principal.role != "recovery":
            return error("FORBIDDEN", 403)
        data = body("resolve")
        key = request.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{8,40}", key):
            return error("VALIDATION_ERROR", 400)
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        fingerprint = hashlib.sha256(json.dumps([journal_id, data], sort_keys=True).encode()).hexdigest()
        seen, cached = audit.resolution_replay(g.principal.identity, key_hash, fingerprint)
        if seen == "cached":
            return cached, 200
        if seen == "conflict":
            return error("IDEMPOTENCY_CONFLICT", 409)
        review = journal_review(journal_id)
        if review is None:
            return error("NOT_FOUND", 404)
        if review["revision"] != data["expected_revision"] or review["review_hash"] != data["review_hash"]:
            return error("STALE_REVIEW", 409)
        if not review["resolution_allowed"]:
            return error("PRECONDITION_FAILED", 409)
        response, _ = success({"state": "journal_resolved", "plan_id": review["plan_id"],
            "journal_id": journal_id, "revision": review["revision"] + 1})
        state, result = audit.resolve(journal_id, review["revision"], g.principal.identity, key_hash, fingerprint,
                                      data["evidence_ref"], response)
        if state == "conflict":
            return error("IDEMPOTENCY_CONFLICT", 409)
        if state == "stale":
            return error("STALE_REVIEW", 409)
        return result, 200

    @app.post("/candidate/v1/shared/plans/<plan_id>/cancel")
    def cancel(plan_id):
        return recover(plan_id, "cancel")

    @app.post("/candidate/v1/shared/plans/<plan_id>/repair")
    def repair(plan_id):
        return recover(plan_id, "repair")

    return app
