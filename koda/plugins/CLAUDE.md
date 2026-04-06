# Plugin System Guide

Enables dynamic tool registration via YAML manifests.

## Key Files
- `registry.py` -- PluginRegistry (register/unregister/reload/lookup)
- `manifest.py` -- Parse plugin.yaml manifests
- `validator.py` -- Validate plugin structure

## Adding a Plugin
1. Create a directory with `plugin.yaml` manifest
2. Define tools with handlers pointing to Python modules
3. Install via `plugin_install` tool or place in `PLUGIN_DIRS`
4. See `plugins/example-hello/` for a working example

## Handler Pattern
```python
async def my_handler(params: dict, ctx) -> AgentToolResult:
    return AgentToolResult(tool="my_tool", success=True, output="result")
```

## Security
Plugin handlers execute in the main process. Only install trusted plugins.
