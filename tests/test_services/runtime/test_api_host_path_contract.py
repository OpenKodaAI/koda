"""No runtime GET route or WebSocket snapshot sends a host path (D-357, D-358).

A runtime API response is an explicit projection of named fields: a host path is relative to the
task's runtime directory, or null, and free-form kernel or controller metadata is not forwarded.

The store holds a task, its environment, a kernel-forwarded browser session, a terminal and
runtime events, each with absolute paths under the runtime root and the state root. Every GET
route the runtime registers is called (the inventory test fails when a route is added without
being called here), and every WebSocket's first messages are read. No body may contain the
runtime root, the state root or the task directory.

The real controller logic runs over a stub store. Not covered, and listed in the D-358 record:
``GET /api/runtime/readiness``, the operator diagnostics surface, which reports the runtime root's
path, the kernel's health and its last answer per operation; and the artifact, checkpoint and
warning rows, which this test does not seed.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from koda.services.runtime.api import setup_runtime_routes
from koda.services.runtime.controller import RuntimeController
from koda.services.runtime.events import RuntimeEventBroker

_TASK_ID = 7
_ENV_ID = 3
_TERMINAL_ID = 5
_HEADERS = {"X-Runtime-Token": "signed", "X-Koda-Attach-Token": "attach-token"}
# Operator diagnostics, not task data: it reports the runtime root's path by design (see the module
# docstring and the D-358 record).
_NOT_COVERED = {"/api/runtime/readiness"}


class _AllowAll:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def authorize(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"capability": "read"}


class _Roots:
    def __init__(self, tmp_path: Path) -> None:
        self.runtime = tmp_path / "runtime"
        self.state = tmp_path / "state"
        self.task = self.runtime / "tasks" / str(_TASK_ID)
        self.workspace = self.runtime / "worktrees" / "task-7-build"

    def all(self) -> tuple[Path, ...]:
        return (self.runtime, self.state, self.task)


def _event(seq: int, event_type: str, payload: dict[str, Any], refs: list[str] | None = None) -> dict[str, Any]:
    return {
        "task_id": _TASK_ID,
        "env_id": _ENV_ID,
        "attempt": None,
        "phase": "provisioning",
        "severity": "info",
        "resource_snapshot_ref": None,
        "seq": seq,
        "type": event_type,
        "ts": "2026-11-15T00:00:00+00:00",
        "payload": payload,
        "artifact_refs": refs or [],
    }


class _Store:
    """The rows ``PostgresRuntimeStore`` returns for one task, with absolute host paths."""

    def __init__(self, roots: _Roots) -> None:
        browser_dir = roots.task / "browser"
        stdout_log = roots.task / "stdout" / "build.log"
        self.task = {
            "id": _TASK_ID,
            "user_id": 1,
            "chat_id": 1,
            "status": "running",
            "query_text": "build the app",
            "work_dir": "/srv/project",
            "env_id": _ENV_ID,
            "current_phase": "executing",
        }
        self.environment = {
            "id": _ENV_ID,
            "task_id": _TASK_ID,
            "classification": "heavy",
            "environment_kind": "dev_worktree_browser",
            "isolation": "worktree",
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(roots.workspace),
            "runtime_dir": str(roots.task),
            "base_work_dir": str(roots.state / "agents" / "A" / "workspace"),
            "source_root_path": str(roots.state / "agents" / "A" / "workspace"),
            "source_root_exists": True,
            "branch_name": "task/7-build",
            "checkpoint_status": "saved",
            "checkpoint_path": str(roots.task / "checkpoints" / "1"),
            "browser_transport": "novnc",
            "novnc_port": 6081,
        }
        session_metadata = {
            "requested_transport": "novnc",
            "xvfb_log": str(browser_dir / "xvfb.log"),
            "websockify_log": str(browser_dir / "websockify.log"),
            "runtime_dir": str(browser_dir),
            "kernel_socket": str(roots.state / "kernel.sock"),
        }
        live_session = {
            "session_id": "kbs-7",
            "scope_id": _TASK_ID,
            "transport": "novnc",
            "status": "running",
            "runtime_dir": str(browser_dir),
            "display_id": 99,
            "vnc_port": 5901,
            "novnc_port": 6081,
            "missing_binaries": [],
            "forwarded": True,
            "metadata": session_metadata,
        }
        self.browser_sessions = [
            {
                "id": 1,
                "task_id": _TASK_ID,
                "env_id": _ENV_ID,
                "scope_id": _TASK_ID,
                "transport": "novnc",
                "status": "running",
                "display_id": 99,
                "vnc_port": 5901,
                "novnc_port": 6081,
                "metadata": live_session,
                "created_at": "2026-11-15T00:00:00+00:00",
                "updated_at": "2026-11-15T00:00:00+00:00",
                "ended_at": None,
            }
        ]
        self.terminals = [
            {
                "id": _TERMINAL_ID,
                "task_id": _TASK_ID,
                "env_id": _ENV_ID,
                "terminal_kind": "process",
                "label": "build",
                "path": str(stdout_log),
                "stream_path": str(stdout_log),
                "interactive": False,
                "cursor_offset": 0,
                "last_offset": 0,
                "created_at": "2026-11-15T00:00:00+00:00",
                "updated_at": "2026-11-15T00:00:00+00:00",
            }
        ]
        frame = str(browser_dir / "frame_1.png")
        self.events = [
            _event(1, "env.provisioning.started", {"base_work_dir": self.environment["base_work_dir"]}),
            _event(
                2,
                "runtime_kernel.create_environment",
                {
                    "operation": "create_environment",
                    "ok": True,
                    "workspace_path": str(roots.workspace),
                    "metadata_path": str(roots.task / "worktree.json"),
                    "runtime_kernel": {"details": {"socket_path": str(roots.state / "kernel.sock")}},
                },
            ),
            _event(
                3,
                "worktree.created",
                {
                    "workspace_path": str(roots.workspace),
                    "branch_name": "task/7-build",
                    "created": True,
                    "mode": "worktree",
                    "metadata_path": str(roots.task / "worktree.json"),
                },
                [str(roots.task / "worktree.json")],
            ),
            _event(4, "browser.started", live_session),
            _event(5, "runtime_kernel.start_browser_session", {"operation": "start_browser_session", **live_session}),
            _event(6, "env.provisioning.finished", {"workspace_path": str(roots.workspace)}),
            _event(7, "browser.frame", {"path": frame}, [frame]),
            _event(8, "browser.video_ready", {"path": str(browser_dir / "s.webm")}, [str(browser_dir / "s.webm")]),
            _event(9, "browser.trace_ready", {"path": str(browser_dir / "t.zip")}, [str(browser_dir / "t.zip")]),
            _event(
                10,
                "checkpoint.saved",
                {"checkpoint_id": 1, "checkpoint_dir": str(roots.task / "checkpoints" / "1")},
                [str(roots.task / "checkpoints" / "1" / "manifest.json")],
            ),
            _event(11, "plan.updated", {"goal": "build"}, [str(roots.task / "decision_trace.jsonl")]),
            # As record_warning writes it for a failed required kernel operation: its details are
            # the kernel operation record, with the kernel's health and answer.
            _event(
                12,
                "warning.issued",
                {
                    "warning_type": "runtime_kernel_restore_checkpoint_failed",
                    "message": "checkpoint missing",
                    "details": {
                        "operation": "restore_checkpoint",
                        "required": True,
                        "ok": False,
                        "runtime_kernel": {
                            "details": {
                                "runtime_root": str(roots.runtime),
                                "socket_path": str(roots.state / "kernel.sock"),
                            }
                        },
                        "cutover": {"socket": str(roots.state / "kernel.sock")},
                        "checkpoint_dir": str(roots.task / "checkpoints" / "1"),
                    },
                },
            ),
            # A voice response is persisted under the task's artifacts directory.
            _event(
                13,
                "artifact_ready",
                {
                    "artifact": {
                        "id": "12",
                        "kind": "audio",
                        "label": "voice-response-7.ogg",
                        "download_url": "/api/runtime/artifacts/12/download",
                        "path": str(roots.task / "artifacts" / "voice-response-7.ogg"),
                    }
                },
                [str(roots.task / "artifacts" / "voice-response-7.ogg")],
            ),
        ]

    def get_task_runtime(self, task_id: int) -> dict[str, Any] | None:
        return dict(self.task) if task_id == _TASK_ID else None

    def get_environment(self, env_id: int) -> dict[str, Any] | None:
        return dict(self.environment) if env_id == _ENV_ID else None

    def get_environment_by_task(self, task_id: int) -> dict[str, Any] | None:
        return dict(self.environment) if task_id == _TASK_ID else None

    def list_environments(self) -> list[dict[str, Any]]:
        return [dict(self.environment)]

    def list_browser_sessions(self, task_id: int) -> list[dict[str, Any]]:
        return [dict(row) for row in self.browser_sessions]

    def list_terminals(self, task_id: int) -> list[dict[str, Any]]:
        return [dict(row) for row in self.terminals]

    def list_events(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [dict(event) for event in self.events]

    def list_attach_sessions(self, task_id: int) -> list[dict[str, Any]]:
        return [{"id": 1, "task_id": _TASK_ID, "attach_kind": "terminal", "token": "secret-token"}]

    def get_artifact(self, artifact_id: int) -> dict[str, Any] | None:
        return None

    def list_runtime_queues(self) -> list[dict[str, Any]]:
        return []

    def list_artifacts(self, task_id: int) -> list[dict[str, Any]]:
        return []

    def list_checkpoints(self, task_id: int) -> list[dict[str, Any]]:
        return []

    def list_service_endpoints(self, task_id: int) -> list[dict[str, Any]]:
        return []

    def list_resource_samples(self, task_id: int, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def list_loop_cycles(self, task_id: int) -> list[dict[str, Any]]:
        return []

    def list_guardrail_hits(self, task_id: int) -> list[dict[str, Any]]:
        return []

    def list_warnings(self, task_id: int) -> list[dict[str, Any]]:
        return []


def _controller(roots: _Roots) -> RuntimeController:
    """The real controller methods over the stub store, without starting a kernel."""
    controller = RuntimeController.__new__(RuntimeController)
    store = _Store(roots)
    controller.runtime_root = roots.runtime
    controller.store = store  # type: ignore[assignment]
    controller.events = RuntimeEventBroker(store, roots.runtime)  # type: ignore[arg-type]
    controller._runtime_kernel_operations = {}
    controller._application = None

    async def kernel_snapshot(**_kwargs: Any) -> dict[str, Any]:
        return {}

    async def terminal_stream(**kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "chunk", "terminal_id": kwargs["terminal_id"], "offset": 5, "data": "built"}

    async def close_attach_session(**_kwargs: Any) -> None:
        return None

    controller.get_runtime_kernel_snapshot = kernel_snapshot  # type: ignore[method-assign]
    controller.iter_terminal_stream = terminal_stream  # type: ignore[method-assign,assignment]
    controller.close_attach_session = close_attach_session  # type: ignore[method-assign,assignment]
    controller._runtime_kernel_terminal_authoritative = lambda *_args, **_kwargs: False  # type: ignore[method-assign]
    controller.authorize_attach = lambda **_kwargs: {  # type: ignore[method-assign]
        "task_id": _TASK_ID,
        "terminal_id": _TERMINAL_ID,
        "can_write": 0,
    }
    return controller


@pytest.fixture
def roots(tmp_path: Path) -> _Roots:
    roots = _Roots(tmp_path)
    for directory in ("browser", "stdout", "checkpoints/1"):
        (roots.task / directory).mkdir(parents=True)
    (roots.task / "stdout" / "build.log").write_text("built\n")
    roots.workspace.mkdir(parents=True)
    (roots.workspace / "README.md").write_text("build the app\n")
    roots.state.mkdir()
    return roots


@pytest.fixture
def app() -> web.Application:
    app = web.Application()
    setup_runtime_routes(app)
    return app


@pytest.fixture
def isolated_task_detail() -> Iterator[None]:
    """The task detail's knowledge, asset and child-run lookups fail fast; each is optional there."""
    unavailable = {
        name: None
        for name in (
            "koda.state.knowledge_governance_store",
            "koda.knowledge.repository",
            "koda.knowledge.storage_v2",
            "koda.services.agent_asset_registry",
            "koda.services.child_runs",
        )
    }
    with (
        patch.dict(sys.modules, unavailable),
        patch("koda.services.run_graph_store.load_persisted_run_graph", return_value=None),
        patch("koda.services.scheduled_jobs.list_all_jobs", return_value=[]),
        patch("koda.services.scheduled_jobs.get_job_detail", return_value=None),
    ):
        yield


