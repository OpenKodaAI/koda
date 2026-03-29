"""Runtime access brokering for control-plane initiated operations."""

from __future__ import annotations

from typing import Any

from koda.agent_contract import normalize_string_list
from koda.services.runtime_access_service import RuntimeAccessService

from .agent_spec import _safe_json_object, normalize_knowledge_policy
from .crypto import decrypt_secret
from .database import fetch_one


class ControlPlaneRuntimeAccessBroker:
    """Issue short-lived runtime credentials without exposing the base secret."""

    def __init__(self, manager: Any) -> None:
        self._manager = manager

    def _resolve_runtime_secret(self, snapshot: dict[str, Any]) -> str:
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
        return decrypt_secret(encrypted_value) if encrypted_value else ""

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

        runtime_secret = self._resolve_runtime_secret(snapshot)
        sections = _safe_json_object(snapshot.get("sections"))
        knowledge_section = _safe_json_object(sections.get("knowledge"))
        knowledge_policy = normalize_knowledge_policy(_safe_json_object(knowledge_section.get("policy")))
        try:
            workspace_id = str(agent_row["workspace_id"]).strip()
        except Exception:
            workspace_id = ""
        workspace_scope = tuple(
            item
            for item in [workspace_id]
            if item
        )
        source_scope = tuple(normalize_string_list(knowledge_policy.get("allowed_source_labels")))
        access_scope = {
            "agent_scope": normalized,
            "capabilities": [str(capability or "read").strip().lower() or "read"],
            "workspace_scope": list(workspace_scope),
            "source_scope": list(source_scope),
            "sensitive_allowed": bool(runtime_secret and include_sensitive),
        }

        runtime_request_token = None
        runtime_request_expires_at = None
        access_scope_token = None
        access_scope_expires_at = None

        if runtime_secret:
            access_service = RuntimeAccessService(runtime_secret)
            request_envelope, runtime_request_token = access_service.issue(
                agent_scope=normalized,
                capabilities=(str(capability or "read").strip().lower() or "read",),
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
