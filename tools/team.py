"""Validate the team task DAG, list ready tasks and render bounded handoff briefs.

This is a stateless planning tool, not an agent launcher or a shared status store.
"""

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
TRACKS = ("legacy", "integration")
SEATS = {"A", "B", "C", "D"}


def validate_relative_path(relative):
    pure = PurePosixPath(relative)
    if not relative.strip() or pure.is_absolute() or ".." in pure.parts or "\\" in relative or ":" in relative:
        raise ValueError(f"Unsafe task path: {relative}")


def load_plan(path=None, root=ROOT):
    path = path or root / "orchestration/workplan.json"
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("version") != 1 or not isinstance(plan.get("tasks"), list) or not plan["tasks"]:
        raise ValueError("Expected a version 1 plan with tasks.")
    tasks = {}
    for task in plan["tasks"]:
        if not isinstance(task, dict):
            raise ValueError("Each task must be an object.")
        task_id = task.get("id", "")
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Z][A-Z0-9]*", task_id) or task_id in tasks:
            raise ValueError(f"Invalid or duplicate task ID: {task_id}")
        role = task.get("role", "")
        if not isinstance(role, str) or not re.fullmatch(r"aleph-[a-z-]+", role) or not (root / "ai/roles" / f"{role}.md").is_file():
            raise ValueError(f"Unknown role for {task_id}: {role}")
        if not isinstance(task.get("title"), str) or not task["title"].strip():
            raise ValueError(f"Missing title for {task_id}.")
        for field in ("depends_on", "read", "write", "checks", "done_when"):
            values = task.get(field)
            if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
                raise ValueError(f"{task_id}.{field} must be a list of nonempty strings.")
            if field != "depends_on" and not values:
                raise ValueError(f"{task_id}.{field} cannot be empty.")
        for relative in task["read"] + task["write"]:
            validate_relative_path(relative)
        for relative in task["read"]:
            source = root / relative
            if not source.is_file() or not source.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"Missing or out-of-repository input: {relative}")
        if task.get("track", "legacy") not in TRACKS:
            raise ValueError(f"Unknown track for {task_id}.")
        for field in ("people", "handoff_to", "preconditions"):
            values = task.get(field, [])
            if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
                raise ValueError(f"{task_id}.{field} must be a list of nonempty strings.")
            if task.get("track") == "integration" and not values:
                raise ValueError(f"{task_id}.{field} is required for integration.")
            if field != "preconditions" and (not set(values) <= SEATS or len(set(values)) != len(values)):
                raise ValueError(f"{task_id}.{field} must contain unique human seats A~D.")
        refs = task.get("external_refs", [])
        if not isinstance(refs, list):
            raise ValueError(f"{task_id}.external_refs must be a list.")
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("repository"), str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", ref["repository"]
            ):
                raise ValueError(f"Invalid external repository for {task_id}.")
            if not isinstance(ref.get("path"), str) or not isinstance(ref.get("note"), str) or not ref["note"].strip():
                raise ValueError(f"External path and verification note required for {task_id}.")
            validate_relative_path(ref["path"])
        tasks[task_id] = task
    for task_id, task in tasks.items():
        if len(set(task["depends_on"])) != len(task["depends_on"]):
            raise ValueError(f"Duplicate dependency for {task_id}.")
        for dependency in task["depends_on"]:
            if dependency not in tasks:
                raise ValueError(f"Unknown dependency {dependency} for {task_id}.")

    visited, active = set(), set()

    def visit(task_id):
        if task_id in active:
            raise ValueError(f"Task dependency cycle at {task_id}.")
        if task_id in visited:
            return
        active.add(task_id)
        for dependency in tasks[task_id]["depends_on"]:
            visit(dependency)
        active.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id)
    return tasks


def validate_completed(tasks, completed):
    completed = set(completed)
    unknown = completed - tasks.keys()
    if unknown:
        raise ValueError("Unknown completed tasks: " + ", ".join(sorted(unknown)))
    for task_id in completed:
        missing = set(tasks[task_id]["depends_on"]) - completed
        if missing:
            raise ValueError(f"Completed task {task_id} is missing dependencies: {', '.join(sorted(missing))}")
    return completed


def ready_tasks(tasks, completed=(), role=None, track=None):
    completed = validate_completed(tasks, completed)
    if track is not None and track not in TRACKS:
        raise ValueError(f"Unknown track: {track}")
    return [task for task_id, task in tasks.items()
            if task_id not in completed and set(task["depends_on"]) <= completed
            and (role is None or task["role"] == role)
            and (track is None or task.get("track", "legacy") == track)]


