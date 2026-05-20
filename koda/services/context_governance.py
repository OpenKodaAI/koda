"""Context governance v1 helpers for bounded child runs.

The assembler works from prompt-budget metadata only. It never serializes the
compiled prompt or raw segment text, so child-run traces can explain what was
included or fenced without leaking the parent context.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

CONTEXT_GOVERNANCE_SCHEMA_VERSION = "context_governance.v1"

DEFAULT_CONTEXT_POLICY: dict[str, Any] = {
    "mode": "minimal",
    "allow_categories": ["base", "runtime_rules", "tool_contracts"],
    "deny_categories": ["secrets", "pending_approval"],
    "max_tokens": 1200,
    "redaction": "strict",
    "include_memory": False,
    "include_artifacts": False,
    "include_squad_context": False,
    "review_on_sensitive": True,
}

_SENSITIVE_CATEGORY_TOKENS = (
    "approval",
    "credential",
    "env",
    "mount",
    "secret",
    "token",
)
_MEMORY_CATEGORIES = {"memory", "authoritative_knowledge", "cache_hints", "supporting_knowledge", "scripts_assets"}
_ARTIFACT_CATEGORIES = {"artifact", "artifacts", "supporting_knowledge"}
_SQUAD_SEGMENT_IDS = {"squad_context"}


def _stable_id(value: Any, *, prefix: str = "ctx") -> str:
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    digest = hashlib.sha256(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{prefix}:{digest}"


def _list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_context_policy(value: Any | None) -> dict[str, Any]:
    """Return a strict, bounded `context_governance.v1` policy."""

    policy = dict(DEFAULT_CONTEXT_POLICY)
    if isinstance(value, Mapping):
        policy.update({str(key): item for key, item in value.items()})

    allow_categories = _list_strings(policy.get("allow_categories")) or list(DEFAULT_CONTEXT_POLICY["allow_categories"])
    deny_categories = _list_strings(policy.get("deny_categories")) or list(DEFAULT_CONTEXT_POLICY["deny_categories"])
    max_tokens = max(128, min(16_000, _int(policy.get("max_tokens"), int(DEFAULT_CONTEXT_POLICY["max_tokens"]))))

    return {
        "schema_version": CONTEXT_GOVERNANCE_SCHEMA_VERSION,
        "mode": str(policy.get("mode") or "minimal"),
        "allow_categories": sorted(set(allow_categories)),
        "deny_categories": sorted(set(deny_categories)),
        "max_tokens": max_tokens,
        "redaction": str(policy.get("redaction") or "strict"),
        "include_memory": bool(policy.get("include_memory", False)),
        "include_artifacts": bool(policy.get("include_artifacts", False)),
        "include_squad_context": bool(policy.get("include_squad_context", False)),
        "review_on_sensitive": bool(policy.get("review_on_sensitive", True)),
    }


@dataclass(frozen=True, slots=True)
class ContextGovernanceBlock:
    block_id: str
    category: str
    source: str
    token_estimate: int
    status: str
    include_reason: str | None = None
    drop_reason: str | None = None
    redaction: str = "metadata_only"
    risk: str = "low"
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CONTEXT_GOVERNANCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "block_id": self.block_id,
            "category": self.category,
            "source": self.source,
            "token_estimate": self.token_estimate,
            "status": self.status,
            "include_reason": self.include_reason,
            "drop_reason": self.drop_reason,
            "redaction": self.redaction,
            "risk": self.risk,
            "provenance": dict(self.provenance),
        }


def _risk_for_segment(segment: Mapping[str, Any]) -> str:
    category = str(segment.get("category") or "").lower()
    segment_id = str(segment.get("segment_id") or "").lower()
    raw_metadata = segment.get("metadata")
    metadata = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
    joined = " ".join([category, segment_id, " ".join(str(key).lower() for key in metadata)])
    if any(token in joined for token in _SENSITIVE_CATEGORY_TOKENS):
        return "sensitive"
    if category in _MEMORY_CATEGORIES:
        return "memory"
    if category in _ARTIFACT_CATEGORIES:
        return "artifact"
    if segment_id in _SQUAD_SEGMENT_IDS:
        return "squad"
    return "low"


def _govern_status(
    segment: Mapping[str, Any], *, policy: Mapping[str, Any], default_status: str
) -> tuple[str, str | None, str | None]:
    category = str(segment.get("category") or "unknown")
    segment_id = str(segment.get("segment_id") or "")
    risk = _risk_for_segment(segment)
    deny_categories = set(_list_strings(policy.get("deny_categories")))
    allow_categories = set(_list_strings(policy.get("allow_categories")))

    if category in deny_categories:
        return "dropped", None, "category_denied"
    if risk == "sensitive":
        if bool(policy.get("review_on_sensitive", True)):
            return "review_required", None, "sensitive_context_requires_review"
        return "dropped", None, "sensitive_context_fenced"
    if category in _MEMORY_CATEGORIES and not bool(policy.get("include_memory", False)):
        return "dropped", None, "memory_not_allowed"
    if category in _ARTIFACT_CATEGORIES and not bool(policy.get("include_artifacts", False)):
        return "dropped", None, "artifact_context_not_allowed"
    if segment_id in _SQUAD_SEGMENT_IDS and not bool(policy.get("include_squad_context", False)):
        return "dropped", None, "squad_context_not_allowed"
    if default_status == "dropped":
        return "dropped", None, "prompt_budget_dropped"
    if allow_categories and category not in allow_categories:
        return "dropped", None, "category_not_allowed"
    return "included", "policy_allowed_metadata_only", None


def govern_prompt_budget(
    prompt_budget: Mapping[str, Any] | None, context_policy: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Summarize prompt blocks for child-run governance without raw text."""

    policy = normalize_context_policy(context_policy)
    budget = dict(prompt_budget or {})
    blocks: list[ContextGovernanceBlock] = []
    token_totals = {"included": 0, "dropped": 0, "review_required": 0}

    for default_status, key in (("included", "included_segments"), ("dropped", "dropped_segments")):
        segments = budget.get(key)
        if not isinstance(segments, list):
            continue
        for index, item in enumerate(segments):
            if not isinstance(item, Mapping):
                continue
            token_estimate = max(0, _int(item.get("token_estimate"), 0))
            status, include_reason, drop_reason = _govern_status(item, policy=policy, default_status=default_status)
            token_totals[status] = token_totals.get(status, 0) + token_estimate
            block_id = str(item.get("segment_id") or "") or _stable_id(
                {"index": index, "category": item.get("category")}
            )
            raw_metadata = item.get("metadata")
            metadata = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
            blocks.append(
                ContextGovernanceBlock(
                    block_id=block_id,
                    category=str(item.get("category") or "unknown"),
                    source=str(metadata.get("source") or metadata.get("agent_id") or item.get("category") or "runtime"),
                    token_estimate=token_estimate,
                    status=status,
                    include_reason=include_reason,
                    drop_reason=drop_reason,
                    redaction=str(policy.get("redaction") or "strict"),
                    risk=_risk_for_segment(item),
                    provenance={
                        "prompt_budget_status": default_status,
                        "priority": item.get("priority"),
                        "compression_strategy": item.get("compression_strategy"),
                        "drop_policy": item.get("drop_policy"),
                    },
                )
            )

    included = sum(1 for block in blocks if block.status == "included")
    dropped = sum(1 for block in blocks if block.status == "dropped")
    review_required = sum(1 for block in blocks if block.status == "review_required")
    return {
        "schema_version": CONTEXT_GOVERNANCE_SCHEMA_VERSION,
        "policy": dict(policy),
        "summary": {
            "block_count": len(blocks),
            "included_count": included,
            "dropped_count": dropped,
            "review_required_count": review_required,
            "included_token_estimate": token_totals.get("included", 0),
            "dropped_token_estimate": token_totals.get("dropped", 0),
            "review_required_token_estimate": token_totals.get("review_required", 0),
            "max_tokens": policy["max_tokens"],
        },
        "blocks": [block.to_dict() for block in blocks],
    }


