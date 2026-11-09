"""Bounded local collector subprocesses. No SSH, API or service execution."""

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time

from .collectors import load_profile
from .compare import compare
from .handoff import report_documents
from .models import LabError, ROOT, canonical, digest, placeholder, policy, read_json, validate, validate_input, validate_receipt
from .store import contained, publish, reserve, verified_document


def gather(card, phase, input_data, plan_path, root, out, now=None):
    selected = policy(card)
    if phase == "final" and input_data is None:
        raise LabError("Final gather requires existing input evidence; it never sends input.")
    if input_data is not None:
        validate_input(card, input_data)
    plan_path = Path(plan_path).absolute()
    plan = read_json(plan_path)
    validate("gather-plan", plan)
    jobs = {j["seat"]: j for j in plan["jobs"]}
    if len(jobs) != len(plan["jobs"]):
        raise LabError("Duplicate configured seat.")
    required = sorted({c["seat"] for c in selected["checks"]})
    work = reserve(root, out)
    frozen = publish(work, "card", {"card.json": card, **({"input.json": input_data} if input_data else {})})
    config = reserve(work, "config")
    ready, running, receipts, summaries = deque(), {}, {}, []
    peak = 0

    def finish(seat, status, exit_code, elapsed, profile_hash, receipt=None):
        reason = {"timeout": "COLLECTOR_TIMEOUT", "not_configured": "NOT_CONFIGURED"}.get(status, "COLLECTOR_FAILED")
        receipt = receipt or placeholder(card, seat, phase, reason, now or datetime.now(timezone.utc))
        validate_receipt(card, receipt)
        publish(work, f"receipts/{seat}", {"receipt.json": receipt})
        receipts[seat] = receipt
        summaries.append(dict(seat=seat, status=status, worker_exit_code=exit_code,
                              duration_seconds=round(elapsed, 6), profile_sha256=profile_hash))

    for seat in required:
        if seat not in jobs:
            finish(seat, "not_configured", None, 0, None)
            continue
        try:
            path = contained(plan_path.parent, jobs[seat]["profile"])
            profile = load_profile(path)
        except (LabError, OSError):
            finish(seat, "failed", None, 0, None)
            continue
        with (config / f"{seat}.json").open("xb") as stream:
            stream.write(canonical(profile) + b"\n")
        ready.append((seat, digest(profile)))

    try:
        while ready or running:
            while ready and len(running) < plan["max_workers"]:
                seat, profile_hash = ready.popleft()
                command = [sys.executable, str(ROOT / "tools/lab_check.py"), "--run-root", str(work), "collect",
                           "--card", str(frozen / "card.json"), "--seat", seat, "--phase", phase,
                           "--profile", str(config / f"{seat}.json"), "--out", f"attempts/{seat}"]
                if input_data is not None:
                    command += ["--input", str(frozen / "input.json")]
                started = time.monotonic()
                try:
                    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
                    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
                    running[seat] = (process, started, profile_hash)
                    peak = max(peak, len(running))
                except OSError:
                    finish(seat, "failed", None, 0, profile_hash)
            for seat, (process, started, profile_hash) in list(running.items()):
                elapsed = time.monotonic() - started
                code = process.poll()
                if code is None and elapsed < plan["timeout_seconds"]:
                    continue
                if code is None:
                    process.kill()
                    process.wait()
                    finish(seat, "timeout", process.returncode, elapsed, profile_hash)
                else:
                    try:
                        if code not in (0, 3):
                            raise LabError("Collector did not finish successfully.")
                        receipt = verified_document(work / f"attempts/{seat}", "receipt.json")
                        validate_receipt(card, receipt)
                        if (receipt["seat"], receipt["phase"]) != (seat, phase):
                            raise LabError("Collector identity mismatch.")
                        finish(seat, "collected" if code == 0 else "partial", code, elapsed, profile_hash, receipt)
                    except (LabError, OSError):
                        finish(seat, "failed", code, elapsed, profile_hash)
                del running[seat]
            if running:
                time.sleep(0.02)
    finally:
        for process, _started, _hash in running.values():
            if process.poll() is None:
                process.kill()
            process.wait()
    result = compare(card, list(receipts.values()), phase, input_data, now)
    result["collection_summary"] = dict(peak_workers=peak, jobs=sorted(summaries, key=lambda j: j["seat"]))
    bundle = publish(work, "result", report_documents(result))
    return bundle, result
