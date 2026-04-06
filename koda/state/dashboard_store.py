"""Canonical dashboard read/write store over the primary backend."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from koda.memory.types import MemoryStatus
from koda.state.agent_scope import normalize_agent_scope
from koda.state_primary import (
    primary_execute,
    primary_fetch_all,
    primary_fetch_one,
    require_primary_state_backend,
    run_coro_sync,
)
from koda.utils.url_detector import extract_urls

_DEFAULT_MEMORY_LIMIT = 160
_MAX_MEMORY_LIMIT = 1200
_SEMANTIC_THRESHOLD = 0.56
_CURATION_EVENT_TYPE = "dashboard.memory_curation"
_ALLOWED_CURATION_ACTIONS = frozenset({"approve", "merge", "discard", "expire", "archive", "restore"})
_ALLOWED_CURATION_TARGETS = frozenset({"memory", "cluster"})
_EXECUTION_ARTIFACT_KINDS = frozenset(
    {
        "image",
        "audio",
        "video",
        "pdf",
        "docx",
        "spreadsheet",
        "text",
        "html",
        "json",
        "yaml",
        "xml",
        "csv",
        "tsv",
        "url",
        "code",
        "file",
    }
)
_EXECUTION_ARTIFACT_KIND_ALIASES = {
    "document": "docx",
    "documents": "docx",
    "sheet": "spreadsheet",
    "spreadsheet_file": "spreadsheet",
    "xlsx": "spreadsheet",
    "xls": "spreadsheet",
    "markdown": "text",
    "md": "text",
    "link": "url",
}
_CODE_ARTIFACT_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".css",
        ".go",
        ".html",
        ".java",
        ".js",
        ".jsx",
        ".json",
        ".kt",
        ".lua",
        ".mjs",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".sh",
        ".sql",
        ".swift",
        ".ts",
        ".tsx",
        ".vue",
        ".xml",
        ".yaml",
        ".yml",
    }
)


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().isoformat()


def _normalize_scope(agent_id: str) -> str:
    scope = normalize_agent_scope(agent_id)
    if not scope:
        raise ValueError("invalid agent_id")
    require_primary_state_backend(agent_id=scope, error="dashboard_primary_backend_unavailable")
    return scope


def _fetch_all(agent_id: str, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], run_coro_sync(primary_fetch_all(query, params, agent_id=agent_id)) or [])


def _fetch_one(agent_id: str, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    return cast(dict[str, Any] | None, run_coro_sync(primary_fetch_one(query, params, agent_id=agent_id)))


def _execute(agent_id: str, query: str, params: tuple[Any, ...] = ()) -> int:
    return int(run_coro_sync(primary_execute(query, params, agent_id=agent_id)) or 0)


def _iso(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _timestamp(value: Any) -> float:
    text = _iso(value)
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _clip_text(value: Any, limit: int = 140) -> str | None:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _safe_float(value: Any) -> float:
    try:
        parsed = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _parse_trace_envelope(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not entry or str(entry.get("event_type") or "") != "task.execution_trace":
        return None
    details = _json_object(entry.get("details_json"))
    if str(details.get("schema") or "") != "execution_trace":
        return None
    return details


def _duration_ms(row: dict[str, Any]) -> int | None:
    started = _timestamp(row.get("started_at"))
    completed = _timestamp(row.get("completed_at"))
    if started <= 0 or completed <= 0 or completed < started:
        return None
    return int((completed - started) * 1000)


def _build_in_clause(values: list[Any]) -> tuple[str, tuple[Any, ...]]:
    placeholders = ", ".join("?" for _ in values)
    return placeholders, tuple(values)


def _task_activity_iso(row: dict[str, Any]) -> str | None:
    return _iso(row.get("completed_at")) or _iso(row.get("started_at")) or _iso(row.get("created_at"))


def _public_agent_id(agent_id: str | None) -> str:
    return normalize_agent_scope(agent_id, fallback=agent_id)


def _latest_execution_trace_event(audit_events: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (item for item in reversed(audit_events) if str(item.get("event_type") or "") == "task.execution_trace"),
        None,
    )


def _trace_request_text(trace_event: dict[str, Any] | None) -> str | None:
    envelope = _parse_trace_envelope(trace_event)
    request = _json_object((envelope or {}).get("request"))
    return _iso(request.get("query_text"))


def _trace_response_text(trace_event: dict[str, Any] | None) -> str | None:
    envelope = _parse_trace_envelope(trace_event)
    assistant = _json_object((envelope or {}).get("assistant"))
    return _iso(assistant.get("response_text"))


def _session_cursor_key(activity_at: str | None, entry_id: str) -> tuple[float, str]:
    return (_timestamp(activity_at), str(entry_id))


def _encode_session_cursor(activity_at: str | None, entry_id: str) -> str:
    return f"{_iso(activity_at) or ''}|{entry_id}"


def _decode_session_cursor(cursor: str | None) -> tuple[float, str] | None:
    text = str(cursor or "").strip()
    if not text:
        return None
    timestamp, separator, entry_id = text.partition("|")
    if not separator or not entry_id:
        return None
    return _session_cursor_key(timestamp or None, entry_id)


def _normalize_execution_artifact_kind(
    kind: Any,
    *,
    mime_type: Any = None,
    path: Any = None,
    url: Any = None,
) -> str:
    normalized = _EXECUTION_ARTIFACT_KIND_ALIASES.get(str(kind or "").strip().lower(), str(kind or "").strip().lower())
    if normalized in _EXECUTION_ARTIFACT_KINDS:
        return normalized

    mime = str(mime_type or "").strip().lower()
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    if mime == "application/pdf":
        return "pdf"
    if mime in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }:
        return "docx"
    if mime in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }:
        return "spreadsheet"
    if mime == "text/html":
        return "html"
    if mime == "application/json":
        return "json"
    if mime in {"application/x-yaml", "text/yaml", "text/x-yaml"}:
        return "yaml"
    if mime in {"application/xml", "text/xml"}:
        return "xml"
    if mime == "text/csv":
        return "csv"
    if mime == "text/tab-separated-values":
        return "tsv"
    if mime.startswith("text/"):
        return "text"

    candidate_path = str(path or "").strip()
    candidate_url = str(url or "").strip()
    suffix_source = candidate_path or urlparse(candidate_url).path
    suffix = Path(suffix_source).suffix.lower()
    if suffix in _CODE_ARTIFACT_SUFFIXES:
        return "code"
    return {
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".gif": "image",
        ".webp": "image",
        ".svg": "image",
        ".mp4": "video",
        ".mov": "video",
        ".webm": "video",
        ".mp3": "audio",
        ".wav": "audio",
        ".pdf": "pdf",
        ".docx": "docx",
        ".doc": "docx",
        ".xlsx": "spreadsheet",
        ".xls": "spreadsheet",
        ".csv": "csv",
        ".tsv": "tsv",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".xml": "xml",
        ".json": "json",
        ".txt": "text",
        ".md": "text",
    }.get(suffix, "url" if candidate_url and not candidate_path else "file")


def _read_artifact_filename(path_or_url: str | None) -> str | None:
    value = str(path_or_url or "").strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        return Path(parsed.path).name or parsed.hostname or None
    return Path(value).name or None


def _normalize_artifact_urls(text: str | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in extract_urls(text or ""):
        url = raw.rstrip(".,;:!?)")
        if not url or url in seen:
            continue
        seen.add(url)
        normalized.append(url)
    return normalized


def _append_execution_artifact(
    artifacts: list[dict[str, Any]],
    seen_keys: set[str],
    artifact: dict[str, Any],
) -> None:
    dedupe_candidates = [
        f"url:{artifact.get('url')}" if artifact.get("url") else None,
        f"path:{artifact.get('path')}" if artifact.get("path") else None,
        f"id:{artifact.get('id')}" if artifact.get("id") else None,
    ]
    dedupe_key = next((candidate for candidate in dedupe_candidates if candidate), None)
    if dedupe_key and dedupe_key in seen_keys:
        return
    if dedupe_key:
        seen_keys.add(dedupe_key)
    artifacts.append(artifact)


def _build_execution_artifacts(raw_artifacts: Any, response_text: str | None, task_id: int) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    raw_payload = raw_artifacts if isinstance(raw_artifacts, dict) else {}

    for dossier_index, dossier in enumerate(_json_list(raw_payload.get("artifact_dossiers"))):
        dossier_record = _json_object(dossier)
        dossier_label = _iso(dossier_record.get("subject_label")) or f"Artifact bundle {dossier_index + 1}"
        dossier_summary = _clip_text(dossier_record.get("summary"), 280)
        for artifact_index, raw_artifact in enumerate(_json_list(dossier_record.get("artifacts"))):
            artifact_record = _json_object(raw_artifact)
            ref = _json_object(artifact_record.get("ref"))
            ref_metadata = _json_object(ref.get("metadata"))
            artifact_metadata = _json_object(artifact_record.get("metadata"))
            path = _iso(ref.get("path"))
            url = _iso(ref.get("url"))
            visual_paths = [
                candidate for item in _json_list(artifact_record.get("visual_paths")) if (candidate := _iso(item))
            ]
            preview_image_url = next(
                (candidate for candidate in visual_paths if candidate.startswith(("http://", "https://"))),
                None,
            )
            preview_image_path = next(
                (candidate for candidate in visual_paths if not candidate.startswith(("http://", "https://"))),
                None,
            )
            kind = _normalize_execution_artifact_kind(
                ref.get("kind"),
                mime_type=ref.get("mime_type"),
                path=path or preview_image_path,
                url=url,
            )
            label = _iso(ref.get("label")) or _read_artifact_filename(path or url) or dossier_label
            text_content = _clip_text(artifact_record.get("text_content"), 2000)
            summary = _clip_text(artifact_record.get("summary"), 320) or dossier_summary
            description = summary or _clip_text(text_content, 240)
            if kind == "json" and artifact_metadata:
                content: Any = artifact_metadata
            elif text_content:
                content = text_content
            elif artifact_metadata or ref_metadata:
                content = {
                    "metadata": artifact_metadata or ref_metadata,
                    "path": path,
                    "url": url,
                }
            else:
                content = summary or label
            _append_execution_artifact(
                artifacts,
                seen_keys,
                {
                    "id": _iso(ref.get("artifact_id")) or f"artifact-{task_id}-{dossier_index}-{artifact_index}",
                    "label": label,
                    "kind": kind,
                    "content": content,
                    "description": description,
                    "summary": summary,
                    "url": url,
                    "path": path,
                    "mime_type": _iso(ref.get("mime_type")),
                    "size_bytes": _safe_int(ref.get("size_bytes")) or None,
                    "source_type": _iso(ref.get("source_type")) or "artifact_dossier",
                    "status": _iso(artifact_record.get("status")),
                    "text_content": text_content,
                    "metadata": artifact_metadata or ref_metadata,
                    "visual_paths": visual_paths[:4],
                    "preview_image_url": preview_image_url
                    or (url if kind == "image" and url and url.startswith(("http://", "https://")) else None),
                    "preview_image_path": preview_image_path or (path if kind == "image" else None),
                    "domain": urlparse(url).hostname if url else None,
                    "site_name": _iso(ref_metadata.get("site_name")) or _iso(artifact_metadata.get("site_name")),
                    "unavailable": str(artifact_record.get("status") or "") in {"unresolved", "unsupported"},
                },
            )

    for native_index, raw_native in enumerate(_json_list(raw_payload.get("native_items"))):
        native_item = _json_object(raw_native)
        if str(native_item.get("type") or "") != "file_change":
            continue
        path = _iso(native_item.get("path")) or _iso(native_item.get("file_path"))
        if not path:
            continue
        kind = _normalize_execution_artifact_kind(
            native_item.get("artifact_kind"),
            mime_type=native_item.get("mime_type"),
            path=path,
        )
        change_kind = _iso(native_item.get("kind")) or _iso(native_item.get("change_type"))
        label = _read_artifact_filename(path) or f"File {native_index + 1}"
        _append_execution_artifact(
            artifacts,
            seen_keys,
            {
                "id": f"native-file-{task_id}-{native_index}",
                "label": label,
                "kind": kind,
                "content": native_item,
                "description": _clip_text(
                    f"{(change_kind or 'updated').replace('_', ' ')} file",
                    160,
                ),
                "summary": _clip_text(native_item.get("title") or change_kind or "Generated file", 220),
                "url": None,
                "path": path,
                "mime_type": _iso(native_item.get("mime_type")),
                "size_bytes": _safe_int(native_item.get("size_bytes")) or None,
                "source_type": "file_change",
                "status": "complete",
                "text_content": None,
                "metadata": native_item,
                "visual_paths": [],
                "preview_image_url": None,
                "preview_image_path": path if kind == "image" else None,
                "domain": None,
                "site_name": None,
                "unavailable": False,
            },
        )

    for url_index, url in enumerate(_normalize_artifact_urls(response_text)):
        _append_execution_artifact(
            artifacts,
            seen_keys,
            {
                "id": f"response-link-{task_id}-{url_index}",
                "label": _read_artifact_filename(url) or urlparse(url).hostname or "Link",
                "kind": "url",
                "content": url,
                "description": _clip_text(response_text, 240),
                "summary": "Link referenced in the assistant response",
                "url": url,
                "path": None,
                "mime_type": None,
                "size_bytes": None,
                "source_type": "assistant_response",
                "status": "complete",
                "text_content": _clip_text(response_text, 1200),
                "metadata": {},
                "visual_paths": [],
                "preview_image_url": None,
                "preview_image_path": None,
                "domain": urlparse(url).hostname,
                "site_name": None,
                "unavailable": False,
            },
        )

    if artifacts:
        return artifacts

    if response_text:
        return [
            {
                "id": f"response-{task_id}",
                "label": "Response",
                "kind": "text",
                "content": response_text,
                "description": _clip_text(response_text, 240),
                "summary": _clip_text(response_text, 320),
                "url": None,
                "path": None,
                "mime_type": None,
                "size_bytes": None,
                "source_type": "assistant_response",
                "status": "complete",
                "text_content": _clip_text(response_text, 1200),
                "metadata": {},
                "visual_paths": [],
                "preview_image_url": None,
                "preview_image_path": None,
                "domain": None,
                "site_name": None,
                "unavailable": False,
            }
        ]

    return []


def _sanitize_details(entry: dict[str, Any]) -> dict[str, Any]:
    details = _json_object(entry.get("details_json"))
    if details:
        return details
    details_field = entry.get("details")
    return details_field if isinstance(details_field, dict) else {}


def _tool_trace_from_audit(entry: dict[str, Any]) -> dict[str, Any]:
    details = _sanitize_details(entry)
    metadata = details.get("metadata")
    return {
        "id": f"audit-tool-{entry.get('id')}",
        "tool": str(details.get("tool") or entry.get("event_type") or "tool"),
        "category": str((metadata or {}).get("category") or "tool") if isinstance(metadata, dict) else "tool",
        "success": details.get("success") if isinstance(details.get("success"), bool) else None,
        "duration_ms": _safe_float(entry.get("duration_ms")) or None,
        "started_at": _iso(details.get("started_at")),
        "completed_at": _iso(entry.get("timestamp")),
        "params": details.get("params") if isinstance(details.get("params"), dict) else {},
        "output": _clip_text(details.get("output"), 4000),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "summary": _clip_text(details.get("summary") or details.get("error") or details.get("tool"), 180) or "",
        "redactions": details.get("redactions") if isinstance(details.get("redactions"), dict) else None,
    }


def _timeline_item(
    *,
    item_id: str,
    item_type: str,
    title: str,
    status: str,
    timestamp: str | None,
    summary: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_status = status if status in {"info", "success", "warning", "error"} else "info"
    return {
        "id": item_id,
        "type": item_type,
        "title": title,
        "summary": summary,
        "status": normalized_status,
        "timestamp": timestamp,
        "details": details or {},
    }


def _task_row_to_summary(
    agent_id: str,
    task: dict[str, Any],
    *,
    trace_event: dict[str, Any] | None,
    audit_events: list[dict[str, Any]],
) -> dict[str, Any]:
    envelope = _parse_trace_envelope(trace_event)
    runtime = _json_object((envelope or {}).get("runtime"))
    tools = (envelope or {}).get("tools")
    tool_count = (
        len(tools)
        if isinstance(tools, list)
        else len([item for item in audit_events if str(item.get("event_type") or "") == "task.tool_executed"])
    )
    warning_count = len([item for item in (runtime.get("warnings") or []) if isinstance(item, str)])
    return {
        "task_id": _safe_int(task.get("id")),
        "agent_id": _public_agent_id(agent_id),
        "bot_id": _public_agent_id(agent_id),
        "status": str(task.get("status") or "queued"),
        "query_text": _iso(task.get("query_text")),
        "model": _iso(task.get("model")),
        "session_id": _iso(task.get("session_id")),
        "user_id": _safe_int(task.get("user_id")),
        "chat_id": _safe_int(task.get("chat_id")),
        "created_at": _iso(task.get("created_at")) or "",
        "started_at": _iso(task.get("started_at")),
        "completed_at": _iso(task.get("completed_at")),
        "cost_usd": _safe_float(task.get("cost_usd")),
        "duration_ms": _duration_ms(task),
        "attempt": _safe_int(task.get("attempt")),
        "max_attempts": _safe_int(task.get("max_attempts")),
        "has_rich_trace": envelope is not None,
        "trace_source": "trace" if envelope is not None else ("legacy" if audit_events else "missing"),
        "tool_count": tool_count,
        "warning_count": warning_count,
        "stop_reason": _iso(runtime.get("stop_reason")),
        "error_message": _iso(task.get("error_message")),
    }


def _find_execution_match(
    executions: list[dict[str, Any]],
    *,
    query_text: str | None,
    timestamp: str | None,
) -> int:
    query_preview = " ".join((query_text or "").split()).strip().lower()
    target_ts = _timestamp(timestamp)
    best_index = -1
    best_diff = float("inf")
    best_task = float("inf")
    for index, execution in enumerate(executions):
        if query_preview and " ".join(str(execution.get("query_text") or "").split()).strip().lower() == query_preview:
            diff = abs(_timestamp(_task_activity_iso(execution)) - target_ts)
            task_id = _safe_int(execution.get("task_id"))
            if diff < best_diff or (diff == best_diff and task_id < best_task):
                best_index = index
                best_diff = diff
                best_task = task_id
    if best_index >= 0:
        return best_index
    for index, execution in enumerate(executions):
        diff = abs(_timestamp(_task_activity_iso(execution)) - target_ts)
        task_id = _safe_int(execution.get("task_id"))
        if diff < best_diff or (diff == best_diff and task_id < best_task):
            best_index = index
            best_diff = diff
            best_task = task_id
    return best_index


def _word_overlap_score(left: str, right: str) -> float:
    left_terms = {part for part in re_split_words(left) if len(part) > 2}
    right_terms = {part for part in re_split_words(right) if len(part) > 2}
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / max(len(left_terms), len(right_terms))


def re_split_words(value: str) -> list[str]:
    return [part for part in "".join(ch if ch.isalnum() else " " for ch in value.lower()).split() if part]


def _memory_status_to_review_status(status: str, *, expires_at: str | None, is_active: bool, action: str | None) -> str:
    normalized = status or MemoryStatus.ACTIVE.value
    if action == "merge" or normalized == MemoryStatus.SUPERSEDED.value:
        return "merged"
    if action == "discard" or normalized == MemoryStatus.REJECTED.value:
        return "discarded"
    if action == "archive" or normalized == MemoryStatus.INVALIDATED.value or not is_active:
        return "archived"
    if action == "expire" or normalized == MemoryStatus.STALE.value:
        return "expired"
    if action in {"approve", "restore"}:
        return "approved"
    if expires_at and _timestamp(expires_at) and _timestamp(expires_at) <= _now().timestamp():
        return "expired"
    return "pending"


def _memory_type_color(memory_type: str) -> str:
    return {
        "fact": "#ff8a4c",
        "procedure": "#5cc8ff",
        "event": "#ffd166",
        "preference": "#7bd389",
        "decision": "#ff6b6b",
        "problem": "#a78bfa",
        "task": "#60a5fa",
        "commit": "#34d399",
        "relationship": "#f472b6",
    }.get(memory_type, "#94a3b8")


def _memory_size(importance: float, access_count: int) -> float:
    return round(max(16.0, (importance * 18.0) + math.log1p(max(access_count, 0)) * 4.0 + 14.0), 2)


def _build_cluster_id(member_ids: list[int]) -> str:
    ordered = ",".join(str(item) for item in sorted(member_ids))
    digest = hashlib.sha256(ordered.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"cluster-{digest}"


class DashboardStore:
    """Read/write dashboard primitives over canonical stores only."""

    def get_agent_stats(self, agent_id: str) -> dict[str, Any]:
        scope = _normalize_scope(agent_id)
        task_counts = (
            _fetch_one(
                scope,
                """
            SELECT
                COUNT(*) AS total_tasks,
                COUNT(*) FILTER (WHERE status IN ('running', 'retrying')) AS active_tasks,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed_tasks,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed_tasks,
                COUNT(*) FILTER (WHERE status = 'queued') AS queued_tasks
            FROM tasks
            WHERE agent_id = ?
            """,
                (scope,),
            )
            or {}
        )
        query_stats = (
            _fetch_one(
                scope,
                """
                SELECT COUNT(*) AS total_queries,
                       COALESCE(SUM(cost_usd), 0) AS total_cost
                FROM query_history
                WHERE agent_id = ?
                """,
                (scope,),
            )
            or {}
        )
        today_cutoff = _now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        today_cost = (
            _fetch_one(
                scope,
                """
                SELECT COALESCE(SUM(cost_usd), 0) AS today_cost
                FROM query_history
                WHERE agent_id = ? AND timestamp >= ?
                """,
                (scope, today_cutoff),
            )
            or {}
        )
        daily_cutoff = (_now() - timedelta(days=30)).isoformat()
        daily_costs = _fetch_all(
            scope,
            """
            SELECT TO_CHAR(DATE_TRUNC('day', timestamp), 'YYYY-MM-DD') AS date,
                   COALESCE(SUM(cost_usd), 0) AS cost
            FROM query_history
            WHERE agent_id = ? AND timestamp >= ?
            GROUP BY 1
            ORDER BY 1 ASC
            """,
            (scope, daily_cutoff),
        )
        recent_tasks = _fetch_all(
            scope,
            """
            SELECT id, user_id, chat_id, status, query_text, provider, model, work_dir, attempt, max_attempts,
                   cost_usd, error_message, created_at, started_at, completed_at, session_id
            FROM tasks
            WHERE agent_id = ?
            ORDER BY id DESC
            LIMIT 5
            """,
            (scope,),
        )
        return {
            "agentId": scope,
            "totalTasks": _safe_int(task_counts.get("total_tasks")),
            "activeTasks": _safe_int(task_counts.get("active_tasks")),
            "completedTasks": _safe_int(task_counts.get("completed_tasks")),
            "failedTasks": _safe_int(task_counts.get("failed_tasks")),
            "queuedTasks": _safe_int(task_counts.get("queued_tasks")),
            "totalQueries": _safe_int(query_stats.get("total_queries")),
            "totalCost": _safe_float(query_stats.get("total_cost")),
            "todayCost": _safe_float(today_cost.get("today_cost")),
            "dbExists": True,
            "recentTasks": recent_tasks,
            "dailyCosts": [
                {"date": str(row.get("date") or ""), "cost": _safe_float(row.get("cost"))} for row in daily_costs
            ],
        }

    def _audit_events_for_tasks(self, agent_id: str, task_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        if not task_ids:
            return {}
        placeholders, params = _build_in_clause(task_ids)
        rows = _fetch_all(
            agent_id,
            f"""
            SELECT id, timestamp, event_type, agent_id, pod_name, user_id, task_id,
                   trace_id, details_json, cost_usd, duration_ms
            FROM audit_events
            WHERE task_id IN ({placeholders})
            ORDER BY timestamp ASC, id ASC
            """,
            params,
        )
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[_safe_int(row.get("task_id"))].append(row)
        return grouped

    def list_executions(
        self,
        agent_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        scope = _normalize_scope(agent_id)
        clauses = ["agent_id = ?"]
        params: list[Any] = [scope]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if search:
            clauses.append("LOWER(COALESCE(query_text, '')) LIKE ?")
            params.append(f"%{' '.join(search.lower().split())}%")
        params.extend([max(1, int(limit)), max(0, int(offset))])
        tasks = _fetch_all(
            scope,
            f"""
            SELECT id, user_id, chat_id, status, query_text, provider, model, work_dir, attempt, max_attempts,
                   cost_usd, error_message, created_at, started_at, completed_at, session_id, provider_session_id
            FROM tasks
            WHERE {" AND ".join(clauses)}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        audit_by_task = self._audit_events_for_tasks(scope, [_safe_int(task.get("id")) for task in tasks])
        summaries: list[dict[str, Any]] = []
        for task in tasks:
            events = audit_by_task.get(_safe_int(task.get("id")), [])
            trace_event = _latest_execution_trace_event(events)
            summaries.append(_task_row_to_summary(scope, task, trace_event=trace_event, audit_events=events))
        return summaries

    def _task_rows_for_session(self, agent_id: str, session_id: str) -> list[dict[str, Any]]:
        scope = _normalize_scope(agent_id)
        return _fetch_all(
            scope,
            """
            SELECT id, user_id, chat_id, status, query_text, provider, model, work_dir, attempt, max_attempts,
                   cost_usd, error_message, created_at, started_at, completed_at, session_id, provider_session_id
            FROM tasks
            WHERE agent_id = ? AND session_id = ?
            ORDER BY COALESCE(completed_at, started_at, created_at) ASC, id ASC
            """,
            (scope, session_id),
        )

    def _query_rows_for_session(
        self,
        agent_id: str,
        session_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        sql = [
            (
                "SELECT id, user_id, timestamp, query_text, response_text, "
                "cost_usd, provider, model, session_id, work_dir, error"
            ),
            "FROM query_history WHERE agent_id = ? AND session_id = ?",
            f"ORDER BY timestamp {'DESC' if descending else 'ASC'}, id {'DESC' if descending else 'ASC'}",
        ]
        params: list[Any] = [agent_id, session_id]
        if limit is not None:
            sql.append("LIMIT ?")
            params.append(limit)
            sql.append("OFFSET ?")
            params.append(max(0, int(offset)))
        return _fetch_all(agent_id, " ".join(sql), tuple(params))

    def _find_best_query_match(self, agent_id: str, task: dict[str, Any]) -> dict[str, Any] | None:
        session_id = _iso(task.get("session_id"))
        if not session_id:
            return None
        queries = self._query_rows_for_session(agent_id, session_id, limit=50)
        if not queries:
            return None
        query_preview = " ".join(str(task.get("query_text") or "").split()).strip().lower()
        task_ts = _timestamp(_task_activity_iso(task))
        best: dict[str, Any] | None = None
        best_diff = float("inf")
        for row in queries:
            row_preview = " ".join(str(row.get("query_text") or "").split()).strip().lower()
            if query_preview and row_preview and row_preview != query_preview:
                continue
            diff = abs(_timestamp(row.get("timestamp")) - task_ts)
            if diff < best_diff:
                best = row
                best_diff = diff
        if best is not None:
            return best
        return min(queries, key=lambda row: abs(_timestamp(row.get("timestamp")) - task_ts))

    def _build_execution_detail(
        self,
        agent_id: str,
        task: dict[str, Any],
        *,
        audit_events: list[dict[str, Any]] | None = None,
        matched_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        scope = _normalize_scope(agent_id)
        task_id = _safe_int(task.get("id"))
        events = list(audit_events or [])
        trace_event = _latest_execution_trace_event(events)
        envelope = _parse_trace_envelope(trace_event)
        runtime = _json_object((envelope or {}).get("runtime"))
        request = _json_object((envelope or {}).get("request"))
        assistant = _json_object((envelope or {}).get("assistant"))
        resolved_query = matched_query or self._find_best_query_match(scope, task)
        tools = []
        if isinstance((envelope or {}).get("tools"), list):
            for index, step in enumerate(cast(list[Any], (envelope or {}).get("tools") or [])):
                record = step if isinstance(step, dict) else {}
                tools.append(
                    {
                        "id": f"tool-{index}",
                        "tool": str(record.get("tool") or f"tool_{index + 1}"),
                        "category": str(record.get("category") or "tool"),
                        "success": record.get("success") if isinstance(record.get("success"), bool) else None,
                        "duration_ms": _safe_float(record.get("duration_ms")) or None,
                        "started_at": _iso(record.get("started_at")),
                        "completed_at": _iso(record.get("completed_at")),
                        "params": record.get("params") if isinstance(record.get("params"), dict) else {},
                        "output": _clip_text(record.get("output"), 4000),
                        "metadata": record.get("metadata") if isinstance(record.get("metadata"), dict) else {},
                        "summary": _clip_text(record.get("summary") or record.get("tool"), 180) or "",
                        "redactions": record.get("redactions") if isinstance(record.get("redactions"), dict) else None,
                    }
                )
        if not tools:
            tools = [
                _tool_trace_from_audit(item)
                for item in events
                if str(item.get("event_type") or "") == "task.tool_executed"
            ]
        timeline: list[dict[str, Any]] = [
            _timeline_item(
                item_id=f"task-created-{task_id}",
                item_type="task.created",
                title="Execution created",
                status="info",
                timestamp=_iso(task.get("created_at")),
                summary="Task registered in the queue.",
            )
        ]
        if _iso(task.get("started_at")):
            timeline.append(
                _timeline_item(
                    item_id=f"task-started-{task_id}",
                    item_type="task.started",
                    title="Execution started",
                    status="info",
                    timestamp=_iso(task.get("started_at")),
                    summary="Task entered execution.",
                )
            )
        for event in events:
            event_type = str(event.get("event_type") or "")
            details = _sanitize_details(event)
            if event_type == "task.tool_executed":
                tool_name = str(details.get("tool") or "tool")
                timeline.append(
                    _timeline_item(
                        item_id=f"event-{event.get('id')}",
                        item_type=event_type,
                        title=f"Tool {tool_name}",
                        status="error" if details.get("success") is False else "success",
                        timestamp=_iso(event.get("timestamp")),
                        summary=_clip_text(details.get("summary") or details.get("error") or tool_name, 180),
                        details=details,
                    )
                )
                continue
            if event_type in {"task.assigned", "task.retried", "task.failed", "task.completed", "task.dead_letter"}:
                timeline.append(
                    _timeline_item(
                        item_id=f"event-{event.get('id')}",
                        item_type=event_type,
                        title=event_type.replace(".", " ").title(),
                        status="error"
                        if event_type in {"task.failed", "task.dead_letter"}
                        else ("warning" if event_type == "task.retried" else "success"),
                        timestamp=_iso(event.get("timestamp")),
                        summary=_clip_text(details.get("error") or details.get("summary"), 180),
                        details=details,
                    )
                )
        response_text = _iso(assistant.get("response_text")) or _iso((resolved_query or {}).get("response_text"))
        response_source = (
            "trace"
            if _iso(assistant.get("response_text"))
            else ("queries" if _iso((resolved_query or {}).get("response_text")) else "missing")
        )
        trace_source = "trace" if envelope else ("legacy" if events else "missing")
        tools_source = (
            "trace"
            if envelope and isinstance((envelope or {}).get("tools"), list)
            else ("audit" if tools else "missing")
        )
        reasoning_summary = [
            str(item) for item in cast(list[Any], runtime.get("reasoning_summary") or []) if isinstance(item, str)
        ]
        if not reasoning_summary:
            reasoning_summary = [
                f"Status: {task.get('status') or 'queued'}",
                f"Tools used: {len(tools)}",
            ]
            if runtime.get("stop_reason"):
                reasoning_summary.append(f"Stop reason: {runtime.get('stop_reason')}")
        raw_artifacts = (envelope or {}).get("raw_artifacts")
        artifacts = _build_execution_artifacts(raw_artifacts, response_text, _safe_int(task.get("id")))
        return {
            "task_id": _safe_int(task.get("id")),
            "agent_id": _public_agent_id(scope),
            "bot_id": _public_agent_id(scope),
            "status": str(task.get("status") or "queued"),
            "query_text": _iso(request.get("query_text")) or _iso(task.get("query_text")),
            "response_text": response_text,
            "model": _iso(request.get("model")) or _iso(task.get("model")),
            "session_id": _iso(request.get("session_id")) or _iso(task.get("session_id")),
            "work_dir": _iso(request.get("work_dir")) or _iso(task.get("work_dir")),
            "user_id": _safe_int(task.get("user_id")),
            "chat_id": _safe_int(task.get("chat_id")),
            "created_at": _iso(task.get("created_at")) or "",
            "started_at": _iso(task.get("started_at")),
            "completed_at": _iso(task.get("completed_at")),
            "cost_usd": _safe_float(task.get("cost_usd")),
            "duration_ms": _safe_float(runtime.get("duration_ms")) or _duration_ms(task),
            "attempt": _safe_int(task.get("attempt")),
            "max_attempts": _safe_int(task.get("max_attempts")),
            "error_message": _iso(runtime.get("error_message")) or _iso(task.get("error_message")),
            "stop_reason": _iso(runtime.get("stop_reason")),
            "warnings": [str(item) for item in cast(list[Any], runtime.get("warnings") or []) if isinstance(item, str)],
            "has_rich_trace": envelope is not None,
            "trace_source": trace_source,
            "response_source": response_source,
            "tools_source": tools_source,
            "tool_count": len(tools),
            "timeline": timeline,
            "tools": tools,
            "reasoning_summary": reasoning_summary,
            "artifacts": artifacts,
            "redactions": runtime.get("redactions") if isinstance(runtime.get("redactions"), dict) else None,
        }

    def get_execution(self, agent_id: str, task_id: int) -> dict[str, Any] | None:
        scope = _normalize_scope(agent_id)
        task = _fetch_one(
            scope,
            """
            SELECT id, user_id, chat_id, status, query_text, provider, model, work_dir, attempt, max_attempts,
                   cost_usd, error_message, created_at, started_at, completed_at, session_id, provider_session_id
            FROM tasks
            WHERE agent_id = ? AND id = ?
            """,
            (scope, task_id),
        )
        if task is None:
            return None
        audit_events = self._audit_events_for_tasks(scope, [task_id]).get(task_id, [])
        return self._build_execution_detail(scope, task, audit_events=audit_events)

    def list_sessions(
        self,
        agent_id: str,
        *,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        scope = _normalize_scope(agent_id)
        session_rows = _fetch_all(
            scope,
            """
            SELECT session_id, name, user_id, created_at, last_used
            FROM sessions
            WHERE agent_id = ? AND session_id IS NOT NULL
            """,
            (scope,),
        )
        query_aggregates = _fetch_all(
            scope,
            """
            SELECT session_id,
                   COUNT(*) AS query_count,
                   COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
                   MAX(timestamp) AS last_query_at
            FROM query_history
            WHERE agent_id = ? AND session_id IS NOT NULL
            GROUP BY session_id
            """,
            (scope,),
        )
        latest_queries = _fetch_all(
            scope,
            """
            SELECT DISTINCT ON (session_id)
                   session_id, user_id, timestamp, query_text, response_text, model, error
            FROM query_history
            WHERE agent_id = ? AND session_id IS NOT NULL
            ORDER BY session_id, timestamp DESC, id DESC
            """,
            (scope,),
        )
        task_aggregates = _fetch_all(
            scope,
            """
            SELECT session_id,
                   COUNT(*) AS execution_count,
                   COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
                   SUM(CASE WHEN status IN ('running', 'retrying') THEN 1 ELSE 0 END) AS running_count,
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                   MAX(COALESCE(completed_at, started_at, created_at)) AS last_execution_at
            FROM tasks
            WHERE agent_id = ? AND session_id IS NOT NULL
            GROUP BY session_id
            """,
            (scope,),
        )
        latest_tasks = _fetch_all(
            scope,
            """
            SELECT DISTINCT ON (session_id)
                   id AS task_id,
                   session_id,
                   user_id,
                   status,
                   query_text,
                   COALESCE(completed_at, started_at, created_at) AS activity_at
            FROM tasks
            WHERE agent_id = ? AND session_id IS NOT NULL
            ORDER BY session_id, COALESCE(completed_at, started_at, created_at) DESC, id DESC
            """,
            (scope,),
        )
        latest_task_events = self._audit_events_for_tasks(
            scope,
            [_safe_int(row.get("task_id")) for row in latest_tasks if row.get("task_id") is not None],
        )
        session_by_id = {str(row.get("session_id") or ""): row for row in session_rows}
        query_by_session = {str(row.get("session_id") or ""): row for row in query_aggregates}
        latest_query_by_session = {str(row.get("session_id") or ""): row for row in latest_queries}
        task_by_session = {str(row.get("session_id") or ""): row for row in task_aggregates}
        latest_task_by_session = {str(row.get("session_id") or ""): row for row in latest_tasks}
        session_ids = sorted(
            {
                key
                for key in [
                    *session_by_id.keys(),
                    *query_by_session.keys(),
                    *latest_query_by_session.keys(),
                    *task_by_session.keys(),
                    *latest_task_by_session.keys(),
                ]
                if key
            },
            key=lambda key: max(
                _timestamp((latest_query_by_session.get(key) or {}).get("timestamp")),
                _timestamp((task_by_session.get(key) or {}).get("last_execution_at")),
            ),
            reverse=True,
        )
        items: list[dict[str, Any]] = []
        search_term = " ".join((search or "").lower().split())
        for session_id in session_ids:
            session_row = session_by_id.get(session_id, {})
            query_agg = query_by_session.get(session_id, {})
            latest_query = latest_query_by_session.get(session_id, {})
            task_agg = task_by_session.get(session_id, {})
            latest_task = latest_task_by_session.get(session_id, {})
            latest_task_trace = _latest_execution_trace_event(
                latest_task_events.get(_safe_int(latest_task.get("task_id")), [])
            )
            latest_task_query_preview = _clip_text(
                latest_task.get("query_text") or _trace_request_text(latest_task_trace),
                120,
            )
            latest_task_response_preview = _clip_text(_trace_response_text(latest_task_trace), 120)
            latest_message_preview = _clip_text(
                latest_query.get("response_text")
                or latest_query.get("query_text")
                or latest_task_response_preview
                or latest_task_query_preview,
                132,
            )
            if not latest_message_preview:
                continue
            item = {
                "agent_id": _public_agent_id(scope),
                "bot_id": _public_agent_id(scope),
                "session_id": session_id,
                "name": _iso(session_row.get("name")),
                "user_id": session_row.get("user_id") or latest_query.get("user_id") or latest_task.get("user_id"),
                "created_at": _iso(session_row.get("created_at"))
                or _iso(latest_query.get("timestamp"))
                or _iso(task_agg.get("last_execution_at")),
                "last_used": _iso(session_row.get("last_used"))
                or _iso(query_agg.get("last_query_at"))
                or _iso(task_agg.get("last_execution_at")),
                "last_activity_at": _iso(session_row.get("last_used"))
                or _iso(query_agg.get("last_query_at"))
                or _iso(task_agg.get("last_execution_at")),
                "query_count": _safe_int(query_agg.get("query_count")),
                "execution_count": _safe_int(task_agg.get("execution_count")),
                "total_cost_usd": _safe_float(task_agg.get("total_cost_usd"))
                or _safe_float(query_agg.get("total_cost_usd")),
                "running_count": _safe_int(task_agg.get("running_count")),
                "failed_count": _safe_int(task_agg.get("failed_count")),
                "latest_status": _iso(latest_task.get("status")),
                "latest_query_preview": _clip_text(latest_query.get("query_text"), 120) or latest_task_query_preview,
                "latest_response_preview": _clip_text(latest_query.get("response_text"), 120)
                or latest_task_response_preview,
                "latest_message_preview": latest_message_preview,
            }
            if search_term:
                haystack = " ".join(
                    part.lower()
                    for part in [
                        session_id,
                        str(item.get("name") or ""),
                        str(item.get("latest_query_preview") or ""),
                        str(item.get("latest_response_preview") or ""),
                        str(item.get("latest_message_preview") or ""),
                    ]
                    if part
                )
                if search_term not in haystack:
                    continue
            items.append(item)
        return items[offset : offset + limit]

    def get_session(
        self,
        agent_id: str,
        session_id: str,
        *,
        limit: int | None = None,
        before: str | None = None,
    ) -> dict[str, Any] | None:
        scope = _normalize_scope(agent_id)
        summary = next(
            (item for item in self.list_sessions(scope, limit=5000) if item["session_id"] == session_id), None
        )
        if summary is None:
            return None
        query_rows = self._query_rows_for_session(scope, session_id)
        task_rows = self._task_rows_for_session(scope, session_id)
        audit_by_task = self._audit_events_for_tasks(scope, [_safe_int(row.get("id")) for row in task_rows])
        task_rows_by_id = {_safe_int(row.get("id")): row for row in task_rows}
        execution_summaries = [
            _task_row_to_summary(
                scope,
                task,
                trace_event=_latest_execution_trace_event(audit_by_task.get(_safe_int(task.get("id")), [])),
                audit_events=audit_by_task.get(_safe_int(task.get("id")), []),
            )
            for task in task_rows
        ]
        execution_detail_cache: dict[int, dict[str, Any]] = {}

        def resolve_execution_detail(task_id: int) -> dict[str, Any] | None:
            if task_id in execution_detail_cache:
                return execution_detail_cache[task_id]
            task_row = task_rows_by_id.get(task_id)
            if task_row is None:
                return None
            detail = self._build_execution_detail(
                scope,
                task_row,
                audit_events=audit_by_task.get(task_id, []),
            )
            execution_detail_cache[task_id] = detail
            return detail

        transcript_entries: list[dict[str, Any]] = []
        unmatched_executions = list(execution_summaries)

        for row in query_rows:
            match_index = _find_execution_match(
                unmatched_executions,
                query_text=_iso(row.get("query_text")),
                timestamp=_iso(row.get("timestamp")),
            )
            linked_execution = unmatched_executions.pop(match_index) if match_index >= 0 else None
            linked_detail = (
                resolve_execution_detail(_safe_int(linked_execution.get("task_id")))
                if linked_execution is not None
                else None
            )
            query_text = _iso(row.get("query_text")) or _iso((linked_detail or {}).get("query_text"))
            response_text = _iso(row.get("response_text")) or _iso((linked_detail or {}).get("response_text"))
            user_timestamp = _iso(row.get("timestamp")) or _iso((linked_detail or {}).get("created_at"))
            assistant_timestamp = (
                _iso(row.get("timestamp"))
                or _iso((linked_detail or {}).get("completed_at"))
                or _iso((linked_detail or {}).get("started_at"))
                or user_timestamp
            )
            entry_messages: list[dict[str, Any]] = []
            if _clip_text(query_text, 10_000):
                entry_messages.append(
                    {
                        "id": f"query-{row.get('id')}-user",
                        "role": "user",
                        "text": str(query_text or ""),
                        "timestamp": user_timestamp,
                        "model": None,
                        "cost_usd": None,
                        "query_id": _safe_int(row.get("id")),
                        "session_id": session_id,
                        "error": False,
                        "linked_execution": linked_execution,
                    }
                )
            if _clip_text(response_text, 10_000):
                entry_messages.append(
                    {
                        "id": f"query-{row.get('id')}-assistant",
                        "role": "assistant",
                        "text": str(response_text or ""),
                        "timestamp": assistant_timestamp,
                        "model": _iso(row.get("model")) or _iso((linked_detail or {}).get("model")),
                        "cost_usd": _safe_float(row.get("cost_usd"))
                        or _safe_float((linked_detail or {}).get("cost_usd")),
                        "query_id": _safe_int(row.get("id")),
                        "session_id": session_id,
                        "error": bool(row.get("error")),
                        "linked_execution": linked_execution,
                    }
                )
            if entry_messages:
                transcript_entries.append(
                    {
                        "entry_id": f"query-{_safe_int(row.get('id'))}",
                        "activity_at": assistant_timestamp or user_timestamp,
                        "messages": entry_messages,
                    }
                )

        recoverable_execution_ids: set[int] = set()
        for execution in sorted(
            unmatched_executions,
            key=lambda item: _session_cursor_key(
                _task_activity_iso(item),
                f"execution-{_safe_int(item.get('task_id'))}",
            ),
        ):
            task_id = _safe_int(execution.get("task_id"))
            execution_detail = resolve_execution_detail(task_id)
            query_text = _iso((execution_detail or {}).get("query_text")) or _iso(execution.get("query_text"))
            response_text = _iso((execution_detail or {}).get("response_text"))
            user_timestamp = _iso((execution_detail or {}).get("created_at")) or _task_activity_iso(execution)
            assistant_timestamp = (
                _iso((execution_detail or {}).get("completed_at"))
                or _iso((execution_detail or {}).get("started_at"))
                or user_timestamp
            )
            execution_entry_messages: list[dict[str, Any]] = []
            synthetic_query_id = -task_id if task_id > 0 else -1
            if _clip_text(query_text, 10_000):
                execution_entry_messages.append(
                    {
                        "id": f"execution-{task_id}-user",
                        "role": "user",
                        "text": str(query_text or ""),
                        "timestamp": user_timestamp,
                        "model": None,
                        "cost_usd": None,
                        "query_id": synthetic_query_id,
                        "session_id": session_id,
                        "error": False,
                        "linked_execution": execution,
                    }
                )
            if _clip_text(response_text, 10_000):
                execution_entry_messages.append(
                    {
                        "id": f"execution-{task_id}-assistant",
                        "role": "assistant",
                        "text": str(response_text or ""),
                        "timestamp": assistant_timestamp,
                        "model": _iso((execution_detail or {}).get("model")) or _iso(execution.get("model")),
                        "cost_usd": _safe_float((execution_detail or {}).get("cost_usd"))
                        or _safe_float(execution.get("cost_usd")),
                        "query_id": synthetic_query_id,
                        "session_id": session_id,
                        "error": str(execution.get("status") or "") == "failed",
                        "linked_execution": execution,
                    }
                )
            if execution_entry_messages:
                recoverable_execution_ids.add(task_id)
                transcript_entries.append(
                    {
                        "entry_id": f"execution-{task_id}",
                        "activity_at": assistant_timestamp or user_timestamp,
                        "messages": execution_entry_messages,
                    }
                )

        transcript_entries.sort(
            key=lambda entry: _session_cursor_key(entry.get("activity_at"), str(entry.get("entry_id") or "")),
        )
        decoded_cursor = _decode_session_cursor(before)
        visible_entries = transcript_entries
        if decoded_cursor is not None:
            visible_entries = [
                entry
                for entry in transcript_entries
                if _session_cursor_key(entry.get("activity_at"), str(entry.get("entry_id") or "")) < decoded_cursor
            ]

        if limit is None:
            page_entries = visible_entries
        else:
            page_entries = visible_entries[-max(1, int(limit)) :]

        has_more = len(visible_entries) > len(page_entries)
        next_cursor = (
            _encode_session_cursor(page_entries[0].get("activity_at"), str(page_entries[0].get("entry_id") or ""))
            if has_more and page_entries
            else None
        )
        messages = [
            message for entry in page_entries for message in cast(list[dict[str, Any]], entry.get("messages") or [])
        ]
        return {
            "summary": summary,
            "messages": messages,
            "orphan_executions": [
                execution
                for execution in unmatched_executions
                if _safe_int(execution.get("task_id")) not in recoverable_execution_ids
            ],
            "page": {
                "limit": len(page_entries) if limit is None else max(1, int(limit)),
                "returned": len(page_entries),
                "next_cursor": next_cursor,
                "has_more": has_more,
            },
            "totals": {
                "messages": sum(
                    len(cast(list[dict[str, Any]], entry.get("messages") or [])) for entry in transcript_entries
                ),
                "executions": len(execution_summaries),
                "tools": sum(_safe_int(item.get("tool_count")) for item in execution_summaries),
                "cost_usd": sum(_safe_float(item.get("cost_usd")) for item in execution_summaries)
                or _safe_float(summary.get("total_cost_usd")),
            },
        }

    def list_dlq(self, agent_id: str, *, limit: int = 50, retry_eligible: bool | None = None) -> list[dict[str, Any]]:
        scope = _normalize_scope(agent_id)
        clauses = ["COALESCE(agent_id, ?) = ?"]
        params: list[Any] = [scope, scope]
        if retry_eligible is not None:
            clauses.append("retry_eligible = ?")
            params.append(1 if retry_eligible else 0)
        params.append(max(1, int(limit)))
        return _fetch_all(
            scope,
            f"""
            SELECT id, task_id, user_id, chat_id, agent_id, pod_name, query_text, model, error_message,
                   error_class, attempt_count, original_created_at, failed_at, retry_eligible, retried_at, metadata_json
            FROM dead_letter_queue
            WHERE {" AND ".join(clauses)}
            ORDER BY id DESC
            LIMIT ?
            """,
            tuple(params),
        )

    def get_costs(self, agent_id: str, *, days: int = 30) -> dict[str, Any]:
        scope = _normalize_scope(agent_id)
        daily_cutoff = (_now() - timedelta(days=max(1, int(days)))).isoformat()
        total = (
            _fetch_one(
                scope, "SELECT COALESCE(SUM(cost_usd), 0) AS value FROM query_history WHERE agent_id = ?", (scope,)
            )
            or {}
        )
        today = (
            _fetch_one(
                scope,
                "SELECT COALESCE(SUM(cost_usd), 0) AS value FROM query_history WHERE agent_id = ? AND timestamp >= ?",
                (scope, _now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()),
            )
            or {}
        )
        daily = _fetch_all(
            scope,
            """
            SELECT TO_CHAR(DATE_TRUNC('day', timestamp), 'YYYY-MM-DD') AS date,
                   COALESCE(SUM(cost_usd), 0) AS cost
            FROM query_history
            WHERE agent_id = ? AND timestamp >= ?
            GROUP BY 1
            ORDER BY 1 ASC
            """,
            (scope, daily_cutoff),
        )
        return {
            "total": _safe_float(total.get("value")),
            "today": _safe_float(today.get("value")),
            "daily": [{"date": str(row.get("date") or ""), "cost": _safe_float(row.get("cost"))} for row in daily],
        }

    def list_schedules(self, agent_id: str) -> list[dict[str, Any]]:
        scope = _normalize_scope(agent_id)
        rows = _fetch_all(
            scope,
            """
            SELECT id, user_id, chat_id, agent_id, job_type, trigger_type, schedule_expr, timezone,
                   payload_json, status, work_dir, provider_preference, model_preference,
                   next_run_at, last_run_at, last_success_at, last_failure_at, config_version,
                   verification_policy_json, notification_policy_json, dry_run_required,
                   created_at, updated_at
            FROM scheduled_jobs
            WHERE COALESCE(agent_id, ?) = ? AND status != 'archived'
            ORDER BY COALESCE(next_run_at, updated_at) ASC, id DESC
            """,
            (scope, scope),
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = _json_object(row.get("payload_json"))
            items.append(
                {
                    "id": _safe_int(row.get("id")),
                    "bot_id": str(row.get("agent_id") or "") or scope,
                    "user_id": _safe_int(row.get("user_id")),
                    "chat_id": _safe_int(row.get("chat_id")),
                    "job_type": str(row.get("job_type") or ""),
                    "trigger_type": str(row.get("trigger_type") or ""),
                    "schedule_expr": str(row.get("schedule_expr") or ""),
                    "cron_expression": str(row.get("schedule_expr") or ""),
                    "timezone": str(row.get("timezone") or ""),
                    "payload": payload,
                    "command": str(payload.get("query") or payload.get("text") or payload.get("command") or ""),
                    "description": str(payload.get("description") or ""),
                    "created_at": _iso(row.get("created_at")),
                    "updated_at": _iso(row.get("updated_at")),
                    "enabled": 1 if str(row.get("status") or "") == "active" else 0,
                    "status": str(row.get("status") or ""),
                    "work_dir": _iso(row.get("work_dir")),
                    "provider_preference": _iso(row.get("provider_preference")),
                    "model_preference": _iso(row.get("model_preference")),
                    "next_run_at": _iso(row.get("next_run_at")),
                    "last_run_at": _iso(row.get("last_run_at")),
                    "last_success_at": _iso(row.get("last_success_at")),
                    "last_failure_at": _iso(row.get("last_failure_at")),
                    "config_version": _safe_int(row.get("config_version")) or 1,
                    "verification_policy": _json_object(row.get("verification_policy_json")),
                    "notification_policy": _json_object(row.get("notification_policy_json")),
                    "dry_run_required": bool(row.get("dry_run_required")),
                }
            )
        return items

    def list_audit(
        self,
        agent_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = None,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        scope = _normalize_scope(agent_id)
        clauses = ["agent_id = ?"]
        params: list[Any] = [scope]
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        params.extend([max(1, int(limit)), max(0, int(offset))])
        rows = _fetch_all(
            scope,
            f"""
            SELECT id, timestamp, event_type, agent_id, pod_name, user_id, task_id,
                   trace_id, details_json, cost_usd, duration_ms
            FROM audit_events
            WHERE {" AND ".join(clauses)}
            ORDER BY timestamp DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            details = _json_object(row.get("details_json"))
            items.append(
                {
                    "id": _safe_int(row.get("id")),
                    "timestamp": _iso(row.get("timestamp")) or "",
                    "event_type": str(row.get("event_type") or ""),
                    "agent_id": _iso(row.get("agent_id")),
                    "pod_name": _iso(row.get("pod_name")),
                    "user_id": row.get("user_id"),
                    "task_id": row.get("task_id"),
                    "trace_id": _iso(row.get("trace_id")),
                    "details_json": json.dumps(details, ensure_ascii=False, sort_keys=True, default=str),
                    "details": details,
                    "cost_usd": _safe_float(row.get("cost_usd")) or None,
                    "duration_ms": _safe_float(row.get("duration_ms")) or None,
                }
            )
        return items

    def list_audit_types(self, agent_id: str) -> list[str]:
        scope = _normalize_scope(agent_id)
        rows = _fetch_all(
            scope,
            "SELECT DISTINCT event_type FROM audit_events WHERE agent_id = ? ORDER BY event_type ASC",
            (scope,),
        )
        return [str(row.get("event_type") or "") for row in rows if str(row.get("event_type") or "").strip()]

    def _load_memory_rows(
        self,
        agent_id: str,
        *,
        user_id: int | None = None,
        session_id: str | None = None,
        days: int = 30,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        scope = _normalize_scope(agent_id)
        clauses = ["COALESCE(agent_id, ?) = ?"]
        params: list[Any] = [scope, scope]
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if not include_inactive:
            clauses.append("is_active = 1")
        cutoff = (_now() - timedelta(days=max(1, int(days)))).isoformat()
        clauses.append("COALESCE(last_accessed, created_at) >= ?")
        params.append(cutoff)
        return _fetch_all(
            scope,
            f"""
            SELECT id, user_id, memory_type, content, source_query_id, session_id, agent_id, importance, access_count,
                   last_accessed, created_at, expires_at, is_active, metadata_json, supersedes_memory_id, memory_status
            FROM napkin_log
            WHERE {" AND ".join(clauses)}
            ORDER BY COALESCE(last_accessed, created_at) DESC, id DESC
            """,
            tuple(params),
        )

    def _memory_snapshot(
        self,
        agent_id: str,
        *,
        user_id: int | None = None,
        session_id: str | None = None,
        days: int = 30,
        include_inactive: bool = False,
        limit: int = _DEFAULT_MEMORY_LIMIT,
    ) -> dict[str, Any]:
        scope = _normalize_scope(agent_id)
        rows = self._load_memory_rows(
            scope,
            user_id=user_id,
            session_id=session_id,
            days=days,
            include_inactive=include_inactive,
        )
        type_counts = Counter(str(row.get("memory_type") or "fact") for row in rows)
        user_counts = Counter(_safe_int(row.get("user_id")) for row in rows)
        session_counts = Counter(
            str(row.get("session_id") or "") for row in rows if str(row.get("session_id") or "").strip()
        )
        ordered_rows = sorted(
            rows,
            key=lambda row: (
                _safe_float(row.get("importance")),
                math.log1p(max(_safe_int(row.get("access_count")), 0)),
                _timestamp(row.get("last_accessed")) or _timestamp(row.get("created_at")),
            ),
            reverse=True,
        )
        rendered = ordered_rows[: max(12, min(int(limit), _MAX_MEMORY_LIMIT))]
        latest_actions_by_memory: dict[int, str] = {}
        action_rows = _fetch_all(
            scope,
            """
            SELECT details_json->>'target_id' AS target_id, details_json->>'action' AS action
            FROM audit_events
            WHERE agent_id = ? AND event_type = ? AND details_json->>'target_type' = 'memory'
            ORDER BY timestamp DESC, id DESC
            LIMIT 5000
            """,
            (scope, _CURATION_EVENT_TYPE),
        )
        for row in action_rows:
            target_id = _safe_int(row.get("target_id"))
            if target_id and target_id not in latest_actions_by_memory:
                latest_actions_by_memory[target_id] = str(row.get("action") or "")
        nodes: list[dict[str, Any]] = []
        session_groups: dict[str, list[str]] = defaultdict(list)
        source_groups: dict[str, list[str]] = defaultdict(list)
        cluster_candidates: dict[str, list[str]] = defaultdict(list)
        for row in rendered:
            memory_id = _safe_int(row.get("id"))
            metadata = _json_object(row.get("metadata_json"))
            node_id = f"memory-{memory_id}"
            source_query_preview = _clip_text(metadata.get("source_query_preview"), 120)
            node = {
                "id": node_id,
                "kind": "memory",
                "agent_id": scope,
                "label": _clip_text(row.get("content"), 34) or "Memory",
                "title": _clip_text(row.get("content"), 88) or "Memory",
                "size": _memory_size(_safe_float(row.get("importance")), _safe_int(row.get("access_count"))),
                "cluster_id": None,
                "created_at": _iso(row.get("created_at")),
                "related_count": 0,
                "memory_id": memory_id,
                "memory_type": str(row.get("memory_type") or "fact"),
                "importance": _safe_float(row.get("importance")),
                "access_count": _safe_int(row.get("access_count")),
                "is_active": bool(row.get("is_active")),
                "session_id": _iso(row.get("session_id")),
                "user_id": _safe_int(row.get("user_id")),
                "last_accessed": _iso(row.get("last_accessed")),
                "expires_at": _iso(row.get("expires_at")),
                "source_query_id": row.get("source_query_id"),
                "source_query_text": None,
                "source_query_preview": source_query_preview,
                "content": str(row.get("content") or ""),
                "metadata": metadata,
                "memory_status": str(row.get("memory_status") or MemoryStatus.ACTIVE.value),
                "review_status": _memory_status_to_review_status(
                    str(row.get("memory_status") or MemoryStatus.ACTIVE.value),
                    expires_at=_iso(row.get("expires_at")),
                    is_active=bool(row.get("is_active")),
                    action=latest_actions_by_memory.get(memory_id),
                ),
                "review_reason": None,
                "duplicate_of_memory_id": row.get("supersedes_memory_id"),
                "semantic_strength": None,
            }
            nodes.append(node)
            if node["session_id"]:
                session_groups[str(node["session_id"])].append(node_id)
            source_key = f"query:{node['source_query_id']}" if node["source_query_id"] else source_query_preview
            if source_key:
                source_groups[str(source_key)].append(node_id)
            cluster_key = str(node.get("session_id") or source_key or "")
            if cluster_key:
                cluster_candidates[cluster_key].append(node_id)
        edges: list[dict[str, Any]] = []
        existing_pairs: set[tuple[str, str]] = set()

        def _append_group_edges(group_rows: dict[str, list[str]], edge_type: str, weight: float, label: str) -> None:
            index = 0
            for key, members in group_rows.items():
                if len(members) < 2:
                    continue
                for position in range(len(members) - 1):
                    left = members[position]
                    right = members[position + 1]
                    pair = cast(tuple[str, str], tuple(sorted((left, right))))
                    if pair in existing_pairs:
                        continue
                    existing_pairs.add(pair)
                    edges.append(
                        {
                            "id": f"{edge_type}-{index}-{left}-{right}",
                            "source": left,
                            "target": right,
                            "type": edge_type,
                            "weight": weight,
                            "label": label,
                            "similarity": None,
                            "session_id": key if edge_type == "session" else None,
                            "source_key": key if edge_type == "source" else None,
                        }
                    )
                    index += 1

        _append_group_edges(session_groups, "session", 0.56, "Shares the same operational session")
        _append_group_edges(source_groups, "source", 0.48, "Shares the same source context")
        node_by_id = {node["id"]: node for node in nodes}
        learning_nodes: list[dict[str, Any]] = []
        learning_edges: list[dict[str, Any]] = []
        cluster_events = _fetch_all(
            scope,
            """
            SELECT details_json->>'cluster_id' AS cluster_id, details_json->>'action' AS action
            FROM audit_events
            WHERE agent_id = ? AND event_type = ? AND details_json->>'target_type' = 'cluster'
            ORDER BY timestamp DESC, id DESC
            LIMIT 2000
            """,
            (scope, _CURATION_EVENT_TYPE),
        )
        latest_cluster_actions: dict[str, str] = {}
        for row in cluster_events:
            cluster_id = str(row.get("cluster_id") or "")
            if cluster_id and cluster_id not in latest_cluster_actions:
                latest_cluster_actions[cluster_id] = str(row.get("action") or "")
        for members in cluster_candidates.values():
            if len(members) < 2:
                continue
            member_ids = [_safe_int(member.removeprefix("memory-")) for member in members]
            cluster_id = _build_cluster_id(member_ids)
            type_counter = Counter(str(node_by_id.get(member, {}).get("memory_type") or "fact") for member in members)
            dominant_type = type_counter.most_common(1)[0][0] if type_counter else "fact"
            summary = " · ".join(node_by_id.get(member, {}).get("label") or "Memory" for member in members[:2])
            created_candidates = [
                created_at
                for created_at in (_iso(node_by_id.get(member, {}).get("created_at")) for member in members)
                if created_at
            ]
            learning_nodes.append(
                {
                    "id": cluster_id,
                    "kind": "learning",
                    "agent_id": scope,
                    "label": _clip_text(summary, 34) or "Cluster",
                    "title": _clip_text(summary, 88) or "Cluster",
                    "size": 22 + len(members) * 1.2,
                    "cluster_id": cluster_id,
                    "created_at": max(created_candidates, default=None),
                    "related_count": len(members),
                    "dominant_type": dominant_type,
                    "importance": round(
                        sum(_safe_float(node_by_id.get(member, {}).get("importance")) for member in members)
                        / len(members),
                        4,
                    ),
                    "summary": summary,
                    "member_ids": members,
                    "member_count": len(members),
                    "session_ids": sorted(
                        {
                            str(node_by_id.get(member, {}).get("session_id") or "")
                            for member in members
                            if node_by_id.get(member, {}).get("session_id")
                        }
                    ),
                    "semantic_strength": None,
                    "review_status": _memory_status_to_review_status(
                        MemoryStatus.ACTIVE.value,
                        expires_at=None,
                        is_active=True,
                        action=latest_cluster_actions.get(cluster_id),
                    ),
                    "review_reason": None,
                }
            )
            for index, member in enumerate(members):
                node_by_id[member]["cluster_id"] = cluster_id
                learning_edges.append(
                    {
                        "id": f"learning-{cluster_id}-{index}",
                        "source": cluster_id,
                        "target": member,
                        "type": "learning",
                        "weight": 0.7,
                        "label": "Belongs to the same learned cluster",
                        "similarity": None,
                        "session_id": None,
                        "source_key": None,
                    }
                )
        all_nodes = [*nodes, *learning_nodes]
        return {
            "rows": rows,
            "memory_nodes": nodes,
            "cluster_nodes": learning_nodes,
            "nodes": all_nodes,
            "edges": [*edges, *learning_edges],
            "stats": {
                "total_memories": len(rows),
                "rendered_memories": len(nodes),
                "hidden_memories": max(0, len(rows) - len(nodes)),
                "active_memories": sum(1 for row in rows if bool(row.get("is_active"))),
                "inactive_memories": sum(1 for row in rows if not bool(row.get("is_active"))),
                "learning_nodes": len(learning_nodes),
                "users": len([key for key in user_counts if key]),
                "sessions": len(session_groups),
                "semantic_edges": 0,
                "contextual_edges": len(edges) + len(learning_edges),
                "expiring_soon": sum(
                    1
                    for row in rows
                    if _iso(row.get("expires_at"))
                    and 0 < (_timestamp(row.get("expires_at")) - _now().timestamp()) <= 7 * 24 * 60 * 60
                ),
                "maintenance_operations": 0,
                "last_maintenance_at": None,
                "semantic_status": "fallback",
            },
            "filters": {
                "applied": {
                    "user_id": user_id,
                    "session_id": session_id,
                    "days": max(1, int(days)),
                    "include_inactive": bool(include_inactive),
                    "limit": max(12, min(int(limit), _MAX_MEMORY_LIMIT)),
                },
                "users": [
                    {"user_id": user_key, "label": f"User {user_key}", "count": count}
                    for user_key, count in sorted(user_counts.items())
                    if user_key
                ],
                "sessions": [
                    {"session_id": session_key, "label": session_key, "count": count, "last_used": None}
                    for session_key, count in sorted(session_counts.items())
                ],
                "types": [
                    {
                        "value": memory_type,
                        "label": memory_type.replace("_", " ").title(),
                        "count": count,
                        "color": _memory_type_color(memory_type),
                    }
                    for memory_type, count in sorted(type_counts.items())
                ],
            },
        }

    def get_memory_map(
        self,
        agent_id: str,
        *,
        user_id: int | None = None,
        session_id: str | None = None,
        days: int = 30,
        include_inactive: bool = False,
        limit: int = _DEFAULT_MEMORY_LIMIT,
    ) -> dict[str, Any]:
        scope = _normalize_scope(agent_id)
        snapshot = self._memory_snapshot(
            scope,
            user_id=user_id,
            session_id=session_id,
            days=days,
            include_inactive=include_inactive,
            limit=limit,
        )
        return {
            "stats": snapshot["stats"],
            "filters": snapshot["filters"],
            "nodes": snapshot["nodes"],
            "edges": snapshot["edges"],
            "semantic_status": "fallback",
        }

    def _list_memory_history(
        self, agent_id: str, *, memory_id: int | None = None, cluster_id: str | None = None
    ) -> list[dict[str, Any]]:
        scope = _normalize_scope(agent_id)
        if memory_id is not None:
            rows = _fetch_all(
                scope,
                """
                SELECT id, timestamp, details_json
                FROM audit_events
                WHERE agent_id = ? AND event_type = ? AND details_json->>'target_type' = 'memory'
                  AND details_json->>'target_id' = ?
                ORDER BY timestamp DESC, id DESC
                """,
                (scope, _CURATION_EVENT_TYPE, str(memory_id)),
            )
        else:
            rows = _fetch_all(
                scope,
                """
                SELECT id, timestamp, details_json
                FROM audit_events
                WHERE agent_id = ? AND event_type = ? AND details_json->>'target_type' = 'cluster'
                  AND details_json->>'cluster_id' = ?
                ORDER BY timestamp DESC, id DESC
                """,
                (scope, _CURATION_EVENT_TYPE, str(cluster_id or "")),
            )
        history: list[dict[str, Any]] = []
        for row in rows:
            details = _json_object(row.get("details_json"))
            history.append(
                {
                    "id": _safe_int(row.get("id")),
                    "target_type": str(details.get("target_type") or ""),
                    "target_id": str(details.get("target_id") or details.get("cluster_id") or ""),
                    "action": str(details.get("action") or ""),
                    "reason": _iso(details.get("reason")),
                    "duplicate_of_memory_id": details.get("duplicate_of_memory_id"),
                    "created_at": _iso(row.get("timestamp")) or "",
                }
            )
        return history

    def list_memory_curation(
        self,
        agent_id: str,
        *,
        search: str | None = None,
        status: str | None = None,
        memory_type: str | None = None,
        kind: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        scope = _normalize_scope(agent_id)
        snapshot = self._memory_snapshot(scope, days=3650, include_inactive=True, limit=1000)
        items = []
        for node in snapshot["memory_nodes"]:
            item = {
                "agent_id": scope,
                "memory_id": node["memory_id"],
                "memory_type": node["memory_type"],
                "title": node["title"],
                "content": node["content"],
                "source_query_id": node["source_query_id"],
                "source_query_preview": node["source_query_preview"],
                "session_id": node["session_id"],
                "user_id": node["user_id"],
                "importance": node["importance"],
                "access_count": node["access_count"],
                "created_at": node["created_at"],
                "last_accessed": node["last_accessed"],
                "expires_at": node["expires_at"],
                "review_status": node["review_status"],
                "review_reason": node["review_reason"],
                "duplicate_of_memory_id": node["duplicate_of_memory_id"],
                "cluster_id": node["cluster_id"],
                "semantic_strength": node["semantic_strength"],
                "metadata": node["metadata"],
                "is_active": node["is_active"],
            }
            items.append(item)
        clusters = []
        for node in snapshot["cluster_nodes"]:
            clusters.append(
                {
                    "cluster_id": node["cluster_id"],
                    "agent_id": scope,
                    "dominant_type": node["dominant_type"],
                    "summary": node["summary"],
                    "member_count": node["member_count"],
                    "member_ids": [int(item.removeprefix("memory-")) for item in node["member_ids"]],
                    "session_ids": node["session_ids"],
                    "semantic_strength": node["semantic_strength"],
                    "created_at": node["created_at"],
                    "review_status": node["review_status"],
                    "review_reason": node["review_reason"],
                }
            )
        filtered_items = items
        filtered_clusters = clusters
        search_term = " ".join((search or "").lower().split())
        if status:
            filtered_items = [item for item in filtered_items if str(item.get("review_status") or "") == status]
            filtered_clusters = [item for item in filtered_clusters if str(item.get("review_status") or "") == status]
        if memory_type:
            filtered_items = [item for item in filtered_items if str(item.get("memory_type") or "") == memory_type]
            filtered_clusters = [
                item for item in filtered_clusters if str(item.get("dominant_type") or "") == memory_type
            ]
        if search_term:
            filtered_items = [
                item
                for item in filtered_items
                if search_term
                in " ".join(
                    part.lower()
                    for part in [
                        str(item.get("title") or ""),
                        str(item.get("content") or ""),
                        str(item.get("source_query_preview") or ""),
                    ]
                )
            ]
            filtered_clusters = [
                item
                for item in filtered_clusters
                if search_term
                in " ".join([str(item.get("summary") or "").lower(), str(item.get("cluster_id") or "").lower()])
            ]
        if kind == "memory":
            filtered_clusters = []
        elif kind == "cluster":
            filtered_items = []
        items_page = filtered_items[offset : offset + limit]
        clusters_page = filtered_clusters[offset : offset + limit]
        overview = {
            "pending_memories": sum(1 for item in items if item["review_status"] == "pending"),
            "pending_clusters": sum(1 for item in clusters if item["review_status"] == "pending"),
            "expiring_soon": snapshot["stats"]["expiring_soon"],
            "discarded_last_7d": len(
                [
                    item
                    for item in self.list_audit(scope, limit=1000, event_type=_CURATION_EVENT_TYPE)
                    if item["details"].get("action") == "discard"
                    and _timestamp(item.get("timestamp")) >= (_now() - timedelta(days=7)).timestamp()
                ]
            ),
            "merged_last_7d": len(
                [
                    item
                    for item in self.list_audit(scope, limit=1000, event_type=_CURATION_EVENT_TYPE)
                    if item["details"].get("action") == "merge"
                    and _timestamp(item.get("timestamp")) >= (_now() - timedelta(days=7)).timestamp()
                ]
            ),
            "approved_last_7d": len(
                [
                    item
                    for item in self.list_audit(scope, limit=1000, event_type=_CURATION_EVENT_TYPE)
                    if item["details"].get("action") in {"approve", "restore"}
                    and _timestamp(item.get("timestamp")) >= (_now() - timedelta(days=7)).timestamp()
                ]
            ),
        }
        available_filters = {
            "statuses": [
                {"value": value, "label": value.title(), "count": count}
                for value, count in sorted(Counter(item["review_status"] for item in items).items())
            ],
            "types": [
                {"value": value, "label": value.title(), "count": count, "color": _memory_type_color(value)}
                for value, count in sorted(Counter(item["memory_type"] for item in items).items())
            ],
        }
        return {
            "overview": overview,
            "items": items_page,
            "clusters": clusters_page,
            "available_filters": available_filters,
        }

    def get_memory_curation_detail(self, agent_id: str, memory_id: int) -> dict[str, Any] | None:
        scope = _normalize_scope(agent_id)
        snapshot = self.list_memory_curation(scope, kind="memory", limit=5000)
        items = cast(list[dict[str, Any]], snapshot.get("items") or [])
        item = next((candidate for candidate in items if _safe_int(candidate.get("memory_id")) == memory_id), None)
        if item is None:
            return None
        all_items = cast(
            list[dict[str, Any]], self.list_memory_curation(scope, kind="memory", limit=5000).get("items") or []
        )
        cluster = None
        if item.get("cluster_id"):
            all_clusters = cast(
                list[dict[str, Any]], self.list_memory_curation(scope, kind="cluster", limit=5000).get("clusters") or []
            )
            cluster = next(
                (
                    candidate
                    for candidate in all_clusters
                    if str(candidate.get("cluster_id") or "") == str(item.get("cluster_id") or "")
                ),
                None,
            )
        related = [
            candidate
            for candidate in all_items
            if _safe_int(candidate.get("memory_id")) != memory_id
            and (
                (item.get("cluster_id") and candidate.get("cluster_id") == item.get("cluster_id"))
                or (item.get("session_id") and candidate.get("session_id") == item.get("session_id"))
                or (item.get("source_query_id") and candidate.get("source_query_id") == item.get("source_query_id"))
            )
        ][:6]
        similar = [
            candidate
            for candidate in sorted(
                [
                    (
                        _word_overlap_score(str(candidate.get("content") or ""), str(item.get("content") or "")),
                        candidate,
                    )
                    for candidate in all_items
                    if _safe_int(candidate.get("memory_id")) != memory_id
                ],
                key=lambda entry: entry[0],
                reverse=True,
            )
            if candidate[0] >= 0.32
        ][:6]
        source_query_text = None
        if item.get("source_query_id"):
            row = _fetch_one(
                scope,
                "SELECT query_text FROM query_history WHERE agent_id = ? AND id = ?",
                (scope, _safe_int(item.get("source_query_id"))),
            )
            source_query_text = _iso((row or {}).get("query_text"))
        return {
            "item": item,
            "source_query_text": source_query_text or item.get("source_query_preview"),
            "session_name": item.get("session_id"),
            "related_memories": related,
            "similar_memories": [entry[1] for entry in similar],
            "cluster": cluster,
            "history": self._list_memory_history(scope, memory_id=memory_id),
        }

    def get_memory_cluster_detail(self, agent_id: str, cluster_id: str) -> dict[str, Any] | None:
        scope = _normalize_scope(agent_id)
        payload = self.list_memory_curation(scope, kind="cluster", limit=5000)
        clusters = cast(list[dict[str, Any]], payload.get("clusters") or [])
        cluster = next(
            (candidate for candidate in clusters if str(candidate.get("cluster_id") or "") == cluster_id), None
        )
        if cluster is None:
            return None
        items = cast(
            list[dict[str, Any]], self.list_memory_curation(scope, kind="memory", limit=5000).get("items") or []
        )
        members = [item for item in items if str(item.get("cluster_id") or "") == cluster_id]
        overlap_counter = Counter(
            str(item.get("session_id") or "") for item in members if str(item.get("session_id") or "").strip()
        )
        overlaps = [{"session_id": session_key, "count": count} for session_key, count in overlap_counter.most_common()]
        return {
            "cluster": cluster,
            "members": members,
            "overlaps": overlaps,
            "history": self._list_memory_history(scope, cluster_id=cluster_id),
        }

    def apply_memory_curation_action(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        scope = _normalize_scope(agent_id)
        target_type = str(payload.get("target_type") or "").strip().lower()
        action = str(payload.get("action") or "").strip().lower()
        target_ids = [
            str(item).strip() for item in cast(list[Any], payload.get("target_ids") or []) if str(item).strip()
        ]
        if target_type not in _ALLOWED_CURATION_TARGETS:
            raise ValueError("invalid target_type")
        if action not in _ALLOWED_CURATION_ACTIONS:
            raise ValueError("invalid action")
        if not target_ids:
            raise ValueError("target_ids must not be empty")
        reason = _iso(payload.get("reason"))
        duplicate_of_memory_id = payload.get("duplicate_of_memory_id")
        if duplicate_of_memory_id is not None:
            duplicate_of_memory_id = _safe_int(duplicate_of_memory_id)
        memory_ids: list[int] = []
        cluster_id: str | None = None
        if target_type == "cluster":
            cluster_id = target_ids[0]
            detail = self.get_memory_cluster_detail(scope, cluster_id)
            if detail is None:
                raise KeyError(cluster_id)
            memory_ids = [
                _safe_int(item.get("memory_id")) for item in cast(list[dict[str, Any]], detail.get("members") or [])
            ]
        else:
            memory_ids = [_safe_int(item) for item in target_ids]
        memory_ids = [item for item in memory_ids if item > 0]
        if not memory_ids:
            raise ValueError("no valid target_ids")
        if action == "merge" and not duplicate_of_memory_id:
            duplicate_of_memory_id = memory_ids[0]
        current_rows = _fetch_all(
            scope,
            f"""
            SELECT id, COALESCE(memory_status, ?) AS memory_status, is_active
            FROM napkin_log
            WHERE id IN ({", ".join("?" for _ in memory_ids)})
            """,
            (MemoryStatus.ACTIVE.value, *memory_ids),
        )
        current_by_id = {_safe_int(row.get("id")): row for row in current_rows}
        if action in {"approve", "restore"}:
            next_status = MemoryStatus.ACTIVE.value
            is_active = 1
            expires_at = None
            supersedes_id = None
        elif action == "merge":
            next_status = MemoryStatus.SUPERSEDED.value
            is_active = 0
            expires_at = None
            supersedes_id = duplicate_of_memory_id
        elif action == "discard":
            next_status = MemoryStatus.REJECTED.value
            is_active = 0
            expires_at = None
            supersedes_id = None
        elif action == "expire":
            next_status = MemoryStatus.STALE.value
            is_active = 0
            expires_at = _now_iso()
            supersedes_id = None
        else:
            next_status = MemoryStatus.INVALIDATED.value
            is_active = 0
            expires_at = None
            supersedes_id = None
        updated = 0
        for memory_id in memory_ids:
            updated += _execute(
                scope,
                """
                UPDATE napkin_log
                SET memory_status = ?, supersedes_memory_id = ?,
                    is_active = ?, expires_at = ?
                WHERE id = ? AND COALESCE(agent_id, ?) = ?
                """,
                (next_status, supersedes_id, is_active, expires_at, memory_id, scope, scope),
            )
            previous_status = str(
                (current_by_id.get(memory_id) or {}).get("memory_status") or MemoryStatus.ACTIVE.value
            )
            _execute(
                scope,
                """
                INSERT INTO audit_events (
                    agent_id, timestamp, event_type, pod_name, user_id, task_id,
                    trace_id, details_json, cost_usd, duration_ms
                )
                VALUES (?, ?, ?, '', NULL, NULL, '', ?::jsonb, NULL, NULL)
                """,
                (
                    scope,
                    _now_iso(),
                    _CURATION_EVENT_TYPE,
                    json.dumps(
                        {
                            "target_type": "memory",
                            "target_id": str(memory_id),
                            "memory_id": memory_id,
                            "cluster_id": cluster_id,
                            "action": action,
                            "reason": reason,
                            "duplicate_of_memory_id": supersedes_id,
                            "previous_status": previous_status,
                            "next_status": next_status,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
            )
        if cluster_id:
            _execute(
                scope,
                """
                INSERT INTO audit_events (
                    agent_id, timestamp, event_type, pod_name, user_id, task_id,
                    trace_id, details_json, cost_usd, duration_ms
                )
                VALUES (?, ?, ?, '', NULL, NULL, '', ?::jsonb, NULL, NULL)
                """,
                (
                    scope,
                    _now_iso(),
                    _CURATION_EVENT_TYPE,
                    json.dumps(
                        {
                            "target_type": "cluster",
                            "target_id": cluster_id,
                            "cluster_id": cluster_id,
                            "action": action,
                            "reason": reason,
                            "duplicate_of_memory_id": supersedes_id,
                            "member_ids": memory_ids,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
            )
        return {
            "updated": updated,
            "target_type": target_type,
            "action": action,
            "target_ids": target_ids,
            "duplicate_of_memory_id": supersedes_id,
        }


_STORE = DashboardStore()


def get_dashboard_store() -> DashboardStore:
    return _STORE
