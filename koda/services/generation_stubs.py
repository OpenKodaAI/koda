"""Functional generation services for image/video/music slots.

The Models section lets operators pick a default provider+model for
``general``, ``image``, ``video``, ``audio``, ``transcription`` and
``music``. Image generation is now wired to the OpenAI Images API for the
``codex`` provider; video and music still fail closed with explicit errors
until provider integrations are added.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast
from urllib import error as urllib_error
from urllib import request as urllib_request

from koda.config import resolve_functional_default
from koda.logging_config import get_logger

FunctionalSlot = Literal["image", "video", "music"]

OPENAI_IMAGES_GENERATIONS_URL = "https://api.openai.com/v1/images/generations"
OPENAI_IMAGE_TIMEOUT_SECONDS = 180

_OPENAI_IMAGE_PROVIDERS = {"codex", "openai"}
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_OUTPUT_FORMAT_ALIASES = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}
_DEFAULT_OUTPUT_FORMAT = "png"

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FunctionalDefaultSelection:
    """Operator-selected default provider+model for a functional slot."""

    provider_id: str
    model_id: str

    @property
    def present(self) -> bool:
        return bool(self.provider_id) and bool(self.model_id)


@dataclass(frozen=True, slots=True)
class GeneratedImageArtifact:
    """A generated image persisted on disk and ready to be sent as an artifact."""

    path: str
    provider_id: str
    model_id: str
    size: str = ""
    output_format: str = _DEFAULT_OUTPUT_FORMAT
    revised_prompt: str = ""


@dataclass(frozen=True, slots=True)
class ImageGenerationResult:
    """Result returned by ``invoke_image_generation`` and the image tool."""

    provider_id: str
    model_id: str
    prompt: str
    output_dir: str
    artifacts: list[GeneratedImageArtifact] = field(default_factory=list)


class GenerationServiceNotImplemented(NotImplementedError):
    """Raised when a functional slot is selected but has no runtime integration."""

    def __init__(self, slot: FunctionalSlot, selection: FunctionalDefaultSelection) -> None:
        self.slot = slot
        self.selection = selection
        if selection.present:
            detail = (
                f"{slot.capitalize()} generation configured as "
                f"{selection.provider_id}/{selection.model_id} - runtime not yet implemented."
            )
        else:
            detail = (
                f"{slot.capitalize()} generation not implemented and no default provider configured. "
                "Set a default under /control-plane/system/models."
            )
        super().__init__(detail)


class ImageGenerationError(RuntimeError):
    """Raised when an image provider integration is configured but execution fails."""


def _resolve(slot: FunctionalSlot) -> FunctionalDefaultSelection | None:
    provider, model = resolve_functional_default(slot)
    if not provider or not model:
        return None
    return FunctionalDefaultSelection(provider_id=provider, model_id=model)


def resolve_image_generation_default() -> FunctionalDefaultSelection | None:
    """Return the image-generation default selection, or ``None`` when unset."""
    return _resolve("image")


def resolve_video_generation_default() -> FunctionalDefaultSelection | None:
    """Return the video-generation default selection, or ``None`` when unset."""
    return _resolve("video")


def resolve_music_generation_default() -> FunctionalDefaultSelection | None:
    """Return the music-generation default selection, or ``None`` when unset."""
    return _resolve("music")


def _invoke_unimplemented(slot: FunctionalSlot) -> None:
    selection = _resolve(slot) or FunctionalDefaultSelection(provider_id="", model_id="")
    raise GenerationServiceNotImplemented(slot, selection)


def _resolve_image_selection(
    provider_id: str | None = None,
    model_id: str | None = None,
) -> FunctionalDefaultSelection:
    provider = str(provider_id or "").strip().lower()
    model = str(model_id or "").strip()
    if provider and model:
        return FunctionalDefaultSelection(provider_id=provider, model_id=model)
    selection = resolve_image_generation_default()
    if selection is None or not selection.present:
        _invoke_unimplemented("image")
    return cast(FunctionalDefaultSelection, selection)


def _normalize_openai_provider(selection: FunctionalDefaultSelection) -> str:
    normalized = selection.provider_id.strip().lower()
    if normalized not in _OPENAI_IMAGE_PROVIDERS:
        raise GenerationServiceNotImplemented(
            "image",
            FunctionalDefaultSelection(provider_id=normalized, model_id=selection.model_id),
        )
    return "codex"


def _resolve_openai_api_key() -> str:
    api_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if api_key:
        return api_key
    try:
        from koda.control_plane.manager import ControlPlaneManager

        value = ControlPlaneManager()._provider_api_key_secret_value("codex")
        return str(value or "").strip()
    except Exception as exc:
        log.debug("image_api_key_lookup_failed", error=str(exc))
        return ""


def _extract_openai_error(body: str) -> str:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return body.strip()
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            message = str(err.get("message") or "").strip()
            code = str(err.get("code") or "").strip()
            err_type = str(err.get("type") or "").strip()
            parts = [part for part in (message, code, err_type) if part]
            if parts:
                return " | ".join(parts)
    return body.strip()


def _post_openai_images(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    request = urllib_request.Request(
        OPENAI_IMAGES_GENERATIONS_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=OPENAI_IMAGE_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        detail = _extract_openai_error(body) or f"OpenAI image API returned HTTP {exc.code}"
        raise ImageGenerationError(detail) from exc
    except urllib_error.URLError as exc:
        raise ImageGenerationError(f"OpenAI image API request failed: {exc.reason}") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ImageGenerationError("OpenAI image API returned an invalid JSON response.") from exc
    if not isinstance(decoded, dict):
        raise ImageGenerationError("OpenAI image API returned an unexpected response.")
    return decoded


def _download_image_url(url: str) -> tuple[bytes, str]:
    if not url.startswith("https://"):
        raise ImageGenerationError("OpenAI image API returned a non-HTTPS image URL.")
    request = urllib_request.Request(url, method="GET")
    try:
        with urllib_request.urlopen(request, timeout=OPENAI_IMAGE_TIMEOUT_SECONDS) as response:
            content_type = str(response.headers.get("Content-Type") or "")
            return response.read(), content_type
    except urllib_error.URLError as exc:
        raise ImageGenerationError(f"Failed to download generated image: {exc.reason}") from exc


def _decode_base64_image(value: str) -> tuple[bytes, str]:
    content_type = ""
    payload = value.strip()
    if payload.startswith("data:") and "," in payload:
        header, payload = payload.split(",", 1)
        if ";base64" in header:
            content_type = header.removeprefix("data:").split(";", 1)[0]
    try:
        return base64.b64decode(payload, validate=True), content_type
    except binascii.Error:
        try:
            return base64.b64decode(payload), content_type
        except binascii.Error as exc:
            raise ImageGenerationError("OpenAI image API returned invalid base64 image data.") from exc


def _normalize_output_format(value: object) -> str:
    raw = str(value or "").strip().lower().removeprefix(".")
    if not raw or raw == "auto":
        return _DEFAULT_OUTPUT_FORMAT
    return _OUTPUT_FORMAT_ALIASES.get(raw, _DEFAULT_OUTPUT_FORMAT)


def _infer_output_format(content: bytes, *, requested: str, content_type: str = "") -> str:
    lowered_type = content_type.lower()
    if "webp" in lowered_type or content.startswith(b"RIFF"):
        return "webp"
    if "jpeg" in lowered_type or "jpg" in lowered_type or content.startswith(b"\xff\xd8"):
        return "jpeg"
    if "png" in lowered_type or content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    return _normalize_output_format(requested)


def _safe_stem(filename: str | None) -> str:
    if filename:
        stem = Path(filename).name
        stem = Path(stem).stem or "generated_image"
    else:
        stem = f"generated_image_{time.strftime('%Y%m%d_%H%M%S')}"
    stem = _SAFE_FILENAME_RE.sub("_", stem).strip("._")
    return (stem or "generated_image")[:96]


def _unique_path(output_dir: Path, stem: str, extension: str, index: int, total: int) -> Path:
    suffix = f"_{index + 1}" if total > 1 else ""
    candidate = output_dir / f"{stem}{suffix}.{extension}"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"{stem}{suffix}_{counter}.{extension}"
        counter += 1
    return candidate


def _json_item(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _coerce_positive_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        coerced = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ImageGenerationError("Image count 'n' must be a positive integer.") from exc
    if coerced < 1 or coerced > 10:
        raise ImageGenerationError("Image count 'n' must be between 1 and 10.")
    return coerced


def _string_param(value: object) -> str:
    return str(value or "").strip()


def generate_image(
    prompt: str,
    *,
    provider_id: str | None = None,
    model_id: str | None = None,
    output_dir: str | Path | None = None,
    filename: str | None = None,
    size: str | None = None,
    quality: str | None = None,
    background: str | None = None,
    output_format: str | None = None,
    n: int | str | None = None,
    user: str | None = None,
) -> ImageGenerationResult:
    """Generate an image with the configured image provider/model.

    Currently supports the OpenAI Images API through Koda's ``codex`` provider.
    Generated files are written to ``output_dir`` and returned as artifact
    paths for Telegram/document delivery.
    """
    clean_prompt = str(prompt or "").strip()
    if not clean_prompt:
        raise ImageGenerationError("Image prompt is required.")

    selection = _resolve_image_selection(provider_id=provider_id, model_id=model_id)
    auth_provider = _normalize_openai_provider(selection)
    api_key = _resolve_openai_api_key()
    if not api_key:
        raise ImageGenerationError(
            "OpenAI image generation requires an OPENAI_API_KEY or a verified OpenAI provider API key."
        )

    payload: dict[str, Any] = {
        "model": selection.model_id,
        "prompt": clean_prompt,
    }
    for key, value in (
        ("size", size),
        ("quality", quality),
        ("background", background),
        ("output_format", output_format),
        ("user", user),
    ):
        normalized_value = _string_param(value)
        if normalized_value:
            payload[key] = normalized_value
    image_count = _coerce_positive_int(n)
    if image_count is not None:
        payload["n"] = image_count

    response = _post_openai_images(payload, api_key)
    data = response.get("data")
    if not isinstance(data, list) or not data:
        raise ImageGenerationError("OpenAI image API returned no image data.")

    target_dir = Path(output_dir or os.getcwd()).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(filename)
    artifacts: list[GeneratedImageArtifact] = []
    total = len(data)
    requested_format = _normalize_output_format(output_format)

    for index, raw_item in enumerate(data):
        item = _json_item(raw_item)
        b64_json = str(item.get("b64_json") or "").strip()
        image_url = str(item.get("url") or "").strip()
        if b64_json:
            content, content_type = _decode_base64_image(b64_json)
        elif image_url:
            content, content_type = _download_image_url(image_url)
        else:
            raise ImageGenerationError("OpenAI image API returned an item without image bytes.")
        if not content:
            raise ImageGenerationError("OpenAI image API returned empty image bytes.")
        extension = _infer_output_format(content, requested=requested_format, content_type=content_type)
        output_path = _unique_path(target_dir, stem, extension, index, total)
        output_path.write_bytes(content)
        artifacts.append(
            GeneratedImageArtifact(
                path=str(output_path),
                provider_id=auth_provider,
                model_id=selection.model_id,
                size=str(item.get("size") or payload.get("size") or ""),
                output_format=extension,
                revised_prompt=str(item.get("revised_prompt") or "").strip(),
            )
        )

    log.info(
        "image_generation_completed",
        provider_id=auth_provider,
        model_id=selection.model_id,
        count=len(artifacts),
        output_dir=str(target_dir),
    )
    return ImageGenerationResult(
        provider_id=auth_provider,
        model_id=selection.model_id,
        prompt=clean_prompt,
        output_dir=str(target_dir),
        artifacts=artifacts,
    )


def invoke_image_generation(prompt: str, **kwargs: Any) -> ImageGenerationResult:
    """Generate an image using the operator-selected image default."""
    return generate_image(prompt, **kwargs)


def invoke_video_generation(_prompt: str) -> None:
    """Fail closed until a video-generation provider is implemented."""
    _invoke_unimplemented("video")


def invoke_music_generation(_prompt: str) -> None:
    """Fail closed until a music-generation provider is implemented."""
    _invoke_unimplemented("music")