def planning_sections(task):
    sections = [
        ("Human seats (not development roles)", task.get("people", [])),
        ("Declared preconditions (not verified by this tool)", task.get("preconditions", [])),
        ("Next human recipients", task.get("handoff_to", [])),
        ("External references (not opened or verified)", [
            f"{ref['repository']}:{ref['path']} — {ref['note']}" for ref in task.get("external_refs", [])
        ]),
    ]
    lines = []
    for heading, items in sections:
        if items:
            lines += ["", f"## {heading}"] + [f"- {item}" for item in items]
    return lines


def inspect_task(tasks, task_id, completed=()):
    """Show blockers without emitting an executable work brief or changing status."""
    completed = validate_completed(tasks, completed)
    if task_id not in tasks:
        raise ValueError(f"Unknown task: {task_id}")
    task = tasks[task_id]
    missing = sorted(set(task["depends_on"]) - completed)
    state = "supplied as completed; evidence not verified" if task_id in completed else (
        "blocked by: " + ", ".join(missing) if missing else "candidate; preconditions still require evidence"
    )
    lines = [f"# Inspect {task_id}: {task['title']}", f"Planning status: {state}",
             "This is a stateless lookup, not permission to run a measurement."]
    lines += planning_sections(task)
    independent = ready_tasks(tasks, completed, track=task.get("track", "legacy"))
    lines += ["", "## Other ready candidates (verify their conditions)"]
    lines += [f"- {other['id']} | {other['title']}" for other in independent if other['id'] != task_id]
    return "\n".join(lines) + "\n"


def render_brief(tasks, task_id, completed=()):
    completed = validate_completed(tasks, completed)
    if task_id not in tasks:
        raise ValueError(f"Unknown task: {task_id}")
    task = tasks[task_id]
    if task_id in completed:
        raise ValueError(f"Task {task_id} was already supplied as completed.")
    missing = set(task["depends_on"]) - completed
    if missing:
        raise ValueError(f"Task {task_id} is blocked by: {', '.join(sorted(missing))}")
    lines = [f"# {task_id}: {task['title']}", "", f"Role: {task['role']}",
             f"Track: {task.get('track', 'legacy')}",
             "Read AGENTS.md and the role definition below. Work only on this task.",
             "Completed IDs are supplied by the coordinator; verify their PR and evidence.",
             "A ready candidate does not verify live conditions or authorize equipment access."]
    lines += planning_sections(task)
    sections = [
        ("Read", ["AGENTS.md", f"ai/roles/{task['role']}.md"] + task["read"]),
        ("Owned write scope", task["write"]),
        ("Acceptance criteria", task["done_when"]),
        ("Relevant verification commands", task["checks"]),
    ]
    for heading, items in sections:
        lines += ["", f"## {heading}"] + [f"- {item}" for item in items]
    lines += ["", "Return the handoff in orchestration/handoff-template.md format.",
              "Do not claim unimplemented integrations or unexecuted checks are complete."]
    return "\n".join(lines) + "\n"


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "ready", "brief", "inspect"))
    parser.add_argument("task_id", nargs="?")
    parser.add_argument("--done", action="append", default=[], metavar="TASK_ID")
    parser.add_argument("--role")
    parser.add_argument("--track", choices=TRACKS, help="filter ready candidates; legacy = historical scaffold")
    args = parser.parse_args()
    try:
        tasks = load_plan()
        validate_completed(tasks, args.done)
        if args.role and args.role not in {task["role"] for task in tasks.values()}:
            raise ValueError(f"Unknown role: {args.role}")
        if args.command == "validate":
            print(f"Valid task DAG: {len(tasks)} tasks.")
        elif args.command == "ready":
            ready = ready_tasks(tasks, args.done, args.role, args.track)
            print("Ready candidates based on supplied completed IDs; not shared task status:")
            for task in ready:
                print(f"{task['id']} | {task['role']} | {task['title']} | track={task.get('track', 'legacy')}"
                      f" | people={','.join(task.get('people', [])) or 'not assigned'}")
                for condition in task.get("preconditions", []):
                    print(f"  Unverified condition: {condition}")
            if not ready:
                print("No ready tasks.")
        elif args.command in ("brief", "inspect"):
            if not args.task_id:
                raise ValueError(f"{args.command} requires a task ID.")
            if args.track and args.task_id in tasks and tasks[args.task_id].get("track", "legacy") != args.track:
                raise ValueError(f"Task {args.task_id} does not belong to track {args.track}.")
            renderer = render_brief if args.command == "brief" else inspect_task
            print(renderer(tasks, args.task_id, args.done), end="")
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
