"""Tests for runtime browser API helpers and routes."""

import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.runtime.api import (
    _runtime_readiness,
    _runtime_task_browser,
    _runtime_task_browser_screenshot,
    _runtime_task_detail,
)
from koda.services.runtime_access_service import RuntimeAccessService

_UNSET = object()


def _patch_knowledge_modules(
    *,
    supervisor: object | None = None,
    repository_cls: object | None = None,
    storage_cls: object | None = None,
):
    knowledge_package = ModuleType("koda.knowledge")
    knowledge_package.__path__ = []  # type: ignore[attr-defined]
    modules: dict[str, ModuleType] = {"koda.knowledge": knowledge_package}

    if supervisor is not None:
        runtime_supervisor_module = ModuleType("koda.knowledge.runtime_supervisor")
        runtime_supervisor_module.get_knowledge_runtime_supervisor = lambda *_args, **_kwargs: supervisor
        knowledge_package.runtime_supervisor = runtime_supervisor_module
        modules["koda.knowledge.runtime_supervisor"] = runtime_supervisor_module

    if repository_cls is not None:
        repository_module = ModuleType("koda.knowledge.repository")
        repository_module.KnowledgeRepository = repository_cls
        knowledge_package.repository = repository_module
        modules["koda.knowledge.repository"] = repository_module

    if storage_cls is not None:
        storage_module = ModuleType("koda.knowledge.storage_v2")
        storage_module.KnowledgeStorageV2 = storage_cls
        knowledge_package.storage_v2 = storage_module
        modules["koda.knowledge.storage_v2"] = storage_module

    presentation_module = ModuleType("koda.knowledge.presentation")

    def _redact_sensitive(value):
        sensitive_keys = {"extracted_text", "source_path", "source_url"}
        if isinstance(value, dict):
            payload = {}
            for key, item in value.items():
                payload[key] = "[redacted]" if key in sensitive_keys and item else _redact_sensitive(item)
            return payload
        if isinstance(value, list):
            return [_redact_sensitive(item) for item in value]
        return value

    def redact_runtime_knowledge_payload(
        *,
        episode,
        retrieval_trace,
        answer_trace,
        artifact_evidence,
        include_sensitive,
    ):
        if include_sensitive:
            return {
                "episode": deepcopy(episode),
                "retrieval_trace": deepcopy(retrieval_trace),
                "answer_trace": deepcopy(answer_trace),
                "artifact_evidence": deepcopy(artifact_evidence),
            }

        redacted_episode = _redact_sensitive(deepcopy(episode)) if episode else None
        redacted_trace = _redact_sensitive(deepcopy(retrieval_trace)) if retrieval_trace else None
        redacted_answer_trace = _redact_sensitive(deepcopy(answer_trace)) if answer_trace else None
        redacted_artifacts = [_redact_sensitive(dict(item)) for item in artifact_evidence]

        plan = dict((redacted_episode or {}).get("plan") or {})
        retrieval_bundle = (
            dict(plan.get("retrieval_bundle") or {}) if isinstance(plan.get("retrieval_bundle"), dict) else {}
        )
        plan_answer_trace = dict(plan.get("answer_trace") or {}) if isinstance(plan.get("answer_trace"), dict) else {}
        effective_answer_trace = redacted_answer_trace or plan_answer_trace
        judge_result = dict(effective_answer_trace.get("judge_result") or {}) if effective_answer_trace else {}
        if not judge_result and isinstance(plan.get("judge_result"), dict):
            judge_result = dict(plan.get("judge_result") or {})
        authoritative_sources = list(retrieval_bundle.get("authoritative_evidence") or [])
        if effective_answer_trace and (
            effective_answer_trace.get("authoritative_sources") or not authoritative_sources
        ):
            authoritative_sources = list(effective_answer_trace.get("authoritative_sources") or [])
        supporting_sources = list(retrieval_bundle.get("supporting_evidence") or [])
        if effective_answer_trace and (effective_answer_trace.get("supporting_sources") or not supporting_sources):
            supporting_sources = list(effective_answer_trace.get("supporting_sources") or [])
        uncertainty = {
            "level": str(retrieval_bundle.get("uncertainty_level") or ""),
            "notes": list(retrieval_bundle.get("uncertainty_notes") or []),
        }
        if effective_answer_trace and (effective_answer_trace.get("uncertainty") or not uncertainty["level"]):
            uncertainty = dict(effective_answer_trace.get("uncertainty") or uncertainty)
        return {
            "episode": redacted_episode,
            "retrieval_trace": redacted_trace,
            "artifact_evidence": redacted_artifacts,
            "retrieval_bundle": retrieval_bundle,
            "answer_trace": effective_answer_trace,
            "judge_result": judge_result,
            "authoritative_sources": authoritative_sources,
            "supporting_sources": supporting_sources,
            "uncertainty": uncertainty,
        }

    presentation_module.redact_runtime_knowledge_payload = redact_runtime_knowledge_payload
    knowledge_package.presentation = presentation_module
    modules["koda.knowledge.presentation"] = presentation_module

    return patch.dict(sys.modules, modules)


