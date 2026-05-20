"""Canonical Phase 2 MCP risk taxonomy and fail-closed evaluation helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from koda.services.mcp_client import McpToolAnnotations, McpToolDefinition

McpRiskClass = Literal[
    "read_context",
    "low_risk_write",
    "network_write",
    "destructive_write",
    "secret_access",
    "code_execution",
    "unknown",
]
McpRiskDecisionKind = Literal["allow", "allow_with_preview", "require_approval"]

MCP_RISK_TAXONOMY_VERSION = "mcp_risk.v1"
MCP_RISK_CLASSES: tuple[McpRiskClass, ...] = (
    "read_context",
    "low_risk_write",
    "network_write",
    "destructive_write",
    "secret_access",
    "code_execution",
    "unknown",
)
HIGH_RISK_MCP_CLASSES: frozenset[McpRiskClass] = frozenset(
    {
        "network_write",
        "destructive_write",
        "secret_access",
        "code_execution",
        "unknown",
    }
)

_RISK_RANK: dict[McpRiskClass, int] = {
    "read_context": 0,
    "low_risk_write": 10,
    "network_write": 20,
    "destructive_write": 30,
    "secret_access": 40,
    "code_execution": 40,
    "unknown": 100,
}
_RISK_ALIASES: dict[str, McpRiskClass] = {
    "read": "read_context",
    "readonly": "read_context",
    "read_only": "read_context",
    "read_context": "read_context",
    "context_read": "read_context",
    "safe_read": "read_context",
    "write": "low_risk_write",
    "local_write": "low_risk_write",
    "low_risk": "low_risk_write",
    "low_risk_write": "low_risk_write",
    "network": "network_write",
    "external_write": "network_write",
    "network_write": "network_write",
    "remote_write": "network_write",
    "destructive": "destructive_write",
    "destructive_write": "destructive_write",
    "delete": "destructive_write",
    "secret": "secret_access",
    "secrets": "secret_access",
    "secret_access": "secret_access",
    "credential_access": "secret_access",
    "credentials": "secret_access",
    "code": "code_execution",
    "code_execution": "code_execution",
    "command_execution": "code_execution",
    "shell": "code_execution",
    "unknown": "unknown",
    "": "unknown",
}
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_READ_KEYWORDS = frozenset(
    {
        "describe",
        "fetch",
        "find",
        "get",
        "inspect",
        "list",
        "query",
        "read",
        "retrieve",
        "search",
        "show",
    }
)
_LOW_WRITE_KEYWORDS = frozenset(
    {
        "add",
        "append",
        "create",
        "edit",
        "insert",
        "patch",
        "save",
        "set",
        "sync",
        "update",
        "upsert",
        "write",
    }
)
_NETWORK_WRITE_KEYWORDS = frozenset(
    {
        "broadcast",
        "call",
        "comment",
        "email",
        "http",
        "message",
        "notify",
        "post",
        "publish",
        "request",
        "send",
        "share",
        "slack",
        "sms",
        "upload",
        "webhook",
    }
)
_DESTRUCTIVE_KEYWORDS = frozenset(
    {
        "archive",
        "ban",
        "close",
        "delete",
        "destroy",
        "disable",
        "drop",
        "erase",
        "kill",
        "purge",
        "remove",
        "reset",
        "revoke",
        "terminate",
        "truncate",
        "wipe",
    }
)
_SECRET_KEYWORDS = frozenset(
    {
        "api_key",
        "auth",
        "credential",
        "credentials",
        "env",
        "keychain",
        "oauth",
        "password",
        "private_key",
        "secret",
        "token",
    }
)
_CODE_KEYWORDS = frozenset(
    {
        "bash",
        "code",
        "command",
        "exec",
        "execute",
        "eval",
        "javascript",
        "node",
        "python",
        "run",
        "script",
        "shell",
        "subprocess",
    }
)


@dataclass(frozen=True, slots=True)
class McpRiskAssessment:
    """Normalized governance result for one MCP capability."""

    risk_class: McpRiskClass
    reasons: tuple[str, ...] = ()
    annotation_risk_class: McpRiskClass = "unknown"
    keyword_risk_class: McpRiskClass = "unknown"
    declared_risk_class: McpRiskClass | None = None
    evidence: tuple[str, ...] = ()

    @property
    def is_high_risk(self) -> bool:
        return self.risk_class in HIGH_RISK_MCP_CLASSES

    @property
    def is_unknown(self) -> bool:
        return self.risk_class == "unknown"

    @property
    def requires_approval_first(self) -> bool:
        return self.risk_class in HIGH_RISK_MCP_CLASSES

    def to_payload(self) -> dict[str, Any]:
        return {
            "risk_class": self.risk_class,
            "reasons": list(self.reasons),
            "annotation_risk_class": self.annotation_risk_class,
            "keyword_risk_class": self.keyword_risk_class,
            "declared_risk_class": self.declared_risk_class,
            "evidence": list(self.evidence),
            "requires_approval_first": self.requires_approval_first,
        }


@dataclass(frozen=True, slots=True)
class McpRiskDecision:
    """Fail-closed execution decision derived from an MCP risk assessment."""

    decision: McpRiskDecisionKind
    allowed_to_execute: bool
    requires_approval: bool
    reason_code: str
    risk_class: McpRiskClass
    reasons: tuple[str, ...] = field(default_factory=tuple)


def normalize_mcp_risk_class(value: Any) -> McpRiskClass:
    """Normalize external risk labels into the canonical Phase 2 taxonomy."""

    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"_+", "_", normalized)
    return _RISK_ALIASES.get(normalized, "unknown")


def assess_mcp_tool_risk(
    tool: McpToolDefinition | Mapping[str, Any] | str,
    *,
    description: str | None = None,
    input_schema: Mapping[str, Any] | None = None,
    annotations: McpToolAnnotations | Mapping[str, Any] | None = None,
    declared_risk_class: Any = None,
) -> McpRiskAssessment:
    """Classify an MCP tool by annotations, explicit metadata, schema, and keywords.

    The helper is intentionally conservative: contradictory safe hints do not
    lower a higher-risk signal, and missing evidence resolves to ``unknown``.
    """

    name, resolved_description, resolved_schema, resolved_annotations, resolved_declared = _coerce_tool_inputs(
        tool,
        description=description,
        input_schema=input_schema,
        annotations=annotations,
        declared_risk_class=declared_risk_class,
    )
    reasons: list[str] = []
    evidence: list[str] = []
    candidates: list[McpRiskClass] = []

    declared_present = resolved_declared is not None
    declared_risk = normalize_mcp_risk_class(resolved_declared) if declared_present else None
    if declared_present:
        candidates.append(declared_risk or "unknown")
        reasons.append("declared_risk_class")
        evidence.append(f"declared:{declared_risk}")
        if declared_risk == "unknown" and str(resolved_declared or "").strip():
            reasons.append("unknown_declared_risk_class")

    annotation_risk, annotation_reasons = _risk_from_annotations(resolved_annotations)
    if annotation_reasons:
        candidates.append(annotation_risk)
        reasons.extend(annotation_reasons)
        evidence.append(f"annotations:{annotation_risk}")

    keyword_risk, keyword_reasons, keyword_evidence = _risk_from_keywords_and_schema(
        name,
        resolved_description,
        resolved_schema,
    )
    if keyword_reasons:
        candidates.append(keyword_risk)
        reasons.extend(keyword_reasons)
        evidence.extend(keyword_evidence)

    if annotation_risk == "read_context" and keyword_risk in HIGH_RISK_MCP_CLASSES - {"unknown"}:
        reasons.append("annotation_keyword_conflict")
    if declared_risk == "read_context" and keyword_risk in HIGH_RISK_MCP_CLASSES - {"unknown"}:
        reasons.append("declared_keyword_conflict")

    risk_class: McpRiskClass
    if declared_risk == "unknown" and str(resolved_declared or "").strip():
        risk_class = "unknown"
    else:
        risk_class = _highest_risk(candidates)
    if risk_class == "unknown" and not reasons:
        reasons.append("unknown_risk")
    return McpRiskAssessment(
        risk_class=risk_class,
        reasons=_dedupe(reasons),
        annotation_risk_class=annotation_risk,
        keyword_risk_class=keyword_risk,
        declared_risk_class=declared_risk,
        evidence=_dedupe(evidence),
    )


def evaluate_mcp_risk(
    assessment: McpRiskAssessment,
    *,
    approval_granted: bool = False,
    allow_low_risk_write_without_preview: bool = False,
) -> McpRiskDecision:
    """Return the execution posture for one MCP risk assessment.

    High-risk and unknown classes are fail-closed: they never produce an
    executable ``allow`` decision unless an upstream approval grant is present.
    """

    risk_class = assessment.risk_class
    if risk_class == "read_context":
        return McpRiskDecision(
            decision="allow",
            allowed_to_execute=True,
            requires_approval=False,
            reason_code="read_context_allowed",
            risk_class=risk_class,
            reasons=assessment.reasons,
        )
    if approval_granted:
        return McpRiskDecision(
            decision="allow",
            allowed_to_execute=True,
            requires_approval=False,
            reason_code="approval_grant",
            risk_class=risk_class,
            reasons=assessment.reasons,
        )
    if risk_class == "low_risk_write":
        decision: McpRiskDecisionKind = "allow" if allow_low_risk_write_without_preview else "allow_with_preview"
        return McpRiskDecision(
            decision=decision,
            allowed_to_execute=decision == "allow",
            requires_approval=decision != "allow",
            reason_code="low_risk_write_preview_required" if decision != "allow" else "low_risk_write_allowed",
            risk_class=risk_class,
            reasons=assessment.reasons,
        )
    return McpRiskDecision(
        decision="require_approval",
        allowed_to_execute=False,
        requires_approval=True,
        reason_code="unknown_risk_fail_closed" if risk_class == "unknown" else f"{risk_class}_approval_required",
        risk_class=risk_class,
        reasons=assessment.reasons,
    )


def _coerce_tool_inputs(
    tool: McpToolDefinition | Mapping[str, Any] | str,
    *,
    description: str | None,
    input_schema: Mapping[str, Any] | None,
    annotations: McpToolAnnotations | Mapping[str, Any] | None,
    declared_risk_class: Any,
) -> tuple[str, str | None, Mapping[str, Any] | None, McpToolAnnotations | Mapping[str, Any] | None, Any]:
    if isinstance(tool, McpToolDefinition):
        return (
            tool.name,
            description if description is not None else tool.description,
            input_schema if input_schema is not None else tool.input_schema,
            annotations if annotations is not None else tool.annotations,
            declared_risk_class,
        )
    if isinstance(tool, Mapping):
        return (
            str(tool.get("name") or tool.get("tool_name") or ""),
            description if description is not None else _optional_string(tool.get("description")),
            input_schema if input_schema is not None else _optional_mapping(tool.get("input_schema")),
            annotations if annotations is not None else _optional_mapping(tool.get("annotations")),
            declared_risk_class
            if declared_risk_class is not None
            else tool.get("risk_class", tool.get("risk", tool.get("mcp_risk_class"))),
        )
    return str(tool), description, input_schema, annotations, declared_risk_class


def _risk_from_annotations(
    annotations: McpToolAnnotations | Mapping[str, Any] | None,
) -> tuple[McpRiskClass, list[str]]:
    if annotations is None:
        return "unknown", []
    read_only = _annotation_bool(annotations, "read_only_hint", "readOnlyHint")
    destructive = _annotation_bool(annotations, "destructive_hint", "destructiveHint")
    open_world = _annotation_bool(annotations, "open_world_hint", "openWorldHint")
    reasons: list[str] = []
    candidates: list[McpRiskClass] = []

    if read_only is True:
        candidates.append("read_context")
        reasons.append("annotation_read_only")
    if destructive is True:
        candidates.append("destructive_write")
        reasons.append("annotation_destructive")
    if open_world is True and read_only is not True:
        candidates.append("network_write")
        reasons.append("annotation_open_world")
    if read_only is True and destructive is True:
        reasons.append("annotation_conflict")
    if candidates:
        return _highest_risk(candidates), reasons
    return "unknown", ["annotation_unclassified"]


def _risk_from_keywords_and_schema(
    name: str,
    description: str | None,
    input_schema: Mapping[str, Any] | None,
) -> tuple[McpRiskClass, list[str], list[str]]:
    text = " ".join(item for item in (name, description or "") if item)
    tokens = _tokens(text)
    schema_tokens = _schema_tokens(input_schema)
    all_tokens = tokens | schema_tokens
    candidates: list[McpRiskClass] = []
    reasons: list[str] = []
    evidence: list[str] = []

    for risk_class, keywords, reason in (
        ("code_execution", _CODE_KEYWORDS, "keyword_code_execution"),
        ("secret_access", _SECRET_KEYWORDS, "keyword_secret_access"),
        ("destructive_write", _DESTRUCTIVE_KEYWORDS, "keyword_destructive"),
        ("network_write", _NETWORK_WRITE_KEYWORDS, "keyword_network_write"),
        ("low_risk_write", _LOW_WRITE_KEYWORDS, "keyword_low_risk_write"),
        ("read_context", _READ_KEYWORDS, "keyword_read_context"),
    ):
        matched = sorted(all_tokens & keywords)
        if matched:
            candidates.append(cast(McpRiskClass, risk_class))
            reasons.append(reason)
            evidence.extend(f"{reason}:{item}" for item in matched)

    if not candidates:
        return "unknown", [], []
    return _highest_risk(candidates), reasons, evidence


def _tokens(text: str) -> set[str]:
    normalized = str(text or "").strip().lower()
    split_tokens = {part for part in _TOKEN_SPLIT_RE.split(normalized) if part}
    phrase_token = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    compound_tokens = {item for item in re.split(r"(?<=[a-z])(?=[A-Z])", str(text or "")) if item}
    lowered_compounds = {item.lower() for item in compound_tokens}
    return split_tokens | lowered_compounds | ({phrase_token} if phrase_token else set())


def _schema_tokens(input_schema: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(input_schema, Mapping):
        return set()
    tokens: set[str] = set()
    properties = input_schema.get("properties")
    if isinstance(properties, Mapping):
        for key, value in properties.items():
            tokens.update(_tokens(str(key)))
            if isinstance(value, Mapping):
                tokens.update(_tokens(str(value.get("description") or "")))
                enum_values = value.get("enum")
                if isinstance(enum_values, list):
                    for enum_item in enum_values:
                        tokens.update(_tokens(str(enum_item)))
    return tokens


def _highest_risk(candidates: list[McpRiskClass]) -> McpRiskClass:
    if not candidates:
        return "unknown"
    if "unknown" in candidates:
        known = [candidate for candidate in candidates if candidate != "unknown"]
        if not known:
            return "unknown"
        return max(known, key=lambda item: _RISK_RANK[item])
    return max(candidates, key=lambda item: _RISK_RANK[item])


def _annotation_bool(
    annotations: McpToolAnnotations | Mapping[str, Any],
    snake_key: str,
    camel_key: str,
) -> bool | None:
    if isinstance(annotations, McpToolAnnotations):
        return cast(bool | None, getattr(annotations, snake_key))
    value = annotations.get(snake_key, annotations.get(camel_key))
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _dedupe(values: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return tuple(result)
