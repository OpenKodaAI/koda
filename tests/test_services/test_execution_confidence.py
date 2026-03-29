"""Tests for execution confidence heuristics."""

from datetime import UTC, datetime, timedelta

from koda.knowledge.policy import default_execution_policy
from koda.memory.profile import MemoryProfile
from koda.services.execution_confidence import ActionPlan, evaluate_write_confidence


def _valid_plan() -> ActionPlan:
    return ActionPlan(
        summary="Apply the change",
        assumptions="Inputs are correct",
        evidence="I inspected the relevant docs",
        sources="README.md",
        risk="Could break scheduling",
        success="The resulting state can be verified",
    )


def test_blocks_when_no_read_evidence_exists() -> None:
    report = evaluate_write_confidence(
        action_plan=_valid_plan(),
        task_kind="code_change",
        policy=default_execution_policy("code_change"),
        read_calls=[],
        prior_tool_steps=[],
        native_tool_uses=[],
        knowledge_hits=[{"source_label": "README.md", "layer": "workspace_doc", "freshness": "fresh"}],
        warnings=[],
    )

    assert report.blocked is True
    assert report.read_evidence_count == 0


def test_native_read_tools_count_as_evidence() -> None:
    report = evaluate_write_confidence(
        action_plan=_valid_plan(),
        task_kind="general",
        policy=default_execution_policy("general"),
        read_calls=[],
        prior_tool_steps=[],
        native_tool_uses=[{"name": "Read", "input": {"file_path": "/tmp/README.md"}}],
        knowledge_hits=[{"source_label": "README.md", "layer": "workspace_doc", "freshness": "fresh"}],
        warnings=[],
    )

    assert report.blocked is False
    assert report.read_evidence_count == 1


def test_review_tasks_are_read_only() -> None:
    report = evaluate_write_confidence(
        action_plan=_valid_plan(),
        task_kind="review",
        policy=default_execution_policy("review"),
        read_calls=[object()],
        prior_tool_steps=[],
        native_tool_uses=[],
        knowledge_hits=[{"source_label": "README.md", "layer": "workspace_doc", "freshness": "fresh"}],
        warnings=[],
    )

    assert report.blocked is True
    assert report.write_mode == "read_only"


def test_deploy_requires_grounded_policy_layers_and_rollback_note() -> None:
    plan = _valid_plan()
    report = evaluate_write_confidence(
        action_plan=plan,
        task_kind="deploy",
        policy=default_execution_policy("deploy"),
        read_calls=[object(), object()],
        prior_tool_steps=[],
        native_tool_uses=[],
        knowledge_hits=[{"source_label": "workspace:README.md", "layer": "workspace_doc", "freshness": "fresh"}],
        warnings=[],
    )

    assert report.blocked is True
    assert "canonical_policy" in report.required_source_layers


def test_investigation_writes_require_escalation() -> None:
    report = evaluate_write_confidence(
        action_plan=_valid_plan(),
        task_kind="investigation",
        policy=default_execution_policy("investigation"),
        read_calls=[object()],
        prior_tool_steps=[],
        native_tool_uses=[],
        knowledge_hits=[{"source_label": "README.md", "layer": "workspace_doc", "freshness": "fresh"}],
        warnings=[],
    )

    assert report.blocked is True
    assert "missing structured action plan" not in report.reasons


def test_guardrails_force_human_approval_even_when_write_is_otherwise_valid() -> None:
    report = evaluate_write_confidence(
        action_plan=_valid_plan(),
        task_kind="code_change",
        policy=default_execution_policy("code_change"),
        read_calls=[object(), object()],
        prior_tool_steps=[],
        native_tool_uses=[],
        knowledge_hits=[{"source_label": "agent_a.toml", "layer": "canonical_policy", "freshness": "fresh"}],
        warnings=[],
        guardrails=[{"title": "Do not touch production cron without review"}],
    )

    assert report.blocked is False
    assert report.requires_human_approval is True
    assert report.guardrail_count == 1


def test_policy_max_source_age_forces_human_approval() -> None:
    report = evaluate_write_confidence(
        action_plan=_valid_plan(),
        task_kind="code_change",
        policy=default_execution_policy("code_change"),
        read_calls=[object(), object()],
        prior_tool_steps=[],
        native_tool_uses=[],
        knowledge_hits=[
            {
                "source_label": "agent_a.toml",
                "layer": "canonical_policy",
                "freshness": "fresh",
                "updated_at": (datetime.now(UTC) - timedelta(days=120)).isoformat(),
            }
        ],
        warnings=[],
    )

    assert report.blocked is False
    assert report.requires_human_approval is True
    assert report.stale_sources_present is True


def test_code_change_without_canonical_or_runbook_grounding_requires_human_approval() -> None:
    report = evaluate_write_confidence(
        action_plan=_valid_plan(),
        task_kind="code_change",
        policy=default_execution_policy("code_change"),
        read_calls=[object(), object()],
        prior_tool_steps=[],
        native_tool_uses=[],
        knowledge_hits=[{"source_label": "README.md", "layer": "workspace_doc", "freshness": "fresh"}],
        warnings=[],
        ungrounded_operationally=True,
    )

    assert report.blocked is False
    assert report.requires_human_approval is True


def test_non_operable_sources_do_not_satisfy_write_grounding() -> None:
    report = evaluate_write_confidence(
        action_plan=_valid_plan(),
        task_kind="code_change",
        policy=default_execution_policy("code_change"),
        read_calls=[object(), object()],
        prior_tool_steps=[],
        native_tool_uses=[],
        knowledge_hits=[
            {"source_label": "pattern", "layer": "approved_runbook", "freshness": "fresh", "operable": False}
        ],
        warnings=[],
    )

    assert report.blocked is True
    assert "approved_runbook" in report.non_operable_source_layers


def test_operable_runbook_still_allows_grounded_write() -> None:
    report = evaluate_write_confidence(
        action_plan=_valid_plan(),
        task_kind="code_change",
        policy=default_execution_policy("code_change"),
        read_calls=[object(), object()],
        prior_tool_steps=[],
        native_tool_uses=[],
        knowledge_hits=[
            {"source_label": "runbook", "layer": "approved_runbook", "freshness": "fresh", "operable": True}
        ],
        warnings=[],
    )

    assert report.blocked is False
    assert "approved_runbook" in report.operable_source_layers


def test_profile_forbidden_memory_layers_require_human_approval() -> None:
    profile = MemoryProfile(
        agent_id="test",
        risk_posture="conservative",
        forbidden_layers_for_actions=("conversational",),
    )
    memory_resolution = type(
        "Resolution",
        (),
        {"trust_score": 0.9, "selected_layers": ["conversational"], "explanations": [{"id": 1}]},
    )()

    report = evaluate_write_confidence(
        action_plan=_valid_plan(),
        task_kind="code_change",
        policy=default_execution_policy("code_change"),
        read_calls=[object(), object()],
        prior_tool_steps=[],
        native_tool_uses=[],
        knowledge_hits=[
            {"source_label": "runbook", "layer": "approved_runbook", "freshness": "fresh", "operable": True}
        ],
        memory_resolution=memory_resolution,
        memory_profile=profile,
        warnings=[],
    )

    assert report.requires_human_approval is True
