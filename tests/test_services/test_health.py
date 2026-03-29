"""Tests for health and readiness handlers."""

import json
import sys
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.health import (
    _database_health,
    _health_handler,
    _ready_handler,
    normalize_runtime_kernel_health,
)


class _RuntimeStub:
    def get_runtime_snapshot(self) -> dict[str, int]:
        return {"active_environments": 2}

    def get_runtime_readiness(self) -> dict[str, object]:
        return {"ready": True, "runtime_root": {"ready": True}}


def _patch_runtime_supervisor_module(supervisor):
    runtime_supervisor_module = ModuleType("koda.knowledge.runtime_supervisor")
    runtime_supervisor_module.get_knowledge_runtime_supervisor = lambda: supervisor
    knowledge_package = ModuleType("koda.knowledge")
    knowledge_package.runtime_supervisor = runtime_supervisor_module
    return patch.dict(
        sys.modules,
        {
            "koda.knowledge": knowledge_package,
            "koda.knowledge.runtime_supervisor": runtime_supervisor_module,
        },
    )


def _patch_scheduled_jobs_module(snapshot: dict[str, object] | None = None):
    scheduled_jobs_module = ModuleType("koda.services.scheduled_jobs")
    scheduled_jobs_module.get_scheduler_snapshot = lambda: dict(snapshot or {})
    return patch.dict(sys.modules, {"koda.services.scheduled_jobs": scheduled_jobs_module})


