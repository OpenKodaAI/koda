#!/usr/bin/env python3
"""Lint the task statuses and dependencies in docs/engineering/MASTER_PLAN.md.

The task format is MASTER_PLAN.md section 6. Every task is a
``#### M<m>-E<e>-T<t> · Title`` heading whose next line is the status line
(``Owner … · **status** · Deps …``), or a row of a table whose header has
``Task`` and ``Status`` columns (plus optional ``Deps`` and ``Evidence``
columns). Such a table sits under a group heading that names exactly its rows,
for example ``#### M5-E3-T5, M5-E3-T12 to M5-E3-T17 · …``. Each row also takes
the group's Deps, and its evidence is the ``<ID>: …`` entry of the group's
Evidence field that names it, unless the table has an Evidence column.

Every task ID in a Deps field is a hard dependency, except in a
``coordinate with …`` note, which runs to the next ``;`` or the end of the
field and names tasks that only share files.

The lint fails when (MASTER_PLAN.md section 1, "Started early" and "Evidence
rule"):

- a task is ``done`` and its Evidence field reads "—" (or starts with a dash);
- a task is ``ready`` and one of its dependencies is not ``done``;
- a task has started (``in-progress``, ``in-review`` or ``done``) with an
  unfinished dependency and its status lacks the *started early* flag;
- a ``done`` task carries the *started early* flag and no VALIDATION_REPORT.md
  section whose heading names its ID has a line naming a "regression test" by
  test ID (``<file>::<test>``);
- a dependency or a coordination note names an ID that does not exist, or the
  dependency graph has a cycle;
- a task has no status line, an unknown status, or is defined twice;
- a heading starts with a task ID but is in neither heading form, or a group
  heading and the rows of its table do not name the same tasks;
- the plan defines no task at all.

It always prints the per-milestone status counts in the layout of section 3,
so that table can be refreshed from the output.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "docs" / "engineering" / "MASTER_PLAN.md"
REPORT_PATH = ROOT / "docs" / "engineering" / "VALIDATION_REPORT.md"

STATUSES = ("ready", "pending", "blocked", "in-progress", "in-review", "done")
STARTED_STATUSES = frozenset({"in-progress", "in-review", "done"})

TASK_ID = r"M\d+-E\d+-T\d+"
TASK_ID_FULL_RE = re.compile(TASK_ID)
# A full ID, or a bare "T14" that inherits the milestone and epic of the
# previous full ID ("M1-E1-T13, T14, T15").
DEP_TOKEN_RE = re.compile(r"\b(?:(M\d+-E\d+)-)?T(\d+)\b")
# Section 6: a note naming tasks that only share files; not a dependency.
COORDINATE_NOTE_RE = re.compile(r"\bcoordinate with\b[^;]*", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
TASK_ID_START_RE = re.compile(rf"{TASK_ID}\b")
TASK_HEADING_RE = re.compile(rf"^####\s+(?P<ids>{TASK_ID}[^·]*?)\s+·\s+\S")
# One item of a group heading: an ID, or a range "M5-E3-T12 to M5-E3-T17" / "M5-E3-T12 to T17".
GROUP_ITEM_RE = re.compile(
    r"(?P<prefix>M\d+-E\d+)-T(?P<first>\d+)(?:\s+to\s+(?:(?P<end_prefix>M\d+-E\d+)-)?T(?P<last>\d+))?"
)
STATUS_RE = re.compile(r"\*\*([A-Za-z-]+)\*\*")
DEPS_FIELD_RE = re.compile(r"(?:^|·)\s*Deps\s+(?P<deps>.*?)\s*(?:·|$)")
EVIDENCE_FIELD_RE = re.compile(r"\*\*Evidence:\*\*\s*(?P<evidence>.*)$")
TABLE_SEPARATOR_RE = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+\s*$")
STARTED_EARLY_RE = re.compile(r"started early", re.IGNORECASE)
REGRESSION_TEST_RE = re.compile(r"regression test", re.IGNORECASE)
# A test ID such as tests/test_queue.py::test_cancel or apps/web/src/x.test.ts::renders.
TEST_ID_RE = re.compile(r"[\w./-]+\.\w+::\w")
MISSING_EVIDENCE_RE = re.compile(r"\s*(?:[—–-]|$)")

HEADING_FORM = "'#### <ID> · Title' or '#### <ID>, <ID> to <ID> · Title' (section 6)"


@dataclass
class Task:
    task_id: str
    line: int
    status: str
    deps: list[str]
    started_early: bool
    evidence: str
    coordinates: list[str] = field(default_factory=list)


def parse_dep_ids(text: str) -> list[str]:
    ids: list[str] = []
    prefix: str | None = None
    for match in DEP_TOKEN_RE.finditer(text):
        if match.group(1):
            prefix = match.group(1)
        elif prefix is None:
            continue
        task_id = f"{prefix}-T{match.group(2)}"
        if task_id not in ids:
            ids.append(task_id)
    return ids


def split_deps(text: str) -> tuple[list[str], list[str]]:
    """The hard dependencies of a Deps field, and the IDs its "coordinate with" notes name."""
    notes = " ; ".join(COORDINATE_NOTE_RE.findall(text))
    return parse_dep_ids(COORDINATE_NOTE_RE.sub(";", text)), parse_dep_ids(notes)


def group_ids(text: str) -> list[str] | None:
    """The IDs a task heading names ("M5-E3-T5, M5-E3-T12 to M5-E3-T17"), or None when it is not such a list."""
    ids: list[str] = []
    for item in re.split(r"\s*,\s*", text.strip()):
        match = GROUP_ITEM_RE.fullmatch(item)
        if match is None:
            return None
        prefix, first = match.group("prefix"), int(match.group("first"))
        last = int(match.group("last") or first)
        if match.group("end_prefix") not in (None, prefix) or last < first:
            return None
        ids.extend(f"{prefix}-T{number}" for number in range(first, last + 1))
    return ids


def has_evidence(evidence: str) -> bool:
    """False when the field, without remarks in parentheses, is empty or starts with a dash ("—", "— pending")."""
    return MISSING_EVIDENCE_RE.match(re.sub(r"\([^)]*\)", "", evidence)) is None


def group_row_evidence(group_evidence: str, task_id: str) -> str:
    """The ``;``-separated entries of a group's Evidence field that name ``task_id``, without their ``<ID>:`` label."""
    id_re = re.compile(rf"\b{re.escape(task_id)}\b")
    label_re = re.compile(rf"^{re.escape(task_id)}\s*:\s*")
    entries = [label_re.sub("", entry.strip()) for entry in group_evidence.split(";") if id_re.search(entry)]
    return "; ".join(entries)


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _cell(cells: list[str], columns: dict[str, int], name: str) -> str:
    position = columns.get(name)
    return cells[position] if position is not None and position < len(cells) else ""


