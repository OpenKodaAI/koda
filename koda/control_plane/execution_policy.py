"""Execution policy helpers for control-plane AgentSpec contracts."""

from __future__ import annotations

import contextlib
from fnmatch import fnmatch
from typing import Any

from koda.agent_contract import (
    CORE_INTEGRATION_CATALOG,
    build_action_envelope,
    normalize_string_list,
    resolve_core_integration_action_catalog,
    resolve_feature_filtered_tools,
)

EXECUTION_POLICY_DECISIONS = frozenset({"allow", "allow_with_preview", "require_approval", "deny"})
EXECUTION_POLICY_EFFECT_TAGS = (
    "external_communication",
    "sharing_or_permissions",
    "destructive_change",
    "bulk_write",
    "credential_access",
    "private_network",
    "browser_state_mutation",
    "package_or_plugin_install",
    "delegation",
    "identity_admin",
)
_PREVIEW_EFFECT_TAGS = frozenset(
    {
        "external_communication",
        "sharing_or_permissions",
        "destructive_change",
        "bulk_write",
        "package_or_plugin_install",
        "mcp_write",
    }
)
_ALWAYS_APPROVAL_EFFECT_TAGS = frozenset(
    {
        "credential_access",
        "private_network",
        "browser_state_mutation",
        "delegation",
        "identity_admin",
    }
)
EXECUTION_POLICY_SELECTOR_KEYS = frozenset(
    {
        "tool_id",
        "integration_id",
        "action_id",
        "server_key",
        "effect_tags",
        "access_level",
        "risk_class",
        "task_kind",
        "domain",
        "path",
        "db_env",
        "transport",
        "private_network",
        "uses_secrets",
        "bulk_operation",
        "external_side_effect",
    }
)
_CORE_TOOL_FAMILY_OVERRIDES = {
    "agent_set_workdir": "agent_runtime",
    "agent_get_status": "agent_runtime",
    "agent_send": "agent_comm",
    "agent_receive": "agent_comm",
    "agent_delegate": "agent_comm",
    "agent_list_agents": "agent_comm",
    "agent_broadcast": "agent_comm",
}
_ACTION_GROUPING_TEMPLATES = (
    {
        "kind": "approval_once",
        "label": "Approve once",
        "description": "Approve a single normalized action envelope for one execution.",
    },
    {
        "kind": "approval_scope",
        "label": "Approve scope",
        "description": "Approve a bounded action scope for a short TTL and limited use count.",
    },
    {
        "kind": "deny",
        "label": "Deny",
        "description": "Block this action or rule path explicitly.",
    },
)


def _safe_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _trimmed(value: Any) -> str:
    return str(value or "").strip()


def _humanize_label(value: str) -> str:
    label = str(value or "").replace("_", " ").replace(".", " ").replace("-", " ").replace(":", " ")
    return " ".join(part.capitalize() if part.islower() else part for part in label.split())


def _tool_family(tool_id: str) -> str:
    normalized = _trimmed(tool_id).lower()
    if normalized in _CORE_TOOL_FAMILY_OVERRIDES:
        return _CORE_TOOL_FAMILY_OVERRIDES[normalized]
    if normalized.startswith(("job_", "cron_")):
        return "scheduler"
    if normalized in {"web_search", "fetch_url", "http_request"}:
        return "web"
    if normalized.startswith("browser_"):
        return "browser"
    if normalized in {"gws", "jira", "confluence"}:
        return normalized
    if normalized.startswith("script_"):
        return "script_library"
    if normalized.startswith("cache_"):
        return "cache"
    if normalized.startswith("file_"):
        return "fileops"
    if normalized.startswith("shell_"):
        return "shell"
    if normalized.startswith("git_"):
        return "git"
    if normalized.startswith("gh_"):
        return "gh"
    if normalized.startswith("glab_"):
        return "glab"
    if normalized.startswith("docker_"):
        return "docker"
    if normalized.startswith("pip_"):
        return "pip"
    if normalized.startswith("npm_"):
        return "npm"
    if normalized.startswith("plugin_"):
        return "plugin"
    if normalized.startswith("workflow_"):
        return "workflow"
    if normalized.startswith("webhook_"):
        return "webhook"
    return normalized or "general"


def _default_decision_for_action(access_level: str, effect_tags: list[str] | tuple[str, ...]) -> tuple[str, str]:
    normalized_level = _trimmed(access_level).lower()
    normalized_tags = {str(tag).strip().lower() for tag in effect_tags if str(tag).strip()}
    if normalized_level == "read":
        return "allow", "safe_read_default"
    if normalized_level in {"admin", "destructive"} or normalized_tags & _ALWAYS_APPROVAL_EFFECT_TAGS:
        return "require_approval", "human_factor_required"
    if normalized_tags & _PREVIEW_EFFECT_TAGS or normalized_level == "write":
        return "allow_with_preview", "preview_required_default"
    return "allow_with_preview", "preview_required_default"


def _preview_required_for_action(decision: str) -> bool:
    return decision in {"allow_with_preview", "require_approval"}


def _approval_scope_default(decision: str) -> str | None:
    return "tool_call" if _preview_required_for_action(decision) else None