class TestHealthHandlers:
    def test_normalize_runtime_kernel_health_marks_authoritative_remote_kernel(self):
        payload = normalize_runtime_kernel_health(
            {
                "mode": "rust",
                "transport": "grpc-uds",
                "connected": True,
                "ready": True,
                "status": "running",
                "details": {"authoritative": "true", "production_ready": "true", "maturity": "ga"},
            }
        )

        assert payload["ready"] is True
        assert payload["authoritative"] is True
        assert payload["production_ready"] is True
        assert payload["cutover_allowed"] is True
        assert payload["cutover_state"] == "remote_authoritative"
        assert payload["full_authority"] is True
        assert payload["partial_authority"] is False

    def test_normalize_runtime_kernel_health_defaults_ready_rust_remote_to_authoritative(self):
        payload = normalize_runtime_kernel_health(
            {
                "mode": "rust",
                "transport": "grpc-uds",
                "connected": True,
                "ready": True,
                "status": "running",
            }
        )

        assert payload["ready"] is True
        assert payload["authoritative"] is True
        assert payload["production_ready"] is True
        assert payload["cutover_allowed"] is True
        assert payload["cutover_state"] == "remote_authoritative"
        assert payload["full_authority"] is True
        assert payload["partial_authority"] is False

    def test_database_health_does_not_require_legacy_runtime_state(self):
        backend = AsyncMock()
        backend.health = AsyncMock(return_value={"enabled": True, "ready": True, "pool_active": True})

        with (
            patch("koda.services.health.config_module.STATE_BACKEND", "postgres"),
            patch("koda.services.health.postgres_primary_mode", return_value=True),
            patch("koda.services.health.get_primary_state_backend", return_value=backend),
        ):
            payload = _database_health()
        assert payload["backend"] == "postgres"
        assert payload["ready"] is True
        assert payload["primary_state_backend"]["ready"] is True

    def test_database_health_skips_legacy_runtime_requirement_in_postgres_mode(self):
        backend = AsyncMock()
        backend.health = AsyncMock(return_value={"enabled": True, "ready": True, "pool_active": True})

        with (
            patch("koda.services.health.config_module.STATE_BACKEND", "postgres"),
            patch("koda.services.health.postgres_primary_mode", return_value=True),
            patch("koda.services.health.get_primary_state_backend", return_value=backend),
        ):
            payload = _database_health()

        assert payload["ready"] is True
        assert payload["primary_state_backend"]["ready"] is True

    def test_database_health_ignores_legacy_runtime_state_metadata(self):
        backend = AsyncMock()
        backend.health = AsyncMock(return_value={"enabled": True, "ready": True, "pool_active": True})

        with (
            patch("koda.services.health.config_module.STATE_BACKEND", "postgres"),
            patch("koda.services.health.postgres_primary_mode", return_value=True),
            patch("koda.services.health.get_primary_state_backend", return_value=backend),
        ):
            payload = _database_health()

        assert payload["ready"] is True

    @pytest.mark.asyncio
    async def test_health_includes_provider_snapshot(self):
        backend = AsyncMock()
        backend.health = AsyncMock(return_value={"enabled": True, "ready": True, "pool_active": True})
        background_loops = {
            "started": True,
            "ready": True,
            "critical_ready": True,
            "loops": {"cache_maintenance": {"running": True, "critical": False}},
        }
        with (
            patch("koda.services.health.postgres_primary_mode", return_value=True),
            patch("koda.services.health.get_primary_state_backend", return_value=backend),
            patch("koda.services.health._get_breaker_states", return_value={}),
            patch(
                "koda.services.health.get_runtime_startup_state",
                return_value={"phase": "ready", "details": {}, "expected_background_loops": []},
            ),
            patch("koda.services.health._background_loop_health", return_value=background_loops),
            patch("koda.services.runtime.get_runtime_controller", return_value=_RuntimeStub()),
            patch(
                "koda.services.llm_runner.get_provider_health_snapshot",
                new=AsyncMock(
                    return_value={
                        "claude": {"status": "ready", "can_execute": True},
                        "codex": {"status": "degraded", "can_execute": True},
                    }
                ),
            ),
            _patch_scheduled_jobs_module({"status": "ok"}),
        ):
            response = await _health_handler(object())

        payload = json.loads(response.text)
        assert payload["status"] == "healthy"
        assert payload["providers"]["codex"]["status"] == "degraded"
        assert payload["runtime"]["active_environments"] == 2
        assert payload["runtime_readiness"]["runtime_root"]["ready"] is True
        assert payload["background_loops"]["critical_ready"] is True

    @pytest.mark.asyncio
    async def test_ready_fails_when_no_provider_can_execute(self):
        backend = AsyncMock()
        backend.health = AsyncMock(return_value={"enabled": True, "ready": True, "pool_active": True})
        with (
            patch("koda.services.health.postgres_primary_mode", return_value=True),
            patch("koda.services.health.get_primary_state_backend", return_value=backend),
            patch(
                "koda.services.health.get_runtime_startup_state",
                return_value={"phase": "ready", "details": {}, "expected_background_loops": []},
            ),
            patch(
                "koda.services.llm_runner.get_provider_health_snapshot",
                new=AsyncMock(
                    return_value={
                        "claude": {"status": "unavailable", "can_execute": False},
                        "codex": {"status": "degraded", "can_execute": False},
                    }
                ),
            ),
            _patch_scheduled_jobs_module({"status": "ok"}),
        ):
            response = await _ready_handler(object())

        payload = json.loads(response.text)
        assert response.status == 503
        assert payload["reason"] == "no provider can execute a new turn"

    @pytest.mark.asyncio
    async def test_ready_allows_missing_legacy_runtime_state_in_postgres_mode(self):
        backend = AsyncMock()
        backend.health = AsyncMock(return_value={"enabled": True, "ready": True, "pool_active": True})
        runtime = type(
            "_ReadyRuntimeStub",
            (),
            {
                "get_runtime_snapshot": lambda self: {
                    "active_environments": 0,
                    "runtime_kernel": {"mode": "python", "transport": "in-process", "ready": True},
                },
                "get_runtime_readiness": lambda self: {
                    "ready": True,
                    "reasons": [],
                    "runtime_root": {"ready": True},
                    "runtime_kernel": {"mode": "python", "transport": "in-process", "ready": True},
                },
            },
        )()
        with (
            patch("koda.services.health.config_module.STATE_BACKEND", "postgres"),
            patch("koda.services.health.postgres_primary_mode", return_value=True),
            patch("koda.services.health.get_primary_state_backend", return_value=backend),
            patch(
                "koda.services.health.get_runtime_startup_state",
                return_value={"phase": "ready", "details": {}, "expected_background_loops": []},
            ),
            patch(
                "koda.services.health._background_loop_health",
                return_value={"started": False, "ready": True, "critical_ready": True, "loops": {}},
            ),
            patch(
                "koda.services.llm_runner.get_provider_health_snapshot",
                new=AsyncMock(return_value={"claude": {"status": "ready", "can_execute": True}}),
            ),
            patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
            _patch_runtime_supervisor_module(
                AsyncMock(health=AsyncMock(return_value={"enabled": False, "ready": False}))
            ),
            _patch_scheduled_jobs_module({"status": "ok"}),
        ):
            response = await _ready_handler(object())

        payload = json.loads(response.text)
        assert response.status == 200
        assert payload["status"] == "ready"

    @pytest.mark.asyncio
    async def test_ready_fails_when_critical_background_loop_is_unhealthy(self):
        backend = AsyncMock()
        backend.health = AsyncMock(return_value={"enabled": True, "ready": True, "pool_active": True})
        with (
            patch("koda.services.health.postgres_primary_mode", return_value=True),
            patch("koda.services.health.get_primary_state_backend", return_value=backend),
            patch(
                "koda.services.health.get_runtime_startup_state",
                return_value={"phase": "ready", "details": {}, "expected_background_loops": []},
            ),
            patch(
                "koda.services.health._background_loop_health",
                return_value={
                    "started": True,
                    "ready": False,
                    "critical_ready": False,
                    "degraded_loops": ["critical_loop"],
                    "loops": {"critical_loop": {"critical": True, "running": False}},
                },
            ),
            patch(
                "koda.services.llm_runner.get_provider_health_snapshot",
                new=AsyncMock(return_value={"claude": {"status": "ready", "can_execute": True}}),
            ),
            patch("koda.services.runtime.get_runtime_controller", return_value=_RuntimeStub()),
            _patch_runtime_supervisor_module(
                AsyncMock(health=AsyncMock(return_value={"enabled": False, "ready": False}))
            ),
            _patch_scheduled_jobs_module({"status": "ok"}),
        ):
            response = await _ready_handler(object())

        payload = json.loads(response.text)
        assert response.status == 503
        assert payload["reason"] == "background loop supervision unavailable"
        assert payload["background_loops"]["critical_ready"] is False

    @pytest.mark.asyncio
    async def test_ready_fails_when_runtime_backend_is_not_ready(self):
        backend = AsyncMock()
        backend.health = AsyncMock(return_value={"enabled": True, "ready": True, "pool_active": True})
        runtime = type(
            "_FailingRuntimeStub",
            (),
            {
                "get_runtime_snapshot": lambda self: {"active_environments": 0},
                "get_runtime_readiness": lambda self: {
                    "ready": False,
                    "reasons": ["browser_live_unavailable"],
                    "runtime_root": {"ready": True},
                },
            },
        )()
        with (
            patch("koda.services.health.postgres_primary_mode", return_value=True),
            patch("koda.services.health.get_primary_state_backend", return_value=backend),
            patch(
                "koda.services.health.get_runtime_startup_state",
                return_value={"phase": "ready", "details": {}, "expected_background_loops": []},
            ),
            patch(
                "koda.services.llm_runner.get_provider_health_snapshot",
                new=AsyncMock(return_value={"claude": {"status": "ready", "can_execute": True}}),
            ),
            patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
            _patch_scheduled_jobs_module({"status": "ok"}),
        ):
            response = await _ready_handler(object())

        payload = json.loads(response.text)
        assert response.status == 503
        assert payload["reason"] == "runtime backend unavailable"
        assert payload["runtime_readiness"]["ready"] is False

    @pytest.mark.asyncio
    async def test_ready_fails_with_kernel_specific_reason(self):
        backend = AsyncMock()
        backend.health = AsyncMock(return_value={"enabled": True, "ready": True, "pool_active": True})
        runtime = type(
            "_KernelFailingRuntimeStub",
            (),
            {
                "get_runtime_snapshot": lambda self: {
                    "active_environments": 0,
                    "runtime_kernel": {"mode": "rust", "transport": "grpc-uds", "ready": False},
                },
                "get_runtime_readiness": lambda self: {
                    "ready": False,
                    "reasons": ["runtime_kernel_unavailable"],
                    "runtime_root": {"ready": True},
                    "runtime_kernel": {"mode": "rust", "transport": "grpc-uds", "ready": False},
                },
            },
        )()
        with (
            patch("koda.services.health.postgres_primary_mode", return_value=True),
            patch("koda.services.health.get_primary_state_backend", return_value=backend),
            patch(
                "koda.services.health.get_runtime_startup_state",
                return_value={"phase": "ready", "details": {}, "expected_background_loops": []},
            ),
            patch(
                "koda.services.llm_runner.get_provider_health_snapshot",
                new=AsyncMock(return_value={"claude": {"status": "ready", "can_execute": True}}),
            ),
            patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
            _patch_scheduled_jobs_module({"status": "ok"}),
        ):
            response = await _ready_handler(object())

        payload = json.loads(response.text)
        assert response.status == 503
        assert payload["reason"] == "runtime kernel unavailable"
        assert payload["runtime_readiness"]["runtime_kernel"]["transport"] == "grpc-uds"

    @pytest.mark.asyncio
    async def test_ready_fails_with_kernel_startup_failure_reason(self):
        backend = AsyncMock()
        backend.health = AsyncMock(return_value={"enabled": True, "ready": True, "pool_active": True})
        runtime = type(
            "_KernelStartupFailingRuntimeStub",
            (),
            {
                "get_runtime_snapshot": lambda self: {
                    "active_environments": 0,
                    "runtime_kernel": {
                        "mode": "rust",
                        "transport": "grpc-uds",
                        "ready": False,
                        "startup_error": "grpc_runtime_kernel_client_requires_runtime_stubs",
                    },
                },
                "get_runtime_readiness": lambda self: {
                    "ready": False,
                    "reasons": ["runtime_kernel_unavailable"],
                    "runtime_root": {"ready": True},
                    "runtime_kernel": {
                        "mode": "rust",
                        "transport": "grpc-uds",
                        "ready": False,
                        "startup_error": "grpc_runtime_kernel_client_requires_runtime_stubs",
                    },
                },
            },
        )()
        with (
            patch("koda.services.health.postgres_primary_mode", return_value=True),
            patch("koda.services.health.get_primary_state_backend", return_value=backend),
            patch(
                "koda.services.health.get_runtime_startup_state",
                return_value={"phase": "ready", "details": {}, "expected_background_loops": []},
            ),
            patch(
                "koda.services.health._background_loop_health",
                return_value={"started": True, "ready": True, "critical_ready": True, "loops": {}},
            ),
            patch(
                "koda.services.llm_runner.get_provider_health_snapshot",
                new=AsyncMock(return_value={"claude": {"status": "ready", "can_execute": True}}),
            ),
            patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
            _patch_scheduled_jobs_module({"status": "ok"}),
        ):
            response = await _ready_handler(object())

        payload = json.loads(response.text)
        assert response.status == 503
        assert payload["reason"] == "runtime kernel startup failed"
        assert payload["runtime_readiness"]["runtime_kernel"]["failure_reason"] == "runtime_kernel_startup_failed"

    @pytest.mark.asyncio
    async def test_ready_fails_while_startup_is_bootstrapping(self):
        with patch(
            "koda.services.health.get_runtime_startup_state",
            return_value={"phase": "bootstrapping", "details": {}, "expected_background_loops": []},
        ):
            response = await _ready_handler(object())

        payload = json.loads(response.text)
        assert response.status == 503
        assert payload["reason"] == "startup_incomplete"
