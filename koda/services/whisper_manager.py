"""Catalog and managed local storage for whisper.cpp GGML models."""

from __future__ import annotations

import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from koda.config import WHISPER_ASSET_ROOT, WHISPER_MODEL

# Catalog of GGML variants that the in-app downloader knows how to fetch.
# IDs are stable strings used as ``asset_id`` in cp_provider_download_jobs and
# in the HTTP routes (``/providers/whispercpp/models/{variant_id}/download``).
# URLs come from the canonical whisper.cpp Hugging Face mirror published by
# ggerganov/upstream — they are stable and CDN-backed.
KNOWN_WHISPER_VARIANTS: dict[str, dict[str, Any]] = {
    "large-v3-turbo-q5_0": {
        "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin",
        "filename": "ggml-large-v3-turbo-q5_0.bin",
        "label": "Whisper large-v3 turbo (q5_0)",
        "description": "Quantizado q5_0 do large-v3 turbo. Equilibra qualidade e tamanho (~574 MB).",
        "approx_size_bytes": 574_000_000,
    },
    "large-v3-turbo": {
        "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin",
        "filename": "ggml-large-v3-turbo.bin",
        "label": "Whisper large-v3 turbo (full)",
        "description": "Versão integral do large-v3 turbo, sem quantização (~1.6 GB).",
        "approx_size_bytes": 1_600_000_000,
    },
    "medium-q5_0": {
        "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium-q5_0.bin",
        "filename": "ggml-medium-q5_0.bin",
        "label": "Whisper medium (q5_0)",
        "description": "Modelo médio quantizado q5_0; menor pegada de memória (~539 MB).",
        "approx_size_bytes": 539_000_000,
    },
}

WHISPER_DEFAULT_VARIANT = "large-v3-turbo-q5_0"
_WHISPER_DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def whisper_models_dir() -> Path:
    """Resolve the on-disk directory where GGML files live.

    Defaults to ``WHISPER_ASSET_ROOT`` (which itself defaults to the parent of
    ``WHISPER_MODEL``). Created lazily on first download.
    """
    return Path(WHISPER_ASSET_ROOT).expanduser()


def whisper_model_path(variant_id: str) -> Path:
    descriptor = KNOWN_WHISPER_VARIANTS.get(variant_id)
    if descriptor is None:
        raise KeyError(f"unknown whisper variant: {variant_id}")
    return whisper_models_dir() / str(descriptor["filename"])


def is_whisper_variant_downloaded(variant_id: str) -> bool:
    try:
        path = whisper_model_path(variant_id)
    except KeyError:
        return False
    return path.exists() and path.stat().st_size > 0


def downloaded_whisper_variants() -> set[str]:
    return {variant for variant in KNOWN_WHISPER_VARIANTS if is_whisper_variant_downloaded(variant)}


def whisper_default_variant_id() -> str:
    """The variant the operator gets when they click the primary download CTA.

    Derived from the configured ``WHISPER_MODEL`` filename when possible so the
    UI surfaces whichever variant the runtime is already pointed at. Falls back
    to ``WHISPER_DEFAULT_VARIANT`` when the configured filename doesn't match a
    known variant.
    """
    configured_filename = Path(WHISPER_MODEL).name
    for variant_id, descriptor in KNOWN_WHISPER_VARIANTS.items():
        if descriptor["filename"] == configured_filename:
            return variant_id
    return WHISPER_DEFAULT_VARIANT


def whisper_catalog_payload() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for variant_id, descriptor in KNOWN_WHISPER_VARIANTS.items():
        path = whisper_model_path(variant_id)
        bytes_on_disk = path.stat().st_size if path.exists() else 0
        items.append(
            {
                "variant_id": variant_id,
                "label": descriptor["label"],
                "description": descriptor["description"],
                "url": descriptor["url"],
                "filename": descriptor["filename"],
                "approx_size_bytes": descriptor["approx_size_bytes"],
                "downloaded": bytes_on_disk > 0,
                "bytes": bytes_on_disk,
                "local_path": str(path),
            }
        )
    return {
        "items": items,
        "default_variant": whisper_default_variant_id(),
        "models_dir": str(whisper_models_dir()),
    }


def delete_whisper_model(variant_id: str) -> dict[str, Any]:
    """Remove a Whisper GGML file from disk.

    Idempotent: missing-file is treated as success. The runtime falls back
    to "model not present" the next time transcription is requested.
    """
    descriptor = KNOWN_WHISPER_VARIANTS.get(variant_id)
    if descriptor is None:
        raise KeyError(f"unknown whisper variant: {variant_id}")

    target_path = whisper_model_path(variant_id)
    existed = target_path.exists()
    bytes_freed = target_path.stat().st_size if existed else 0
    if existed:
        target_path.unlink(missing_ok=True)
    return {
        "variant_id": variant_id,
        "removed": existed,
        "bytes_freed": int(bytes_freed),
        "local_path": str(target_path),
    }


def ensure_whisper_model_downloaded(
    variant_id: str = WHISPER_DEFAULT_VARIANT,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    descriptor = KNOWN_WHISPER_VARIANTS.get(variant_id)
    if descriptor is None:
        raise KeyError(f"unknown whisper variant: {variant_id}")

    target_path = whisper_model_path(variant_id)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists() and target_path.stat().st_size > 0:
        total = target_path.stat().st_size
        if progress_callback is not None:
            progress_callback(total, total)
        return {
            "variant_id": variant_id,
            "downloaded": True,
            "bytes": total,
            "local_path": str(target_path),
        }

    request = urllib.request.Request(
        str(descriptor["url"]),
        headers={"User-Agent": "koda/whisper-manager"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        total_bytes = int(response.headers.get("Content-Length", "0") or "0")
        downloaded_bytes = 0
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        try:
            with open(tmp_path, "wb") as handle:
                while True:
                    chunk = response.read(_WHISPER_DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded_bytes += len(chunk)
                    if progress_callback is not None:
                        progress_callback(downloaded_bytes, total_bytes)
            tmp_path.replace(target_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    return {
        "variant_id": variant_id,
        "downloaded": True,
        "bytes": target_path.stat().st_size,
        "local_path": str(target_path),
    }