def _request(*, task_id: int | None = None, headers: dict[str, str] | None = None, query: dict[str, str] | None = None):
    match_info = {"task_id": str(task_id)} if task_id is not None else {}
    normalized_headers = dict(headers or {})
    runtime_token = str(normalized_headers.get("X-Runtime-Token") or "").strip()
    if runtime_token:
        capabilities = tuple(
            str(item).strip()
            for item in normalized_headers.pop("X-Runtime-Capabilities", "read,mutate,attach").split(",")
            if str(item).strip()
        )
        _, signed_runtime_token = RuntimeAccessService(runtime_token).issue(
            agent_scope="",
            capabilities=capabilities,
            sensitive_allowed=True,
        )
        normalized_headers["X-Runtime-Token"] = signed_runtime_token
    return SimpleNamespace(match_info=match_info, headers=normalized_headers, query=query or {})


def _patch_agent_asset_registry(registry: object):
    module = ModuleType("koda.services.agent_asset_registry")
    module.get_agent_asset_registry = lambda *_args, **_kwargs: registry
    return patch.dict(sys.modules, {"koda.services.agent_asset_registry": module})


class _StoreStub:
    def __init__(
        self,
        *,
        env: dict[str, object] | None = None,
        artifacts: list[dict[str, object]] | None = None,
    ) -> None:
        self._env = env
        self._artifacts = artifacts or []

    def get_environment_by_task(self, task_id: int) -> dict[str, object] | None:
        return self._env

    def list_artifacts(self, task_id: int) -> list[dict[str, object]]:
        return list(self._artifacts)

    def list_browser_sessions(self, task_id: int) -> list[dict[str, object]]:
        return []

    def get_task_runtime(self, task_id: int) -> dict[str, object] | None:
        return {"id": task_id, "status": "running"}

    def list_warnings(self, task_id: int) -> list[dict[str, object]]:
        return []


class _ControllerStub:
    def __init__(
        self,
        *,
        runtime_root: Path,
        env: dict[str, object] | None = None,
        artifacts: list[dict[str, object]] | None = None,
        browser_snapshot: dict[str, object] | None = None,
    ) -> None:
        self.runtime_root = runtime_root
        self.store = _StoreStub(env=env, artifacts=artifacts)
        self._browser_snapshot = browser_snapshot or {}

    def get_browser_snapshot(self, task_id: int) -> dict[str, object]:
        return dict(self._browser_snapshot)

    def list_guardrail_hits(self, task_id: int) -> list[dict[str, object]]:
        return []

    def get_runtime_readiness(self) -> dict[str, object]:
        return {"status": "ready", "ready": True}


