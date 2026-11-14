#!/usr/bin/env python3
"""Lint the task statuses and dependencies in docs/engineering/MASTER_PLAN.md.

Every task is a ``#### M<m>-E<e>-T<t> · Title`` heading whose next line is the
status line (``Owner … · **status** · Deps …``), or a row of a table whose
header has ``Task`` and ``Status`` columns (plus optional ``Deps`` and
``Evidence`` columns). A table row under a group heading such as
``#### M5-E3-T5, M5-E3-T12 to M5-E3-T17 · …`` also takes the group's Deps, and
its evidence is the group's Evidence field only when that field names the row.

The lint fails when (MASTER_PLAN.md section 1, "Started early" and "Evidence
rule"):

- a task is ``done`` and its Evidence field reads "—";
- a task is ``ready`` and one of its dependencies is not ``done``;
- a task has started (``in-progress``, ``in-review`` or ``done``) with an
  unfinished dependency and its status lacks the *started early* flag;
- a ``done`` task carries the *started early* flag and no VALIDATION_REPORT.md
  section headed by its ID mentions a "regression test";
- a dependency names an ID that does not exist, or the dependency graph has a
  cycle;
- a task has no status line, an unknown status, or is defined twice.

It always prints the per-milestone status counts in the layout of section 3,
so that table can be refreshed from the output.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
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
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
TASK_HEADING_RE = re.compile(rf"^####\s+(?P<ids>{TASK_ID}[^·]*?)\s+·\s")
STATUS_RE = re.compile(r"\*\*([A-Za-z-]+)\*\*")
DEPS_FIELD_RE = re.compile(r"(?:^|·)\s*Deps\s+(?P<deps>.*?)\s*(?:·|$)")
EVIDENCE_FIELD_RE = re.compile(r"\*\*Evidence:\*\*\s*(?P<evidence>.*)$")
TABLE_SEPARATOR_RE = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+\s*$")
STARTED_EARLY_RE = re.compile(r"started early", re.IGNORECASE)
REGRESSION_TEST_RE = re.compile(r"regression test", re.IGNORECASE)
NO_EVIDENCE = frozenset({"", "—", "–", "-"})


@dataclass
class Task:
    task_id: str
    line: int
    status: str
    deps: list[str]
    started_early: bool
    evidence: str


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


def has_evidence(evidence: str) -> bool:
    """False when the field reads "—", ignoring remarks in parentheses."""
    return re.sub(r"\([^)]*\)", "", evidence).strip() not in NO_EVIDENCE


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
        deps=parse_dep_ids(deps_field.group("deps")) if deps_field else [],
        started_early=bool(STARTED_EARLY_RE.search(status_line)),
        evidence=evidence,
    )
    return task, deps_field is not None


def _row_task(cells: list[str], columns: dict[str, int], line: int, group: Task | None) -> Task:
    """A task table row; under a task heading it also takes that heading's Deps and, if named, Evidence."""
    task_id = _cell(cells, columns, "task")
    status = _cell(cells, columns, "status")
    deps = parse_dep_ids(_cell(cells, columns, "deps"))
    evidence = _cell(cells, columns, "evidence")
    if group is not None:
        deps = [dep for dep in group.deps if dep not in deps] + deps
        if "evidence" not in columns and re.search(rf"\b{re.escape(task_id)}\b", group.evidence):
            evidence = group.evidence
    return Task(
        task_id=task_id,
        line=line,
        status=_status(status),
        deps=deps,
        started_early=bool(STARTED_EARLY_RE.search(status)),
        evidence=evidence,
    )


def _add(tasks: dict[str, Task], errors: list[str], task: Task) -> None:
    if task.status not in STATUSES:
        shown = f"**{task.status}**" if task.status else "no **status**"
        errors.append(f"{task.line}: {task.task_id}: unknown status {shown}; expected one of {', '.join(STATUSES)}")
    if task.task_id in tasks:
        errors.append(f"{task.line}: {task.task_id}: defined twice (first at line {tasks[task.task_id].line})")
        return
    tasks[task.task_id] = task


def parse_plan(text: str) -> tuple[dict[str, Task], list[str]]:
    """Return the tasks by ID and the parse errors, each prefixed with its line."""
    lines = text.splitlines()
    tasks: dict[str, Task] = {}
    errors: list[str] = []
    group: Task | None = None  # the task heading above the current line
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

        if HEADING_RE.match(line):
            group = None
            if heading := TASK_HEADING_RE.match(line):
                group, has_deps = _heading_task(lines, index, heading.group("ids"))
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
            if TASK_ID_FULL_RE.fullmatch(row.task_id):
                _add(tasks, errors, row)
            else:
                errors.append(f"{row.line}: task table row does not start with one task ID: {row.task_id!r}")
    return tasks, errors


def report_mentions_regression_test(report_text: str, task_id: str) -> bool:
    """True when a VALIDATION_REPORT.md section headed by ``task_id`` mentions a regression test."""
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
        if REGRESSION_TEST_RE.search("\n".join(section)):
            return True
    return False


def check_tasks(tasks: dict[str, Task], report_text: str) -> list[str]:
    """Return the rule violations, each prefixed with the task's line."""
    violations: list[str] = []
    for task in sorted(tasks.values(), key=lambda item: item.line):
        where = f"{task.line}: {task.task_id}"
        unknown = [dep for dep in task.deps if dep not in tasks]
        for dep in unknown:
            violations.append(f"{where}: dependency {dep} does not exist")
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
        if (
            task.status == "done"
            and task.started_early
            and not report_mentions_regression_test(report_text, task.task_id)
        ):
            violations.append(
                f"{where}: is done and was started early, but no VALIDATION_REPORT.md section headed "
                f"{task.task_id} names its real-path regression test"
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
