"""Extract and send files created by provider execution via Telegram."""

import os
import re
from pathlib import Path
from typing import BinaryIO

from telegram import Update

from koda.logging_config import get_logger
from koda.telegram_types import BotContext

log = get_logger(__name__)

_FILE_CREATING_TOOLS = {"Write", "write_file", "Edit", "edit_file", "file_write", "file_edit", "file_move"}
_ARTIFACT_DISCOVERY_TOOLS = {
    "Bash",
    "shell_execute",
    "shell_bg",
    "shell_output",
    "browser_screenshot",
    "browser_pdf",
    "browser_download",
    "file_write",
    "file_edit",
    "file_move",
}
_EXPLICIT_PATH_KEYS = ("file_path", "path", "destination", "output_path", "save_path")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
GIF_EXTS = {".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".m4a"}
VOICE_EXTS = {".ogg"}
DOCUMENT_EXTS = {
    ".csv",
    ".doc",
    ".docx",
    ".html",
    ".json",
    ".md",
    ".odp",
    ".ods",
    ".odt",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rtf",
    ".tex",
    ".tsv",
    ".txt",
    ".xls",
    ".xlsx",
    ".zip",
}
ARTIFACT_EXTS = IMAGE_EXTS | GIF_EXTS | VIDEO_EXTS | AUDIO_EXTS | VOICE_EXTS | DOCUMENT_EXTS
_ARTIFACT_EXT_PATTERN = "|".join(sorted(re.escape(ext.lstrip(".")) for ext in ARTIFACT_EXTS))
_QUOTED_ARTIFACT_PATH_RE = re.compile(rf"""["']([^"'\n]+\.(?:{_ARTIFACT_EXT_PATTERN}))["']""", re.IGNORECASE)
_BARE_ARTIFACT_PATH_RE = re.compile(
    rf"""(?<![\w./~-])([~./\w-][^\s"'<>|;]*\.(?:{_ARTIFACT_EXT_PATTERN}))(?![\w.-])""",
    re.IGNORECASE,
)

MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# Magic bytes for image validation
_IMAGE_SIGNATURES = [
    (b"\x89PNG", 4),  # PNG
    (b"\xff\xd8\xff", 3),  # JPEG
    (b"BM", 2),  # BMP
    (b"RIFF", 4),  # WebP (RIFF....WEBP)
]


def _is_valid_image(path: str) -> bool:
    """Check if file starts with a known image magic byte signature."""
    try:
        with open(path, "rb") as f:
            header = f.read(12)
    except OSError:
        return False
    for sig, length in _IMAGE_SIGNATURES:
        if header[:length] == sig:
            if sig == b"RIFF":
                return header[8:12] == b"WEBP"
            return True
    return False


def _format_size(size_bytes: int) -> str:
    """Format file size as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def _add_unique_path(paths: list[str], seen: set[str], path: str | os.PathLike[str]) -> None:
    value = os.fspath(path)
    if value and value not in seen:
        seen.add(value)
        paths.append(value)


def _resolve_existing_artifact(candidate: str, work_dir: str | None) -> str | None:
    candidate = candidate.strip().strip("\"'`")
    candidate = candidate.rstrip(").,;:]}")
    if not candidate:
        return None

    path = Path(os.path.expanduser(candidate))
    if not path.is_absolute():
        if not work_dir:
            return None
        path = Path(work_dir) / path

    try:
        resolved = path.resolve()
    except OSError:
        return None

    if work_dir:
        try:
            resolved.relative_to(Path(work_dir).resolve())
        except ValueError:
            return None

    return str(resolved) if resolved.is_file() else None


def _iter_text_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        texts: list[str] = []
        for item in value:
            texts.extend(_iter_text_values(item))
        return texts
    if isinstance(value, dict):
        texts = []
        for key in (
            "command",
            "output",
            "stdout",
            "stderr",
            "text",
            "summary",
            "title",
            "path",
            "file_path",
            "destination",
            "output_path",
            "save_path",
            "artifact",
            "artifacts",
        ):
            if key in value:
                texts.extend(_iter_text_values(value[key]))
        return texts
    return []


def _extract_existing_artifact_paths_from_texts(values: list[object], work_dir: str | None) -> list[str]:
    if not work_dir:
        return []
    candidates: list[str] = []
    for value in values:
        for text in _iter_text_values(value):
            candidates.extend(match.group(1) for match in _QUOTED_ARTIFACT_PATH_RE.finditer(text))
            candidates.extend(match.group(1) for match in _BARE_ARTIFACT_PATH_RE.finditer(text))

    paths: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = _resolve_existing_artifact(candidate, work_dir)
        if resolved:
            _add_unique_path(paths, seen, resolved)
    return paths


def _extract_artifact_paths_from_native_item(item: dict, work_dir: str | None) -> list[str]:
    return _extract_existing_artifact_paths_from_texts([item], work_dir)


def _explicit_path_from_mapping(value: object, keys: tuple[str, ...] = _EXPLICIT_PATH_KEYS) -> object | None:
    if not isinstance(value, dict):
        return None
    for key in keys:
        if key in value:
            found: object = value[key]
            return found
    return None


def _is_artifact_discovery_step(step: dict) -> bool:
    tool = str(step.get("tool") or step.get("name") or "")
    metadata_obj = step.get("metadata")
    metadata: dict[str, object] = metadata_obj if isinstance(metadata_obj, dict) else {}
    if bool(metadata.get("write")):
        return True
    if tool in _ARTIFACT_DISCOVERY_TOOLS:
        return True
    return tool.startswith(("shell_", "browser_download", "browser_screenshot"))


def _extract_artifact_paths_from_tool_step(step: dict, work_dir: str | None) -> list[str]:
    if not _is_artifact_discovery_step(step):
        return []
    if step.get("success") is False:
        return []
    tool = str(step.get("tool") or step.get("name") or "")
    keys: tuple[str, ...]
    if tool in {"Bash", "shell_execute", "shell_bg", "shell_output"} or tool.startswith("shell_"):
        keys = ("output", "data", "metadata")
    else:
        keys = ("params", "input", "output", "data", "metadata")
    values: list[object] = []
    for key in keys:
        if key in step:
            values.append(step[key])
    return _extract_existing_artifact_paths_from_texts(values, work_dir)


def _extract_artifact_paths_from_tool_use(block: dict, work_dir: str | None) -> list[str]:
    name = str(block.get("name") or block.get("tool") or "")
    if name not in _ARTIFACT_DISCOVERY_TOOLS and not name.startswith("shell_"):
        return []
    if name in {"Bash", "shell_execute", "shell_bg", "shell_output"} or name.startswith("shell_"):
        values = [block.get("output", {}), block.get("result", {})]
    else:
        values = [block.get("input", {}), block.get("output", {}), block.get("result", {})]
    return _extract_existing_artifact_paths_from_texts(values, work_dir)


def _normalize_explicit_path(path: object, work_dir: str | None) -> str | None:
    if not isinstance(path, str) or not path.strip():
        return None
    if not work_dir:
        return path
    candidate = Path(os.path.expanduser(path.strip()))
    if candidate.is_absolute():
        return str(candidate)
    return str(Path(work_dir) / candidate)


def extract_created_files(
    tool_uses: list[dict],
    native_items: list[dict] | None = None,
    tool_execution_trace: list[dict] | None = None,
    work_dir: str | None = None,
) -> list[str]:
    """Extract unique file paths from tool and provider-native creation signals."""
    seen: set[str] = set()
    paths: list[str] = []
    for block in tool_uses:
        if block.get("name") not in _FILE_CREATING_TOOLS:
            for fp in _extract_artifact_paths_from_tool_use(block, work_dir):
                _add_unique_path(paths, seen, fp)
            continue
        explicit_fp = _normalize_explicit_path(_explicit_path_from_mapping(block.get("input") or {}), work_dir)
        if explicit_fp:
            _add_unique_path(paths, seen, explicit_fp)
        for fp in _extract_artifact_paths_from_tool_use(block, work_dir):
            _add_unique_path(paths, seen, fp)
    for item in native_items or []:
        item_type = item.get("type")
        if item_type == "file_change":
            kind = str(item.get("kind") or item.get("change_type") or "").lower()
            if kind and kind != "add":
                continue
            native_fp = _normalize_explicit_path(item.get("path") or item.get("file_path"), work_dir)
            if native_fp:
                _add_unique_path(paths, seen, native_fp)
            continue
        if item_type == "command_execution":
            for fp in _extract_artifact_paths_from_native_item(item, work_dir):
                _add_unique_path(paths, seen, fp)
    for step in tool_execution_trace or []:
        for fp in _extract_artifact_paths_from_tool_step(step, work_dir):
            _add_unique_path(paths, seen, fp)
    return paths


async def _send_media(
    method_name: str,
    file_obj: BinaryIO,
    chat_id: int,
    context: BotContext,
    update: Update | None,
    caption: str,
) -> None:
    """Send media via reply or context.bot, eliminating if/else duplication."""
    if update and update.message:
        method = getattr(update.message, f"reply_{method_name}")
        await method(**{method_name: file_obj}, caption=caption)
    else:
        method = getattr(context.bot, f"send_{method_name}")
        await method(chat_id=chat_id, **{method_name: file_obj}, caption=caption)


async def _send_media_with_document_fallback(
    method_name: str,
    file_obj: BinaryIO,
    chat_id: int,
    context: BotContext,
    update: Update | None,
    caption: str,
    *,
    path: str,
) -> None:
    try:
        await _send_media(method_name, file_obj, chat_id, context, update, caption)
    except Exception:
        if method_name == "document":
            raise
        log.warning(f"{method_name}_send_failed_fallback_document", path=path)
        file_obj.seek(0)
        await _send_media("document", file_obj, chat_id, context, update, caption)


async def send_created_files(
    paths: list[str],
    chat_id: int,
    context: BotContext,
    update: Update | None,
) -> int:
    """Send created files to Telegram. Returns count of files sent."""
    sent = 0
    for path in paths:
        if not os.path.isfile(path):
            log.debug("artifact_skip_missing", path=path)
            continue
        file_size = os.path.getsize(path)
        if file_size > MAX_FILE_SIZE:
            log.debug("artifact_skip_large", path=path)
            continue

        filename = os.path.basename(path)
        ext = os.path.splitext(filename)[1].lower()
        caption = f"{filename} ({_format_size(file_size)})"

        try:
            with open(path, "rb") as f:
                if ext in IMAGE_EXTS:
                    if file_size > MAX_PHOTO_SIZE or not _is_valid_image(path):
                        await _send_media("document", f, chat_id, context, update, caption)
                    else:
                        await _send_media_with_document_fallback(
                            "photo",
                            f,
                            chat_id,
                            context,
                            update,
                            caption,
                            path=path,
                        )
                elif ext in GIF_EXTS:
                    await _send_media_with_document_fallback(
                        "animation",
                        f,
                        chat_id,
                        context,
                        update,
                        caption,
                        path=path,
                    )
                elif ext in VIDEO_EXTS:
                    await _send_media_with_document_fallback(
                        "video",
                        f,
                        chat_id,
                        context,
                        update,
                        caption,
                        path=path,
                    )
                elif ext in AUDIO_EXTS:
                    await _send_media_with_document_fallback(
                        "audio",
                        f,
                        chat_id,
                        context,
                        update,
                        caption,
                        path=path,
                    )
                elif ext in VOICE_EXTS:
                    await _send_media_with_document_fallback(
                        "voice",
                        f,
                        chat_id,
                        context,
                        update,
                        caption,
                        path=path,
                    )
                else:
                    await _send_media("document", f, chat_id, context, update, caption)
            sent += 1
        except Exception:
            log.exception("artifact_send_error", path=path)

    return sent
