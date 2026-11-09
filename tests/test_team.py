import json
import subprocess
import sys

import pytest

from tools import team


def test_brief_cli_preserves_utf8_and_resolves_project_from_other_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, str(team.ROOT / "tools/team.py"), "brief", "B01", "--done", "P01"],
        cwd=tmp_path, capture_output=True, encoding="utf-8", check=True,
    )
    assert team.load_plan()["B01"]["title"] in result.stdout
    assert "src/aleph_soar/portal/**" in result.stdout


def test_blocked_task_cli_returns_failure_without_a_work_brief():
    result = subprocess.run(
        [sys.executable, str(team.ROOT / "tools/team.py"), "brief", "B01"],
        capture_output=True, encoding="utf-8",
    )
    assert result.returncode != 0
    assert "blocked by: P01" in result.stderr
    assert result.stdout == ""


def test_ready_tasks_obey_integration_dependencies():
    tasks = team.load_plan()
    assert [task["id"] for task in team.ready_tasks(tasks, track="legacy")] == ["P01"]
    assert {task["id"] for task in team.ready_tasks(tasks, ["P01"], track="legacy")} == {"B01", "D01", "U01"}
    partial = ["P01", "B01", "D01"]
    assert "I01" not in {task["id"] for task in team.ready_tasks(tasks, partial, track="legacy")}
    assert [task["id"] for task in team.ready_tasks(tasks, partial + ["U01"], track="legacy")] == ["I01"]


def test_blocked_brief_and_inconsistent_completion_are_rejected():
    tasks = team.load_plan()
    with pytest.raises(ValueError, match="blocked"):
        team.render_brief(tasks, "B01")
    with pytest.raises(ValueError, match="missing dependencies"):
        team.ready_tasks(tasks, ["B01"])
    with pytest.raises(ValueError, match="Unknown"):
        team.ready_tasks(tasks, ["not-a-task"])
    brief = team.render_brief(tasks, "B01", ["P01"])
    assert "src/aleph_soar/portal/**" in brief
    assert "contracts/event.schema.json" in brief


@pytest.mark.parametrize("defect", ["cycle", "missing", "duplicate", "escape"])
def test_invalid_workplans_fail_validation(tmp_path, defect):
    plan = json.loads((team.ROOT / "orchestration/workplan.json").read_text(encoding="utf-8"))
    if defect == "cycle":
        plan["tasks"][0]["depends_on"] = ["I01"]
    elif defect == "missing":
        plan["tasks"][0]["depends_on"] = ["UNKNOWN"]
    elif defect == "duplicate":
        plan["tasks"].append(plan["tasks"][0])
    else:
        plan["tasks"][0]["write"] = ["../outside.py"]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError):
        team.load_plan(path)


def ids(tasks, completed=(), **filters):
    return {task["id"] for task in team.ready_tasks(tasks, completed, track="integration", **filters)}


def test_preparation_and_final_checks_are_parallel_without_legacy_completion():
    tasks = team.load_plan()
    assert ids(tasks) == {"T00"}
    preparation = {"T10A", "T10B", "T10C", "T10D"}
    assert ids(tasks, ["T00"]) == preparation
    # A's reply never blocks the other three preparation replies.
    assert ids(tasks, ["T00", "T10A"]) == preparation - {"T10A"}
    connected = ["T00", *sorted(preparation), "T20"]
    assert ids(tasks, connected) == {"T30"}
    supplied_input = connected + ["T30"]
    checks = {"T40A", "T40B", "T40C", "T40D"}
    assert ids(tasks, supplied_input) == checks
    assert ids(tasks, supplied_input + ["T40A"]) == checks - {"T40A"}
    assert ids(tasks, supplied_input + sorted(checks)) == {"T50"}
    assert ids(tasks, supplied_input + sorted(checks) + ["T50"]) == {"T60"}


def test_s10_pending_receipt_does_not_create_input_or_final_completion():
    tasks = team.load_plan()
    supplied_ready = ["T00", "T10A", "T10B", "T10C", "T10D"]
    assert ids(tasks, supplied_ready) == {"T20"}
    with pytest.raises(ValueError, match="blocked by: T20"):
        team.render_brief(tasks, "T30", supplied_ready)
    with pytest.raises(ValueError, match="missing dependencies"):
        team.ready_tasks(tasks, supplied_ready + ["T30"])
    lookup = team.inspect_task(tasks, "T20", supplied_ready)
    assert "not permission to run" in lookup
    assert "not verified by this tool" in lookup
    assert "ID25265/seq164" in lookup
    assert "자동 재송신 금지" in lookup
    # A blocked receiver leaves independent preparation work available.
    lookup = team.inspect_task(tasks, "T20", ["T00", "T10A"])
    assert "blocked by: T10B, T10C, T10D" in lookup
    assert "- T10B |" in lookup and "- T10C |" in lookup


