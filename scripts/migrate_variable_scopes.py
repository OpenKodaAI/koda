"""One-shot migration: normalize legacy `bot_grant` scope to `agent_grant`.

Iterates ``cp_global_sections`` and ``cp_agent_sections``, deserializes each
row's ``data_json``, rewrites any ``variables[].scope == 'bot_grant'`` entry
to ``agent_grant``, and persists the updated payload.

Idempotent: running twice is a no-op. Supports ``--dry-run``.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from koda.control_plane.database import execute, fetch_all, json_dump, json_load, now_iso


def _rewrite_variables(data: Any) -> tuple[Any, int]:
    """Return (possibly-mutated dict, number of variables rewritten)."""
    if not isinstance(data, dict):
        return data, 0
    variables = data.get("variables")
    if not isinstance(variables, list):
        return data, 0
    changes = 0
    next_variables: list[Any] = []
    for entry in variables:
        if isinstance(entry, dict) and entry.get("scope") == "bot_grant":
            next_variables.append({**entry, "scope": "agent_grant"})
            changes += 1
        else:
            next_variables.append(entry)
    if not changes:
        return data, 0
    updated = dict(data)
    updated["variables"] = next_variables
    return updated, changes


def _migrate_global_sections(*, dry_run: bool) -> tuple[int, int]:
    rows = fetch_all("SELECT section, data_json FROM cp_global_sections")
    touched = 0
    total_changes = 0
    for row in rows:
        section = row["section"]
        raw = row["data_json"]
        parsed = json_load(raw) if raw is not None else None
        if not isinstance(parsed, dict):
            continue
        updated, changes = _rewrite_variables(parsed)
        if not changes:
            continue
        touched += 1
        total_changes += changes
        print(f"  global[{section}] → {changes} variable(s) rewritten")
        if not dry_run:
            execute(
                "UPDATE cp_global_sections SET data_json = ?, updated_at = ? WHERE section = ?",
                (json_dump(updated), now_iso(), section),
            )
    return touched, total_changes


def _migrate_agent_sections(*, dry_run: bool) -> tuple[int, int]:
    rows = fetch_all("SELECT agent_id, section, data_json FROM cp_agent_sections")
    touched = 0
    total_changes = 0
    for row in rows:
        agent_id = row["agent_id"]
        section = row["section"]
        raw = row["data_json"]
        parsed = json_load(raw) if raw is not None else None
        if not isinstance(parsed, dict):
            continue
        updated, changes = _rewrite_variables(parsed)
        if not changes:
            continue
        touched += 1
        total_changes += changes
        print(f"  {agent_id}[{section}] → {changes} variable(s) rewritten")
        if not dry_run:
            execute(
                "UPDATE cp_agent_sections SET data_json = ?, updated_at = ? WHERE agent_id = ? AND section = ?",
                (json_dump(updated), now_iso(), agent_id, section),
            )
    return touched, total_changes


def migrate(*, dry_run: bool) -> int:
    global_touched, global_changes = _migrate_global_sections(dry_run=dry_run)
    agent_touched, agent_changes = _migrate_agent_sections(dry_run=dry_run)
    total_changes = global_changes + agent_changes
    total_touched = global_touched + agent_touched
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(
        f"[{mode}] rows_touched={total_touched} "
        f"(global={global_touched}, agent={agent_touched}) "
        f"replacements={total_changes}"
    )
    return total_changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy bot_grant scope to agent_grant.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
    args = parser.parse_args()
    return migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