@pytest.fixture
async def client(app: web.Application, roots: _Roots, isolated_task_detail: None) -> AsyncIterator[TestClient]:
    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=_controller(roots)),
        patch("koda.services.runtime.api.RuntimeAccessService", _AllowAll),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
    ):
        async with TestClient(TestServer(app)) as test_client:
            yield test_client


_GET_ROUTES = {
    "/api/runtime/queues": "/api/runtime/queues",
    "/api/runtime/environments": "/api/runtime/environments",
    "/api/runtime/environments/{env_id}": f"/api/runtime/environments/{_ENV_ID}",
    "/api/runtime/schedules": "/api/runtime/schedules",
    "/api/runtime/schedules/preview": "/api/runtime/schedules/preview?trigger_type=cron&schedule_expr=0+9+*+*+*",
    "/api/runtime/schedules/{job_id}": "/api/runtime/schedules/1",
    "/api/runtime/tasks/{task_id}": f"/api/runtime/tasks/{_TASK_ID}",
    "/api/runtime/tasks/{task_id}/run-graph": f"/api/runtime/tasks/{_TASK_ID}/run-graph",
    "/api/runtime/tasks/{task_id}/replay": f"/api/runtime/tasks/{_TASK_ID}/replay",
    "/api/runtime/tasks/{task_id}/sandbox-doctor": f"/api/runtime/tasks/{_TASK_ID}/sandbox-doctor",
    "/api/runtime/tasks/{task_id}/events": f"/api/runtime/tasks/{_TASK_ID}/events",
    "/api/runtime/tasks/{task_id}/artifacts": f"/api/runtime/tasks/{_TASK_ID}/artifacts",
    "/api/runtime/artifacts/{artifact_id}/download": "/api/runtime/artifacts/1/download",
    "/api/runtime/tasks/{task_id}/checkpoints": f"/api/runtime/tasks/{_TASK_ID}/checkpoints",
    "/api/runtime/tasks/{task_id}/terminals": f"/api/runtime/tasks/{_TASK_ID}/terminals",
    "/api/runtime/tasks/{task_id}/browser": f"/api/runtime/tasks/{_TASK_ID}/browser",
    "/api/runtime/tasks/{task_id}/browser/screenshot": f"/api/runtime/tasks/{_TASK_ID}/browser/screenshot",
    "/api/runtime/tasks/{task_id}/workspace/tree": f"/api/runtime/tasks/{_TASK_ID}/workspace/tree",
    "/api/runtime/tasks/{task_id}/workspace/file": f"/api/runtime/tasks/{_TASK_ID}/workspace/file?path=README.md",
    "/api/runtime/tasks/{task_id}/workspace/search": f"/api/runtime/tasks/{_TASK_ID}/workspace/search?q=build",
    "/api/runtime/tasks/{task_id}/workspace/status": f"/api/runtime/tasks/{_TASK_ID}/workspace/status",
    "/api/runtime/tasks/{task_id}/workspace/diff": f"/api/runtime/tasks/{_TASK_ID}/workspace/diff",
    "/api/runtime/tasks/{task_id}/services": f"/api/runtime/tasks/{_TASK_ID}/services",
    "/api/runtime/tasks/{task_id}/resources": f"/api/runtime/tasks/{_TASK_ID}/resources",
    "/api/runtime/tasks/{task_id}/loop": f"/api/runtime/tasks/{_TASK_ID}/loop",
    "/api/runtime/tasks/{task_id}/sessions": f"/api/runtime/tasks/{_TASK_ID}/sessions",
}
_EVENT_COUNT = 13
_STREAMS = {
    # route: (URL, messages to read)
    "/api/runtime/stream": (f"/api/runtime/stream?task_id={_TASK_ID}", _EVENT_COUNT),
    "/ws/runtime": (f"/ws/runtime?task_id={_TASK_ID}", _EVENT_COUNT),
    "/ws/runtime/events": (f"/ws/runtime/events?task_id={_TASK_ID}", _EVENT_COUNT),
    "/ws/runtime/tasks/{task_id}/terminals/{terminal_id}": (
        f"/ws/runtime/tasks/{_TASK_ID}/terminals/{_TERMINAL_ID}",
        1,
    ),
    "/ws/runtime/tasks/{task_id}/browser": (f"/ws/runtime/tasks/{_TASK_ID}/browser", 1),
}


