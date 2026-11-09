"""One-command synthetic C integration/recovery rehearsal. No live targets or n8n."""
import argparse
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.resource_gate import ResourceGate
from tools.simulated_execution import CTestClient, SimulatedExecution, SimulatedTarget


def require(condition, name):
    if not condition:
        raise RuntimeError("synthetic rehearsal failed: " + name)


def run(source):
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    diff = subprocess.check_output(["git", "diff", "--binary", "--full-index", "--no-ext-diff"], cwd=source)
    patch = (ROOT / "patches/ticket-store-pr55/0001-resource-via-cycle.patch").read_bytes()
    require(base == "e8db8ecd6aa497ad75df1d89cf01653b6cb5988a" and diff == patch, "pinned C patch checkout")
    sys.path.insert(0, str(source / "services/ticket-store"))
    from ticket_store.app import create_n8n_app, create_dashboard_app
    from ticket_store import db
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource

    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in (source / "contracts").glob("*.schema.json")]
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
    validator = Draft202012Validator(json.loads((source / "contracts/ticket-response.schema.json").read_text(encoding="utf-8")),
        registry=registry, format_checker=FormatChecker(formats=["date-time", "ipv4", "ipv6"]))
    sample = json.loads((source / "contracts/ticket-examples/record-s12-applied.json").read_text(encoding="utf-8"))
    resource = {"asset_id": sample["asset_id"], **{k: sample["action"][k] for k in ("via", "action", "target")}}

    def make_body(mode, event="synthetic-event-01"):
        body = deepcopy(sample)
        body["event_ids"] = [event]
        if mode == "release":
            body["stage"] = "released"
            body["action"].update(action="unblock", result="released")
        return body

    cases = []
    with TemporaryDirectory(prefix="home-rehearsal-") as temp:
        for scenario in ("normal", "overlap", "after_target", "after_record", "record_unavailable", "ack_loss"):
            folder = Path(temp) / scenario
            folder.mkdir()
            c_path = str(folder / "tickets.db")

            def clients():
                return CTestClient(create_n8n_app(c_path, "synthetic-home-key-0001").test_client(),
                                   create_dashboard_app(c_path).test_client(), "synthetic-home-key-0001", validator)

            target = SimulatedTarget(folder / "target.db", create=True)
            gate = ResourceGate(folder / "gate.db", create=True)
            tickets = clients()
            simulation = SimulatedExecution(gate, target, tickets)

            def count():
                with closing(target.connect()) as conn:
                    return conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]

            if scenario == "normal":
                require(simulation.run("apply-0001", "apply", make_body("apply"), resource)["state"] == "recorded", scenario)
                require(simulation.run("apply-0001", "apply", make_body("apply"), resource)["state"] == "replayed" and count() == 1, "normal replay")
                require(simulation.run("release-0001", "release", make_body("release"), resource)["state"] == "recorded", "normal release")
                require(simulation.run("new-cycle-0001", "apply", make_body("apply", "synthetic-event-02"), resource)["state"] == "not_called", "restored requires close")
                query = tickets.observe("apply", {"seat": "D", "group_key": resource["target"]})
                old_id = query["observation"]["body"]["ticket_id"]
                with closing(db.connect(c_path)) as conn:
                    db.close_ticket(conn, old_id, "synthetic fixture close after verified release")
                require(simulation.run("new-cycle-0002", "apply", make_body("apply", "synthetic-event-02"), resource)["state"] == "recorded", "new cycle after close")
                new_id = tickets.observe("apply", {"seat": "D", "group_key": resource["target"]})["observation"]["body"]["ticket_id"]
                require(new_id != old_id, "new cycle ticket ID")
                require(simulation.run("release-0002", "release", make_body("release", "synthetic-event-02"), resource)["state"] == "recorded", "new cycle release")
                require(not target.active(resource) and count() == 4, "normal final synthetic state")
                detail = "two cycles, stable replay, explicit close/new ticket, synthetic final release"
            elif scenario == "overlap":
                a = make_body("apply")
                a.update(seat="A", case_id="S1", group_key="zz_synthetic_owner")
                require(simulation.run("owner-a-0001", "apply", a, resource)["state"] == "recorded", "owner A")
                require(simulation.run("owner-d-0001", "apply", make_body("apply"), resource)["state"] == "recorded", "owner D")
                require(simulation.run("release-d-0001", "release", make_body("release"), resource)["state"] == "not_called", "other owner hold")
                require(target.active(resource) and count() == 2, "no overlap release")
                detail = "different grouping owners: release held; claim relinquishment policy unresolved"
            else:
                original = tickets.record
                if scenario in ("record_unavailable", "ack_loss"):
                    def fail(body, key):
                        if scenario == "ack_loss":
                            original(body, key)
                        raise RuntimeError("synthetic record failure")
                    tickets.record = fail
                outcome = simulation.run("unknown-0001", "apply", make_body("apply"), resource,
                    fault=scenario if scenario.startswith("after_") else None)
                require(outcome["state"] == "pending" and target.active(resource) and count() == 1, scenario)
                require(simulation.run("blocked-release", "release", make_body("release"), resource)["state"] == "busy", "pending blocks release")
                # Reopen BOTH stores and C applications, without clearing pending or reissuing target commands.
                simulation = SimulatedExecution(ResourceGate(gate.path), SimulatedTarget(target.path), clients())
                repaired = simulation.repair_records("unknown-0001", "apply", make_body("apply"), resource, executor_stopped=True)
                require(repaired["state"] == "reconciled" and count() == 1, "record-only repair after restart")
                require(simulation.run("unknown-0001", "apply", make_body("apply"), resource)["state"] == "replayed", "repaired replay")
                require(simulation.run("release-0001", "release", make_body("release"), resource)["state"] == "recorded", "release after repair")
                require(not target.active(resource) and count() == 2, "repaired final synthetic state")
                detail = "pending survives restart; record-only repair; target receipts unchanged during repair"
            cases.append({"name": scenario, "passed": True, "detail": detail, "synthetic_target_receipts": count()})
            print("PASS " + scenario)
    return {"version": 1, "synthetic_only": True, "scope": "block_unblock_simulated_target",
            "actual_device_calls": 0, "live_n8n_verified": False, "c_source_commit": base,
            "c_patch_sha256": hashlib.sha256(patch).hexdigest(), "cases": cases,
            "implementation_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                "tools/simulated_execution.py", "tools/resource_gate.py", "tools/rehearse_integration.py",
                "infra/n8n/workflows/haedam-16-ticket-decision-offline.json")},
            "remaining": ["C/D policy adoption and shared-claim relinquishment", "actual n8n deployment and all-caller coordination",
                          "actual target idempotency, effects, normal access and recovery", "school VPN/firewall and operating procedures"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new local output folder; never overwritten")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output folder already exists; choose a new name")
    report = run(args.ticket_source.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (args.output / "report.json").write_bytes(raw)
    markdown = "# Home synthetic integration rehearsal\n\nSynthetic only; actual device calls: 0; live n8n: unverified.\n\n"
    markdown += "\n".join(f"- PASS {c['name']}: {c['detail']}" for c in report["cases"]) + "\n"
    (args.output / "report.md").write_text(markdown, encoding="utf-8", newline="\n")
    manifest = {"complete": True, "files": {name: hashlib.sha256((args.output / name).read_bytes()).hexdigest()
                                             for name in ("report.json", "report.md")}}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Verified 6 synthetic integration/recovery cases; report written without credentials")


if __name__ == "__main__":
    main()
