"""Catalog and managed local storage for Kokoro voices."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KOKORO_MODEL_VERSION = "v1.0"
KOKORO_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
KOKORO_VOICE_BASE_URL = "https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/voices"
KOKORO_DEFAULT_LANGUAGE_ID = "pt-br"
KOKORO_DEFAULT_VOICE_ID = "pf_dora"

_STATE_ROOT_DIR = Path(os.environ.get("STATE_ROOT_DIR", str(Path.home() / ".koda-state"))).expanduser()
_CONTROL_PLANE_RUNTIME_DIR = os.environ.get("CONTROL_PLANE_RUNTIME_DIR", "").strip()
_KOKORO_ROOT = Path(
    os.environ.get(
        "KOKORO_ASSET_ROOT",
        str(
            (Path(_CONTROL_PLANE_RUNTIME_DIR).expanduser() / "providers" / "kokoro")
            if _CONTROL_PLANE_RUNTIME_DIR
            else (_STATE_ROOT_DIR / "providers" / "kokoro")
        ),
    )
).expanduser()
_KOKORO_MODEL_DIR = _KOKORO_ROOT / "model"
_KOKORO_VOICES_DIR = _KOKORO_ROOT / "voices"
_KOKORO_BANK_DIR = _KOKORO_ROOT / "voice_bank"
_KOKORO_METADATA_PATH = _KOKORO_ROOT / "voices.json"
_KOKORO_MODEL_PATH = _KOKORO_MODEL_DIR / "kokoro-v1.0.onnx"
_KOKORO_VOICES_BANK_PATH = _KOKORO_BANK_DIR / "voices-managed-v1.0.bin"
_KOKORO_DOWNLOAD_CHUNK_SIZE = 64 * 1024
_KOKORO_REBUILD_LOCK = threading.RLock()

_KOKORO_LANGUAGES: tuple[dict[str, Any], ...] = (
    {
        "id": "en-us",
        "label": "American English",
        "lang_code": "a",
        "tts_lang": "en-us",
        "voices": (
            "af_heart",
            "af_alloy",
            "af_aoede",
            "af_bella",
            "af_jessica",
            "af_kore",
            "af_nicole",
            "af_nova",
            "af_river",
            "af_sarah",
            "af_sky",
            "am_adam",
            "am_echo",
            "am_eric",
            "am_fenrir",
            "am_liam",
            "am_michael",
            "am_onyx",
            "am_puck",
            "am_santa",
        ),
    },
    {
        "id": "en-gb",
        "label": "British English",
        "lang_code": "b",
        "tts_lang": "en-gb",
        "voices": (
            "bf_alice",
            "bf_emma",
            "bf_isabella",
            "bf_lily",
            "bm_daniel",
            "bm_fable",
            "bm_george",
            "bm_lewis",
        ),
    },
    {
        "id": "ja-jp",
        "label": "Japanese",
        "lang_code": "j",
        "tts_lang": "ja",
        "voices": (
            "jf_alpha",
            "jf_gongitsune",
            "jf_nezumi",
            "jf_tebukuro",
            "jm_kumo",
        ),
    },
    {
        "id": "zh-cn",
        "label": "Mandarin Chinese",
        "lang_code": "z",
        "tts_lang": "zh",
        "voices": (
            "zf_xiaobei",
            "zf_xiaoni",
            "zf_xiaoxiao",
            "zf_xiaoyi",
            "zm_yunjian",
            "zm_yunxi",
            "zm_yunxia",
            "zm_yunyang",
        ),
    },
    {
        "id": "es-es",
        "label": "Spanish",
        "lang_code": "e",
        "tts_lang": "es",
        "voices": (
            "ef_dora",
            "em_alex",
            "em_santa",
        ),
    },
    {
        "id": "fr-fr",
        "label": "French",
        "lang_code": "f",
        "tts_lang": "fr-fr",
        "voices": ("ff_siwis",),
    },
    {
        "id": "hi-in",
        "label": "Hindi",
        "lang_code": "h",
        "tts_lang": "hi",
        "voices": (
            "hf_alpha",
            "hf_beta",
            "hm_omega",
            "hm_psi",
        ),
    },
    {
        "id": "it-it",
        "label": "Italian",
        "lang_code": "i",
        "tts_lang": "it",
        "voices": (
            "if_sara",
            "im_nicola",
        ),
    },
    {
        "id": "pt-br",
        "label": "Brazilian Portuguese",
        "lang_code": "p",
        "tts_lang": "pt-br",
        "voices": (
            "pf_dora",
            "pm_alex",
            "pm_santa",
        ),
    },
)

_KOKORO_SHA256_PREFIXES: dict[str, str] = {
    "af_heart": "0ab5709b",
    "af_alloy": "6d877149",
    "af_aoede": "c03bd1a4",
    "af_bella": "8cb64e02",
    "af_jessica": "cdfdccb8",
    "af_kore": "8bfbc512",
    "af_nicole": "c5561808",
    "af_nova": "e0233676",
    "af_river": "e149459b",
    "af_sarah": "49bd364e",
    "af_sky": "c799548a",
    "am_adam": "ced7e284",
    "am_echo": "8bcfdc85",
    "am_eric": "ada66f0e",
    "am_fenrir": "98e507ec",
    "am_liam": "c8255075",
    "am_michael": "9a443b79",
    "am_onyx": "e8452be1",
    "am_puck": "dd1d8973",
    "am_santa": "7f2f7582",
    "bf_alice": "d292651b",
    "bf_emma": "d0a423de",
    "bf_isabella": "cdd4c370",
    "bf_lily": "6e09c2e4",
    "bm_daniel": "fc3fce4e",
    "bm_fable": "d44935f3",
    "bm_george": "f1bc8122",
    "bm_lewis": "b5204750",
    "jf_alpha": "1bf4c9dc",
    "jf_gongitsune": "1b171917",
    "jf_nezumi": "d83f007a",
    "jf_tebukuro": "0d691790",
    "jm_kumo": "98340afd",
    "zf_xiaobei": "9b76be63",
    "zf_xiaoni": "95b49f16",
    "zf_xiaoxiao": "cfaf6f2d",
    "zf_xiaoyi": "b5235dba",
    "zm_yunjian": "76cbf8ba",
    "zm_yunxi": "dbe6e1ce",
    "zm_yunxia": "bb2b03b0",
    "zm_yunyang": "5238ac22",
    "ef_dora": "d9d69b0f",
    "em_alex": "5eac53f7",
    "em_santa": "aa8620cb",
    "ff_siwis": "8073bf2d",
    "hf_alpha": "06906fe0",
    "hf_beta": "63c0a1a6",
    "hm_omega": "b55f02a8",
    "hm_psi": "2f0f055c",
    "if_sara": "6c0b253b",
    "im_nicola": "234ed066",
    "pf_dora": "07e4ff98",
    "pm_alex": "cf0ba8c5",
    "pm_santa": "d4210316",
}


def _voice_name(voice_id: str) -> str:
    return voice_id.split("_", 1)[1].replace("_", " ").title()


def _voice_gender(voice_id: str) -> str:
    return "female" if voice_id[1] == "f" else "male"


def _ensure_storage() -> None:
    _KOKORO_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    _KOKORO_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    _KOKORO_BANK_DIR.mkdir(parents=True, exist_ok=True)


def kokoro_model_path() -> Path:
    _ensure_storage()
    return _KOKORO_MODEL_PATH


def kokoro_managed_voices_storage_path() -> Path:
    return _KOKORO_VOICES_BANK_PATH


def kokoro_managed_voices_path() -> Path:
    _ensure_storage()
    return kokoro_managed_voices_storage_path()


def kokoro_voice_languages() -> list[dict[str, str]]:
    return [{"id": item["id"], "label": item["label"]} for item in _KOKORO_LANGUAGES]


def kokoro_voice_metadata(voice_id: str) -> dict[str, Any] | None:
    normalized = str(voice_id or "").strip().lower()
    for language in _KOKORO_LANGUAGES:
        if normalized in language["voices"]:
            return {
                "voice_id": normalized,
                "name": _voice_name(normalized),
                "gender": _voice_gender(normalized),
                "language_id": language["id"],
                "language_label": language["label"],
                "lang_code": language["lang_code"],
                "tts_lang": language["tts_lang"],
                "download_url": f"{KOKORO_VOICE_BASE_URL}/{normalized}.pt",
                "sha256_prefix": _KOKORO_SHA256_PREFIXES.get(normalized, ""),
            }
    return None


def kokoro_voice_file_path(voice_id: str) -> Path:
    metadata = kokoro_voice_metadata(voice_id)
    if metadata is None:
        raise KeyError(f"unknown kokoro voice: {voice_id}")
    _ensure_storage()
    language_dir = _KOKORO_VOICES_DIR / str(metadata["language_id"])
    language_dir.mkdir(parents=True, exist_ok=True)
    return language_dir / f"{metadata['voice_id']}.pt"


def list_kokoro_voices(language_id: str = "") -> list[dict[str, Any]]:
    requested_language = str(language_id or "").strip().lower()
    downloaded = downloaded_kokoro_voice_ids()
    items: list[dict[str, Any]] = []
    for language in _KOKORO_LANGUAGES:
        if requested_language and language["id"] != requested_language:
            continue
        for voice_id in language["voices"]:
            metadata = kokoro_voice_metadata(voice_id)
            if metadata is None:
                continue
            items.append(
                {
                    **metadata,
                    "downloaded": voice_id in downloaded,
                    "local_path": str(kokoro_voice_file_path(voice_id)) if voice_id in downloaded else "",
                }
            )
    return items


def downloaded_kokoro_voice_ids() -> set[str]:
    try:
        _ensure_storage()
    except OSError:
        return set()
    downloaded: set[str] = set()
    for path in _KOKORO_VOICES_DIR.rglob("*.pt"):
        voice_id = path.stem.strip().lower()
        if kokoro_voice_metadata(voice_id) is None:
            continue
        if path.is_file() and path.stat().st_size > 0:
            downloaded.add(voice_id)
    return downloaded


def kokoro_catalog_payload(language_id: str = "") -> dict[str, Any]:
    requested_language = str(language_id or "").strip().lower()
    items = list_kokoro_voices(requested_language)
    return {
        "items": items,
        "available_languages": kokoro_voice_languages(),
        "selected_language": requested_language,
        "downloaded_voice_ids": sorted(downloaded_kokoro_voice_ids()),
    }


def ensure_kokoro_model() -> Path:
    _ensure_storage()
    if _KOKORO_MODEL_PATH.exists() and _KOKORO_MODEL_PATH.stat().st_size > 0:
        return _KOKORO_MODEL_PATH
    tmp_path = _KOKORO_MODEL_PATH.with_suffix(".tmp")
    urllib.request.urlretrieve(KOKORO_MODEL_URL, tmp_path)
    tmp_path.replace(_KOKORO_MODEL_PATH)
    return _KOKORO_MODEL_PATH


def _write_voice_metadata_file(downloaded_voice_ids: set[str]) -> None:
    payload = {
        "downloaded_voice_ids": sorted(downloaded_voice_ids),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _KOKORO_METADATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def rebuild_kokoro_voice_bank() -> Path:
    _ensure_storage()
    with _KOKORO_REBUILD_LOCK:
        import numpy as np
        import torch

        downloaded = sorted(downloaded_kokoro_voice_ids())
        if not downloaded:
            raise RuntimeError("no kokoro voices downloaded")

        payload: dict[str, Any] = {}
        for voice_id in downloaded:
            tensor = torch.load(kokoro_voice_file_path(voice_id), map_location="cpu")
            payload[voice_id] = tensor.detach().cpu().numpy()

        tmp_path = _KOKORO_VOICES_BANK_PATH.with_suffix(".tmp")
        with open(tmp_path, "wb") as handle:
            np.savez(handle, **payload)
        tmp_path.replace(_KOKORO_VOICES_BANK_PATH)
        _write_voice_metadata_file(set(downloaded))
        return _KOKORO_VOICES_BANK_PATH


def ensure_kokoro_voice_downloaded(
    voice_id: str,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    metadata = kokoro_voice_metadata(voice_id)
    if metadata is None:
        raise KeyError(f"unknown kokoro voice: {voice_id}")

    target_path = kokoro_voice_file_path(str(metadata["voice_id"]))
    if target_path.exists() and target_path.stat().st_size > 0:
        rebuild_kokoro_voice_bank()
        total_bytes = target_path.stat().st_size
        if progress_callback is not None:
            progress_callback(total_bytes, total_bytes)
        return {
            **metadata,
            "downloaded": True,
            "bytes": total_bytes,
            "local_path": str(target_path),
        }

    request = urllib.request.Request(
        str(metadata["download_url"]),
        headers={"User-Agent": "koda/kokoro-manager"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        total_bytes = int(response.headers.get("Content-Length", "0") or "0")
        downloaded_bytes = 0
        hasher = hashlib.sha256()
        tmp_path = target_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "wb") as handle:
                while True:
                    chunk = response.read(_KOKORO_DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    hasher.update(chunk)
                    downloaded_bytes += len(chunk)
                    if progress_callback is not None:
                        progress_callback(downloaded_bytes, total_bytes)
            expected_prefix = str(metadata.get("sha256_prefix") or "").lower()
            actual_hash = hasher.hexdigest().lower()
            if expected_prefix and not actual_hash.startswith(expected_prefix):
                raise RuntimeError(f"hash mismatch for {metadata['voice_id']}")
            tmp_path.replace(target_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    rebuild_kokoro_voice_bank()
    return {
        **metadata,
        "downloaded": True,
        "bytes": target_path.stat().st_size,
        "local_path": str(target_path),
    }


def ensure_default_kokoro_assets() -> tuple[Path, Path]:
    ensure_kokoro_model()
    if not downloaded_kokoro_voice_ids():
        ensure_kokoro_voice_downloaded(KOKORO_DEFAULT_VOICE_ID)
    if not _KOKORO_VOICES_BANK_PATH.exists():
        rebuild_kokoro_voice_bank()
    return _KOKORO_MODEL_PATH, _KOKORO_VOICES_BANK_PATH


def resolve_kokoro_language(voice_id: str, default_language: str = "") -> str:
    metadata = kokoro_voice_metadata(voice_id)
    if metadata is not None:
        return str(metadata["tts_lang"])
    normalized_default = str(default_language or "").strip().lower()
    if normalized_default:
        for language in _KOKORO_LANGUAGES:
            if language["id"] == normalized_default:
                return str(language["tts_lang"])
    return "pt-br"