def test_current_brief_exposes_seats_conditions_and_unverified_external_boundary():
    tasks = team.load_plan()
    brief = team.render_brief(tasks, "T10A", ["T00"])
    assert "Human seats (not development roles)\n- A" in brief
    assert "Next human recipients\n- D\n- B" in brief
    assert "haedam-portal-backend:src/haedam_portal/" in brief
    assert "not opened or verified" in brief
    assert "not verified by this tool" in brief
    # A seat filter must not be inferred from the technical role's name.
    assert ids(tasks, ["T00"], role="aleph-backend") == {"T10A"}


@pytest.mark.parametrize("command,arguments,expected", [
    ("ready", ["--track", "integration", "--done", "T00"], "T10D |"),
    ("inspect", ["T30"], "blocked by: T20"),
    ("inspect", ["T00", "--done", "T00"], "supplied as completed; evidence not verified"),
])
def test_new_cli_queries_preserve_utf8_and_do_not_write_status(tmp_path, command, arguments, expected):
    state = {name: (team.ROOT / name).read_bytes() for name in (
        "orchestration/workplan.json", "docs/PROGRESS.md",
    )}
    result = subprocess.run([sys.executable, str(team.ROOT / "tools/team.py"), command, *arguments],
                            cwd=tmp_path, capture_output=True, encoding="utf-8", check=True)
    assert expected in result.stdout
    assert not list(tmp_path.iterdir())
    assert all((team.ROOT / name).read_bytes() == content for name, content in state.items())


@pytest.mark.parametrize("defect", [
    "external-traversal", "external-absolute", "external-windows", "external-repository",
    "external-missing-note", "external-not-list", "local-external-path", "missing-conditions",
    "unknown-seat", "duplicate-seat", "unknown-track",
])
def test_external_references_do_not_weaken_local_path_or_metadata_validation(tmp_path, defect):
    plan = json.loads((team.ROOT / "orchestration/workplan.json").read_text(encoding="utf-8"))
    task = next(t for t in plan["tasks"] if t["id"] == "T10A")
    ref = task["external_refs"][0]
    if defect == "external-traversal":
        ref["path"] = "../outside.py"
    elif defect == "external-absolute":
        ref["path"] = "/outside.py"
    elif defect == "external-windows":
        ref["path"] = "C:/school/backend.py"
    elif defect == "external-repository":
        ref["repository"] = "../backend"
    elif defect == "external-missing-note":
        del ref["note"]
    elif defect == "external-not-list":
        task["external_refs"] = "NoBugs-Aleph/backend"
    elif defect == "local-external-path":
        task["read"].append("../haedam-portal-backend/app.py")
    elif defect == "missing-conditions":
        del task["preconditions"]
    elif defect == "unknown-seat":
        task["people"] = ["backend"]
    elif defect == "duplicate-seat":
        task["handoff_to"] = ["D", "D"]
    else:
        task["track"] = "live-status"
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError):
        team.load_plan(path)


def test_wrong_track_and_unsupported_completion_cli_fail_without_work_brief():
    for arguments in (["brief", "T10A", "--done", "T00", "--track", "legacy"],
                      ["brief", "T30", "--done", "T30"],
                      ["inspect", "UNKNOWN"], ["inspect"]):
        result = subprocess.run([sys.executable, str(team.ROOT / "tools/team.py"), *arguments],
                                capture_output=True, encoding="utf-8")
        assert result.returncode == 1
        assert result.stdout == ""
        assert result.stderr.strip()


def test_original_version_one_plan_without_new_metadata_remains_supported(tmp_path):
    plan = json.loads((team.ROOT / "orchestration/workplan.json").read_text(encoding="utf-8"))
    plan["tasks"] = [t for t in plan["tasks"] if t.get("track") == "legacy"]
    for task in plan["tasks"]:
        del task["track"]
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    tasks = team.load_plan(path)
    assert [task["id"] for task in team.ready_tasks(tasks)] == ["P01"]
    assert "src/aleph_soar/portal/**" in team.render_brief(tasks, "B01", ["P01"])
