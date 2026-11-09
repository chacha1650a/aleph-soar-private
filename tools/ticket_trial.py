"""Reserved read-only home trial: reserve -> fresh GET -> JS -> not_called.

There is deliberately no target callback, POST, execution permit or enable flag.
"""
from copy import deepcopy
import hashlib
import json
import re

from tools.check_ticket_guard import evaluate, WORKFLOW
from tools.resource_gate import Conflict, ResourceGate
from tools.ticket_http import TicketHTTP


def _digest():
    return hashlib.sha256(WORKFLOW.read_bytes()).hexdigest()


class TicketTrial:
    def __init__(self, gate, transport):
        if type(gate) is not ResourceGate or type(transport) is not TicketHTTP:
            raise ValueError("ResourceGate and loopback TicketHTTP are required")
        self.gate, self.transport = gate, transport

    def run(self, request_id, mode, expected, evidence_ref):
        def result(state, reason, reservation, decision=None):
            return {"state": state, "reason": reason, "reservation_state": reservation,
                    "decision": decision, "allow_target_call": False, "automatic_retry": False}

        if mode not in ("apply", "release") or not isinstance(expected, dict):
            raise ValueError("apply/release and expected object required")
        if not isinstance(evidence_ref, str) or not 1 <= len(evidence_ref) <= 500 or re.search(r"[\x00-\x1f\x7f]", evidence_ref):
            raise ValueError("sanitized evidence reference required")
        expected = deepcopy(expected)
        workflow_hash = _digest()
        payload = {"trial_version": 1, "expected": expected, "evidence_ref": evidence_ref,
                   "workflow_sha256": workflow_hash, "port": self.transport.port, "timeout": self.transport.timeout}
        # Validate JSON before reserving. No credentials or raw response in the payload.
        json.dumps(payload, allow_nan=False)
        try:
            acquired = self.gate.reserve(expected.get("resource"), request_id, mode, payload)
        except Conflict:
            return result("conflict", "trial_id_content_conflict", "not_acquired")
        except Exception:
            return result("failed", "reservation_failed", "unknown")
        if acquired["state"] == "busy":
            return result("busy", acquired["reason"], "not_acquired")
        if acquired["state"] == "replayed":
            # Do NOT replay an old candidate as if it were a current observation.
            return result("replayed", "prior_trial_completed_no_fresh_query", "not_acquired")

        permit = acquired["permit"]
        state, reason, decision = "completed", "read_only_trial_completed", None
        try:
            envelope = self.transport.apply(expected) if mode == "apply" else self.transport.release(expected)
            answers = evaluate([envelope])
            if _digest() != workflow_hash:
                raise ValueError("workflow changed during trial")
            if (not isinstance(answers, list) or len(answers) != 1 or not isinstance(answers[0], dict)
                    or answers[0].get("allow_target_call") is not False or answers[0].get("automatic_retry") is not False
                    or answers[0].get("decision") not in ("hold", "skip_active", "apply_candidate", "release_candidate")):
                raise ValueError("unexpected decision result")
            decision = answers[0]
        except Exception:
            # Only GET and pure JS were reachable: even query/JS failures have no target side effect.
            state, reason, decision = "failed", "query_or_decision_failed", None
        # BaseException/process exit is not caught: its durable pending state needs reconciliation.
        try:
            self.gate.finish(permit, "not_called", evidence_ref)
        except Exception:
            # Do not retry the cleanup or claim that the lock was released.
            return result("failed", "reservation_cleanup_unconfirmed", "unknown")
        return result(state, reason, "released", decision)
