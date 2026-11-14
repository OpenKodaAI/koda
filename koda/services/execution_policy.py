"""Central execution-policy gate for tools, MCP, and operator commands.

This module is the one execution-policy engine (ADR-002 AG-06, ADR-008 step 1).
The control plane delegates normalization and validation to it, and its
simulate route evaluates calls with :func:`evaluate_execution_policy`.

Rule semantics:

* ``normalize_execution_policy`` produces the canonical rule shape (``name``,
  ``priority``, ``match``, ``decision``). A rule's ``name`` is its audit
  ``rule_id``.
* Among the rules that match a call, the most restrictive decision wins
  (deny > require_approval > allow_with_preview > allow); ties go to the
  highest priority, then the lowest name.
* Selector values are fnmatch patterns (``*``, ``?``, ``[seq]``), compared
  case-insensitively. An ``effect_tags`` selector needs every listed pattern to
  match a tag.
* A ``path`` selector also covers everything below the path. Path rules are
  evaluated against the paths :func:`koda.agent_contract.resolve_action_paths`
  returns, exactly as the tool receives them: a ``file_*`` tool's ``path``,
  ``source`` and ``destination`` (both ends of a ``file_move``); the working
  directory for ``file_list``, ``file_search`` and ``file_grep`` without a
  ``path``; the ``path`` of an ``agent_*`` tool (``agent_set_workdir``); and the
  path an operator file command (``/write``, ``/edit``, ``/rm``, ``/mkdir``,
  ``/cat``) acts on, resolved under the work dir as the command resolves it. No
  other param is a path to these rules: an MCP tool's params,
  ``browser_upload``'s ``file_path``, ``plugin_install``'s ``path``, the ``path``
  of ``git_diff`` and ``git_log`` and ``job_create``'s ``work_dir`` are not
  evaluated, nor is anything a shell command touches, so a path rule does not
  keep those tools out of a directory (owner: AG-12).
* ``file_list``, ``file_search``, ``file_grep`` and both ends of ``file_move`` act
  on everything below their path (:data:`koda.agent_contract.SUBTREE_PATH_TOOLS`).
  For them a deny, require_approval or allow_with_preview path rule also matches
  when its path lies below a spelling of the call's path, so a listing, search,
  grep or move of an ancestor of the rule's directory does not step around it. A
  rule path with a wildcard segment counts when the call's path is at, above or
  below the segments before the wildcard, and one that starts with ``*`` always
  counts. An allow path rule must still cover the call's path itself.
* An absolute path is evaluated once for each of its spellings: lexically
  normalized (``.``, ``..`` and repeated ``/`` resolved) and as written, each
  compared with case and ignoring case. The as-written spelling is the one
  below a rule's path in a call such as ``<rule path>/../other``: when the
  rule's path is a symlink, the tool's realpath resolves the link before the
  ``..``. A path that is not absolute (``~``-prefixed, relative, the working
  directory, or with leading whitespace) cannot be placed, because the engine
  knows neither a working directory nor a HOME: every deny, require_approval
  and allow_with_preview path rule counts as matching it, and no allow path
  rule does. In the worker the dispatcher hands the engine each file tool's
  paths, and the working directory of a call without a ``path``, resolved
  under the work dir (``tool_dispatcher._file_tool_policy_params``), so there
  this applies to ``agent_set_workdir``'s path; the simulate route evaluates
  params as sent and applies it to every relative or ``~`` path. The decision is the most restrictive over all of
  these evaluations, counting the no-match fallback as an outcome, and the
  deciding rule is the highest-priority, then lowest-name rule with that
  decision that matched any of them. So no ``.``, ``..``, repeated ``/`` or
  other-case spelling, ``~`` or relative path, and neither end of a move, steps
  around a deny, require_approval or allow_with_preview path rule, and an allow
  path rule covers a call only when it covers each spelling of each of its
  paths. A call's path is not symlink-resolved here; in the worker a file
  tool's path arrives resolved by the safe-path resolver (M1-E4-T13). A deny,
  require_approval or allow_with_preview rule's path is also compared with its
  fixed part symlink-resolved (:func:`_resolved_rule_path`), so a restrictive
  rule written through a symlinked directory still decides a resolved call
  path; an allow rule's path is compared as written.
* A rule's ``path`` patterns are normalized as call paths are (repeated ``/``,
  ``.`` and ``..`` resolved). A pattern must be absolute or start with ``*``
  (any depth): ``~`` and relative patterns could never match a call, and
  ``..`` cannot follow a segment with a wildcard.
* Validation rejects every selector the engine cannot evaluate (an unknown key,
  an empty value, a mapping value, a non-boolean value on a boolean selector, a
  ``^regex`` pattern, a path pattern that cannot be normalized), a rule with no
  selectors or an unknown decision (which the normalizer would drop), and
  duplicate rule names. If such a selector is stored anyway, a deny rule skips
  it, so it matches more calls, and any other rule does not match.
"""

from __future__ import annotations

import os
import posixpath
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatchcase
from typing import Any

from koda.agent_contract import (
    CORE_TOOL_CATALOG,
    SUBTREE_PATH_TOOLS,
    ActionEnvelope,
    IntegrationGrantDecision,
    is_tool_allowed_by_secure_default,
    normalize_string_list,
    resolve_action_envelope,
    resolve_action_paths,
    resolve_allowed_tool_ids,
    resolve_feature_filtered_tools,
    resolve_integration_action,
)
from koda.config import (
    AGENT_EXECUTION_POLICY,
    AGENT_ID,
    AGENT_RESOURCE_ACCESS_POLICY,
    AGENT_TOOL_POLICY,
    BROWSER_FEATURES_ENABLED,
    BROWSER_NETWORK_INTERCEPTION_ENABLED,
    BROWSER_SESSION_PERSISTENCE_ENABLED,
    FILEOPS_ENABLED,
    GIT_ENABLED,
    INTER_AGENT_ENABLED,
    PLUGIN_SYSTEM_ENABLED,
    SHELL_ENABLED,
    SNAPSHOT_ENABLED,
    WEBHOOK_ENABLED,
    WORKFLOW_ENABLED,
)
from koda.knowledge.task_policy_defaults import default_execution_policy
from koda.knowledge.types import EffectiveExecutionPolicy

DecisionKind = str

EXECUTION_POLICY_DECISIONS = frozenset({"allow", "allow_with_preview", "require_approval", "deny"})
# Most restrictive first: among the rules that match a call, the first decision in this order wins.
_RULE_DECISION_ORDER: tuple[str, ...] = ("deny", "require_approval", "allow_with_preview", "allow")
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
_BOOLEAN_SELECTOR_KEYS = frozenset({"private_network", "uses_secrets", "bulk_operation", "external_side_effect"})
_BOOLEAN_PATTERNS = frozenset({"true", "false"})
_GLOB_CHARACTERS = frozenset("*?[")
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
        "browser_state_mutation",
        "delegation",
        "credential_access",
        "identity_admin",
        "private_network",
    }
)

