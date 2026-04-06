"""Prompt budget planning and compilation helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from koda.config import AGENT_ID

_DEFAULT_CONTEXT_WINDOW = 200_000
_DEFAULT_RESERVED_OUTPUT = 8_000
_DEFAULT_SYSTEM_PROMPT_CAP = 16_000
_DEFAULT_SAFETY_MARGIN_RATIO = 0.10
_CHARS_PER_TOKEN = 4
_ELLIPSIS = "\n...[truncated for prompt budget]..."

_AGENT_CONTRACT_LAYOUT: tuple[tuple[str, str], ...] = (
    ("identity_md", "agent_identity"),
    ("soul_md", "agent_interaction_style"),
    ("system_prompt_md", "agent_response_policy"),
    ("instructions_md", "agent_operating_instructions"),
    ("rules_md", "agent_hard_rules"),
)

_RUNTIME_DISCRETIONARY_CATEGORY_ORDER: tuple[str, ...] = (
    "identity",
    "runtime_rules",
    "tool_contracts",
    "authoritative_knowledge",
    "memory",
    "supporting_knowledge",
    "scripts_assets",
    "cache_hints",
    "extras",
)

_RUNTIME_UNMODELED_SEGMENTS: tuple[dict[str, Any], ...] = (
    {
        "segment_id": "operator_instructions",
        "category": "identity",
        "dynamic": True,
        "source": "per-turn /system instructions",
    },
    {
        "segment_id": "scheduled_dry_run_rules",
        "category": "runtime_rules",
        "dynamic": True,
        "source": "scheduled dry-run execution mode",
    },
    {
        "segment_id": "voice_prompt",
        "category": "runtime_rules",
        "dynamic": True,
        "source": "audio response mode",
    },
    {
        "segment_id": "tool_contracts",
        "category": "tool_contracts",
        "dynamic": False,
        "source": "runtime tool exposure and execution contract",
    },
    {
        "segment_id": "memory_context",
        "category": "memory",
        "dynamic": True,
        "source": "session and procedural memory recall",
    },
    {
        "segment_id": "artifact_context",
        "category": "supporting_knowledge",
        "dynamic": True,
        "source": "artifact bundle extraction",
    },
    {
        "segment_id": "jira_artifact_context",
        "category": "supporting_knowledge",
        "dynamic": True,
        "source": "Jira dossier artifact extraction",
    },
    {
        "segment_id": "relevant_scripts",
        "category": "scripts_assets",
        "dynamic": True,
        "source": "saved script search",
    },
    {
        "segment_id": "asset_memory",
        "category": "scripts_assets",
        "dynamic": True,
        "source": "agent asset registry lookup",
    },
    {
        "segment_id": "cache_hint",
        "category": "cache_hints",
        "dynamic": True,
        "source": "cache fuzzy suggestion",
    },
    {
        "segment_id": "relevant_skills_awareness",
        "category": "extras",
        "dynamic": True,
        "source": "query-scoped curated skills awareness",
    },
    {
        "segment_id": "authoritative_knowledge",
        "category": "authoritative_knowledge",
        "dynamic": True,
        "source": "knowledge retrieval context",
    },
)

_CATEGORY_QUOTAS: dict[str, float] = {
    "conversation": 0.25,
    "authoritative_knowledge": 0.25,
    "supporting_knowledge": 0.12,
    "memory": 0.12,
    "scripts_assets": 0.08,
    "cache_hints": 0.05,
    "extras": 0.05,
}

_MODEL_CONTEXT_HINTS: tuple[tuple[str, int], ...] = (
    ("gemini-3", 1_000_000),
    ("gemini-2.5", 1_000_000),
    ("gpt-5", 200_000),
    ("o3", 200_000),
    ("o4", 200_000),
    ("claude", 200_000),
)


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text or "") / _CHARS_PER_TOKEN))


def infer_context_window(*, provider: str, model: str) -> int:
    haystack = f"{provider}:{model}".lower()
    for needle, size in _MODEL_CONTEXT_HINTS:
        if needle in haystack:
            return size
    return _DEFAULT_CONTEXT_WINDOW


@dataclass(slots=True)
class PromptSegment:
    segment_id: str
    text: str
    category: str
    priority: int = 100
    compression_strategy: str = "truncate_tail"
    drop_policy: str = "drop"
    token_estimate: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.token_estimate:
            self.token_estimate = estimate_tokens(self.text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "category": self.category,
            "priority": self.priority,
            "compression_strategy": self.compression_strategy,
            "drop_policy": self.drop_policy,
            "token_estimate": self.token_estimate,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class PromptBudgetResult:
    compiled_prompt: str
    max_input_tokens: int
    compiled_tokens: int
    overflow_tokens: int
    within_budget: bool
    hard_floor_tokens: int
    discretionary_tokens: int
    gate_reason: str | None
    final_segment_order: list[str]
    category_token_caps: dict[str, int]
    ordered_categories: list[str]
    included_segments: list[dict[str, Any]]
    dropped_segments: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_input_tokens": self.max_input_tokens,
            "compiled_tokens": self.compiled_tokens,
            "overflow_tokens": self.overflow_tokens,
            "within_budget": self.within_budget,
            "hard_floor_tokens": self.hard_floor_tokens,
            "discretionary_tokens": self.discretionary_tokens,
            "gate_reason": self.gate_reason,
            "final_segment_order": list(self.final_segment_order),
            "category_token_caps": dict(self.category_token_caps),
            "ordered_categories": list(self.ordered_categories),
            "included_segments": list(self.included_segments),
            "dropped_segments": list(self.dropped_segments),
        }


class PromptBudgetPlanner:
    """Apply fixed budget rules to prompt segments before provider execution."""

    def __init__(
        self,
        *,
        context_window: int | None = None,
        reserved_output_tokens: int = _DEFAULT_RESERVED_OUTPUT,
        safety_margin_ratio: float = _DEFAULT_SAFETY_MARGIN_RATIO,
        max_system_prompt_tokens: int = _DEFAULT_SYSTEM_PROMPT_CAP,
    ) -> None:
        self._context_window = context_window
        self._reserved_output_tokens = max(512, reserved_output_tokens)
        self._safety_margin_ratio = max(0.0, min(0.4, safety_margin_ratio))
        self._max_system_prompt_tokens = max(2_048, max_system_prompt_tokens)

    def compile(
        self,
        *,
        provider: str,
        model: str,
        segments: list[PromptSegment],
        category_token_caps: dict[str, int] | None = None,
    ) -> PromptBudgetResult:
        context_window = self._context_window or infer_context_window(provider=provider, model=model)
        safety_margin = int(context_window * self._safety_margin_ratio)
        max_input_tokens = max(
            2_048,
            min(
                self._max_system_prompt_tokens,
                context_window - self._reserved_output_tokens - safety_margin,
            ),
        )
        hard_floor_segments: list[PromptSegment] = []
        discretionary_segments: list[PromptSegment] = []
        for segment in segments:
            if not (segment.text or "").strip():
                continue
            if segment.drop_policy == "hard_floor":
                hard_floor_segments.append(segment)
            else:
                discretionary_segments.append(segment)

        included: list[dict[str, Any]] = []
        dropped: list[dict[str, Any]] = []
        compiled_segments: list[str] = []
        used_tokens = 0

        for segment in hard_floor_segments:
            compiled_segments.append(segment.text)
            used_tokens += segment.token_estimate
            included.append({**segment.to_dict(), "final_token_estimate": segment.token_estimate})

        remaining_budget = max(0, max_input_tokens - used_tokens)
        quotas = {category: max(0, int(max_input_tokens * ratio)) for category, ratio in _CATEGORY_QUOTAS.items()}
        quotas.setdefault("base", max_input_tokens)
        quotas.setdefault("tool_contracts", max_input_tokens)
        quotas.setdefault("runtime_rules", max_input_tokens)
        quotas.setdefault("identity", max_input_tokens)
        if category_token_caps:
            for category, cap in category_token_caps.items():
                if cap <= 0:
                    continue
                current = quotas.get(category, max_input_tokens)
                quotas[category] = min(current, int(cap))

        grouped: dict[str, list[PromptSegment]] = {}
        for segment in discretionary_segments:
            grouped.setdefault(segment.category, []).append(segment)
        for items in grouped.values():
            items.sort(key=lambda item: (item.priority, item.segment_id))

        ordered_categories = list(_RUNTIME_DISCRETIONARY_CATEGORY_ORDER)
        for category in ordered_categories:
            category_segments = grouped.get(category, [])
            if not category_segments or remaining_budget <= 0:
                for segment in category_segments:
                    dropped.append({**segment.to_dict(), "reason": "budget_exhausted"})
                continue
            category_budget = min(remaining_budget, quotas.get(category, remaining_budget))
            category_used = 0
            for segment in category_segments:
                allowed_tokens = max(0, min(category_budget - category_used, remaining_budget))
                if allowed_tokens <= 0:
                    dropped.append({**segment.to_dict(), "reason": "category_budget_exhausted"})
                    continue
                if segment.token_estimate <= allowed_tokens:
                    text = segment.text
                    final_tokens = segment.token_estimate
                    compressed = False
                else:
                    if segment.priority >= 80 and segment.drop_policy == "drop":
                        dropped.append({**segment.to_dict(), "reason": "dropped_for_budget"})
                        continue
                    text = self._compress(segment.text, allowed_tokens, strategy=segment.compression_strategy)
                    final_tokens = estimate_tokens(text) if text else 0
                    compressed = bool(text)
                if not text:
                    dropped.append({**segment.to_dict(), "reason": "dropped_for_budget"})
                    continue
                compiled_segments.append(text)
                category_used += final_tokens
                remaining_budget = max(0, remaining_budget - final_tokens)
                included.append(
                    {
                        **segment.to_dict(),
                        "compressed": compressed,
                        "final_token_estimate": final_tokens,
                    }
                )

        compiled_prompt = "\n\n".join(block for block in compiled_segments if block.strip()).strip()
        compiled_tokens = estimate_tokens(compiled_prompt) if compiled_prompt else 0
        hard_floor_tokens = sum(segment.token_estimate for segment in hard_floor_segments)
        discretionary_tokens = max(0, compiled_tokens - hard_floor_tokens)
        overflow_tokens = max(0, compiled_tokens - max_input_tokens)
        gate_reason: str | None = None
        if hard_floor_tokens > max_input_tokens:
            gate_reason = "hard_floor_overflow"
        elif overflow_tokens > 0:
            gate_reason = "compiled_overflow"
        return PromptBudgetResult(
            compiled_prompt=compiled_prompt,
            max_input_tokens=max_input_tokens,
            compiled_tokens=compiled_tokens,
            overflow_tokens=overflow_tokens,
            within_budget=compiled_tokens <= max_input_tokens,
            hard_floor_tokens=hard_floor_tokens,
            discretionary_tokens=discretionary_tokens,
            gate_reason=gate_reason,
            final_segment_order=[item["segment_id"] for item in included],
            category_token_caps=quotas,
            ordered_categories=ordered_categories,
            included_segments=included,
            dropped_segments=dropped,
        )

    def _compress(self, text: str, allowed_tokens: int, *, strategy: str) -> str:
        if allowed_tokens <= 8:
            return ""
        allowed_chars = max(64, allowed_tokens * _CHARS_PER_TOKEN)
        if len(text) <= allowed_chars:
            return text
        if strategy == "truncate_head":
            return _ELLIPSIS + text[-(allowed_chars - len(_ELLIPSIS)) :]
        if strategy == "head_and_tail":
            head_size = max(32, int((allowed_chars - len(_ELLIPSIS)) * 0.6))
            tail_size = max(16, allowed_chars - len(_ELLIPSIS) - head_size)
            return text[:head_size].rstrip() + _ELLIPSIS + text[-tail_size:].lstrip()
        return text[: allowed_chars - len(_ELLIPSIS)].rstrip() + _ELLIPSIS


def preview_compiled_prompt(
    *,
    compiled_prompt: str,
    documents: dict[str, str],
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Return a control-plane friendly preview of prompt ordering and sizes."""
    segments = []
    for kind, tag in _AGENT_CONTRACT_LAYOUT:
        content = str(documents.get(kind) or "").strip()
        if not content:
            continue
        # Detect origin from hierarchical markers
        origin = "agent"
        if "<!-- origin:workspace -->" in content and "<!-- origin:agent -->" not in content:
            origin = "workspace"
        elif "<!-- origin:squad -->" in content and "<!-- origin:agent -->" not in content:
            origin = "squad"
        elif "<!-- origin:workspace -->" in content or "<!-- origin:squad -->" in content:
            origin = "merged"
        segments.append(
            {
                "segment_id": kind,
                "runtime_tag": tag,
                "scope": "agent_contract",
                "origin": origin,
                "token_estimate": estimate_tokens(content),
                "char_count": len(content),
            }
        )
    return {
        "agent_id": (agent_id or AGENT_ID or "").upper() or None,
        "preview_scope": "agent_contract_only",
        "compiled_tokens": estimate_tokens(compiled_prompt) if compiled_prompt else 0,
        "segment_order": [segment["segment_id"] for segment in segments],
        "segments": segments,
        "runtime_hard_floor_order": [
            "immutable_base_policy",
            "operator_instructions",
            "scheduled_dry_run_rules",
        ],
        "runtime_discretionary_category_order": list(_RUNTIME_DISCRETIONARY_CATEGORY_ORDER),
        "runtime_unmodeled_segments": [dict(item) for item in _RUNTIME_UNMODELED_SEGMENTS],
        "runtime_alignment": {
            "represents_full_runtime_prompt": False,
            "matches_agent_contract_order": True,
            "budget_gate_applied": False,
            "requires_turn_context": True,
            "uses_runtime_category_order": True,
        },
    }


