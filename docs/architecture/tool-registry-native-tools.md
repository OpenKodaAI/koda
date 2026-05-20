# ToolRegistry And Native Tools

Phase 1 introduces `tool-definition.v1` as the schema-first source for core
agent tools and provider-native tool schemas.

## Contract

Python definitions live in `koda/services/tool_registry.py`.

`ToolDefinition` fields:

- `id`
- `title`
- `category`
- `description`
- `args_schema`
- `handler_ref`
- `access_level`
- `effect_tags`
- `idempotency`
- `risk_class`
- `approval_default`
- `timeout_seconds`
- `feature_flag`
- `ui_metadata`
- `docs_metadata`
- `schema_version`
- `source`

The runtime registry is built from the existing core tool catalog plus the
compatibility dispatcher maps: `_TOOL_HANDLERS`, `_READ_TOOLS`, and
`_WRITE_TOOLS`. This preserves Phase 1 behavior while giving prompts,
providers, UI, approvals, and tests one contract source.

## Prompt And Provider Exports

The XML prompt includes a versioned `<tool_registry>` block generated from
`ToolRegistry.export_xml_prompt_entries()`.

OpenAI-compatible native schemas are generated with
`build_openai_tool_schemas_for_runtime()`. Providers only receive `tools` when
their capability snapshot reports `supports_native_tool_calls=true`.

Unsupported providers continue through the mandatory XML fallback:

```xml
<agent_cmd tool="web_search">{"query":"example"}</agent_cmd>
```

## Provider Capability Matrix

OpenAI-compatible providers expose:

- `supports_native_tool_calls`
- `supports_streaming_tool_calls`
- `supports_structured_output`
- `supports_json_schema_subset`
- `supports_xml_fallback`

Native tool calls are normalized from `choices[].message.tool_calls` into
`RunResult.tool_uses` with `source="openai_compatible_tool_call"`. The same
queue dispatcher, execution policy, approval, audit, and tool-result path then
handles native and XML calls.

## Validation

Focused tests:

```bash
.venv/bin/python -m pytest tests/test_services/test_tool_registry.py
.venv/bin/python -m pytest tests/test_services/test_openai_compatible_runner.py
.venv/bin/python -m pytest tests/test_services/test_llm_runner.py
.venv/bin/python -m pytest tests/test_services/test_queue_helpers.py::TestPhase1NativeToolHelpers
```

## Rollback

Disable native schemas by not passing `native_tools` to `run_llm`. XML fallback
continues to work because no tool handler was removed and the dispatcher path is
unchanged.
