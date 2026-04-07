"""Tests for plugin registry."""

from pathlib import Path

from koda.plugins.registry import PluginManifest, PluginRegistry, PluginToolDef


def _make_manifest(name: str = "test-plugin", tools: list[PluginToolDef] | None = None) -> PluginManifest:
    if tools is None:
        tools = [
            PluginToolDef(
                id="test_tool",
                title="Test",
                category="test",
                description="A test tool",
                handler_path="handlers.test_handler",
            )
        ]
    return PluginManifest(
        name=name,
        version="1.0.0",
        description="Test",
        author="test",
        plugin_dir=Path("/tmp/test-plugin"),
        tools=tools,
    )


class TestPluginRegistry:
    def test_register(self) -> None:
        reg = PluginRegistry()
        # Can't actually register because handler loading will fail on fake path
        manifest = _make_manifest()
        # Handler loading will fail, so this returns an error
        err = reg.register(manifest)
        assert err is not None  # expected: handler load fails

    def test_list_empty(self) -> None:
        reg = PluginRegistry()
        assert reg.list_plugins() == []

    def test_get_handler_missing(self) -> None:
        reg = PluginRegistry()
        assert reg.get_handler("nonexistent") is None

    def test_unregister_missing(self) -> None:
        reg = PluginRegistry()
        err = reg.unregister("nonexistent")
        assert err is not None

    def test_list_tools_empty(self) -> None:
        reg = PluginRegistry()
        assert reg.list_tools() == []

    def test_get_prompt_sections_empty(self) -> None:
        reg = PluginRegistry()
        assert reg.get_prompt_sections() == []

    def test_get_tool_def_missing(self) -> None:
        reg = PluginRegistry()
        assert reg.get_tool_def("nonexistent") is None

    def test_reload_missing(self) -> None:
        reg = PluginRegistry()
        err = reg.reload("nonexistent")
        assert err is not None