class _KnowledgeStorageStub:
    def __init__(
        self,
        *,
        retrieval_trace: dict[str, object] | None = None,
        retrieval_traces: list[dict[str, object]] | None = None,
        answer_trace: object = _UNSET,
        artifact_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self._retrieval_trace = retrieval_trace
        self._retrieval_traces = retrieval_traces or [{"id": 91, "trace_role": "primary"}]
        self._answer_trace = {"id": 44} if answer_trace is _UNSET else answer_trace
        self._artifact_rows = artifact_rows or [{"artifact_id": "art-1"}]

    def primary_read_enabled(self) -> bool:
        return True

    async def get_retrieval_trace_async(self, trace_id: int) -> dict[str, object] | None:
        return self._retrieval_trace

    async def list_retrieval_traces_async(self, *, task_id: int | None = None, limit: int = 50):
        rows: list[dict[str, object]] = []
        for row in self._retrieval_traces[:limit]:
            item = dict(row)
            item.setdefault("task_id", task_id)
            rows.append(item)
        return rows

    async def get_latest_answer_trace_async(self, task_id: int):
        if self._answer_trace is None:
            return None
        payload = dict(self._answer_trace)
        payload.setdefault("task_id", task_id)
        return payload

    async def list_artifact_evidence_rows_async(self, **kwargs):
        return [dict(item) for item in self._artifact_rows]


@pytest.mark.asyncio
async def test_runtime_task_browser_exposes_preview_url(tmp_path):
    runtime_root = tmp_path / "runtime"
    preview_path = runtime_root / "tasks" / "7" / "artifacts" / "preview.png"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"\x89PNG\r\n")
    controller = _ControllerStub(
        runtime_root=runtime_root,
        env={"task_id": 7, "browser_scope_id": 7},
        artifacts=[{"path": str(preview_path)}],
        browser_snapshot={"scope_id": 7, "status": "running", "transport": "local_headful"},
    )
    request = _request(task_id=7, headers={"X-Runtime-Token": "secret"})

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
    ):
        response = await _runtime_task_browser(request)

    payload = json.loads(response.text)
    assert payload["browser"]["screenshot_url"] == "/api/runtime/tasks/7/browser/screenshot"
    assert payload["browser"]["preview_url"] == "/api/runtime/tasks/7/browser/screenshot"
    assert payload["browser"]["preview_available"] is True
    assert payload["browser"]["preview_path"] == str(preview_path)


@pytest.mark.asyncio
async def test_runtime_readiness_includes_knowledge_v2_health(tmp_path):
    controller = _ControllerStub(runtime_root=tmp_path / "runtime")
    request = _request(headers={"X-Runtime-Token": "secret"})
    supervisor = SimpleNamespace(
        health=AsyncMock(
            return_value={
                "storage_mode": "primary",
                "primary_read_enabled": True,
                "external_read_enabled": True,
                "primary_backend": {"enabled": True, "ready": True, "pool_active": True},
                "object_store": {"enabled": True, "ready": True, "mode": "local"},
                "ingest_worker": {
                    "enabled": True,
                    "ready": True,
                    "queue": {"enabled": True, "ready": True, "queue_depth": 0},
                },
            }
        ),
    )
    background_loops = {
        "started": True,
        "ready": True,
        "critical_ready": True,
        "loops": {"temp_cleanup": {"running": True, "critical": False}},
    }

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        _patch_knowledge_modules(supervisor=supervisor),
        patch(
            "koda.services.health.get_runtime_startup_state",
            return_value={"phase": "ready", "details": {}, "expected_background_loops": []},
        ),
        patch(
            "koda.services.lifecycle_supervisor.get_background_loop_supervisor",
            return_value=SimpleNamespace(snapshot=lambda: background_loops),
        ),
    ):
        response = await _runtime_readiness(request)

    payload = json.loads(response.text)
    assert payload["status"] == "ready"
    assert payload["ready"] is True
    assert payload["background_loops"]["critical_ready"] is True
    assert payload["knowledge_v2"]["storage_mode"] == "primary"
    assert payload["knowledge_v2"]["primary_backend"]["ready"] is True


