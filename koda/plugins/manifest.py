"""Plugin manifest parser and validator."""

from __future__ import annotations

from pathlib import Path

from koda.plugins.registry import PluginManifest, PluginToolDef


def parse_manifest(path: Path) -> PluginManifest | str:
    """Parse a plugin.yaml manifest. Returns PluginManifest or error string."""
    import yaml

    if not path.exists():
        return f"Manifest not found: {path}"
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        return f"Failed to parse manifest: {e}"

    if not isinstance(data, dict):
        return "Manifest must be a YAML mapping."

    # Required fields
    name = data.get("name", "").strip()
    if not name:
        return "Manifest missing required field: 'name'."
    version = data.get("version", "0.0.0")
    description = data.get("description", "")
    author = data.get("author", "unknown")

    # Parse tools
    tools = []
    for tool_data in data.get("tools", []):
        if not isinstance(tool_data, dict):
            return f"Each tool must be a mapping, got: {type(tool_data).__name__}"
        tool_id = tool_data.get("id", "").strip()
        if not tool_id:
            return "Tool missing required field: 'id'."
        handler = tool_data.get("handler", "").strip()
        if not handler:
            return f"Tool '{tool_id}' missing required field: 'handler'."
        tools.append(
            PluginToolDef(
                id=tool_id,
                title=tool_data.get("title", tool_id),
                category=tool_data.get("category", "plugin"),
                description=tool_data.get("description", ""),
                handler_path=handler,
                read_only=bool(tool_data.get("read_only", False)),
                params=tool_data.get("params", {}),
                integration_id=tool_data.get("integration_id"),
                access_level=tool_data.get("access_level", "write"),
            )
        )

    return PluginManifest(
        name=name,
        version=str(version),
        description=description,
        author=author,
        plugin_dir=path.parent,
        tools=tools,
        prompt_section=data.get("prompt_section", ""),
        requires=data.get("requires", {}),
    )