def _catalog_action_entry(
    *,
    tool_id: str,
    integration_id: str,
    action_id: str,
    title: str,
    description: str,
    transport: str,
    access_level: str,
    risk_class: str,
    effect_tags: list[str] | tuple[str, ...],
    resource_method: str | None = None,
    server_key: str | None = None,
    source: str = "core",
    default_decision: str | None = None,
    default_reason_code: str | None = None,
) -> dict[str, Any]:
    normalized_tags = [str(tag).strip().lower() for tag in effect_tags if str(tag).strip()]
    decision = _trimmed(default_decision).lower() or _default_decision_for_action(access_level, normalized_tags)[0]
    reason_code = _trimmed(default_reason_code) or _default_decision_for_action(access_level, normalized_tags)[1]
    preview_required = _preview_required_for_action(decision)
    return _compact_mapping(
        {
            "tool_id": tool_id,
            "integration_id": integration_id,
            "action_id": action_id,
            "title": title,
            "description": description,
            "transport": transport,
            "access_level": access_level,
            "risk_class": risk_class,
            "effect_tags": normalized_tags,
            "resource_method": resource_method,
            "server_key": server_key,
            "default_decision": decision,
            "default_reason_code": reason_code,
            "preview_required_default": preview_required,
            "approval_scope_default": _approval_scope_default(decision),
            "source": source,
        }
    )


def _effect_tags_for_core_action(tool_id: str, access_level: str, description: str = "") -> list[str]:
    normalized = _trimmed(tool_id).lower()
    tags: set[str] = set()
    if access_level == "destructive":
        tags.add("destructive_change")
    if access_level == "admin":
        tags.add("identity_admin")
    if normalized in {"plugin_install", "plugin_uninstall", "plugin_reload"} or "plugin" in normalized:
        tags.add("package_or_plugin_install")
    if normalized.startswith("browser_") and access_level != "read":
        tags.add("browser_state_mutation")
    if normalized == "browser_cookies":
        tags.add("browser_state_mutation")
        if access_level != "read":
            tags.add("identity_admin")
    if normalized in {"agent_send", "agent_delegate", "agent_broadcast"}:
        tags.add("external_communication")
    if normalized == "agent_delegate":
        tags.add("delegation")
    if normalized.startswith("job_") or normalized.startswith("cron_") or normalized.startswith("workflow_"):
        tags.add("delegation")
    if normalized.startswith("webhook_"):
        tags.add("external_communication")
    if normalized.startswith("file_") and access_level == "destructive":
        tags.add("destructive_change")
    if "publish" in normalized or "push" in normalized or "send" in normalized or "share" in normalized:
        tags.add("external_communication")
    if "permission" in normalized or "acl" in normalized or "share" in normalized:
        tags.add("sharing_or_permissions")
    if "credential" in description.lower() or normalized in {"gws", "jira", "confluence"}:
        tags.add("credential_access")
    return sorted(tags)


