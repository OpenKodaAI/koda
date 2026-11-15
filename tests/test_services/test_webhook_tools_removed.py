"""The webhook and ``event_wait`` tools are gone (M4-E1-T10, D-067).

No HTTP route ever delivered an event to the webhook manager, so the tools
could register paths but ``event_wait`` always timed out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import koda
from koda.agent_contract import CORE_TOOL_CATALOG
from koda.control_plane import execution_policy
from koda.services import tool_dispatcher
from koda.services.tool_prompt import build_agent_tools_prompt
from koda.squads import capabilities

_REMOVED_TOOLS = ("webhook_register", "webhook_unregister", "webhook_list", "event_wait")
_KODA_ROOT = Path(koda.__file__).parent


def test_tools_are_absent_from_the_agent_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    # The old switch, if an operator still sets it, no longer adds anything.
    monkeypatch.setattr("koda.services.tool_prompt.WEBHOOK_ENABLED", True, raising=False)

    prompt = build_agent_tools_prompt(feature_flags={"webhooks": True})

    assert "Webhook" not in prompt
    for tool in _REMOVED_TOOLS:
        assert tool not in prompt


@pytest.mark.parametrize("tool", _REMOVED_TOOLS)
def test_tools_have_no_dispatcher_handler_or_catalog_entry(tool: str) -> None:
    assert tool not in tool_dispatcher._TOOL_HANDLERS
    assert tool not in tool_dispatcher._READ_TOOLS
    assert tool not in tool_dispatcher._WRITE_TOOLS
    assert tool not in CORE_TOOL_CATALOG


def test_webhook_manager_is_gone_and_unreferenced() -> None:
    assert not (_KODA_ROOT / "services" / "webhook_manager.py").exists()
    referencing = [
        str(path.relative_to(_KODA_ROOT))
        for path in _KODA_ROOT.rglob("*.py")
        if "webhook_manager" in path.read_text(encoding="utf-8")
    ]
    assert referencing == []


def test_category_maps_no_longer_name_a_webhook_category() -> None:
    assert "webhook_" not in capabilities._TOOL_PREFIX_CATEGORY
    assert capabilities._infer_tool_category("webhook_list") == "tool"
    assert execution_policy._tool_family("webhook_list") != "webhook"
