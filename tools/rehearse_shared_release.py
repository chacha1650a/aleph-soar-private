"""Run baseline + candidate shared-release scenarios against local C test clients."""
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

from tools.rehearse_integration import run as baseline, require
from tools.resource_gate import ResourceGate
from tools.shared_claims import ClaimBook
from tools.shared_release_simulation import SharedReleaseSimulation
from tools.simulated_execution import CTestClient, SimulatedExecution, SimulatedTarget


def run(source):
    report = baseline(source)  # Also verifies pinned C head and patch before importing C.
    from ticket_store.app import create_n8n_app, create_dashboard_app
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in (source / "contracts").glob("*.schema.json")]
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
    validator = Draft202012Validator(json.loads((source / "contracts/ticket-response.schema.json").read_text(encoding="utf-8")),
        registry=registry, format_checker=FormatChecker(formats=["date-time", "ipv4", "ipv6"]))
    sample = json.loads((source / "contracts/ticket-examples/record-s12-applied.json").read_text(encoding="utf-8"))
    resource = {"asset_id": sample["asset_id"], **{k: sample["action"][k] for k in ("via", "action", "target")}}
    with TemporaryDirectory(prefix="shared-release-candidate-") as temp:
        for scenario in ("last_owner", "new_owner", "retained_owner", "after_target", "after_first_record", "after_book_complete"):
            folder = Path(temp) / scenario
            folder.mkdir()
            c_path = str(folder / "tickets.db")

            def client():
                return CTestClient(create_n8n_app(c_path, "synthetic-shared-key-0001").test_client(),
                    create_dashboard_app(c_path).test_client(), "synthetic-shared-key-0001", validator)

            gate = ResourceGate(folder / "gate.db", create=True)
            target = SimulatedTarget(folder / "target.db", create=True)
            book = ClaimBook(folder / "claims.db", create=True)
            tickets = client()
            applied = SimulatedExecution(gate, target, tickets)
            shared = SharedReleaseSimulation(gate, book, target, tickets)
            owners = {}

            def add_owner(seat):
                body = deepcopy(sample)
                body.update(seat=seat, case_id={"A": "S1", "B": "S8", "D": "S12"}[seat],
                            group_key="zz_synthetic_owner" if seat == "A" else resource["target"], event_ids=["synthetic-owner-" + seat])
                request = "claim-" + seat.lower() + "-0001"
                require(applied.run(request, "apply", body, resource)["state"] == "recorded", "owner apply " + seat)
                ticket_id = tickets.observe("apply", {"seat": seat, "group_key": body["group_key"]})["observation"]["body"]["ticket_id"]
                owners[seat] = (ticket_id, request + "-record")

            def count():
                with closing(target.connect()) as conn:
                    return conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]

            add_owner("A")
            add_owner("D")
            first = shared.withdraw("withdraw-a-0001", resource, *owners["A"])
            require(first["state"] == "withdrawn_waiting" and target.active(resource) and count() == 2, "logical-only withdrawal")
            require(tickets.ticket(owners["A"][0])["status"] == "verified", "withdrawal does not claim physical release")
            require(shared.withdraw("withdraw-a-0001", resource, *owners["A"])["state"] == "replayed" and count() == 2, "intent replay")
            if scenario == "retained_owner":
                require(shared.retain("retain-a-0001", resource, *owners["A"])["state"] == "retained", "explicit owner retain")
                require(shared.withdraw("withdraw-d-0001", resource, *owners["D"])["state"] == "withdrawn_waiting", "retained owner blocks final release")
                last = shared.withdraw("withdraw-a-0002", resource, *owners["A"])
            elif scenario == "new_owner":
                add_owner("B")
                require(shared.withdraw("withdraw-d-0001", resource, *owners["D"])["state"] == "withdrawn_waiting", "new owner blocks old final release")
                last = shared.withdraw("withdraw-b-0001", resource, *owners["B"])
            else:
                fault = scenario if scenario.startswith("after_") else None
                last = shared.withdraw("withdraw-d-0001", resource, *owners["D"], fault=fault)
            if scenario.startswith("after_"):
                require(last["state"] == "pending" and not target.active(resource) and count() == 3, "uncertain fake physical release")
                require(gate.reserve(resource, "blocked-new-call", "apply", {})["state"] == "busy", "pending blocks interleaving")
                restarted = SharedReleaseSimulation(ResourceGate(gate.path), ClaimBook(book.path), SimulatedTarget(target.path), client())
                repaired = restarted.repair_records("withdraw-d-0001", resource, *owners["D"], executor_stopped=True)
                require(repaired["state"] == "reconciled" and count() == 3, "record-only shared repair")
            else:
                require(last["state"] == "released", "last owner synthetic release")
            require(not target.active(resource) and not shared.snapshot(resource), "all owner releases observed")
            require(all(tickets.ticket(ticket)["status"] == "restored" for ticket, _ in owners.values()), "all C owner tickets restored")
            require(count() == len(owners) + 1, "one physical synthetic release only")
            report["cases"].append({"name": "shared_" + scenario, "passed": True,
                "detail": "candidate policy: logical withdrawal, one fake release, all C owner records verified; no target recall in repair",
                "synthetic_target_receipts": count()})
            print("PASS shared_" + scenario)
    report["scope"] = "baseline_and_candidate_shared_release_policy"
    for name in ("tools/shared_claims.py", "tools/shared_release_simulation.py", "tools/rehearse_shared_release.py"):
        report["implementation_sha256"][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    report["remaining"][0] = "C/D adoption, authentication and operational API for the candidate shared-claim policy"
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
    markdown = "# Candidate shared-release synthetic rehearsal\n\nSynthetic only; actual device calls: 0; live n8n: unverified.\n\n"
    markdown += "\n".join(f"- PASS {c['name']}: {c['detail']}" for c in report["cases"]) + "\n"
    (args.output / "report.md").write_text(markdown, encoding="utf-8", newline="\n")
    manifest = {"complete": True, "files": {name: hashlib.sha256((args.output / name).read_bytes()).hexdigest()
                                             for name in ("report.json", "report.md")}}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Verified 12 synthetic cases (baseline 6 + candidate shared-release 6)")


if __name__ == "__main__":
    main()
