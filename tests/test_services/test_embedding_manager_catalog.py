"""Tests for the control-plane embedding model catalog wrapper."""

from __future__ import annotations

import koda.control_plane.manager as manager_mod


def test_embedding_catalog_survives_active_job_probe_failure(monkeypatch):
    manager = manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)
    manager._selected_embedding_model_id = lambda: "paraphrase-multilingual-minilm"  # type: ignore[attr-defined]

    monkeypatch.setattr(
        manager_mod,
        "_embedding_catalog_payload",
        lambda active_model_id: {
            "items": [
                {
                    "id": "paraphrase-multilingual-minilm",
                    "installed": False,
                    "disk_bytes": 0,
                },
            ],
            "active": active_model_id,
            "default": "paraphrase-multilingual-minilm",
        },
    )

    def _raise_active_job(_provider_id: str, _asset_id: str):
        raise RuntimeError("download job table unavailable")

    manager._active_provider_download_job = _raise_active_job  # type: ignore[attr-defined]

    payload = manager.get_embedding_model_catalog()

    assert payload["items"][0]["active_job"] is None
    assert payload["active"] == "paraphrase-multilingual-minilm"
