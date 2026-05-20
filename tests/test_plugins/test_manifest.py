"""Tests for manifest parsing."""

from koda.plugins.manifest import parse_manifest


class TestParseManifest:
    def test_missing_file(self, tmp_path):  # type: ignore[no-untyped-def]
        result = parse_manifest(tmp_path / "nonexistent.yaml")
        assert isinstance(result, str)
        assert "not found" in result

    def test_valid_manifest(self, tmp_path):  # type: ignore[no-untyped-def]
        manifest_file = tmp_path / "plugin.yaml"
        manifest_file.write_text(
            """
name: test-plugin
version: "1.0.0"
description: A test plugin
author: test
tools:
  - id: test_tool
    title: Test Tool
    handler: handlers.test_func
    description: A test tool
"""
        )
        result = parse_manifest(manifest_file)
        assert not isinstance(result, str), f"Parse error: {result}"
        assert result.name == "test-plugin"
        assert len(result.tools) == 1
        assert result.tools[0].id == "test_tool"

    def test_missing_name(self, tmp_path):  # type: ignore[no-untyped-def]
        manifest_file = tmp_path / "plugin.yaml"
        manifest_file.write_text("version: '1.0'\ntools: []")
        result = parse_manifest(manifest_file)
        assert isinstance(result, str)
        assert "name" in result

    def test_tool_missing_handler(self, tmp_path):  # type: ignore[no-untyped-def]
        manifest_file = tmp_path / "plugin.yaml"
        manifest_file.write_text(
            """
name: test
tools:
  - id: broken_tool
    title: Broken
"""
        )
        result = parse_manifest(manifest_file)
        assert isinstance(result, str)
        assert "handler" in result
