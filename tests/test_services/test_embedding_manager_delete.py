"""End-to-end style tests for ControlPlaneManager.delete_embedding_model_asset.

These tests stub out the three external surfaces the method touches —
catalog deletion (filesystem), DB persistence, and the in-flight download
job lookup — and verify each branch of the auto-switch logic the operator
relies on:

  1. deleting a non-active model: state is left alone.
  2. deleting the active model when another is installed: auto-switch.
  3. deleting the active model with nothing else installed: clear selection.
  4. unknown model_id: ValueError.
  5. in-flight download: ValueError.
"""

from __future__ import annotations

from typing import Any

import pytest

import koda.control_plane.manager as manager_mod


def _manager() -> manager_mod.ControlPlaneManager:
    """Construct a bare manager instance — no DB / no init — so we can wire
    only the dependencies the method under test actually reaches for."""
    return manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)


def _wire_manager(
    monkeypatch: pytest.MonkeyPatch,
    *,
    selected_id: str,
    installed_ids: set[str],
    in_flight_for: str | None = None,
) -> tuple[manager_mod.ControlPlaneManager, list[tuple[str, dict[str, Any]]]]:
    """Plug in just enough so ``delete_embedding_model_asset`` can run.

    Returns ``(manager, persisted_calls)`` where ``persisted_calls`` captures
    every ``execute(...)`` invocation so tests can assert what was written
    to ``cp_global_sections``.
    """
    persisted: list[tuple[str, dict[str, Any]]] = []

    def _execute(query: str, params: tuple = ()):
        # Decode the second positional ("data_json") so tests can inspect
        # the memory section after the auto-switch logic ran.
        try:
            import json

            data = json.loads(params[1])
        except Exception:
            data = {}
        persisted.append((query, data))
        return 1

    monkeypatch.setattr(manager_mod, "execute", _execute)
    monkeypatch.setattr(manager_mod, "now_iso", lambda: "2026-05-02T15:00:00Z")
    monkeypatch.setattr(manager_mod, "_embedding_model_installed", lambda mid: mid in installed_ids)

    deleted_ids: list[str] = []

    def _fake_delete_model(model_id: str) -> dict[str, Any]:
        deleted_ids.append(model_id)
        installed_ids.discard(model_id)
        return {"model_id": model_id, "removed": True, "bytes_freed": 100}

    monkeypatch.setattr(manager_mod, "_delete_embedding_model", _fake_delete_model)

    manager = _manager()
    manager._provider_download_threads = {}  # type: ignore[attr-defined]
    manager._system_settings_sections = lambda: {  # type: ignore[attr-defined]
        "memory": {"embedding_model": selected_id} if selected_id else {}
    }
    manager._selected_embedding_model_id = lambda: selected_id  # type: ignore[attr-defined]
    manager._active_provider_download_job = lambda provider, asset: (  # type: ignore[attr-defined]
        {"job_id": "x", "status": "running"} if asset == in_flight_for else None
    )
    # The method calls get_embedding_model_catalog at the end — stub it to a
    # constant payload so we exercise the side-effect path, not the catalog.
    manager.get_embedding_model_catalog = lambda: {  # type: ignore[attr-defined]
        "items": [],
        "active": "",
        "default": "",
    }

    # Make sure the runtime cache reset import doesn't blow up.
    monkeypatch.setattr(
        "koda.utils.embeddings.reset_embedding_load_cache",
        lambda *_args, **_kwargs: None,
    )

    return manager, persisted


def test_delete_non_active_model_leaves_selection_untouched(monkeypatch):
    """Deleting a non-active model should NOT touch cp_global_sections at all."""
    catalog_keys = list(manager_mod._EMBEDDING_CATALOG.keys())
    assert len(catalog_keys) >= 2
    active_id, victim_id = catalog_keys[0], catalog_keys[1]
    manager, persisted = _wire_manager(
        monkeypatch,
        selected_id=active_id,
        installed_ids={active_id, victim_id},
    )

    payload = manager.delete_embedding_model_asset(victim_id)

    assert payload == {"items": [], "active": "", "default": ""}
    assert persisted == [], "non-active deletion must not write to cp_global_sections"


def test_delete_active_model_auto_switches_to_another_installed(monkeypatch):
    """When the active model is deleted and another is installed, persist the
    other model id as the new active."""
    catalog_keys = list(manager_mod._EMBEDDING_CATALOG.keys())
    assert len(catalog_keys) >= 2
    active_id = catalog_keys[0]
    other_installed = catalog_keys[1]
    manager, persisted = _wire_manager(
        monkeypatch,
        selected_id=active_id,
        installed_ids={active_id, other_installed},
    )

    manager.delete_embedding_model_asset(active_id)

    assert len(persisted) == 1, "exactly one DB write expected"
    _query, data = persisted[0]
    assert data == {"embedding_model": other_installed}, "auto-switch should pick the next installed catalog entry"


def test_delete_active_model_with_nothing_else_clears_selection(monkeypatch):
    """When the active model is deleted and nothing else is installed, drop
    the operator selection entirely so the resolver falls back to env/default."""
    catalog_keys = list(manager_mod._EMBEDDING_CATALOG.keys())
    active_id = catalog_keys[0]
    manager, persisted = _wire_manager(
        monkeypatch,
        selected_id=active_id,
        installed_ids={active_id},  # only the active one is installed
    )

    manager.delete_embedding_model_asset(active_id)

    assert len(persisted) == 1
    _query, data = persisted[0]
    assert "embedding_model" not in data, "with nothing else installed the operator selection must be cleared"


def test_delete_unknown_model_id_raises(monkeypatch):
    catalog_keys = list(manager_mod._EMBEDDING_CATALOG.keys())
    manager, _persisted = _wire_manager(
        monkeypatch,
        selected_id=catalog_keys[0],
        installed_ids=set(),
    )
    with pytest.raises(ValueError, match="unknown embedding model"):
        manager.delete_embedding_model_asset("definitely-not-a-real-model-id")


def test_delete_with_in_flight_download_raises(monkeypatch):
    catalog_keys = list(manager_mod._EMBEDDING_CATALOG.keys())
    victim_id = catalog_keys[0]
    manager, _persisted = _wire_manager(
        monkeypatch,
        selected_id=catalog_keys[1],
        installed_ids={victim_id},
        in_flight_for=victim_id,
    )
    with pytest.raises(ValueError, match="download in progress"):
        manager.delete_embedding_model_asset(victim_id)
