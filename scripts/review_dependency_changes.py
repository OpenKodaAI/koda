#!/usr/bin/env python3
"""Review dependency manifest changes in a pull request without GitHub feature flags."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NODE_MANIFESTS = (
    Path("package.json"),
    Path("apps/web/package.json"),
    Path("packages/cli/package.json"),
)
PYTHON_MANIFEST = Path("pyproject.toml")
PYTHON_LOCKFILE = Path("uv.lock")
NODE_LOCKFILE = Path("pnpm-lock.yaml")
CARGO_LOCKFILE = Path("rust/Cargo.lock")
DEPENDENCY_REVIEW_SUMMARY = "## Dependency review\n"
NODE_DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
BLOCKED_NODE_PREFIXES = (
    "file:",
    "git+",
    "git:",
    "github:",
    "http:",
    "https:",
    "link:",
)
BLOCKED_PYTHON_REFERENCE_TOKENS = (
    " @ file://",
    " @ git+",
    " @ http://",
    " @ https://",
    " @ ssh://",
)


class DependencyReviewError(RuntimeError):
    """Raised when a dependency policy violation is detected."""


@dataclass(frozen=True)
class PythonSnapshot:
    dependency_entries: tuple[str, ...]
    optional_entries: tuple[tuple[str, tuple[str, ...]], ...]
    dependency_groups: tuple[tuple[str, tuple[str, ...]], ...]
    uv_sources: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class NodeSnapshot:
    sections: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]


@dataclass(frozen=True)
class CargoSnapshot:
    entries: tuple[tuple[str, str, str], ...]


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DependencyReviewError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def read_file_at_ref(ref: str, path: Path) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path.as_posix()}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def normalize_table_of_lists(value: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not isinstance(value, Mapping):
        return ()
    normalized: list[tuple[str, tuple[str, ...]]] = []
    for key in sorted(value):
        items = value[key]
        if not isinstance(items, list):
            continue
        normalized.append((str(key), tuple(sorted(str(item) for item in items))))
    return tuple(normalized)


def normalize_uv_sources(value: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Mapping):
        return ()
    normalized: list[tuple[str, str]] = []
    for key in sorted(value):
        normalized.append((str(key), json.dumps(value[key], sort_keys=True, separators=(",", ":"))))
    return tuple(normalized)


def parse_python_snapshot(text: str | None) -> PythonSnapshot:
    if not text:
        return PythonSnapshot((), (), (), ())
    payload = tomllib.loads(text)
    project = payload.get("project", {})
    tool = payload.get("tool", {})
    uv_sources = {}
    if isinstance(tool, Mapping):
        uv = tool.get("uv", {})
        if isinstance(uv, Mapping):
            uv_sources = uv.get("sources", {})

    return PythonSnapshot(
        dependency_entries=tuple(
            sorted(str(item) for item in project.get("dependencies", []) if isinstance(item, str))
        ),
        optional_entries=normalize_table_of_lists(project.get("optional-dependencies", {})),
        dependency_groups=normalize_table_of_lists(payload.get("dependency-groups", {})),
        uv_sources=normalize_uv_sources(uv_sources),
    )


def parse_node_snapshot(text: str | None) -> NodeSnapshot:
    if not text:
        return NodeSnapshot(())
    payload = json.loads(text)
    sections: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for section in NODE_DEPENDENCY_SECTIONS:
        values = payload.get(section, {})
        if not isinstance(values, Mapping):
            continue
        sections.append((section, tuple(sorted((str(name), str(spec)) for name, spec in values.items()))))
    return NodeSnapshot(tuple(sections))


def _collect_cargo_entries(
    table: Mapping[str, Any],
    prefix: tuple[str, ...],
    collected: list[tuple[str, str, str]],
) -> None:
    for key, value in table.items():
        if key in {"dependencies", "dev-dependencies", "build-dependencies"} and isinstance(value, Mapping):
            for dependency_name in sorted(value):
                spec = value[dependency_name]
                if isinstance(spec, str):
                    spec_text = json.dumps({"version": spec}, sort_keys=True, separators=(",", ":"))
                else:
                    spec_text = json.dumps(spec, sort_keys=True, separators=(",", ":"))
                collected.append((".".join((*prefix, key)), str(dependency_name), spec_text))
            continue
        if isinstance(value, Mapping):
            _collect_cargo_entries(value, (*prefix, str(key)), collected)


def parse_cargo_snapshot(text: str | None) -> CargoSnapshot:
    if not text:
        return CargoSnapshot(())
    payload = tomllib.loads(text)
    entries: list[tuple[str, str, str]] = []
    _collect_cargo_entries(payload, (), entries)
    return CargoSnapshot(tuple(sorted(entries)))


def _python_risky_dependency_entries(snapshot: PythonSnapshot) -> set[str]:
    risky: set[str] = set()
    for entry in snapshot.dependency_entries:
        if any(token in entry for token in BLOCKED_PYTHON_REFERENCE_TOKENS):
            risky.add(f"project dependency: {entry}")
    for group_name, entries in snapshot.optional_entries:
        for entry in entries:
            if any(token in entry for token in BLOCKED_PYTHON_REFERENCE_TOKENS):
                risky.add(f"optional dependency [{group_name}]: {entry}")
    for group_name, entries in snapshot.dependency_groups:
        for entry in entries:
            if any(token in entry for token in BLOCKED_PYTHON_REFERENCE_TOKENS):
                risky.add(f"dependency group [{group_name}]: {entry}")
    for source_name, encoded in snapshot.uv_sources:
        source = json.loads(encoded)
        if isinstance(source, Mapping) and any(key in source for key in ("git", "url", "path")):
            risky.add(f"tool.uv.sources.{source_name}: {encoded}")
    return risky


def _node_risky_specs(snapshot: NodeSnapshot, manifest_path: Path) -> set[str]:
    risky: set[str] = set()
    for section, entries in snapshot.sections:
        for dependency_name, spec in entries:
            normalized = spec.lower()
            if normalized.startswith(BLOCKED_NODE_PREFIXES):
                risky.add(f"{manifest_path.as_posix()}::{section}.{dependency_name} -> {spec}")
    return risky


def _cargo_risky_specs(snapshot: CargoSnapshot, manifest_path: Path) -> set[str]:
    risky: set[str] = set()
    manifest_dir = manifest_path.parent.resolve()
    for scope, dependency_name, spec_text in snapshot.entries:
        spec = json.loads(spec_text)
        if isinstance(spec, Mapping) and "git" in spec:
            risky.add(f"{manifest_path.as_posix()}::{scope}.{dependency_name} uses git source")
            continue
        if isinstance(spec, Mapping) and "path" in spec:
            candidate = (manifest_dir / str(spec["path"])).resolve()
            try:
                candidate.relative_to(ROOT)
            except ValueError:
                risky.add(
                    f"{manifest_path.as_posix()}::{scope}.{dependency_name} points outside the repository via path"
                )
    return risky


def python_dependency_change_details(old: PythonSnapshot, new: PythonSnapshot) -> list[str]:
    if old == new:
        return []
    details: list[str] = []
    old_risky = _python_risky_dependency_entries(old)
    new_risky = _python_risky_dependency_entries(new)
    for item in sorted(new_risky - old_risky):
        details.append(item)
    return details


def node_dependency_change_details(old: NodeSnapshot, new: NodeSnapshot, manifest_path: Path) -> list[str]:
    if old == new:
        return []
    old_risky = _node_risky_specs(old, manifest_path)
    new_risky = _node_risky_specs(new, manifest_path)
    return sorted(new_risky - old_risky)


def cargo_dependency_change_details(old: CargoSnapshot, new: CargoSnapshot, manifest_path: Path) -> list[str]:
    if old == new:
        return []
    old_risky = _cargo_risky_specs(old, manifest_path)
    new_risky = _cargo_risky_specs(new, manifest_path)
    return sorted(new_risky - old_risky)


def lockfile_requirements(
    changed_files: set[Path],
    changed_python: bool,
    changed_node_manifests: list[Path],
    changed_cargo_manifests: list[Path],
) -> list[str]:
    failures: list[str] = []
    if changed_python and PYTHON_LOCKFILE not in changed_files:
        failures.append("pyproject.toml changed dependency inputs but uv.lock was not updated")
    if changed_node_manifests and NODE_LOCKFILE not in changed_files:
        manifests = ", ".join(path.as_posix() for path in changed_node_manifests)
        failures.append(f"{manifests} changed dependency inputs but pnpm-lock.yaml was not updated")
    if changed_cargo_manifests and CARGO_LOCKFILE not in changed_files:
        manifests = ", ".join(path.as_posix() for path in changed_cargo_manifests)
        failures.append(f"{manifests} changed dependency inputs but rust/Cargo.lock was not updated")
    return failures


def write_summary(lines: list[str], success: bool) -> None:
    step_summary_env = os.environ.get("GITHUB_STEP_SUMMARY")
    if not step_summary_env:
        return
    summary_path = Path(step_summary_env)
    status_line = "Passed custom manifest review.\n" if success else "Found dependency policy violations.\n"
    content = DEPENDENCY_REVIEW_SUMMARY + status_line
    if lines:
        content += "\n".join(f"- {line}" for line in lines) + "\n"
    summary_path.write_text(content, encoding="utf-8")


def review_dependency_changes(base_ref: str, head_ref: str) -> list[str]:
    merge_base = run_git("merge-base", base_ref, head_ref)
    changed_file_paths = {
        Path(path) for path in run_git("diff", "--name-only", merge_base, head_ref).splitlines() if path.strip()
    }
    failures: list[str] = []

    old_python = parse_python_snapshot(read_file_at_ref(merge_base, PYTHON_MANIFEST))
    new_python = parse_python_snapshot(read_file_at_ref(head_ref, PYTHON_MANIFEST))
    changed_python = old_python != new_python
    failures.extend(python_dependency_change_details(old_python, new_python))

    changed_node_manifests: list[Path] = []
    for manifest_path in NODE_MANIFESTS:
        old_node = parse_node_snapshot(read_file_at_ref(merge_base, manifest_path))
        new_node = parse_node_snapshot(read_file_at_ref(head_ref, manifest_path))
        if old_node == new_node:
            continue
        changed_node_manifests.append(manifest_path)
        failures.extend(node_dependency_change_details(old_node, new_node, manifest_path))

    changed_cargo_manifests: list[Path] = []
    for manifest_path in sorted(path for path in changed_file_paths if path.name == "Cargo.toml"):
        old_cargo = parse_cargo_snapshot(read_file_at_ref(merge_base, manifest_path))
        new_cargo = parse_cargo_snapshot(read_file_at_ref(head_ref, manifest_path))
        if old_cargo == new_cargo:
            continue
        changed_cargo_manifests.append(manifest_path)
        failures.extend(cargo_dependency_change_details(old_cargo, new_cargo, manifest_path))

    failures.extend(
        lockfile_requirements(changed_file_paths, changed_python, changed_node_manifests, changed_cargo_manifests)
    )
    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True, help="Base commit or ref for the comparison")
    parser.add_argument("--head-ref", required=True, help="Head commit or ref for the comparison")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        failures = review_dependency_changes(args.base_ref, args.head_ref)
    except DependencyReviewError as exc:
        print(f"dependency review failed to execute: {exc}", file=sys.stderr)
        return 2

    if failures:
        for failure in failures:
            print(f"dependency review failure: {failure}", file=sys.stderr)
        write_summary(failures, success=False)
        return 1

    success_lines = [
        "No risky dependency sources were introduced.",
        "Lockfiles were updated when dependency manifests changed.",
    ]
    for line in success_lines:
        print(line)
    write_summary(success_lines, success=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
