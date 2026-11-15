"""Import the retired approval JSON files into Postgres, once, at startup (M2-E1-T2).

Earlier releases wrote ``approval_grants.json`` and ``pending_approvals.json``
in ``STATE_ROOT_DIR`` when a Postgres write failed, and never read them back.
Postgres is now the only approval store. At startup each file still there is
imported and then renamed ``<name>.migrated``; it is never deleted. A row that
is already stored is left as it is. When an import stops before the rename,
the next boot imports the file again, and a row deleted in between is
inserted again.

Every imported grant is expired, with one ``approval.grant_expired`` audit
row: the old release left a grant in the file after its last use or its
revocation, so the file cannot tell a spent grant from an unused one, and
none of them authorizes anything. An imported grant keeps its ``agent_id``.
One without an agent follows the migration ``050_approval_tables`` rule: it
gets the one agent its approval request, session or chat names.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import koda.config as config_module
from koda.logging_config import get_logger
from koda.state.approval_grants import import_approval_grants
from koda.state.pending_approvals import import_pending_ops
from koda.state.primary import get_primary_state_backend, primary_execute, run_coro_sync

log = get_logger(__name__)

_GRANTS_FILE = "approval_grants.json"
_PENDING_FILE = "pending_approvals.json"


def _json_files() -> tuple[Path, Path]:
    root = config_module.STATE_ROOT_DIR
    return root / _PENDING_FILE, root / _GRANTS_FILE


def _read_entries(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("approval_json_import_unreadable", path=str(path), exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def _mark_migrated(path: Path) -> None:
    """Rename the file ``<name>.migrated``, next to an earlier one rather than over it."""
    target = path.with_name(f"{path.name}.migrated")
    if target.exists():
        target = path.with_name(f"{path.name}.{int(time.time())}.migrated")
    try:
        path.rename(target)
    except FileNotFoundError:
        # Another worker sharing STATE_ROOT_DIR imported and renamed it first.
        return
    log.info("approval_json_import_renamed", path=str(path), renamed_to=str(target))


def _apply_legacy_grant_rule() -> None:
    from koda.knowledge.v2.postgres_backend import approval_grant_legacy_rule_sql

    backend = get_primary_state_backend(agent_id=config_module.AGENT_ID)
    if backend is None:
        raise RuntimeError("approval_import_primary_backend_unavailable")
    for statement in approval_grant_legacy_rule_sql(backend.schema):
        run_coro_sync(primary_execute(statement, (), agent_id=config_module.AGENT_ID))


async def import_approval_json_files() -> dict[str, int]:
    """Import each approval JSON file still in STATE_ROOT_DIR, then rename it ``*.migrated``.

    Returns the rows inserted per file. A failed write is logged and raised,
    and the file stays in place for the next boot.
    """
    pending_path, grants_path = _json_files()
    imported: dict[str, int] = {}
    # Pending ops first: the legacy grant rule reads the request that issued a grant.
    if pending_path.exists():
        imported[_PENDING_FILE] = import_pending_ops(_read_entries(pending_path))
        _mark_migrated(pending_path)
    if grants_path.exists():
        imported[_GRANTS_FILE] = import_approval_grants(_read_entries(grants_path))
        try:
            _apply_legacy_grant_rule()
        except Exception:
            log.exception("approval_json_import_legacy_rule_failed")
            raise
        _mark_migrated(grants_path)
    if imported:
        log.info("approval_json_import_complete", **imported)
    return imported
