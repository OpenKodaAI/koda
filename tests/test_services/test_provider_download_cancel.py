from __future__ import annotations

import json
import threading
from typing import Any

import pytest

import koda.control_plane.manager as manager_mod


def _manager() -> manager_mod.ControlPlaneManager:
    return manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)


def _job_row(
    *,
    job_id: str = "job-1",
    provider_id: str = "embedding",
    asset_id: str = "minilm-l6-v2",
    status: str = "running",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": job_id,
        "provider_id": provider_id,
        "asset_id": asset_id,
        "status": status,
        "downloaded_bytes": 128,
        "total_bytes": 1024,
        "progress_percent": 12.5,
        "details_json": json.dumps(details or {"title": "MiniLM"}),
        "created_at": "2026-05-03T10:00:00Z",
        "updated_at": "2026-05-03T10:00:01Z",
        "completed_at": None,
    }


def test_cancel_provider_download_marks_running_job_cancelled(monkeypatch: pytest.MonkeyPatch):
    manager = _manager()
    event = threading.Event()
    row = _job_row()
    manager._provider_download_threads = {}  # type: ignore[attr-defined]
    manager._provider_download_cancel_events = {"job-1": event}  # type: ignore[attr-defined]
    manager._cleanup_provider_download_jobs = lambda: None  # type: ignore[attr-defined]

    def fake_fetch_one(_query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        return row if params == ("job-1", "embedding") else None

    def fake_persist(
        job_id: str,
        *,
        provider_id: str,
        asset_id: str,
        status: str,
        downloaded_bytes: int = 0,
        total_bytes: int = 0,
        details: dict[str, Any] | None = None,
    ) -> None:
        row.update(
            {
                "id": job_id,
                "provider_id": provider_id,
                "asset_id": asset_id,
                "status": status,
                "downloaded_bytes": downloaded_bytes,
                "total_bytes": total_bytes,
                "details_json": json.dumps(details or {}),
                "completed_at": "2026-05-03T10:00:02Z",
            }
        )

    monkeypatch.setattr(manager_mod, "fetch_one", fake_fetch_one)
    manager._persist_provider_download_job = fake_persist  # type: ignore[method-assign]

    payload = manager.cancel_provider_download_job("embedding", "job-1")

    assert event.is_set()
    assert payload["status"] == "cancelled"
    assert payload["downloaded_bytes"] == 128
    assert payload["total_bytes"] == 1024
    assert payload["details"]["message"] == "Download cancelado."
    assert payload["message"] == "Download cancelado."


def test_cancel_provider_download_returns_terminal_job_without_mutation(monkeypatch: pytest.MonkeyPatch):
    manager = _manager()
    event = threading.Event()
    row = _job_row(status="completed", details={"message": "Modelo pronto."})
    manager._provider_download_threads = {}  # type: ignore[attr-defined]
    manager._provider_download_cancel_events = {"job-1": event}  # type: ignore[attr-defined]
    manager._cleanup_provider_download_jobs = lambda: None  # type: ignore[attr-defined]
    persist_calls: list[str] = []

    monkeypatch.setattr(manager_mod, "fetch_one", lambda *_args, **_kwargs: row)
    manager._persist_provider_download_job = lambda *args, **kwargs: persist_calls.append("persist")  # type: ignore[method-assign]

    payload = manager.cancel_provider_download_job("embedding", "job-1")

    assert payload["status"] == "completed"
    assert not event.is_set()
    assert persist_calls == []


def test_get_provider_download_job_supports_embedding(monkeypatch: pytest.MonkeyPatch):
    manager = _manager()
    row = _job_row(status="running")
    manager._cleanup_provider_download_jobs = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setattr(manager_mod, "fetch_one", lambda *_args, **_kwargs: row)

    payload = manager.get_provider_download_job("embedding", "job-1")

    assert payload["provider_id"] == "embedding"
    assert payload["status"] == "running"


def test_kokoro_voice_catalog_includes_active_job(monkeypatch: pytest.MonkeyPatch):
    manager = _manager()
    manager._system_settings_sections = lambda: {"providers": {}}  # type: ignore[method-assign]
    manager._general_ui_meta = lambda *, sections: {}  # type: ignore[method-assign]
    manager._active_provider_download_job = lambda provider, asset: (  # type: ignore[method-assign]
        {"provider_id": provider, "asset_id": asset, "status": "running"} if asset == "pm_alex" else None
    )
    monkeypatch.setattr(
        manager_mod,
        "kokoro_catalog_payload",
        lambda language_id: {
            "items": [
                {
                    "voice_id": "pm_alex",
                    "name": "Alex",
                    "language_id": language_id,
                    "downloaded": False,
                }
            ],
            "available_languages": [],
            "downloaded_voice_ids": [],
        },
    )
    monkeypatch.setattr(
        manager_mod,
        "kokoro_voice_metadata",
        lambda _voice_id: {"voice_id": "pm_alex", "name": "Alex", "language_id": "pt-br"},
    )

    payload = manager.get_kokoro_voice_catalog(language="pt-br")

    assert payload["items"][0]["active_job"]["status"] == "running"


def test_provider_download_runner_honors_cancel_before_network(monkeypatch: pytest.MonkeyPatch):
    manager = _manager()
    event = threading.Event()
    event.set()
    statuses: list[str] = []
    manager._provider_download_threads = {"job-2": threading.current_thread()}  # type: ignore[attr-defined]
    manager._provider_download_cancel_events = {"job-2": event}  # type: ignore[attr-defined]

    def fake_persist(
        _job_id: str,
        *,
        status: str,
        **_kwargs: Any,
    ) -> None:
        statuses.append(status)

    monkeypatch.setattr(manager_mod, "kokoro_model_path", lambda: manager_mod.Path("/tmp/kokoro.onnx"))
    monkeypatch.setattr(
        manager_mod,
        "ensure_kokoro_model",
        lambda **_kwargs: pytest.fail("download should not start after cancellation"),
    )
    manager._persist_provider_download_job = fake_persist  # type: ignore[method-assign]

    manager._run_kokoro_model_download("job-2")

    assert statuses == ["cancelled"]
    assert manager._provider_download_cancel_events == {}
