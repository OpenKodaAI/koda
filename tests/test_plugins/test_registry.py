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
        module = sys.modules["_koda_plugin_demo/handlers"]
        assert str(plugin_dir) not in module.SYS_PATH_AT_IMPORT
        assert reg.get_handler("demo_run") is not None
        reg.unregister("demo")


class TestHandlerLoadIsAtomic:
    """D-270: the file checked is the file loaded, under a flat module name."""

    @pytest.mark.parametrize("swap", ["file", "parent_directory"])
    def test_a_handler_swapped_for_an_outside_file_after_the_check_does_not_run(
        self, tmp_path: Path, swap: str
    ) -> None:
        import os

        from koda.skills import _package

        outside = _write_evil(tmp_path)
        (outside / "handlers.py").write_text(_EVIL_SOURCE.replace("def fn", "def run"), encoding="utf-8")
        plugin_dir = _write_plugin(tmp_path, "sub.handlers.run")
        (plugin_dir / "sub").mkdir()
        (plugin_dir / "sub" / "handlers.py").write_text(_HANDLER_SOURCE, encoding="utf-8")
        real_check = _package._safe_child_path
        swapped: list[bool] = []

        def check_then_swap(root: Path, value: str) -> Path | None:
            result = real_check(root, value)
            if not swapped:
                swapped.append(True)
                if swap == "file":
                    (plugin_dir / "sub" / "link").symlink_to(outside / "handlers.py")
                    os.replace(plugin_dir / "sub" / "link", plugin_dir / "sub" / "handlers.py")
                else:
                    (plugin_dir / "sub").rename(plugin_dir / "sub_checked")
                    (plugin_dir / "sub").symlink_to(outside, target_is_directory=True)
            return result

        with patch.object(_package, "_safe_child_path", check_then_swap):
            handler_fn = PluginRegistry()._load_handler(plugin_dir, "sub.handlers.run")

        assert swapped
        assert handler_fn is None
        assert not (outside / "pwned").exists()

    def test_a_parent_directory_flipped_back_for_each_later_path_lookup_still_does_not_load_outside_code(
        self, tmp_path: Path
    ) -> None:
        """The load trusts the file it opened, not a second lookup of the path, which a flip can satisfy."""
        from koda.skills import _package

        outside = _write_evil(tmp_path)
        (outside / "handlers.py").write_text(_EVIL_SOURCE.replace("def fn", "def run"), encoding="utf-8")
        plugin_dir = _write_plugin(tmp_path, "sub.handlers.run")
        (plugin_dir / "sub").mkdir()
        (plugin_dir / "sub" / "handlers.py").write_text(_HANDLER_SOURCE, encoding="utf-8")
        real_check = _package._safe_child_path
        checks: list[Path | None] = []

        def flipping_check(root: Path, value: str) -> Path | None:
            # Every check sees the real directory; right after it, `sub` points outside again.
            if checks:
                (plugin_dir / "sub").unlink()
                (plugin_dir / "sub_real").rename(plugin_dir / "sub")
            checks.append(real_check(root, value))
            (plugin_dir / "sub").rename(plugin_dir / "sub_real")
            (plugin_dir / "sub").symlink_to(outside, target_is_directory=True)
            return checks[-1]

        with patch.object(_package, "_safe_child_path", flipping_check):
            handler_fn = PluginRegistry()._load_handler(plugin_dir, "sub.handlers.run")

        assert checks
        assert handler_fn is None
        assert not (outside / "pwned").exists()

    def test_the_handler_module_has_a_flat_name_so_a_relative_import_cannot_reach_another_package(
        self, tmp_path: Path
    ) -> None:
        import types

        outside = _write_evil(tmp_path)
        (outside / "helper.py").write_text(_EVIL_SOURCE, encoding="utf-8")
        plugin_dir = _write_plugin(tmp_path, "handlers.run")
        (plugin_dir / "handlers.py").write_text(
            "from . import helper\n\n\nasync def run(params, ctx):\n    return 'ok'\n", encoding="utf-8"
        )
        # A package that happens to sit at the dotted name the handler used to get.
        lookalike = types.ModuleType("_koda_plugin_demo")
        lookalike.__path__ = [str(outside)]
        with patch.dict(sys.modules, {"_koda_plugin_demo": lookalike}):
            handler_fn = PluginRegistry()._load_handler(plugin_dir, "handlers.run")
            sys.modules.pop("_koda_plugin_demo.helper", None)

        assert handler_fn is None
        assert not (outside / "pwned").exists()

    def test_handler_modules_are_registered_under_flat_names_and_removed_on_unregister(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from koda.plugins.manifest import parse_manifest

        for name in [name for name in sys.modules if name.startswith("_koda_plugin_demo")]:
            monkeypatch.delitem(sys.modules, name)
        plugin_dir = _write_plugin(tmp_path, "sub.handlers.run")
        (plugin_dir / "sub").mkdir()
        (plugin_dir / "sub" / "handlers.py").write_text(_HANDLER_SOURCE, encoding="utf-8")
        manifest = parse_manifest(plugin_dir / "plugin.yaml")
        assert not isinstance(manifest, str)
        reg = PluginRegistry()

        assert reg.register(manifest) is None
        names = [name for name in sys.modules if name.startswith("_koda_plugin_demo")]
        assert names == ["_koda_plugin_demo/sub/handlers"]
        assert sys.modules[names[0]].__package__ == ""

        reg.unregister("demo")
        assert not [name for name in sys.modules if name.startswith("_koda_plugin_demo")]

    def test_handler_module_names_stay_unique_when_plugin_or_module_names_contain_double_underscores(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for name in [name for name in sys.modules if name.startswith("_koda_plugin_foo")]:
            monkeypatch.delitem(sys.modules, name)
        foo = tmp_path / "plugins" / "foo"
        (foo / "a").mkdir(parents=True)
        foo_bar = tmp_path / "plugins" / "foo__bar"
        foo_bar.mkdir()
        files = [foo / "bar__x.py", foo / "a" / "b.py", foo / "a__b.py", foo_bar / "x.py"]
        for path in files:
            path.write_text(_HANDLER_SOURCE, encoding="utf-8")

        def manifest(name: str, plugin_dir: Path, handlers: list[str]) -> PluginManifest:
            tools = [
                PluginToolDef(id=f"{name}_{index}", title="t", category="test", description="d", handler_path=handler)
                for index, handler in enumerate(handlers)
            ]
            return PluginManifest(
                name=name, version="1.0.0", description="", author="", plugin_dir=plugin_dir, tools=tools
            )

        reg = PluginRegistry()
        assert reg.register(manifest("foo", foo, ["bar__x.run", "a.b.run", "a__b.run"])) is None
        assert reg.register(manifest("foo__bar", foo_bar, ["x.run"])) is None

        def loaded_files() -> set[str]:
            return {
                str(Path(str(module.__file__)).resolve())
                for name, module in sys.modules.items()
                if name.startswith("_koda_plugin_foo")
            }

        assert loaded_files() == {str(path.resolve()) for path in files}

        reg.unregister("foo")
        assert loaded_files() == {str((foo_bar / "x.py").resolve())}
        reg.unregister("foo__bar")
        assert loaded_files() == set()
