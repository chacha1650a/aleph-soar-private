"""S1 with real Flask portal/C code and disposable SQLite, never live transport.

Run using the explicitly selected backend environment. The Node helper evaluates
committed Code snippets; HTTP bindings are adapted to in-process test clients.
This does not execute n8n, Graylog, Docker, SSH or any service network request.
"""
import argparse
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_s1_candidate import check, PACKET

S1 = "haedam-30-s1-main.json"
LOG = "haedam-10-result-log.json"
PORTAL = "haedam-12-portal-ip-block.json"
ATTACK, NORMAL = "203.0.113.22", "203.0.113.100"
PORTAL_KEY, TICKET_KEY = "synthetic-portal-key-not-live-1027", "synthetic-ticket-key-not-live-1027"
PASSWORD = "Synthetic-only-password-1027!"


def require(value, code):
    if not value:
        raise RuntimeError(code)


def evaluate(file, node, data, execution="home-s1-one", prior=None, raw=False):
    env = {k: v for k, v in os.environ.items() if k not in ("NODE_OPTIONS", "NODE_PATH")}
    node_bin = shutil.which("node")
    require(node_bin, "NODE_REQUIRED")
    step = {"file": file, "node": node, "input": data, "execution_id": execution, "prior": prior or {}}
    result = subprocess.run([node_bin, str(ROOT / "tests/helpers/n8n_code_runner.cjs")],
        input=json.dumps([step]), text=True, encoding="utf-8", capture_output=True, timeout=15, check=True, env=env)
    value = json.loads(result.stdout)[0]
    require(value["http_calls"] == 0, "CODE_HTTP_NOT_ALLOWED")
    if raw:
        return value
    require("error" not in value, "CODE_NODE_FAILED")
    return value["output"]


