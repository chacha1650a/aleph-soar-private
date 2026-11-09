"""Baseline + authenticated candidate API, through local C Flask test clients only."""
import argparse
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.control_audit import ControlAudit
from tools.rehearse_shared_release import run as baseline
from tools.rehearse_integration import require
from tools.resource_gate import ResourceGate
from tools.shared_claims import ClaimBook
from tools.shared_control_api import Principal, create_shared_control_api
from tools.shared_release_simulation import SharedReleaseSimulation
from tools.simulated_execution import CTestClient, SimulatedExecution, SimulatedTarget


def run(source):
    report = baseline(source)
    from ticket_store.app import create_n8n_app, create_dashboard_app
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in (source / "contracts").glob("*.schema.json")]
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
    c_validator = Draft202012Validator(json.loads((source / "contracts/ticket-response.schema.json").read_text(encoding="utf-8")),
        registry=registry, format_checker=FormatChecker(formats=["date-time", "ipv4", "ipv6"]))
    api_validator = Draft202012Validator(json.loads((ROOT / "contracts/candidate-shared-control.schema.json").read_text(encoding="utf-8")))
    sample = json.loads((source / "contracts/ticket-examples/record-s12-applied.json").read_text(encoding="utf-8"))
    resource = {"asset_id": sample["asset_id"], **{k: sample["action"][k] for k in ("via", "action", "target")}}
    with TemporaryDirectory(prefix="control-api-candidate-") as temp:
        for scenario in ("auth_and_idempotency", "cancel_before_target", "repair_after_target", "repair_after_first_record", "repair_after_book_complete",
                         "journal_terminal", "journal_pending", "journal_no_dispatch", "journal_stale"):
            folder = Path(temp) / scenario
            folder.mkdir()
            c_path = str(folder / "tickets.db")
            tickets = CTestClient(create_n8n_app(c_path, "synthetic-control-C-key").test_client(),
                create_dashboard_app(c_path).test_client(), "synthetic-control-C-key", c_validator)
            gate = ResourceGate(folder / "gate.db", create=True)
            target = SimulatedTarget(folder / "target.db", create=True)
            book = ClaimBook(folder / "claims.db", create=True)
            shared = SharedReleaseSimulation(gate, book, target, tickets)
            apply = SimulatedExecution(gate, target, tickets)
            owners = {}
            for seat in ("A", "D"):
                body = deepcopy(sample)
                body.update(seat=seat, case_id="S1" if seat == "A" else "S12",
                    group_key="synthetic-control-user" if seat == "A" else resource["target"], event_ids=["synthetic-control-" + seat])
                request_id = "control-apply-" + seat
                require(apply.run(request_id, "apply", body, resource)["state"] == "recorded", "control fixture apply")
                ticket_id = tickets.observe("apply", {"seat": seat, "group_key": body["group_key"]})["observation"]["body"]["ticket_id"]
                owners[seat] = (ticket_id, request_id + "-record")
            tokens = {seat: "synthetic-control-token-" + seat for seat in ("A", "D", "op")}
            credentials = {tokens[seat]: Principal("owner-" + seat, "owner", frozenset({seat})) for seat in ("A", "D")}
            credentials[tokens["op"]] = Principal("operator", "recovery", frozenset())
            audit = ControlAudit(folder / "audit.db", create=True)
            app = create_shared_control_api(shared, audit, credentials).test_client()

            def post(path, payload, seat, key):
                response = app.post(path, json=payload, headers={"X-Control-Key": tokens[seat], "Idempotency-Key": key})
                api_validator.validate(response.get_json())
                return response

            def owner_body(seat):
                return {"operation": "withdraw", "resource": resource, "ticket_id": owners[seat][0], "action_id": owners[seat][1]}

            if scenario.startswith("journal_"):
                actor = "D" if scenario == "journal_pending" else "A"
                if actor == "D":
                    require(post("/candidate/v1/shared/intents", owner_body("A"), "A", "first-owner-withdraw").status_code == 200, "first journal owner")
                original = shared.withdraw
                dispatches = []

                def lost_result(*args):
                    dispatches.append(1)
                    if scenario != "journal_no_dispatch":
                        original(*args, fault="after_target" if scenario == "journal_pending" else None)
                    raise RuntimeError("synthetic lost API result")

                shared.withdraw = lost_result
                require(post("/candidate/v1/shared/intents", owner_body(actor), actor, "lost-api-result").status_code == 500, "lost API result")

                def get(path, seat, key="operator-read-1"):
                    response = app.get(path, headers={"X-Control-Key": tokens[seat], "Idempotency-Key": key})
                    api_validator.validate(response.get_json())
                    return response

                journal_id = get("/candidate/v1/shared/requests/status", actor, "lost-api-result").get_json()["result"]["journal_id"]
                path = "/candidate/v1/shared/journals/" + journal_id
                require(get(path, actor).status_code == 403, "owner cannot review operator journal")
                review = get(path, "op").get_json()["result"]

                def resolve_body(snapshot):
                    return {"executor_stopped": True, "evidence_ref": "synthetic/rehearsal-journal-review",
                            "expected_revision": snapshot["revision"], "review_hash": snapshot["review_hash"]}

                if scenario == "journal_pending":
                    require(not review["resolution_allowed"], "pending work blocks journal close")
                    require(post(path + "/resolve", resolve_body(review), "op", "operator-close-1").status_code == 409, "no premature journal close")
                    repair_path = "/candidate/v1/shared/plans/" + review["plan_id"] + "/repair"
                    require(post(repair_path, {"executor_stopped": True, "evidence_ref": "synthetic/repair-before-resolution"},
                        "op", "journal-repair-1").get_json()["result"]["state"] == "reconciled", "repair before journal close")
                    require(post(path + "/resolve", resolve_body(review), "op", "stale-close-1").get_json()["error"]["code"] == "STALE_REVIEW", "changed business invalidates review")
                    review = get(path, "op").get_json()["result"]
                if scenario == "journal_no_dispatch":
                    require(review["related_state"] == "not_seen" and not review["resolution_allowed"], "no guessed zero-effect proof")
                    require(post(path + "/resolve", resolve_body(review), "op", "operator-close-1").status_code == 409, "unknown dispatch stays held")
                elif scenario == "journal_stale":
                    ack = {"ok": True, "synthetic_only": True, "allow_target_call": False,
                           "result": {"state": "withdrawn_waiting", "plan_id": None}}
                    audit.finish("owner-" + actor, hashlib.sha256(b"lost-api-result").hexdigest(), 200, ack)
                    require(post(path + "/resolve", resolve_body(review), "op", "operator-close-1").get_json()["error"]["code"] == "STALE_REVIEW", "late ACK invalidates revision")
                else:
                    require(review["resolution_allowed"], "terminal work permits response-journal close")
                    closed = post(path + "/resolve", resolve_body(review), "op", "operator-close-final")
                    require(closed.get_json()["result"]["state"] == "journal_resolved", "operator journal close")
                    require(post(path + "/resolve", resolve_body(review), "op", "operator-close-final").get_json() == closed.get_json(), "resolution replay")
                    require(post("/candidate/v1/shared/intents", owner_body(actor), actor, "lost-api-result").get_json()["error"]["code"] == "OPERATOR_RESOLVED", "original key stays consumed")
                require(len(dispatches) == 1, "journal review never redispatches business")
            elif scenario == "auth_and_idempotency":
                path = "/candidate/v1/shared/intents"
                unauthorized = app.post(path, json=owner_body("A"))
                api_validator.validate(unauthorized.get_json())
                require(unauthorized.status_code == 401, "candidate missing auth")
                require(post(path, owner_body("D"), "A", "forbidden-0001").status_code == 403, "server seat grants")
                a = post(path, owner_body("A"), "A", "same-key-0001")
                require(a.get_json()["result"]["state"] == "withdrawn_waiting" and target.active(resource), "authenticated logical withdrawal")
                require(post(path, owner_body("A"), "A", "same-key-0001").get_json() == a.get_json(), "candidate response replay")
                require(post(path, {**owner_body("A"), "operation": "retain"}, "A", "same-key-0001").status_code == 409, "candidate payload conflict")
                require(post(path, owner_body("D"), "D", "same-key-0001").get_json()["result"]["state"] == "released", "actor-scoped key")
            else:
                shared.withdraw("operator-seed-a", resource, *owners["A"])
                fault = "before_target" if scenario == "cancel_before_target" else scenario[len("repair_"):]
                prepared = shared.withdraw("operator-seed-d", resource, *owners["D"], fault=fault)
                plan_id = prepared["plan_id"]
                recovery = {"executor_stopped": True, "evidence_ref": "synthetic/control-rehearsal"}
                prefix = "/candidate/v1/shared/plans/" + plan_id
                require(post(prefix + "/repair", recovery, "A", "denied-recovery").status_code == 403, "recovery role")
                if scenario == "cancel_before_target":
                    require(post(prefix + "/cancel", recovery, "op", "cancel-plan-0001").get_json()["result"]["state"] == "cancelled", "no-effect cancellation")
                    require(target.receipt(plan_id) is None and target.active(resource), "cancel preserved physical fake state")
                    require(all(tickets.ticket(t)["status"] == "verified" for t, _ in owners.values()), "cancel leaves C effects unchanged")
                else:
                    require(post(prefix + "/cancel", recovery, "op", "cancel-plan-0001").status_code == 409, "post-effect cancellation refused")
                    repaired = post(prefix + "/repair", recovery, "op", "repair-plan-0001")
                    require(repaired.get_json()["result"]["state"] == "reconciled", "authenticated record-only repair")
                    require(post(prefix + "/repair", recovery, "op", "repair-plan-0001").get_json() == repaired.get_json(), "repair response replay")
            with closing(target.connect()) as conn:
                count = conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
            expected_count = 2 if scenario in ("cancel_before_target", "journal_terminal", "journal_no_dispatch", "journal_stale") else 3
            require(count == expected_count, "no extra fake target calls")
            report["cases"].append({"name": "api_" + scenario, "passed": True,
                "detail": "candidate auth/scope/idempotency/recovery checked against C test clients; no real target",
                "synthetic_target_receipts": count})
            print("PASS api_" + scenario)
    report["scope"] = "baseline_shared_policy_and_local_control_api_candidate"
    for name in ("tools/shared_control_api.py", "tools/control_audit.py", "tools/rehearse_control_api.py", "contracts/candidate-shared-control.schema.json"):
        report["implementation_sha256"][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    report["remaining"][0] = "C/D policy adoption, real identity/TLS/deployment, v1-to-v2 migration and stopped-executor verification"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output folder exists; choose a new one")
    report = run(args.ticket_source.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    text = "# Local control API candidate rehearsal\n\nSynthetic only; actual device calls: 0; live n8n: unverified.\n\n"
    text += "\n".join(f"- PASS {c['name']}: {c['detail']}" for c in report["cases"]) + "\n"
    (args.output / "report.md").write_text(text, encoding="utf-8", newline="\n")
    manifest = {"complete": True, "files": {name: hashlib.sha256((args.output / name).read_bytes()).hexdigest()
        for name in ("report.json", "report.md")}}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Verified 21 synthetic cases (baseline 6 + shared policy 6 + local API 9)")


if __name__ == "__main__":
    main()
