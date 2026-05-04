"""Tests for the curated embedding catalog + filesystem helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from koda.services import embedding_catalog as catalog_module
from koda.services.embedding_catalog import (
    CATALOG,
    DEFAULT_MODEL_ID,
    EmbeddingModelDefinition,
    catalog_payload,
    delete_model,
    is_model_installed,
    model_disk_bytes,
    model_local_path,
    model_payload,
)


def test_catalog_has_default_model():
    """The DEFAULT_MODEL_ID points at a real catalog entry — the *recommended*
    starting point, even though nothing is pre-installed."""
    assert DEFAULT_MODEL_ID in CATALOG
    assert isinstance(CATALOG[DEFAULT_MODEL_ID], EmbeddingModelDefinition)


def test_catalog_entries_are_unique_and_well_formed():
    seen_ids: set[str] = set()
    seen_repos: set[str] = set()
    for model_id, definition in CATALOG.items():
        assert model_id == definition.id, "key must equal definition.id"
        assert model_id not in seen_ids
        seen_ids.add(model_id)
        assert "/" in definition.repo_id, "repo_id should be 'org/name'"
        assert definition.repo_id not in seen_repos
        seen_repos.add(definition.repo_id)
        assert 0 < definition.size_mb <= 5000, "size_mb in sane range"
        assert definition.dimension > 0
        assert 1 <= definition.quality <= 5
        assert 1 <= definition.speed <= 5
        assert isinstance(definition, EmbeddingModelDefinition)


def test_no_model_marked_default_install():
    """Koda no longer ships any model pre-installed — operators opt in
    explicitly via the UI to keep a fresh install lightweight."""
    defaults = [m.id for m in CATALOG.values() if m.is_default_install]
    assert defaults == [], "no model should be flagged as pre-installed"


def test_model_local_path_resolves_for_known_id():
    path = model_local_path(DEFAULT_MODEL_ID)
    assert isinstance(path, Path)
    # The cache path uses the HF naming convention `models--<org>--<name>`.
    assert path.name.startswith("models--")


def test_model_local_path_unknown_returns_none():
    assert model_local_path("nope-not-a-model") is None


def test_is_model_installed_false_for_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog_module, "_hf_cache_dir", lambda: tmp_path)
    assert is_model_installed(DEFAULT_MODEL_ID) is False


def test_is_model_installed_true_when_safetensors_present(tmp_path, monkeypatch):
    definition = CATALOG[DEFAULT_MODEL_ID]
    safe_repo = definition.repo_id.replace("/", "--")
    snapshot = tmp_path / f"models--{safe_repo}" / "snapshots" / "abc"
    snapshot.mkdir(parents=True)
    (snapshot / "model.safetensors").write_bytes(b"x")
    blobs = tmp_path / f"models--{safe_repo}" / "blobs"
    blobs.mkdir(parents=True)
    monkeypatch.setattr(catalog_module, "_hf_cache_dir", lambda: tmp_path)
    assert is_model_installed(DEFAULT_MODEL_ID) is True


def test_is_model_installed_false_when_incomplete_blob_exists(tmp_path, monkeypatch):
    definition = CATALOG[DEFAULT_MODEL_ID]
    safe_repo = definition.repo_id.replace("/", "--")
    snapshot = tmp_path / f"models--{safe_repo}" / "snapshots" / "abc"
    snapshot.mkdir(parents=True)
    (snapshot / "model.safetensors").write_bytes(b"x")
    blobs = tmp_path / f"models--{safe_repo}" / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "stuck.incomplete").write_bytes(b"")
    monkeypatch.setattr(catalog_module, "_hf_cache_dir", lambda: tmp_path)
    assert is_model_installed(DEFAULT_MODEL_ID) is False, "incomplete blob blocks install"


def test_model_disk_bytes_sums_blob_sizes(tmp_path, monkeypatch):
    definition = CATALOG[DEFAULT_MODEL_ID]
    safe_repo = definition.repo_id.replace("/", "--")
    blobs = tmp_path / f"models--{safe_repo}" / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "a.safetensors").write_bytes(b"a" * 100)
    (blobs / "b.json").write_bytes(b"b" * 50)
    monkeypatch.setattr(catalog_module, "_hf_cache_dir", lambda: tmp_path)
    assert model_disk_bytes(DEFAULT_MODEL_ID) == 150


def test_model_payload_includes_status_fields():
    payload = model_payload(DEFAULT_MODEL_ID)
    for key in (
        "id",
        "repo_id",
        "title",
        "description",
        "size_mb",
        "dimension",
        "languages",
        "quality",
        "speed",
        "hardware_hint",
        "multilingual",
        "is_default_install",
        "installed",
        "disk_bytes",
    ):
        assert key in payload, f"missing key {key!r}"


def test_model_payload_survives_install_status_probe_failure(monkeypatch):
    monkeypatch.setattr(
        catalog_module,
        "is_model_installed",
        lambda _id: (_ for _ in ()).throw(OSError("cache busy")),
    )

    payload = model_payload(DEFAULT_MODEL_ID)

    assert payload["installed"] is False
    assert payload["disk_bytes"] == 0


def test_model_payload_survives_disk_usage_probe_failure(monkeypatch):
    monkeypatch.setattr(catalog_module, "is_model_installed", lambda _id: True)
    monkeypatch.setattr(
        catalog_module,
        "model_disk_bytes",
        lambda _id: (_ for _ in ()).throw(OSError("cache disappeared")),
    )

    payload = model_payload(DEFAULT_MODEL_ID)

    assert payload["installed"] is True
    assert payload["disk_bytes"] == 0


def test_catalog_payload_marks_active(monkeypatch):
    # Pretend nothing is installed so we can lock down the structure shape
    # without depending on the real cache dir.
    monkeypatch.setattr(catalog_module, "is_model_installed", lambda _id: False)
    monkeypatch.setattr(catalog_module, "model_disk_bytes", lambda _id: 0)
    payload = catalog_payload(active_model_id="multilingual-e5-small")
    assert payload["active"] == "multilingual-e5-small"
    assert payload["default"] == DEFAULT_MODEL_ID
    assert {item["id"] for item in payload["items"]} == set(CATALOG.keys())


def test_resolve_active_embedding_repo_falls_back_to_default(monkeypatch):
    """The runtime resolver should fall back to the catalog default
    when DB lookup fails and no env var is set."""
    monkeypatch.delenv("MEMORY_EMBEDDING_MODEL", raising=False)
    # Force the DB lookup to raise
    with patch("koda.state.control_plane_store.fetch_one", side_effect=RuntimeError("no db")):
        from koda.utils.embeddings import resolve_active_embedding_repo

        result = resolve_active_embedding_repo()
        assert result == CATALOG[DEFAULT_MODEL_ID].repo_id


def test_resolve_active_embedding_repo_honors_env_override(monkeypatch):
    """Env var wins over catalog default when DB returns nothing."""
    monkeypatch.setenv("MEMORY_EMBEDDING_MODEL", "custom-org/custom-model")
    with patch("koda.state.control_plane_store.fetch_one", return_value=None):
        from koda.utils.embeddings import resolve_active_embedding_repo

        result = resolve_active_embedding_repo()
        assert result == "custom-org/custom-model"


def test_resolve_active_embedding_repo_uses_db_choice_first(monkeypatch):
    """An operator selection persisted in the DB beats env + default."""
    monkeypatch.setenv("MEMORY_EMBEDDING_MODEL", "custom-org/custom-model")
    fake_row = {"data_json": '{"embedding_model": "multilingual-e5-small"}'}
    with patch("koda.state.control_plane_store.fetch_one", return_value=fake_row):
        from koda.utils.embeddings import resolve_active_embedding_repo

        result = resolve_active_embedding_repo()
        assert result == CATALOG["multilingual-e5-small"].repo_id


def test_resolve_active_embedding_repo_ignores_unknown_db_choice(monkeypatch):
    """If the DB has a model id we don't recognize, fall through cleanly."""
    monkeypatch.delenv("MEMORY_EMBEDDING_MODEL", raising=False)
    fake_row = {"data_json": '{"embedding_model": "non-existent-model"}'}
    with patch("koda.state.control_plane_store.fetch_one", return_value=fake_row):
        from koda.utils.embeddings import resolve_active_embedding_repo

        result = resolve_active_embedding_repo()
        assert result == CATALOG[DEFAULT_MODEL_ID].repo_id