@pytest.mark.asyncio
async def test_runtime_readiness_is_not_ready_while_startup_is_bootstrapping(tmp_path):
    controller = _ControllerStub(runtime_root=tmp_path / "runtime")
    request = _request(headers={"X-Runtime-Token": "secret"})

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch(
            "koda.services.health.get_runtime_startup_state",
            return_value={"phase": "bootstrapping", "details": {}, "expected_background_loops": []},
        ),
        patch(
            "koda.services.lifecycle_supervisor.get_background_loop_supervisor",
            return_value=SimpleNamespace(
                snapshot=lambda: {"started": False, "ready": True, "critical_ready": True, "loops": {}}
            ),
        ),
        _patch_knowledge_modules(
            supervisor=SimpleNamespace(
                health=AsyncMock(
                    return_value={
                        "storage_mode": "primary",
                        "primary_read_enabled": True,
                        "external_read_enabled": True,
                        "primary_backend": {"enabled": True, "ready": True, "pool_active": True},
                        "object_store": {"enabled": True, "ready": True, "mode": "local"},
                        "ingest_worker": {
                            "enabled": True,
                            "ready": True,
                            "queue": {"enabled": True, "ready": True, "queue_depth": 0},
                        },
                    }
                )
            )
        ),
    ):
        response = await _runtime_readiness(request)

    payload = json.loads(response.text)
    assert payload["startup"]["phase"] == "bootstrapping"
    assert payload["ready"] is False


@pytest.mark.asyncio
async def test_runtime_readiness_surfaces_kernel_reason(tmp_path):
    controller = type(
        "_KernelReadinessStub",
        (),
        {
            "get_runtime_readiness": lambda self: {
                "ready": False,
                "reasons": ["runtime_kernel_unavailable"],
                "runtime_root": {"ready": True},
                "runtime_kernel": {"mode": "rust", "transport": "grpc-uds", "ready": False},
            }
        },
    )()
    request = _request(headers={"X-Runtime-Token": "secret"})

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch(
            "koda.services.health.get_runtime_startup_state",
            return_value={"phase": "ready", "details": {}, "expected_background_loops": []},
        ),
        patch(
            "koda.services.lifecycle_supervisor.get_background_loop_supervisor",
            return_value=SimpleNamespace(
                snapshot=lambda: {"started": True, "ready": True, "critical_ready": True, "loops": {}}
            ),
        ),
        _patch_knowledge_modules(
            supervisor=SimpleNamespace(
                health=AsyncMock(
                    return_value={
                        "storage_mode": "primary",
                        "primary_read_enabled": True,
                        "external_read_enabled": True,
                        "primary_backend": {"enabled": True, "ready": True, "pool_active": True},
                        "object_store": {"enabled": True, "ready": True, "mode": "local"},
                        "ingest_worker": {
                            "enabled": True,
                            "ready": True,
                            "queue": {"enabled": True, "ready": True, "queue_depth": 0},
                        },
                    }
                )
            )
        ),
    ):
        response = await _runtime_readiness(request)

    payload = json.loads(response.text)
    assert payload["status"] == "not_ready"
    assert payload["reason"] == "runtime_kernel_unavailable"
    assert payload["runtime_kernel"]["transport"] == "grpc-uds"


@pytest.mark.asyncio
async def test_runtime_readiness_inherits_kernel_health_from_snapshot(tmp_path):
    controller = type(
        "_KernelSnapshotOnlyStub",
        (),
        {
            "get_runtime_health_snapshot": lambda self: {
                "runtime_kernel": {
                    "mode": "rust",
                    "transport": "grpc-uds",
                    "ready": False,
                    "startup_error": "grpc_runtime_kernel_client_requires_runtime_stubs",
                }
            },
            "get_runtime_readiness": lambda self: {
                "ready": True,
                "reasons": [],
                "runtime_root": {"ready": True},
            },
        },
    )()
    request = _request(headers={"X-Runtime-Token": "secret"})

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch(
            "koda.services.health.get_runtime_startup_state",
            return_value={"phase": "ready", "details": {}, "expected_background_loops": []},
        ),
        patch(
            "koda.services.lifecycle_supervisor.get_background_loop_supervisor",
            return_value=SimpleNamespace(
                snapshot=lambda: {"started": True, "ready": True, "critical_ready": True, "loops": {}}
            ),
        ),
        _patch_knowledge_modules(
            supervisor=SimpleNamespace(
                health=AsyncMock(
                    return_value={
                        "storage_mode": "primary",
                        "primary_read_enabled": True,
                        "external_read_enabled": True,
                        "primary_backend": {"enabled": True, "ready": True, "pool_active": True},
                        "object_store": {"enabled": True, "ready": True, "mode": "local"},
                        "ingest_worker": {
                            "enabled": True,
                            "ready": True,
                            "queue": {"enabled": True, "ready": True, "queue_depth": 0},
                        },
                    }
                )
            )
        ),
    ):
        response = await _runtime_readiness(request)

    payload = json.loads(response.text)
    assert payload["status"] == "not_ready"
    assert payload["reason"] == "runtime_kernel_unavailable"
    assert payload["runtime_kernel"]["failure_reason"] == "runtime_kernel_startup_failed"
    assert payload["runtime"]["runtime_kernel"]["startup_error"] == "grpc_runtime_kernel_client_requires_runtime_stubs"