_GRANT_REASON_MESSAGES: dict[str, str] = {
    "integration_disabled": "Blocked by integration policy: this integration is disabled.",
    "action_denied": "Blocked by integration policy: this action is explicitly denied.",
    "action_not_granted": "Blocked by integration policy: this action is outside the granted scope.",
    "explicit_integration_grant_required": "Blocked by integration policy: this action requires an explicit grant.",
    "read_only_policy": "Blocked by integration policy: this grant allows read-only actions only.",
    "domain_unknown": "Blocked by integration policy: the target domain is unknown for this action.",
    "domain_not_granted": "Blocked by integration policy: the target domain is outside the granted scope.",
    "private_network_not_granted": "Blocked by integration policy: private-network access is not granted.",
    "db_env_not_granted": "Blocked by integration policy: this database environment is outside the granted scope.",
    "path_not_granted": "Blocked by integration policy: this path is outside the granted scope.",
}


@dataclass(frozen=True, slots=True)
class ApprovalScope:
    kind: str = "once"
    ttl_seconds: int = 600
    max_uses: int = 1


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    decision: DecisionKind
    reason_code: str
    reason: str
    envelope: ActionEnvelope
    rule_id: str | None = None
    matched_selector: dict[str, Any] | None = None
    approval_scope: ApprovalScope | None = None
    audit_payload: dict[str, Any] = field(default_factory=dict)
    preview_text: str | None = None
    preview_fields: tuple[str, ...] = ()
    legacy_compiled: bool = False

    @property
    def requires_confirmation(self) -> bool:
        return self.decision in {"allow_with_preview", "require_approval"}

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready copy, as the control-plane simulate route returns it."""
        payload = asdict(self)
        payload["requires_confirmation"] = self.requires_confirmation
        return payload


def _configured_feature_flags() -> dict[str, bool]:
    return {
        "browser": BROWSER_FEATURES_ENABLED,
        "browser_network": BROWSER_NETWORK_INTERCEPTION_ENABLED,
        "browser_session": BROWSER_SESSION_PERSISTENCE_ENABLED,
        "snapshots": SNAPSHOT_ENABLED,
        "webhooks": WEBHOOK_ENABLED,
        "fileops": FILEOPS_ENABLED,
        "shell": SHELL_ENABLED,
        "git": GIT_ENABLED,
        "plugins": PLUGIN_SYSTEM_ENABLED,
        "workflows": WORKFLOW_ENABLED,
        "inter_agent": INTER_AGENT_ENABLED,
    }


# The koda.config settings behind each feature flag above, with their defaults. A flag is on when any
# of its settings is "true", as BROWSER_FEATURES_ENABLED is BROWSER_ENABLED or RUNTIME_BROWSER_LIVE_ENABLED.
_FEATURE_FLAG_SETTINGS: dict[str, tuple[tuple[str, str], ...]] = {
    "browser": (("BROWSER_ENABLED", "false"), ("RUNTIME_BROWSER_LIVE_ENABLED", "true")),
    "browser_network": (("BROWSER_NETWORK_INTERCEPTION_ENABLED", "false"),),
    "browser_session": (("BROWSER_SESSION_PERSISTENCE_ENABLED", "false"),),
    "snapshots": (("SNAPSHOT_ENABLED", "false"),),
    "webhooks": (("WEBHOOK_ENABLED", "false"),),
    "fileops": (("FILEOPS_ENABLED", "true"),),
    "shell": (("SHELL_ENABLED", "true"),),
    "git": (("GIT_ENABLED", "true"),),
    "plugins": (("PLUGIN_SYSTEM_ENABLED", "false"),),
    "workflows": (("WORKFLOW_ENABLED", "false"),),
    "inter_agent": (("INTER_AGENT_ENABLED", "false"),),
}
FEATURE_FLAG_ENV_KEYS = frozenset(key for settings in _FEATURE_FLAG_SETTINGS.values() for key, _default in settings)


def feature_flags_from_env(env: Mapping[str, str]) -> dict[str, bool]:
    """Return the feature flags koda.config computes in a process whose environment is ``env``.

    The control-plane simulator evaluates with the flags of the agent's worker, derived
    this way from the worker's environment, not with the flags of its own process.
    Each setting is read as koda.config's ``_env`` reads it: ``<AGENT_ID>_<KEY>`` when
    ``env`` has an ``AGENT_ID`` and that key, else ``<KEY>``, else the default.
    """
    agent_id = env.get("AGENT_ID")

    def setting(key: str, default: str) -> str:
        if agent_id and f"{agent_id}_{key}" in env:
            return str(env[f"{agent_id}_{key}"])
        return str(env.get(key, default))

    return {
        flag: any(setting(key, default).lower() == "true" for key, default in settings)
        for flag, settings in _FEATURE_FLAG_SETTINGS.items()
    }


def _safe_json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _grant_reason_message(reason_code: str | None) -> str:
    return _GRANT_REASON_MESSAGES.get(
        str(reason_code or "").strip().lower(),
        "Blocked by resource-access policy.",
    )


def _resolve_legacy_mcp_policy(tool_id: str, *, agent_id: str) -> str | None:
    parsed_tool = None
    try:
        from koda.services.mcp_bridge import parse_mcp_tool_id, resolve_mcp_tool_policy

        parsed_tool = parse_mcp_tool_id(tool_id)
        if parsed_tool is None:
            return None
        server_key, tool_name = parsed_tool
        from koda.control_plane.manager import get_control_plane_manager

        policy_map = {
            str(item.get("tool_name") or ""): str(item.get("policy") or "auto")
            for item in get_control_plane_manager().list_mcp_tool_policies(agent_id, server_key)
        }
        return resolve_mcp_tool_policy(policy_map, tool_name, None)
    except Exception:
        return None


def _resolve_mcp_risk_class(tool_id: str, *, agent_id: str) -> str:
    try:
        from koda.services.mcp_bridge import parse_mcp_tool_id
        from koda.services.mcp_risk import normalize_mcp_risk_class

        parsed_tool = parse_mcp_tool_id(tool_id)
        if parsed_tool is None:
            return "unknown"
        server_key, tool_name = parsed_tool
        from koda.control_plane.manager import get_control_plane_manager

        payload = get_control_plane_manager().get_mcp_connection_tools(agent_id, server_key)
        for tool in payload.get("tools") or []:
            if str(tool.get("name") or "") == tool_name:
                return normalize_mcp_risk_class(tool.get("risk_class") or tool.get("risk_level"))
    except Exception:
        return "unknown"
    return "unknown"


def _trimmed(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _compact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {}, ())}


def _normalize_path_pattern(pattern: str) -> tuple[str, str | None]:
    """Return a ``path`` selector pattern normalized as call paths are, and why it cannot be.

    Repeated ``/`` collapse and ``.`` and ``..`` segments resolve, as for a call's
    path (:func:`_normalized_call_path`), so the pattern compares with the
    normalized call path. A pattern must be absolute or start with ``*``, which
    matches at any depth: ``~`` is not expanded and a relative pattern is not
    resolved, so neither could match a call. A ``..`` segment cannot follow a
    segment with a wildcard, which can stand for several segments. A pattern that
    cannot be normalized comes back as written, with the reason.
    """
    if pattern.startswith("~"):
        return pattern, "~ is not expanded"
    if not pattern.startswith(("/", "*")):
        return pattern, "a relative path is not resolved"
    segments: list[str] = []
    for segment in pattern.split("/"):
        if segment in ("", "."):
            continue
        if segment != "..":
            segments.append(segment)
        elif segments and _GLOB_CHARACTERS & set(segments[-1]):
            return pattern, ".. cannot follow a segment with a wildcard"
        elif segments:
            segments.pop()
        # A ``..`` at the root stays at the root, as posixpath.normpath has it.
    normalized = "/".join(segments)
    return ("/" + normalized if pattern.startswith("/") else normalized), None


def _normalize_selector_value(value: Any, *, key: str) -> Any:
    if key == "path" and isinstance(value, str):
        return _normalize_path_pattern(value.strip())[0]
    if key == "effect_tags":
        return [item.lower() for item in normalize_string_list(value)]
    if key in _BOOLEAN_SELECTOR_KEYS:
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


def _rule_selectors(rule: dict[str, Any]) -> Any:
    """Return a rule's selectors: ``match``, or the runtime-legacy ``selectors`` when ``match`` is absent."""
    match = rule.get("match")
    return rule.get("selectors") if match is None else match


