"""Runtime access brokering for control-plane initiated operations."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse, urlunparse

from koda.agent_contract import normalize_integration_grants, normalize_string_list
from koda.services.runtime_access_service import RuntimeAccessService

from .agent_spec import _safe_json_object, normalize_knowledge_policy
from .crypto import decrypt_secret
from .database import fetch_one

_LOOPBACK_RUNTIME_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _host_from_grpc_target(raw_target: str) -> str | None:
    raw = str(raw_target or "").strip()
    if not raw or raw.startswith(("unix:", "unix://")):
        return None
    if raw.startswith("dns:///"):
        raw = raw.removeprefix("dns:///")
    if "://" in raw:
        parsed = urlparse(raw)
        return parsed.hostname
    if raw.startswith("[") and "]" in raw:
        return raw[1 : raw.index("]")]
    return raw.rsplit(":", 1)[0].strip() or None


def _remote_runtime_kernel_host() -> str | None:
    host = _host_from_grpc_target(
        os.environ.get("RUNTIME_KERNEL_SOCKET") or os.environ.get("RUNTIME_KERNEL_GRPC_TARGET") or ""
    )
    if not host or host.lower() in _LOOPBACK_RUNTIME_HOSTS:
        return None
    return host


def _control_plane_reachable_runtime_url(raw_url: str) -> str:
    raw = str(raw_url or "").strip()
    if not raw:
        return raw
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw
    runtime_host = _remote_runtime_kernel_host()
    if not runtime_host or (parsed.hostname or "").lower() not in _LOOPBACK_RUNTIME_HOSTS:
        return raw
    netloc = runtime_host
    if parsed.port:
        netloc = f"{runtime_host}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


class ControlPlaneRuntimeAccessBroker:
    """Issue short-lived runtime credentials without exposing the base secret."""

    def __init__(self, manager: Any) -> None:
        self._manager = manager

    def _resolve_runtime_secret(self, agent_id: str, snapshot: dict[str, Any]) -> str:
        secrets = _safe_json_object(snapshot.get("secrets"))
        payload = _safe_json_object(secrets.get("RUNTIME_LOCAL_UI_TOKEN"))
        encrypted_value = str(payload.get("encrypted_value") or "").strip()
        if encrypted_value:
            return decrypt_secret(encrypted_value)

        row = fetch_one(
            "SELECT encrypted_value FROM cp_secret_values WHERE scope_id = 'global' AND secret_key = ?",
            ("RUNTIME_LOCAL_UI_TOKEN",),
        )
        encrypted_value = str(row["encrypted_value"] or "").strip() if row else ""
        if encrypted_value:
            return decrypt_secret(encrypted_value)

        normalized_agent_id = str(agent_id or "").strip().upper()
        if normalized_agent_id:
            scoped_value = str(os.environ.get(f"{normalized_agent_id}_RUNTIME_LOCAL_UI_TOKEN") or "").strip()
            if scoped_value:
                return scoped_value
        return str(os.environ.get("RUNTIME_LOCAL_UI_TOKEN") or "").strip()

    def resolve_runtime_secret(self, agent_id: str, snapshot: dict[str, Any] | None = None) -> str:
        return self._resolve_runtime_secret(agent_id, _safe_json_object(snapshot))

    def get_runtime_access(
        self,
        agent_id: str,
        *,
        capability: str = "read",
        include_sensitive: bool = False,
    ) -> dict[str, Any]:
        normalized, agent_row = self._manager._require_agent_row(agent_id)

        applied_version = int(agent_row["applied_version"] or 0)
        desired_version = int(agent_row["desired_version"] or 0)
        selected_version = applied_version or desired_version

        snapshot_candidate = (
            self._manager.get_published_snapshot(normalized, version=selected_version)
            if selected_version > 0
            else self._manager.build_draft_snapshot(normalized)
        )
        snapshot = snapshot_candidate or self._manager.build_draft_snapshot(normalized)
        agent_payload = _safe_json_object(snapshot.get("agent"))
        runtime_endpoint = _safe_json_object(agent_payload.get("runtime_endpoint"))
        health_url = str(
            runtime_endpoint.get("health_url")
            or f"http://127.0.0.1:{runtime_endpoint.get('health_port') or 8080}/health"
        )
        runtime_base_url = str(
            runtime_endpoint.get("runtime_base_url") or health_url.removesuffix("/health").rstrip("/")
        )
        health_url = _control_plane_reachable_runtime_url(health_url)
        runtime_base_url = _control_plane_reachable_runtime_url(runtime_base_url)

        runtime_secret = self._resolve_runtime_secret(normalized, snapshot)
        sections = _safe_json_object(snapshot.get("sections"))
        knowledge_section = _safe_json_object(sections.get("knowledge"))
        access_section = _safe_json_object(sections.get("access"))
        knowledge_policy = normalize_knowledge_policy(_safe_json_object(knowledge_section.get("policy")))
        resource_access_policy = _safe_json_object(access_section.get("resource_access_policy"))
        integration_grants = normalize_integration_grants(resource_access_policy.get("integration_grants"))
        try:
            workspace_id = str(agent_row["workspace_id"]).strip()
        except Exception:
            workspace_id = ""
        workspace_scope = tuple(item for item in [workspace_id] if item)
        source_scope = tuple(normalize_string_list(knowledge_policy.get("allowed_source_labels")))
        access_scope = {
            "agent_scope": normalized,
            "capabilities": [str(capability or "read").strip().lower() or "read"],
            "workspace_scope": list(workspace_scope),
            "source_scope": list(source_scope),
            "sensitive_allowed": bool(runtime_secret and include_sensitive),
            "integration_grants": integration_grants,
        }

        runtime_request_token = None
        runtime_request_expires_at = None
        access_scope_token = None
        access_scope_expires_at = None

        if runtime_secret:
            access_service = RuntimeAccessService(runtime_secret)
            requested_capability = str(capability or "read").strip().lower() or "read"
            runtime_capabilities: tuple[str, ...] = (requested_capability,)
            if requested_capability == "mutate":
                runtime_capabilities = ("mutate", "read")
            request_envelope, runtime_request_token = access_service.issue(
                agent_scope=normalized,
                capabilities=runtime_capabilities,
                sensitive_allowed=False,
                ttl_seconds=300,
            )
            runtime_request_expires_at = request_envelope.expires_at

            if include_sensitive:
                scope_envelope, access_scope_token = access_service.issue(
                    agent_scope=normalized,
                    capabilities=("read",),
                    workspace_scope=workspace_scope,
                    source_scope=source_scope,
                    sensitive_allowed=True,
                    ttl_seconds=300,
                )
                access_scope_expires_at = scope_envelope.expires_at

        return {
            "agent_id": normalized,
            "applied_version": applied_version or None,
            "desired_version": desired_version or None,
            "selected_version": selected_version or None,
            "health_url": health_url,
            "runtime_base_url": runtime_base_url,
            "runtime_token": None,
            "runtime_token_present": bool(runtime_secret),
            "runtime_request_token": runtime_request_token,
            "runtime_request_expires_at": runtime_request_expires_at,
            "runtime_request_capability": str(capability or "read").strip().lower() or "read",
            "access_scope": access_scope,
            "access_scope_token": access_scope_token,
            "access_scope_expires_at": access_scope_expires_at,
        }
