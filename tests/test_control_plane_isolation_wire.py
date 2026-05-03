"""Supervisor calls isolation primitives before/after spawn.

The cgroup v2 Linux body lives in the Rust runtime-kernel; this wires it into
``ControlPlaneSupervisor._start_worker`` so the limits are actually
applied. Tests are a mixture of grep gates (regression-proof) plus
runtime checks of the helper that builds default limits and the
sanitizer that prevents path traversal via ``workspace_id``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from koda.control_plane import isolation_runtime as iso


def _read_supervisor() -> str:
    return Path("koda/control_plane/supervisor.py").read_text(encoding="utf-8")


def test_start_worker_calls_isolation_helpers() -> None:
    src = _read_supervisor()
    sw_idx = src.index("async def _start_worker(")
    next_def = src.index("async def ", sw_idx + 1)
    body = src[sw_idx:next_def]
    assert "ensure_cgroup_v2_root()" in body
    assert "apply_workspace_limits(" in body
    assert "place_pid(" in body
    # apply must run BEFORE spawn so the cgroup exists when the
    # worker starts allocating.
    apply_idx = body.index("apply_workspace_limits(")
    spawn_idx = body.index("create_subprocess_exec(")
    place_idx = body.index("place_pid(")
    assert apply_idx < spawn_idx < place_idx, "expected order: apply_workspace_limits → spawn → place_pid"


def test_supervisor_resolves_workspace_id_per_agent() -> None:
    src = _read_supervisor()
    assert "_workspace_id_for_agent" in src, (
        "supervisor must resolve a workspace_id per agent so the cgroup directory groups workers by team / squad."
    )


def test_default_limits_are_unset_without_env() -> None:
    """An operator who has not set ``KODA_AGENT_DEFAULT_*`` should
    still get the cgroup directory created (so future runtime tuning
    works) but no actual limit writes."""
    for key in ("KODA_AGENT_DEFAULT_MEMORY_MB", "KODA_AGENT_DEFAULT_CPU_FRACTION", "KODA_AGENT_DEFAULT_PIDS_MAX"):
        os.environ.pop(key, None)
    limits = iso.default_limits_from_env("ws_alpha")
    assert limits.workspace_id == "ws_alpha"
    assert limits.memory_max_bytes is None
    assert limits.cpu_max_quota_period is None
    assert limits.pids_max is None


def test_default_limits_parse_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODA_AGENT_DEFAULT_MEMORY_MB", "512")
    monkeypatch.setenv("KODA_AGENT_DEFAULT_CPU_FRACTION", "0.5")
    monkeypatch.setenv("KODA_AGENT_DEFAULT_PIDS_MAX", "256")
    limits = iso.default_limits_from_env("ws_test")
    assert limits.memory_max_bytes == 512 * 1024 * 1024
    assert limits.cpu_max_quota_period is not None
    quota, period = limits.cpu_max_quota_period
    assert period == 100_000
    assert quota == 50_000  # 0.5 * period
    assert limits.pids_max == 256


def test_invalid_env_falls_back_to_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODA_AGENT_DEFAULT_MEMORY_MB", "garbage")
    monkeypatch.setenv("KODA_AGENT_DEFAULT_PIDS_MAX", "-7")
    limits = iso.default_limits_from_env("ws_bad")
    assert limits.memory_max_bytes is None
    assert limits.pids_max is None


def test_sanitizer_blocks_path_traversal() -> None:
    """Workspace IDs come from the control plane; even though they are
    structured today, defense-in-depth: never let a malformed value
    escape the cgroup root."""
    assert iso._sanitize_workspace_segment("../escape") == "___escape"
    assert iso._sanitize_workspace_segment("ws/abc") == "ws_abc"
    assert iso._sanitize_workspace_segment("ws.dot") == "ws_dot"
    assert iso._sanitize_workspace_segment("") == "default"
    assert iso._sanitize_workspace_segment("ws_alpha-1") == "ws_alpha-1"


def test_helpers_are_noop_on_non_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iso, "_is_linux", lambda: False)
    iso.ensure_cgroup_v2_root()
    iso.apply_workspace_limits(iso.WorkspaceIsolationLimits(workspace_id="ws_test", memory_max_bytes=1024))
    iso.place_pid("ws_test", 12345)


def test_apply_writes_files_under_temp_root_on_linux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the file-write path with a temp dir as the cgroup
    root so the test passes everywhere — cgroup files behave like
    regular files at this layer."""
    monkeypatch.setattr(iso, "_is_linux", lambda: True)
    monkeypatch.setenv("KODA_CGROUP_ROOT", str(tmp_path))
    iso.ensure_cgroup_v2_root()
    iso.apply_workspace_limits(
        iso.WorkspaceIsolationLimits(
            workspace_id="ws_alpha",
            memory_max_bytes=2 * 1024 * 1024 * 1024,
            cpu_max_quota_period=(50_000, 100_000),
            pids_max=128,
        )
    )
    target = tmp_path / "ws_ws_alpha"
    assert (target / "memory.max").read_text() == str(2 * 1024 * 1024 * 1024)
    assert (target / "cpu.max").read_text() == "50000 100000"
    assert (target / "pids.max").read_text() == "128"

    iso.place_pid("ws_alpha", 99999)
    assert (target / "cgroup.procs").read_text() == "99999"


def test_place_pid_skips_when_cgroup_dir_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If apply_workspace_limits never ran (e.g. permission error),
    place_pid must NOT raise — soft-fail instead."""
    monkeypatch.setattr(iso, "_is_linux", lambda: True)
    monkeypatch.setenv("KODA_CGROUP_ROOT", str(tmp_path))
    # No apply call; just place_pid into a non-existent dir.
    iso.place_pid("ws_missing", 1234)


def test_place_pid_rejects_invalid_pid() -> None:
    iso.place_pid("ws_test", 0)
    iso.place_pid("ws_test", -1)


def test_supervisor_workspace_id_falls_back_to_default() -> None:
    """When the agent row has no workspace_id (enforcement
    not yet enabled), the helper returns ``"default"`` so the cgroup
    directory still exists for future operator tuning."""
    from koda.control_plane import supervisor as supervisor_mod

    sup = supervisor_mod.ControlPlaneSupervisor.__new__(supervisor_mod.ControlPlaneSupervisor)
    sup._manager = type("M", (), {"get_agent": staticmethod(lambda _aid: {"id": "AGENT_A"})})()
    assert sup._workspace_id_for_agent("AGENT_A") == "default"


def test_supervisor_workspace_id_uses_agent_row_when_set() -> None:
    from koda.control_plane import supervisor as supervisor_mod

    sup = supervisor_mod.ControlPlaneSupervisor.__new__(supervisor_mod.ControlPlaneSupervisor)
    sup._manager = type(
        "M",
        (),
        {"get_agent": staticmethod(lambda _aid: {"id": "AGENT_A", "workspace_id": "ws_squad_alpha"})},
    )()
    assert sup._workspace_id_for_agent("AGENT_A") == "ws_squad_alpha"
