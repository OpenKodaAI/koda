"""Tests for the MASTER_PLAN.md status lint (scripts/check_master_plan.py, M0-E1-T4)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_master_plan.py"

FENCE = "```"
STARTED_EARLY_FLAG = " (started early: real-path regression test required before done)"

# A small plan in the real layout: headed tasks, a group heading whose tasks are
# table rows, a non-task table that names IDs, and a heading inside a code fence.
PLAN = f"""# Master Plan

## 5. Decision and approval register

| Task | Clause | Ask | Main impact | Restore |
|---|---|---|---|---|
| M9-E9-T9 | §13: paid service | Not a task definition | — | — |

## 6. Backlog

### M0 — Baseline

#### M0-E1 — Gate truth

#### M0-E1-T1 · Finished task
Owner QA · Risk low · Gate none · **done** · Deps —
- **Done when:** it works.
- **Tests:** G · **Evidence:** VALIDATION_REPORT.md "M0-E1-T1"

#### M0-E1-T2 · Ready task
Owner QA · Risk low · Gate none · **ready** · Deps M0-E1-T1
- **Tests:** G · **Evidence:** —

#### M0-E1-T3 · Pending task
Owner QA · Risk low · Gate none · **pending** · Deps M0-E1-T2
- **Tests:** G · **Evidence:** —

#### M0-E1-T4 · Task started early
Owner QA · Risk med · Gate none · **in-progress**{STARTED_EARLY_FLAG} · Deps M0-E1-T3 · Active work: X
- **Tests:** G · **Evidence:** —

### M1 — Security

#### M1-E1-T1, M1-E1-T2 to M1-E1-T3 · One store each
Owner SEC · Risk high · Gate none · **pending** · Deps M0-E1-T1 (each row also depends on the row before it)
- **Tests (each task):** G · **Evidence:** — (one entry per task)

| Task | Store | Status | Deps |
|---|---|---|---|
| M1-E1-T1 | Tool policy | **ready** | — |
| M1-E1-T2 | Model policy | **pending** | M1-E1-T1 |
| M1-E1-T3 | Autonomy policy | **pending** | M1-E1-T2 |

#### M1-E1-T4 · Shorthand dependencies
Owner SEC · Risk low · Gate none · **pending** · Deps M0-E1-T1, T3; and the exit criteria of M0 (section 3)
- **Tests:** G · **Evidence:** —

## 7. Dependency graph

{FENCE}
#### M8-E8-T8 · a heading inside a code fence is not a task
{FENCE}
"""

REPORT = """# Validation Report

## M0-E1-T1 — finished task