def _assert_no_host_path(route: str, body: str, roots: _Roots) -> None:
    for root in roots.all():
        assert str(root) not in body, f"{route} sends {root}"
    assert "_log" not in body, f"{route} sends a browser log path"
    assert "secret-token" not in body, f"{route} sends an attach token"


def test_every_runtime_get_route_is_called(app: web.Application) -> None:
    registered = {
        route.resource.canonical
        for route in app.router.routes()
        if route.method == "GET" and route.resource is not None
    }
    assert registered == set(_GET_ROUTES) | set(_STREAMS) | _NOT_COVERED


async def test_no_get_route_sends_a_host_path(client: TestClient, roots: _Roots) -> None:
    for route, url in _GET_ROUTES.items():
        response = await client.get(url, headers=_HEADERS)
        body = await response.text()
        assert response.status < 500, f"{route}: {response.status} {body}"
        _assert_no_host_path(route, body, roots)


async def test_the_routes_that_carry_the_rows_send_them_projected(client: TestClient) -> None:
    detail = json.loads(await (await client.get(f"/api/runtime/tasks/{_TASK_ID}", headers=_HEADERS)).text())
    environment = detail["environment"]
    assert (environment["runtime_dir"], environment["checkpoint_path"]) == (".", "checkpoints/1")
    # A directory outside the task is named, not located: the task room shows it (D-358).
    assert (environment["workspace_path"], environment["base_work_dir"], environment["source_root_path"]) == (
        "task-7-build",
        "workspace",
        "workspace",
    )
    assert (environment["source_root_exists"], environment["branch_name"]) == (True, "task/7-build")
    assert len(detail["run_graph"]["nodes"]) > _EVENT_COUNT
    environments = json.loads(await (await client.get("/api/runtime/environments", headers=_HEADERS)).text())
    assert environments["items"] == [environment]
    terminals = json.loads(
        await (await client.get(f"/api/runtime/tasks/{_TASK_ID}/terminals", headers=_HEADERS)).text()
    )
    assert [(row["path"], row["stream_path"], row["preview"]) for row in terminals["items"]] == [
        ("stdout/build.log", "stdout/build.log", "built\n")
    ]
    sessions = json.loads(await (await client.get(f"/api/runtime/tasks/{_TASK_ID}/sessions", headers=_HEADERS)).text())
    assert sessions["terminals"] == [{key: value for key, value in terminals["items"][0].items() if key != "preview"}]


async def test_no_stream_sends_a_host_path(client: TestClient, roots: _Roots) -> None:
    for route, (url, count) in _STREAMS.items():
        if route.startswith("/ws/"):
            async with client.ws_connect(url, headers=_HEADERS) as ws:
                messages = [str((await ws.receive(timeout=5)).data) for _ in range(count)]
        else:
            response = await client.get(url, headers=_HEADERS)
            messages = [
                (await asyncio.wait_for(response.content.readuntil(b"\n\n"), timeout=5)).decode() for _ in range(count)
            ]
            response.close()
        assert all(message.strip() for message in messages), route
        _assert_no_host_path(route, "".join(messages), roots)
