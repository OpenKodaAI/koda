"""Memory-engine client selection for the Rust migration seam."""

from __future__ import annotations

import json
from typing import Any, Protocol, cast

from koda import config
from koda.internal_rpc.common import (
    EngineSelection,
    ensure_generated_proto_path,
    normalize_internal_service_probe,
    resolve_grpc_target,
    select_engine_backend,
)
from koda.internal_rpc.metadata import build_rpc_metadata


def _coerce_score(raw: object) -> float:
    if isinstance(raw, bool):
        return float(int(raw))
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return 0.0
    return 0.0


def _message_string(raw: object) -> str:
    return "" if raw is None else str(raw)


def _message_int(raw: object) -> int:
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return 0
    return 0


def _message_bool(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _object_list(raw: object) -> list[object]:
    return list(raw) if isinstance(raw, list) else []


def _dict_list(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    return [cast(dict[str, object], item) for item in raw if isinstance(item, dict)]


def _dynamic_value_to_python(raw: object) -> object:
    if raw is None:
        return None
    which_oneof = getattr(raw, "WhichOneof", None)
    kind = which_oneof("kind") if callable(which_oneof) else None
    if kind == "null_value":
        return None
    if kind == "bool_value":
        return _message_bool(getattr(raw, "bool_value", False))
    if kind == "number_value":
        return _coerce_score(getattr(raw, "number_value", 0.0))
    if kind == "string_value":
        return _message_string(getattr(raw, "string_value", ""))
    if kind == "struct_value":
        return _dynamic_struct_to_dict(getattr(raw, "struct_value", None))
    if kind == "list_value":
        return [_dynamic_value_to_python(item) for item in list(getattr(getattr(raw, "list_value", None), "items", []))]

    if hasattr(raw, "bool_value"):
        return _message_bool(getattr(raw, "bool_value", False))
    if hasattr(raw, "number_value"):
        return _coerce_score(getattr(raw, "number_value", 0.0))
    if hasattr(raw, "string_value"):
        return _message_string(getattr(raw, "string_value", ""))
    if hasattr(raw, "struct_value"):
        return _dynamic_struct_to_dict(getattr(raw, "struct_value", None))
    if hasattr(raw, "list_value"):
        return [_dynamic_value_to_python(item) for item in list(getattr(getattr(raw, "list_value", None), "items", []))]
    return None


def _dynamic_struct_to_dict(raw: object) -> dict[str, object]:
    if raw is None:
        return {}
    return {
        _message_string(getattr(field, "key", "")): _dynamic_value_to_python(getattr(field, "value", None))
        for field in list(getattr(raw, "fields", []) or [])
        if _message_string(getattr(field, "key", "")).strip()
    }


def _memory_record_row_to_dict(entry: object) -> dict[str, object]:
    return {
        "id": _message_int(getattr(entry, "id", 0)),
        "content_hash": _message_string(getattr(entry, "content_hash", "")),
        "conflict_key": _message_string(getattr(entry, "conflict_key", "")),
        "quality_score": _coerce_score(getattr(entry, "quality_score", 0.0)),
        "importance": _coerce_score(getattr(entry, "importance", 0.0)),
        "created_at": _message_string(getattr(entry, "created_at", "")) or None,
        "agent_id": _message_string(getattr(entry, "agent_id", "")) or None,
        "memory_type": _message_string(getattr(entry, "memory_type", "")),
        "subject": _message_string(getattr(entry, "subject", "")),
        "content": _message_string(getattr(entry, "content", "")),
        "session_id": _message_string(getattr(entry, "session_id", "")) or None,
        "user_id": _message_int(getattr(entry, "user_id", 0)),
        "origin_kind": _message_string(getattr(entry, "origin_kind", "")),
        "source_query_id": _message_int(getattr(entry, "source_query_id", 0)) or None,
        "source_task_id": _message_int(getattr(entry, "source_task_id", 0)) or None,
        "source_episode_id": _message_int(getattr(entry, "source_episode_id", 0)) or None,
        "project_key": _message_string(getattr(entry, "project_key", "")),
        "environment": _message_string(getattr(entry, "environment", "")),
        "team": _message_string(getattr(entry, "team", "")),
        "extraction_confidence": _coerce_score(getattr(entry, "extraction_confidence", 0.0)),
        "embedding_status": _message_string(getattr(entry, "embedding_status", "")),
        "claim_kind": _message_string(getattr(entry, "claim_kind", "")),
        "decision_source": _message_string(getattr(entry, "decision_source", "")),
        "evidence_refs": _dynamic_value_to_python(getattr(entry, "evidence_refs", None)) or [],
        "applicability_scope": _dynamic_value_to_python(getattr(entry, "applicability_scope", None)) or {},
        "valid_until": _message_string(getattr(entry, "valid_until", "")) or None,
        "supersedes_memory_id": _message_int(getattr(entry, "supersedes_memory_id", 0)) or None,
        "memory_status": _message_string(getattr(entry, "memory_status", "")),
        "retention_reason": _message_string(getattr(entry, "retention_reason", "")),
        "embedding_attempts": _message_int(getattr(entry, "embedding_attempts", 0)),
        "embedding_last_error": _message_string(getattr(entry, "embedding_last_error", "")),
        "embedding_retry_at": _message_string(getattr(entry, "embedding_retry_at", "")) or None,
        "access_count": _message_int(getattr(entry, "access_count", 0)),
        "last_accessed": _message_string(getattr(entry, "last_accessed", "")) or None,
        "last_recalled_at": _message_string(getattr(entry, "last_recalled_at", "")) or None,
        "expires_at": _message_string(getattr(entry, "expires_at", "")) or None,
        "is_active": _message_bool(getattr(entry, "is_active", False)),
        "metadata": _dynamic_struct_to_dict(getattr(entry, "metadata", None)),
        "vector_ref_id": _message_string(getattr(entry, "vector_ref_id", "")) or None,
        "source_query_preview": _message_string(getattr(entry, "source_query_preview", "")) or None,
    }


def _counter_entry_to_pair(entry: object) -> tuple[str, int] | None:
    key = _message_string(getattr(entry, "key", ""))
    if not key:
        return None
    return key, _message_int(getattr(entry, "count", 0))


def _cluster_summary_to_dict(entry: object) -> dict[str, object]:
    return {
        "cluster_id": _message_string(getattr(entry, "cluster_id", "")),
        "agent_id": _message_string(getattr(entry, "agent_id", "")) or None,
        "summary": _message_string(getattr(entry, "summary", "")),
        "memory_count": _message_int(getattr(entry, "memory_count", 0)),
        "latest_created_at": _message_string(getattr(entry, "latest_created_at", "")) or None,
        "review_status": _message_string(getattr(entry, "review_status", "")) or None,
        "dominant_type": _message_string(getattr(entry, "dominant_type", "")) or None,
        "member_ids": [int(item) for item in list(getattr(entry, "member_ids", []) or [])],
    }


def _curation_item_to_dict(entry: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent_id": _message_string(getattr(entry, "agent_id", "")),
        "id": _message_int(getattr(entry, "id", 0)),
        "memory_id": _message_int(getattr(entry, "memory_id", 0)),
        "memory_type": _message_string(getattr(entry, "memory_type", "")),
        "title": _message_string(getattr(entry, "title", "")),
        "content": _message_string(getattr(entry, "content", "")),
        "source_query_id": _message_int(getattr(entry, "source_query_id", 0)) or None,
        "source_query_preview": _message_string(getattr(entry, "source_query_preview", "")) or None,
        "session_id": _message_string(getattr(entry, "session_id", "")) or None,
        "user_id": _message_int(getattr(entry, "user_id", 0)),
        "importance": _coerce_score(getattr(entry, "importance", 0.0)),
        "access_count": _message_int(getattr(entry, "access_count", 0)),
        "created_at": _message_string(getattr(entry, "created_at", "")) or None,
        "last_accessed": _message_string(getattr(entry, "last_accessed", "")) or None,
        "expires_at": _message_string(getattr(entry, "expires_at", "")) or None,
        "review_status": _message_string(getattr(entry, "review_status", "")),
        "review_reason": _message_string(getattr(entry, "review_reason", "")) or None,
        "duplicate_of_memory_id": _message_int(getattr(entry, "duplicate_of_memory_id", 0)) or None,
        "cluster_id": _message_string(getattr(entry, "cluster_id", "")) or None,
        "semantic_strength": _coerce_score(getattr(entry, "semantic_strength", 0.0)) or None,
        "memory_status": _message_string(getattr(entry, "memory_status", "")),
        "is_active": _message_bool(getattr(entry, "is_active", False)),
    }
    raw_metadata = _message_string(getattr(entry, "metadata_json", ""))
    if raw_metadata.strip():
        try:
            payload["metadata"] = json.loads(raw_metadata)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload["metadata"] = {}
    else:
        payload["metadata"] = {}
    return payload


def _recall_log_item_to_dict(entry: object) -> dict[str, object]:
    return {
        "id": _message_int(getattr(entry, "id", 0)),
        "user_id": _message_int(getattr(entry, "user_id", 0)),
        "task_id": _message_int(getattr(entry, "task_id", 0)),
        "query_preview": _message_string(getattr(entry, "query_preview", "")),
        "trust_score": _coerce_score(getattr(entry, "trust_score", 0.0)),
        "total_considered": _message_int(getattr(entry, "total_considered", 0)),
        "total_selected": _message_int(getattr(entry, "total_selected", 0)),
        "total_discarded": _message_int(getattr(entry, "total_discarded", 0)),
        "conflict_group_count": _message_int(getattr(entry, "conflict_group_count", 0)),
        "selected_layers_csv": _message_string(getattr(entry, "selected_layers_csv", "")),
        "retrieval_sources_csv": _message_string(getattr(entry, "retrieval_sources_csv", "")),
        "created_at": _message_string(getattr(entry, "created_at", "")) or None,
    }


def _maintenance_log_item_to_dict(entry: object) -> dict[str, object]:
    return {
        "operation": _message_string(getattr(entry, "operation", "")),
        "memories_affected": _message_int(getattr(entry, "memories_affected", 0)),
        "details": _message_string(getattr(entry, "details", "")),
        "executed_at": _message_string(getattr(entry, "executed_at", "")) or None,
    }


def _audit_log_item_to_dict(entry: object) -> dict[str, object]:
    return {
        "id": _message_int(getattr(entry, "id", 0)),
        "task_id": _message_int(getattr(entry, "task_id", 0)),
        "query_preview": _message_string(getattr(entry, "query_preview", "")),
        "trust_score": _coerce_score(getattr(entry, "trust_score", 0.0)),
        "considered_json": _message_string(getattr(entry, "considered_json", "")),
        "selected_json": _message_string(getattr(entry, "selected_json", "")),
        "discarded_json": _message_string(getattr(entry, "discarded_json", "")),
        "conflicts_json": _message_string(getattr(entry, "conflicts_json", "")),
        "explanations_json": _message_string(getattr(entry, "explanations_json", "")),
        "created_at": _message_string(getattr(entry, "created_at", "")) or None,
        "timestamp": _message_string(getattr(entry, "timestamp", "")) or None,
        "details_json": _message_string(getattr(entry, "details_json", "")),
    }


def _action_operation_to_dict(entry: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "op": _message_string(getattr(entry, "op", "")),
        "memory_id": _message_int(getattr(entry, "memory_id", 0)),
        "memory_ids": [int(item) for item in list(getattr(entry, "memory_ids", []) or [])],
        "review_status": _message_string(getattr(entry, "review_status", "")),
        "memory_status": _message_string(getattr(entry, "memory_status", "")),
        "is_active": _message_bool(getattr(entry, "is_active", False)),
        "reason": _message_string(getattr(entry, "reason", "")),
        "duplicate_of_memory_id": _message_int(getattr(entry, "duplicate_of_memory_id", 0)),
        "expires_now": _message_bool(getattr(entry, "expires_now", False)),
    }
    return payload


def _row_message_kwargs(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": _message_int(row.get("id", 0)),
        "content_hash": _message_string(row.get("content_hash", "")),
        "conflict_key": _message_string(row.get("conflict_key", "")),
        "quality_score": _coerce_score(row.get("quality_score")),
        "importance": _coerce_score(row.get("importance")),
        "created_at": _message_string(row.get("created_at", "")),
        "agent_id": _message_string(row.get("agent_id", "")),
        "memory_type": _message_string(row.get("memory_type", "")),
        "subject": _message_string(row.get("subject", "")),
        "content": _message_string(row.get("content", "")),
        "session_id": _message_string(row.get("session_id", "")),
        "user_id": _message_int(row.get("user_id", 0)),
        "origin_kind": _message_string(row.get("origin_kind", "")),
        "source_query_id": _message_int(row.get("source_query_id", 0)),
        "source_task_id": _message_int(row.get("source_task_id", 0)),
        "source_episode_id": _message_int(row.get("source_episode_id", 0)),
        "project_key": _message_string(row.get("project_key", "")),
        "environment": _message_string(row.get("environment", "")),
        "team": _message_string(row.get("team", "")),
        "extraction_confidence": _coerce_score(row.get("extraction_confidence")),
        "embedding_status": _message_string(row.get("embedding_status", "")),
        "claim_kind": _message_string(row.get("claim_kind", "")),
        "decision_source": _message_string(row.get("decision_source", "")),
        "evidence_refs_json": json.dumps(row.get("evidence_refs_json"), ensure_ascii=False)
        if isinstance(row.get("evidence_refs_json"), (list, dict))
        else _message_string(row.get("evidence_refs_json", "")),
        "applicability_scope_json": json.dumps(row.get("applicability_scope_json"), ensure_ascii=False)
        if isinstance(row.get("applicability_scope_json"), (list, dict))
        else _message_string(row.get("applicability_scope_json", "")),
        "valid_until": _message_string(row.get("valid_until", "")),
        "supersedes_memory_id": _message_int(row.get("supersedes_memory_id", 0)),
        "memory_status": _message_string(row.get("memory_status", "")),
        "retention_reason": _message_string(row.get("retention_reason", "")),
        "embedding_attempts": _message_int(row.get("embedding_attempts", 0)),
        "embedding_last_error": _message_string(row.get("embedding_last_error", "")),
        "embedding_retry_at": _message_string(row.get("embedding_retry_at", "")),
        "access_count": _message_int(row.get("access_count", 0)),
        "last_accessed": _message_string(row.get("last_accessed", "")),
        "last_recalled_at": _message_string(row.get("last_recalled_at", "")),
        "expires_at": _message_string(row.get("expires_at", "")),
        "is_active": _message_bool(row.get("is_active", False)),
        "metadata_json": json.dumps(row.get("metadata"), ensure_ascii=False, sort_keys=True)
        if isinstance(row.get("metadata"), dict)
        else _message_string(row.get("metadata_json", "")),
        "vector_ref_id": _message_string(row.get("vector_ref_id", "")),
        "source_query_preview": _message_string(row.get("source_query_preview", "")),
    }


def _cluster_summary_message_kwargs(item: dict[str, object]) -> dict[str, object]:
    member_ids = [_message_int(value) for value in _object_list(item.get("member_ids")) if _message_int(value) > 0]
    return {
        "cluster_id": _message_string(item.get("cluster_id", "")),
        "agent_id": _message_string(item.get("agent_id", "")),
        "summary": _message_string(item.get("summary", "")),
        "memory_count": _message_int(item.get("memory_count", 0)),
        "latest_created_at": _message_string(item.get("latest_created_at", "")),
        "review_status": _message_string(item.get("review_status", "")),
        "dominant_type": _message_string(item.get("dominant_type", "")),
        "member_ids": member_ids,
    }


def _counter_entry_message_kwargs(item: dict[str, object]) -> dict[str, object]:
    return {
        "key": _message_string(item.get("key", "")),
        "count": _message_int(item.get("count", 0)),
        "updated_at": _message_string(item.get("updated_at", "")),
    }


def _dashboard_filter_message_kwargs(filters: dict[str, object]) -> dict[str, object]:
    has_is_active = "is_active" in filters and filters.get("is_active") is not None
    return {
        "user_id": _message_int(filters.get("user_id", 0)),
        "session_id": _message_string(filters.get("session_id", "")),
        "days": _message_int(filters.get("days", 0)),
        "include_inactive": _message_bool(filters.get("include_inactive", False)),
        "limit": _message_int(filters.get("limit", 0)),
        "offset": _message_int(filters.get("offset", 0)),
        "review_status": _message_string(filters.get("review_status", "")),
        "memory_status": _message_string(filters.get("memory_status", "")),
        "memory_type": _message_string(filters.get("memory_type", "")),
        "query": _message_string(filters.get("query", "")),
        "cluster_id": _message_string(filters.get("cluster_id", "")),
        "origin_kind": _message_string(filters.get("origin_kind", "")),
        "kind": _message_string(filters.get("kind", "")),
        "has_is_active": has_is_active,
        "is_active": _message_bool(filters.get("is_active", False)),
    }


def _dashboard_filter_to_dict(entry: object) -> dict[str, object]:
    payload: dict[str, object] = {}
    user_id = _message_int(getattr(entry, "user_id", 0))
    if user_id:
        payload["user_id"] = user_id
    session_id = _message_string(getattr(entry, "session_id", ""))
    if session_id:
        payload["session_id"] = session_id
    days = _message_int(getattr(entry, "days", 0))
    if days:
        payload["days"] = days
    if _message_bool(getattr(entry, "include_inactive", False)):
        payload["include_inactive"] = True
    limit = _message_int(getattr(entry, "limit", 0))
    if limit:
        payload["limit"] = limit
    offset = _message_int(getattr(entry, "offset", 0))
    if offset:
        payload["offset"] = offset
    for key in ("review_status", "memory_status", "memory_type", "query", "cluster_id", "origin_kind", "kind"):
        value = _message_string(getattr(entry, key, ""))
        if value:
            payload[key] = value
    if _message_bool(getattr(entry, "has_is_active", False)):
        payload["is_active"] = _message_bool(getattr(entry, "is_active", False))
    return payload


def _filter_option_to_dict(entry: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "value": _message_string(getattr(entry, "value", "")),
        "label": _message_string(getattr(entry, "label", "")),
        "count": _message_int(getattr(entry, "count", 0)),
    }
    color = _message_string(getattr(entry, "color", ""))
    if color:
        payload["color"] = color
    return payload


def _user_filter_option_to_dict(entry: object) -> dict[str, object]:
    return {
        "user_id": _message_int(getattr(entry, "user_id", 0)),
        "label": _message_string(getattr(entry, "label", "")),
        "count": _message_int(getattr(entry, "count", 0)),
    }


def _session_filter_option_to_dict(entry: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "session_id": _message_string(getattr(entry, "session_id", "")),
        "label": _message_string(getattr(entry, "label", "")),
        "count": _message_int(getattr(entry, "count", 0)),
    }
    last_used = _message_string(getattr(entry, "last_used", ""))
    if last_used:
        payload["last_used"] = last_used
    return payload


def _graph_node_to_dict(entry: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": _message_string(getattr(entry, "id", "")),
        "kind": _message_string(getattr(entry, "kind", "")),
        "agent_id": _message_string(getattr(entry, "agent_id", "")) or None,
        "label": _message_string(getattr(entry, "label", "")),
        "title": _message_string(getattr(entry, "title", "")) or None,
        "size": _message_int(getattr(entry, "size", 0)),
        "cluster_id": _message_string(getattr(entry, "cluster_id", "")) or None,
        "created_at": _message_string(getattr(entry, "created_at", "")) or None,
        "related_count": _message_int(getattr(entry, "related_count", 0)),
        "source_query_text": _message_string(getattr(entry, "source_query_text", "")) or None,
        "memory_id": _message_int(getattr(entry, "memory_id", 0)) or None,
        "memory_type": _message_string(getattr(entry, "memory_type", "")) or None,
        "content": _message_string(getattr(entry, "content", "")) or None,
        "source_query_id": _message_int(getattr(entry, "source_query_id", 0)) or None,
        "source_query_preview": _message_string(getattr(entry, "source_query_preview", "")) or None,
        "session_id": _message_string(getattr(entry, "session_id", "")) or None,
        "user_id": _message_int(getattr(entry, "user_id", 0)) or None,
        "importance": _coerce_score(getattr(entry, "importance", 0.0)),
        "access_count": _message_int(getattr(entry, "access_count", 0)),
        "last_accessed": _message_string(getattr(entry, "last_accessed", "")) or None,
        "expires_at": _message_string(getattr(entry, "expires_at", "")) or None,
        "review_status": _message_string(getattr(entry, "review_status", "")) or None,
        "review_reason": _message_string(getattr(entry, "review_reason", "")) or None,
        "duplicate_of_memory_id": _message_int(getattr(entry, "duplicate_of_memory_id", 0)) or None,
        "semantic_strength": _coerce_score(getattr(entry, "semantic_strength", 0.0)) or None,
        "memory_status": _message_string(getattr(entry, "memory_status", "")) or None,
        "is_active": _message_bool(getattr(entry, "is_active", False)),
        "dominant_type": _message_string(getattr(entry, "dominant_type", "")) or None,
        "summary": _message_string(getattr(entry, "summary", "")) or None,
        "member_ids": [int(item) for item in list(getattr(entry, "member_ids", []) or [])],
        "member_count": _message_int(getattr(entry, "member_count", 0)),
        "session_ids": [str(item) for item in list(getattr(entry, "session_ids", []) or []) if str(item)],
    }
    raw_metadata = _message_string(getattr(entry, "metadata_json", ""))
    if raw_metadata.strip():
        try:
            payload["metadata"] = json.loads(raw_metadata)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload["metadata"] = {}
    elif payload["kind"] == "memory":
        payload["metadata"] = {}
    return payload


def _graph_edge_to_dict(entry: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": _message_string(getattr(entry, "id", "")),
        "source": _message_string(getattr(entry, "source", "")),
        "target": _message_string(getattr(entry, "target", "")),
        "type": _message_string(getattr(entry, "type", "")),
        "weight": _coerce_score(getattr(entry, "weight", 0.0)),
        "label": _message_string(getattr(entry, "label", "")),
        "similarity": _coerce_score(getattr(entry, "similarity", 0.0)),
        "session_id": _message_string(getattr(entry, "session_id", "")) or None,
        "source_key": _message_string(getattr(entry, "source_key", "")) or None,
    }
    return payload


def _memory_map_stats_to_dict(entry: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "total_memories": _message_int(getattr(entry, "total_memories", 0)),
        "rendered_memories": _message_int(getattr(entry, "rendered_memories", 0)),
        "hidden_memories": _message_int(getattr(entry, "hidden_memories", 0)),
        "active_memories": _message_int(getattr(entry, "active_memories", 0)),
        "inactive_memories": _message_int(getattr(entry, "inactive_memories", 0)),
        "learning_nodes": _message_int(getattr(entry, "learning_nodes", 0)),
        "users": _message_int(getattr(entry, "users", 0)),
        "sessions": _message_int(getattr(entry, "sessions", 0)),
        "semantic_edges": _message_int(getattr(entry, "semantic_edges", 0)),
        "contextual_edges": _message_int(getattr(entry, "contextual_edges", 0)),
        "expiring_soon": _message_int(getattr(entry, "expiring_soon", 0)),
        "maintenance_operations": _message_int(getattr(entry, "maintenance_operations", 0)),
        "semantic_status": _message_string(getattr(entry, "semantic_status", "")) or None,
    }
    last_maintenance_at = _message_string(getattr(entry, "last_maintenance_at", ""))
    if last_maintenance_at:
        payload["last_maintenance_at"] = last_maintenance_at
    return payload


def _user_memory_count_to_dict(entry: object) -> dict[str, object]:
    return {
        "user_id": _message_int(getattr(entry, "user_id", 0)),
        "memory_count": _message_int(getattr(entry, "memory_count", 0)),
        "active_count": _message_int(getattr(entry, "active_count", 0)),
    }


def _audit_log_item_message_kwargs(item: dict[str, object]) -> dict[str, object]:
    return {
        "id": _message_int(item.get("id", 0)),
        "task_id": _message_int(item.get("task_id", 0)),
        "query_preview": _message_string(item.get("query_preview", "")),
        "trust_score": _coerce_score(item.get("trust_score")),
        "considered_json": _message_string(item.get("considered_json", "")),
        "selected_json": _message_string(item.get("selected_json", "")),
        "discarded_json": _message_string(item.get("discarded_json", "")),
        "conflicts_json": _message_string(item.get("conflicts_json", "")),
        "explanations_json": _message_string(item.get("explanations_json", "")),
        "created_at": _message_string(item.get("created_at", "")),
        "timestamp": _message_string(item.get("timestamp", "")),
        "details_json": _message_string(item.get("details_json", "")),
    }


def _recall_log_item_message_kwargs(item: dict[str, object]) -> dict[str, object]:
    return {
        "id": _message_int(item.get("id", 0)),
        "user_id": _message_int(item.get("user_id", 0)),
        "task_id": _message_int(item.get("task_id", 0)),
        "query_preview": _message_string(item.get("query_preview", "")),
        "trust_score": _coerce_score(item.get("trust_score")),
        "total_considered": _message_int(item.get("total_considered", 0)),
        "total_selected": _message_int(item.get("total_selected", 0)),
        "total_discarded": _message_int(item.get("total_discarded", 0)),
        "conflict_group_count": _message_int(item.get("conflict_group_count", 0)),
        "selected_layers_csv": _message_string(item.get("selected_layers_csv", "")),
        "retrieval_sources_csv": _message_string(item.get("retrieval_sources_csv", "")),
        "created_at": _message_string(item.get("created_at", "")),
    }


def _maintenance_log_item_message_kwargs(item: dict[str, object]) -> dict[str, object]:
    return {
        "operation": _message_string(item.get("operation", "")),
        "memories_affected": _message_int(item.get("memories_affected", 0)),
        "details": _message_string(item.get("details", "")),
        "executed_at": _message_string(item.get("executed_at", "")),
    }


class MemoryEngineClient(Protocol):
    """Behavior expected from the memory-engine adapter."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def recall(
        self,
        *,
        query: str,
        limit: int,
        user_id: int | None = None,
        memory_types: list[str] | None = None,
        project_key: str = "",
        environment: str = "",
        team: str = "",
        origin_kinds: list[str] | None = None,
        session_id: str | None = None,
        source_query_id: int | None = None,
        source_task_id: int | None = None,
        source_episode_id: int | None = None,
        memory_statuses: list[str] | None = None,
        allowed_layers: list[str] | None = None,
        allowed_retrieval_sources: list[str] | None = None,
    ) -> list[dict[str, object]]: ...

    async def cluster(self, *, rows: list[dict[str, object]]) -> list[dict[str, object]]: ...

    async def deduplicate(self, *, rows: list[dict[str, object]]) -> dict[str, object]: ...

    async def list_curation_items(self, *, payload: dict[str, object]) -> dict[str, object]: ...

    async def get_memory_map(self, *, payload: dict[str, object]) -> dict[str, object]: ...

    async def get_curation_detail(self, *, subject_id: str, payload: dict[str, object]) -> dict[str, object]: ...

    async def apply_curation_action(
        self,
        *,
        subject_id: str,
        action: str,
        payload: dict[str, object],
    ) -> dict[str, object]: ...

    def health(self) -> dict[str, object]: ...


class GrpcMemoryEngineClient:
    """Future Rust memory client over internal gRPC."""

    def __init__(self, *, selection: EngineSelection) -> None:
        self.selection = selection
        self._target, self._transport = resolve_grpc_target(config.MEMORY_GRPC_TARGET)
        self._channel: Any | None = None
        self._stub: Any | None = None
        self._metadata_pb2: Any | None = None
        self._memory_pb2: Any | None = None
        self._startup_error: str | None = None
        self._last_health: dict[str, object] = {
            "service": "memory",
            "mode": self.selection.mode,
            "implementation": "grpc-memory-engine-client",
            "transport": self._transport,
            "configured_target": self._target,
            "deadline_ms": config.INTERNAL_RPC_DEADLINE_MS,
            "connected": False,
            "verified": False,
            "ready": False,
            "startup_error": None,
            "selection_reason": self.selection.reason,
            "agent_id": self.selection.agent_id,
        }

    def _rpc_metadata(self) -> tuple[tuple[str, str], ...]:
        extra = {
            "x-internal-rpc-mode": self.selection.mode,
            "x-engine-selection-reason": self.selection.reason,
        }
        return build_rpc_metadata(
            agent_id=self.selection.agent_id,
            extra=extra,
        )

    def _request_metadata(self) -> Any | None:
        if self._metadata_pb2 is None:
            return None
        request_metadata_type = getattr(self._metadata_pb2, "RequestMetadata", None)
        if request_metadata_type is None:
            return None
        return request_metadata_type(
            agent_id=self.selection.agent_id or "",
            labels={
                "engine_selection_reason": self.selection.reason,
                "internal_rpc_mode": self.selection.mode,
            },
        )

    def _build_request(self, factory: Any, /, **kwargs: object) -> Any:
        request_metadata = self._request_metadata()
        if request_metadata is not None:
            try:
                return factory(metadata=request_metadata, **kwargs)
            except TypeError:
                pass
        return factory(**kwargs)

    async def _probe_health(self) -> None:
        if self._stub is None or self._metadata_pb2 is None:
            return
        response = await self._stub.Health(
            self._metadata_pb2.HealthRequest(),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        self._last_health = normalize_internal_service_probe(
            base_health=self._last_health,
            service=response.service,
            ready=bool(response.ready),
            status=response.status,
            details=dict(response.details),
        )

    async def start(self) -> None:
        try:
            import grpc.aio as grpc_aio

            ensure_generated_proto_path()
            from common.v1 import metadata_pb2
            from memory.v1 import memory_pb2, memory_pb2_grpc
        except Exception as exc:  # pragma: no cover - import failure depends on environment
            self._startup_error = f"{type(exc).__name__}: {exc}"
            self._last_health = {
                **self._last_health,
                "startup_error": self._startup_error,
                "ready": False,
            }
            raise RuntimeError("grpc_memory_engine_client_requires_grpcio") from exc
        self._channel = grpc_aio.insecure_channel(self._target)
        self._metadata_pb2 = metadata_pb2
        self._memory_pb2 = memory_pb2
        self._stub = memory_pb2_grpc.MemoryEngineServiceStub(self._channel)
        await self._probe_health()

    async def stop(self) -> None:
        if self._channel is None:
            return
        channel = self._channel
        self._channel = None
        self._stub = None
        await channel.close()

    async def recall(
        self,
        *,
        query: str,
        limit: int,
        user_id: int | None = None,
        memory_types: list[str] | None = None,
        project_key: str = "",
        environment: str = "",
        team: str = "",
        origin_kinds: list[str] | None = None,
        session_id: str | None = None,
        source_query_id: int | None = None,
        source_task_id: int | None = None,
        source_episode_id: int | None = None,
        memory_statuses: list[str] | None = None,
        allowed_layers: list[str] | None = None,
        allowed_retrieval_sources: list[str] | None = None,
    ) -> list[dict[str, object]]:
        if self._stub is None or self._memory_pb2 is None:
            raise RuntimeError("grpc_memory_engine_unavailable")
        recall_context_type = self._memory_pb2.RecallContext
        response = await self._stub.Recall(
            self._build_request(
                self._memory_pb2.RecallRequest,
                agent_id=self.selection.agent_id or "",
                query=query,
                limit=max(0, int(limit)),
                context=recall_context_type(
                    user_id=max(0, int(user_id or 0)),
                    memory_types=[str(item) for item in list(memory_types or []) if str(item)],
                    project_key=str(project_key or ""),
                    environment=str(environment or ""),
                    team=str(team or ""),
                    origin_kinds=[str(item) for item in list(origin_kinds or []) if str(item)],
                    session_id=str(session_id or ""),
                    source_query_id=max(0, int(source_query_id or 0)),
                    source_task_id=max(0, int(source_task_id or 0)),
                    source_episode_id=max(0, int(source_episode_id or 0)),
                    memory_statuses=[str(item) for item in list(memory_statuses or []) if str(item)],
                ),
                allowed_layers=list(allowed_layers or []),
                allowed_retrieval_sources=list(allowed_retrieval_sources or []),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        return [
            {
                "memory_id": _message_int(getattr(getattr(item, "memory", None), "id", 0)),
                "kind": _message_string(getattr(getattr(item, "memory", None), "memory_type", "")),
                "content": _message_string(getattr(getattr(item, "memory", None), "content", "")),
                "score": float(item.score or 0.0),
                "retrieval_source": _message_string(getattr(item, "retrieval_source", "")),
                "layer": _message_string(getattr(item, "layer", "")),
                "memory": _memory_record_row_to_dict(getattr(item, "memory", None)),
            }
            for item in response.items
        ]

    async def cluster(self, *, rows: list[dict[str, object]]) -> list[dict[str, object]]:
        if self._stub is None or self._memory_pb2 is None:
            raise RuntimeError("grpc_memory_engine_unavailable")
        row_type = self._memory_pb2.MemoryRecordRow
        response = await self._stub.Cluster(
            self._build_request(
                self._memory_pb2.ClusterRequest,
                agent_id=self.selection.agent_id or "",
                rows=[row_type(**_row_message_kwargs(row)) for row in list(rows)],
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        payload = json.loads(str(response.cluster_json or "[]") or "[]")
        return list(payload) if isinstance(payload, list) else []

    async def deduplicate(self, *, rows: list[dict[str, object]]) -> dict[str, object]:
        if self._stub is None or self._memory_pb2 is None:
            raise RuntimeError("grpc_memory_engine_unavailable")
        row_type = self._memory_pb2.MemoryRecordRow
        response = await self._stub.Deduplicate(
            self._build_request(
                self._memory_pb2.DeduplicateRequest,
                agent_id=self.selection.agent_id or "",
                rows=[row_type(**_row_message_kwargs(row)) for row in list(rows)],
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        payload = json.loads(str(response.dedupe_json or "{}") or "{}")
        return payload if isinstance(payload, dict) else {}

    async def list_curation_items(self, *, payload: dict[str, object]) -> dict[str, object]:
        if self._stub is None or self._memory_pb2 is None:
            raise RuntimeError("grpc_memory_engine_unavailable")
        row_type = self._memory_pb2.MemoryRecordRow
        cluster_summary_type = self._memory_pb2.CurationClusterSummary
        filter_type = self._memory_pb2.MemoryDashboardFilter
        rows = _dict_list(payload.get("rows"))
        all_rows = _dict_list(payload.get("all_rows"))
        cluster_rows = _dict_list(payload.get("cluster_rows"))
        filters = payload.get("filters")
        response = await self._stub.ListCurationItems(
            self._build_request(
                self._memory_pb2.ListCurationItemsRequest,
                agent_id=self.selection.agent_id or "",
                total=_message_int(payload.get("total", 0)),
                rows=[row_type(**_row_message_kwargs(item)) for item in rows],
                all_rows=[row_type(**_row_message_kwargs(item)) for item in all_rows],
                cluster_rows=[cluster_summary_type(**_cluster_summary_message_kwargs(item)) for item in cluster_rows],
                filters=filter_type(**_dashboard_filter_message_kwargs(filters))
                if isinstance(filters, dict)
                else filter_type(),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        typed_overview = getattr(response, "overview", None)
        typed_page = getattr(response, "page", None)
        return {
            "agent_id": _message_string(getattr(response, "agent_id", "")) or self.selection.agent_id or "",
            "overview": {
                "pending_memories": _message_int(getattr(typed_overview, "pending_memories", 0)),
                "pending_clusters": _message_int(getattr(typed_overview, "pending_clusters", 0)),
                "expiring_soon": _message_int(getattr(typed_overview, "expiring_soon", 0)),
                "discarded_last_7d": _message_int(getattr(typed_overview, "discarded_last_7d", 0)),
                "merged_last_7d": _message_int(getattr(typed_overview, "merged_last_7d", 0)),
                "approved_last_7d": _message_int(getattr(typed_overview, "approved_last_7d", 0)),
            },
            "items": [_curation_item_to_dict(item) for item in _object_list(getattr(response, "items", []))],
            "clusters": [_cluster_summary_to_dict(item) for item in _object_list(getattr(response, "clusters", []))],
            "available_filters": {
                "statuses": [
                    _filter_option_to_dict(item) for item in _object_list(getattr(response, "status_filters", []))
                ],
                "types": [_filter_option_to_dict(item) for item in _object_list(getattr(response, "type_filters", []))],
            },
            "filters": _dashboard_filter_to_dict(getattr(response, "filters", None)),
            "page": {
                "limit": _message_int(getattr(typed_page, "limit", 0)),
                "offset": _message_int(getattr(typed_page, "offset", 0)),
                "total": _message_int(getattr(typed_page, "total", 0)),
                "has_more": _message_bool(getattr(typed_page, "has_more", False)),
            },
        }

    async def get_memory_map(self, *, payload: dict[str, object]) -> dict[str, object]:
        if self._stub is None or self._memory_pb2 is None:
            raise RuntimeError("grpc_memory_engine_unavailable")
        summary_type = self._memory_pb2.MemoryMapSummary
        counter_type = self._memory_pb2.CounterEntry
        user_count_type = self._memory_pb2.UserMemoryCount
        cluster_summary_type = self._memory_pb2.CurationClusterSummary
        row_type = self._memory_pb2.MemoryRecordRow
        recall_log_type = self._memory_pb2.RecallLogItem
        maintenance_log_type = self._memory_pb2.MaintenanceLogItem
        filter_type = self._memory_pb2.MemoryDashboardFilter
        summary = payload.get("summary_row", {})
        type_rows = _dict_list(payload.get("type_rows"))
        user_rows = _dict_list(payload.get("user_rows"))
        embedding_rows = _dict_list(payload.get("embedding_rows"))
        quality_rows = _dict_list(payload.get("quality_rows"))
        cluster_rows = _dict_list(payload.get("cluster_rows"))
        rows = _dict_list(payload.get("rows"))
        recent_recall = _dict_list(payload.get("recent_recall"))
        maintenance_rows = _dict_list(payload.get("maintenance_rows"))
        filters = payload.get("filters")
        response = await self._stub.GetMemoryMap(
            self._build_request(
                self._memory_pb2.GetMemoryMapRequest,
                agent_id=self.selection.agent_id or "",
                summary=summary_type(
                    total=_message_int(getattr(summary, "get", lambda *_: 0)("total_memories", 0))
                    if isinstance(summary, dict)
                    else 0,
                    active=_message_int(summary.get("active_memories", 0)) if isinstance(summary, dict) else 0,
                    superseded=_message_int(summary.get("superseded_memories", 0)) if isinstance(summary, dict) else 0,
                    stale=_message_int(summary.get("stale_memories", 0)) if isinstance(summary, dict) else 0,
                    invalidated=_message_int(summary.get("invalidated_memories", 0))
                    if isinstance(summary, dict)
                    else 0,
                ),
                type_counts=[
                    counter_type(
                        key=_message_string(item.get("memory_type", "")),
                        count=_message_int(item.get("memory_count", 0)),
                    )
                    for item in type_rows
                ],
                user_counts=[
                    user_count_type(
                        user_id=_message_int(item.get("user_id", 0)),
                        memory_count=_message_int(item.get("memory_count", 0)),
                        active_count=_message_int(item.get("active_count", 0)),
                    )
                    for item in user_rows
                ],
                embedding_jobs=[
                    counter_type(
                        key=_message_string(item.get("status", "")), count=_message_int(item.get("job_count", 0))
                    )
                    for item in embedding_rows
                ],
                quality_counters=[
                    counter_type(
                        key=_message_string(item.get("counter_key", "")),
                        count=_message_int(item.get("counter_value", 0)),
                        updated_at=_message_string(item.get("updated_at", "")),
                    )
                    for item in quality_rows
                ],
                cluster_rows=[cluster_summary_type(**_cluster_summary_message_kwargs(item)) for item in cluster_rows],
                rows=[row_type(**_row_message_kwargs(item)) for item in rows],
                recent_recall=[recall_log_type(**_recall_log_item_message_kwargs(item)) for item in recent_recall],
                maintenance_rows=[
                    maintenance_log_type(**_maintenance_log_item_message_kwargs(item)) for item in maintenance_rows
                ],
                filters=filter_type(**_dashboard_filter_message_kwargs(filters))
                if isinstance(filters, dict)
                else filter_type(),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        typed_summary = getattr(response, "summary", None)
        return {
            "agent_id": _message_string(getattr(response, "agent_id", "")) or self.selection.agent_id or "",
            "summary": {
                "total": _message_int(getattr(typed_summary, "total", 0)),
                "active": _message_int(getattr(typed_summary, "active", 0)),
                "superseded": _message_int(getattr(typed_summary, "superseded", 0)),
                "stale": _message_int(getattr(typed_summary, "stale", 0)),
                "invalidated": _message_int(getattr(typed_summary, "invalidated", 0)),
            },
            "embedding_jobs": dict(
                pair
                for entry in _object_list(getattr(response, "embedding_jobs", []))
                if (pair := _counter_entry_to_pair(entry)) is not None
            ),
            "quality_counters": dict(
                pair
                for entry in _object_list(getattr(response, "quality_counters", []))
                if (pair := _counter_entry_to_pair(entry)) is not None
            ),
            "top_clusters": [
                _cluster_summary_to_dict(item) for item in _object_list(getattr(response, "top_clusters", []))
            ],
            "recent_recall": [
                _recall_log_item_to_dict(item) for item in _object_list(getattr(response, "recent_recall", []))
            ],
            "maintenance": [
                _maintenance_log_item_to_dict(item) for item in _object_list(getattr(response, "maintenance", []))
            ],
            "stats": _memory_map_stats_to_dict(getattr(response, "stats", None)),
            "filters": {
                "applied": _dashboard_filter_to_dict(getattr(response, "filters", None)),
                "users": [
                    _user_filter_option_to_dict(item) for item in _object_list(getattr(response, "filter_users", []))
                ],
                "sessions": [
                    _session_filter_option_to_dict(item)
                    for item in _object_list(getattr(response, "filter_sessions", []))
                ],
                "types": [_filter_option_to_dict(item) for item in _object_list(getattr(response, "filter_types", []))],
                "type_counts": dict(
                    pair
                    for entry in _object_list(getattr(response, "type_counts", []))
                    if (pair := _counter_entry_to_pair(entry)) is not None
                ),
                "user_counts": [
                    _user_memory_count_to_dict(item) for item in _object_list(getattr(response, "user_counts", []))
                ],
            },
            "nodes": [_graph_node_to_dict(item) for item in _object_list(getattr(response, "nodes", []))],
            "edges": [_graph_edge_to_dict(item) for item in _object_list(getattr(response, "edges", []))],
            "semantic_status": _message_string(getattr(response, "semantic_status", "")) or None,
        }

    async def get_curation_detail(self, *, subject_id: str, payload: dict[str, object]) -> dict[str, object]:
        if self._stub is None or self._memory_pb2 is None:
            raise RuntimeError("grpc_memory_engine_unavailable")
        row_type = self._memory_pb2.MemoryRecordRow
        audit_type = self._memory_pb2.AuditLogItem
        row_payload = payload.get("row")
        cluster_rows = _dict_list(payload.get("cluster_rows"))
        related_rows = _dict_list(payload.get("related_rows"))
        recent_audit_rows = _dict_list(payload.get("recent_audits"))
        response = await self._stub.GetCurationDetail(
            self._build_request(
                self._memory_pb2.GetCurationDetailRequest,
                agent_id=self.selection.agent_id or "",
                subject_id=subject_id,
                detail_kind=_message_string(payload.get("detail_kind", "")),
                cluster_id=_message_string(payload.get("cluster_id", "")),
                row=row_type(**_row_message_kwargs(row_payload)) if isinstance(row_payload, dict) else row_type(),
                cluster_rows=[row_type(**_row_message_kwargs(item)) for item in cluster_rows],
                related_rows=[row_type(**_row_message_kwargs(item)) for item in related_rows],
                recent_audits=[audit_type(**_audit_log_item_message_kwargs(item)) for item in recent_audit_rows],
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        detail_kind = _message_string(getattr(response, "detail_kind", ""))
        cluster_members = _object_list(getattr(response, "cluster_members", []))
        recent_audit_entries = _object_list(getattr(response, "recent_audits", []))
        related_memories = _object_list(getattr(response, "related_memories", []))
        cluster_summary = getattr(response, "cluster_summary", None)
        memory = getattr(response, "memory", None)
        audit_payload = [_audit_log_item_to_dict(item) for item in recent_audit_entries]
        history_payload = [_audit_log_item_to_dict(item) for item in _object_list(getattr(response, "history", []))]
        result: dict[str, object] = {
            "detail_kind": detail_kind or ("memory" if memory is not None else "cluster"),
            "recent_audits": audit_payload,
            "history": history_payload or audit_payload,
        }
        if memory is not None:
            result["memory"] = _curation_item_to_dict(memory)
            result["item"] = result["memory"]
            result["similar_memories"] = []
        if related_memories:
            result["related_memories"] = [_curation_item_to_dict(item) for item in related_memories]
        if cluster_summary is not None:
            cluster_summary_dict = _cluster_summary_to_dict(cluster_summary)
            members = [_curation_item_to_dict(item) for item in cluster_members]
            if result["detail_kind"] == "cluster":
                result["cluster"] = cluster_summary_dict
                result["members"] = members
                result["overlaps"] = [
                    {
                        "session_id": _message_string(getattr(item, "session_id", "")),
                        "count": _message_int(getattr(item, "count", 0)),
                    }
                    for item in _object_list(getattr(response, "overlaps", []))
                ]
            else:
                result["cluster"] = {
                    "summary": cluster_summary_dict,
                    "members": members,
                }
        source_query_text = _message_string(getattr(response, "source_query_text", ""))
        if source_query_text:
            result["source_query_text"] = source_query_text
        session_name = _message_string(getattr(response, "session_name", ""))
        if session_name:
            result["session_name"] = session_name
        return result

    async def apply_curation_action(
        self,
        *,
        subject_id: str,
        action: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        if self._stub is None or self._memory_pb2 is None:
            raise RuntimeError("grpc_memory_engine_unavailable")
        row_type = self._memory_pb2.MemoryRecordRow
        request_kwargs: dict[str, object] = {
            "agent_id": self.selection.agent_id or "",
            "subject_id": subject_id,
            "action": action,
            "target_type": _message_string(payload.get("target_type", "")),
            "target_ids": [str(item) for item in _object_list(payload.get("target_ids")) if str(item)],
            "cluster_ids": [str(item) for item in _object_list(payload.get("cluster_ids")) if str(item)],
            "memory_ids": [
                _message_int(item) for item in _object_list(payload.get("memory_ids")) if _message_int(item) > 0
            ],
            "reason": _message_string(payload.get("reason", "")),
            "duplicate_of_memory_id": _message_int(payload.get("duplicate_of_memory_id", 0)),
            "memory_status": _message_string(payload.get("memory_status", "")),
        }
        cluster_rows = payload.get("cluster_rows")
        if isinstance(cluster_rows, list):
            request_kwargs["cluster_rows"] = [
                row_type(**_row_message_kwargs(item)) for item in _dict_list(cluster_rows)
            ]
        response = await self._stub.ApplyCurationAction(
            self._build_request(
                self._memory_pb2.ApplyCurationActionRequest,
                **request_kwargs,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        typed_operations = _object_list(getattr(response, "operations", []))
        typed_memory_ids = [_message_int(item) for item in _object_list(getattr(response, "memory_ids", []))]
        if typed_operations or typed_memory_ids or _message_int(getattr(response, "updated_count", 0)):
            payload = {
                "applied": bool(getattr(response, "applied", False)),
                "updated_count": _message_int(getattr(response, "updated_count", 0)),
                "memory_ids": typed_memory_ids,
                "duplicate_of_memory_id": _message_int(getattr(response, "duplicate_of_memory_id", 0)) or None,
                "operations": [_action_operation_to_dict(item) for item in typed_operations],
                "target_type": _message_string(getattr(response, "target_type", "")) or None,
                "cluster_ids": [str(item) for item in _object_list(getattr(response, "cluster_ids", [])) if str(item)],
                "reason": _message_string(getattr(response, "reason", "")) or None,
                "memory_status": _message_string(getattr(response, "memory_status", "")) or None,
                "review_status": _message_string(getattr(response, "review_status", "")) or None,
            }
            error = _message_string(getattr(response, "error", ""))
            if error:
                payload["error"] = error
            return payload
        return {"applied": bool(getattr(response, "applied", False))}

    def health(self) -> dict[str, object]:
        connected = self._channel is not None
        return {
            **self._last_health,
            "connected": connected,
            "ready": bool(self._last_health.get("ready")) and connected and self._startup_error is None,
            "production_ready": bool(self._last_health.get("production_ready"))
            and connected
            and self._startup_error is None,
            "cutover_allowed": bool(self._last_health.get("cutover_allowed"))
            and connected
            and self._startup_error is None,
            "startup_error": self._startup_error,
        }


def build_memory_engine_client(*, agent_id: str | None = None) -> MemoryEngineClient:
    """Build the Rust memory-engine client."""

    selection = select_engine_backend(
        mode=config.INTERNAL_RPC_MODE,
        agent_id=agent_id,
    )
    return GrpcMemoryEngineClient(selection=selection)
