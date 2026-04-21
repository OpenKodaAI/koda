"""One-shot migration: compile legacy tool/autonomy/resource policies into execution_policy v2.

Iterates every agent tracked in ``cp_agent_definitions``, assembles its effective
``agent_spec`` (global + agent overrides), and, if the ``execution_policy`` field
is empty while any of ``tool_policy``/``autonomy_policy``/``resource_access_policy``
carry v1 content, calls :func:`compile_legacy_execution_policy` and persists the
compiled payload onto the agent's ``runtime`` section.

After this migration runs successfully, ``compile_legacy_execution_policy`` and
its ``resolve_execution_policy`` fallback path can be removed from the codebase
without risk.

Idempotent: agents that already carry an explicit ``execution_policy`` are left
untouched. Supports ``--dry-run``.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from koda.control_plane.database import execute, fetch_all, fetch_one, json_dump, now_iso
from koda.control_plane.execution_policy import compile_legacy_execution_policy


def _safe_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _agent_runtime_section(agent_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    agent_row = fetch_one(
        "SELECT data_json FROM cp_agent_sections WHERE agent_id = ? AND section = ?",
        (agent_id, "runtime"),
    )
    global_row = fetch_one(
        "SELECT data_json FROM cp_global_sections WHERE section = ?",
        ("runtime",),
    )
    agent_runtime = _safe_json_object((agent_row or {}).get("data_json")) if agent_row else {}
    global_runtime = _safe_json_object((global_row or {}).get("data_json")) if global_row else {}
    return agent_runtime, global_runtime


def _agent_tools_section(agent_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    agent_row = fetch_one(
        "SELECT data_json FROM cp_agent_sections WHERE agent_id = ? AND section = ?",
        (agent_id, "tools"),
    )
    global_row = fetch_one(
        "SELECT data_json FROM cp_global_sections WHERE section = ?",
        ("tools",),
    )
    agent_tools = _safe_json_object((agent_row or {}).get("data_json")) if agent_row else {}
    global_tools = _safe_json_object((global_row or {}).get("data_json")) if global_row else {}
    return agent_tools, global_tools


def _agent_access_section(agent_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    agent_row = fetch_one(
        "SELECT data_json FROM cp_agent_sections WHERE agent_id = ? AND section = ?",
        (agent_id, "access"),
    )
    global_row = fetch_one(
        "SELECT data_json FROM cp_global_sections WHERE section = ?",
        ("access",),
    )
    agent_access = _safe_json_object((agent_row or {}).get("data_json")) if agent_row else {}
    global_access = _safe_json_object((global_row or {}).get("data_json")) if global_row else {}
    return agent_access, global_access


def _merge(agent_section: dict[str, Any], global_section: dict[str, Any], key: str) -> dict[str, Any]:
    agent_value = _safe_json_object(agent_section.get(key))
    if agent_value:
        return agent_value
    return _safe_json_object(global_section.get(key))


def migrate(*, dry_run: bool) -> int:
    agent_rows = fetch_all("SELECT id FROM cp_agent_definitions ORDER BY id ASC")
    total_migrated = 0
    total_skipped_existing = 0
    total_skipped_empty = 0
    for row in agent_rows:
        agent_id = row["id"]
        agent_runtime, global_runtime = _agent_runtime_section(agent_id)
        agent_tools, global_tools = _agent_tools_section(agent_id)
        agent_access, global_access = _agent_access_section(agent_id)

        existing_execution = _safe_json_object(agent_runtime.get("execution_policy")) or _safe_json_object(
            global_runtime.get("execution_policy")
        )
        if existing_execution:
            total_skipped_existing += 1
            continue

        effective_spec = {
            "tool_policy": _merge(agent_tools, global_tools, "tool_policy"),
            "autonomy_policy": _merge(agent_runtime, global_runtime, "autonomy_policy"),
            "resource_access_policy": _merge(agent_access, global_access, "resource_access_policy"),
        }
        if not any(effective_spec.values()):
            total_skipped_empty += 1
            continue

        compiled = compile_legacy_execution_policy(effective_spec)
        next_runtime = dict(agent_runtime)
        next_runtime["execution_policy"] = compiled
        print(f"  {agent_id}: compiled v2 execution_policy from legacy sources")

        if not dry_run:
            existing = fetch_one(
                "SELECT 1 FROM cp_agent_sections WHERE agent_id = ? AND section = ?",
                (agent_id, "runtime"),
            )
            if existing:
                execute(
                    "UPDATE cp_agent_sections SET data_json = ?, updated_at = ? WHERE agent_id = ? AND section = ?",
                    (json_dump(next_runtime), now_iso(), agent_id, "runtime"),
                )
            else:
                execute(
                    "INSERT INTO cp_agent_sections (agent_id, section, data_json, updated_at) VALUES (?, ?, ?, ?)",
                    (agent_id, "runtime", json_dump(next_runtime), now_iso()),
                )
        total_migrated += 1
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(
        f"[{mode}] agents_migrated={total_migrated} "
        f"agents_skipped_existing={total_skipped_existing} "
        f"agents_skipped_empty={total_skipped_empty}"
    )
    return total_migrated


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile legacy execution policies into v2 per agent.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
    args = parser.parse_args()
    return migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
