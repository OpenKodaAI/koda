"""Plugin registry for dynamic tool management."""

from __future__ import annotations

import errno
import importlib
import importlib.util
import os
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
    # The verified bytes of a skill package's files, by path under plugin_dir. When set, the
    # handlers load from these bytes only, never from a later read of the files (D-292).
    sources: dict[str, bytes] | None = None


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
            handler = self._load_handler(manifest, tool.handler_path)
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
        prefix = _plugin_module_prefix(plugin_name)
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
        if manifest.sources is not None:
            # A skill package registers again only from its lock, which verifies its files first (D-292).
            return f"Plugin '{plugin_name}' is a skill package: plugin_reload reloads it from its lock."
        plugin_dir = manifest.plugin_dir
        err = self.unregister(plugin_name)
        if err:
            return err
        from koda.plugins.manifest import parse_manifest

        new_manifest = parse_manifest(plugin_dir / "plugin.yaml")
        if isinstance(new_manifest, str):
            return new_manifest
        return self.register(new_manifest)

    def _load_handler(self, manifest: PluginManifest, handler_path: str) -> ToolHandler | None:
        """Load a handler function from a plugin module.

        The handler file must resolve inside the plugin directory; an absolute path, a
        traversal or a symlink out of the plugin is rejected before anything is
        imported. The source is then read from a handle opened by walking down
        from the plugin directory without following a symlink, so a file or a
        directory swapped in after the check is not loaded (D-270); a skill
        package's handler source is the verified bytes in ``manifest.sources``
        hashed at the handler's path, wherever a symlink swapped in there points,
        or, when none were hashed there, at its real path inside the package, which
        a directory symlink inside the package leads to (D-309); a file missing at
        both is not loaded (D-292). The module
        gets a flat name, with no parent package, so a relative import in it fails
        instead of resolving against another package; the name starts with the
        plugin's prefix, which ``unregister`` removes (D-291). ``sys.path`` is left
        untouched.
        """
        from koda.skills._package import _safe_child_path, _SourceOnlyLoader

        plugin_dir = manifest.plugin_dir

        parts = handler_path.rsplit(".", 1)
        if len(parts) != 2:
            return None
        module_path, func_name = parts
        relative_path = f"{module_path.replace('.', '/')}.py"
        file_path = _safe_child_path(plugin_dir, relative_path)
        if file_path is None:
            log.warning("plugin_handler_path_rejected", handler=handler_path, plugin_dir=str(plugin_dir))
            return None
        # Create a unique module name to avoid conflicts
        module_name = _plugin_module_prefix(manifest.name) + module_path.replace(".", "/")
        try:
            if manifest.sources is not None:
                source = manifest.sources.get(os.path.normpath(relative_path))
                if source is None:
                    # Declared through a directory symlink inside the package: the bytes hashed
                    # at the handler's real path, which file_path is (D-309).
                    source = manifest.sources.get(str(file_path.relative_to(plugin_dir.resolve())))
                if source is None:
                    log.warning("plugin_handler_not_verified", handler=handler_path, plugin_dir=str(plugin_dir))
                    return None
            else:
                source = _read_checked_source(plugin_dir, file_path)
            if source is None:
                log.warning("plugin_handler_path_changed", handler=handler_path, plugin_dir=str(plugin_dir))
                return None
            if module_name in sys.modules:
                del sys.modules[module_name]
            loader = _SourceOnlyLoader(module_name, str(file_path), source=source)
            spec = importlib.util.spec_from_file_location(module_name, file_path, loader=loader)
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


def _plugin_module_prefix(plugin_name: str) -> str:
    """The start of a plugin's handler module names, which hold no dot, so there is no parent package.

    Loading and unregistering both derive it from the manifest name (D-291), which is unique
    in the registry. A '/' ends the plugin's part and separates the module's parts; the
    dots and slashes of the plugin name are escaped, so two plugins' names never meet and
    one prefix matches the modules of one plugin only.
    """
    return "_koda_plugin_" + plugin_name.replace("%", "%25").replace(".", "%2E").replace("/", "%2F") + "/"


def _read_checked_source(plugin_dir: Path, file_path: Path) -> bytes | None:
    """Read *file_path*, which the path check resolved inside *plugin_dir*, or return None.

    The file is opened by walking down from *plugin_dir* one component at a time, each
    opened relative to the directory before it and never through a symlink. The bytes
    therefore come from the file at the checked place inside the plugin: when a file or a
    directory on the way is swapped for a symlink after the check, the open fails and
    None is returned, whatever a later lookup of the path would show.
    """
    root = plugin_dir.resolve()
    *directories, name = file_path.relative_to(root).parts
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in directories:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            return None
        raise
    finally:
        os.close(fd)
    with os.fdopen(file_fd, "rb") as handle:
        return handle.read()
