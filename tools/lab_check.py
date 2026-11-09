"""Prepare cards, gather bounded file snapshots, compare and share scoped evidence.

No direct API, SSH, shell, attack, response or service operations are performed.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lab_checks.compare import compare
from tools.lab_checks.collectors import collect_file, load_profile
from tools.lab_checks.handoff import render_seat, report_documents, share, validate_comparison
from tools.lab_checks.models import LabError, ROOT, instant, placeholder, policy, read_json, validate_input, validate_receipt
from tools.lab_checks.runner import gather
from tools.lab_checks.store import publish, receipts_from_inbox, verified_document


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", default=str(ROOT / ".local/lab-check"), help="explicit local output root")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--card", required=True)
    prepare.add_argument("--out", required=True, help="new directory relative to run-root")
    collect = sub.add_parser("collect")
    comparison = sub.add_parser("compare")
    gathering = sub.add_parser("gather")
    for command in (collect, comparison, gathering):
        command.add_argument("--card", required=True, help="card.json inside a completed prepare bundle")
        command.add_argument("--phase", choices=("prepare", "final"), required=True)
        command.add_argument("--input")
        command.add_argument("--out", required=True, help="new directory relative to run-root")
    collect.add_argument("--seat", choices=list("ABCD"), required=True)
    collect.add_argument("--profile", help="local file-export/JSONL/filterlog profile; no commands or credentials")
    comparison.add_argument("--receipts", required=True, help="inbox of complete receipt bundle directories")
    comparison.add_argument("--at", help="fixture-only replay clock with an explicit UTC offset")
    gathering.add_argument("--plan", required=True, help="local profiles, maximum parallelism and per-collector deadline")
    gathering.add_argument("--at", help="fixture-only replay clock")
    gathering.add_argument("--share-root", help="explicit existing team storage location; no share is created/configured")
    gathering.add_argument("--share-out", help="new report directory relative to share-root")
    sharing = sub.add_parser("share")
    sharing.add_argument("--bundle", required=True)
    sharing.add_argument("--out", required=True, help="new shared report directory under run-root")
    status = sub.add_parser("status")
    status.add_argument("--bundle", required=True)
    status.add_argument("--seat", choices=list("ABCD"), required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            result = verified_document(args.bundle, "comparison.json")
            validate_comparison(result)
            print(render_seat(result, args.seat), end="")
            return 0  # Successful lookup, not a workflow success or completion status.
        if args.command == "share":
            output = share(args.bundle, args.run_root, args.out)
            code = 0
        elif args.command == "prepare":
            card = read_json(args.card)
            policy(card)
            output = publish(args.run_root, args.out, {"card.json": card})
            code = 0
        else:
            card_path = Path(args.card)
            if card_path.name != "card.json":
                raise LabError("Use card.json from a completed prepare bundle.")
            card = verified_document(card_path.parent, "card.json")
            selected = policy(card)
            input_data = read_json(args.input) if args.input else None
            if input_data is not None:
                validate_input(card, input_data)
            if args.command == "gather":
                if bool(args.share_root) != bool(args.share_out):
                    raise LabError("Provide both share-root and share-out, or neither.")
                if args.at and card["environment"] != "fixture":
                    raise LabError("Replay clock is allowed only for fixture cards.")
                output, result = gather(card, args.phase, input_data, args.plan, args.run_root, args.out,
                                        instant(args.at) if args.at else None)
                if args.share_root:
                    share(output, args.share_root, args.share_out)
                code = result["exit_code"]
            elif args.command == "collect":
                if args.seat not in {c["seat"] for c in selected["checks"]}:
                    raise LabError("Seat is outside this profile scope.")
                if args.phase == "final" and input_data is None:
                    raise LabError("Final collection requires input evidence; it never executes input.")
                now = datetime.now(timezone.utc)
                code = 0
                if args.profile:
                    profile = load_profile(args.profile)
                    try:
                        receipt, code = collect_file(card, args.seat, args.phase, profile)
                    except OSError:
                        receipt = placeholder(card, args.seat, args.phase, "SOURCE_UNAVAILABLE", now)
                        code = 3
                else:
                    receipt = placeholder(card, args.seat, args.phase, "NOT_CONFIGURED", now)
                    code = 3
                validate_receipt(card, receipt)
                if (receipt["seat"], receipt["phase"]) != (args.seat, args.phase):
                    raise LabError("Export has a different seat or phase.")
                if any(c["query_status"] in ("failed", "incomplete") or c["availability"] == "unknown" for c in receipt["checks"]):
                    code = 3
                output = publish(args.run_root, args.out, {"receipt.json": receipt})
            else:
                if args.at and card["environment"] != "fixture":
                    raise LabError("Replay clock is allowed only for fixture cards.")
                result = compare(card, receipts_from_inbox(args.receipts), args.phase, input_data,
                                 instant(args.at) if args.at else None)
                output = publish(args.run_root, args.out, report_documents(result))
                code = result["exit_code"]
        print(f"{args.command}: exit {code}; bundle written under the selected run-root.")
        return code
    except LabError as error:
        print(str(error), file=sys.stderr)
        return 2
    except OSError:
        print("Local file access failed; check configured paths and permissions.", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
