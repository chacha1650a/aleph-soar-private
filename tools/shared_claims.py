"""Candidate shared-ownership policy for synthetic trials, not a deployed C API."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

from tools.resource_gate import Conflict, _resource_key


def claim_id(ticket_id, action_id):
    return hashlib.sha256(json.dumps([ticket_id, action_id]).encode()).hexdigest()


def _observed(resource, owner_id, snapshot):
    if resource["action"] != "block" or not isinstance(snapshot, list) or not snapshot:
        raise ValueError("complete block-claim snapshot required")
    observed = {}
    for entry in deepcopy(snapshot):
        record, identity = entry["record"], entry["claim_id"]
        action = record["action"]
        if (identity in observed or identity != claim_id(entry["ticket_id"], entry["action_id"])
                or record["asset_id"] != resource["asset_id"] or record["stage"] != "released"
                or action["via"] != resource["via"] or action["target"] != resource["target"] or action["action"] != "unblock"):
            raise ValueError("claim scope/identity mismatch")
        observed[identity] = entry
    if owner_id not in observed:
        raise ValueError("exact active claim owner required")
    return observed


class ClaimBook:
    """All methods must be inside the SAME resource gate as apply/release callers."""
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
                    CREATE TABLE claims(resource_key TEXT, claim_id TEXT, payload TEXT NOT NULL,
                        state TEXT NOT NULL CHECK(state IN ('active','withdrawn','released')),
                        PRIMARY KEY(resource_key,claim_id));
                    CREATE TABLE intents(request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL);
                    CREATE TABLE plans(plan_id TEXT PRIMARY KEY, resource_key TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE,
                        payload TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('prepared','completed','cancelled')));
                    CREATE UNIQUE INDEX one_prepared ON plans(resource_key) WHERE state='prepared';
                    PRAGMA user_version=2;
                    COMMIT;
                """)
            elif conn.execute("PRAGMA user_version").fetchone()[0] != 2:
                raise ValueError("existing synthetic claim database required")

    def connect(self):
        conn = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def withdraw(self, resource, request_id, owner_id, snapshot):
        resource = deepcopy(resource)
        key = _resource_key(resource)
        if resource["action"] != "block":
            raise ValueError("candidate policy covers block/unblock only")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{8,40}", request_id):
            raise ValueError("synthetic intent ID required")
        observed = _observed(resource, owner_id, snapshot)
        fingerprint = hashlib.sha256(json.dumps([key, owner_id, "withdraw"]).encode()).hexdigest()
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            seen = conn.execute("SELECT fingerprint FROM intents WHERE request_id=?", (request_id,)).fetchone()
            if seen:
                if seen[0] != fingerprint:
                    raise Conflict("withdrawal ID reused for another claim")
                return {"state": "replayed", "plan_id": None}
            if conn.execute("SELECT 1 FROM plans WHERE resource_key=? AND state='prepared'", (key,)).fetchone():
                raise ValueError("prepared release requires reconciliation")
            existing = conn.execute("SELECT * FROM claims WHERE resource_key=?", (key,)).fetchall()
            if any(row["state"] != "released" and row["claim_id"] not in observed for row in existing):
                raise ValueError("known claim missing from snapshot; hold")
            if any(row["state"] == "released" and row["claim_id"] in observed for row in existing):
                raise ValueError("released claim reappeared; hold")
            for identity, entry in observed.items():
                conn.execute("INSERT OR IGNORE INTO claims VALUES(?,?,?,'active')",
                             (key, identity, json.dumps(entry, sort_keys=True, allow_nan=False)))
            conn.execute("UPDATE claims SET state='withdrawn' WHERE resource_key=? AND claim_id=?", (key, owner_id))
            conn.execute("INSERT INTO intents VALUES(?,?)", (request_id, fingerprint))
            remaining = conn.execute("SELECT COUNT(*) FROM claims WHERE resource_key=? AND state='active'", (key,)).fetchone()[0]
            if remaining:
                return {"state": "withdrawn_waiting", "remaining_owners": remaining}
            rows = conn.execute("SELECT * FROM claims WHERE resource_key=? AND state='withdrawn' ORDER BY claim_id", (key,)).fetchall()
            plan = {"plan_id": "shared-" + uuid.uuid4().hex, "resource": deepcopy(resource),
                    "trigger_owner_id": owner_id,
                    "requested_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                    "claims": [json.loads(row["payload"]) for row in rows]}
            conn.execute("INSERT INTO plans VALUES(?,?,?,?,'prepared')", (plan["plan_id"], key, request_id, json.dumps(plan, sort_keys=True)))
            return {"state": "plan_prepared", "plan_id": plan["plan_id"]}

    def retain(self, resource, request_id, owner_id, snapshot):
        """Explicitly cancel a prior withdrawal while no physical release is prepared."""
        resource = deepcopy(resource)
        key = _resource_key(resource)
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{8,40}", request_id):
            raise ValueError("synthetic retain intent ID required")
        observed = _observed(resource, owner_id, snapshot)
        fingerprint = hashlib.sha256(json.dumps([key, owner_id, "retain"]).encode()).hexdigest()
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            seen = conn.execute("SELECT fingerprint FROM intents WHERE request_id=?", (request_id,)).fetchone()
            if seen:
                if seen[0] != fingerprint:
                    raise Conflict("intent ID reused for another operation")
                return {"state": "replayed", "plan_id": None}
            if conn.execute("SELECT 1 FROM plans WHERE resource_key=? AND state='prepared'", (key,)).fetchone():
                raise ValueError("physical release already prepared; reconcile first")
            row = conn.execute("SELECT * FROM claims WHERE resource_key=? AND claim_id=?", (key, owner_id)).fetchone()
            if row is None or row["state"] == "released":
                raise ValueError("existing unreleased claim required")
            known = {r[0] for r in conn.execute("SELECT claim_id FROM claims WHERE resource_key=? AND state!='released'", (key,))}
            if not known.issubset(observed):
                raise ValueError("known claim missing; hold")
            conn.execute("UPDATE claims SET state='active' WHERE resource_key=? AND claim_id=?", (key, owner_id))
            conn.execute("INSERT INTO intents VALUES(?,?)", (request_id, fingerprint))
            return {"state": "retained"}

    def plan(self, plan_id):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT payload,state,request_id FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
            return {"plan": json.loads(row["payload"]), "state": row["state"], "request_id": row["request_id"]} if row else None

    def plan_for_request(self, request_id):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT payload,state FROM plans WHERE request_id=?", (request_id,)).fetchone()
            return {"plan": json.loads(row["payload"]), "state": row["state"]} if row else None

    def complete(self, plan_id):
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
            if row is None:
                raise ValueError("release plan required")
            if row["state"] == "completed":
                return
            if row["state"] != "prepared":
                raise ValueError("cancelled plan cannot be completed")
            for entry in json.loads(row["payload"])["claims"]:
                conn.execute("UPDATE claims SET state='released' WHERE resource_key=? AND claim_id=?",
                             (row["resource_key"], entry["claim_id"]))
            conn.execute("UPDATE plans SET state='completed' WHERE plan_id=?", (plan_id,))

    def cancel(self, plan_id):
        """Trusted coordinator only, AFTER receipt absence/current-state checks."""
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
            if row is None or row["state"] == "completed":
                raise ValueError("uncompleted plan required")
            if row["state"] == "cancelled":
                return
            for entry in json.loads(row["payload"])["claims"]:
                conn.execute("UPDATE claims SET state='active' WHERE resource_key=? AND claim_id=? AND state='withdrawn'",
                             (row["resource_key"], entry["claim_id"]))
            conn.execute("UPDATE plans SET state='cancelled' WHERE plan_id=?", (plan_id,))