def test_delete_model_removes_cache_dir(tmp_path, monkeypatch):
    """delete_model() wipes the entire models--<repo> tree and reports bytes_freed."""
    definition = CATALOG[DEFAULT_MODEL_ID]
    safe_repo = definition.repo_id.replace("/", "--")
    base = tmp_path / f"models--{safe_repo}"
    blobs = base / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "weight.safetensors").write_bytes(b"x" * 100)
    (blobs / "tokenizer.json").write_bytes(b"y" * 50)
    monkeypatch.setattr(catalog_module, "_hf_cache_dir", lambda: tmp_path)

    result = delete_model(DEFAULT_MODEL_ID)

    assert result["model_id"] == DEFAULT_MODEL_ID
    assert result["removed"] is True
    assert result["bytes_freed"] == 150
    assert not base.exists(), "cache dir should be gone after delete"


def test_delete_model_no_op_when_not_installed(tmp_path, monkeypatch):
    """delete_model() is idempotent: deleting a model with no cache returns removed=False."""
    monkeypatch.setattr(catalog_module, "_hf_cache_dir", lambda: tmp_path)
    result = delete_model(DEFAULT_MODEL_ID)
    assert result["removed"] is False
    assert result["bytes_freed"] == 0


def test_delete_model_unknown_id_raises():
    with pytest.raises(KeyError):
        delete_model("nope-not-a-model")
