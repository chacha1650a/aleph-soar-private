"""Synthetic target execution only: durable fake effects + C test-client records.

No sockets, real target adapters, enable flag or production execution permission.
"""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from tools.check_ticket_guard import evaluate
from tools.resource_gate import ResourceGate, Conflict, _resource_key


class SimulatedTarget:
    def __init__(self, path, *, create=False):
        self.path = Path(path).resolve()
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("xb"):
                pass
        with closing(self.connect()) as conn:
            if create:
                conn.executescript("""
                    BEGIN;
                    CREATE TABLE resources(resource_key TEXT PRIMARY KEY, active INTEGER NOT NULL);
                    CREATE TABLE receipts(request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                        resource_key TEXT NOT NULL, active INTEGER NOT NULL, changed INTEGER NOT NULL, at TEXT NOT NULL);
                    PRAGMA user_version=1;
                    COMMIT;
                """)
            elif conn.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("existing synthetic target database required")

    def connect(self):
        conn = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def perform(self, request_id, resource, mode):
        if mode not in ("apply", "release"):
            raise ValueError("apply/release required")
        key = _resource_key(resource)
        fingerprint = hashlib.sha256(json.dumps([key, mode]).encode()).hexdigest()
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT * FROM receipts WHERE request_id=?", (request_id,)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise Conflict("synthetic target request reused with other content")
                return dict(old)
            previous = conn.execute("SELECT active FROM resources WHERE resource_key=?", (key,)).fetchone()
            active = int(mode == "apply")
            changed = int((previous[0] if previous else 0) != active)
            at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            conn.execute("INSERT INTO resources VALUES(?,?) ON CONFLICT(resource_key) DO UPDATE SET active=excluded.active", (key, active))
            conn.execute("INSERT INTO receipts VALUES(?,?,?,?,?,?)", (request_id, fingerprint, key, active, changed, at))
            return dict(conn.execute("SELECT * FROM receipts WHERE request_id=?", (request_id,)).fetchone())

    def receipt(self, request_id):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM receipts WHERE request_id=?", (request_id,)).fetchone()
            return dict(row) if row else None

    def active(self, resource):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT active FROM resources WHERE resource_key=?", (_resource_key(resource),)).fetchone()
            return bool(row[0]) if row else False


class CTestClient:
    """In-process C Flask test clients, never an HTTP/target transport."""
    def __init__(self, n8n_client, dashboard_client, key, validator=None):
        from flask.testing import FlaskClient
        if not isinstance(n8n_client, FlaskClient) or not isinstance(dashboard_client, FlaskClient):
            raise ValueError("local Flask test clients required")
        self.n8n, self.dashboard, self.headers = n8n_client, dashboard_client, {"X-Response-Key": key}
        self.validator = validator

    def _json(self, response):
        data = response.get_json()
        if self.validator is not None:
            self.validator.validate(data)
        return data

    def observe(self, mode, expected):
        query = ({"seat": expected["seat"], "group_key": expected["group_key"]} if mode == "apply" else expected["resource"])
        response = self.n8n.get("/api/v1/tickets/" + ("open" if mode == "apply" else "active"),
                                query_string=query, headers=self.headers)
        return {"mode": mode, "expected": expected, "observation": {"status": response.status_code,
                "query": query, "body": self._json(response)}}

    def record(self, body, key):
        response = self.n8n.post("/api/v1/tickets/record", json=body,
                                 headers={**self.headers, "Idempotency-Key": key})
        data = self._json(response)
        if response.status_code not in (200, 201) or not isinstance(data, dict) or data.get("ok") is not True:
            raise ValueError("synthetic record not acknowledged")
        return data

    def ticket(self, ticket_id):
        response = self.dashboard.get(f"/api/v1/tickets/{ticket_id}")
        data = self._json(response)
        if response.status_code != 200 or not isinstance(data, dict) or data.get("ok") is not True:
            raise ValueError("synthetic ticket read unavailable")
        return data["ticket"]


