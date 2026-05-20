"""Tests for schema-first tool registry helpers."""

from __future__ import annotations

import pytest

from koda.agent_contract import CoreToolDefinition
from koda.services.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    ToolRegistryDriftError,
    ToolSchemaError,
    build_openai_tool_schemas_for_runtime,
    export_openai_tool_schemas,
    export_xml_prompt_entries,
    get_default_tool_registry,
    get_tool_definition,
    validate_json_schema_object,
)


def _sample_core_tools() -> tuple[CoreToolDefinition, ...]:
    return (
        CoreToolDefinition(
            "web_search",
            "Web search",
            "research",
            "Search & summarize the web.",
            read_only=True,
        ),
        CoreToolDefinition(
            "file_write",
            "File write",
            "fileops",
            "Create or overwrite a file.",
            feature_flag="fileops",
        ),
    )


def test_builds_core_definitions_with_read_write_metadata() -> None:
    registry = ToolRegistry.from_core_tools(
        _sample_core_tools(),
        read_tool_ids={"web_search"},
        write_tool_ids={"file_write"},
        handler_ids={"web_search", "file_write"},
        handler_refs={
            "web_search": "koda.services.tool_dispatcher._handle_web_search",
            "file_write": "koda.services.tool_dispatcher._handle_file_write",
        },
        args_schemas={
            "web_search": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            "file_write": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
        default_timeout_seconds=30,
    )

    read_tool = registry.require("web_search")
    write_tool = registry.require("file_write")

    assert read_tool.access_level == "read"
    assert read_tool.read_only is True
    assert read_tool.approval_default == "allow"
    assert read_tool.idempotency == "read_only"
    assert read_tool.ui_metadata == {"read_only": True, "write_capable": False}
    assert read_tool.handler_ref.endswith("_handle_web_search")

    assert write_tool.access_level == "write"
    assert write_tool.read_only is False
    assert write_tool.approval_default == "allow_with_preview"
    assert write_tool.idempotency == "non_idempotent"
    assert write_tool.effect_tags == ("workspace_mutation",)
    assert write_tool.feature_flag == "fileops"
    assert write_tool.timeout_seconds == 30
    assert write_tool.ui_metadata == {"read_only": False, "write_capable": True}


def test_validates_json_schema_object_basics() -> None:
    valid = validate_json_schema_object(
        {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        }
    )

    assert valid["type"] == "object"

    with pytest.raises(ToolSchemaError, match="type='object'"):
        validate_json_schema_object({"type": "string"})

    with pytest.raises(ToolSchemaError, match="unknown properties"):
        validate_json_schema_object({"type": "object", "properties": {}, "required": ["missing"]})

    with pytest.raises(ToolSchemaError, match="properties.path"):
        ToolDefinition(
            id="bad_tool",
            title="Bad tool",
            category="tests",
            description="Invalid nested schema.",
            args_schema={"type": "object", "properties": {"path": "string"}},
        )


def test_exports_xml_prompt_entries_and_openai_native_tool_schemas() -> None:
    read_tool = ToolDefinition(
        id="web_search",
        title="Web search",
        category="research",
        description="Search & summarize the web.",
        args_schema={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        handler_ref="koda.services.tool_dispatcher._handle_web_search",
        access_level="read",
        risk_class="read",
        approval_default="allow",
        idempotency="read_only",
        source="core",
    )

    xml = export_xml_prompt_entries([read_tool])
    assert '<tool id="web_search"' in xml
    assert 'access_level="read"' in xml
    assert "<description>Search &amp; summarize the web.</description>" in xml
    assert '"required":["query"]' in xml

    native = export_openai_tool_schemas([read_tool])
    assert native == [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search & summarize the web.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "Search query"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }
    ]


def test_detects_missing_handler_drift() -> None:
    registry = ToolRegistry.from_core_tools(
        _sample_core_tools(),
        read_tool_ids={"web_search"},
        write_tool_ids={"file_write"},
        handler_ids={"web_search", "file_write"},
    )

    drift = registry.detect_drift(
        handler_ids={"web_search"},
        read_tool_ids={"web_search"},
        write_tool_ids={"file_write"},
    )

    assert drift.ok is False
    assert drift.missing_handlers == ("file_write",)
    assert drift.uncatalogued_handlers == ()
    assert drift.missing_access_metadata == ()
    assert drift.conflicting_access_metadata == ()
    with pytest.raises(ToolRegistryDriftError, match="missing handlers: file_write"):
        drift.raise_if_any()


def test_default_runtime_registry_bridges_dispatcher_and_native_schemas() -> None:
    registry = get_default_tool_registry(
        feature_flags={"fileops": True},
        allowed_tool_ids={"web_search", "file_write"},
    )

    assert registry.require("web_search").args_schema["required"] == ["query"]
    assert registry.require("file_write").approval_default == "allow_with_preview"
    assert registry.require("file_write").args_schema["required"] == ["path", "content"]

    schemas = build_openai_tool_schemas_for_runtime(
        feature_flags={"fileops": True},
        allowed_tool_ids={"web_search", "file_write"},
    )
    assert [item["function"]["name"] for item in schemas] == ["file_write", "web_search"]
    assert get_tool_definition("web_search") is not None


def test_delegate_task_registry_contract_is_schema_first() -> None:
    registry = get_default_tool_registry(
        feature_flags={"inter_agent": True},
        allowed_tool_ids={"task"},
    )

    definition = registry.require("task")
    assert definition.title == "Delegate Task"
    assert definition.category == "agent_comm"
    assert definition.access_level == "write"
    assert definition.risk_class == "code_execution"
    assert definition.approval_default == "require_approval"
    assert definition.idempotency == "idempotent"
    assert definition.args_schema["properties"]["tasks"]["type"] == "array"

    schemas = build_openai_tool_schemas_for_runtime(
        feature_flags={"inter_agent": True},
        allowed_tool_ids={"task"},
    )
    assert [item["function"]["name"] for item in schemas] == ["task"]
