"""Synthetic C API -> exported n8n JS comparison; optional loopback GET transport."""
import argparse
from contextlib import contextmanager, ExitStack
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
WORKFLOW = ROOT / "infra/n8n/workflows/haedam-16-ticket-decision-offline.json"


@contextmanager
def local_server(app):
    from werkzeug.serving import make_server, WSGIRequestHandler

    class Quiet(WSGIRequestHandler):
        def log(self, *args, **kwargs):
            pass

    server = make_server("127.0.0.1", 0, app, threaded=True, request_handler=Quiet)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def evaluate(inputs):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required; no Python simulation is substituted")
    code = json.loads(WORKFLOW.read_text(encoding="utf-8"))[0]["nodes"][1]["parameters"]["jsCode"]
    runner = """
const fs = require('node:fs'), vm = require('node:vm');
const p = JSON.parse(fs.readFileSync(0, 'utf8'));
const sandbox = {$input: {all: () => p.inputs.map(json => ({json}))}};
const result = vm.runInNewContext('(function(){' + p.code + '\\n})()', sandbox, {timeout: 1000});
process.stdout.write(JSON.stringify(result.map(item => item.json)));
"""
    run = subprocess.run([node, "-e", runner], input=json.dumps({"code": code, "inputs": inputs}),
                         text=True, encoding="utf-8", capture_output=True, timeout=10, check=True)
    return json.loads(run.stdout)


def check_source(source, *, loopback_http=False, reserved_trial=False):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    package = source / "services/ticket-store"
    if not (package / "ticket_store/app.py").is_file():
        raise ValueError("ticket source checkout is missing services/ticket-store")
    sys.path.insert(0, str(package))
    from ticket_store.app import create_n8n_app

    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in (source / "contracts").glob("*.schema.json")]
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
    schema = json.loads((source / "contracts/ticket-response.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, registry=registry)
    body = json.loads((source / "contracts/ticket-examples/record-s12-applied.json").read_text(encoding="utf-8"))
    resource = {"asset_id": body["asset_id"], **{k: body["action"][k] for k in ("via", "action", "target")}}
    expected = {"resource": resource, "seat": body["seat"], "bot": body["action"]["bot"], "group_key": body["group_key"]}
    cases = []
    trial_answers = {}
    with TemporaryDirectory(prefix="ticket-guard-offline-") as temp, ExitStack() as stack:
        app = create_n8n_app(str(Path(temp) / "tickets.db"), "synthetic-guard-key-0001")
        client = app.test_client()
        headers = {"X-Response-Key": "synthetic-guard-key-0001"}
        transport = None
        if loopback_http or reserved_trial:
            from tools.ticket_http import TicketHTTP
            transport = TicketHTTP(stack.enter_context(local_server(app)), headers["X-Response-Key"])
        trial = None
        if reserved_trial:
            from tools.resource_gate import ResourceGate
            from tools.ticket_trial import TicketTrial
            trial = TicketTrial(ResourceGate(Path(temp) / "reservations.db", create=True), transport)

        def record(payload, key):
            response = client.post("/api/v1/tickets/record", json=payload, headers={**headers, "Idempotency-Key": key})
            validator.validate(response.get_json())
            return {"status": response.status_code, "body": response.get_json()}

        def query(mode, name, reason, owner=None):
            args = {"seat": body["seat"], "group_key": body["group_key"]} if mode == "apply" else resource
            if trial:
                scope = {**expected, "owner_ticket_id": owner}
                outcome = trial.run(name, mode, scope, f"synthetic/{name}")
                if outcome["state"] != "completed" or outcome["reservation_state"] != "released":
                    raise RuntimeError(f"reserved trial failed: {name}")
                replay = trial.run(name, mode, scope, f"synthetic/{name}")
                if replay["state"] != "replayed" or replay["decision"] is not None:
                    raise RuntimeError(f"stale candidate replayed: {name}")
                trial_answers[name] = outcome["decision"]
                cases.append((name, reason, None))
                return
            if transport:
                scope = {**expected, "owner_ticket_id": owner}
                envelope = transport.apply(scope) if mode == "apply" else transport.release(scope)
                validator.validate(envelope["observation"]["body"])
                cases.append((name, reason, envelope))
                return
            response = client.get("/api/v1/tickets/" + ("open" if mode == "apply" else "active"),
                                  query_string=args, headers=headers)
            validator.validate(response.get_json())
            cases.append((name, reason, {"mode": mode, "expected": {**expected, "owner_ticket_id": owner},
                "observation": {"status": response.status_code, "query": args, "body": response.get_json()}}))

        query("apply", "empty", "no_open_ticket_snapshot")
        first = record(body, "guard-d-applied")
        owner = first["body"]["ticket_id"]
        cases.append(("record_ack", "effect_not_inferred", {"mode": "record_response", "expected": {"ticket_id": None}, "observation": first}))
        query("apply", "active", "matching_active_action")
        other = deepcopy(body)
        other.update(seat="A", case_id="S1", group_key="zz_offline_guard")
        other["action"]["bot"] = "manual"
        record(other, "guard-a-applied")
        query("release", "cross_group_bot", "other_active_claims", owner)
        other["stage"] = "released"
        other["action"].update(action="unblock", result="released")
        record(other, "guard-a-released")
        query("release", "owner_only", "owner_only_snapshot_requires_serialization", owner)
        released = deepcopy(body)
        released["stage"] = "released"
        released["action"].update(action="unblock", result="released")
        record(released, "guard-d-released")
        query("release", "released", "no_recorded_claims", owner)
        query("apply", "restored", "close_restored_before_new_cycle")
        fresh = deepcopy(body)
        fresh["event_ids"] = ["synthetic-new-cycle"]
        conflict = record(fresh, "guard-new-cycle")
        cases.append(("cycle_conflict", "resolve_cycle_or_asset_scope", {"mode": "record_response", "expected": {"ticket_id": owner}, "observation": conflict}))
    direct_inputs = [data for _, _, data in cases if data is not None]
    direct_outputs = evaluate(direct_inputs)
    if len(direct_outputs) != len(direct_inputs):
        raise RuntimeError("direct guard output count mismatch")
    direct_answers = iter(direct_outputs)
    answers = [trial_answers[name] if data is None else next(direct_answers) for name, _, data in cases]
    if len(answers) != len(cases):
        raise RuntimeError("guard output count mismatch")
    for (name, reason, _), answer in zip(cases, answers):
        if answer.get("reason") != reason or answer.get("allow_target_call") is not False or answer.get("automatic_retry") is not False:
            raise RuntimeError(f"guard integration failed: {name}")
        print(f"PASS {name}: {reason}")
    label = ("6 reserved loopback GET trials + 2 test-client record responses" if reserved_trial else
             "6 loopback HTTP GETs + 2 test-client record responses" if loopback_http else "Flask test client")
    print(f"Verified {len(cases)} synthetic C API -> exported JS cases ({label}); no live n8n/target calls")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket-source", type=Path, required=True, help="local PR55 checkout with the reviewed patch applied")
    parser.add_argument("--loopback-http", action="store_true", help="temporary 127.0.0.1 server; read-only GET observations over real HTTP")
    parser.add_argument("--reserved-trial", action="store_true", help="reserve before each loopback GET/JS trial, then finish not_called")
    args = parser.parse_args()
    check_source(args.ticket_source.resolve(), loopback_http=args.loopback_http, reserved_trial=args.reserved_trial)


if __name__ == "__main__":
    main()