def _core_tool_action_entries(*, feature_flags: dict[str, bool] | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    browser_write_tools = {
        "browser_session_save",
        "browser_session_restore",
        "browser_tab_open",
        "browser_tab_close",
        "browser_tab_switch",
        "browser_execute_js",
        "browser_download",
        "browser_upload",
        "browser_set_viewport",
    }
    destructive_or_write_tools = {
        "shell_kill",
        "git_push",
        "git_pull",
        "plugin_install",
        "plugin_uninstall",
        "plugin_reload",
        "workflow_run",
        "workflow_create",
        "workflow_delete",
        "agent_send",
        "agent_delegate",
        "agent_broadcast",
    }
    destructive_write_only_tools = {
        "shell_kill",
        "workflow_delete",
        "plugin_uninstall",
    }
    known_read_tools = {
        "browser_navigate",
        "browser_screenshot",
        "browser_get_text",
        "browser_get_elements",
        "browser_scroll",
        "browser_wait",
        "browser_back",
        "browser_forward",
        "browser_tab_list",
        "browser_tab_compare",
        "browser_pdf",
        "script_search",
        "script_list",
        "cache_stats",
        "file_read",
        "file_list",
        "file_search",
        "file_grep",
        "file_info",
        "shell_status",
        "shell_output",
        "git_status",
        "git_diff",
        "git_log",
        "plugin_list",
        "plugin_info",
        "workflow_list",
        "workflow_get",
        "agent_receive",
        "agent_list_agents",
        "job_list",
        "job_get",
        "job_runs",
        "cron_list",
    }
    for tool in resolve_feature_filtered_tools(feature_flags):
        if not bool(tool.get("available", True)):
            continue
        tool_id = str(tool.get("id") or "")
        if not tool_id:
            continue
        family = _tool_family(tool_id)
        integration_definition = CORE_INTEGRATION_CATALOG.get(family)
        access_level = "read" if bool(tool.get("read_only")) else "write"
        if tool_id in {"file_delete", "job_delete", "cron_delete", "workflow_delete"} or "delete" in tool_id:
            access_level = "destructive"
        if tool_id in {"browser_cookies"}:
            access_level = "write"
        if tool_id in {"browser_network_capture_start", "browser_network_capture_stop", "browser_network_mock"}:
            access_level = "write"
        if tool_id in browser_write_tools:
            access_level = "write"
        if tool_id in destructive_or_write_tools:
            access_level = "write" if tool_id not in destructive_write_only_tools else "destructive"
        if tool_id in known_read_tools:
            access_level = "read"
        effect_tags = _effect_tags_for_core_action(tool_id, access_level, str(tool.get("description") or ""))
        default_decision, default_reason_code = _default_decision_for_action(access_level, effect_tags)
        if tool_id in {"browser_cookies"}:
            entries.extend(
                _browser_cookie_action_entries(tool, access_level=access_level, family=family, source="core")
            )
            continue
        if tool_id == "http_request":
            entries.extend(_http_request_action_entries(tool, source="core"))
            continue
        entries.append(
            _catalog_action_entry(
                tool_id=tool_id,
                integration_id=family,
                action_id=tool_id,
                title=str(tool.get("title") or _humanize_label(tool_id)),
                description=str(tool.get("description") or ""),
                transport=str(integration_definition.transport if integration_definition is not None else "internal"),
                access_level=access_level,
                risk_class=access_level,
                effect_tags=effect_tags,
                resource_method=tool_id,
                source="core_tool",
                default_decision=default_decision,
                default_reason_code=default_reason_code,
            )
        )
    return entries


def _http_request_action_entries(tool: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for method, access_level in (
        ("get", "read"),
        ("head", "read"),
        ("options", "read"),
        ("post", "write"),
        ("put", "write"),
        ("patch", "write"),
        ("delete", "destructive"),
    ):
        action_id = f"http.{method}"
        effect_tags = ["external_communication"]
        if access_level == "destructive":
            effect_tags.append("destructive_change")
        default_decision, default_reason_code = _default_decision_for_action(access_level, effect_tags)
        entries.append(
            _catalog_action_entry(
                tool_id="http_request",
                integration_id="web",
                action_id=action_id,
                title=f"HTTP {method.upper()}",
                description=str(tool.get("description") or ""),
                transport="http",
                access_level=access_level,
                risk_class=access_level,
                effect_tags=effect_tags,
                resource_method=action_id,
                source=source,
                default_decision=default_decision,
                default_reason_code=default_reason_code,
            )
        )
    return entries


def _browser_cookie_action_entries(
    tool: dict[str, Any],
    *,
    access_level: str,
    family: str,
    source: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for action_id, action_level in (("cookies.get", "read"), ("cookies.set", "admin")):
        effect_tags = ["browser_state_mutation"] if action_id == "cookies.set" else []
        if action_id == "cookies.set":
            effect_tags.append("identity_admin")
        default_decision, default_reason_code = _default_decision_for_action(action_level, effect_tags)
        entries.append(
            _catalog_action_entry(
                tool_id="browser_cookies",
                integration_id=family,
                action_id=action_id,
                title="Browser cookies set" if action_id.endswith(".set") else "Browser cookies get",
                description=str(tool.get("description") or ""),
                transport="browser",
                access_level=action_level,
                risk_class=action_level,
                effect_tags=effect_tags,
                resource_method=action_id,
                source=source,
                default_decision=default_decision,
                default_reason_code=default_reason_code,
            )
        )
    return entries


def _sample_args_for_action(action_id: str) -> str:
    parts = [part for part in str(action_id or "").replace(".", " ").split() if part]
    return " ".join(parts)


def _grouped_surface_action_entries() -> list[dict[str, Any]]:
    catalog = resolve_core_integration_action_catalog()
    entries: list[dict[str, Any]] = []

    for surface in ("gws", "jira", "confluence"):
        for item in catalog.get(surface, []):
            action_id = str(item.get("action_id") or "").strip()
            if not action_id:
                continue
            sample_args = _sample_args_for_action(action_id)
            envelope = build_action_envelope(surface, {"args": sample_args})
            effect_tags = list(envelope.effect_tags)
            if envelope.access_level != "read" and "credential_access" not in effect_tags:
                effect_tags.append("credential_access")
            entries.append(
                _catalog_action_entry(
                    tool_id=surface,
                    integration_id=surface,
                    action_id=action_id,
                    title=f"{_humanize_label(surface)} {_humanize_label(action_id)}",
                    description=f"Governed {surface} action {action_id}.",
                    transport=envelope.transport,
                    access_level=str(item.get("access_level") or envelope.access_level),
                    risk_class=str(item.get("access_level") or envelope.risk_class),
                    effect_tags=effect_tags,
                    resource_method=action_id,
                    source="core_surface",
                    default_reason_code=(
                        "preview_required_default" if envelope.access_level != "read" else "safe_read_default"
                    ),
                )
            )

    return entries


def build_mcp_action_catalog(
    *,
    server_key: str,
    tools: list[dict[str, Any]],
    tool_policies: dict[str, str] | None = None,
    transport: str = "mcp",
    connection_title: str | None = None,
    connection_description: str | None = None,
) -> list[dict[str, Any]]:
    policy_map = {
        str(key).strip(): str(value or "auto").strip().lower() for key, value in (tool_policies or {}).items()
    }
    entries: list[dict[str, Any]] = []
    for tool in tools:
        tool_name = str(tool.get("name") or "").strip()
        if not tool_name:
            continue
        tool_id = f"mcp_{server_key}__{tool_name}"
        envelope = build_action_envelope(tool_id, {})
        annotations = _safe_object(tool.get("annotations"))
        description = str(tool.get("description") or connection_description or "")
        title = str(annotations.get("title") or tool.get("title") or connection_title or _humanize_label(tool_name))
        access_level = str(tool.get("risk_level") or envelope.access_level or "write").lower()
        policy = policy_map.get(tool_name, "auto")
        if policy == "blocked":
            default_decision = "deny"
            default_reason_code = "mcp_tool_blocked"
        elif policy == "always_allow":
            default_decision = "allow"
            default_reason_code = "mcp_tool_always_allow"
        elif policy == "always_ask":
            default_decision = "require_approval"
            default_reason_code = "mcp_tool_requires_approval"
        else:
            default_decision, default_reason_code = _default_decision_for_action(access_level, envelope.effect_tags)
        entries.append(
            _catalog_action_entry(
                tool_id=tool_id,
                integration_id=f"mcp:{server_key}",
                action_id=tool_name,
                title=title,
                description=description,
                transport=transport,
                access_level=access_level,
                risk_class=access_level,
                effect_tags=list(envelope.effect_tags),
                resource_method=str(envelope.resource_method or tool_name),
                server_key=server_key,
                source="mcp_discovered",
                default_decision=default_decision,
                default_reason_code=default_reason_code,
            )
        )
    return entries


def _compact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {}, ())}


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return None


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_selector_value(value: Any, *, key: str) -> Any:
    if key == "effect_tags":
        tags = [item.lower() for item in normalize_string_list(value)]
        return tags
    if key in {"private_network", "uses_secrets", "bulk_operation", "external_side_effect"}:
        parsed = _as_bool(value)
        return parsed if parsed is not None else value
    if isinstance(value, dict):
        return {
            str(sub_key).strip(): _normalize_selector_value(sub_value, key=str(sub_key).strip())
            for sub_key, sub_value in value.items()
            if str(sub_key).strip()
        }
    if isinstance(value, list):
        normalized = [_normalize_selector_value(item, key=key) for item in value]
        return [item for item in normalized if item not in (None, "", [], {}, ())]
    if isinstance(value, str):
        return value.strip()
    return value


def normalize_execution_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(_safe_object(policy))
    if not raw:
        return {}

    version = _as_int(raw.get("version")) or 1
    raw["version"] = version

    default_decision = _trimmed(raw.get("default_decision")).lower()
    if default_decision in EXECUTION_POLICY_DECISIONS:
        raw["default_decision"] = default_decision

    default_approval_mode = _trimmed(_safe_object(raw.get("defaults")).get("default_approval_mode")).lower()
    if default_approval_mode:
        defaults = dict(_safe_object(raw.get("defaults")))
        defaults["default_approval_mode"] = default_approval_mode
        raw["defaults"] = _compact_mapping(defaults)

    normalized_rules: list[dict[str, Any]] = []
    for index, rule in enumerate(_safe_list(raw.get("rules"))):
        if not isinstance(rule, dict):
            continue

        match = _safe_object(rule.get("match"))
        normalized_match: dict[str, Any] = {}
        for key, value in match.items():
            selector = _trimmed(key)
            if not selector:
                continue
            normalized_match[selector] = _normalize_selector_value(value, key=selector)

        decision = _trimmed(rule.get("decision")).lower()
        if not decision:
            decision = "require_approval"

        normalized_rule = {
            "name": _trimmed(rule.get("name")) or f"rule_{index}",
            "priority": _as_int(rule.get("priority")) or 0,
            "match": normalized_match,
            "decision": decision,
        }
        reason = _trimmed(rule.get("reason"))
        if reason:
            normalized_rule["reason"] = reason
        preview_fields = normalize_string_list(rule.get("preview_fields"))
        if preview_fields:
            normalized_rule["preview_fields"] = preview_fields
        approval_scope_kind = _trimmed(rule.get("approval_scope_kind"))
        if approval_scope_kind:
            normalized_rule["approval_scope_kind"] = approval_scope_kind
        approval_ttl_seconds = _as_int(rule.get("approval_ttl_seconds"))
        if approval_ttl_seconds is not None:
            normalized_rule["approval_ttl_seconds"] = approval_ttl_seconds

        if decision in EXECUTION_POLICY_DECISIONS and normalized_match:
            normalized_rules.append(_compact_mapping(normalized_rule))

    if normalized_rules:
        normalized_rules.sort(
            key=lambda item: (
                -int(item.get("priority", 0) or 0),
                str(item.get("name") or ""),
            )
        )
        raw["rules"] = normalized_rules
    elif "rules" in raw:
        raw["rules"] = []

    source = _trimmed(raw.get("source")).lower()
    if source:
        raw["source"] = source

    return _compact_mapping(raw)


def validate_execution_policy(policy: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    raw = _safe_object(policy)
    if not raw:
        return [], []

    errors: list[str] = []
    warnings: list[str] = []

    version = _as_int(raw.get("version"))
    if version is not None and version != 1:
        errors.append(f"execution_policy.version is invalid: {version}")

    rules = _safe_list(raw.get("rules"))
    if raw.get("rules") is not None and not isinstance(raw.get("rules"), list):
        errors.append("execution_policy.rules must be a list.")
        return errors, warnings

    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"execution_policy.rules[{index}] must be a mapping.")
            continue

        decision = _trimmed(rule.get("decision")).lower()
        if decision and decision not in EXECUTION_POLICY_DECISIONS:
            errors.append(
                f"execution_policy.rules[{index}].decision is invalid: {decision}. "
                f"Expected one of: {', '.join(sorted(EXECUTION_POLICY_DECISIONS))}"
            )

        match = rule.get("match")
        if not isinstance(match, dict):
            errors.append(f"execution_policy.rules[{index}].match must be a mapping.")
            continue

        unknown_selectors = sorted(str(key) for key in match if str(key).strip() not in EXECUTION_POLICY_SELECTOR_KEYS)
        if unknown_selectors:
            warnings.append(
                f"execution_policy.rules[{index}].match contains unsupported selectors: " + ", ".join(unknown_selectors)
            )

        for key in ("preview_fields",):
            value = rule.get(key)
            if value is None:
                continue
            if not isinstance(value, list):
                errors.append(f"execution_policy.rules[{index}].{key} must be a list.")

        ttl_value = rule.get("approval_ttl_seconds")
        if ttl_value not in (None, ""):
            ttl = _as_int(ttl_value)
            if ttl is None or ttl <= 0:
                errors.append(f"execution_policy.rules[{index}].approval_ttl_seconds must be a positive integer.")

    return errors, warnings


def compile_legacy_execution_policy(
    agent_spec: dict[str, Any],
    *,
    feature_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    normalized_spec = {
        "tool_policy": _safe_object(agent_spec.get("tool_policy")),
        "autonomy_policy": _safe_object(agent_spec.get("autonomy_policy")),
        "resource_access_policy": _safe_object(agent_spec.get("resource_access_policy")),
    }
    catalog = build_policy_catalog(feature_flags=feature_flags)
    allowed_tool_ids = normalize_string_list(normalized_spec["tool_policy"].get("allowed_tool_ids"))
    rules: list[dict[str, Any]] = []

    for tool_id in allowed_tool_ids:
        if tool_id not in catalog["tool_ids"]:
            continue
        rules.append(
            {
                "name": f"allow_{tool_id}",
                "priority": 100,
                "match": {"tool_id": tool_id},
                "decision": "allow",
                "reason": "legacy_tool_policy_allowlist",
            }
        )

    resource_policy = normalized_spec["resource_access_policy"]
    grants = _safe_object(resource_policy.get("integration_grants"))
    for integration_id, grant in grants.items():
        grant_data = _safe_object(grant)
        if grant_data.get("enabled") is False:
            rules.append(
                {
                    "name": f"deny_{integration_id}_disabled",
                    "priority": 90,
                    "match": {"integration_id": integration_id},
                    "decision": "deny",
                    "reason": "legacy_integration_disabled",
                }
            )
            continue

        allow_actions = normalize_string_list(grant_data.get("allow_actions"))
        if allow_actions:
            rules.append(
                {
                    "name": f"allow_{integration_id}_actions",
                    "priority": 80,
                    "match": {"integration_id": integration_id, "action_id": allow_actions},
                    "decision": "allow",
                    "reason": "legacy_integration_allow_actions",
                }
            )

        deny_actions = normalize_string_list(grant_data.get("deny_actions"))
        if deny_actions:
            rules.append(
                {
                    "name": f"deny_{integration_id}_actions",
                    "priority": 85,
                    "match": {"integration_id": integration_id, "action_id": deny_actions},
                    "decision": "deny",
                    "reason": "legacy_integration_deny_actions",
                }
            )

        allowed_domains = normalize_string_list(grant_data.get("allowed_domains"))
        if allowed_domains:
            rules.append(
                {
                    "name": f"allow_{integration_id}_domains",
                    "priority": 70,
                    "match": {"integration_id": integration_id, "domain": allowed_domains},
                    "decision": "allow",
                    "reason": "legacy_allowed_domains",
                }
            )

        allowed_paths = normalize_string_list(grant_data.get("allowed_paths"))
        if allowed_paths:
            rules.append(
                {
                    "name": f"allow_{integration_id}_paths",
                    "priority": 70,
                    "match": {"integration_id": integration_id, "path": allowed_paths},
                    "decision": "allow",
                    "reason": "legacy_allowed_paths",
                }
            )

        if grant_data.get("allow_private_network") is True:
            rules.append(
                {
                    "name": f"allow_{integration_id}_private_network",
                    "priority": 70,
                    "match": {"integration_id": integration_id, "private_network": True},
                    "decision": "allow_with_preview",
                    "reason": "legacy_private_network_grant",
                }
            )

    autonomy_policy = normalized_spec["autonomy_policy"]
    defaults: dict[str, Any] = {}
    approval_mode = _trimmed(autonomy_policy.get("default_approval_mode")).lower()
    if approval_mode:
        defaults["default_approval_mode"] = approval_mode
    autonomy_tier = _trimmed(autonomy_policy.get("default_autonomy_tier")).lower()
    if autonomy_tier:
        defaults["default_autonomy_tier"] = autonomy_tier
    task_overrides = _safe_object(autonomy_policy.get("task_overrides"))
    if task_overrides:
        defaults["task_overrides"] = task_overrides

    return _compact_mapping(
        {
            "version": 1,
            "source": "compiled_legacy",
            "defaults": defaults,
            "rules": rules,
            "legacy_sources": [
                name
                for name, payload in (
                    ("tool_policy", normalized_spec["tool_policy"]),
                    ("autonomy_policy", autonomy_policy),
                    ("resource_access_policy", resource_policy),
                )
                if payload
            ],
            "catalog_snapshot": {
                "allowed_tool_ids": allowed_tool_ids,
                "available_core_tools": catalog["tool_ids"],
            },
        }
    )


def resolve_execution_policy(
    agent_spec: dict[str, Any],
    *,
    feature_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    explicit = normalize_execution_policy(_safe_object(agent_spec.get("execution_policy")))
    if explicit:
        return explicit
    return compile_legacy_execution_policy(agent_spec, feature_flags=feature_flags)


def _group_catalog_actions(actions: list[dict[str, Any]]) -> dict[str, Any]:
    by_integration: dict[str, dict[str, Any]] = {}
    by_access_level: dict[str, int] = {}
    by_transport: dict[str, int] = {}
    for item in actions:
        integration_id = str(item.get("integration_id") or "general").strip().lower()
        group = by_integration.setdefault(
            integration_id,
            {
                "integration_id": integration_id,
                "title": (
                    f"MCP {_humanize_label(integration_id.split(':', 1)[1])}"
                    if integration_id.startswith("mcp:") and ":" in integration_id
                    else _humanize_label(integration_id)
                ),
                "action_count": 0,
                "action_ids": [],
            },
        )
        action_id = str(item.get("action_id") or "").strip()
        if action_id:
            group["action_ids"].append(action_id)
        group["action_count"] += 1
        access_level = str(item.get("access_level") or "write").strip().lower()
        by_access_level[access_level] = by_access_level.get(access_level, 0) + 1
        transport = str(item.get("transport") or "internal").strip().lower()
        by_transport[transport] = by_transport.get(transport, 0) + 1
    for group in by_integration.values():
        group["action_ids"] = sorted(group["action_ids"])
    return {
        "by_integration": sorted(
            by_integration.values(),
            key=lambda item: (str(item["title"]), str(item["integration_id"])),
        ),
        "by_access_level": [{"access_level": key, "count": value} for key, value in sorted(by_access_level.items())],
        "by_transport": [{"transport": key, "count": value} for key, value in sorted(by_transport.items())],
    }


def build_policy_catalog(
    *,
    feature_flags: dict[str, bool] | None = None,
    mcp_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tools = resolve_feature_filtered_tools(feature_flags)
    integrations = [
        {
            "id": integration.id,
            "title": integration.title,
            "description": integration.description,
            "transport": integration.transport,
            "risk_class": integration.risk_class,
            "default_approval_mode": integration.default_approval_mode,
            "auth_modes": list(integration.auth_modes),
            "supports_persistence": integration.supports_persistence,
        }
        for integration in CORE_INTEGRATION_CATALOG.values()
    ]
    core_actions = _core_tool_action_entries(feature_flags=feature_flags)
    surface_actions = _grouped_surface_action_entries()
    extra_actions = [dict(item) for item in mcp_actions or [] if isinstance(item, dict)]
    combined_actions = []
    seen: set[tuple[str, str, str]] = set()
    for item in [*core_actions, *surface_actions, *extra_actions]:
        tool_id = str(item.get("tool_id") or "").strip()
        action_id = str(item.get("action_id") or "").strip()
        integration_id = str(item.get("integration_id") or "").strip()
        if not tool_id or not action_id or not integration_id:
            continue
        key = (tool_id, action_id, integration_id)
        if key in seen:
            continue
        seen.add(key)
        combined_actions.append(item)
    combined_actions.sort(key=lambda item: (str(item.get("integration_id") or ""), str(item.get("action_id") or "")))
    return {
        "version": 1,
        "decision_values": sorted(EXECUTION_POLICY_DECISIONS),
        "effect_tags": list(EXECUTION_POLICY_EFFECT_TAGS),
        "selector_keys": sorted(EXECUTION_POLICY_SELECTOR_KEYS),
        "tool_ids": [str(item["id"]) for item in tools],
        "core_tools": tools,
        "core_integrations": integrations,
        "actions": combined_actions,
        "action_groups": _group_catalog_actions(combined_actions),
        "approval_scope_templates": list(_ACTION_GROUPING_TEMPLATES),
    }


def _rule_matches(rule: dict[str, Any], envelope: dict[str, Any]) -> bool:
    match = _safe_object(rule.get("match"))
    if not match:
        return False

    for key, pattern in match.items():
        value = envelope.get(key)
        if value is None:
            return False
        if isinstance(pattern, list):
            if not any(_matches_value(item, value) for item in pattern):
                return False
            continue
        if not _matches_value(pattern, value):
            return False
    return True


def _matches_value(pattern: Any, value: Any) -> bool:
    normalized_pattern = _trimmed(pattern)
    if not normalized_pattern:
        return False
    if isinstance(value, list):
        return any(_matches_value(normalized_pattern, item) for item in value)
    if isinstance(value, bool):
        return str(value).lower() == normalized_pattern.lower()
    normalized_value = _trimmed(value).lower()
    candidate = normalized_pattern.lower()
    if candidate.startswith("^"):
        literal_prefix = candidate[1:].strip()
        if not literal_prefix:
            return False
        return normalized_value.startswith(literal_prefix)
    if "*" in candidate or "?" in candidate:
        return fnmatch(normalized_value, candidate)
    return normalized_value == candidate


def _normalize_envelope(envelope: dict[str, Any] | None) -> dict[str, Any]:
    raw = _safe_object(envelope)
    normalized: dict[str, Any] = {}
    for key in EXECUTION_POLICY_SELECTOR_KEYS:
        if key not in raw:
            continue
        value = raw.get(key)
        normalized[key] = _normalize_selector_value(value, key=key)
    if "tool_id" in raw:
        normalized["tool_id"] = _trimmed(raw.get("tool_id"))
    if "integration_id" in raw:
        normalized["integration_id"] = _trimmed(raw.get("integration_id"))
    if "action_id" in raw:
        normalized["action_id"] = _trimmed(raw.get("action_id"))
    if "server_key" in raw:
        normalized["server_key"] = _trimmed(raw.get("server_key"))
    if "access_level" in raw:
        normalized["access_level"] = _trimmed(raw.get("access_level")).lower()
    if "risk_class" in raw:
        normalized["risk_class"] = _trimmed(raw.get("risk_class")).lower()
    if "task_kind" in raw:
        normalized["task_kind"] = _trimmed(raw.get("task_kind")).lower()
    if "domain" in raw:
        normalized["domain"] = _trimmed(raw.get("domain")).lower()
    if "path" in raw:
        normalized["path"] = _trimmed(raw.get("path"))
    if "db_env" in raw:
        normalized["db_env"] = _trimmed(raw.get("db_env")).lower()
    if "transport" in raw:
        normalized["transport"] = _trimmed(raw.get("transport")).lower()
    if "confidence_score" in raw:
        confidence_score = raw.get("confidence_score")
        if confidence_score is not None:
            with contextlib.suppress(TypeError, ValueError):
                normalized["confidence_score"] = float(confidence_score)
    for key in ("private_network", "uses_secrets", "bulk_operation", "external_side_effect"):
        if key in raw:
            parsed = _as_bool(raw.get(key))
            if parsed is not None:
                normalized[key] = parsed
    return normalized


def _resolve_catalog_action_payload(
    payload: dict[str, Any],
    *,
    catalog: dict[str, Any] | None,
) -> dict[str, Any]:
    raw = dict(_safe_object(payload))
    base_payload = dict(_safe_object(raw.get("envelope") or raw.get("action")))
    if base_payload:
        base_payload.update({key: value for key, value in raw.items() if key not in {"action", "envelope"}})
        raw = base_payload

    action_id = _trimmed(raw.get("action_id"))
    if not action_id:
        return raw

    actions = [item for item in _safe_list(_safe_object(catalog).get("actions")) if isinstance(item, dict)]
    tool_id = _trimmed(raw.get("tool_id"))
    integration_id = _trimmed(raw.get("integration_id"))
    server_key = _trimmed(raw.get("server_key"))
    matches = [
        item
        for item in actions
        if _trimmed(item.get("action_id")).lower() == action_id.lower()
        and (
            not tool_id
            or _trimmed(item.get("tool_id")).lower() == tool_id.lower()
            or _trimmed(item.get("tool_id")).lower().endswith(tool_id.lower())
        )
        and (
            not integration_id
            or _trimmed(item.get("integration_id")).lower() == integration_id.lower()
            or _trimmed(item.get("integration_id")).lower().endswith(integration_id.lower())
        )
        and (not server_key or _trimmed(item.get("server_key")).lower() == server_key.lower())
    ]
    if not matches:
        matches = [item for item in actions if _trimmed(item.get("action_id")).lower() == action_id.lower()]
    if len(matches) != 1:
        return raw
    selected = dict(matches[0])
    merged = {
        **selected,
        **{key: value for key, value in raw.items() if key not in {"action", "envelope"}},
    }
    merged.setdefault("tool_id", selected.get("tool_id"))
    merged.setdefault("integration_id", selected.get("integration_id"))
    merged.setdefault("resource_method", selected.get("resource_method"))
    merged.setdefault("transport", selected.get("transport"))
    merged.setdefault("access_level", selected.get("access_level"))
    merged.setdefault("risk_class", selected.get("risk_class"))
    merged.setdefault("effect_tags", selected.get("effect_tags"))
    merged.setdefault("server_key", selected.get("server_key"))
    return merged


def evaluate_execution_policy(
    policy: dict[str, Any] | None,
    envelope: dict[str, Any] | None,
    *,
    policy_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_policy = normalize_execution_policy(policy)
    catalog = policy_catalog or build_policy_catalog()
    resolved_input = _resolve_catalog_action_payload(_safe_object(envelope), catalog=catalog)
    effective_envelope = _normalize_envelope(resolved_input)

    tool_id = _trimmed(effective_envelope.get("tool_id"))
    if not tool_id:
        if _trimmed(resolved_input.get("action_id")):
            return _decision_payload(
                decision="deny",
                reason_code="unknown_action",
                rule_id=None,
                envelope=effective_envelope,
                policy=resolved_policy,
            )
        return _decision_payload(
            decision="deny",
            reason_code="missing_tool_id",
            rule_id=None,
            envelope=effective_envelope,
            policy=resolved_policy,
        )

    catalog_tool_ids = set(catalog.get("tool_ids") or [])
    if tool_id not in catalog_tool_ids and not str(effective_envelope.get("integration_id") or "").strip():
        return _decision_payload(
            decision="deny",
            reason_code="unknown_action",
            rule_id=None,
            envelope=effective_envelope,
            policy=resolved_policy,
        )

    matched_rule: dict[str, Any] | None = None
    for rule in sorted(
        resolved_policy.get("rules", []),
        key=lambda item: int(item.get("priority", 0) or 0),
        reverse=True,
    ):
        if not isinstance(rule, dict):
            continue
        if _rule_matches(rule, effective_envelope):
            matched_rule = rule
            break

    if matched_rule is not None:
        decision = _trimmed(matched_rule.get("decision")).lower() or "require_approval"
        if decision not in EXECUTION_POLICY_DECISIONS:
            decision = "require_approval"
        effect_tags = set(normalize_string_list(effective_envelope.get("effect_tags")))
        access_level = _trimmed(effective_envelope.get("access_level")).lower()
        if decision == "allow" and access_level != "read" and effect_tags & _PREVIEW_EFFECT_TAGS:
            decision = "allow_with_preview"
        elif decision == "allow" and access_level != "read" and effect_tags & _ALWAYS_APPROVAL_EFFECT_TAGS:
            decision = "require_approval"
        reason_code = _trimmed(matched_rule.get("reason"))
        if not reason_code:
            if decision == "allow_with_preview":
                reason_code = "preview_required"
            elif decision == "require_approval":
                reason_code = "human_factor_required"
            else:
                reason_code = "matched_rule"
        return _decision_payload(
            decision=decision,
            reason_code=reason_code,
            rule_id=_trimmed(matched_rule.get("name")) or None,
            envelope=effective_envelope,
            policy=resolved_policy,
            matched_selector=matched_rule.get("match"),
            approval_scope=_approval_scope(matched_rule, effective_envelope, decision),
            preview_text=_build_preview_text(
                effective_envelope,
                decision=decision,
                rule=matched_rule,
            ),
        )

    if bool(effective_envelope.get("private_network")):
        return _decision_payload(
            decision="deny",
            reason_code="private_network_not_granted",
            rule_id=None,
            envelope=effective_envelope,
            policy=resolved_policy,
        )

    effect_tags = set(normalize_string_list(effective_envelope.get("effect_tags")))
    access_level = _trimmed(effective_envelope.get("access_level")).lower()
    destructive_or_admin = access_level in {"destructive", "admin"} or bool(
        effect_tags & {"credential_access", "identity_admin"}
    )
    high_risk = bool(
        effect_tags
        & {
            "external_communication",
            "sharing_or_permissions",
            "destructive_change",
            "bulk_write",
            "browser_state_mutation",
            "package_or_plugin_install",
            "delegation",
            "mcp_write",
        }
    )

    if destructive_or_admin:
        return _decision_payload(
            decision="require_approval",
            reason_code="high_risk_default",
            rule_id=None,
            envelope=effective_envelope,
            policy=resolved_policy,
            approval_scope=_approval_scope(
                {"approval_scope_kind": "tool_call", "approval_ttl_seconds": 300},
                effective_envelope,
                "require_approval",
            ),
            preview_text=_build_preview_text(
                effective_envelope,
                decision="require_approval",
            ),
        )

    if high_risk or access_level == "write":
        return _decision_payload(
            decision="allow_with_preview",
            reason_code="preview_required_default",
            rule_id=None,
            envelope=effective_envelope,
            policy=resolved_policy,
            approval_scope=_approval_scope(
                {"approval_scope_kind": "tool_call", "approval_ttl_seconds": 300},
                effective_envelope,
                "allow_with_preview",
            ),
            preview_text=_build_preview_text(
                effective_envelope,
                decision="allow_with_preview",
            ),
        )

    return _decision_payload(
        decision="allow",
        reason_code="safe_read_default",
        rule_id=None,
        envelope=effective_envelope,
        policy=resolved_policy,
    )


def _approval_scope(
    rule: dict[str, Any],
    envelope: dict[str, Any],
    decision: str,
) -> dict[str, Any] | None:
    scope_kind = _trimmed(rule.get("approval_scope_kind")).lower() or (
        "tool_call" if decision in {"allow_with_preview", "require_approval"} else ""
    )
    ttl = _as_int(rule.get("approval_ttl_seconds"))
    if ttl is None and decision in {"allow_with_preview", "require_approval"}:
        ttl = 300
    if not scope_kind and ttl is None:
        return None
    payload: dict[str, Any] = {
        "kind": scope_kind or "tool_call",
        "ttl_seconds": ttl or 300,
        "fingerprint": {
            "tool_id": envelope.get("tool_id"),
            "integration_id": envelope.get("integration_id"),
            "action_id": envelope.get("action_id"),
            "server_key": envelope.get("server_key"),
            "path": envelope.get("path"),
            "domain": envelope.get("domain"),
            "db_env": envelope.get("db_env"),
        },
    }
    return _compact_mapping(payload)


def _preview_fields(
    rule: dict[str, Any] | None,
    envelope: dict[str, Any],
    decision: str,
) -> tuple[str, ...]:
    if rule:
        explicit = tuple(normalize_string_list(rule.get("preview_fields")))
        if explicit:
            return explicit
    if decision not in {"allow_with_preview", "require_approval"}:
        return ()

    ordered = (
        "tool_id",
        "integration_id",
        "action_id",
        "access_level",
        "risk_class",
        "resource_method",
        "server_key",
        "domain",
        "path",
        "db_env",
        "effect_tags",
        "private_network",
        "uses_secrets",
        "bulk_operation",
        "external_side_effect",
    )
    selected: list[str] = []
    for field in ordered:
        value = envelope.get(field)
        if value in (None, "", [], False):
            continue
        selected.append(field)
    return tuple(selected)


def _format_preview_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _build_preview_text(
    envelope: dict[str, Any],
    *,
    decision: str,
    rule: dict[str, Any] | None = None,
) -> str | None:
    fields = _preview_fields(rule, envelope, decision)
    if not fields:
        return None
    lines: list[str] = []
    for field in fields:
        value = envelope.get(field)
        if value in (None, "", [], False):
            continue
        lines.append(f"{_humanize_label(field)}: {_format_preview_value(value)}")
    if not lines:
        return None
    return "\n".join(lines)


def _decision_payload(
    *,
    decision: str,
    reason_code: str,
    rule_id: str | None,
    envelope: dict[str, Any],
    policy: dict[str, Any],
    matched_selector: dict[str, Any] | None = None,
    approval_scope: dict[str, Any] | None = None,
    preview_text: str | None = None,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "reason_code": reason_code,
        "rule_id": rule_id,
        "matched_selector": matched_selector,
        "audit_payload": {
            "envelope": envelope,
            "policy_source": policy.get("source") or "execution_policy",
            "decision": decision,
            "reason_code": reason_code,
        },
        "approval_scope": approval_scope,
        "preview_text": preview_text,
        "policy": policy,
    }
