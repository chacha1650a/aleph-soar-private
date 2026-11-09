"""Read-only audit of Webhook auth declarations in local n8n JSON exports.

No network, credential lookup, workflow execution or export changes. Output uses
file/workflow/node ordinals and input hashes, never names, paths or raw values.
Exit 0 = declarations present (runtime unverified); 1 = auth findings;
2 = incomplete/invalid input or inventory mismatch.
"""
import argparse
import hashlib
import json
from pathlib import Path

DEFAULT_FOLDER = Path(__file__).resolve().parents[1] / "infra/n8n/workflows"
WEBHOOK = "n8n-nodes-base.webhook"
CREDENTIALS = {"basicAuth": "httpBasicAuth", "headerAuth": "httpHeaderAuth", "jwtAuth": "jwtAuth"}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("non-JSON constant")


def _reference(value):
    # A name alone is not proof that an imported credential resolved to an ID.
    return (isinstance(value, dict) and isinstance(value.get("id"), str)
            and bool(value["id"].strip()) and not value["id"].startswith("="))


def inspect_webhook(node):
    """Return allowlisted auth metadata only; never echo node or credential values."""
    params = node.get("parameters")
    if not isinstance(params, dict):
        return "invalid", False, "INVALID_WEBHOOK_PARAMETERS"
    auth = params.get("authentication")
    if auth is None or auth == "none" or auth == "":
        return "none", False, "AUTH_NOT_CONFIGURED"
    if not isinstance(auth, str) or auth not in CREDENTIALS:
        return "unsupported", False, "AUTH_REQUIRES_REVIEW"
    credentials = node.get("credentials")
    ref = credentials.get(CREDENTIALS[auth]) if isinstance(credentials, dict) else None
    present = _reference(ref)
    return auth, present, "DECLARED_UNVERIFIED" if present else "CREDENTIAL_REFERENCE_UNRESOLVED"


def audit(folder, expected_webhooks=None):
    report = {"schema_version": "1.0", "scope": "local_exports_only",
              "runtime_verified": False, "files": [], "webhooks": [], "errors": []}
    try:
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".json" and p.is_file())
    except OSError:
        files = []
        report["errors"].append({"code": "INPUT_UNREADABLE"})
    if not files:
        report["errors"].append({"code": "NO_EXPORTS"})
    for file_index, source in enumerate(files, 1):
        entry = {"file_index": file_index}
        report["files"].append(entry)
        try:
            raw = source.read_bytes()
            entry["sha256"] = hashlib.sha256(raw).hexdigest()
            payload = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                                 parse_constant=_invalid_constant)
        except (OSError, UnicodeError, ValueError):
            report["errors"].append({"file_index": file_index, "code": "INVALID_EXPORT"})
            continue
        workflows = payload if isinstance(payload, list) else [payload]
        if not workflows:
            report["errors"].append({"file_index": file_index, "code": "EMPTY_EXPORT"})
        for workflow_index, workflow in enumerate(workflows, 1):
            location = {"file_index": file_index, "workflow_index": workflow_index}
            if not isinstance(workflow, dict) or not isinstance(workflow.get("nodes"), list) or not workflow["nodes"]:
                report["errors"].append({**location, "code": "INVALID_WORKFLOW"})
                continue
            active = workflow.get("active")
            active = active if isinstance(active, bool) else "unknown"
            for node_index, node in enumerate(workflow["nodes"], 1):
                node_location = {**location, "node_index": node_index}
                if not isinstance(node, dict) or not isinstance(node.get("type"), str):
                    report["errors"].append({**node_location, "code": "INVALID_NODE"})
                    continue
                if node["type"] != WEBHOOK:
                    continue
                auth, reference, status = inspect_webhook(node)
                report["webhooks"].append({**node_location, "workflow_active": active,
                    "node_disabled": node.get("disabled") is True, "authentication": auth,
                    "credential_reference_present": reference, "status": status})
                if status == "INVALID_WEBHOOK_PARAMETERS":
                    report["errors"].append({**node_location, "code": status})
    hooks = report["webhooks"]
    if not hooks:
        report["errors"].append({"code": "NO_WEBHOOKS"})
    if expected_webhooks is not None and len(hooks) != expected_webhooks:
        report["errors"].append({"code": "WEBHOOK_COUNT_MISMATCH"})
    declared = sum(h["status"] == "DECLARED_UNVERIFIED" for h in hooks)
    report["summary"] = {"files": len(files), "webhooks": len(hooks),
                         "declared_unverified": declared, "auth_findings": len(hooks) - declared,
                         "input_errors": len(report["errors"])}
    report["exit_code"] = 2 if report["errors"] else 1 if len(hooks) != declared else 0
    return report


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("expected webhook count must be positive")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=DEFAULT_FOLDER,
                        help="local folder containing workflow JSON exports (nonrecursive)")
    parser.add_argument("--expected-webhooks", type=positive_int,
                        help="fail incomplete inventory when the count differs")
    args = parser.parse_args(argv)
    report = audit(args.folder, args.expected_webhooks)
    print(json.dumps(report, indent=2))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
