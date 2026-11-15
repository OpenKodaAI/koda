"""Tests keep runtime scratch in the session's own RUNTIME_EPHEMERAL_ROOT, never in the shared default (D-276).

RUNTIME_EPHEMERAL_ROOT defaults to ``<tmp>/koda-runtime/<agent>``, which every test session and
checkout on the machine shares, and RUNTIME_ROOT_DIR follows it. Task ids restart at 1 in each
test database, so parallel sessions appended to the same ``tasks/<id>/events.ndjson``.
tests/conftest.py points the root at a per-session directory before koda is imported, like
STATE_ROOT_DIR (D-265), and its session-end guard fails the run if a loaded koda module still
points into the shared one.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests import conftest

_SHARED_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "koda-runtime"

# (module, attribute) of every path a module derives from RUNTIME_EPHEMERAL_ROOT when it is imported.
_RUNTIME_PATHS = (
    ("koda.config", "RUNTIME_EPHEMERAL_ROOT"),
    ("koda.config", "RUNTIME_ROOT_DIR"),
    ("koda.config", "IMAGE_TEMP_DIR"),
    ("koda.config", "ARTIFACT_CACHE_DIR"),
    ("koda.control_plane.settings", "RUNTIME_EPHEMERAL_ROOT"),
    ("koda.control_plane.settings", "CONTROL_PLANE_RUNTIME_DIR"),
    ("koda.services.runtime.controller", "RUNTIME_ROOT_DIR"),
    ("koda.utils.workdir", "RUNTIME_ROOT_DIR"),
    ("koda.utils.workdir", "RUNTIME_EPHEMERAL_ROOT"),
)


@pytest.mark.parametrize(("module", "attr"), _RUNTIME_PATHS)
def test_runtime_path_is_outside_the_shared_runtime_root(module: str, attr: str) -> None:
    path = Path(getattr(importlib.import_module(module), attr))
    assert not path.is_relative_to(_SHARED_RUNTIME_ROOT), f"{module}.{attr} = {path}"


class _EventStore:
    def add_event(self, **event: Any) -> dict[str, Any]:
        return {"seq": 1, **event}


@pytest.mark.asyncio
async def test_runtime_events_are_written_in_the_session_runtime_root(
    monkeypatch: pytest.MonkeyPatch, session_runtime_root: Path
) -> None:
    """A RuntimeController built with the default root logs task 1's events in this session's directory."""
    from koda.services.runtime import controller as controller_module

    monkeypatch.setattr(controller_module, "postgres_primary_mode", lambda: True)
    monkeypatch.setattr(controller_module, "get_primary_state_backend", lambda: object())
    monkeypatch.setattr(controller_module, "PostgresRuntimeStore", _EventStore)
    monkeypatch.setattr(controller_module, "build_runtime_kernel_client", lambda runtime_root, store: object())
    monkeypatch.setattr(controller_module, "build_artifact_engine_client", lambda agent_id: object())
    monkeypatch.setattr(controller_module, "RecoveryManager", lambda store: SimpleNamespace())
    monkeypatch.setattr(controller_module, "PortAllocator", lambda store: SimpleNamespace())

    controller = controller_module.RuntimeController()
    await controller.events.publish(task_id=1, env_id=None, attempt=1, phase="queued", event_type="d276.probe")

    log = controller.runtime_root / "tasks" / "1" / "events.ndjson"
    assert controller.runtime_root.is_relative_to(session_runtime_root.resolve()), controller.runtime_root
    assert [json.loads(line)["event_type"] for line in log.read_text().splitlines()][-1] == "d276.probe"


def test_the_session_guard_catches_a_path_in_the_shared_runtime_root(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda import config

    shared = _SHARED_RUNTIME_ROOT / "agent_a"
    monkeypatch.setattr(config, "RUNTIME_ROOT_DIR", shared)

    leaks = conftest._session_root_leaks()

    assert f"koda.config.RUNTIME_ROOT_DIR = {shared}" in "\n".join(leaks), leaks


# What a developer .env might set. koda.config loads .env without override, so it refills any of
# these keys the environment lacks, and in ``_env`` the AGENT_A_-prefixed key wins over the
# unprefixed one tests/conftest.py points at the session directory.
_DOTENV_ROOTS = {
    "AGENT_A_STATE_ROOT_DIR": "/var/lib/koda/state",
    "AGENT_A_RUNTIME_EPHEMERAL_ROOT": "/var/lib/koda/runtime/agent_a",
    "AGENT_A_RUNTIME_ROOT_DIR": "/var/lib/koda/runtime/agent_a",
    "RUNTIME_ROOT_DIR": "/var/lib/koda/runtime/agent_a",
}


def test_a_dotenv_cannot_move_the_session_roots(session_state_root: Path, session_runtime_root: Path) -> None:
    from dotenv import load_dotenv

    from koda import config

    before = {key: os.environ.get(key) for key in _DOTENV_ROOTS}
    try:
        load_dotenv(stream=io.StringIO("".join(f"{key}={value}\n" for key, value in _DOTENV_ROOTS.items())))

        assert config.AGENT_ID == "AGENT_A"
        assert config._env("STATE_ROOT_DIR") == str(session_state_root)
        assert config._env("RUNTIME_EPHEMERAL_ROOT") == str(session_runtime_root)
        assert config._env("RUNTIME_ROOT_DIR") == str(session_runtime_root)
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