@pytest.mark.asyncio
async def test_runtime_task_detail_skips_legacy_local_knowledge_in_postgres_primary(tmp_path):
    controller = _ControllerStub(runtime_root=tmp_path / "runtime")
    request = _request(task_id=12, headers={"X-Runtime-Token": "secret"})

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch("koda.state.knowledge_governance_store.get_latest_execution_episode", return_value=None),
        _patch_knowledge_modules(
            repository_cls=MagicMock(),
            storage_cls=MagicMock(return_value=_KnowledgeStorageStub()),
        ),
        _patch_agent_asset_registry(SimpleNamespace(search=AsyncMock(return_value=[]))),
    ):
        response = await _runtime_task_detail(request)

    payload = json.loads(response.text)
    assert response.status == 200
    assert payload["knowledge"]["retrieval_trace"]["id"] == 91
    assert payload["knowledge"]["answer_trace"]["id"] == 44


@pytest.mark.asyncio
async def test_runtime_task_browser_marks_persisted_only_session_without_preview_as_unavailable(tmp_path):
    runtime_root = tmp_path / "runtime"
    controller = _ControllerStub(
        runtime_root=runtime_root,
        env={"task_id": 70, "browser_scope_id": 70},
        browser_snapshot={
            "scope_id": 70,
            "status": "closed",
            "session_persisted_only": True,
        },
    )
    request = _request(task_id=70, headers={"X-Runtime-Token": "secret"})

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
    ):
        response = await _runtime_task_browser(request)

    payload = json.loads(response.text)
    assert payload["browser"]["preview_available"] is False


@pytest.mark.asyncio
async def test_runtime_task_browser_screenshot_returns_preview_png(tmp_path):
    runtime_root = tmp_path / "runtime"
    preview_path = runtime_root / "tasks" / "8" / "artifacts" / "preview.png"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"\x89PNG\r\nlive")
    controller = _ControllerStub(
        runtime_root=runtime_root,
        env={"task_id": 8, "browser_scope_id": 8, "current_phase": "executing"},
        artifacts=[{"path": str(preview_path)}],
        browser_snapshot={"scope_id": 8, "status": "running", "transport": "local_headful"},
    )
    request = _request(task_id=8, headers={"X-Runtime-Token": "secret"})

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
    ):
        response = await _runtime_task_browser_screenshot(request)

    assert response.status == 200
    assert Path(str(response._path)) == preview_path


@pytest.mark.asyncio
async def test_runtime_task_browser_screenshot_falls_back_to_saved_preview(tmp_path):
    runtime_root = tmp_path / "runtime"
    preview_path = runtime_root / "tasks" / "9" / "artifacts" / "preview.png"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"\x89PNG\r\nsaved")
    controller = _ControllerStub(
        runtime_root=runtime_root,
        env={"task_id": 9, "browser_scope_id": 9},
        artifacts=[{"path": str(preview_path)}],
        browser_snapshot={"scope_id": 9, "status": "running", "transport": "local_headful"},
    )
    request = _request(task_id=9, headers={"X-Runtime-Token": "secret"})

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
    ):
        response = await _runtime_task_browser_screenshot(request)

    assert response.status == 200
    assert Path(str(response._path)) == preview_path


