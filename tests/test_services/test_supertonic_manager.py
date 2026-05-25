import json
import sys
from types import SimpleNamespace

import pytest

from koda.services import supertonic_manager as module


def _patch_storage(monkeypatch: pytest.MonkeyPatch, tmp_path):
    root = tmp_path / "supertonic"
    monkeypatch.setattr(module, "_SUPERTONIC_ROOT", root)
    monkeypatch.setattr(module, "_SUPERTONIC_MODELS_DIR", root / "models")
    monkeypatch.setattr(module, "_SUPERTONIC_VOICES_DIR", root / "voices")
    monkeypatch.setattr(module, "_SUPERTONIC_CUSTOM_VOICES_DIR", root / "custom_voices")
    monkeypatch.setattr(module, "_SUPERTONIC_CUSTOM_INDEX_PATH", root / "custom_voices.json")
    return root


def _valid_style() -> dict[str, object]:
    return {"style_ttl": [0.1, 0.2], "style_dp": [0.3, 0.4]}


def test_supertonic_catalog_defaults(monkeypatch, tmp_path):
    root = _patch_storage(monkeypatch, tmp_path)

    catalog = module.supertonic_model_catalog_payload()
    voice_catalog = module.supertonic_voice_catalog_payload()

    assert catalog["default_model"] == "supertonic-3"
    assert catalog["asset_root"] == str(root)
    assert [item["model_id"] for item in catalog["items"]] == [
        "supertonic-3",
        "supertonic-2",
        "supertonic",
    ]
    assert voice_catalog["default_voice"] == "F1"
    assert {item["voice_id"] for item in voice_catalog["items"]} >= {"F1", "F5", "M1", "M5"}
    assert any(language["id"] == "pt" for language in voice_catalog["available_languages"])


def test_supertonic_model_download_is_idempotent_and_uses_snapshot(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    calls: list[dict[str, object]] = []

    def fake_snapshot_download(**kwargs):
        calls.append(kwargs)
        target = tmp_path / "supertonic" / "models" / "supertonic-3"
        target.mkdir(parents=True, exist_ok=True)
        (target / "model.onnx").write_bytes(b"onnx")
        (target / "voice_styles").mkdir(exist_ok=True)
        (target / "voice_styles" / "F1.json").write_text(json.dumps(_valid_style()), encoding="utf-8")
        return str(target)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=fake_snapshot_download))
    progress: list[tuple[int, int]] = []

    path = module.ensure_supertonic_model(
        "supertonic-3", progress_callback=lambda done, total: progress.append((done, total))
    )
    second = module.ensure_supertonic_model("supertonic-3")

    assert path == second
    assert calls and calls[0]["repo_id"] == "Supertone/supertonic-3"
    assert path.joinpath("model.onnx").exists()
    assert module.supertonic_model_status("supertonic-3")["downloaded"] is True
    assert progress[-1][0] == progress[-1][1]


def test_supertonic_preset_voice_activation_copies_style(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    model_root = module.supertonic_model_path("supertonic-3")
    model_root.joinpath("voice_styles").mkdir(parents=True, exist_ok=True)
    model_root.joinpath("model.onnx").write_bytes(b"onnx")
    model_root.joinpath("voice_styles", "F1.json").write_text(json.dumps(_valid_style()), encoding="utf-8")

    result = module.ensure_supertonic_voice_downloaded("F1", "supertonic-3")

    assert result["downloaded"] is True
    assert result["voice_id"] == "F1"
    assert module.resolve_supertonic_voice_path("F1", "supertonic-3").exists()
    assert "F1" in module.downloaded_supertonic_voice_ids("supertonic-3")


def test_supertonic_custom_voice_import_and_delete(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    payload = json.dumps(_valid_style()).encode("utf-8")

    imported = module.import_supertonic_voice_json(payload, name="Minha Voz", model_id="supertonic-3")
    voice_id = imported["voice_id"]

    assert voice_id == "custom-minha-voz"
    assert module.supertonic_voice_metadata(voice_id)["kind"] == "custom"
    assert module.resolve_supertonic_voice_path(voice_id).exists()

    removed = module.delete_supertonic_voice(voice_id, "supertonic-3")

    assert removed["removed"] is True
    assert module.supertonic_voice_metadata(voice_id) is None


def test_supertonic_custom_voice_import_rejects_invalid_json(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)

    with pytest.raises(ValueError):
        module.import_supertonic_voice_json(b'{"style_ttl": []}', name="bad")
