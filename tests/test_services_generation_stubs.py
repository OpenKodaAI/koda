"""Tests for functional generation defaults and image generation."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

import koda.services.generation_stubs as stubs

PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


class _FakeResponse:
    def __init__(self, payload: bytes, headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


def _patch_defaults(monkeypatch: pytest.MonkeyPatch, payload: dict[str, dict[str, str]]) -> None:
    monkeypatch.setenv("MODEL_FUNCTION_DEFAULTS_JSON", json.dumps(payload))


def _fake_image_urlopen(seen: dict[str, Any]):
    def _urlopen(request: Any, timeout: int) -> _FakeResponse:
        seen["timeout"] = timeout
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        body = {
            "data": [
                {
                    "b64_json": base64.b64encode(PNG_BYTES).decode("ascii"),
                    "revised_prompt": "A crisp generated image.",
                    "size": "1024x1024",
                }
            ]
        }
        return _FakeResponse(json.dumps(body).encode("utf-8"))

    return _urlopen


def test_resolve_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_FUNCTION_DEFAULTS_JSON", raising=False)
    assert stubs.resolve_image_generation_default() is None
    assert stubs.resolve_video_generation_default() is None
    assert stubs.resolve_music_generation_default() is None


def test_resolve_returns_selection_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(
        monkeypatch,
        {
            "image": {"provider_id": "codex", "model_id": "gpt-image-2"},
            "video": {"provider_id": "runway", "model_id": "gen-3"},
            "music": {"provider_id": "suno", "model_id": "v3.5"},
        },
    )
    image = stubs.resolve_image_generation_default()
    assert image is not None
    assert image.provider_id == "codex"
    assert image.model_id == "gpt-image-2"
    assert image.present is True

    video = stubs.resolve_video_generation_default()
    assert video is not None and video.provider_id == "runway"

    music = stubs.resolve_music_generation_default()
    assert music is not None and music.model_id == "v3.5"


def test_resolve_returns_none_when_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(monkeypatch, {"image": {"provider_id": "codex", "model_id": ""}})
    assert stubs.resolve_image_generation_default() is None


def test_invoke_image_generation_uses_configured_gpt_image_2(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _patch_defaults(
        monkeypatch,
        {"image": {"provider_id": "codex", "model_id": "gpt-image-2"}},
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(stubs.urllib_request, "urlopen", _fake_image_urlopen(seen))

    result = stubs.invoke_image_generation(
        "A small blue house",
        output_dir=tmp_path,
        filename="house.png",
        size="1024x1024",
        quality="high",
        output_format="png",
    )

    assert result.provider_id == "codex"
    assert result.model_id == "gpt-image-2"
    assert len(result.artifacts) == 1
    output_path = tmp_path / "house.png"
    assert output_path.read_bytes() == PNG_BYTES
    assert result.artifacts[0].path == str(output_path)
    assert result.artifacts[0].revised_prompt == "A crisp generated image."
    assert seen["url"] == stubs.OPENAI_IMAGES_GENERATIONS_URL
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert seen["payload"] == {
        "model": "gpt-image-2",
        "prompt": "A small blue house",
        "size": "1024x1024",
        "quality": "high",
        "output_format": "png",
    }


def test_invoke_image_generation_supports_openai_provider_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _patch_defaults(
        monkeypatch,
        {"image": {"provider_id": "openai", "model_id": "gpt-image-2"}},
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(stubs.urllib_request, "urlopen", _fake_image_urlopen({}))

    result = stubs.invoke_image_generation("A cat", output_dir=tmp_path)

    assert result.provider_id == "codex"
    assert result.model_id == "gpt-image-2"
    output_path = tmp_path / result.artifacts[0].path.rsplit("/", 1)[-1]
    assert output_path.exists()
    assert output_path.name.startswith("generated_image_")
    assert output_path.suffix == ".png"


def test_invoke_image_generation_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _patch_defaults(
        monkeypatch,
        {"image": {"provider_id": "codex", "model_id": "gpt-image-2"}},
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(stubs, "_resolve_openai_api_key", lambda: "")

    with pytest.raises(stubs.ImageGenerationError) as excinfo:
        stubs.invoke_image_generation("prompt", output_dir=tmp_path)

    assert "OPENAI_API_KEY" in str(excinfo.value)


def test_invoke_image_generation_raises_for_unsupported_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_defaults(
        monkeypatch,
        {"image": {"provider_id": "runway", "model_id": "gen-3"}},
    )

    with pytest.raises(stubs.GenerationServiceNotImplemented) as excinfo:
        stubs.invoke_image_generation("prompt")

    assert excinfo.value.slot == "image"
    assert excinfo.value.selection.provider_id == "runway"
    assert excinfo.value.selection.model_id == "gen-3"


def test_invoke_raises_with_unconfigured_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_FUNCTION_DEFAULTS_JSON", raising=False)
    with pytest.raises(stubs.GenerationServiceNotImplemented) as excinfo:
        stubs.invoke_video_generation("prompt")
    assert excinfo.value.selection.present is False
    message = str(excinfo.value)
    assert "no default provider configured" in message
    assert "/control-plane/system/models" in message


def test_invoke_music_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_FUNCTION_DEFAULTS_JSON", raising=False)
    with pytest.raises(stubs.GenerationServiceNotImplemented) as excinfo:
        stubs.invoke_music_generation("prompt")
    assert excinfo.value.slot == "music"


def test_generation_service_not_implemented_is_not_implemented_error() -> None:
    selection = stubs.FunctionalDefaultSelection(provider_id="", model_id="")
    err = stubs.GenerationServiceNotImplemented("image", selection)
    assert isinstance(err, NotImplementedError)
