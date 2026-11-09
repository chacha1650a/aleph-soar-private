"""Check local S1 source packet consistency, never deployment readiness.

Reads the pinned manifest and known source files only. No network, git commands,
credential lookup, imports from exports, workflow execution or file writes.
Exit 0: source bundle matches, runtime pending; 2: invalid/incomplete input;
4: source or dependency mismatch. Output contains fixed codes and counts only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.check_n8n_webhooks import inspect_webhook

ROOT = Path(__file__).resolve().parents[1]
PACKET = "docs/capstone/evidence/s1-candidate-20261030/versions.json"
LEGACY_PACKET = "docs/capstone/evidence/s1-candidate-20261028/versions.json"  # preserved; select with --packet
ENTRY = "haedamS1Main01"
TICKET_FILES = {"api_n8n.py", "core.py", "db.py", "app.py", "dashboard.py", "validate.py"}


class Invalid(Exception):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Invalid()
        result[key] = value
    return result


def _json(raw):
    def invalid_constant(value):
        raise Invalid()
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique, parse_constant=invalid_constant)


def _read(root, relative):
    source = root / relative
    if not source.resolve().is_relative_to(root):
        raise Invalid()
    return source.read_bytes()


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def check(root, packet=PACKET):
    report = {"scope": "local_source_bundle", "runtime_verified": False, "deployment_ready": False,
              "errors": [], "summary": {}, "pending": ["FINAL_DEPLOYMENT_HEAD", "RUNNING_IMAGES_AND_DATABASE",
                "PUBLISHED_WORKFLOW_AND_CREDENTIALS", "INGRESS_AUTH_RUNTIME", "SOURCE_PATH_AND_DETECTOR",
                "ACTUAL_EFFECT_NORMAL_ACCESS_AND_RESTORATION"]}
    codes = report["errors"]
    try:
        root = root.resolve()
        # The packet path is explicitly selected; its contents cannot select arbitrary reads.
        manifest = _json(_read(root, packet))
        if (not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0"
                or manifest.get("scope") not in {"home_candidate_sources", "integration_candidate_sources"}
                or manifest.get("runtime_verified") is not False):
            raise Invalid()
        rows, ticket = manifest.get("n8n_exports"), manifest.get("ticket_source_sha256")
        deps = manifest.get("s1_workflow_dependencies")
        if not isinstance(rows, list) or not rows or not isinstance(ticket, dict) or set(ticket) != TICKET_FILES:
            raise Invalid()
        expected = {}
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {"path", "sha256"}
                    or not isinstance(row["path"], str)
                    or not re.fullmatch(r"infra/n8n/workflows/haedam-[a-zA-Z0-9-]+\.json", row["path"])
                    or row["path"] in expected or not _digest(row["sha256"])):
                raise Invalid()
            expected[row["path"]] = row["sha256"]
        if (not isinstance(deps, list) or not deps or not all(isinstance(p, str) and p in expected for p in deps)
                or len(set(deps)) != len(deps) or not all(_digest(v) for v in ticket.values())):
            raise Invalid()
        actual = {p.relative_to(root).as_posix() for p in (root / "infra/n8n/workflows").glob("*.json")}
        if actual != set(expected):
            codes.append("WORKFLOW_INVENTORY_MISMATCH")
        workflows = {}
        for relative, digest in expected.items():
            raw = _read(root, relative)
            if hashlib.sha256(raw).hexdigest() != digest:
                codes.append("WORKFLOW_HASH_MISMATCH")
            payload = _json(raw)
            payload = payload if isinstance(payload, list) else [payload]
            if not payload:
                raise Invalid()
            for w in payload:
                if not isinstance(w, dict) or not isinstance(w.get("nodes"), list) or not w["nodes"]:
                    raise Invalid()
                if any(not isinstance(n, dict) or not isinstance(n.get("type"), str) for n in w["nodes"]):
                    raise Invalid()
                if w.get("id") is None:
                    continue  # The offline standalone guard has no workflow ID.
                if not isinstance(w["id"], str) or w["id"] in workflows:
                    raise Invalid()
                workflows[w["id"]] = (relative, w)
        for name, digest in ticket.items():
            raw = _read(root, "services/ticket-store/ticket_store/" + name)
            if hashlib.sha256(raw).hexdigest() != digest:
                codes.append("TICKET_SOURCE_HASH_MISMATCH")
        visited, stack, paths = set(), set(), set()
        hooks = []

        def visit(wid):
            if wid in stack:
                codes.append("WORKFLOW_CALL_CYCLE")
                return
            if wid in visited:
                return
            if wid not in workflows:
                codes.append("WORKFLOW_REFERENCE_UNRESOLVED")
                return
            visited.add(wid)
            stack.add(wid)
            relative, workflow = workflows[wid]
            paths.add(relative)
            for node in workflow["nodes"]:
                if node["type"] == "n8n-nodes-base.webhook":
                    hooks.append(inspect_webhook(node)[2])
                if node["type"] != "n8n-nodes-base.executeWorkflow":
                    continue
                params = node.get("parameters")
                if not isinstance(params, dict):
                    raise Invalid()
                target = params.get("workflowId")
                target = target.get("value") if isinstance(target, dict) else target
                if not isinstance(target, str) or target.startswith("="):
                    codes.append("WORKFLOW_REFERENCE_UNRESOLVED")
                    continue
                visit(target)
            stack.remove(wid)

        visit(ENTRY)
        if paths != set(deps):
            codes.append("S1_DEPENDENCY_MISMATCH")
        if ENTRY not in workflows or not any(n["type"] == "n8n-nodes-base.webhook" for n in workflows[ENTRY][1]["nodes"]):
            codes.append("S1_WEBHOOK_MISSING")
        if "INVALID_WEBHOOK_PARAMETERS" in hooks:
            raise Invalid()
        report["summary"] = {"workflow_files": len(expected), "ticket_source_files": len(ticket),
            "s1_workflow_files": len(paths), "s1_webhooks": len(hooks),
            "auth_findings": sum(s != "DECLARED_UNVERIFIED" for s in hooks)}
        report["exit_code"] = 4 if codes else 0
    except (OSError, ValueError, UnicodeError, TypeError, RuntimeError, Invalid):
        codes.append("INVALID_OR_UNREADABLE_INPUT")
        report["exit_code"] = 2
    report["errors"] = sorted(set(codes))
    report["state"] = "SOURCE_MATCH_RUNTIME_PENDING" if report["exit_code"] == 0 else "SOURCE_CHECK_FAILED"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="explicit local capstone source root")
    parser.add_argument("--packet", default=PACKET, help="packet path relative to source root")
    args = parser.parse_args(argv)
    report = check(args.root, args.packet)
    print(json.dumps(report, indent=2))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
