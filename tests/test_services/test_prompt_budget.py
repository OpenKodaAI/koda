"""Tests for prompt budgeting and compilation."""

from koda.services.prompt_budget import (
    PromptBudgetPlanner,
    PromptSegment,
    preview_compiled_prompt,
    preview_modeled_runtime_prompt,
)


def test_prompt_budget_keeps_hard_floor_and_drops_low_priority_segments():
    planner = PromptBudgetPlanner(context_window=12_000, reserved_output_tokens=2_000, max_system_prompt_tokens=1_200)
    result = planner.compile(
        provider="claude",
        model="claude-sonnet-4-6",
        segments=[
            PromptSegment(
                segment_id="immutable_base_policy",
                text="A" * 1200,
                category="base",
                priority=0,
                drop_policy="hard_floor",
            ),
            PromptSegment(
                segment_id="memory_context",
                text="B" * 3200,
                category="memory",
                priority=50,
            ),
            PromptSegment(
                segment_id="cache_hint",
                text="C" * 3200,
                category="cache_hints",
                priority=90,
            ),
        ],
    )

    included_ids = [item["segment_id"] for item in result.included_segments]
    dropped_ids = [item["segment_id"] for item in result.dropped_segments]
    assert "immutable_base_policy" in included_ids
    assert "cache_hint" in dropped_ids
    assert result.within_budget is True
    assert result.overflow_tokens == 0


def test_preview_compiled_prompt_reports_segment_order():
    preview = preview_compiled_prompt(
        compiled_prompt="<agent_identity>x</agent_identity>",
        documents={
            "identity_md": "# Identity",
            "soul_md": "# Soul",
            "system_prompt_md": "# System",
            "instructions_md": "# Instructions",
            "rules_md": "# Rules",
        },
        agent_id="AGENT_A",
    )

    assert preview["segment_order"] == [
        "identity_md",
        "soul_md",
        "system_prompt_md",
        "instructions_md",
        "rules_md",
    ]
    assert preview["preview_scope"] == "agent_contract_only"
    assert preview["segments"][1]["runtime_tag"] == "agent_interaction_style"
    assert preview["runtime_hard_floor_order"] == [
        "immutable_base_policy",
        "operator_instructions",
        "scheduled_dry_run_rules",
    ]
    assert preview["runtime_alignment"]["represents_full_runtime_prompt"] is False


def test_prompt_budget_applies_category_caps():
    planner = PromptBudgetPlanner(context_window=24_000, reserved_output_tokens=2_000, max_system_prompt_tokens=3_000)
    result = planner.compile(
        provider="claude",
        model="claude-sonnet-4-6",
        segments=[
            PromptSegment(
                segment_id="immutable_base_policy",
                text="A" * 1200,
                category="base",
                priority=0,
                drop_policy="hard_floor",
            ),
            PromptSegment(
                segment_id="memory_context",
                text="B" * 2400,
                category="memory",
                priority=40,
            ),
        ],
        category_token_caps={"memory": 120},
    )

    memory_segment = next(item for item in result.included_segments if item["segment_id"] == "memory_context")
    assert memory_segment["final_token_estimate"] <= 120


def test_prompt_budget_reports_hard_floor_overflow_reason():
    planner = PromptBudgetPlanner(context_window=8_000, reserved_output_tokens=2_000, max_system_prompt_tokens=500)
    result = planner.compile(
        provider="claude",
        model="claude-sonnet-4-6",
        segments=[
            PromptSegment(
                segment_id="immutable_base_policy",
                text="A" * 10000,
                category="base",
                priority=0,
                drop_policy="hard_floor",
            )
        ],
    )

    assert result.within_budget is False
    assert result.gate_reason == "hard_floor_overflow"
    assert result.overflow_tokens > 0


def test_preview_modeled_runtime_prompt_applies_budget_gate():
    preview = preview_modeled_runtime_prompt(
        immutable_base_prompt="A" * 80000,
        provider="claude",
        model="claude-sonnet-4-6",
        static_segments=[],
    )

    assert preview["preview_scope"] == "runtime_modeled_static"
    assert preview["runtime_alignment"]["budget_gate_applied"] is True
    assert preview["budget"]["within_budget"] is False
    assert preview["budget"]["gate_reason"] == "hard_floor_overflow"