def _memory_id_list(values: Any, *, limit: int = 25) -> list[Any]:
    if not isinstance(values, list):
        return []
    ids: list[Any] = []
    for item in values:
        memory_id = getattr(getattr(item, "memory", None), "id", None)
        if memory_id is None and isinstance(item, Mapping):
            memory_id = item.get("memory_id")
        if memory_id is not None:
            ids.append(memory_id)
        if len(ids) >= limit:
            break
    return ids


def _memory_reason_counts(values: Any, attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(values, list):
        return counts
    for item in values:
        reason = getattr(item, attr, None)
        if reason is None and isinstance(item, Mapping):
            reason = item.get(attr)
        text = str(reason or "unknown").strip() or "unknown"
        counts[text] = counts.get(text, 0) + 1
    return counts


def append_memory_resolution_blocks(
    context_summary: Mapping[str, Any] | None,
    memory_resolution: Any | None,
    context_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach metadata-only memory recall explanations to context governance."""

    summary = dict(context_summary or {})
    if not memory_resolution:
        return summary
    policy = normalize_context_policy(context_policy or summary.get("policy"))
    status = "included" if bool(policy.get("include_memory", False)) else "dropped"
    selected = list(getattr(memory_resolution, "selected", []) or [])
    discarded = list(getattr(memory_resolution, "discarded", []) or [])
    conflicts = list(getattr(memory_resolution, "conflicts", []) or [])
    explanations = list(getattr(memory_resolution, "explanations", []) or [])
    sensitive_selected = sum(
        1
        for item in selected
        if str(getattr(getattr(item, "memory", None), "sensitivity", "normal") or "normal") == "sensitive"
    )
    if sensitive_selected and bool(policy.get("review_on_sensitive", True)):
        status = "review_required"
    drop_reason = None
    if status == "dropped":
        drop_reason = "memory_not_allowed"
    elif status == "review_required":
        drop_reason = "sensitive_context_requires_review"
    block = ContextGovernanceBlock(
        block_id=_stable_id(
            {
                "source": "memory_recall",
                "selected": _memory_id_list(selected),
                "discarded": _memory_id_list(discarded),
                "trust_score": getattr(memory_resolution, "trust_score", 0.0),
            },
            prefix="memory",
        ),
        category="memory",
        source="memory_recall",
        token_estimate=0,
        status=status,
        include_reason="memory_recall_policy_allowed_metadata_only" if status == "included" else None,
        drop_reason=drop_reason,
        redaction="metadata_only",
        risk="memory" if not sensitive_selected else "sensitive",
        provenance={
            "selected_count": len(selected),
            "dropped_count": len(discarded),
            "conflict_count": len(conflicts),
            "trust_score": float(getattr(memory_resolution, "trust_score", 0.0) or 0.0),
            "selected_layers": list(getattr(memory_resolution, "selected_layers", []) or []),
            "retrieval_sources": list(getattr(memory_resolution, "retrieval_sources", []) or []),
            "selected_memory_ids": _memory_id_list(selected),
            "dropped_reasons": _memory_reason_counts(discarded, "reason"),
            "conflict_keys": [str(getattr(item, "conflict_key", "") or "") for item in conflicts[:20]],
            "explanations": [
                {
                    "memory_id": getattr(item, "memory_id", None),
                    "layer": getattr(item, "layer", ""),
                    "retrieval_source": getattr(item, "retrieval_source", ""),
                    "score": getattr(item, "score", 0.0),
                    "scope_score": getattr(item, "scope_score", 0.0),
                    "reasons": list(getattr(item, "reasons", []) or []),
                    "namespace_kind": getattr(item, "namespace_kind", "agent"),
                    "namespace_key": getattr(item, "namespace_key", ""),
                    "sensitivity": getattr(item, "sensitivity", "normal"),
                }
                for item in explanations[:20]
            ],
        },
    )
    blocks = [item for item in list(summary.get("blocks") or []) if isinstance(item, Mapping)]
    blocks.append(block.to_dict())
    summary["schema_version"] = CONTEXT_GOVERNANCE_SCHEMA_VERSION
    summary["policy"] = dict(policy)
    summary["blocks"] = blocks
    counts = {
        "included_count": sum(1 for item in blocks if item.get("status") == "included"),
        "dropped_count": sum(1 for item in blocks if item.get("status") == "dropped"),
        "review_required_count": sum(1 for item in blocks if item.get("status") == "review_required"),
    }
    current_summary = dict(summary.get("summary") or {})
    current_summary.update(
        {
            "block_count": len(blocks),
            **counts,
        }
    )
    summary["summary"] = current_summary
    return summary


def build_child_context_prompt(
    *,
    parent_task_id: int,
    goal: str,
    context_policy: Mapping[str, Any] | None = None,
    context_summary: Mapping[str, Any] | None = None,
) -> str:
    """Build the bounded child-run context block injected into the child turn."""

    policy = normalize_context_policy(context_policy)
    summary = dict(context_summary or {})
    blocks = [item for item in summary.get("blocks", []) if isinstance(item, Mapping)]
    included = [item for item in blocks if item.get("status") == "included"][:20]
    dropped = [item for item in blocks if item.get("status") in {"dropped", "review_required"}][:20]
    lines = [
        '<child_run_context schema_version="context_governance.v1">',
        f"parent_task_id={int(parent_task_id)}",
        f"goal={goal.strip()[:500]}",
        f"mode={policy['mode']}",
        f"max_context_tokens={policy['max_tokens']}",
        "The parent run delegated this bounded task. Use only the user brief below, "
        "normal runtime context, and metadata-only approved blocks.",
        "Do not infer access to hidden parent prompt text, secrets, pending approvals, "
        "sensitive mounts, or fenced memory.",
        "Approved context block metadata:",
    ]
    if included:
        for block in included:
            lines.append(
                "- "
                f"{block.get('block_id')} "
                f"category={block.get('category')} "
                f"tokens={block.get('token_estimate')} "
                f"source={block.get('source')} "
                f"risk={block.get('risk')}"
            )
    else:
        lines.append("- none")
    if dropped:
        lines.append("Fenced or review-required blocks:")
        for block in dropped:
            lines.append(
                "- "
                f"{block.get('block_id')} "
                f"category={block.get('category')} "
                f"status={block.get('status')} "
                f"reason={block.get('drop_reason')}"
            )
    lines.append("</child_run_context>")
    return "\n".join(lines)
