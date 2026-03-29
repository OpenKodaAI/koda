"""Tests for runtime prompt contract selection in config."""

from __future__ import annotations

import importlib

import pytest


def test_config_uses_only_compiled_prompt_contract() -> None:
    import koda.config as config_module

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setenv("AGENT_COMPILED_PROMPT_TEXT", "CONTROL-PLANE PROMPT")

        reloaded = importlib.reload(config_module)

        assert reloaded.AGENT_COMPILED_PROMPT_TEXT == "CONTROL-PLANE PROMPT"
        assert reloaded.DEFAULT_SYSTEM_PROMPT.startswith("CONTROL-PLANE PROMPT")
    finally:
        monkeypatch.undo()
        importlib.reload(config_module)
