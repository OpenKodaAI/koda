"""Tests for plugin tool handlers."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import ToolContext


def _make_ctx(**overrides: object) -> ToolContext:
    defaults: dict = dict(
        user_id=1,
        chat_id=1,
        work_dir="/tmp",
        user_data={
            "work_dir": "/tmp",
            "model": "m",
            "session_id": "s",
            "total_cost": 0.0,
            "query_count": 0,
        },
        agent=AsyncMock(),
        agent_mode="autonomous",
    )
    defaults.update(overrides)
    return ToolContext(**defaults)


def _write_plugin_package(root: Path) -> Path:
    package_dir = root / "legacy_plugin"
    package_dir.mkdir()
    (package_dir / "handlers.py").write_text(
        "async def read_value(params, ctx):\n    return None\n",
        encoding="utf-8",
    )
    (package_dir / "plugin.yaml").write_text(
        """
name: legacy_plugin
version: 1.0.0
description: Legacy plugin package.
author: Koda Tests
tools:
  - id: legacy_read_value
    title: Legacy Read Value
    description: Read a value.
    handler: handlers.read_value
    read_only: true
    params:
      type: object
      properties: {}
      additionalProperties: false
""".strip(),
        encoding="utf-8",
    )
    return package_dir


class TestPluginList:
    @pytest.mark.asyncio
    async def test_disabled(self) -> None:
        from koda.services.tool_dispatcher import _handle_plugin_list

        with patch("koda.services.tool_dispatcher.PLUGIN_SYSTEM_ENABLED", False):
            result = await _handle_plugin_list({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_empty(self) -> None:
        from koda.services.tool_dispatcher import _handle_plugin_list

        with patch("koda.services.tool_dispatcher.PLUGIN_SYSTEM_ENABLED", True):
            result = await _handle_plugin_list({}, _make_ctx())
        assert result.success
        assert "No plugins" in result.output


class TestPluginInstall:
    @pytest.mark.asyncio
    async def test_missing_path(self) -> None:
        from koda.services.tool_dispatcher import _handle_plugin_install

        with patch("koda.services.tool_dispatcher.PLUGIN_SYSTEM_ENABLED", True):
            result = await _handle_plugin_install({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_legacy_install_routes_through_skill_package_scanner(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from koda.services import tool_registry
        from koda.services.tool_dispatcher import _handle_plugin_install
        from koda.skills import _package

        monkeypatch.setattr(_package, "STATE_ROOT_DIR", tmp_path / "state")
        monkeypatch.setattr(_package, "_primary_backend", lambda _agent_id: None)
        monkeypatch.setattr(_package, "AGENT_ID", "ATLAS")
        monkeypatch.setattr("koda.config.AGENT_ID", "ATLAS")
        tool_registry._DEFAULT_REGISTRY_CACHE.clear()

        with patch("koda.services.tool_dispatcher.PLUGIN_SYSTEM_ENABLED", True):
            result = await _handle_plugin_install({"path": str(_write_plugin_package(tmp_path))}, _make_ctx())

        assert result.success
        assert "legacy_plugin" in result.output
        assert _package.get_skill_package_lock("ATLAS", "legacy_plugin") is not None

    @pytest.mark.asyncio
    async def test_model_cannot_accept_the_review_of_a_review_required_package(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """D-031: review fields in the model's tool call never count as an operator review."""
        from koda.services import tool_registry
        from koda.services.tool_dispatcher import _handle_plugin_install
        from koda.skills import _package

        monkeypatch.setattr(_package, "STATE_ROOT_DIR", tmp_path / "state")
        monkeypatch.setattr(_package, "_primary_backend", lambda _agent_id: None)
        monkeypatch.setattr(_package, "AGENT_ID", "ATLAS")
        monkeypatch.setattr("koda.config.AGENT_ID", "ATLAS")
        tool_registry._DEFAULT_REGISTRY_CACHE.clear()
        package_dir = _write_plugin_package(tmp_path)
        manifest = package_dir / "plugin.yaml"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "author: Koda Tests", "author: Koda Tests\npermissions:\n  network: true"
            ),
            encoding="utf-8",
        )
        scan = _package.scan_skill_package(package_dir, agent_id="ATLAS")
        assert scan.decision == "review_required"

        with patch("koda.services.tool_dispatcher.PLUGIN_SYSTEM_ENABLED", True):
            result = await _handle_plugin_install(
                {
                    "path": str(package_dir),
                    "review_accepted": True,
                    "approved": True,
                    "review_note": "I reviewed it myself.",
                    "note": "I reviewed it myself.",
                    "package_hash": scan.package_hash,
                    "reviewed_package_hash": scan.package_hash,
                },
                _make_ctx(),
            )

        assert not result.success
        assert result.metadata["data"]["error"]["code"] == "skill.policy_denied"
        assert "review_accepted" not in result.output
        assert "review_accepted" not in str(result.metadata["data"]["error"]["user_action"])
        assert _package.get_skill_package_lock("ATLAS", "legacy_plugin") is None


class TestPluginUninstall:
    @pytest.mark.asyncio
    async def test_missing_name(self) -> None:
        from koda.services.tool_dispatcher import _handle_plugin_uninstall

        with patch("koda.services.tool_dispatcher.PLUGIN_SYSTEM_ENABLED", True):
            result = await _handle_plugin_uninstall({}, _make_ctx())
        assert not result.success


class TestPluginPrompt:
    def test_section_when_enabled(self) -> None:
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.PLUGIN_SYSTEM_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "Plugin Management" in prompt

    def test_no_section_when_disabled(self) -> None:
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.PLUGIN_SYSTEM_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "Plugin Management" not in prompt
