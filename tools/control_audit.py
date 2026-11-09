"""Local candidate journal: no credentials or raw request/claim payloads."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import uuid


class ControlAudit:
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
                    CREATE TABLE requests(principal TEXT, key_hash TEXT, fingerprint TEXT NOT NULL,
                        state TEXT NOT NULL, status INTEGER, response TEXT,
                        journal_id TEXT NOT NULL UNIQUE, context TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY(principal,key_hash));
                    CREATE TABLE events(id INTEGER PRIMARY KEY, principal TEXT, endpoint TEXT,
                        status INTEGER NOT NULL, code TEXT NOT NULL, at TEXT DEFAULT CURRENT_TIMESTAMP);
                    CREATE TABLE resolutions(operator TEXT, key_hash TEXT, fingerprint TEXT NOT NULL,
                        journal_id TEXT NOT NULL, evidence_ref TEXT NOT NULL, response TEXT NOT NULL,
                        PRIMARY KEY(operator,key_hash));
                    PRAGMA user_version=2;
                    COMMIT;
                """)
            elif conn.execute("PRAGMA user_version").fetchone()[0] != 2:
                raise ValueError("existing candidate audit database required")

    def connect(self):
        conn = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def begin(self, principal, key_hash, fingerprint, context=None):
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM resolutions WHERE operator=? AND key_hash=?", (principal, key_hash)).fetchone():
                return "conflict", None
            row = conn.execute("SELECT * FROM requests WHERE principal=? AND key_hash=?", (principal, key_hash)).fetchone()
            if row:
                if row["fingerprint"] != fingerprint:
                    return "conflict", None
                if row["state"] not in ("done", "resolved"):
                    return "pending", None
                return "cached", (row["status"], json.loads(row["response"]))
            conn.execute("INSERT INTO requests(principal,key_hash,fingerprint,state,status,response,journal_id,context) "
                         "VALUES(?,?,?,'pending',NULL,NULL,?,?)", (principal, key_hash, fingerprint,
                         "journal-" + uuid.uuid4().hex, json.dumps(context or {}, sort_keys=True)))
            return "new", None

    def finish(self, principal, key_hash, status, response):
        with closing(self.connect()) as conn, conn:
            changed = conn.execute("UPDATE requests SET state='done',status=?,response=?,revision=revision+1 WHERE principal=? AND key_hash=? AND state='pending'",
                                   (status, json.dumps(response, sort_keys=True), principal, key_hash))
            if changed.rowcount != 1:
                raise RuntimeError("API journal pending row is no longer owned")

    def event(self, principal, endpoint, status, code):
        with closing(self.connect()) as conn, conn:
            conn.execute("INSERT INTO events(principal,endpoint,status,code) VALUES(?,?,?,?)", (principal, endpoint, status, code))

    def inspect(self, principal, key_hash):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT state,status,response,journal_id,revision FROM requests WHERE principal=? AND key_hash=?", (principal, key_hash)).fetchone()
            if row is None:
                return None
            data = json.loads(row["response"]) if row["response"] else {}
            result = {"state": {"done": "journal_done", "resolved": "journal_resolved"}.get(row["state"], "journal_pending"),
                      "plan_id": data.get("result", {}).get("plan_id"), "journal_id": row["journal_id"], "revision": row["revision"]}
            if row["status"] is not None:
                result["operation_status"] = row["status"]
            return result

    def journal(self, journal_id):
        """Server-side metadata only. Never expose this raw row as an API response."""
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT journal_id,state,context,revision FROM requests WHERE journal_id=?", (journal_id,)).fetchone()
            return {**dict(row), "context": json.loads(row["context"])} if row else None

    def resolution_replay(self, operator, key_hash, fingerprint):
        with closing(self.connect()) as conn:
            if conn.execute("SELECT 1 FROM requests WHERE principal=? AND key_hash=?", (operator, key_hash)).fetchone():
                return "conflict", None
            row = conn.execute("SELECT fingerprint,response FROM resolutions WHERE operator=? AND key_hash=?", (operator, key_hash)).fetchone()
            if row is None:
                return "new", None
            return ("cached", json.loads(row["response"])) if row["fingerprint"] == fingerprint else ("conflict", None)

    def resolve(self, journal_id, revision, operator, key_hash, fingerprint, evidence_ref, response):
        """CAS + consumed original key + resolution audit in one transaction. No dispatch."""
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM requests WHERE principal=? AND key_hash=?", (operator, key_hash)).fetchone():
                return "conflict", None
            seen = conn.execute("SELECT fingerprint,response FROM resolutions WHERE operator=? AND key_hash=?", (operator, key_hash)).fetchone()
            if seen:
                return ("cached", json.loads(seen["response"])) if seen["fingerprint"] == fingerprint else ("conflict", None)
            retired = {"ok": False, "synthetic_only": True, "allow_target_call": False, "error": {"code": "OPERATOR_RESOLVED"}}
            changed = conn.execute("UPDATE requests SET state='resolved',status=409,response=?,revision=revision+1 "
                "WHERE journal_id=? AND state='pending' AND revision=?", (json.dumps(retired, sort_keys=True), journal_id, revision))
            if changed.rowcount != 1:
                return "stale", None
            conn.execute("INSERT INTO resolutions VALUES(?,?,?,?,?,?)", (operator, key_hash, fingerprint, journal_id,
                evidence_ref, json.dumps(response, sort_keys=True)))
            conn.execute("INSERT INTO events(principal,endpoint,status,code) VALUES(?,'operator_journal_resolution',200,'journal_resolved')", (operator,))
            return "resolved", response