| Command | Result |
|---|---|
| `pytest` | pass |
"""

CLEAN_COUNTS = """| Milestone | Tasks | ready / pending / blocked / in-progress / in-review / done |
|---|---:|---|
| M0 | 4 | 1 / 1 / 0 / 1 / 0 / 1 |
| M1 | 4 | 1 / 3 / 0 / 0 / 0 / 0 |
| Total | 8 | 2 / 4 / 0 / 1 / 0 / 1 |"""


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_master_plan", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def seed(old: str, new: str, plan: str = PLAN) -> str:
    assert plan.count(old) == 1, f"seed target must occur once: {old!r}"
    return plan.replace(old, new)


def problems_for(plan: str, report: str = REPORT) -> list[str]:
    _, problems = load_module().lint(plan, report)
    return list(problems)


def test_clean_plan_parses_headed_and_table_tasks() -> None:
    module = load_module()
    tasks, problems = module.lint(PLAN, REPORT)

    assert problems == []
    assert sorted(tasks) == [
        "M0-E1-T1",
        "M0-E1-T2",
        "M0-E1-T3",
        "M0-E1-T4",
        "M1-E1-T1",
        "M1-E1-T2",
        "M1-E1-T3",
        "M1-E1-T4",
    ]
    assert tasks["M0-E1-T4"].started_early is True
    # Table rows take the group heading's Deps plus their own.
    assert tasks["M1-E1-T3"].deps == ["M0-E1-T1", "M1-E1-T2"]
    assert tasks["M1-E1-T3"].status == "pending"
    # A bare "T3" inherits the milestone and epic of the previous full ID.
    assert tasks["M1-E1-T4"].deps == ["M0-E1-T1", "M0-E1-T3"]
    assert module.status_counts(tasks) == CLEAN_COUNTS


# The four violation classes of M0-E1-T4's "Do" list; the last one has two parts.
@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        pytest.param(
            '**Evidence:** VALIDATION_REPORT.md "M0-E1-T1"',
            "**Evidence:** —",
            "15: M0-E1-T1: is done but its Evidence field reads '—'",
            id="done-without-evidence",
        ),
        pytest.param(
            "**pending** · Deps M0-E1-T2",
            "**ready** · Deps M0-E1-T2",
            "24: M0-E1-T3: is ready but depends on unfinished M0-E1-T2 (ready)",
            id="ready-with-unfinished-dependency",
        ),
        pytest.param(
            f"**in-progress**{STARTED_EARLY_FLAG}",
            "**in-progress**",
            "28: M0-E1-T4: is in-progress with unfinished dependencies M0-E1-T3 (pending) "
            "but its status lacks the 'started early' flag",
            id="in-progress-early-without-flag",
        ),
        pytest.param(
            "**pending** · Deps M0-E1-T2",
            "**pending** · Deps M0-E1-T9",
            "24: M0-E1-T3: dependency M0-E1-T9 does not exist",
            id="unknown-dependency",
        ),
        pytest.param(
            "| M1-E1-T2 | Model policy | **pending** | M1-E1-T1 |",
            "| M1-E1-T2 | Model policy | **pending** | M1-E1-T1, M1-E1-T3 |",
            "dependency cycle M1-E1-T",
            id="dependency-cycle",
        ),
    ],
)
def test_each_seeded_violation_fails(old: str, new: str, expected: str) -> None:
    problems = problems_for(seed(old, new))

    assert len(problems) == 1, problems
    assert expected in problems[0]


def test_cycle_names_every_task_in_it() -> None:
    plan = seed("**pending** · Deps M0-E1-T2", "**pending** · Deps M0-E1-T2, M1-E1-T4")

    (problem,) = problems_for(plan)

    assert "dependency cycle" in problem
    assert "M0-E1-T3 -> M1-E1-T4 -> M0-E1-T3" in problem or "M1-E1-T4 -> M0-E1-T3 -> M1-E1-T4" in problem


def test_self_dependency_is_a_cycle() -> None:
    (problem,) = problems_for(seed("**pending** · Deps M0-E1-T2", "**pending** · Deps M0-E1-T3"))

    assert "dependency cycle M0-E1-T3 -> M0-E1-T3" in problem


def test_table_rows_are_checked_like_headed_tasks() -> None:
    ready_row = seed("| M1-E1-T2 | Model policy | **pending** |", "| M1-E1-T2 | Model policy | **ready** |")
    assert problems_for(ready_row) == ["41: M1-E1-T2: is ready but depends on unfinished M1-E1-T1 (ready)"]

    unknown_row = seed(
        "| M1-E1-T3 | Autonomy policy | **pending** | M1-E1-T2 |",
        "| M1-E1-T3 | Autonomy policy | **pending** | M1-E1-T7 |",
    )
    assert problems_for(unknown_row) == ["42: M1-E1-T3: dependency M1-E1-T7 does not exist"]


def test_table_row_done_needs_evidence_that_names_it() -> None:
    done_row = seed("| M1-E1-T1 | Tool policy | **ready** |", "| M1-E1-T1 | Tool policy | **done** |")
    assert problems_for(done_row) == ["40: M1-E1-T1: is done but its Evidence field reads '—'"]

    other_task_evidenced = seed(
        "**Evidence:** — (one entry per task)",
        '**Evidence:** M1-E1-T2: VALIDATION_REPORT.md "M1-E1-T2"; others —',
        done_row,
    )
    assert problems_for(other_task_evidenced) == ["40: M1-E1-T1: is done but its Evidence field reads '—'"]

    evidenced = seed(
        "**Evidence:** — (one entry per task)",
        '**Evidence:** M1-E1-T1: VALIDATION_REPORT.md "M1-E1-T1"; others —',
        done_row,
    )
    assert problems_for(evidenced) == []


def test_table_evidence_column_is_used_when_present() -> None:
    plan = seed(
        "| Task | Store | Status | Deps |\n|---|---|---|---|",
        "| Task | Store | Status | Deps | Evidence |\n|---|---|---|---|---|",
    )
    plan = seed("| M1-E1-T1 | Tool policy | **ready** | — |", "| M1-E1-T1 | Tool policy | **done** | — | — |", plan)
    assert problems_for(plan) == ["40: M1-E1-T1: is done but its Evidence field reads '—'"]

    plan = seed("| **done** | — | — |", '| **done** | — | VALIDATION_REPORT.md "M1-E1-T1" |', plan)
    assert problems_for(plan) == []


def test_evidence_dash_with_a_remark_is_still_missing() -> None:
    plan = seed('**Evidence:** VALIDATION_REPORT.md "M0-E1-T1"', "**Evidence:** — (CI run pending)")

    assert problems_for(plan) == ["15: M0-E1-T1: is done but its Evidence field reads '—'"]


def test_in_review_or_done_with_unfinished_dependency_needs_the_flag() -> None:
    in_review = seed(f"**in-progress**{STARTED_EARLY_FLAG}", "**in-review**")
    assert problems_for(in_review) == [
        "28: M0-E1-T4: is in-review with unfinished dependencies M0-E1-T3 (pending) "
        "but its status lacks the 'started early' flag"
    ]

    in_review_flagged = seed(f"**in-progress**{STARTED_EARLY_FLAG}", f"**in-review**{STARTED_EARLY_FLAG}")
    assert problems_for(in_review_flagged) == []


def test_done_after_starting_early_needs_a_regression_test_in_the_report() -> None:
    plan = seed(f"**in-progress**{STARTED_EARLY_FLAG}", f"**done**{STARTED_EARLY_FLAG}")
    plan = seed(
        "- **Tests:** G · **Evidence:** —\n\n### M1",
        '- **Tests:** G · **Evidence:** VALIDATION_REPORT.md "M0-E1-T4"\n\n### M1',
        plan,
    )
    missing = (
        "28: M0-E1-T4: is done and was started early, but no VALIDATION_REPORT.md section headed "
        "M0-E1-T4 names its real-path regression test by test ID ('<file>::<test>')"
    )

    assert problems_for(plan) == [missing]
    # A section for another task, or one that names no regression test, is not enough.
    assert problems_for(plan, REPORT + "\n## M0-E1-T40 — other\n\nReal-path regression test: `tests/test_x.py`\n") == [
        missing
    ]
    assert problems_for(plan, REPORT + "\n## M0-E1-T4 — started early\n\nUnit tests pass.\n") == [missing]

    report = REPORT + (
        "\n## M0-E1-T4 — started early\n\n### Tests\n\n"
        "Real-path regression test: `tests/test_x.py::test_real_path` (no patching of the code under test).\n"
    )
    assert problems_for(plan, report) == []

    # Dropping the flag instead is caught while the dependency is unfinished.
    unflagged = seed(f"**done**{STARTED_EARLY_FLAG}", "**done**", plan)
    assert problems_for(unflagged) == [
        "28: M0-E1-T4: is done with unfinished dependencies M0-E1-T3 (pending) "
        "but its status lacks the 'started early' flag"
    ]


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        pytest.param(
            "**pending** · Deps M0-E1-T2",
            "**redy** · Deps M0-E1-T2",
            "24: M0-E1-T3: unknown status **redy**",
            id="typo",
        ),
        pytest.param(
            "Owner QA · Risk low · Gate none · **pending** · Deps M0-E1-T2",
            "Owner QA · Risk low · Gate none · Deps M0-E1-T2",
            "24: M0-E1-T3: unknown status no **status**",
            id="no-status",
        ),
        pytest.param(
            "**pending** · Deps M0-E1-T2",
            "**pending**",
            "24: M0-E1-T3: status line has no 'Deps' field",
            id="no-deps-field",
        ),
        pytest.param(
            "#### M0-E1-T3 · Pending task",
            "#### M0-E1-T2 · Pending task",
            "24: M0-E1-T2: defined twice (first at line 20)",
            id="duplicate",
        ),
    ],
)
def test_malformed_tasks_are_reported(old: str, new: str, expected: str) -> None:
    problems = problems_for(seed(old, new))

    assert any(problem.startswith(expected) for problem in problems), problems


# A done task without evidence that nothing depends on: only the heading check can catch it.
HIDDEN_TASK = "Owner QA · Risk low · Gate none · **done** · Deps —\n- **Tests:** G · **Evidence:** —\n\n"


@pytest.mark.parametrize(
    "heading",
    [
        pytest.param("#### M0-E1-T9 — Hidden task", id="em-dash"),
        pytest.param("#### M0-E1-T9 – Hidden task", id="en-dash"),
        pytest.param("### M0-E1-T9 · Hidden task", id="level-3"),
        pytest.param("##### M0-E1-T9 · Hidden task", id="level-5"),
        pytest.param("#### M0-E1-T9 (was M7-E2-T1) · Hidden task", id="text-before-separator"),
        pytest.param("#### M0-E1-T9 to M0-E1-T7 · Hidden tasks", id="backwards-range"),
        pytest.param("#### M0-E1-T9 ·", id="no-title"),
    ],
)
def test_task_heading_in_another_form_is_reported(heading: str) -> None:
    plan = seed("## 7. Dependency graph", f"{heading}\n{HIDDEN_TASK}## 7. Dependency graph")
    line = plan.splitlines().index(heading) + 1

    tasks, problems = load_module().lint(plan, REPORT)

    assert problems == [
        f"{line}: heading starts with a task ID but is not '#### <ID> · Title' "
        f"or '#### <ID>, <ID> to <ID> · Title' (section 6): {heading!r}"
    ]
    assert "M0-E1-T9" not in tasks


def test_group_heading_names_exactly_its_table_rows() -> None:
    missing_row = seed("| M1-E1-T3 | Autonomy policy | **pending** | M1-E1-T2 |\n", "")
    assert problems_for(missing_row) == [
        "34: M1-E1-T1, M1-E1-T2 to M1-E1-T3: names M1-E1-T3, but no task table row under it defines it"
    ]

    extra_row = seed(
        "| M1-E1-T3 | Autonomy policy | **pending** | M1-E1-T2 |\n",
        "| M1-E1-T3 | Autonomy policy | **pending** | M1-E1-T2 |\n| M1-E1-T5 | Extra policy | **pending** | — |\n",
    )
    assert problems_for(extra_row) == ["43: M1-E1-T5: task table row is not named by its heading at line 34"]

    no_table = seed(
        "| Task | Store | Status | Deps |\n|---|---|---|---|\n"
        "| M1-E1-T1 | Tool policy | **ready** | — |\n"
        "| M1-E1-T2 | Model policy | **pending** | M1-E1-T1 |\n"
        "| M1-E1-T3 | Autonomy policy | **pending** | M1-E1-T2 |\n",
        "",
    )
    assert problems_for(no_table) == [
        f"34: M1-E1-T1, M1-E1-T2 to M1-E1-T3: names {task_id}, but no task table row under it defines it"
        for task_id in ("M1-E1-T1", "M1-E1-T2", "M1-E1-T3")
    ]

    # A range may end in a bare "T<n>" that continues the milestone and epic of its start.
    shorthand = seed("#### M1-E1-T1, M1-E1-T2 to M1-E1-T3 ·", "#### M1-E1-T1 to T3 ·")
    assert problems_for(shorthand) == []


def test_plan_without_tasks_fails(tmp_path: Path) -> None:
    no_tasks = ["1: no tasks found; expected '#### <ID> · Title' headings (section 6)"]
    assert problems_for("") == no_tasks
    assert problems_for(PLAN.split("## 6. Backlog")[0]) == no_tasks

    plan_path = tmp_path / "MASTER_PLAN.md"
    plan_path.write_text("", encoding="utf-8")
    assert load_module().main(["--plan", str(plan_path), "--report", str(tmp_path / "missing.md")]) == 1


# Section 6: Deps lists hard dependencies; a "coordinate with" note names tasks that only share files.
def test_coordinate_with_note_is_not_a_dependency() -> None:
    # The M1-E3-T8 pattern: a defect batch must merge first, and three tasks share its files.
    plan = seed(
        "**ready** · Deps M0-E1-T1",
        "**ready** · Deps DEFECT-BATCH-1 (D-003) merged; coordinate with M0-E1-T3, M0-E1-T4 and M1-E1-T2 (same files)",
    )

    tasks, problems = load_module().lint(plan, REPORT)

    assert problems == []
    assert tasks["M0-E1-T2"].deps == []
    assert tasks["M0-E1-T2"].coordinates == ["M0-E1-T3", "M0-E1-T4", "M1-E1-T2"]


def test_dependencies_after_a_coordinate_note_still_count() -> None:
    plan = seed(
        "**pending** · Deps M0-E1-T2",
        "**pending** · Deps M0-E1-T1; coordinate with M1-E1-T3, T2 (same files); M0-E1-T2",
    )

    tasks, problems = load_module().lint(plan, REPORT)

    assert problems == []
    assert tasks["M0-E1-T3"].deps == ["M0-E1-T1", "M0-E1-T2"]
    assert tasks["M0-E1-T3"].coordinates == ["M1-E1-T3", "M1-E1-T2"]

    still_hard = seed("**pending** · Deps M0-E1-T1;", "**ready** · Deps M0-E1-T1;", plan)
    assert problems_for(still_hard) == ["24: M0-E1-T3: is ready but depends on unfinished M0-E1-T2 (ready)"]


def test_coordinate_note_ids_must_exist() -> None:
    plan = seed("**ready** · Deps M0-E1-T1", "**ready** · Deps M0-E1-T1; coordinate with M0-E1-T9 (same files)")

    assert problems_for(plan) == ["20: M0-E1-T2: coordination note names M0-E1-T9, which does not exist"]


@pytest.mark.parametrize(
    "evidence",
    ["— pending", "—; CI run pending", "– pending", "- pending", "— (CI run pending)", "(CI run pending) —", ""],
)
def test_evidence_that_starts_with_a_dash_is_missing(evidence: str) -> None:
    plan = seed('**Evidence:** VALIDATION_REPORT.md "M0-E1-T1"', f"**Evidence:** {evidence}")

    assert problems_for(plan) == ["15: M0-E1-T1: is done but its Evidence field reads '—'"]


def test_group_evidence_counts_the_entry_that_names_the_row() -> None:
    done_row = seed("| M1-E1-T1 | Tool policy | **ready** |", "| M1-E1-T1 | Tool policy | **done** |")

    after_dash = seed(
        "**Evidence:** — (one entry per task)",
        '**Evidence:** — (one entry per task); M1-E1-T1: VALIDATION_REPORT.md "M1-E1-T1"',
        done_row,
    )
    assert problems_for(after_dash) == []

    labelled_dash = seed("**Evidence:** — (one entry per task)", "**Evidence:** M1-E1-T1: — (CI run pending)", done_row)
    assert problems_for(labelled_dash) == ["40: M1-E1-T1: is done but its Evidence field reads '—'"]


def test_started_early_regression_test_needs_a_test_id_in_a_section_headed_by_the_task() -> None:
    plan = seed(f"**in-progress**{STARTED_EARLY_FLAG}", f"**done**{STARTED_EARLY_FLAG}")
    plan = seed(
        "- **Tests:** G · **Evidence:** —\n\n### M1",
        '- **Tests:** G · **Evidence:** VALIDATION_REPORT.md "M0-E1-T4"\n\n### M1',
        plan,
    )
    missing = [
        "28: M0-E1-T4: is done and was started early, but no VALIDATION_REPORT.md section headed "
        "M0-E1-T4 names its real-path regression test by test ID ('<file>::<test>')"
    ]

    negative = "\n## M0-E1-T4 — x\n\nNo regression test was written; all mocked.\n"
    assert problems_for(plan, REPORT + negative) == missing
    # The test ID must be on the line that names the regression test.
    apart = "\n## M0-E1-T4 — x\n\nA regression test exists.\n\nUnit test: `tests/test_x.py::test_mocked`\n"
    assert problems_for(plan, REPORT + apart) == missing
    # Batch evidence counts only under a heading that names the task.
    batch = (
        "\n## DEFECT-BATCH-1 — batch\n\n| Task | Fix |\n|---|---|\n"
        "| M0-E1-T4 | Real-path regression test: `tests/test_x.py::test_real_path` |\n"
    )
    assert problems_for(plan, REPORT + batch) == missing

    batch_subsection = (
        "\n## DEFECT-BATCH-1 — batch\n\n### M0-E1-T4, M0-E1-T3 — real-path tests\n\n"
        "- Real-path regression test: `tests/test_x.py::test_real_path`\n"
    )
    assert problems_for(plan, REPORT + batch_subsection) == []


def test_cli_prints_counts_and_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    module = load_module()
    plan_path = tmp_path / "MASTER_PLAN.md"
    report_path = tmp_path / "VALIDATION_REPORT.md"
    plan_path.write_text(PLAN, encoding="utf-8")
    report_path.write_text(REPORT, encoding="utf-8")

    assert module.main(["--plan", str(plan_path), "--report", str(report_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith(CLEAN_COUNTS + "\n")
    assert "8 tasks checked" in captured.out
    assert captured.err == ""

    plan_path.write_text(seed('**Evidence:** VALIDATION_REPORT.md "M0-E1-T1"', "**Evidence:** —"), encoding="utf-8")
    assert module.main(["--plan", str(plan_path), "--report", str(report_path)]) == 1
    captured = capsys.readouterr()
    assert "| Total | 8 |" in captured.out
    assert "MASTER_PLAN.md:15: M0-E1-T1: is done but its Evidence field reads '—'" in captured.err


def test_repository_master_plan_passes(capsys: pytest.CaptureFixture[str]) -> None:
    module = load_module()

    assert module.main([]) == 0, capsys.readouterr().err

    tasks, _ = module.parse_plan(module.PLAN_PATH.read_text(encoding="utf-8"))
    # The policy-store tasks exist only as table rows under a group heading.
    assert {f"M5-E3-T{number}" for number in (5, 12, 13, 14, 15, 16, 17)} <= set(tasks)
    assert "M0-E1-T4" in tasks