@pytest.mark.asyncio
async def test_runtime_task_browser_screenshot_prefers_saved_preview_when_browser_is_blank(tmp_path):
    runtime_root = tmp_path / "runtime"
    preview_path = runtime_root / "tasks" / "10" / "browser" / "preview.png"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"\x89PNG\r\nsaved")
    controller = _ControllerStub(
        runtime_root=runtime_root,
        env={"task_id": 10, "browser_scope_id": 10},
        artifacts=[{"path": str(preview_path)}],
        browser_snapshot={
            "scope_id": 10,
            "status": "running",
            "transport": "local_headful",
            "url": "about:blank",
        },
    )
    request = _request(task_id=10, headers={"X-Runtime-Token": "secret"})

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
    ):
        response = await _runtime_task_browser_screenshot(request)

    assert response.status == 200
    assert Path(str(response._path)) == preview_path


@pytest.mark.asyncio
async def test_runtime_task_browser_screenshot_does_not_spawn_live_browser_for_persisted_only_session(tmp_path):
    runtime_root = tmp_path / "runtime"
    controller = _ControllerStub(
        runtime_root=runtime_root,
        env={"task_id": 11, "browser_scope_id": 11, "current_phase": "cleaned"},
        browser_snapshot={
            "scope_id": 11,
            "status": "closed",
            "session_persisted_only": True,
        },
    )
    request = _request(task_id=11, headers={"X-Runtime-Token": "secret"})

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
    ):
        response = await _runtime_task_browser_screenshot(request)

    assert response.status == 404


@pytest.mark.asyncio
async def test_runtime_task_detail_requires_token(tmp_path):
    controller = _ControllerStub(runtime_root=tmp_path / "runtime")
    request = _request(task_id=15)

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
    ):
        response = await _runtime_task_detail(request)

    assert response.status == 403


@pytest.mark.asyncio
async def test_runtime_readiness_rejects_raw_secret_header(tmp_path):
    request = SimpleNamespace(match_info={}, headers={"X-Runtime-Token": "secret"}, query={})

    with (
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch(
            "koda.services.runtime.api.get_runtime_controller",
            return_value=_ControllerStub(runtime_root=tmp_path / "runtime"),
        ),
    ):
        response = await _runtime_readiness(request)

    assert response.status == 403
    payload = json.loads(response.text)
    assert payload["error"] == "invalid runtime token"


@pytest.mark.asyncio
async def test_runtime_task_detail_redacts_sensitive_knowledge_by_default(tmp_path):
    controller = _ControllerStub(runtime_root=tmp_path / "runtime")
    request = _request(task_id=16, headers={"X-Runtime-Token": "secret"})
    storage = _KnowledgeStorageStub(
        retrieval_traces=[{"id": 9, "hits": []}],
        artifact_rows=[
            {
                "evidence_key": "e1",
                "extracted_text": "secret text",
                "source_path": "/tmp/private.png",
                "source_url": "https://secret",
            }
        ],
    )

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch("koda.state.knowledge_governance_store.get_latest_execution_episode", return_value=None),
        _patch_knowledge_modules(repository_cls=MagicMock(), storage_cls=MagicMock(return_value=storage)),
        _patch_agent_asset_registry(SimpleNamespace(search=AsyncMock(return_value=[]))),
    ):
        response = await _runtime_task_detail(request)

    payload = json.loads(response.text)
    assert payload["knowledge"]["artifact_evidence"][0]["extracted_text"] != "secret text"
    assert payload["knowledge"]["artifact_evidence"][0]["source_path"] != "/tmp/private.png"