class SimulatedExecution:
    def __init__(self, gate, target, tickets):
        if type(gate) is not ResourceGate or type(target) is not SimulatedTarget:
            raise ValueError("local gate and exact synthetic target required")
        self.gate, self.target, self.tickets = gate, target, tickets

    @staticmethod
    def _input(request_id, mode, body, resource):
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{8,40}", request_id):
            raise ValueError("synthetic request ID must be 8-40 ASCII ID characters")
        _resource_key(resource)
        if mode not in ("apply", "release") or resource["action"] != "block":
            raise ValueError("this simulator covers block/unblock only")
        action = body["action"]
        if (body["asset_id"] != resource["asset_id"] or action["via"] != resource["via"] or action["target"] != resource["target"]
                or action["action"] != ("block" if mode == "apply" else "unblock")
                or body["stage"] != ("applied" if mode == "apply" else "released")):
            raise ValueError("synthetic record/resource/mode mismatch")
        return {"mode": mode, "record_body": deepcopy(body), "simulation_version": 1}

    @staticmethod
    def _result(state, reason):
        return {"state": state, "reason": reason, "synthetic_only": True, "allow_target_call": False}

    def _not_called(self, permit, reason):
        try:
            self.gate.finish(permit, "not_called", "synthetic/" + reason)
            return self._result("not_called", reason)
        except Exception:
            return self._result("held", "reservation_cleanup_unconfirmed")

    def run(self, request_id, mode, body, resource, *, fault=None):
        if fault not in (None, "after_target", "after_record"):
            raise ValueError("unknown synthetic failure point")
        body, resource = deepcopy(body), deepcopy(resource)
        payload = self._input(request_id, mode, body, resource)
        acquired = self.gate.reserve(resource, request_id, mode, payload)
        if acquired["state"] != "reserved":
            return self._result(acquired["state"], "no_new_synthetic_call")
        permit = acquired["permit"]
        try:
            expected = {"seat": body["seat"], "group_key": body["group_key"], "bot": body["action"]["bot"], "resource": resource}
            if mode == "release":
                own = self.tickets.observe("apply", expected)["observation"]["body"]
                expected["owner_ticket_id"] = own.get("ticket_id") if isinstance(own, dict) else None
            decisions = evaluate([self.tickets.observe(mode, expected)])
            if len(decisions) != 1 or decisions[0].get("allow_target_call") is not False:
                raise ValueError("unexpected guard result")
            candidate = decisions[0].get("decision") == mode + "_candidate"
        except Exception:
            return self._not_called(permit, "pre_target_failure")
        if not candidate:
            return self._not_called(permit, "guard_did_not_select_candidate")
        # From this boundary onward, any failure may follow a committed fake effect.
        try:
            receipt = self.target.perform(request_id, resource, mode)
            if fault == "after_target":
                raise RuntimeError("synthetic response loss")
            self._record_and_verify(request_id, mode, body, resource, receipt)
            if fault == "after_record":
                raise RuntimeError("synthetic post-record interruption")
            self.gate.finish(permit, "recorded", "synthetic/target-and-ticket-verified")
            return self._result("recorded", "synthetic_target_and_record_verified")
        except Exception:
            return self._result("pending", "synthetic_effect_or_record_needs_reconciliation")

    def _record_and_verify(self, request_id, mode, body, resource, receipt):
        if receipt["resource_key"] != _resource_key(resource) or bool(receipt["active"]) != (mode == "apply"):
            raise ValueError("synthetic receipt scope mismatch")
        if self.target.active(resource) != (mode == "apply"):
            raise ValueError("synthetic current target state differs")
        record = deepcopy(body)
        record["action"].update(result=("applied" if receipt["changed"] else "already_applied") if mode == "apply" else "released",
                                applied_verified=True, effect_verified=None, effect_verified_at=None, finished_at=receipt["at"])
        first = self.tickets.record(record, request_id + "-record")
        if mode == "apply":
            effect = deepcopy(record)
            effect["stage"] = "effect"
            effect["action"].update(effect_verified=True, effect_verified_at=receipt["at"])
            ack = self.tickets.record(effect, request_id + "-effect")
            if ack["ticket_id"] != first["ticket_id"]:
                raise ValueError("synthetic effect ticket mismatch")
        ticket = self.tickets.ticket(first["ticket_id"])
        if (any(ticket[k] != body[k] for k in ("seat", "group_key", "asset_id"))
                or not set(body["event_ids"]).issubset(ticket["event_ids"])):
            raise ValueError("synthetic ticket scope mismatch")
        lines = [a for a in ticket["actions"] if a["action_id"] == request_id + "-record" and not a["duplicate"]]
        if len(lines) != 1 or not all(lines[0][k] == record["action"][k] for k in ("bot", "via", "target", "action", "result")):
            raise ValueError("synthetic record readback mismatch")
        if mode == "apply" and lines[0]["effect_verified"] is not True:
            raise ValueError("synthetic effect not persisted")
        if mode == "release":
            expected = {"seat": body["seat"], "group_key": body["group_key"]}
            actions = self.tickets.observe("apply", expected)["observation"]["body"]["applied_actions"]
            if any(a["bot"] == body["action"]["bot"] and all(a[k] == resource[k] for k in ("via", "action", "target")) for a in actions):
                raise ValueError("synthetic release still recorded active")

    def repair_records(self, request_id, mode, body, resource, *, executor_stopped=False):
        if executor_stopped is not True:
            raise ValueError("previous executor must be confirmed stopped")
        body, resource = deepcopy(body), deepcopy(resource)
        payload = self._input(request_id, mode, body, resource)
        old = self.gate.inspect(request_id)
        if old is None or old["state"] != "pending":
            return self._result("held", "original_pending_request_required")
        acquired = self.gate.reserve(resource, request_id, mode, payload)
        if acquired != {"state": "busy", "reason": "same_request_pending"}:
            return self._result("held", "original_pending_request_required")
        receipt = self.target.receipt(request_id)
        if receipt is None:
            return self._result("held", "no_synthetic_target_receipt")
        try:
            self._record_and_verify(request_id, mode, body, resource, receipt)
            self.gate.reconcile(request_id, executor_stopped=True, target_checked=True, record_checked=True,
                                evidence_ref="synthetic/record-only-repair")
            return self._result("reconciled", "no_synthetic_target_recall")
        except Exception:
            return self._result("pending", "record_repair_unconfirmed")
