from __future__ import annotations

from koda.services.context_governance import (
    build_child_context_prompt,
    govern_prompt_budget,
    normalize_context_policy,
)


def test_context_governance_uses_metadata_only_and_fences_memory() -> None:
    prompt_budget = {
        "included_segments": [
            {
                "segment_id": "immutable_base_policy",
                "category": "base",
                "priority": 0,
                "compression_strategy": "truncate_tail",
                "drop_policy": "hard_floor",
                "token_estimate": 100,
                "metadata": {"source": "default"},
            },
            {
                "segment_id": "authoritative_knowledge",
                "category": "authoritative_knowledge",
                "priority": 60,
                "compression_strategy": "head_and_tail",
                "drop_policy": "drop",
                "token_estimate": 900,
                "metadata": {"source": "memory"},
            },
        ],
        "dropped_segments": [
            {
                "segment_id": "operator_secret",
                "category": "secrets",
                "token_estimate": 50,
                "metadata": {"secret_token": "should-not-leak"},
            }
        ],
    }

    payload = govern_prompt_budget(prompt_budget)

    assert payload["schema_version"] == "context_governance.v1"
    assert payload["summary"]["included_count"] == 1
    assert payload["summary"]["dropped_count"] == 2
    assert payload["blocks"][0]["block_id"] == "immutable_base_policy"
    assert "should-not-leak" not in str(payload)


def test_child_context_prompt_lists_only_block_metadata() -> None:
    policy = normalize_context_policy({"allow_categories": ["base"], "max_tokens": 500})
    context = {
        "blocks": [
            {
                "block_id": "immutable_base_policy",
                "category": "base",
                "source": "default",
                "token_estimate": 100,
                "status": "included",
                "risk": "low",
            },
            {
                "block_id": "pending_approval",
                "category": "pending_approval",
                "status": "review_required",
                "drop_reason": "sensitive_context_requires_review",
            },
        ]
    }

    prompt = build_child_context_prompt(
        parent_task_id=123,
        goal="inspect files",
        context_policy=policy,
        context_summary=context,
    )

    assert 'schema_version="context_governance.v1"' in prompt
    assert "parent_task_id=123" in prompt
    assert "immutable_base_policy" in prompt
    assert "pending_approval" in prompt
