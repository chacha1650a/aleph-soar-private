"""Embed the reviewed pure JS node in an inactive n8n workflow; no n8n API calls."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "infra/n8n/guards/ticket-decision.js"
TARGET = ROOT / "infra/n8n/workflows/haedam-16-ticket-decision-offline.json"


def build():
    return [{
        "name": "haedam-16 티켓 응답 판단 (오프라인 후보, 대상 호출 없음)",
        "active": False,
        "nodes": [
            {"id": "ticket-input", "name": "Execute Workflow Trigger",
             "type": "n8n-nodes-base.executeWorkflowTrigger", "typeVersion": 1.1,
             "position": [0, 0], "parameters": {"inputSource": "passthrough"}},
            {"id": "ticket-decision", "name": "Validate ticket response and decide",
             "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [260, 0],
             "parameters": {"mode": "runOnceForAllItems", "jsCode": SOURCE.read_text(encoding="utf-8")}},
        ],
        "connections": {"Execute Workflow Trigger": {"main": [[{
            "node": "Validate ticket response and decide", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1"},
    }]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            parser.exit(1, "Ticket guard workflow is out of sync\n")
        print("Ticket guard workflow verified (inactive, no target/HTTP nodes)")
    else:
        TARGET.write_text(content, encoding="utf-8", newline="\n")
        print("Ticket guard workflow generated")


if __name__ == "__main__":
    main()
