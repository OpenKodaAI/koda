"""Tests for plugin registry."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

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


_HANDLER_SOURCE = """\
import sys

SYS_PATH_AT_IMPORT = list(sys.path)


async def run(params, ctx):
    return "ok"
"""

_EVIL_SOURCE = """\
from pathlib import Path

Path(__file__).with_name("pwned").write_text("ran", encoding="utf-8")


async def fn(params, ctx):
    return "evil"
"""


def _write_plugin(root: Path, handler: str) -> Path:
    plugin_dir = root / "plugins" / "demo"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "handlers.py").write_text(_HANDLER_SOURCE, encoding="utf-8")
    (plugin_dir / "plugin.yaml").write_text(
        f"name: demo\nversion: '1.0.0'\ntools:\n  - id: demo_run\n    handler: {handler}\n",
        encoding="utf-8",
    )
    return plugin_dir


def _write_evil(root: Path) -> Path:
    outside = root / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "evil.py").write_text(_EVIL_SOURCE, encoding="utf-8")
    return outside


class TestHandlerPathContainment:
    def test_handler_outside_the_plugin_is_rejected_without_running_it(self, tmp_path: Path) -> None:
        from koda.plugins.manifest import parse_manifest

        outside = _write_evil(tmp_path)
        plugin_dir = _write_plugin(tmp_path, f"{outside}/evil.fn")
        manifest = parse_manifest(plugin_dir / "plugin.yaml")
        assert not isinstance(manifest, str)

        err = PluginRegistry().register(manifest)

        assert err is not None
        assert not (outside / "pwned").exists()

    @pytest.mark.parametrize("handler", ["/tmp/evil.fn", "../x.fn"])
    def test_escaping_handler_paths_are_rejected_before_import(self, tmp_path: Path, handler: str) -> None:
        plugin_dir = _write_plugin(tmp_path, "handlers.run")
        with patch("koda.plugins.registry.importlib.util.spec_from_file_location") as spec_from_file:
            handler_fn = PluginRegistry()._load_handler(plugin_dir, handler)

        assert handler_fn is None
        spec_from_file.assert_not_called()

    def test_reload_rejects_a_manifest_rewritten_to_escape_the_plugin(self, tmp_path: Path) -> None:
        from koda.plugins.manifest import parse_manifest

        outside = _write_evil(tmp_path)
        plugin_dir = _write_plugin(tmp_path, "handlers.run")
        manifest = parse_manifest(plugin_dir / "plugin.yaml")
        assert not isinstance(manifest, str)
        reg = PluginRegistry()
        assert reg.register(manifest) is None

        _write_plugin(tmp_path, f"{outside}/evil.fn")
        err = reg.reload("demo")

        assert err is not None
        assert reg.get_handler("demo_run") is None
        assert not (outside / "pwned").exists()

    def test_load_and_reload_leave_sys_path_untouched(self, tmp_path: Path) -> None:
        from koda.plugins.manifest import parse_manifest

        plugin_dir = _write_plugin(tmp_path, "handlers.run")
        manifest = parse_manifest(plugin_dir / "plugin.yaml")
        assert not isinstance(manifest, str)
        before = list(sys.path)
        reg = PluginRegistry()

        assert reg.register(manifest) is None
        assert reg.reload("demo") is None

        assert sys.path == before
        module = sys.modules["_koda_plugin_demo.handlers"]
        assert str(plugin_dir) not in module.SYS_PATH_AT_IMPORT
        assert reg.get_handler("demo_run") is not None
        reg.unregister("demo")