def _status(text: str) -> str:
    match = STATUS_RE.search(text)
    return match.group(1) if match else ""


def _heading_task(lines: list[str], index: int, ids: str) -> tuple[Task, bool]:
    """The task (or the group of table tasks) a heading defines, and whether its status line has Deps."""
    status_line = next((line for line in lines[index + 1 :] if line.strip()), "")
    deps_field = DEPS_FIELD_RE.search(status_line)
    deps, coordinates = split_deps(deps_field.group("deps")) if deps_field else ([], [])
    evidence = ""
    for line in lines[index + 1 :]:
        if HEADING_RE.match(line):
            break
        if match := EVIDENCE_FIELD_RE.search(line):
            evidence = match.group("evidence").strip()
            break
    task = Task(
        task_id=ids,
        line=index + 1,
        status=_status(status_line),
        deps=deps,
        started_early=bool(STARTED_EARLY_RE.search(status_line)),
        evidence=evidence,
        coordinates=coordinates,
    )
    return task, deps_field is not None


def _row_task(cells: list[str], columns: dict[str, int], line: int, group: Task | None) -> Task:
    """A task table row; under a task heading it also takes that heading's Deps and, if named, Evidence."""
    task_id = _cell(cells, columns, "task")
    status = _cell(cells, columns, "status")
    deps, coordinates = split_deps(_cell(cells, columns, "deps"))
    evidence = _cell(cells, columns, "evidence")
    if group is not None:
        deps = [dep for dep in group.deps if dep not in deps] + deps
        coordinates = [dep for dep in group.coordinates if dep not in coordinates] + coordinates
        if "evidence" not in columns:
            evidence = group_row_evidence(group.evidence, task_id)
    return Task(
        task_id=task_id,
        line=line,
        status=_status(status),
        deps=deps,
        started_early=bool(STARTED_EARLY_RE.search(status)),
        evidence=evidence,
        coordinates=coordinates,
    )


