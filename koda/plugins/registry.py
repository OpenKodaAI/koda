"""Plugin registry for dynamic tool management."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from koda.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class PluginToolDef:
    id: str
    title: str
    category: str
    description: str
    handler_path: str  # e.g., "handlers.slack_send"
    read_only: bool = False
    params: dict[str, Any] = field(default_factory=dict)
    integration_id: str | None = None
    access_level: str = "write"


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str
    author: str
    plugin_dir: Path
    tools: list[PluginToolDef] = field(default_factory=list)
    prompt_section: str = ""
    requires: dict[str, Any] = field(default_factory=dict)


ToolHandler = Callable[[dict, Any], Awaitable[Any]]


class PluginRegistry:
    """Dynamic plugin and tool registry."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._tool_to_plugin: dict[str, str] = {}  # tool_id -> plugin_name

    def register(self, manifest: PluginManifest) -> str | None:
        """Register a plugin from a parsed manifest. Returns error or None."""
        if manifest.name in self._plugins:
            return f"Plugin '{manifest.name}' already registered."
        # Check for tool ID conflicts
        for tool in manifest.tools:
            if tool.id in self._handlers:
                return f"Tool ID '{tool.id}' conflicts with plugin '{self._tool_to_plugin.get(tool.id, 'unknown')}'."
        # Load handlers
        for tool in manifest.tools:
            handler = self._load_handler(manifest.plugin_dir, tool.handler_path)
            if handler is None:
                return f"Failed to load handler '{tool.handler_path}' for tool '{tool.id}'."
            self._handlers[tool.id] = handler
            self._tool_to_plugin[tool.id] = manifest.name
        self._plugins[manifest.name] = manifest
        log.info("plugin_registered", name=manifest.name, tools=len(manifest.tools))
        return None

    def unregister(self, plugin_name: str) -> str | None:
        """Unregister a plugin. Returns error or None."""
        manifest = self._plugins.pop(plugin_name, None)
        if not manifest:
            return f"Plugin '{plugin_name}' not found."
        for tool in manifest.tools:
            self._handlers.pop(tool.id, None)
            self._tool_to_plugin.pop(tool.id, None)
        # Remove plugin module from sys.modules
        prefix = f"_koda_plugin_{plugin_name}"
        to_remove = [k for k in sys.modules if k.startswith(prefix)]
        for k in to_remove:
            del sys.modules[k]
        log.info("plugin_unregistered", name=plugin_name)
        return None

    def get_handler(self, tool_id: str) -> ToolHandler | None:
        """Get handler for a tool ID. Returns None if not found."""
        return self._handlers.get(tool_id)

    def get_tool_def(self, tool_id: str) -> PluginToolDef | None:
        """Get tool definition by ID."""
        plugin_name = self._tool_to_plugin.get(tool_id)
        if not plugin_name:
            return None
        manifest = self._plugins.get(plugin_name)
        if not manifest:
            return None
        for tool in manifest.tools:
            if tool.id == tool_id:
                return tool
        return None

    def list_plugins(self) -> list[dict[str, Any]]:
        """List all registered plugins."""
        return [
            {
                "name": m.name,
                "version": m.version,
                "description": m.description,
                "author": m.author,
                "tool_count": len(m.tools),
                "tools": [t.id for t in m.tools],
            }
            for m in self._plugins.values()
        ]

    def list_tools(self, plugin_name: str | None = None) -> list[dict[str, Any]]:
        """List tools, optionally filtered by plugin."""
        results = []
        for name, manifest in self._plugins.items():
            if plugin_name and name != plugin_name:
                continue
            for tool in manifest.tools:
                results.append(
                    {
                        "id": tool.id,
                        "title": tool.title,
                        "category": tool.category,
                        "description": tool.description,
                        "read_only": tool.read_only,
                        "plugin": name,
                    }
                )
        return results

    def get_prompt_sections(self) -> list[str]:
        """Get prompt sections from all registered plugins."""
        return [m.prompt_section for m in self._plugins.values() if m.prompt_section]

    def reload(self, plugin_name: str) -> str | None:
        """Reload a plugin by unregistering and re-registering."""
        manifest = self._plugins.get(plugin_name)
        if not manifest:
            return f"Plugin '{plugin_name}' not found."
        plugin_dir = manifest.plugin_dir
        err = self.unregister(plugin_name)
        if err:
            return err
        from koda.plugins.manifest import parse_manifest

        new_manifest = parse_manifest(plugin_dir / "plugin.yaml")
        if isinstance(new_manifest, str):
            return new_manifest
        return self.register(new_manifest)

    def _load_handler(self, plugin_dir: Path, handler_path: str) -> ToolHandler | None:
        """Load a handler function from a plugin module."""
        parts = handler_path.rsplit(".", 1)
        if len(parts) != 2:
            return None
        module_path, func_name = parts
        # Create a unique module name to avoid conflicts
        plugin_name = plugin_dir.name
        module_name = f"_koda_plugin_{plugin_name}.{module_path}"
        # Add plugin dir to sys.path temporarily
        plugin_dir_str = str(plugin_dir)
        if plugin_dir_str not in sys.path:
            sys.path.insert(0, plugin_dir_str)
        try:
            if module_name in sys.modules:
                del sys.modules[module_name]
            file_path = plugin_dir / f"{module_path.replace('.', '/')}.py"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            handler = getattr(module, func_name, None)
            if handler is None or not callable(handler):
                return None
            return cast(ToolHandler, handler)
        except Exception as e:
            log.warning("plugin_handler_load_failed", handler=handler_path, error=str(e))
            return None
        finally:
            if plugin_dir_str in sys.path:
                sys.path.remove(plugin_dir_str)