@pytest.mark.asyncio
async def test_runtime_task_detail_returns_sensitive_knowledge_when_requested(tmp_path):
    controller = _ControllerStub(runtime_root=tmp_path / "runtime")
    _, scope_token = RuntimeAccessService("secret").issue(
        agent_scope="AGENT_A",
        sensitive_allowed=True,
    )
    request = _request(
        task_id=17,
        headers={"X-Runtime-Token": "secret", "X-Runtime-Access-Scope": scope_token},
        query={"include_sensitive": "true"},
    )
    storage = _KnowledgeStorageStub(
        retrieval_traces=[{"id": 9, "hits": []}],
        artifact_rows=[
            {
                "evidence_key": "e1",
                "extracted_text": "secret text",
                "source_path": "/tmp/private.png",
                "source_url": "https://secret",
            }
        ],
    )

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch("koda.services.runtime.api.AGENT_ID", "AGENT_A"),
        patch("koda.state.knowledge_governance_store.get_latest_execution_episode", return_value=None),
        _patch_knowledge_modules(repository_cls=MagicMock(), storage_cls=MagicMock(return_value=storage)),
        _patch_agent_asset_registry(SimpleNamespace(search=AsyncMock(return_value=[]))),
    ):
        response = await _runtime_task_detail(request)

    payload = json.loads(response.text)
    assert payload["knowledge"]["artifact_evidence"][0]["extracted_text"] == "secret text"
    assert payload["knowledge"]["artifact_evidence"][0]["source_path"] == "/tmp/private.png"


@pytest.mark.asyncio
async def test_runtime_task_detail_blocks_sensitive_knowledge_without_scope_token(tmp_path):
    controller = _ControllerStub(runtime_root=tmp_path / "runtime")
    request = _request(
        task_id=17,
        headers={"X-Runtime-Token": "secret"},
        query={"include_sensitive": "true"},
    )

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch("koda.services.runtime.api.AGENT_ID", "AGENT_A"),
    ):
        response = await _runtime_task_detail(request)

    assert response.status == 403
    assert "scoped token" in response.text


@pytest.mark.asyncio
async def test_runtime_task_detail_exposes_answer_trace_and_retrieval_bundle(tmp_path):
    controller = _ControllerStub(runtime_root=tmp_path / "runtime")
    request = _request(task_id=18, headers={"X-Runtime-Token": "secret"})
    episode = {
        "retrieval_trace_id": 9,
        "plan": {
            "retrieval_bundle": {
                "authoritative_evidence": [{"source_label": "policy:deploy"}],
                "supporting_evidence": [{"ref_key": "artifact-1"}],
                "uncertainty_level": "medium",
                "uncertainty_notes": ["open grounded conflicts remain"],
            },
            "answer_trace": {"answer_text": "safe answer"},
            "judge_result": {"status": "passed"},
        },
    }

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch("koda.state.knowledge_governance_store.get_latest_execution_episode", return_value=episode),
        _patch_knowledge_modules(
            repository_cls=MagicMock(),
            storage_cls=MagicMock(
                return_value=_KnowledgeStorageStub(
                    retrieval_trace={"id": 9, "hits": []},
                    answer_trace=None,
                    artifact_rows=[],
                )
            ),
        ),
        _patch_agent_asset_registry(SimpleNamespace(search=AsyncMock(return_value=[]))),
    ):
        response = await _runtime_task_detail(request)

    payload = json.loads(response.text)
    assert payload["knowledge"]["answer_trace"]["answer_text"] == "safe answer"
    assert payload["knowledge"]["judge_result"]["status"] == "passed"
    assert payload["knowledge"]["authoritative_sources"][0]["source_label"] == "policy:deploy"
    assert payload["knowledge"]["uncertainty"]["level"] == "medium"


@pytest.mark.asyncio
async def test_runtime_task_detail_prefers_persisted_answer_trace_over_plan_snapshot(tmp_path):
    controller = _ControllerStub(runtime_root=tmp_path / "runtime")
    request = _request(task_id=19, headers={"X-Runtime-Token": "secret"})
    episode = {
        "retrieval_trace_id": 9,
        "plan": {
            "retrieval_bundle": {
                "authoritative_evidence": [{"source_label": "policy:plan"}],
                "uncertainty_level": "low",
                "uncertainty_notes": [],
            },
            "answer_trace": {"answer_text": "plan answer"},
            "judge_result": {"status": "passed"},
        },
    }

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch("koda.state.knowledge_governance_store.get_latest_execution_episode", return_value=episode),
        _patch_knowledge_modules(
            repository_cls=MagicMock(),
            storage_cls=MagicMock(
                return_value=_KnowledgeStorageStub(
                    retrieval_trace={"id": 9, "hits": []},
                    answer_trace={
                        "answer_text": "persisted answer",
                        "judge_result": {"status": "needs_review"},
                        "authoritative_sources": [{"source_label": "policy:db"}],
                        "supporting_sources": [{"ref_key": "artifact-db"}],
                        "uncertainty": {"level": "high", "notes": ["db-backed uncertainty"]},
                    },
                    artifact_rows=[],
                )
            ),
        ),
        _patch_agent_asset_registry(SimpleNamespace(search=AsyncMock(return_value=[]))),
    ):
        response = await _runtime_task_detail(request)

    payload = json.loads(response.text)
    assert payload["knowledge"]["answer_trace"]["answer_text"] == "persisted answer"
    assert payload["knowledge"]["judge_result"]["status"] == "needs_review"
    assert payload["knowledge"]["authoritative_sources"][0]["source_label"] == "policy:db"
    assert payload["knowledge"]["uncertainty"]["level"] == "high"


