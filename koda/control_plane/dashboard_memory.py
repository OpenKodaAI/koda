"""Canonical control-plane payloads for the memory dashboard."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from typing import Any, cast

from koda.internal_rpc.memory_engine import build_memory_engine_client
from koda.services.audit import AuditEvent, emit
from koda.state.agent_scope import normalize_agent_scope
from koda.state.primary import require_primary_state_backend, run_coro_sync

_ENGINE_REVIEW_ACTIONS = {
    "approve",
    "restore",
    "merge",
    "discard",
    "expire",
    "archive",
}


def _scope(agent_id: str) -> str:
    scope = normalize_agent_scope(agent_id, fallback=agent_id)
    require_primary_state_backend(
        agent_id=scope,
        error="memory dashboard requires the primary state backend",
    )
    return scope


def _stringify(raw_value: Any) -> str:
    return "" if raw_value is None else str(raw_value)


def _clip_text(raw_value: Any, limit: int = 160) -> str | None:
    text = " ".join(_stringify(raw_value).split()).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


async def _async_call_memory_engine_projection(
    agent_id: str,
    *,
    method_name: str,
    payload: dict[str, Any],
    subject_id: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    """Run the full gRPC lifecycle (start → health → call → stop) in one event loop."""
    capability_by_method = {
        "list_curation_items": "curation",
        "get_memory_map": "memory_map",
        "get_curation_detail": "curation_detail",
        "apply_curation_action": "curation_action",
    }
    client = build_memory_engine_client(agent_id=agent_id)
    try:
        await client.start()
        health = dict(client.health() or {})
        if not bool(health.get("ready", False)):
            raise RuntimeError("memory_engine_unavailable")
        if not bool(health.get("cutover_allowed", False)):
            raise RuntimeError("memory_engine_not_authoritative")
        required_capability = capability_by_method.get(method_name)
        if required_capability and not _memory_engine_supports(health, required_capability):
            raise RuntimeError(f"memory_engine_missing_capability:{required_capability}")
        method = getattr(client, method_name, None)
        if not callable(method):
            raise RuntimeError(f"memory_engine_missing_method:{method_name}")
        kwargs: dict[str, Any] = {"payload": payload}
        if subject_id is not None:
            kwargs["subject_id"] = subject_id
        if action is not None:
            kwargs["action"] = action
        result = await method(**kwargs)
        if isinstance(result, dict):
            return cast(dict[str, Any], result)
        raise RuntimeError(f"memory_engine_invalid_{method_name}_response")
    finally:
        with contextlib.suppress(Exception):
            await client.stop()


def _call_memory_engine_projection(
    agent_id: str,
    *,
    method_name: str,
    payload: dict[str, Any],
    subject_id: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            run_coro_sync(
                _async_call_memory_engine_projection(
                    agent_id,
                    method_name=method_name,
                    payload=payload,
                    subject_id=subject_id,
                    action=action,
                )
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"memory_engine_projection_failed:{method_name}") from exc


def _memory_engine_supports(health: Mapping[str, Any], capability: str) -> bool:
    details = health.get("details")
    if not isinstance(details, Mapping):
        return False
    raw_capabilities = details.get("capabilities")
    if not isinstance(raw_capabilities, str) or not raw_capabilities.strip():
        return False
    capabilities = {item.strip() for item in raw_capabilities.split(",") if item.strip()}
    return capability in capabilities


def _coerce_memory_ids(payload: dict[str, Any]) -> list[int]:
    memory_ids: list[int] = []
    raw_ids = payload.get("memory_ids")
    if isinstance(raw_ids, list):
        for item in raw_ids:
            try:
                parsed = int(item)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                memory_ids.append(parsed)
    raw_single = payload.get("memory_id")
    if raw_single is not None:
        try:
            parsed = int(raw_single)
        except (TypeError, ValueError):
            parsed = 0
        if parsed > 0:
            memory_ids.append(parsed)
    return sorted(set(memory_ids))


def _coerce_cluster_ids(payload: dict[str, Any]) -> list[str]:
    cluster_ids: list[str] = []
    raw_ids = payload.get("cluster_ids")
    if isinstance(raw_ids, list):
        for item in raw_ids:
            value = _stringify(item).strip()
            if value:
                cluster_ids.append(value)
    single_cluster = _stringify(payload.get("cluster_id")).strip()
    if single_cluster:
        cluster_ids.append(single_cluster)
    raw_target_ids = payload.get("target_ids")
    if not cluster_ids and isinstance(raw_target_ids, list):
        for item in raw_target_ids:
            value = _stringify(item).strip()
            if value:
                cluster_ids.append(value)
    return sorted(set(cluster_ids))


def get_memory_map_payload(
    agent_id: str,
    *,
    user_id: int | None = None,
    session_id: str | None = None,
    days: int = 30,
    include_inactive: bool = False,
    limit: int = 160,
) -> dict[str, Any]:
    scope = _scope(agent_id)
    rpc_payload = {
        "agent_id": scope,
        "filters": {
            "user_id": user_id,
            "session_id": session_id,
            "days": days,
            "include_inactive": include_inactive,
            "limit": limit,
        },
    }
    return _call_memory_engine_projection(scope, method_name="get_memory_map", payload=rpc_payload)


def list_memory_curation_payload(
    agent_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    user_id: int | None = None,
    review_status: str | None = None,
    memory_status: str | None = None,
    status: str | None = None,
    memory_type: str | None = None,
    query_text: str = "",
    search: str | None = None,
    cluster_id: str | None = None,
    origin_kind: str | None = None,
    kind: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    scope = _scope(agent_id)
    effective_review_status = (review_status or status or "").strip().lower() or None
    effective_memory_status = memory_status.strip().lower() if memory_status else None
    effective_query = search if search is not None else query_text
    return _call_memory_engine_projection(
        scope,
        method_name="list_curation_items",
        payload={
            "agent_id": scope,
            "filters": {
                "query": effective_query,
                "memory_status": effective_memory_status,
                "review_status": effective_review_status,
                "memory_type": memory_type,
                "kind": kind,
                "origin_kind": origin_kind,
                "cluster_id": cluster_id,
                "user_id": user_id,
                "is_active": is_active,
                "limit": limit,
                "offset": offset,
            },
        },
    )


def get_memory_curation_detail_payload(agent_id: str, memory_id: int) -> dict[str, Any]:
    scope = _scope(agent_id)
    try:
        return _call_memory_engine_projection(
            scope,
            method_name="get_curation_detail",
            subject_id=str(memory_id),
            payload={
                "agent_id": scope,
                "detail_kind": "memory",
            },
        )
    except RuntimeError as exc:
        if "not found" in str(exc.__cause__ or exc).lower():
            raise KeyError("memory not found") from exc
        raise


def get_memory_curation_cluster_payload(agent_id: str, cluster_id: str) -> dict[str, Any]:
    scope = _scope(agent_id)
    try:
        return _call_memory_engine_projection(
            scope,
            method_name="get_curation_detail",
            subject_id=cluster_id,
            payload={
                "agent_id": scope,
                "detail_kind": "cluster",
                "cluster_id": cluster_id,
            },
        )
    except RuntimeError as exc:
        if "not found" in str(exc.__cause__ or exc).lower():
            raise KeyError("memory cluster not found") from exc
        raise


def apply_memory_curation_action(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    scope = _scope(agent_id)
    action = _stringify(payload.get("action")).strip().lower()
    if action == "set_status":
        target_ids = _coerce_memory_ids(payload)
        if len(target_ids) != 1:
            raise ValueError("exactly one memory_id is required")
        memory_status = _stringify(payload.get("memory_status")).strip().lower()
        if not memory_status:
            raise ValueError("memory_status is required")
        cluster_ids: list[str] = []
        target_type = "memory"
    elif action == "deactivate":
        target_ids = _coerce_memory_ids(payload)
        if not target_ids:
            raise ValueError("no memory targets provided")
        cluster_ids = []
        target_type = "memory"
    elif action in _ENGINE_REVIEW_ACTIONS:
        target_type = _stringify(payload.get("target_type")).strip().lower() or (
            "cluster" if _coerce_cluster_ids(payload) else "memory"
        )
        if target_type == "cluster":
            cluster_ids = _coerce_cluster_ids(payload)
            if not cluster_ids:
                raise ValueError("no cluster targets provided")
        else:
            cluster_ids = []
        target_ids = _coerce_memory_ids(payload)
    else:
        raise ValueError("unsupported memory curation action")
    reason = _clip_text(payload.get("reason"), 400)
    duplicate_of_memory_id = payload.get("duplicate_of_memory_id")
    keeper_id: int | None = None
    if action == "merge":
        try:
            keeper_id = int(duplicate_of_memory_id) if duplicate_of_memory_id is not None else None
        except (TypeError, ValueError):
            keeper_id = None

    rpc_payload = {
        "agent_id": scope,
        "action": action,
        "target_type": target_type,
        "target_ids": cluster_ids if target_type == "cluster" else target_ids,
        "cluster_ids": cluster_ids,
        "memory_ids": target_ids,
        "reason": reason,
        "duplicate_of_memory_id": keeper_id,
        "memory_status": payload.get("memory_status"),
    }
    rpc_action = _call_memory_engine_projection(
        scope,
        method_name="apply_curation_action",
        payload=rpc_payload,
        subject_id=(
            cluster_ids[0]
            if target_type == "cluster" and cluster_ids
            else (str(target_ids[0]) if len(target_ids) == 1 else "memory-batch")
        ),
        action=action,
    )
    if not isinstance(rpc_action, dict) or not rpc_action:
        raise RuntimeError("memory_engine_invalid_action_plan")
    error_message = _stringify(rpc_action.get("error")).strip()
    if error_message:
        raise ValueError(error_message)
    operations = [
        dict(item)
        for item in rpc_action.get("operations") or []
        if isinstance(rpc_action.get("operations"), list) and isinstance(item, dict)
    ]
    if not operations:
        raise RuntimeError("memory_engine_missing_operations")
    reason = _clip_text(rpc_action.get("reason"), 400) or reason
    target_type = _stringify(rpc_action.get("target_type")).strip().lower() or target_type
    cluster_ids = [
        _stringify(item).strip()
        for item in rpc_action.get("cluster_ids") or []
        if isinstance(rpc_action.get("cluster_ids"), list) and _stringify(item).strip()
    ] or cluster_ids
    rpc_memory_ids = [
        int(item)
        for item in rpc_action.get("memory_ids") or []
        if isinstance(rpc_action.get("memory_ids"), list) and str(item).isdigit() and int(item) > 0
    ]
    if rpc_memory_ids:
        target_ids = sorted(set(rpc_memory_ids))
    rpc_duplicate = rpc_action.get("duplicate_of_memory_id")
    if rpc_duplicate is not None:
        try:
            keeper_id = int(rpc_duplicate)
        except (TypeError, ValueError):
            keeper_id = None

    emit(
        AuditEvent(
            event_type="memory.curation.action",
            agent_id=scope,
            details={
                "action": action,
                "reason": reason,
                "target_type": target_type,
                "target_id": cluster_ids[0] if target_type == "cluster" and cluster_ids else str(target_ids[0]),
                "cluster_ids": cluster_ids,
                "memory_ids": rpc_memory_ids or target_ids,
                "duplicate_of_memory_id": keeper_id,
            },
        )
    )

    return {
        "ok": True,
        "agent_id": scope,
        "action": action,
        "updated_count": int(rpc_action.get("updated_count", 0) or 0),
        "memory_ids": rpc_memory_ids or target_ids,
        "cluster_ids": cluster_ids,
        "duplicate_of_memory_id": keeper_id,
    }