def _add(tasks: dict[str, Task], errors: list[str], task: Task) -> None:
    if task.status not in STATUSES:
        shown = f"**{task.status}**" if task.status else "no **status**"
        errors.append(f"{task.line}: {task.task_id}: unknown status {shown}; expected one of {', '.join(STATUSES)}")
    if task.task_id in tasks:
        errors.append(f"{task.line}: {task.task_id}: defined twice (first at line {tasks[task.task_id].line})")
        return
    tasks[task.task_id] = task


def _check_group_rows(group: Task | None, named: list[str], rows: list[str], errors: list[str]) -> None:
    """A group heading names exactly the rows of its task table."""
    if group is None or TASK_ID_FULL_RE.fullmatch(group.task_id):
        return
    for task_id in named:
        if task_id not in rows:
            errors.append(f"{group.line}: {group.task_id}: names {task_id}, but no task table row under it defines it")


def parse_plan(text: str) -> tuple[dict[str, Task], list[str]]:
    """Return the tasks by ID and the parse errors, each prefixed with its line."""
    lines = text.splitlines()
    tasks: dict[str, Task] = {}
    errors: list[str] = []
    group: Task | None = None  # the task heading above the current line
    named: list[str] = []  # the IDs that heading names
    rows: list[str] = []  # the task table rows under it
    columns: dict[str, int] | None = None  # column positions of the open task table
    in_fence = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.startswith("|"):
            columns = None

        if heading := HEADING_RE.match(line):
            _check_group_rows(group, named, rows, errors)
            group, named, rows = None, [], []
            if not TASK_ID_START_RE.match(heading.group(2)):
                continue
            task_heading = TASK_HEADING_RE.match(line)
            ids = group_ids(task_heading.group("ids")) if task_heading else None
            if task_heading is None or ids is None:
                errors.append(f"{index + 1}: heading starts with a task ID but is not {HEADING_FORM}: {line.strip()!r}")
                continue
            group, has_deps = _heading_task(lines, index, task_heading.group("ids"))
            named = ids
            if TASK_ID_FULL_RE.fullmatch(group.task_id):
                if not has_deps:
                    errors.append(f"{group.line}: {group.task_id}: status line has no 'Deps' field")
                _add(tasks, errors, group)
        elif line.startswith("|") and index + 1 < len(lines) and TABLE_SEPARATOR_RE.match(lines[index + 1]):
            header = [cell.lower() for cell in _cells(line)]
            columns = {name: position for position, name in enumerate(header)}
            if not {"task", "status"} <= columns.keys():
                columns = None
        elif columns is not None and not TABLE_SEPARATOR_RE.match(line):
            row = _row_task(_cells(line), columns, index + 1, group)
            if not TASK_ID_FULL_RE.fullmatch(row.task_id):
                errors.append(f"{row.line}: task table row does not start with one task ID: {row.task_id!r}")
                continue
            if group is not None and row.task_id not in named:
                errors.append(
                    f"{row.line}: {row.task_id}: task table row is not named by its heading at line {group.line}"
                )
            rows.append(row.task_id)
            _add(tasks, errors, row)
    _check_group_rows(group, named, rows, errors)
    if not tasks:
        errors.append("1: no tasks found; expected '#### <ID> · Title' headings (section 6)")
    return tasks, errors


def report_names_regression_test(report_text: str, task_id: str) -> bool:
    """True when a VALIDATION_REPORT.md section whose heading names ``task_id`` names a regression test by test ID.

    The words "regression test" and the test ID (``<file>::<test>``) must share a line, so a remark such as
    "No regression test was written" does not count (MASTER_PLAN.md section 1, "Started early").
    """
    lines = report_text.splitlines()
    id_re = re.compile(rf"\b{re.escape(task_id)}\b")
    for start, line in enumerate(lines):
        heading = HEADING_RE.match(line)
        if not heading or not id_re.search(heading.group(2)):
            continue
        level = len(heading.group(1))
        section = [line]
        for body_line in lines[start + 1 :]:
            nested = HEADING_RE.match(body_line)
            if nested and len(nested.group(1)) <= level:
                break
            section.append(body_line)
        if any(REGRESSION_TEST_RE.search(entry) and TEST_ID_RE.search(entry) for entry in section):
            return True
    return False


