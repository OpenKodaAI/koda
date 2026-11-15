"""Service shims and no-op fallbacks that nothing needed are gone (M4-E1-T3).

TD-048, TD-050, TD-057, TD-058, TD-060, TD-061 and TD-066: legacy wrappers over the
scheduled-jobs service, a pass-through runtime store, an in-memory dashboard aggregator
nothing read, a runtime smoke harness with no entry point, fallbacks for two hard
dependencies, metrics that are never set, and an audit helper that only delegated.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import koda
import koda.config as config_module
from koda.services import audit, cron_store, metrics, resilience, scheduler


def test_removed_modules_are_gone() -> None:
    package_root = Path(koda.__file__).resolve().parent
    for relative in ("services/runtime/store.py", "services/runtime/smoke.py", "dashboard"):
        assert not (package_root / relative).exists(), relative


def test_scheduler_keeps_only_the_handler_helpers() -> None:
    for name in ("create_reminder_job", "create_agent_query_job", "list_jobs", "pause_job"):
        assert not hasattr(scheduler, name), name


def test_cron_store_has_no_no_op_hooks_or_restore_flow() -> None:
    for name in ("schedule_cron_task", "cancel_cron_task", "restore_all_jobs", "get_all_enabled_jobs", "get_cron_job"):
        assert not hasattr(cron_store, name), name


def test_list_cron_jobs_returns_job_rows_not_tuples() -> None:
    rows = [
        {"id": 3, "job_type": "shell_command", "status": "active", "schedule_expr": "*/5 * * * *", "payload": {}},
        {"id": 4, "job_type": "shell_command", "status": "archived", "schedule_expr": "* * * * *", "payload": {}},
        {"id": 5, "job_type": "reminder", "status": "active", "schedule_expr": "60", "payload": {}},
    ]
    with patch.object(cron_store, "list_jobs", return_value=rows):
        assert cron_store.list_cron_jobs(7) == [rows[0]]


def test_dependency_fallbacks_are_gone() -> None:
    assert "ModuleNotFoundError" not in inspect.getsource(metrics)
    assert "ModuleNotFoundError" not in inspect.getsource(resilience)


def test_metrics_that_are_never_set_are_gone() -> None:
    for name in ("OPS_BENCHMARK_RUNS", "OPS_BENCHMARK_DURATION", "RUNTIME_WORKTREE_DISK_BYTES"):
        assert not hasattr(metrics, name), name


def test_audit_uses_the_primary_bridge_directly() -> None:
    from koda.state import primary

    assert not hasattr(audit, "_run_coro_sync")
    assert audit.run_coro_sync is primary.run_coro_sync


def test_dashboard_flag_is_gone() -> None:
    assert not hasattr(config_module, "DASHBOARD_ENABLED")
