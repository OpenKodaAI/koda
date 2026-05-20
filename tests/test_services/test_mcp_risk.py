"""Focused tests for Phase 2 MCP risk taxonomy helpers."""

from __future__ import annotations

from koda.services.mcp_client import McpToolAnnotations, McpToolDefinition
from koda.services.mcp_risk import (
    assess_mcp_tool_risk,
    evaluate_mcp_risk,
    normalize_mcp_risk_class,
)


def test_normalize_mcp_risk_class_aliases() -> None:
    assert normalize_mcp_risk_class("read-only") == "read_context"
    assert normalize_mcp_risk_class("network") == "network_write"
    assert normalize_mcp_risk_class("credential_access") == "secret_access"
    assert normalize_mcp_risk_class("command execution") == "code_execution"
    assert normalize_mcp_risk_class("surprising-safe-label") == "unknown"


def test_read_only_annotation_maps_to_read_context() -> None:
    assessment = assess_mcp_tool_risk(
        McpToolDefinition(
            name="list_repos",
            description="List repositories.",
            annotations=McpToolAnnotations(read_only_hint=True),
        )
    )

    assert assessment.risk_class == "read_context"
    assert assessment.annotation_risk_class == "read_context"
    assert evaluate_mcp_risk(assessment).decision == "allow"


def test_annotation_keyword_conflict_uses_higher_risk() -> None:
    assessment = assess_mcp_tool_risk(
        "delete_issue",
        description="Deletes a GitHub issue.",
        annotations=McpToolAnnotations(read_only_hint=True),
    )
    decision = evaluate_mcp_risk(assessment)

    assert assessment.risk_class == "destructive_write"
    assert "annotation_keyword_conflict" in assessment.reasons
    assert decision.decision == "require_approval"
    assert decision.allowed_to_execute is False


def test_conflicting_mcp_annotations_do_not_downgrade_destructive() -> None:
    assessment = assess_mcp_tool_risk(
        "archive_thread",
        annotations=McpToolAnnotations(read_only_hint=True, destructive_hint=True),
    )

    assert assessment.risk_class == "destructive_write"
    assert "annotation_conflict" in assessment.reasons


def test_unknown_mcp_risk_fails_closed_until_approval() -> None:
    assessment = assess_mcp_tool_risk("do_thing")
    blocked = evaluate_mcp_risk(assessment)
    allowed = evaluate_mcp_risk(assessment, approval_granted=True)

    assert assessment.risk_class == "unknown"
    assert blocked.reason_code == "unknown_risk_fail_closed"
    assert blocked.allowed_to_execute is False
    assert allowed.allowed_to_execute is True


def test_secret_code_network_and_destructive_keywords_map_to_high_risk() -> None:
    cases = {
        "get_secret": "secret_access",
        "run_shell_command": "code_execution",
        "post_message": "network_write",
        "delete_file": "destructive_write",
    }

    for tool_name, risk_class in cases.items():
        assert assess_mcp_tool_risk(tool_name).risk_class == risk_class


def test_schema_fields_contribute_to_secret_and_code_mapping() -> None:
    secret_assessment = assess_mcp_tool_risk(
        "exchange",
        input_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string"},
                "payload": {"type": "string"},
            },
        },
    )
    code_assessment = assess_mcp_tool_risk(
        "evaluate",
        input_schema={
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "JavaScript code to run."},
            },
        },
    )

    assert secret_assessment.risk_class == "secret_access"
    assert code_assessment.risk_class == "code_execution"


def test_open_world_write_maps_to_network_write() -> None:
    assessment = assess_mcp_tool_risk(
        "create_item",
        annotations={"openWorldHint": True, "idempotentHint": False},
    )

    assert assessment.risk_class == "network_write"
    assert evaluate_mcp_risk(assessment).requires_approval is True
