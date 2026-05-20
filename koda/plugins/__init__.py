"""Plugin system for dynamic tool registration."""

from __future__ import annotations

from koda.plugins.registry import PluginRegistry

_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


__all__ = ["get_registry", "PluginRegistry"]
