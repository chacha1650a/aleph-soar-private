"""Candidate withdrawal policy -> ONE SQLite fake release -> C test-client records.

Not an operational claim API. No network target, deployment or permission changes.
"""
from copy import deepcopy

from tools.resource_gate import ResourceGate, _resource_key
from tools.shared_claims import ClaimBook, claim_id
from tools.simulated_execution import CTestClient, SimulatedTarget


class SharedReleaseSimulation:
    def __init__(self, gate, book, target, tickets):
        if (type(gate) is not ResourceGate or type(book) is not ClaimBook
                or type(target) is not SimulatedTarget or not isinstance(tickets, CTestClient)):
            raise ValueError("local gate/book, exact fake target and in-process C test clients required")
        self.gate, self.book, self.target, self.tickets = gate, book, target, tickets

    @staticmethod
    def _out(state, plan_id=None):
        return {"state": state, "plan_id": plan_id, "synthetic_only": True, "allow_target_call": False}

    def snapshot(self, resource):
        envelope = self.tickets.observe("release", {"resource": resource})
        data = envelope["observation"]["body"]
        if envelope["observation"]["status"] != 200 or data.get("ok") is not True or data.get("resource") != resource:
            raise ValueError("complete scoped C claim snapshot required")
        entries = []
        for ref in data["tickets"]:
            if ref["status"] not in ("responding", "verified"):
                raise ValueError("unexpected/closed active ticket needs review")
            ticket = self.tickets.ticket(ref["ticket_id"])
            if ticket["asset_id"] != resource["asset_id"] or ticket["seat"] != ref["seat"]:
                raise ValueError("ticket scope mismatch")
            for active in ref["active_actions"]:
                if not all(active[k] == resource[k] for k in ("via", "action", "target")):
                    raise ValueError("mixed resource snapshot")
                applied = [a for a in ticket["actions"] if not a["duplicate"] and a["result"] in ("applied", "already_applied")
                           and a["bot"] == active["bot"] and all(a[k] == resource[k] for k in ("via", "action", "target"))]
                if not applied:
                    raise ValueError("active action detail missing")
                action_id = applied[-1]["action_id"]
                record = {k: ticket[k] for k in ("seat", "case_id", "group_key", "title", "asset_id", "event_ids")}
                for k in ("src_ip", "username", "reason", "first_attack_at", "condition_met_at", "detected_at", "received_at"):
                    if ticket.get(k) is not None:
                        record[k] = ticket[k]
                record.update(stage="released", action={"bot": active["bot"], "via": resource["via"], "target": resource["target"],
                    "action": "unblock", "result": "released", "applied_verified": True, "effect_verified": None,
                    "requested_at": None, "finished_at": None, "effect_verified_at": None,
                    "n8n_execution_id": "synthetic-shared-release", "detail": "synthetic shared physical release"})
                entries.append({"claim_id": claim_id(ticket["ticket_id"], action_id), "ticket_id": ticket["ticket_id"],
                                "action_id": action_id, "record": record})
        if len({x["claim_id"] for x in entries}) != len(entries):
            raise ValueError("duplicate claim snapshot")
        return deepcopy(entries)

    @staticmethod
    def _payload(ticket_id, action_id):
        return {"shared_policy_version": 1, "owner_id": claim_id(ticket_id, action_id)}

    def retain(self, request_id, resource, ticket_id, action_id):
        resource = deepcopy(resource)
        acquired = self.gate.reserve(resource, request_id, "apply", self._payload(ticket_id, action_id))
        if acquired["state"] != "reserved":
            return self._out(acquired["state"])
        permit = acquired["permit"]
        try:
            if not self.target.active(resource):
                raise ValueError("fake block no longer active")
            state = self.book.retain(resource, request_id, claim_id(ticket_id, action_id), self.snapshot(resource))["state"]
        except Exception:
            state = "held"
        try:
            self.gate.finish(permit, "not_called", "synthetic/explicit-retain-intent")
            return self._out(state)
        except Exception:
            return self._out("cleanup_unconfirmed")

    def withdraw(self, request_id, resource, ticket_id, action_id, *, fault=None):
        if fault not in (None, "before_target", "after_target", "after_first_record", "after_book_complete"):
            raise ValueError("unknown synthetic failure point")
        resource = deepcopy(resource)
        acquired = self.gate.reserve(resource, request_id, "release", self._payload(ticket_id, action_id))
        if acquired["state"] != "reserved":
            return self._out(acquired["state"])
        permit = acquired["permit"]
        try:
            if not self.target.active(resource):
                raise ValueError("fake block absent before withdrawal; reconcile first")
            outcome = self.book.withdraw(resource, request_id, claim_id(ticket_id, action_id), self.snapshot(resource))
        except Exception:
            # No fake target call happened; uncertain logical-book commit is deliberately not erased.
            try:
                self.gate.finish(permit, "not_called", "synthetic/shared-pre-target-hold")
            except Exception:
                return self._out("cleanup_unconfirmed")
            return self._out("held")
        if outcome["state"] != "plan_prepared":
            try:
                self.gate.finish(permit, "not_called", "synthetic/logical-withdrawal-only")
                return self._out(outcome["state"])
            except Exception:
                return self._out("cleanup_unconfirmed")
        plan_id = outcome["plan_id"]
        try:
            plan = self.book.plan(plan_id)["plan"]
            if fault == "before_target":
                raise RuntimeError("synthetic interruption before fake target")
            receipt = self.target.perform(plan_id, resource, "release")
            if fault == "after_target":
                raise RuntimeError("synthetic release response loss")
            self._record_plan(plan, receipt, fault=fault)
            self.book.complete(plan_id)
            if fault == "after_book_complete":
                raise RuntimeError("synthetic interruption before gate completion")
            self.gate.finish(permit, "recorded", "synthetic/shared-target-and-all-records-verified")
            return self._out("released", plan_id)
        except Exception:
            return self._out("pending", plan_id)

    def cancel_plan(self, plan_id, *, executor_stopped=False, evidence_ref=None):
        if executor_stopped is not True or not isinstance(evidence_ref, str) or not evidence_ref.startswith("synthetic/"):
            raise ValueError("stopped executor and synthetic evidence reference required")
        stored = self.book.plan(plan_id)
        if stored is None or stored["state"] == "completed":
            return self._out("held", plan_id)
        plan, request_id = stored["plan"], stored["request_id"]
        pending = self.gate.inspect(request_id)
        if stored["state"] == "cancelled" and pending and pending["state"] == "done":
            return self._out("cancelled", plan_id)
        if pending is None or pending["state"] != "pending":
            return self._out("held", plan_id)
        # Only this exact SQLite fake target makes absent receipt an atomic no-effect proof.
        if self.target.receipt(plan_id) is not None or not self.target.active(plan["resource"]):
            return self._out("held", plan_id)
        try:
            current = {c["claim_id"] for c in self.snapshot(plan["resource"])}
            if current != {c["claim_id"] for c in plan["claims"]}:
                return self._out("held", plan_id)
            self.book.cancel(plan_id)
            self.gate.reconcile(request_id, executor_stopped=True, target_checked=True, record_checked=True,
                                evidence_ref=evidence_ref)
            return self._out("cancelled", plan_id)
        except Exception:
            return self._out("cleanup_unconfirmed", plan_id)

    def _record_plan(self, plan, receipt, *, fault=None):
        resource = plan["resource"]
        if receipt["resource_key"] != _resource_key(resource) or receipt["active"] != 0 or self.target.active(resource):
            raise ValueError("fake release receipt/current state mismatch")
        for index, claim in enumerate(plan["claims"]):
            body = deepcopy(claim["record"])
            body["action"].update(requested_at=plan["requested_at"], finished_at=receipt["at"])
            key = plan["plan_id"] + "-" + str(index)
            ack = self.tickets.record(body, key)
            if ack["ticket_id"] != claim["ticket_id"]:
                raise ValueError("claim ticket record mismatch")
            ticket = self.tickets.ticket(claim["ticket_id"])
            if (any(ticket[k] != body[k] for k in ("seat", "asset_id", "group_key"))
                    or not set(body["event_ids"]).issubset(ticket["event_ids"])):
                raise ValueError("claim ticket scope changed")
            rows = [a for a in ticket["actions"] if a["action_id"] == key and not a["duplicate"]]
            if len(rows) != 1 or not all(rows[0][k] == body["action"][k] for k in ("bot", "via", "target", "action", "result")):
                raise ValueError("claim release readback failed")
            if fault == "after_first_record" and index == 0:
                raise RuntimeError("synthetic interruption between owner records")
        if self.snapshot(resource):
            raise ValueError("active claims remain after fake release")

    def repair_records(self, request_id, resource, ticket_id, action_id, *, executor_stopped=False,
                       evidence_ref="synthetic/shared-record-only-repair"):
        if executor_stopped is not True:
            raise ValueError("previous executor must be stopped")
        if not isinstance(evidence_ref, str) or not evidence_ref.startswith("synthetic/"):
            raise ValueError("synthetic evidence reference required")
        resource = deepcopy(resource)
        prior = self.gate.inspect(request_id)
        if prior is None or prior["state"] != "pending":
            return self._out("held")
        acquired = self.gate.reserve(resource, request_id, "release", self._payload(ticket_id, action_id))
        if acquired != {"state": "busy", "reason": "same_request_pending"}:
            return self._out("held")
        stored = self.book.plan_for_request(request_id)
        if stored is None:
            return self._out("held")
        plan = stored["plan"]
        receipt = self.target.receipt(plan["plan_id"])
        if receipt is None:
            return self._out("held", plan["plan_id"])
        try:
            self._record_plan(plan, receipt)
            self.book.complete(plan["plan_id"])
            self.gate.reconcile(request_id, executor_stopped=True, target_checked=True, record_checked=True,
                                evidence_ref=evidence_ref)
            return self._out("reconciled", plan["plan_id"])
        except Exception:
            return self._out("pending", plan["plan_id"])