class Trial:
    def __init__(self, folder, portal_module, models, ticket_app, ticket_db):
        self.folder, self.models, self.ticket_db = folder, models, ticket_db
        portal_module.ROOT = folder / "portal-instance-root"
        # The app constructor creates instance_path before applying config, so
        # redirect its module root as well as all DB/log/static configuration.
        self.app = portal_module.create_app({"TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (folder / "portal.sqlite3").as_posix(),
            "EVENT_LOG_PATH": str(folder / "events.jsonl"), "FRONTEND_DIST": str(folder / "dist"),
            "GELF_ENABLED": False, "COOKIE_SECURE": False, "RESPONSE_API_KEY": PORTAL_KEY,
            "RESPONSE_ALLOWED_CIDRS": ["127.0.0.0/8"], "ASSET_ID": "haedam-portal"})
        from werkzeug.security import generate_password_hash
        with self.app.app_context():
            models.db.create_all()
            models.db.session.add(models.User(username="zz_s1", display_name="Synthetic", role="citizen",
                                              password_hash=generate_password_hash(PASSWORD)))
            models.db.session.commit()
        self.c_path = str(folder / "tickets.db")
        self.c = ticket_app.create_n8n_app(self.c_path, TICKET_KEY).test_client()
        self.portal_posts = 0

    def close(self):
        with self.app.app_context():
            self.models.db.session.remove()
            self.models.db.engine.dispose()

    def login(self, ip, password):
        client = self.app.test_client()
        csrf = client.get("/api/v1/auth/me", environ_overrides={"REMOTE_ADDR": ip}).get_json()["data"]["csrf_token"]
        return client.post("/api/v1/auth/login", json={"username": "zz_s1", "password": password},
            headers={"X-CSRF-Token": csrf}, environ_overrides={"REMOTE_ADDR": ip})

    def health(self, ip):
        return self.app.test_client().get("/api/v1/health", environ_overrides={"REMOTE_ADDR": ip})

    def events(self):
        return [json.loads(line) for line in (self.folder / "events.jsonl").read_text(encoding="utf-8").splitlines()]

    def start(self, fail_detected=False):
        for _ in range(9):
            require(self.login(ATTACK, "Synthetic-wrong-password").status_code == 401, "LOGIN_FAILURE_INPUT")
        failures = [e for e in self.events() if e["event_type"] == "auth.login_failed" and e["src_ip"] == ATTACK]
        require(len(failures) == 9 and len({e["event_id"] for e in failures}) == 9, "NINE_DISTINCT_LOCAL_EVENTS")
        require(self.login(NORMAL, PASSWORD).status_code == 200, "NORMAL_BASELINE")
        data = {"event_id": "synthetic-graylog-decision-one", "asset_id": "haedam-portal", "src_ip": ATTACK,
                "username": "zz_s1", "condition_met_at": failures[-1]["timestamp"], "detected_at": None}
        self.v = evaluate(S1, "입력 검증·설정", {"body": data})
        self.v["ctx"]["cfg"]["dry_run"] = False  # In-memory route to test clients only.
        self.v["ctx"]["cfg"]["store_real"] = True  # Explicit isolated C store, independent of device mode.
        decision = evaluate(S1, "중복 판정", self.ticket(self.v))
        require(decision.get("proceed"), "INITIAL_PREPARATION")
        self.detected = evaluate(S1, "티켓 detected 입력", decision)
        self.ack = self.ticket(self.detected, fault="before_commit" if fail_detected else None)
        if fail_detected:
            return self.ack
        self.ticket_id = self.ack["ticket_id"]
        query = evaluate(S1, "조치 전 티켓 조회 입력 1", self.ack)
        current = evaluate(S1, "조치 전 티켓 대조 1", self.ticket(query))
        return evaluate(S1, "조치1 입력 (포털 IP 차단)", current)

    def ticket(self, data, fault=None):
        route = evaluate(LOG, "저장소 요청 만들기", data)
        url = urlsplit(route["url"])
        require(url.hostname == "10.250.0.3" and url.path in (
            "/api/v1/tickets/open", "/api/v1/tickets/active", "/api/v1/tickets/record"), "TICKET_ROUTE")
        headers = {"X-Response-Key": TICKET_KEY}
        if fault == "before_commit":
            status, body = 500, {"ok": False, "error": {"code": "SERVER_ERROR", "message": "injected boundary fault"}}
        else:
            if route["method"] == "GET":
                response = self.c.get(url.path + "?" + url.query, headers=headers)
            else:
                response = self.c.post(url.path, json=route["body"], headers={**headers, "Idempotency-Key": route["idem"]})
            status, body = response.status_code, response.get_json()
            if fault == "ack_loss":
                require(status in (200, 201), "COMMIT_BEFORE_ACK_LOSS")
                status, body = None, None
        return evaluate(LOG, "응답 변환 1", {"statusCode": status, "body": body},
                        prior={"저장소 요청 만들기": route})

    def portal_call(self, request, key=None):
        require(request["path"] in ("/api/v1/response/ips/block", "/api/v1/response/ips/unblock"), "PORTAL_ROUTE")
        self.portal_posts += 1
        return self.app.test_client().post(request["path"], json={"ip": request["ip"]},
            headers={"X-Response-Key": key or PORTAL_KEY, "Idempotency-Key": request["idem"]},
            environ_overrides={"REMOTE_ADDR": "127.0.0.1"})

    def action(self, target, lose_ack=False):
        request = evaluate(PORTAL, "요청 준비", target)
        require(not request["stop"] and request["dry_run"] is False, "IN_PROCESS_ACTION_READY")
        response = self.portal_call(request)
        if lose_ack:
            require(response.status_code == 200, "PORTAL_COMMITTED")
            lost = evaluate(PORTAL, "응답 분류 1", {"statusCode": None}, prior={"요청 준비": request})
            require(lost["retry"], "PORTAL_RETRY_REQUESTED")
            first_body = response.get_json()
            response = self.portal_call(request)
            require(response.get_json() == first_body, "PORTAL_SAME_KEY_SAME_RESPONSE")
        classified = evaluate(PORTAL, "응답 분류 1", {"statusCode": response.status_code, "body": response.get_json()},
                              prior={"요청 준비": request})
        final = evaluate(PORTAL, "최종 결과", classified)
        listing = self.app.test_client().get("/api/v1/response/ips", headers={"X-Response-Key": PORTAL_KEY},
                                           environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
        final = evaluate(PORTAL, "반영 확인 판정", {"statusCode": listing.status_code, "body": listing.get_json()},
                         prior={"최종 결과": final})
        require(final["ok"] and final["applied_verified"] is True, "PORTAL_CURRENT_STATE_CONFIRMED")
        return final

    def confirm_effect(self):
        with self.app.app_context():
            row = self.models.db.session.get(self.models.BlockedIp, ATTACK)
            require(row is not None and row.active(), "PORTAL_DB_BLOCK_ACTIVE")
        blocked = self.health(ATTACK)
        require(blocked.status_code == 403 and blocked.get_json()["error"]["code"] == "IP_BLOCKED", "ATTACKER_BLOCKED")
        require(self.login(NORMAL, PASSWORD).status_code == 200, "NORMAL_LOGIN_DURING_BLOCK")
        body = deepcopy(self.applied)
        body.update(stage="effect", idempotency_key="home-s1-independent-effect")
        body["action"].update(effect_verified=True, effect_verified_at=datetime.now(timezone.utc).isoformat())
        require(self.ticket(body)["status"] == "verified", "C_EFFECT_VERIFIED")

    def restore(self, ctx):
        # Explicit manual API call in this isolated fixture. Do not enable haedam-50.
        released = self.action({"action": "unblock", "ip": ATTACK, "ticket_id": self.ticket_id,
                                "dry_run": False, "ctx": ctx})
        body = deepcopy(self.applied)
        body.update(stage="released", idempotency_key="home-s1-manual-release")
        body["action"].update(action="unblock", result="released", applied_verified=True,
            effect_verified=None, effect_verified_at=None, requested_at=released["requested_at"], finished_at=released["finished_at"])
        require(self.ticket(body)["status"] == "restored", "C_RESTORED")
        require(self.health(ATTACK).status_code == 200 and self.login(NORMAL, PASSWORD).status_code == 200,
                "ACCESS_RESTORED")
        with self.app.app_context():
            require(self.models.db.session.get(self.models.BlockedIp, ATTACK) is None, "PORTAL_DB_BLOCK_REMOVED")
        active = self.ticket({"mode": "active", "resource": {"asset_id": "haedam-portal", "via": "portal",
            "action": "block", "target": ATTACK}, "ctx": ctx})
        require(active["tickets"] == [], "NO_RECORDED_ACTIVE_CLAIM")


def run(backend_root):
    packet = json.loads((ROOT / PACKET).read_text(encoding="utf-8"))
    require(check(ROOT)["exit_code"] == 0, "SOURCE_PACKET_MISMATCH")
    revision = subprocess.check_output(["git", "-C", str(backend_root), "rev-parse", "HEAD"], text=True).strip()
    require(revision == packet["repositories"]["backend"]["source_revision"], "BACKEND_REVISION_MISMATCH")
    changed = subprocess.check_output(["git", "-C", str(backend_root), "status", "--porcelain", "--", "src"], text=True)
    require(not changed.strip(), "BACKEND_SOURCE_NOT_CLEAN")
    sys.path.insert(0, str(backend_root / "src"))
    sys.path.insert(0, str(ROOT / "services/ticket-store"))
    import haedam_portal as portal
    from haedam_portal import models
    from ticket_store import app as ticket_app, db as ticket_db
    require(Path(portal.__file__).resolve().is_relative_to((backend_root / "src").resolve()), "WRONG_PORTAL_IMPORT")
    # Process-local guard; existing user servers and global settings are untouched.
    def denied(*args, **kwargs):
        raise RuntimeError("NETWORK_FORBIDDEN")
    for name in ("connect", "connect_ex", "sendto"):
        setattr(socket.socket, name, denied)
    socket.create_connection = denied
    os.environ["GELF_PORT"] = "12201"
    cases = []
    with TemporaryDirectory(prefix="aleph-s1-real-portal-") as temp:
        for name in ("normal", "portal_ack_loss", "record_failure", "record_ack_loss", "closed_ack", "bad_portal_key", "detected_failure"):
            folder = Path(temp) / name
            folder.mkdir()
            trial = Trial(folder, portal, models, ticket_app, ticket_db)
            try:
                target = trial.start(fail_detected=name == "detected_failure")
                if name == "detected_failure":
                    stopped = evaluate(S1, "조치1 입력 (포털 IP 차단)", target, raw=True)
                    require(stopped.get("error") == "TICKET_RECORD_REQUIRED" and trial.portal_posts == 0, "NO_TARGET_BEFORE_RECORD")
                    require(trial.health(ATTACK).status_code == 200, "NO_PRE_RECORD_BLOCK")
                    with closing(ticket_db.connect(trial.c_path)) as conn:
                        require(ticket_db.list_tickets(conn) == [], "NO_PRE_RECORD_TICKET")
                    cases.append({"name": name, "passed": True, "expected_outcome": "held_before_action",
                                  "portal_post_attempts": 0, "block_events": 0, "final_attack_status": 200})
                    continue
                if name == "bad_portal_key":
                    request = evaluate(PORTAL, "요청 준비", target)
                    response = trial.portal_call(request, key="synthetic-wrong-key")
                    classified = evaluate(PORTAL, "응답 분류 1", {"statusCode": response.status_code, "body": response.get_json()}, prior={"요청 준비": request})
                    require(classified["result"] == "rejected" and not classified["retry"], "REJECT_WRONG_KEY")
                    require(trial.health(ATTACK).status_code == 200, "WRONG_KEY_DID_NOT_BLOCK")
                    with closing(ticket_db.connect(trial.c_path)) as conn:
                        require(ticket_db.get_ticket(conn, trial.ticket_id)["actions"] == [], "NO_FABRICATED_ACTION")
                    cases.append({"name": name, "passed": True, "portal_post_attempts": trial.portal_posts,
                                  "block_events": 0, "final_attack_status": 200, "expected_outcome": "rejected_no_action"})
                    continue
                receipt = trial.action(target, lose_ack=name == "portal_ack_loss")
                trial.applied = evaluate(S1, "조치1 기록 입력", receipt)
                if name in ("record_failure", "record_ack_loss"):
                    failed = trial.ticket(trial.applied, fault="before_commit" if name == "record_failure" else "ack_loss")
                    attempts = trial.portal_posts
                    stopped = evaluate(S1, "조치1 입력 (포털 IP 차단)", failed, raw=True)
                    require("error" in stopped and trial.portal_posts == attempts, "RECORD_FAILURE_STOPS_TARGET")
                recorded = trial.ticket(trial.applied)
                require(recorded["status"] == "responding", "C_APPLIED")
                duplicate = evaluate(S1, "중복 판정", trial.ticket(trial.v))
                require(duplicate["verdict"] == "duplicate_no_action", "DUPLICATE_STOPS_TARGET")
                with closing(ticket_db.connect(trial.c_path)) as conn:
                    require(len(ticket_db.get_ticket(conn, trial.ticket_id)["actions"]) == 1, "ONE_C_APPLIED_ROW")
                trial.confirm_effect()
                trial.restore(receipt["ctx"])
                if name == "closed_ack":
                    with closing(ticket_db.connect(trial.c_path)) as conn:
                        ticket_db.close_ticket(conn, trial.ticket_id, "synthetic manual restoration confirmed")
                    decision = evaluate(S1, "중복 판정", trial.ticket(trial.v))
                    cached = trial.ticket(evaluate(S1, "티켓 detected 입력", decision))
                    require(cached["status"] == "open", "ORIGINAL_ACK_REPLAYED")
                    query = evaluate(S1, "조치 전 티켓 조회 입력 1", cached)
                    stop = evaluate(S1, "조치 전 티켓 대조 1", trial.ticket(query), raw=True)
                    require(stop.get("error") == "TICKET_CURRENT_REQUIRED", "CLOSED_ACK_STOPS_TARGET")
                events = trial.events()
                blocks = sum(e["event_type"] == "web.ip_blocked" for e in events)
                releases = sum(e["event_type"] == "web.ip_unblocked" for e in events)
                require(blocks == releases == 1, "ONE_BLOCK_AND_ONE_MANUAL_RELEASE")
                require(trial.portal_posts == (3 if name == "portal_ack_loss" else 2), "NO_EXTRA_TARGET_POST")
                cases.append({"name": name, "passed": True, "portal_post_attempts": trial.portal_posts,
                    "block_events": blocks, "release_events": releases, "final_attack_status": 200,
                    "normal_login_during_block": 200, "c_effect_recorded": True, "c_restored": True})
            finally:
                trial.close()
    return {"schema_version": "1.0", "scope": "in_process_real_flask_sqlite", "backend_revision": revision,
        "source_packet_revision": packet["repositories"]["capstone"]["source_revision"],
        "actual_device_calls": 0, "network_transport_exercised": False, "live_n8n_verified": False,
        "graylog_verified": False, "mysql_verified": False, "deployment_ready": False,
        "manual_fixture_release": True, "cases": cases,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "code_runner_sha256": hashlib.sha256((ROOT / "tests/helpers/n8n_code_runner.cjs").read_bytes()).hexdigest(),
        "workflow_sha256": {r["path"]: r["sha256"] for r in packet["n8n_exports"] if r["path"] in packet["s1_workflow_dependencies"]},
        "remaining": ["Graylog rule and webhook auth", "n8n engine and HTTP expression bindings",
                      "VPN/NAT real source and normal clients", "MySQL deployment and independent school restoration"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new report folder, never overwrite")
    args = parser.parse_args()
    if args.output.exists():
        parser.exit(2, "Report folder already exists; select a new output folder.\n")
    try:
        report = run(args.backend_root.resolve())
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("PASS: 7 isolated real-portal/C scenarios; actual device calls 0; runtime deployment unverified.")
        return 0
    except (RuntimeError, OSError, ImportError, ValueError, subprocess.SubprocessError):
        print("Rehearsal failed; check the explicit source revision, backend environment and isolated fixture.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
