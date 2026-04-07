"""Tests for plugin validation."""

from koda.plugins.registry import PluginManifest, PluginToolDef
from koda.plugins.validator import validate_manifest


class TestValidateManifest:
    def test_valid(self, tmp_path):  # type: ignore[no-untyped-def]
        manifest = PluginManifest(
            name="test-plugin",
            version="1.0",
            description="ok",
            author="me",
            plugin_dir=tmp_path,
            tools=[PluginToolDef(id="my_tool", title="T", category="c", description="d", handler_path="mod.func")],
        )
        assert validate_manifest(manifest) == []

    def test_invalid_name(self, tmp_path):  # type: ignore[no-untyped-def]
        manifest = PluginManifest(
            name="INVALID!",
            version="1",
            description="",
            author="",
            plugin_dir=tmp_path,
            tools=[PluginToolDef(id="t", title="T", category="c", description="d", handler_path="m.f")],
        )
        errors = validate_manifest(manifest)
        assert any("name" in e.lower() for e in errors)

    def test_no_tools(self, tmp_path):  # type: ignore[no-untyped-def]
        manifest = PluginManifest(name="empty", version="1", description="", author="", plugin_dir=tmp_path, tools=[])
        errors = validate_manifest(manifest)
        assert any("tool" in e.lower() for e in errors)

    def test_invalid_tool_id(self, tmp_path):  # type: ignore[no-untyped-def]
        manifest = PluginManifest(
            name="test",
            version="1",
            description="",
            author="",
            plugin_dir=tmp_path,
            tools=[PluginToolDef(id="BAD-ID!", title="T", category="c", description="d", handler_path="m.f")],
        )
        errors = validate_manifest(manifest)
        assert any("tool id" in e.lower() for e in errors)

    def test_duplicate_tool_ids(self, tmp_path):  # type: ignore[no-untyped-def]
        manifest = PluginManifest(
            name="test",
            version="1",
            description="",
            author="",
            plugin_dir=tmp_path,
            tools=[
                PluginToolDef(id="dup", title="T", category="c", description="d", handler_path="m.f"),
                PluginToolDef(id="dup", title="T2", category="c", description="d", handler_path="m.g"),
            ],
        )
        errors = validate_manifest(manifest)
        assert any("duplicate" in e.lower() for e in errors)