def check_tasks(tasks: dict[str, Task], report_text: str) -> list[str]:
    """Return the rule violations, each prefixed with the task's line."""
    violations: list[str] = []
    for task in sorted(tasks.values(), key=lambda item: item.line):
        where = f"{task.line}: {task.task_id}"
        for dep in task.deps:
            if dep not in tasks:
                violations.append(f"{where}: dependency {dep} does not exist")
        for other in task.coordinates:
            if other not in tasks:
                violations.append(f"{where}: coordination note names {other}, which does not exist")
        unfinished = [dep for dep in task.deps if dep in tasks and tasks[dep].status != "done"]
        unfinished_text = ", ".join(f"{dep} ({tasks[dep].status})" for dep in unfinished)

        if task.status == "done" and not has_evidence(task.evidence):
            violations.append(f"{where}: is done but its Evidence field reads '—'")
        if task.status == "ready" and unfinished:
            violations.append(f"{where}: is ready but depends on unfinished {unfinished_text}")
        if task.status in STARTED_STATUSES and unfinished and not task.started_early:
            violations.append(
                f"{where}: is {task.status} with unfinished dependencies {unfinished_text} "
                "but its status lacks the 'started early' flag"
            )
        if task.status == "done" and task.started_early and not report_names_regression_test(report_text, task.task_id):
            violations.append(
                f"{where}: is done and was started early, but no VALIDATION_REPORT.md section headed "
                f"{task.task_id} names its real-path regression test by test ID ('<file>::<test>')"
            )

    graph = {task_id: [dep for dep in task.deps if dep in tasks] for task_id, task in tasks.items()}
    try:
        TopologicalSorter(graph).prepare()
    except CycleError as error:
        # graphlib lists the cycle in landing order; print it in "depends on" order.
        cycle = list(reversed(error.args[1]))
        violations.append(
            f"{tasks[cycle[0]].line}: {cycle[0]}: dependency cycle {' -> '.join(cycle)} (each task depends on the next)"
        )
    return violations


def status_counts(tasks: dict[str, Task]) -> str:
    """Per-milestone status counts in the column layout of MASTER_PLAN.md section 3."""
    milestones = sorted({task_id.split("-", 1)[0] for task_id in tasks}, key=lambda name: int(name[1:]))
    rows = [
        "| Milestone | Tasks | " + " / ".join(STATUSES) + " |",
        "|---|---:|---|",
    ]

    def row(name: str, members: list[Task]) -> str:
        counts = " / ".join(str(sum(task.status == status for task in members)) for status in STATUSES)
        return f"| {name} | {len(members)} | {counts} |"

    for milestone in milestones:
        rows.append(row(milestone, [task for task in tasks.values() if task.task_id.startswith(f"{milestone}-")]))
    rows.append(row("Total", list(tasks.values())))
    return "\n".join(rows)


def lint(plan_text: str, report_text: str) -> tuple[dict[str, Task], list[str]]:
    tasks, errors = parse_plan(plan_text)
    return tasks, errors + check_tasks(tasks, report_text)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", type=Path, default=PLAN_PATH, help="master plan to lint")
    parser.add_argument("--report", type=Path, default=REPORT_PATH, help="validation report with task evidence")
    args = parser.parse_args(argv)

    report_text = args.report.read_text(encoding="utf-8") if args.report.exists() else ""
    tasks, problems = lint(args.plan.read_text(encoding="utf-8"), report_text)
    print(status_counts(tasks))
    if problems:
        print(f"\n{len(problems)} problem(s) in {args.plan}:", file=sys.stderr)
        for problem in problems:
            print(f"  {args.plan.name}:{problem}", file=sys.stderr)
        return 1
    print(f"\n{len(tasks)} tasks checked: statuses, evidence and dependencies are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
