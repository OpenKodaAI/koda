"""Tests for the operational runtime smoke runner."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.runtime.smoke import run_runtime_smoke


class _FakeTerminalManager:
    def __init__(self) -> None:
        self._terminals: dict[int, Path] = {}

    def register(self, terminal_id: int, path: Path) -> None:
        self._terminals[terminal_id] = path

    async def write(self, terminal_id: int, content: str) -> None:
        self._terminals[terminal_id].write_text(content, encoding="utf-8")

    async def close(self, terminal_id: int, force: bool = False) -> None:
        self._terminals.pop(terminal_id, None)


class _FakeRuntimeStore:
    def __init__(self, runtime_root: Path) -> None:
        self._runtime_root = runtime_root
        self._envs_by_task: dict[int, dict[str, Any]] = {}
        self._events: dict[int, list[dict[str, Any]]] = {}
        self._checkpoints: dict[int, list[dict[str, Any]]] = {}
        self._artifacts: dict[int, list[dict[str, Any]]] = {}
        self._resources: dict[int, list[dict[str, Any]]] = {}
        self._processes: dict[int, list[dict[str, Any]]] = {}
        self._next_id = 100

    def _task_root(self, task_id: int) -> Path:
        return self._runtime_root / "tasks" / str(task_id)

    def _push_event(self, task_id: int, event_type: str) -> None:
        event = {"id": self._next_id, "seq": len(self._events.get(task_id, [])) + 1, "type": event_type}
        self._next_id += 1
        self._events.setdefault(task_id, []).append(event)
        task_root = self._task_root(task_id)
        task_root.mkdir(parents=True, exist_ok=True)
        with (task_root / "events.ndjson").open("a", encoding="utf-8") as handle:
            handle.write(f"{event_type}\n")

    def create_environment(self, task_id: int, workspace_path: Path) -> dict[str, Any]:
        env = {
            "id": self._next_id,
            "task_id": task_id,
            "workspace_path": str(workspace_path),
            "created_worktree": True,
            "current_phase": "planning",
            "status": "active",
        }
        self._next_id += 1
        self._envs_by_task[task_id] = env
        self._push_event(task_id, "worktree.created")
        return env

    def add_process(self, task_id: int, proc: Any, role: str) -> dict[str, Any]:
        row = {"id": self._next_id, "pid": proc.pid, "role": role, "proc": proc}
        self._next_id += 1
        self._processes.setdefault(task_id, []).append(row)
        return row

    def list_processes(self, task_id: int) -> list[dict[str, Any]]:
        return [{k: v for k, v in row.items() if k != "proc"} for row in self._processes.get(task_id, [])]

    def process_by_id(self, process_id: int) -> dict[str, Any] | None:
        for rows in self._processes.values():
            for row in rows:
                if int(row["id"]) == int(process_id):
                    return row
        return None

    def list_events(self, *, task_id: int) -> list[dict[str, Any]]:
        return list(self._events.get(task_id, []))

    def list_checkpoints(self, task_id: int) -> list[dict[str, Any]]:
        return list(self._checkpoints.get(task_id, []))

    def list_artifacts(self, task_id: int) -> list[dict[str, Any]]:
        return list(self._artifacts.get(task_id, []))

    def list_resource_samples(self, task_id: int) -> list[dict[str, Any]]:
        return list(self._resources.get(task_id, []))

    def get_environment_by_task(self, task_id: int) -> dict[str, Any] | None:
        return self._envs_by_task.get(task_id)

    def add_artifact(self, task_id: int, **kwargs: Any) -> None:
        row = {"id": self._next_id, **kwargs}
        self._next_id += 1
        self._artifacts.setdefault(task_id, []).append(row)

    def add_loop_cycle(self, task_id: int) -> None:
        task_root = self._task_root(task_id)
        task_root.mkdir(parents=True, exist_ok=True)
        with (task_root / "loop_cycles.jsonl").open("a", encoding="utf-8") as handle:
            handle.write('{"cycle": true}\n')

    def finalize(self, task_id: int) -> None:
        env = self._envs_by_task[task_id]
        env["current_phase"] = "completed_retained"
        self._checkpoints.setdefault(task_id, []).append({"id": self._next_id})
        self._next_id += 1
        self._resources.setdefault(task_id, []).append({"id": self._next_id})
        self._next_id += 1
        self._push_event(task_id, "checkpoint.saved")
        self._push_event(task_id, "resource.sampled")


class _FakeRuntimeController:
    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root
        self.store = _FakeRuntimeStore(runtime_root)
        self.terminals = _FakeTerminalManager()
        self._terminal_id = 1

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def register_queued_task(self, **_: Any) -> None:
        return None

    async def classify_task(self, *, task_id: int, query_text: str) -> Any:
        del task_id, query_text
        return SimpleNamespace(classification="standard", environment_kind="dev_worktree")

    async def provision_environment(
        self,
        *,
        task_id: int,
        user_id: int,
        chat_id: int,
        query_text: str,
        base_work_dir: str,
        classification: Any,
    ) -> dict[str, Any]:
        del user_id, chat_id, query_text, classification
        workspace_path = Path(base_work_dir) / f"task-{task_id}"
        workspace_path.mkdir(parents=True, exist_ok=True)
        return self.store.create_environment(task_id=task_id, workspace_path=workspace_path)

    async def mark_phase(self, *, task_id: int, env_id: int, phase: str) -> None:
        del env_id
        self.store.get_environment_by_task(task_id)["current_phase"] = phase  # type: ignore[index]

    async def heartbeat(self, *, task_id: int, env_id: int, phase: str) -> None:
        del task_id, env_id, phase
        return None

    async def record_decision(self, *, task_id: int, decision: dict[str, Any]) -> None:
        del task_id, decision
        return None

    async def record_loop_cycle(self, *, task_id: int, **_: Any) -> None:
        self.store.add_loop_cycle(task_id)

    async def record_process(self, *, task_id: int, proc: Any, role: str, **_: Any) -> None:
        self.store.add_process(task_id, proc, role)

    async def start_operator_terminal(self, *, task_id: int, actor: str, shell: str) -> dict[str, Any]:
        del actor, shell
        terminal_id = self._terminal_id
        self._terminal_id += 1
        terminal_path = self.runtime_root / "tasks" / str(task_id) / "terminal.log"
        terminal_path.parent.mkdir(parents=True, exist_ok=True)
        self.terminals.register(terminal_id, terminal_path)
        return {"id": terminal_id, "path": str(terminal_path)}

    async def write_terminal_input(self, *, task_id: int, terminal_id: int, text: str) -> bool:
        del task_id
        await self.terminals.write(terminal_id, text)
        return True

    async def close_terminal_session(self, *, task_id: int, terminal_id: int, force: bool = False) -> bool:
        del task_id
        await self.terminals.close(terminal_id, force=force)
        return True

    async def ensure_environment_live_resources(self, *, task_id: int, env_id: int) -> dict[str, Any] | None:
        del env_id
        return self.store.get_environment_by_task(task_id)

    def get_browser_snapshot(self, task_id: int) -> dict[str, Any]:
        del task_id
        return {}

    async def add_artifact(self, *, task_id: int, **kwargs: Any) -> None:
        self.store.add_artifact(task_id, **kwargs)

    async def terminate_process(self, *, process_id: int, force: bool = True) -> None:
        del force
        row = self.store.process_by_id(process_id)
        if row is not None:
            proc = row["proc"]
            proc.terminate()
            await proc.wait()

    async def finalize_task(self, *, task_id: int, success: bool, summary: dict[str, Any]) -> None:
        del success, summary
        self.store.finalize(task_id)

    def get_runtime_readiness(self) -> dict[str, Any]:
        return {"ready": True}

    def get_runtime_snapshot(self) -> dict[str, Any]:
        return {"environments": len(self.store._envs_by_task)}


@pytest.mark.asyncio
async def test_run_runtime_smoke_exercises_isolated_backend_lifecycle(tmp_path: Path):
    runtime_root = tmp_path / "runtime-smoke"
    next_task_id = 40

    def _create_task(**_: Any) -> int:
        nonlocal next_task_id
        next_task_id += 1
        return next_task_id

    with (
        patch("koda.services.runtime.smoke.require_primary_state_backend", return_value=object()),
        patch("koda.services.runtime.smoke.RuntimeController", _FakeRuntimeController),
        patch("koda.services.runtime.smoke.create_task", side_effect=_create_task),
        patch("koda.services.runtime.smoke.browser_manager.stop", new=AsyncMock(return_value=None)),
    ):
        result = await run_runtime_smoke(
            runtime_root=runtime_root,
            db_path=tmp_path / "runtime_smoke.db",
            include_browser_live=False,
            shell="/bin/sh",
        )

    assert result["ok"] is True
    assert result["browser_requested"] is False
    assert len(result["tasks"]) == 2
    workspace_paths = {task["workspace_path"] for task in result["tasks"]}
    assert len(workspace_paths) == 2
    for task in result["tasks"]:
        assert task["worktree_created"] is True
        assert task["final_phase"] == "completed_retained"
        assert task["marker_file_exists"] is True
        assert task["events_log_exists"] is True
        assert task["loop_cycles_exists"] is True
        assert task["terminal_log_ready"] is True
        assert task["checkpoints_count"] >= 1
        assert task["resource_samples_count"] >= 1
        assert "worktree.created" in task["event_types"]
        assert "checkpoint.saved" in task["event_types"]
        assert "resource.sampled" in task["event_types"]
        assert Path(task["task_root"]).exists()


@pytest.mark.asyncio
async def test_run_runtime_smoke_requires_primary_backend_in_postgres_mode(tmp_path: Path):
    runtime_root = tmp_path / "runtime-smoke-primary"

    with patch(
        "koda.services.runtime.smoke.require_primary_state_backend",
        side_effect=RuntimeError("runtime_smoke_primary_backend_unavailable"),
    ):
        result = await run_runtime_smoke(runtime_root=runtime_root, include_browser_live=False, shell="/bin/sh")

    assert result["ok"] is False
    assert result["error"] == "runtime_smoke_primary_backend_unavailable"
    assert not runtime_root.exists()


@pytest.mark.asyncio
async def test_run_runtime_smoke_rejects_repo_root_runtime_residue_in_primary_mode(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with (
        patch("koda.services.runtime.smoke.config_module.SCRIPT_DIR", repo_root),
        patch("koda.services.runtime.smoke.require_primary_state_backend", return_value=object()),
    ):
        result = await run_runtime_smoke(runtime_root=repo_root, include_browser_live=False, shell="/bin/sh")

    assert result["ok"] is False
    assert result["error"] == "runtime_smoke_repo_root_residue_forbidden"
    assert str(repo_root / "smoke-workspace") in result["forbidden_paths"]
    assert str(repo_root / "runtime_smoke.db") in result["forbidden_paths"]
    assert not (repo_root / "smoke-workspace").exists()
    assert not (repo_root / "runtime_smoke.db").exists()


@pytest.mark.asyncio
async def test_run_runtime_smoke_rejects_repo_root_db_residue_in_primary_mode(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_root = tmp_path / "runtime-smoke-primary"
    smoke_db_path = repo_root / "runtime_smoke.db"

    with (
        patch("koda.services.runtime.smoke.config_module.SCRIPT_DIR", repo_root),
        patch("koda.services.runtime.smoke.require_primary_state_backend", return_value=object()),
    ):
        result = await run_runtime_smoke(
            runtime_root=runtime_root,
            db_path=smoke_db_path,
            include_browser_live=False,
            shell="/bin/sh",
        )

    assert result["ok"] is False
    assert result["error"] == "runtime_smoke_repo_root_residue_forbidden"
    assert str(smoke_db_path) in result["forbidden_paths"]
    assert not runtime_root.exists()
    assert not smoke_db_path.exists()
