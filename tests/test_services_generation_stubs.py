"""Tests for generation stubs that expose operator-configured defaults for
image/video/music slots and fail-close when actually invoked."""

from __future__ import annotations

import json

import pytest

import koda.services.generation_stubs as stubs


def _patch_defaults(monkeypatch: pytest.MonkeyPatch, payload: dict[str, dict[str, str]]) -> None:
    monkeypatch.setenv("MODEL_FUNCTION_DEFAULTS_JSON", json.dumps(payload))


def test_resolve_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_FUNCTION_DEFAULTS_JSON", raising=False)
    assert stubs.resolve_image_generation_default() is None
    assert stubs.resolve_video_generation_default() is None
    assert stubs.resolve_music_generation_default() is None


def test_resolve_returns_selection_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(
        monkeypatch,
        {
            "image": {"provider_id": "openai", "model_id": "gpt-image-1"},
            "video": {"provider_id": "runway", "model_id": "gen-3"},
            "music": {"provider_id": "suno", "model_id": "v3.5"},
        },
    )
    image = stubs.resolve_image_generation_default()
    assert image is not None
    assert image.provider_id == "openai"
    assert image.model_id == "gpt-image-1"
    assert image.present is True

    video = stubs.resolve_video_generation_default()
    assert video is not None and video.provider_id == "runway"

    music = stubs.resolve_music_generation_default()
    assert music is not None and music.model_id == "v3.5"


def test_resolve_returns_none_when_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch, {"image": {"provider_id": "openai", "model_id": ""}})
    assert stubs.resolve_image_generation_default() is None


def test_invoke_raises_with_configured_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(
        monkeypatch,
        {"image": {"provider_id": "openai", "model_id": "gpt-image-1"}},
    )
    with pytest.raises(stubs.GenerationServiceNotImplemented) as excinfo:
        stubs.invoke_image_generation("prompt")
    assert excinfo.value.slot == "image"
    assert excinfo.value.selection.provider_id == "openai"
    assert excinfo.value.selection.model_id == "gpt-image-1"
    message = str(excinfo.value)
    assert "openai/gpt-image-1" in message
    assert "runtime ainda não implementado" in message


def test_invoke_raises_with_unconfigured_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_FUNCTION_DEFAULTS_JSON", raising=False)
    with pytest.raises(stubs.GenerationServiceNotImplemented) as excinfo:
        stubs.invoke_video_generation("prompt")
    assert excinfo.value.selection.present is False
    message = str(excinfo.value)
    assert "sem provider padrão configurado" in message
    assert "/control-plane/system/models" in message


def test_invoke_music_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_FUNCTION_DEFAULTS_JSON", raising=False)
    with pytest.raises(stubs.GenerationServiceNotImplemented) as excinfo:
        stubs.invoke_music_generation("prompt")
    assert excinfo.value.slot == "music"


def test_generation_service_not_implemented_is_not_implemented_error() -> None:
    # Callers should be able to except either NotImplementedError or the
    # specific class. The explicit subclass lets callers identify the slot.
    selection = stubs.FunctionalDefaultSelection(provider_id="", model_id="")
    err = stubs.GenerationServiceNotImplemented("image", selection)
    assert isinstance(err, NotImplementedError)
