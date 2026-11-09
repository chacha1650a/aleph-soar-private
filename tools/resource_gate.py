"""Durable single-host resource reservations for offline integration trials.

All cooperating apply/release callers must share ONE local SQLite file.
No network, target calls, TTL stealing, distributed lock or execution permission.
"""
from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid


class Conflict(ValueError):
    """Request ID reused for a different resource, operation or payload."""


class StalePermit(ValueError):
    """Reservation is no longer owned by this permit."""


@dataclass(frozen=True)
class Permit:
    request_id: str
    token: str
    resource_key: str


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text(value, limit=300):
    return isinstance(value, str) and 1 <= len(value) <= limit and not re.search(r"[\x00-\x1f\x7f]", value)


def _resource_key(resource):
    if (not isinstance(resource, dict) or set(resource) != {"asset_id", "via", "action", "target"}
            or not all(_text(x) for x in resource.values())
            or resource["via"] not in ("portal", "pfsense", "wazuh-ar", "manual")
            or not re.fullmatch(r"[a-z][a-z_]{1,31}", resource["action"])):
        raise ValueError("exact four-field applied-action resource is required")
    return hashlib.sha256(_json(resource).encode("utf-8")).hexdigest()


class ResourceGate:
    def __init__(self, path, *, create=False):
        if str(path).startswith(("\\\\", "//")) or str(path) == ":memory:":
            raise ValueError("a persistent local disk path is required")
        self.path = Path(path).resolve()
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("xb"):
                pass
        with closing(self._connect()) as conn:
            if not create:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if conn.execute("PRAGMA user_version").fetchone()[0] != 1 or not {"requests", "reservations"} <= tables:
                    raise ValueError("existing reservation database is not initialized or has a different schema")
                return
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                    resource_key TEXT NOT NULL, token TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('pending', 'done')),
                    result TEXT, evidence_ref TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS reservations (
                    resource_key TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE REFERENCES requests(request_id),
                    token TEXT NOT NULL
                );
                PRAGMA user_version=1;
                COMMIT;
            """)

    def _connect(self):
        conn = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def reserve(self, resource, request_id, operation, payload):
        if not _text(request_id, 100) or operation not in ("apply", "release") or not isinstance(payload, dict):
            raise ValueError("request_id, apply/release operation and object payload are required")
        resource_key = _resource_key(resource)
        fingerprint = hashlib.sha256(_json([resource, operation, payload]).encode("utf-8")).hexdigest()
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            seen = conn.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if seen:
                if seen["fingerprint"] != fingerprint:
                    raise Conflict("request_id was used with different content")
                if seen["state"] == "done":
                    return {"state": "replayed", "result": seen["result"], "evidence_ref": seen["evidence_ref"]}
                return {"state": "busy", "reason": "same_request_pending"}
            if conn.execute("SELECT 1 FROM reservations WHERE resource_key=?", (resource_key,)).fetchone():
                return {"state": "busy", "reason": "resource_pending"}
            token = uuid.uuid4().hex
            conn.execute("INSERT INTO requests(request_id,fingerprint,resource_key,token,state) VALUES(?,?,?,?,'pending')",
                         (request_id, fingerprint, resource_key, token))
            conn.execute("INSERT INTO reservations VALUES(?,?,?)", (resource_key, request_id, token))
            return {"state": "reserved", "permit": Permit(request_id, token, resource_key)}

    def finish(self, permit, result, evidence_ref):
        """Use only after known no-call, or target + ticket record reconciliation.

        Exceptions/timeouts after a possible side effect must leave the reservation pending.
        """
        if result not in ("not_called", "recorded") or not isinstance(permit, Permit):
            raise ValueError("known not_called/recorded outcome and Permit required")
        self._finish(permit, result, evidence_ref)

    def _finish(self, permit, result, evidence_ref):
        if not _text(evidence_ref, 500):
            raise ValueError("sanitized evidence reference required")
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            held = conn.execute("SELECT * FROM reservations WHERE resource_key=? AND request_id=? AND token=?",
                                (permit.resource_key, permit.request_id, permit.token)).fetchone()
            if held is None:
                raise StalePermit("reservation no longer owned")
            updated = conn.execute("UPDATE requests SET state='done', result=?, evidence_ref=?, finished_at=CURRENT_TIMESTAMP "
                                   "WHERE request_id=? AND state='pending'", (result, evidence_ref, permit.request_id))
            if updated.rowcount != 1:
                raise StalePermit("pending request state no longer matches reservation")
            conn.execute("DELETE FROM reservations WHERE resource_key=? AND token=?", (permit.resource_key, permit.token))

    def inspect(self, request_id):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT request_id,state,result,evidence_ref,created_at,finished_at FROM requests "
                               "WHERE request_id=?", (request_id,)).fetchone()
            return dict(row) if row else None

    def reconcile(self, request_id, *, executor_stopped, target_checked, record_checked, evidence_ref):
        """Operator declarations, not independently verified evidence. No force/TTL path.

        Never use while an old executor may still be running, even after a timeout.
        """
        if not all(x is True for x in (executor_stopped, target_checked, record_checked)):
            raise ValueError("executor stop, target state and ticket record checks must all be confirmed")
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM requests WHERE request_id=? AND state='pending'", (request_id,)).fetchone()
        if row is None:
            raise StalePermit("no pending request to reconcile")
        self._finish(Permit(request_id, row["token"], row["resource_key"]), "reconciled", evidence_ref)
