"""Snapshot capture: collect state from subsystems."""

from __future__ import annotations

import os
import time
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)


async def capture_snapshot(scope_id: int, work_dir: str) -> dict[str, Any]:
    """Capture current environment state."""
    snapshot: dict[str, Any] = {
        "scope_id": scope_id,
        "work_dir": work_dir,
        "captured_at": time.time(),
        "subsystems": {},
    }

    # 1. Working directory files (top-level listing)
    try:
        if os.path.isdir(work_dir):
            entries = []
            for name in sorted(os.listdir(work_dir))[:500]:
                full = os.path.join(work_dir, name)
                kind = "dir" if os.path.isdir(full) else "file"
                size = os.path.getsize(full) if kind == "file" else 0
                entries.append({"name": name, "type": kind, "size": size})
            snapshot["subsystems"]["filesystem"] = {"entries": entries, "count": len(entries)}
    except Exception as e:
        snapshot["subsystems"]["filesystem"] = {"error": str(e)}

    # 2. Browser session (if available)
    try:
        from koda.config import BROWSER_FEATURES_ENABLED

        if BROWSER_FEATURES_ENABLED:
            from koda.services.browser_manager import browser_manager

            session = browser_manager.get_session_snapshot(scope_id)
            if session:
                snapshot["subsystems"]["browser"] = session
    except Exception as e:
        snapshot["subsystems"]["browser"] = {"error": str(e)}

    # 3. Background processes (if shell tools available)
    try:
        from koda.config import SHELL_ENABLED

        if SHELL_ENABLED:
            from koda.services.shell_tools import bg_process_manager

            processes = []
            for handle_id, proc in bg_process_manager._processes.items():
                processes.append(
                    {
                        "handle_id": handle_id,
                        "command": proc.command,
                        "finished": proc.finished,
                        "exit_code": proc.exit_code,
                    }
                )
            snapshot["subsystems"]["processes"] = {"active": processes}
    except Exception:
        pass

    # 4. Webhook registrations
    try:
        from koda.config import WEBHOOK_ENABLED  # type: ignore[attr-defined]

        if WEBHOOK_ENABLED:
            from koda.services.webhook_manager import webhook_manager  # type: ignore[import-untyped]

            snapshot["subsystems"]["webhooks"] = {"registrations": webhook_manager.list_webhooks()}
    except Exception:
        pass

    # 5. Workflows
    try:
        from koda.config import WORKFLOW_ENABLED  # type: ignore[attr-defined]

        if WORKFLOW_ENABLED:
            from koda.workflows.store import get_workflow_store  # type: ignore[import-untyped]

            snapshot["subsystems"]["workflows"] = {"workflows": get_workflow_store().list_all()}
    except Exception:
        pass

    return snapshot