def preview_modeled_runtime_prompt(
    *,
    immutable_base_prompt: str,
    provider: str,
    model: str,
    agent_id: str | None = None,
    category_token_caps: dict[str, int] | None = None,
    static_segments: list[PromptSegment] | None = None,
) -> dict[str, Any]:
    """Return a runtime-shaped preview for the known static prompt floor.

    This preview intentionally models only query-independent segments available to the
    control plane at authoring time. Query-time memory, artifacts, cache hints, and
    retrieval context remain outside this preview.
    """
    segments = [
        PromptSegment(
            segment_id="immutable_base_policy",
            text=str(immutable_base_prompt or "").strip(),
            category="base",
            priority=0,
            compression_strategy="truncate_tail",
            drop_policy="hard_floor",
            metadata={"source": "modeled_runtime_base"},
        )
    ]
    for segment in static_segments or []:
        if not str(segment.text or "").strip():
            continue
        segments.append(segment)
    budget = PromptBudgetPlanner().compile(
        provider=provider,
        model=model,
        segments=segments,
        category_token_caps=category_token_caps,
    )
    return {
        "agent_id": (agent_id or AGENT_ID or "").upper() or None,
        "preview_scope": "runtime_modeled_static",
        "provider": provider,
        "model": model,
        "compiled_tokens": budget.compiled_tokens,
        "segment_order": list(budget.final_segment_order),
        "runtime_hard_floor_order": [
            item["segment_id"] for item in budget.included_segments if item.get("drop_policy") == "hard_floor"
        ],
        "runtime_discretionary_category_order": list(_RUNTIME_DISCRETIONARY_CATEGORY_ORDER),
        "segments": [
            {
                "segment_id": item["segment_id"],
                "category": item["category"],
                "drop_policy": item["drop_policy"],
                "token_estimate": item["token_estimate"],
                "final_token_estimate": item.get("final_token_estimate", item["token_estimate"]),
                "metadata": dict(item.get("metadata") or {}),
            }
            for item in budget.included_segments
        ],
        "dropped_segments": list(budget.dropped_segments),
        "final_segment_order": list(budget.final_segment_order),
        "ordered_categories": list(budget.ordered_categories),
        "budget": budget.to_dict(),
        "compiled_prompt": budget.compiled_prompt,
        "runtime_alignment": {
            "represents_full_runtime_prompt": False,
            "matches_runtime_planner": True,
            "budget_gate_applied": True,
            "requires_turn_context": True,
            "modeled_static_segments_only": True,
        },
        "runtime_unmodeled_segments": [dict(item) for item in _RUNTIME_UNMODELED_SEGMENTS],
    }