@pytest.mark.asyncio
async def test_runtime_task_detail_exposes_asset_refs(tmp_path):
    controller = _ControllerStub(runtime_root=tmp_path / "runtime")
    request = _request(task_id=21, headers={"X-Runtime-Token": "secret"})
    controller.store.get_task_runtime = lambda task_id: {  # type: ignore[method-assign]
        "id": task_id,
        "status": "running",
        "agent_id": "AGENT_A",
        "user_id": 123,
        "query_text": "reuse rollback helper",
        "work_dir": "/tmp/services/payments",
    }
    registry = SimpleNamespace(
        search=AsyncMock(return_value=[{"asset_key": "script:7", "asset_kind": "script", "title": "rollback helper"}])
    )

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch("koda.state.knowledge_governance_store.get_latest_execution_episode", return_value=None),
        _patch_knowledge_modules(
            repository_cls=MagicMock(),
            storage_cls=MagicMock(
                return_value=_KnowledgeStorageStub(retrieval_traces=[], answer_trace=None, artifact_rows=[])
            ),
        ),
        _patch_agent_asset_registry(registry),
    ):
        response = await _runtime_task_detail(request)

    payload = json.loads(response.text)
    assert payload["asset_refs"][0]["asset_key"] == "script:7"


@pytest.mark.asyncio
async def test_runtime_task_detail_keeps_episode_context_when_primary_knowledge_read_fails(tmp_path):
    controller = _ControllerStub(runtime_root=tmp_path / "runtime")
    request = _request(task_id=20, headers={"X-Runtime-Token": "secret"})
    episode = {
        "retrieval_trace_id": 9,
        "source_refs": [{"source_path": "/tmp/file.md"}],
        "plan": {
            "answer_trace": {"answer_text": "episode answer"},
            "judge_result": {"status": "passed"},
        },
    }

    class _FailingStorage:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def primary_read_enabled(self) -> bool:
            return True

        async def get_retrieval_trace_async(self, _trace_id: int) -> dict[str, object] | None:
            raise RuntimeError("primary trace unavailable")

        async def list_retrieval_traces_async(self, *, task_id: int | None = None, limit: int = 50):
            return []

        async def get_latest_answer_trace_async(self, _task_id: int) -> dict[str, object] | None:
            raise RuntimeError("primary answer unavailable")

        async def list_artifact_evidence_rows_async(self, **_kwargs) -> list[dict[str, object]]:
            raise RuntimeError("primary artifact unavailable")

    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch("koda.state.knowledge_governance_store.get_latest_execution_episode", return_value=episode),
        _patch_knowledge_modules(repository_cls=MagicMock(), storage_cls=_FailingStorage),
        _patch_agent_asset_registry(SimpleNamespace(search=AsyncMock(return_value=[]))),
    ):
        response = await _runtime_task_detail(request)

    payload = json.loads(response.text)
    assert payload["knowledge"]["episode"]["retrieval_trace_id"] == 9
    assert payload["knowledge"]["answer_trace"]["answer_text"] == "episode answer"
    assert payload["knowledge"]["retrieval_trace"] is None
    assert payload["knowledge"]["artifact_evidence"] == []
