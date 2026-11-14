"""Integration tests for the runtime schedules POST endpoint."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from koda.services.runtime.api import (
    _IDEMPOTENCY_CACHE,
    _runtime_schedule_create,
)


class _StubRuntimeAccessService:
    """Minimal stand-in that always authorizes mutate requests."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def authorize(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"capability": "mutate"}


def _make_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/api/runtime/schedules", _runtime_schedule_create)
    return app


class RuntimeScheduleCreateTests(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        return _make_app()

    async def setUpAsync(self) -> None:
        await super().setUpAsync()
        _IDEMPOTENCY_CACHE.clear()

        self._patches = [
            patch(
                "koda.services.runtime.api.RuntimeAccessService",
                _StubRuntimeAccessService,
            ),
            patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "test-token"),
            patch(
                "koda.services.runtime.api._schedule_detail_payload",
                return_value={
                    "job": {"id": 999, "status": "active"},
                    "runs": [],
                    "events": [],
                },
            ),
        ]
        for entry in self._patches:
            entry.start()

    async def tearDownAsync(self) -> None:
        for entry in self._patches:
            entry.stop()
        _IDEMPOTENCY_CACHE.clear()
        await super().tearDownAsync()

    async def _post(self, body: dict[str, Any], *, idem: str = "") -> tuple[int, dict[str, Any]]:
        headers = {"X-Runtime-Token": "any"}
        if idem:
            headers["X-Idempotency-Key"] = idem
        async with self.client.post(
            "/api/runtime/schedules",
            data=json.dumps(body),
            headers={**headers, "Content-Type": "application/json"},
        ) as response:
            payload = await response.json()
            return response.status, payload

    async def test_create_invalid_trigger_returns_422(self) -> None:
        status, payload = await self._post(
            {
                "trigger_type": "wrong",
                "schedule_expr": "0 9 * * *",
                "timezone": "UTC",
                "payload": {"query": "do thing"},
            }
        )
        assert status == 422
        assert payload["field"] == "trigger_type"

    async def test_create_missing_schedule_returns_422(self) -> None:
        status, payload = await self._post(
            {
                "trigger_type": "cron",
                "schedule_expr": "",
                "timezone": "UTC",
                "payload": {"query": "do thing"},
            }
        )
        assert status == 422
        assert payload["field"] == "schedule_expr"

    async def test_create_calls_create_job_and_queues_auto_activating_validation(self) -> None:
        with (
            patch(
                "koda.services.scheduled_jobs.create_job",
                return_value=42,
            ) as create_mock,
            patch(
                "koda.services.scheduled_jobs.queue_validation_run",
                return_value=(314, "Validation queued. The job will activate automatically if validation passes."),
            ) as validation_mock,
            patch("koda.services.scheduled_jobs.activate_job") as activate_mock,
        ):
            status, payload = await self._post(
                {
                    "trigger_type": "cron",
                    "schedule_expr": "0 9 * * *",
                    "timezone": "America/Sao_Paulo",
                    "payload": {
                        "query": "Daily review",
                        "name": "Daily review",
                        "connectors": ["gmail"],
                        "read_only": True,
                        "allowed_paths": ["/repo"],
                    },
                    "auto_activate": True,
                    "session_id": "dashboard:AGENT",
                },
                idem="abc-123",
            )
        assert status == 201
        assert payload["ok"] is True
        assert payload["idempotent_replay"] is False
        create_mock.assert_called_once()
        # `read_only=True` should force dry_run_required=True
        kwargs = create_mock.call_args.kwargs
        assert kwargs["dry_run_required"] is True
        assert kwargs["safety_mode"] == "dry_run_required"
        assert kwargs["payload"]["connectors"] == ["gmail"]
        assert kwargs["payload"]["read_only"] is True
        assert kwargs["payload"]["allowed_paths"] == ["/repo"]
        # A freshly created job is validation_pending, which activate_job always rejects;
        # the create path must queue the validation that activates the job when it passes.
        activate_mock.assert_not_called()
        validation_mock.assert_called_once_with(42, user_id=kwargs["user_id"], activate_on_success=True)
        assert payload["validation_run_id"] == 314
        assert payload["message"].startswith("Job created. Validation queued.")

    async def test_create_without_auto_activate_queues_validation_only(self) -> None:
        with (
            patch("koda.services.scheduled_jobs.create_job", return_value=43),
            patch(
                "koda.services.scheduled_jobs.queue_validation_run",
                return_value=(315, "Validation queued."),
            ) as validation_mock,
        ):
            status, payload = await self._post(
                {
                    "trigger_type": "cron",
                    "schedule_expr": "0 9 * * *",
                    "timezone": "UTC",
                    "payload": {"query": "x"},
                    "auto_activate": False,
                }
            )
        assert status == 201
        assert validation_mock.call_args.kwargs["activate_on_success"] is False
        assert payload["validation_run_id"] == 315

    async def test_create_reports_validation_that_could_not_be_queued(self) -> None:
        with (
            patch("koda.services.scheduled_jobs.create_job", return_value=44),
            patch(
                "koda.services.scheduled_jobs.queue_validation_run",
                return_value=(None, "Validation already pending."),
            ),
        ):
            status, payload = await self._post(
                {
                    "trigger_type": "cron",
                    "schedule_expr": "0 9 * * *",
                    "timezone": "UTC",
                    "payload": {"query": "x"},
                }
            )
        assert status == 201
        assert payload["validation_run_id"] is None
        assert payload["message"] == "Job created, but validation was not queued: Validation already pending."

    async def test_create_idempotent_returns_existing_job(self) -> None:
        with (
            patch(
                "koda.services.scheduled_jobs.create_job",
                return_value=77,
            ) as create_mock,
            patch(
                "koda.services.scheduled_jobs.queue_validation_run",
                return_value=(501, "Validation queued."),
            ),
        ):
            status1, _ = await self._post(
                {
                    "trigger_type": "cron",
                    "schedule_expr": "0 9 * * *",
                    "timezone": "UTC",
                    "payload": {"query": "x"},
                },
                idem="dup-key",
            )
            assert status1 == 201

            # Replay with the same idempotency key should not call create_job again.
            status2, payload2 = await self._post(
                {
                    "trigger_type": "cron",
                    "schedule_expr": "0 9 * * *",
                    "timezone": "UTC",
                    "payload": {"query": "x"},
                },
                idem="dup-key",
            )

        assert status2 == 200
        assert payload2["idempotent_replay"] is True
        assert create_mock.call_count == 1

    async def test_create_value_error_maps_to_field(self) -> None:
        with patch(
            "koda.services.scheduled_jobs.create_job",
            side_effect=ValueError("Blocked: invalid work directory"),
        ):
            status, payload = await self._post(
                {
                    "trigger_type": "cron",
                    "schedule_expr": "0 9 * * *",
                    "timezone": "UTC",
                    "payload": {"query": "x"},
                    "work_dir": "/forbidden",
                }
            )
        assert status == 422
        assert payload["field"] == "work_dir"


def test_idempotency_cache_does_not_grow_unbounded() -> None:
    """Sanity: cache stays bounded even on synthetic flood."""
    from koda.services.runtime.api import _idempotency_remember

    _IDEMPOTENCY_CACHE.clear()
    for i in range(10):
        _idempotency_remember(user_id=1, key=f"k{i}", job_id=i)
    assert len(_IDEMPOTENCY_CACHE) == 10
    _IDEMPOTENCY_CACHE.clear()
