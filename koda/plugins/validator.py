"""Plugin validation utilities."""

from __future__ import annotations

import re

from koda.plugins.registry import PluginManifest

_VALID_TOOL_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_VALID_PLUGIN_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


def validate_manifest(manifest: PluginManifest) -> list[str]:
    """Validate a parsed manifest. Returns list of error strings (empty = valid)."""
    errors = []
    if not _VALID_PLUGIN_NAME.match(manifest.name):
        errors.append(
            f"Invalid plugin name '{manifest.name}'. Must be lowercase alphanumeric with hyphens/underscores."
        )
    if not manifest.tools:
        errors.append("Plugin must define at least one tool.")
    seen_ids: set[str] = set()
    for tool in manifest.tools:
        if not _VALID_TOOL_ID.match(tool.id):
            errors.append(f"Invalid tool ID '{tool.id}'. Must be lowercase alphanumeric with underscores.")
        if tool.id in seen_ids:
            errors.append(f"Duplicate tool ID: '{tool.id}'.")
        seen_ids.add(tool.id)
        if not tool.handler_path or "." not in tool.handler_path:
            errors.append(f"Tool '{tool.id}': handler must be 'module.function' format.")
    if not manifest.plugin_dir.is_dir():
        errors.append(f"Plugin directory does not exist: {manifest.plugin_dir}")
    return errors
