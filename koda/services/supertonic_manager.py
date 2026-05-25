"""Catalog and managed local storage for Supertonic voice assets."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SUPERTONIC_DEFAULT_MODEL_ID = "supertonic-3"
SUPERTONIC_DEFAULT_LANGUAGE_ID = "pt"
SUPERTONIC_DEFAULT_VOICE_ID = "F1"
SUPERTONIC_SAMPLE_RATE = 44_100

_STATE_ROOT_DIR = Path(os.environ.get("STATE_ROOT_DIR", str(Path.home() / ".koda-state"))).expanduser()
_CONTROL_PLANE_RUNTIME_DIR = os.environ.get("CONTROL_PLANE_RUNTIME_DIR", "").strip()
_SUPERTONIC_ROOT = Path(
    os.environ.get(
        "SUPERTONIC_ASSET_ROOT",
        str(
            (Path(_CONTROL_PLANE_RUNTIME_DIR).expanduser() / "providers" / "supertonic")
            if _CONTROL_PLANE_RUNTIME_DIR
            else (_STATE_ROOT_DIR / "providers" / "supertonic")
        ),
    )
).expanduser()
_SUPERTONIC_MODELS_DIR = _SUPERTONIC_ROOT / "models"
_SUPERTONIC_VOICES_DIR = _SUPERTONIC_ROOT / "voices"
_SUPERTONIC_CUSTOM_VOICES_DIR = _SUPERTONIC_ROOT / "custom_voices"
_SUPERTONIC_CUSTOM_INDEX_PATH = _SUPERTONIC_ROOT / "custom_voices.json"
_SUPERTONIC_MODEL_MARKER = ".koda-supertonic-model.json"
_MAX_CUSTOM_VOICE_BYTES = 1_000_000
_STORAGE_LOCK = threading.RLock()


@dataclass(frozen=True, slots=True)
class SupertonicModelDefinition:
    id: str
    title: str
    repo_id: str
    description: str
    revision: str
    languages: int
    legacy: bool = False


_SUPERTONIC_MODELS: dict[str, SupertonicModelDefinition] = {
    "supertonic-3": SupertonicModelDefinition(
        id="supertonic-3",
        title="Supertonic 3",
        repo_id="Supertone/supertonic-3",
        description="99M ONNX multilingual TTS model with 31 languages.",
        revision="724fb5abbf5502583fb520898d45929e62f02c0b",
        languages=31,
    ),
    "supertonic-2": SupertonicModelDefinition(
        id="supertonic-2",
        title="Supertonic 2",
        repo_id="Supertone/supertonic-2",
        description="Previous multilingual ONNX model with 5-language coverage.",
        revision="75e6727618a02f323c720cba9478152d4bc16ca4",
        languages=5,
        legacy=True,
    ),
    "supertonic": SupertonicModelDefinition(
        id="supertonic",
        title="Supertonic",
        repo_id="Supertone/supertonic",
        description="Legacy English-only ONNX model.",
        revision="b6856d033f622c63ea29441795be266a1133e227",
        languages=1,
        legacy=True,
    ),
}

_SUPERTONIC_LANGUAGES: tuple[dict[str, str], ...] = (
    {"id": "pt", "label": "Portuguese"},
    {"id": "en", "label": "English"},
    {"id": "ko", "label": "Korean"},
    {"id": "ja", "label": "Japanese"},
    {"id": "ar", "label": "Arabic"},
    {"id": "bg", "label": "Bulgarian"},
    {"id": "cs", "label": "Czech"},
    {"id": "da", "label": "Danish"},
    {"id": "de", "label": "German"},
    {"id": "el", "label": "Greek"},
    {"id": "es", "label": "Spanish"},
    {"id": "et", "label": "Estonian"},
    {"id": "fi", "label": "Finnish"},
    {"id": "fr", "label": "French"},
    {"id": "hi", "label": "Hindi"},
    {"id": "hr", "label": "Croatian"},
    {"id": "hu", "label": "Hungarian"},
    {"id": "id", "label": "Indonesian"},
    {"id": "it", "label": "Italian"},
    {"id": "lt", "label": "Lithuanian"},
    {"id": "lv", "label": "Latvian"},
    {"id": "nl", "label": "Dutch"},
    {"id": "pl", "label": "Polish"},
    {"id": "ro", "label": "Romanian"},
    {"id": "ru", "label": "Russian"},
    {"id": "sk", "label": "Slovak"},
    {"id": "sl", "label": "Slovenian"},
    {"id": "sv", "label": "Swedish"},
    {"id": "tr", "label": "Turkish"},
    {"id": "uk", "label": "Ukrainian"},
    {"id": "vi", "label": "Vietnamese"},
    {"id": "na", "label": "Unknown / fallback"},
)

_SUPERTONIC_PRESET_VOICES: dict[str, dict[str, str]] = {
    "M1": {"name": "M1", "gender": "male", "description": "Balanced male preset."},
    "M2": {"name": "M2", "gender": "male", "description": "Warm male preset."},
    "M3": {"name": "M3", "gender": "male", "description": "Clear narration male preset."},
    "M4": {"name": "M4", "gender": "male", "description": "Bright male preset."},
    "M5": {"name": "M5", "gender": "male", "description": "Expressive male preset."},
    "F1": {"name": "F1", "gender": "female", "description": "Balanced female preset."},
    "F2": {"name": "F2", "gender": "female", "description": "Warm female preset."},
    "F3": {"name": "F3", "gender": "female", "description": "Clear narration female preset."},
    "F4": {"name": "F4", "gender": "female", "description": "Bright female preset."},
    "F5": {"name": "F5", "gender": "female", "description": "Expressive female preset."},
}


def _ensure_storage() -> None:
    with _STORAGE_LOCK:
        _SUPERTONIC_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        _SUPERTONIC_VOICES_DIR.mkdir(parents=True, exist_ok=True)
        _SUPERTONIC_CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file() and not child.is_symlink():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _normalize_model_id(model_id: str | None = None) -> str:
    normalized = str(model_id or "").strip() or os.environ.get("SUPERTONIC_DEFAULT_MODEL", "")
    normalized = normalized.strip() or SUPERTONIC_DEFAULT_MODEL_ID
    if normalized not in _SUPERTONIC_MODELS:
        raise KeyError(f"unknown supertonic model: {model_id}")
    return normalized


def _normalize_language_id(language_id: str | None = None) -> str:
    normalized = str(language_id or "").strip().lower() or SUPERTONIC_DEFAULT_LANGUAGE_ID
    supported = {item["id"] for item in _SUPERTONIC_LANGUAGES}
    return normalized if normalized in supported else "na"


def _normalize_voice_id(voice_id: str) -> str:
    raw = str(voice_id or "").strip()
    if re.fullmatch(r"[mMfF][1-5]", raw):
        return raw.upper()
    return _slugify(raw)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-._")
    return normalized[:80] or "custom-voice"


def _safe_json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def supertonic_root() -> Path:
    _ensure_storage()
    return _SUPERTONIC_ROOT


def supertonic_model_definitions() -> list[dict[str, Any]]:
    return [supertonic_model_metadata(model_id) for model_id in _SUPERTONIC_MODELS]


def supertonic_model_metadata(model_id: str) -> dict[str, Any]:
    normalized = _normalize_model_id(model_id)
    definition = _SUPERTONIC_MODELS[normalized]
    return {
        "model_id": definition.id,
        "id": definition.id,
        "title": definition.title,
        "repo_id": definition.repo_id,
        "description": definition.description,
        "revision": definition.revision,
        "languages": definition.languages,
        "legacy": definition.legacy,
        "default": definition.id == SUPERTONIC_DEFAULT_MODEL_ID,
    }


def supertonic_model_path(model_id: str | None = None) -> Path:
    normalized = _normalize_model_id(model_id)
    return _SUPERTONIC_MODELS_DIR / normalized


def supertonic_model_downloaded(model_id: str | None = None) -> bool:
    path = supertonic_model_path(model_id)
    return path.exists() and any(path.rglob("*.onnx"))


def supertonic_model_status(model_id: str | None = None) -> dict[str, Any]:
    normalized = _normalize_model_id(model_id)
    metadata = supertonic_model_metadata(normalized)
    path = supertonic_model_path(normalized)
    bytes_on_disk = _dir_size(path)
    return {
        **metadata,
        "downloaded": supertonic_model_downloaded(normalized),
        "bytes": bytes_on_disk,
        "local_path": str(path),
    }


def supertonic_model_catalog_payload() -> dict[str, Any]:
    requested = os.environ.get(
        "SUPERTONIC_AVAILABLE_MODELS",
        "supertonic-3,supertonic-2,supertonic",
    )
    model_ids = [item.strip() for item in requested.split(",") if item.strip()]
    if not model_ids:
        model_ids = list(_SUPERTONIC_MODELS)
    items = [supertonic_model_status(model_id) for model_id in model_ids if model_id in _SUPERTONIC_MODELS]
    return {
        "items": items,
        "default_model": _normalize_model_id(None),
        "models_dir": str(_SUPERTONIC_MODELS_DIR),
        "asset_root": str(_SUPERTONIC_ROOT),
        "acceleration": supertonic_acceleration_status(),
    }


def ensure_supertonic_model(
    model_id: str | None = None,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    normalized = _normalize_model_id(model_id)
    target = supertonic_model_path(normalized)
    if supertonic_model_downloaded(normalized):
        total = _dir_size(target)
        if progress_callback is not None:
            progress_callback(total, total)
        return target

    _ensure_storage()
    definition = _SUPERTONIC_MODELS[normalized]
    revision = os.environ.get("SUPERTONIC_MODEL_REVISION", "").strip() or definition.revision
    if progress_callback is not None:
        progress_callback(0, 0)

    from huggingface_hub import snapshot_download

    target.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {
        "repo_id": definition.repo_id,
        "revision": revision,
        "local_dir": str(target),
        "allow_patterns": [
            "*.json",
            "*.onnx",
            "*.txt",
            "*.md",
            "*.yaml",
            "*.yml",
            "*.model",
            "*.vocab",
            "LICENSE*",
            "README*",
            "config*",
            "tokenizer*",
            "phonemizer/*",
            "voice_styles/*",
        ],
    }
    snapshot_download(**kwargs)

    if not supertonic_model_downloaded(normalized):
        raise RuntimeError(f"Supertonic model snapshot did not contain ONNX assets: {definition.repo_id}")

    marker = {
        "model_id": definition.id,
        "repo_id": definition.repo_id,
        "revision": revision,
        "downloaded_at": datetime.now(UTC).isoformat(),
    }
    (target / _SUPERTONIC_MODEL_MARKER).write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    total = _dir_size(target)
    if progress_callback is not None:
        progress_callback(total, total)
    return target


def delete_supertonic_model(model_id: str) -> dict[str, Any]:
    normalized = _normalize_model_id(model_id)
    path = supertonic_model_path(normalized)
    existed = path.exists()
    bytes_freed = _dir_size(path)
    if existed:
        shutil.rmtree(path, ignore_errors=True)
    voice_root = _SUPERTONIC_VOICES_DIR / normalized
    if voice_root.exists():
        shutil.rmtree(voice_root, ignore_errors=True)
    return {
        "model_id": normalized,
        "removed": existed,
        "bytes_freed": int(bytes_freed),
        "local_path": str(path),
    }


def supertonic_language_options() -> list[dict[str, str]]:
    return [{"id": item["id"], "label": item["label"]} for item in _SUPERTONIC_LANGUAGES]


def _language_label(language_id: str) -> str:
    for item in _SUPERTONIC_LANGUAGES:
        if item["id"] == language_id:
            return item["label"]
    return language_id


def _read_custom_voice_index() -> dict[str, dict[str, Any]]:
    if not _SUPERTONIC_CUSTOM_INDEX_PATH.exists():
        return {}
    try:
        data = json.loads(_SUPERTONIC_CUSTOM_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    items = _safe_json_object(data.get("items") if isinstance(data, dict) else data)
    return {str(key): _safe_json_object(value) for key, value in items.items()}


def _write_custom_voice_index(items: dict[str, dict[str, Any]]) -> None:
    _ensure_storage()
    payload = {
        "items": items,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _SUPERTONIC_CUSTOM_INDEX_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _custom_voice_path(voice_id: str) -> Path:
    return _SUPERTONIC_CUSTOM_VOICES_DIR / f"{_normalize_voice_id(voice_id)}.json"


def _managed_voice_path(model_id: str, voice_id: str) -> Path:
    return _SUPERTONIC_VOICES_DIR / _normalize_model_id(model_id) / f"{_normalize_voice_id(voice_id)}.json"


def _validate_voice_style_payload(payload: Any) -> dict[str, Any]:
    data = _safe_json_object(payload)
    style_ttl = data.get("style_ttl")
    style_dp = data.get("style_dp")
    if not isinstance(style_ttl, (list, dict)) or not isinstance(style_dp, (list, dict)):
        raise ValueError("Supertonic voice JSON must contain style_ttl and style_dp arrays or objects")
    return data


def _load_json_file(path: Path) -> dict[str, Any]:
    return _validate_voice_style_payload(json.loads(path.read_text(encoding="utf-8")))


def _preset_voice_source_path(model_id: str, voice_id: str) -> Path:
    normalized_model = _normalize_model_id(model_id)
    normalized_voice = _normalize_voice_id(voice_id)
    model_root = supertonic_model_path(normalized_model)
    candidates = [
        model_root / "voice_styles" / f"{normalized_voice}.json",
        model_root / "voice_styles" / f"{normalized_voice.lower()}.json",
        model_root / "voices" / f"{normalized_voice}.json",
        model_root / "styles" / f"{normalized_voice}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for candidate in model_root.rglob("*.json"):
        if candidate.stem.lower() == normalized_voice.lower():
            try:
                _load_json_file(candidate)
            except Exception:
                continue
            return candidate
    raise FileNotFoundError(f"voice style {normalized_voice} not found in Supertonic model snapshot {normalized_model}")


def supertonic_voice_metadata(voice_id: str) -> dict[str, Any] | None:
    normalized = _normalize_voice_id(voice_id)
    preset = _SUPERTONIC_PRESET_VOICES.get(normalized)
    if preset is not None:
        return {
            "voice_id": normalized,
            "name": preset["name"],
            "gender": preset["gender"],
            "kind": "preset",
            "description": preset["description"],
            "language_id": "multilingual",
            "language_label": "Multilingual",
        }
    custom = _read_custom_voice_index().get(normalized)
    if custom:
        return {
            "voice_id": normalized,
            "name": str(custom.get("name") or normalized),
            "gender": str(custom.get("gender") or "custom"),
            "kind": "custom",
            "description": str(custom.get("description") or "Imported Voice Builder JSON."),
            "language_id": str(custom.get("language_id") or "multilingual"),
            "language_label": str(custom.get("language_label") or "Multilingual"),
            "model_id": str(custom.get("model_id") or ""),
        }
    return None


def downloaded_supertonic_voice_ids(model_id: str | None = None) -> set[str]:
    _ensure_storage()
    normalized_model = _normalize_model_id(model_id)
    downloaded: set[str] = set()
    for path in (_SUPERTONIC_VOICES_DIR / normalized_model).glob("*.json"):
        downloaded.add(_normalize_voice_id(path.stem))
    downloaded.update(_read_custom_voice_index())
    return downloaded


def resolve_supertonic_voice_path(voice_id: str, model_id: str | None = None) -> Path:
    normalized = _normalize_voice_id(voice_id)
    if normalized in _SUPERTONIC_PRESET_VOICES:
        path = _managed_voice_path(_normalize_model_id(model_id), normalized)
        if not path.exists():
            raise FileNotFoundError(f"Supertonic voice is not downloaded: {normalized}")
        return path
    path = _custom_voice_path(normalized)
    if not path.exists():
        raise FileNotFoundError(f"Supertonic custom voice is not imported: {normalized}")
    return path


def resolve_supertonic_model_path(model_id: str | None = None) -> Path:
    normalized = _normalize_model_id(model_id)
    path = supertonic_model_path(normalized)
    if not supertonic_model_downloaded(normalized):
        raise FileNotFoundError(f"Supertonic model is not downloaded: {normalized}")
    return path


def list_supertonic_voices(model_id: str | None = None, language_id: str | None = None) -> list[dict[str, Any]]:
    normalized_model = _normalize_model_id(model_id)
    selected_language = _normalize_language_id(language_id)
    downloaded = downloaded_supertonic_voice_ids(normalized_model)
    items: list[dict[str, Any]] = []
    for voice_id, preset in _SUPERTONIC_PRESET_VOICES.items():
        path = _managed_voice_path(normalized_model, voice_id)
        is_downloaded = voice_id in downloaded and path.exists()
        items.append(
            {
                "voice_id": voice_id,
                "name": preset["name"],
                "gender": preset["gender"],
                "kind": "preset",
                "description": preset["description"],
                "model_id": normalized_model,
                "language_id": selected_language,
                "language_label": _language_label(selected_language),
                "downloaded": is_downloaded,
                "local_path": str(path) if is_downloaded else "",
                "bytes": int(path.stat().st_size) if is_downloaded else 0,
            }
        )
    for voice_id, metadata in sorted(_read_custom_voice_index().items()):
        path = _custom_voice_path(voice_id)
        items.append(
            {
                "voice_id": voice_id,
                "name": str(metadata.get("name") or voice_id),
                "gender": str(metadata.get("gender") or "custom"),
                "kind": "custom",
                "description": str(metadata.get("description") or "Imported Voice Builder JSON."),
                "model_id": str(metadata.get("model_id") or normalized_model),
                "language_id": selected_language,
                "language_label": _language_label(selected_language),
                "downloaded": path.exists(),
                "local_path": str(path) if path.exists() else "",
                "bytes": int(path.stat().st_size) if path.exists() else 0,
            }
        )
    return items


def supertonic_voice_catalog_payload(
    model_id: str | None = None,
    language_id: str | None = None,
) -> dict[str, Any]:
    normalized_model = _normalize_model_id(model_id)
    selected_language = _normalize_language_id(language_id)
    return {
        "items": list_supertonic_voices(normalized_model, selected_language),
        "available_languages": supertonic_language_options(),
        "selected_model": normalized_model,
        "selected_language": selected_language,
        "default_model": SUPERTONIC_DEFAULT_MODEL_ID,
        "default_language": SUPERTONIC_DEFAULT_LANGUAGE_ID,
        "default_voice": SUPERTONIC_DEFAULT_VOICE_ID,
        "downloaded_voice_ids": sorted(downloaded_supertonic_voice_ids(normalized_model)),
        "provider_connected": True,
        "acceleration": supertonic_acceleration_status(),
    }


def ensure_supertonic_voice_downloaded(
    voice_id: str,
    model_id: str | None = None,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    normalized_model = _normalize_model_id(model_id)
    normalized_voice = _normalize_voice_id(voice_id)
    metadata = supertonic_voice_metadata(normalized_voice)
    if metadata is None:
        raise KeyError(f"unknown supertonic voice: {voice_id}")
    if metadata.get("kind") == "custom":
        path = _custom_voice_path(normalized_voice)
        if not path.exists():
            raise FileNotFoundError(f"custom Supertonic voice is missing: {normalized_voice}")
        total = path.stat().st_size
        if progress_callback is not None:
            progress_callback(total, total)
        return {**metadata, "downloaded": True, "bytes": total, "local_path": str(path)}

    if not supertonic_model_downloaded(normalized_model):
        raise FileNotFoundError(f"Supertonic model must be downloaded first: {normalized_model}")
    target = _managed_voice_path(normalized_model, normalized_voice)
    if target.exists() and target.stat().st_size > 0:
        total = target.stat().st_size
        if progress_callback is not None:
            progress_callback(total, total)
        return {**metadata, "downloaded": True, "bytes": total, "local_path": str(target)}

    source = _preset_voice_source_path(normalized_model, normalized_voice)
    payload = _load_json_file(source)
    _ensure_storage()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    total = target.stat().st_size
    if progress_callback is not None:
        progress_callback(total, total)
    return {**metadata, "downloaded": True, "bytes": total, "local_path": str(target)}


def import_supertonic_voice_json(
    raw_bytes: bytes,
    *,
    name: str = "",
    model_id: str | None = None,
) -> dict[str, Any]:
    if len(raw_bytes) > _MAX_CUSTOM_VOICE_BYTES:
        raise ValueError("Supertonic custom voice JSON is too large")
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Supertonic voice JSON") from exc
    payload = _validate_voice_style_payload(payload)
    requested_name = str(name or payload.get("name") or payload.get("voice_name") or "").strip()
    digest = hashlib.sha256(raw_bytes).hexdigest()[:10]
    voice_id = _slugify(requested_name or f"custom-{digest}")
    if voice_id in _SUPERTONIC_PRESET_VOICES:
        voice_id = f"custom-{voice_id.lower()}"
    if not voice_id.startswith("custom-"):
        voice_id = f"custom-{voice_id}"
    normalized_model = _normalize_model_id(model_id)
    _ensure_storage()
    path = _custom_voice_path(voice_id)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)

    index = _read_custom_voice_index()
    index[voice_id] = {
        "voice_id": voice_id,
        "name": requested_name or voice_id,
        "model_id": normalized_model,
        "kind": "custom",
        "gender": "custom",
        "language_id": "multilingual",
        "language_label": "Multilingual",
        "description": "Imported Voice Builder JSON.",
        "local_path": str(path),
        "bytes": path.stat().st_size,
        "imported_at": datetime.now(UTC).isoformat(),
    }
    _write_custom_voice_index(index)
    return {**index[voice_id], "downloaded": True}


def delete_supertonic_voice(voice_id: str, model_id: str | None = None) -> dict[str, Any]:
    normalized_voice = _normalize_voice_id(voice_id)
    if normalized_voice in _SUPERTONIC_PRESET_VOICES:
        path = _managed_voice_path(_normalize_model_id(model_id), normalized_voice)
        existed = path.exists()
        bytes_freed = path.stat().st_size if existed else 0
        if existed:
            path.unlink(missing_ok=True)
        return {
            "voice_id": normalized_voice,
            "removed": existed,
            "bytes_freed": int(bytes_freed),
            "local_path": str(path),
        }

    path = _custom_voice_path(normalized_voice)
    existed = path.exists()
    bytes_freed = path.stat().st_size if existed else 0
    if existed:
        path.unlink(missing_ok=True)
    index = _read_custom_voice_index()
    index.pop(normalized_voice, None)
    _write_custom_voice_index(index)
    return {
        "voice_id": normalized_voice,
        "removed": existed,
        "bytes_freed": int(bytes_freed),
        "local_path": str(path),
    }


def supertonic_acceleration_status() -> dict[str, Any]:
    configured = [
        item.strip()
        for item in os.environ.get("SUPERTONIC_ONNX_PROVIDERS", "CPUExecutionProvider").split(",")
        if item.strip()
    ]
    coreml_experimental = os.environ.get("SUPERTONIC_COREML_EXPERIMENTAL", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    metal_enabled = os.environ.get("METAL_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
    apple_silicon = False
    with_coreml = False
    available_providers: list[str] = []
    try:
        from koda.services.apple_silicon import is_apple_silicon

        apple_silicon = is_apple_silicon()
    except Exception:
        apple_silicon = False
    try:
        import onnxruntime as ort

        available_providers = list(ort.get_available_providers())
        with_coreml = "CoreMLExecutionProvider" in available_providers
    except Exception:
        available_providers = []
        with_coreml = False

    if coreml_experimental and metal_enabled and apple_silicon and with_coreml:
        selected = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        return {
            "mode": "coreml_experimental",
            "label": "CoreML experimental ativo",
            "providers": selected,
            "available_providers": available_providers,
            "coreml_available": True,
            "metal_enabled": metal_enabled,
            "apple_silicon": apple_silicon,
        }
    return {
        "mode": "cpu_onnx",
        "label": "CPU ONNX oficial" if not coreml_experimental else "CoreML indisponivel",
        "providers": configured or ["CPUExecutionProvider"],
        "available_providers": available_providers,
        "coreml_available": with_coreml,
        "metal_enabled": metal_enabled,
        "apple_silicon": apple_silicon,
    }