def _rule_name(index: int, rule: dict[str, Any]) -> str:
    """Return a rule's name (its audit ``rule_id``): ``name``, legacy ``id``/``rule_id``, or ``rule_<index>``."""
    return _trimmed(rule.get("name") or rule.get("id") or rule.get("rule_id")) or f"rule_{index}"


def _normalize_rule(index: int, rule: dict[str, Any]) -> dict[str, Any] | None:
    """Return one rule in the canonical shape, or ``None`` when it can never apply.

    The runtime-legacy keys ``id``/``rule_id``, ``selectors``, ``action`` and
    ``reason_code`` are migrated to ``name``, ``match``, ``decision`` and
    ``reason``; a canonical key that is present wins.
    """
    match: dict[str, Any] = {}
    for key, value in _safe_json_object(_rule_selectors(rule)).items():
        selector = _trimmed(key)
        if selector:
            match[selector] = _normalize_selector_value(value, key=selector)
    decision = _trimmed(rule.get("decision") or rule.get("action")).lower() or "require_approval"
    if not match or decision not in EXECUTION_POLICY_DECISIONS:
        return None

    normalized: dict[str, Any] = {
        "name": _rule_name(index, rule),
        "priority": _as_int(rule.get("priority")) or 0,
        "match": match,
        "decision": decision,
    }
    reason = _trimmed(rule.get("reason") or rule.get("reason_code"))
    if reason:
        normalized["reason"] = reason
    preview_fields = normalize_string_list(rule.get("preview_fields"))
    if preview_fields:
        normalized["preview_fields"] = preview_fields
    approval_scope_kind = _trimmed(rule.get("approval_scope_kind"))
    if approval_scope_kind:
        normalized["approval_scope_kind"] = approval_scope_kind
    approval_ttl_seconds = _as_int(rule.get("approval_ttl_seconds"))
    if approval_ttl_seconds is not None:
        normalized["approval_ttl_seconds"] = approval_ttl_seconds
    return _compact_mapping(normalized)


def _rule_order(rule: dict[str, Any]) -> tuple[int, str]:
    """Return a rule's place among rules with the same decision: highest priority, then lowest name."""
    return -int(rule.get("priority", 0) or 0), str(rule.get("name") or "")


def normalize_execution_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    """Return the canonical execution-policy document.

    This is the only normalizer: the control plane stores its output and the
    runtime evaluates it. Rules without selectors or with an unknown decision are
    dropped; the others are ordered by priority (highest first), then name.
    Other top-level keys are kept.
    """
    raw = dict(_safe_json_object(policy))
    if not raw:
        return {}

    raw["version"] = _as_int(raw.get("version")) or 1

    default_decision = _trimmed(raw.get("default_decision")).lower()
    if default_decision in EXECUTION_POLICY_DECISIONS:
        raw["default_decision"] = default_decision

    default_approval_mode = _trimmed(_safe_json_object(raw.get("defaults")).get("default_approval_mode")).lower()
    if default_approval_mode:
        defaults = dict(_safe_json_object(raw.get("defaults")))
        defaults["default_approval_mode"] = default_approval_mode
        raw["defaults"] = _compact_mapping(defaults)

    raw_rules = raw.get("rules")
    normalized_rules = [
        rule
        for index, item in enumerate(raw_rules if isinstance(raw_rules, list) else [])
        if isinstance(item, dict) and (rule := _normalize_rule(index, item)) is not None
    ]
    if normalized_rules:
        normalized_rules.sort(key=_rule_order)
        raw["rules"] = normalized_rules
    elif "rules" in raw:
        raw["rules"] = []

    source = _trimmed(raw.get("source")).lower()
    if source:
        raw["source"] = source

    return _compact_mapping(raw)


def _selector_errors(index: int, match: dict[str, Any]) -> list[str]:
    """Return an error for each selector of rule ``index`` that the engine cannot evaluate."""
    errors: list[str] = []
    for raw_key, value in match.items():
        key = _trimmed(raw_key)
        path = f"execution_policy.rules[{index}].match.{key or repr(raw_key)}"
        problem = _unevaluable_selector(key, value)
        if problem == "unknown_key":
            errors.append(
                f"{path} is not a supported selector. "
                f"Expected one of: {', '.join(sorted(EXECUTION_POLICY_SELECTOR_KEYS))}"
            )
        elif problem == "not_scalar":
            errors.append(f"{path} must be a pattern or a list of patterns, not a mapping or a nested list.")
        elif problem == "empty":
            errors.append(f"{path} is empty; a selector needs at least one pattern.")
        elif problem == "not_boolean":
            errors.append(f"{path} must be true or false.")
        elif problem == "regex":
            patterns = _normalize_match_values(_normalize_selector_value(value, key=key), fold_case=False)
            regex_patterns = [pattern for pattern in patterns if pattern.startswith("^")]
            errors.append(
                f"{path} uses a regular expression ({', '.join(regex_patterns)}); "
                "only fnmatch patterns (*, ?, [seq]) are supported."
            )
        elif problem == "path_pattern":
            patterns = _normalize_match_values(_normalize_selector_value(value, key=key), fold_case=False)
            problems = [
                f"{pattern} ({reason})" for pattern in patterns if (reason := _normalize_path_pattern(pattern)[1])
            ]
            errors.append(
                f"{path} cannot be normalized: {'; '.join(problems)}. "
                "A path pattern must be an absolute path, or start with * to match at any depth."
            )
    return errors


def validate_execution_policy(policy: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for an execution-policy document.

    Besides the document's shape, validation rejects every selector the engine
    cannot evaluate (an unknown key, an empty value, a mapping value, a
    non-boolean value on a boolean selector, a ``^regex`` pattern, a ``path``
    pattern that cannot be normalized, see :func:`_normalize_path_pattern`), every rule
    the normalizer would drop (no selectors, or an unknown ``decision`` or legacy
    ``action``), and duplicate rule names. A deny rule skips a selector it cannot
    evaluate, so such a rule would deny every call; a dropped rule would vanish
    without an error; and a rule's name is its audit ``rule_id``.
    """
    raw = _safe_json_object(policy)
    if not raw:
        return [], []

    errors: list[str] = []
    warnings: list[str] = []

    version = _as_int(raw.get("version"))
    if version is not None and version != 1:
        errors.append(f"execution_policy.version is invalid: {version}")

    rules = raw.get("rules")
    if rules is not None and not isinstance(rules, list):
        errors.append("execution_policy.rules must be a list.")
        return errors, warnings

    first_index_by_name: dict[str, int] = {}
    for index, rule in enumerate(rules or []):
        if not isinstance(rule, dict):
            errors.append(f"execution_policy.rules[{index}] must be a mapping.")
            continue

        name = _rule_name(index, rule)
        if name in first_index_by_name:
            errors.append(
                f"execution_policy.rules[{index}].name duplicates rules[{first_index_by_name[name]}]: {name}. "
                "Rule names are audit rule ids and must be unique."
            )
        else:
            first_index_by_name[name] = index

        # Read exactly as _normalize_rule reads it, legacy ``action`` included.
        decision = _trimmed(rule.get("decision") or rule.get("action")).lower()
        if decision and decision not in EXECUTION_POLICY_DECISIONS:
            decision_key = "decision" if rule.get("decision") else "action"
            errors.append(
                f"execution_policy.rules[{index}].{decision_key} is invalid: {decision}. "
                f"Expected one of: {', '.join(sorted(EXECUTION_POLICY_DECISIONS))}"
            )

        match = _rule_selectors(rule)
        if not isinstance(match, dict):
            errors.append(f"execution_policy.rules[{index}].match must be a mapping.")
            continue
        if not match:
            errors.append(f"execution_policy.rules[{index}].match is empty; a rule needs at least one selector.")
            continue

        errors.extend(_selector_errors(index, match))

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


def _configured_execution_policy(execution_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if execution_policy is not None:
        return normalize_execution_policy(execution_policy)
    if AGENT_EXECUTION_POLICY:
        return normalize_execution_policy(AGENT_EXECUTION_POLICY)
    return {}


def _configured_tool_policy(tool_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if tool_policy is not None:
        return dict(tool_policy)
    return dict(AGENT_TOOL_POLICY or {})


def _configured_resource_access_policy(resource_access_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if resource_access_policy is not None:
        return dict(resource_access_policy)
    return dict(AGENT_RESOURCE_ACCESS_POLICY or {})


def _configured_effective_policy(
    *,
    effective_policy: EffectiveExecutionPolicy | None,
    task_kind: str,
) -> EffectiveExecutionPolicy:
    if effective_policy is not None:
        return effective_policy
    return default_execution_policy(task_kind)


def _normalize_match_values(value: Any, *, fold_case: bool = True) -> tuple[str, ...]:
    """Return a selector's patterns, trimmed (and lower-cased unless ``fold_case`` is false), without empty ones."""
    items = value if isinstance(value, (list, tuple, set, frozenset)) else () if value is None else (value,)
    patterns = (str(item).strip() for item in items)
    return tuple(pattern.lower() if fold_case else pattern for pattern in patterns if pattern)


def _unevaluable_selector(key: str, value: Any) -> str | None:
    """Return why the engine cannot evaluate a selector, or ``None``.

    The reasons are ``unknown_key``; ``not_scalar`` (a mapping, or a list that
    holds a mapping or a list); ``empty``; ``not_boolean`` (a boolean selector
    whose value is not true or false); ``regex``; and ``path_pattern`` (a ``path``
    pattern that cannot be normalized). ``value`` is the selector's
    value as written or as normalized. Validation rejects each of these; the
    engine treats one that is stored anyway as described in :func:`_rule_matches`.
    """
    if key not in EXECUTION_POLICY_SELECTOR_KEYS:
        return "unknown_key"
    items = value if isinstance(value, (list, tuple, set, frozenset)) else (value,)
    if any(isinstance(item, (Mapping, list, tuple, set, frozenset)) for item in items):
        return "not_scalar"
    patterns = _normalize_match_values(_normalize_selector_value(value, key=key))
    if not patterns:
        return "empty"
    if key in _BOOLEAN_SELECTOR_KEYS and not set(patterns) <= _BOOLEAN_PATTERNS:
        return "not_boolean"
    if any(pattern.startswith("^") for pattern in patterns):
        return "regex"
    if key == "path" and any(_normalize_path_pattern(pattern)[1] for pattern in patterns):
        return "path_pattern"
    return None


def _value_matches(value: Any, patterns: tuple[str, ...]) -> bool:
    text = str(value).lower() if isinstance(value, bool) else str(value or "")
    normalized_value = text.strip().lower()
    return bool(normalized_value) and any(fnmatchcase(normalized_value, pattern) for pattern in patterns)


@dataclass(frozen=True, slots=True)
class _PathSpelling:
    """One spelling of a path a call acts on, as a ``path`` selector compares it.

    ``path`` is ``None`` for a path the engine cannot place (see :func:`_path_spellings`).
    """

    path: str | None
    ignore_case: bool = False


# A path that is not absolute: the worker's tools place it (``~`` expansion, the working directory).
_UNPLACED_PATH = _PathSpelling(None)


def _normalized_call_path(path: str) -> str:
    """Return an absolute path lexically normalized: repeated ``/``, ``.`` and ``..`` resolved."""
    return posixpath.normpath(re.sub(r"/{2,}", "/", path))


def _path_spellings(paths: tuple[str, ...]) -> tuple[_PathSpelling, ...]:
    """Return the spellings of a call's paths that the rule set is evaluated against.

    For each absolute path: the path lexically normalized (the file the tools act
    on, symlinks aside) and as written, each compared with case and ignoring case.
    A path that is not absolute after normalization (``~``-prefixed, relative, or
    with leading whitespace) cannot be placed here: the tools expand ``~`` with the
    worker's HOME and resolve a relative path against its working directory. It is
    one :data:`_UNPLACED_PATH` spelling, which every restrictive path rule matches
    and no allow path rule does (:func:`_path_matches`).
    """
    spellings: list[_PathSpelling] = []
    for written in paths:
        if not written.startswith("/"):
            spellings.append(_UNPLACED_PATH)
            continue
        normalized = _normalized_call_path(written)
        forms = (normalized,) if normalized == written else (normalized, written)
        spellings.extend(_PathSpelling(form, ignore_case) for ignore_case in (False, True) for form in forms)
    return tuple(dict.fromkeys(spellings))


def _path_pattern_matches(path: str, pattern: str) -> bool:
    """Return whether ``path`` is ``pattern`` or lies below it (fnmatch)."""
    base = pattern.rstrip("/") or "/"
    return fnmatchcase(path, base) or fnmatchcase(path, base.rstrip("/") + "/*")


def _within(path: str, root: str) -> bool:
    """Return whether ``path`` is ``root`` or below it, by whole path segment."""
    return path == root or root == "/" or path.startswith(root + "/")


def _path_pattern_reaches_below(path: str, pattern: str) -> bool:
    """Return whether ``pattern`` can match a path strictly below ``path``.

    ``pattern`` is normalized (:func:`_normalize_path_pattern`). Its fixed part is the
    segments before its first segment with a wildcard; every path it matches starts with
    that part. Without a wildcard, the pattern itself must lie strictly below ``path``.
    With one, a match can lie below ``path`` when the fixed part is ``path``, below it or
    above it: ``*`` also matches ``/``, so the wildcard can stand for several segments,
    and the check fails closed instead of reasoning about what it can match. A pattern
    that starts with ``*`` matches at any depth, so it can lie below any path.
    """
    if not pattern.startswith("/"):
        return True
    root = path.rstrip("/") or "/"
    fixed: list[str] = []
    for segment in pattern.strip("/").split("/"):
        if _GLOB_CHARACTERS & set(segment):
            prefix = "/" + "/".join(fixed)
            return _within(prefix, root) or _within(root, prefix)
        if segment:
            fixed.append(segment)
    prefix = "/" + "/".join(fixed)
    return prefix != root and _within(prefix, root)


def _resolved_rule_path(pattern: str) -> str:
    """Return a normalized absolute ``path`` pattern with its fixed part symlink-resolved.

    The fixed part is the segments before the first segment with a wildcard; the rest is
    kept as it is. The worker resolves a file tool's path before the policy sees it
    (``koda.services.tool_dispatcher._file_tool_policy_params``), so a rule written
    through a symlinked directory, such as ``/srv/app/config/secrets`` with ``/srv/app``
    linking to ``/srv/releases/v42``, is also compared in its resolved form. The
    filesystem is read at evaluation time; a pattern that cannot be resolved comes back
    as written.
    """
    segments = pattern.strip("/").split("/")
    fixed: list[str] = []
    for segment in segments:
        if _GLOB_CHARACTERS & set(segment):
            break
        fixed.append(segment)
    rest = segments[len(fixed) :]
    try:
        resolved = os.path.realpath("/" + "/".join(fixed))
    except (OSError, ValueError):
        return pattern
    return "/".join([resolved.rstrip("/"), *rest]) if rest else resolved


def _restrictive_rule_paths(patterns: tuple[str, ...]) -> tuple[str, ...]:
    """Return a restrictive rule's path patterns as written and with their fixed part resolved.

    Only deny, require_approval and allow_with_preview rules get the resolved form, which
    can only make a decision stricter. An allow rule is compared as written: the agent can
    repoint a link inside its work dir, and resolving an allow rule through it would widen
    the rule.
    """
    resolved = (_resolved_rule_path(pattern) for pattern in patterns if pattern.startswith("/"))
    return tuple(dict.fromkeys((*patterns, *resolved)))


def _path_matches(
    spelling: _PathSpelling | None,
    patterns: tuple[str, ...],
    *,
    decision: str,
    subtree: bool = False,
) -> bool:
    """Return whether one spelling of a call's path matches a ``path`` selector of a rule with ``decision``.

    A call without a path matches no path selector. A path the engine cannot place
    matches the path selector of every deny, require_approval and allow_with_preview
    rule, and of no allow rule, so it fails closed whatever the worker resolves it to.
    For a tool that acts on everything below its path (``subtree``, see
    :data:`koda.agent_contract.SUBTREE_PATH_TOOLS`), a deny, require_approval or
    allow_with_preview rule also matches when its path can lie below the call's path
    (:func:`_path_pattern_reaches_below`), so naming an ancestor of a restrictive rule's
    directory does not step around it; an allow rule must still cover the path itself.
    A restrictive rule's paths are also compared with their fixed part symlink-resolved
    (:func:`_restrictive_rule_paths`).
    """
    if spelling is None:
        return False
    if spelling.path is None:
        return decision != "allow"
    if decision != "allow":
        patterns = _restrictive_rule_paths(patterns)
    path = spelling.path
    if spelling.ignore_case:
        path, patterns = path.lower(), tuple(pattern.lower() for pattern in patterns)
    if any(_path_pattern_matches(path, pattern) for pattern in patterns):
        return True
    return subtree and decision != "allow" and any(_path_pattern_reaches_below(path, pattern) for pattern in patterns)


def _effect_tags_match(effect_tags: tuple[str, ...], patterns: tuple[str, ...]) -> bool:
    tags = {item.lower() for item in effect_tags}
    return all(any(fnmatchcase(tag, pattern) for tag in tags) for pattern in patterns)


def _selector_matches(
    key: str,
    value: Any,
    *,
    decision: str,
    envelope: ActionEnvelope,
    task_kind: str,
    path_spelling: _PathSpelling | None,
) -> bool:
    if key == "path":
        return _path_matches(
            path_spelling,
            _normalize_match_values(value, fold_case=False),
            decision=decision,
            subtree=envelope.tool_id in SUBTREE_PATH_TOOLS,
        )
    patterns = _normalize_match_values(value)
    if key == "effect_tags":
        return _effect_tags_match(envelope.effect_tags, patterns)
    if key == "task_kind":
        return _value_matches(task_kind, patterns)
    return _value_matches(getattr(envelope, key), patterns)


def _rule_matches(
    rule: dict[str, Any],
    *,
    envelope: ActionEnvelope,
    task_kind: str,
    path_spelling: _PathSpelling | None,
) -> bool:
    decision = str(rule.get("decision") or "")
    for key, value in _safe_json_object(rule.get("match")).items():
        if _unevaluable_selector(key, value) is not None:
            # The engine cannot evaluate this selector. A deny rule skips it
            # (matching more calls); any other rule does not match.
            if decision == "deny":
                continue
            return False
        if not _selector_matches(
            key, value, decision=decision, envelope=envelope, task_kind=task_kind, path_spelling=path_spelling
        ):
            return False
    return True


def _find_matching_rule(
    policy: dict[str, Any],
    *,
    envelope: ActionEnvelope,
    call_paths: tuple[str, ...],
    task_kind: str,
    fallback_decision: str,
) -> dict[str, Any] | None:
    """Return the rule that decides a call, or ``None`` when the no-match fallback decides it.

    The rule set is evaluated once per spelling of each path the call acts on
    (:func:`_path_spellings`), or once for a call without a path. The decision is
    the most restrictive outcome of those evaluations, where an evaluation that no
    rule matches yields ``fallback_decision``; whether a path rule matches one
    spelling and not another can therefore only make the outcome stricter. The
    deciding rule is then the highest-priority, then lowest-name rule with that
    decision that matched any spelling, and a rule wins over the fallback at an
    equal decision.
    """
    rules = policy.get("rules") or []
    matched: dict[int, dict[str, Any]] = {}
    fallback_reached = False
    for path_spelling in _path_spellings(call_paths) or (None,):
        matching = {
            index: rule
            for index, rule in enumerate(rules)
            if _rule_matches(rule, envelope=envelope, task_kind=task_kind, path_spelling=path_spelling)
        }
        fallback_reached = fallback_reached or not matching
        matched.update(matching)
    outcomes = {str(rule.get("decision")) for rule in matched.values()} | (
        {fallback_decision} if fallback_reached else set()
    )
    decision = next(item for item in _RULE_DECISION_ORDER if item in outcomes)
    deciding = [rule for rule in matched.values() if rule.get("decision") == decision]
    return min(deciding, key=_rule_order) if deciding else None


def _build_preview_text(envelope: ActionEnvelope, params: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    preview_fields: tuple[str, ...]
    if "external_communication" in envelope.effect_tags:
        preview_fields = ("to", "subject", "body")
    elif "sharing_or_permissions" in envelope.effect_tags:
        preview_fields = ("target", "email", "role")
    elif "destructive_change" in envelope.effect_tags:
        preview_fields = ("path", "id", "key", "url")
    elif "package_or_plugin_install" in envelope.effect_tags:
        preview_fields = ("name", "package", "version", "args")
    else:
        preview_fields = ("args", "path", "url")
    parts = [
        f"Tool: {envelope.tool_id}",
        f"Action: {envelope.integration_id}/{envelope.action_id}",
    ]
    for field_name in preview_fields:
        value = params.get(field_name)
        if value not in (None, "", [], {}):
            parts.append(f"{field_name}: {value}")
    if len(parts) <= 2:
        parts.append(f"Params: {params}")
    return "\n".join(parts), preview_fields


def _approval_scope_for(
    decision: str,
    *,
    envelope: ActionEnvelope,
    ttl_seconds: int | None = None,
) -> ApprovalScope | None:
    if decision not in {"allow_with_preview", "require_approval"}:
        return None
    allow_scope = (
        decision == "require_approval"
        and envelope.access_level == "write"
        and not envelope.external_side_effect
        and not envelope.bulk_operation
        and not (set(envelope.effect_tags) & (_PREVIEW_EFFECT_TAGS | _ALWAYS_APPROVAL_EFFECT_TAGS))
    )
    if allow_scope:
        return ApprovalScope(kind="scope", ttl_seconds=ttl_seconds or 900, max_uses=10)
    return ApprovalScope(kind="once", ttl_seconds=ttl_seconds or 600, max_uses=1)


def resolve_execution_policy_allowed_tool_ids(
    *,
    tool_policy: dict[str, Any] | None = None,
    execution_policy: dict[str, Any] | None = None,
    feature_flags: dict[str, bool] | None = None,
) -> list[str]:
    """Return the effective prompt/runtime tool allowlist for one agent.

    With execution-policy rules, the allowlist is the secure default plus every
    available tool that a non-deny rule can match: the rule's ``tool_id`` and
    ``integration_id`` patterns (fnmatch, as the evaluator applies them) match the
    tool's id and integration, and the rule has no selector the evaluator cannot
    evaluate. Other selectors depend on the call, so the evaluator decides them.
    """
    flags = feature_flags or _configured_feature_flags()
    available_tool_ids = {
        str(item["id"]) for item in resolve_feature_filtered_tools(flags) if bool(item.get("available"))
    }
    resolved_execution_policy = _configured_execution_policy(execution_policy)
    if resolved_execution_policy.get("rules"):
        allowed: set[str] = {tool_id for tool_id in available_tool_ids if is_tool_allowed_by_secure_default(tool_id)}
        integration_ids: dict[str, str] = {}

        def integration_of(tool_id: str) -> str:
            if tool_id not in integration_ids:
                integration_ids[tool_id] = resolve_integration_action(tool_id, {}).integration_id
            return integration_ids[tool_id]

        for rule in resolved_execution_policy.get("rules") or []:
            if str(rule.get("decision") or "").strip().lower() == "deny":
                continue
            match = _safe_json_object(rule.get("match"))
            if any(_unevaluable_selector(key, value) for key, value in match.items()):
                continue  # The evaluator never matches this rule.
            tool_patterns = _normalize_match_values(match.get("tool_id"))
            integration_patterns = _normalize_match_values(match.get("integration_id"))
            if not tool_patterns and not integration_patterns:
                continue
            allowed.update(
                tool_id
                for tool_id in available_tool_ids
                if (not tool_patterns or _value_matches(tool_id, tool_patterns))
                and (not integration_patterns or _value_matches(integration_of(tool_id), integration_patterns))
            )
        return sorted(allowed)
    return resolve_allowed_tool_ids(_configured_tool_policy(tool_policy), feature_flags=flags)


def _explicit_rule_decision(
    *,
    rule: dict[str, Any],
    envelope: ActionEnvelope,
    params: dict[str, Any],
) -> PolicyEvaluation:
    decision = str(rule.get("decision") or "deny")
    preview_text, preview_fields = _build_preview_text(envelope, params)
    approval_scope: ApprovalScope | None = None
    if decision in {"allow_with_preview", "require_approval"}:
        # A rule's approval is single-use unless the rule asks for a scope.
        scope_kind = _trimmed(rule.get("approval_scope_kind")).lower()
        if scope_kind not in {"once", "scope"}:
            scope_kind = "once"
        ttl_seconds = _as_int(rule.get("approval_ttl_seconds")) or (900 if scope_kind == "scope" else 600)
        approval_scope = ApprovalScope(
            kind=scope_kind,
            ttl_seconds=max(60, ttl_seconds),
            max_uses=10 if scope_kind == "scope" else 1,
        )
    return PolicyEvaluation(
        decision=decision,
        reason_code=str(rule.get("reason") or "rule_match") or "rule_match",
        reason=str(rule.get("reason") or "Matched execution-policy rule."),
        envelope=envelope,
        rule_id=str(rule.get("name") or ""),
        matched_selector=_safe_json_object(rule.get("match")),
        approval_scope=approval_scope,
        preview_text=preview_text if decision == "allow_with_preview" else None,
        preview_fields=tuple(rule.get("preview_fields") or preview_fields),
        audit_payload={"source": "execution_policy", "rule": rule},
    )


def _legacy_mcp_decision(
    *,
    legacy_mcp_policy: str | None,
    envelope: ActionEnvelope,
    params: dict[str, Any],
    agent_id: str,
) -> PolicyEvaluation | None:
    if not envelope.integration_id.startswith("mcp:"):
        return None
    normalized = str(legacy_mcp_policy or "always_ask").strip().lower() or "always_ask"
    if normalized == "blocked":
        return PolicyEvaluation(
            decision="deny",
            reason_code="mcp_blocked",
            reason="Blocked by legacy MCP tool policy.",
            envelope=envelope,
            approval_scope=None,
            audit_payload={"source": "legacy_mcp_policy", "policy": normalized},
            legacy_compiled=True,
        )
    from koda.services.mcp_risk import HIGH_RISK_MCP_CLASSES

    risk_class = _resolve_mcp_risk_class(envelope.tool_id, agent_id=agent_id)
    if normalized == "always_allow" and risk_class not in HIGH_RISK_MCP_CLASSES:
        return PolicyEvaluation(
            decision="allow",
            reason_code="mcp_always_allow",
            reason="Allowed by legacy MCP tool policy.",
            envelope=envelope,
            audit_payload={"source": "legacy_mcp_policy", "policy": normalized},
            legacy_compiled=True,
        )
    if normalized == "always_allow":
        preview_text, preview_fields = _build_preview_text(envelope, params)
        return PolicyEvaluation(
            decision="require_approval",
            reason_code="mcp_high_risk_requires_approval",
            reason="MCP risk taxonomy requires approval before this action can execute.",
            envelope=envelope,
            approval_scope=ApprovalScope(kind="scope", ttl_seconds=900, max_uses=10),
            preview_text=preview_text,
            preview_fields=preview_fields,
            audit_payload={"source": "mcp_risk_taxonomy", "legacy_policy": normalized, "risk_class": risk_class},
            legacy_compiled=True,
        )
    preview_text, preview_fields = _build_preview_text(envelope, params)
    return PolicyEvaluation(
        decision="allow_with_preview" if envelope.access_level != "read" else "require_approval",
        reason_code="mcp_requires_approval",
        reason="Legacy MCP policy requires human approval.",
        envelope=envelope,
        approval_scope=ApprovalScope(kind="scope", ttl_seconds=900, max_uses=10),
        preview_text=preview_text if envelope.access_level != "read" else None,
        preview_fields=preview_fields,
        audit_payload={"source": "legacy_mcp_policy", "policy": normalized},
        legacy_compiled=True,
    )


def _legacy_policy_decision(
    *,
    envelope: ActionEnvelope,
    params: dict[str, Any],
    grant_decision: IntegrationGrantDecision,
    effective_policy: EffectiveExecutionPolicy,
    tool_policy: dict[str, Any],
    feature_flags: dict[str, bool],
    legacy_mcp_policy: str | None,
    agent_id: str,
) -> PolicyEvaluation:
    mcp_decision = _legacy_mcp_decision(
        legacy_mcp_policy=(
            legacy_mcp_policy
            if legacy_mcp_policy is not None
            else _resolve_legacy_mcp_policy(envelope.tool_id, agent_id=agent_id)
        ),
        envelope=envelope,
        params=params,
        agent_id=agent_id,
    )
    if mcp_decision is not None:
        return mcp_decision

    allowed_tool_ids = set(resolve_allowed_tool_ids(tool_policy, feature_flags=feature_flags))
    tool_allowed = (
        envelope.tool_id in allowed_tool_ids
        or (envelope.tool_id not in CORE_TOOL_CATALOG and envelope.catalogued)
        or is_tool_allowed_by_secure_default(envelope.tool_id)
    )
    if not tool_allowed and not envelope.integration_id.startswith("mcp:"):
        return PolicyEvaluation(
            decision="deny",
            reason_code="tool_not_enabled",
            reason="Tool is outside the secure default tool subset for this agent.",
            envelope=envelope,
            audit_payload={"allowed_tool_ids": sorted(allowed_tool_ids)},
            legacy_compiled=True,
        )

    if not grant_decision.allowed:
        return PolicyEvaluation(
            decision="deny",
            reason_code=str(grant_decision.reason or "integration_policy"),
            reason=_grant_reason_message(str(grant_decision.reason or "integration_policy")),
            envelope=envelope,
            audit_payload={"grant_reason": grant_decision.reason},
            legacy_compiled=True,
        )

    if effective_policy.read_only and envelope.access_level != "read":
        return PolicyEvaluation(
            decision="deny",
            reason_code="read_only_policy",
            reason="The effective task policy is read-only.",
            envelope=envelope,
            legacy_compiled=True,
        )

    if envelope.access_level == "read":
        return PolicyEvaluation(
            decision="allow",
            reason_code="secure_default_read",
            reason="Safe read allowed by the secure default baseline.",
            envelope=envelope,
            legacy_compiled=True,
        )

    preview_text, preview_fields = _build_preview_text(envelope, params)
    needs_preview = bool(set(envelope.effect_tags) & _PREVIEW_EFFECT_TAGS)
    low_risk_local_write = (
        envelope.access_level == "write"
        and not envelope.external_side_effect
        and not envelope.bulk_operation
        and not (
            set(envelope.effect_tags)
            & (
                _PREVIEW_EFFECT_TAGS
                | _ALWAYS_APPROVAL_EFFECT_TAGS
                | {"mcp_write", "external_communication", "sharing_or_permissions"}
            )
        )
    )
    if effective_policy.approval_mode == "guarded" and low_risk_local_write:
        return PolicyEvaluation(
            decision="allow",
            reason_code="guarded_low_risk_write",
            reason="Low-risk local write allowed by guarded legacy policy.",
            envelope=envelope,
            legacy_compiled=True,
        )

    decision = "allow_with_preview" if needs_preview else "require_approval"
    return PolicyEvaluation(
        decision=decision,
        reason_code="legacy_human_factor",
        reason="Legacy autonomy policy requires explicit human approval.",
        envelope=envelope,
        approval_scope=_approval_scope_for(decision, envelope=envelope),
        preview_text=preview_text if decision == "allow_with_preview" else None,
        preview_fields=preview_fields,
        legacy_compiled=True,
    )


def _apply_overlays(
    evaluation: PolicyEvaluation,
    *,
    grant_decision: IntegrationGrantDecision,
    effective_policy: EffectiveExecutionPolicy,
    confidence_report: dict[str, Any] | None,
    approval_grant: dict[str, Any] | None,
    params: dict[str, Any],
) -> PolicyEvaluation:
    envelope = evaluation.envelope
    if not grant_decision.allowed:
        return PolicyEvaluation(
            decision="deny",
            reason_code=str(grant_decision.reason or "integration_policy"),
            reason=_grant_reason_message(str(grant_decision.reason or "integration_policy")),
            envelope=envelope,
            audit_payload={"grant_reason": grant_decision.reason},
            legacy_compiled=evaluation.legacy_compiled,
        )

    if evaluation.decision == "allow" and effective_policy.read_only and envelope.access_level != "read":
        return PolicyEvaluation(
            decision="deny",
            reason_code="read_only_policy",
            reason="The effective task policy is read-only.",
            envelope=envelope,
            legacy_compiled=evaluation.legacy_compiled,
        )

    if (
        evaluation.decision == "allow"
        and envelope.access_level != "read"
        and set(envelope.effect_tags) & _PREVIEW_EFFECT_TAGS
    ):
        preview_text, preview_fields = _build_preview_text(envelope, params)
        evaluation = PolicyEvaluation(
            decision="allow_with_preview",
            reason_code="preview_required",
            reason="This action class requires an explicit runtime preview before execution.",
            envelope=envelope,
            approval_scope=_approval_scope_for("allow_with_preview", envelope=envelope),
            preview_text=preview_text,
            preview_fields=preview_fields,
            audit_payload={"source": "preview_overlay"},
            legacy_compiled=evaluation.legacy_compiled,
        )

    if (
        evaluation.decision == "allow"
        and envelope.access_level != "read"
        and set(envelope.effect_tags) & _ALWAYS_APPROVAL_EFFECT_TAGS
    ):
        _preview_text, preview_fields = _build_preview_text(envelope, params)
        evaluation = PolicyEvaluation(
            decision="require_approval",
            reason_code="human_factor_required",
            reason="This action class requires explicit human approval before execution.",
            envelope=envelope,
            approval_scope=_approval_scope_for("require_approval", envelope=envelope),
            preview_fields=preview_fields,
            audit_payload={"source": "human_factor_overlay"},
            legacy_compiled=evaluation.legacy_compiled,
        )

    if evaluation.decision == "allow" and effective_policy.escalation_required and envelope.access_level != "read":
        preview_text, preview_fields = _build_preview_text(envelope, params)
        evaluation = PolicyEvaluation(
            decision="allow_with_preview" if set(envelope.effect_tags) & _PREVIEW_EFFECT_TAGS else "require_approval",
            reason_code="escalation_required",
            reason="This task kind requires human escalation before writes.",
            envelope=envelope,
            approval_scope=_approval_scope_for("require_approval", envelope=envelope),
            preview_text=preview_text if set(envelope.effect_tags) & _PREVIEW_EFFECT_TAGS else None,
            preview_fields=preview_fields,
            audit_payload={"source": "effective_policy"},
            legacy_compiled=evaluation.legacy_compiled,
        )

    if evaluation.decision == "allow" and confidence_report:
        blocked = bool(confidence_report.get("blocked"))
        requires_human_approval = bool(confidence_report.get("requires_human_approval"))
        if blocked:
            return PolicyEvaluation(
                decision="deny",
                reason_code="confidence_blocked",
                reason="Blocked by execution-confidence overlay.",
                envelope=envelope,
                audit_payload={"confidence": confidence_report},
                legacy_compiled=evaluation.legacy_compiled,
            )
        if requires_human_approval and envelope.access_level != "read":
            preview_text, preview_fields = _build_preview_text(envelope, params)
            decision = "allow_with_preview" if set(envelope.effect_tags) & _PREVIEW_EFFECT_TAGS else "require_approval"
            evaluation = PolicyEvaluation(
                decision=decision,
                reason_code="confidence_requires_human",
                reason="Confidence overlay requires human confirmation.",
                envelope=envelope,
                approval_scope=_approval_scope_for(decision, envelope=envelope),
                preview_text=preview_text if decision == "allow_with_preview" else None,
                preview_fields=preview_fields,
                audit_payload={"confidence": confidence_report},
                legacy_compiled=evaluation.legacy_compiled,
            )

    if approval_grant and evaluation.requires_confirmation:
        return PolicyEvaluation(
            decision="allow",
            reason_code="approval_grant",
            reason="Allowed by active scoped approval grant.",
            envelope=envelope,
            rule_id=str(approval_grant.get("grant_id") or ""),
            audit_payload={"grant": dict(approval_grant)},
            legacy_compiled=evaluation.legacy_compiled,
        )
    return evaluation


def evaluate_execution_policy(
    tool_id: str,
    params: dict[str, Any] | None,
    *,
    task_kind: str = "general",
    effective_policy: EffectiveExecutionPolicy | None = None,
    tool_policy: dict[str, Any] | None = None,
    resource_access_policy: dict[str, Any] | None = None,
    execution_policy: dict[str, Any] | None = None,
    confidence_report: dict[str, Any] | None = None,
    approval_grant: dict[str, Any] | None = None,
    legacy_mcp_policy: str | None = None,
    known_tool: bool = True,
    agent_id: str | None = None,
    feature_flags: dict[str, bool] | None = None,
) -> PolicyEvaluation:
    """Evaluate one tool/action through the central policy gate.

    ``agent_id`` names the agent whose control-plane rows (legacy MCP tool policy
    and MCP risk class) are consulted; it defaults to this worker's ``AGENT_ID``.
    ``feature_flags`` default to this process's (:func:`_configured_feature_flags`).
    The control-plane simulate route passes both to evaluate on an agent's behalf.
    """
    payload = params or {}
    resolved_agent_id = agent_id or AGENT_ID or "default"
    resolved_effective_policy = _configured_effective_policy(effective_policy=effective_policy, task_kind=task_kind)
    resolved_tool_policy = _configured_tool_policy(tool_policy)
    resolved_resource_policy = _configured_resource_access_policy(resource_access_policy)
    resolved_execution_policy = _configured_execution_policy(execution_policy)
    resolved_feature_flags = _configured_feature_flags() if feature_flags is None else dict(feature_flags)
    envelope, grant_decision = resolve_action_envelope(tool_id, payload, resolved_resource_policy)

    if not known_tool:
        return PolicyEvaluation(
            decision="deny",
            reason_code="unknown_action",
            reason="Unknown or uncatalogued action blocked by fail-closed policy.",
            envelope=envelope,
            audit_payload={"tool_id": tool_id, "agent_id": resolved_agent_id},
        )

    if resolved_execution_policy.get("rules"):
        safe_read = envelope.access_level == "read" and is_tool_allowed_by_secure_default(tool_id)
        matched_rule = _find_matching_rule(
            resolved_execution_policy,
            envelope=envelope,
            call_paths=resolve_action_paths(tool_id, payload),
            task_kind=task_kind,
            fallback_decision="allow" if safe_read else "deny",
        )
        if matched_rule is not None:
            base = _explicit_rule_decision(rule=matched_rule, envelope=envelope, params=payload)
        elif safe_read:
            base = PolicyEvaluation(
                decision="allow",
                reason_code="secure_default_read",
                reason="Safe read allowed by secure default.",
                envelope=envelope,
            )
        else:
            base = PolicyEvaluation(
                decision="deny",
                reason_code="secure_default_block",
                reason="No execution-policy rule matched a non-safe action.",
                envelope=envelope,
            )
    else:
        base = _legacy_policy_decision(
            envelope=envelope,
            params=payload,
            grant_decision=grant_decision,
            effective_policy=resolved_effective_policy,
            tool_policy=resolved_tool_policy,
            feature_flags=resolved_feature_flags,
            legacy_mcp_policy=legacy_mcp_policy,
            agent_id=resolved_agent_id,
        )

    return _apply_overlays(
        base,
        grant_decision=grant_decision,
        effective_policy=resolved_effective_policy,
        confidence_report=confidence_report,
        approval_grant=approval_grant,
        params=payload,
    )
