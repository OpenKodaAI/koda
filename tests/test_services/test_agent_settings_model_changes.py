"""Model changes made through the agent-local setters reach the running agent (M6-E3-T2, D-068).

The supervisor starts each agent worker with the published snapshot inlined in its
environment (``AGENT_SPEC_JSON`` / ``AGENT_MODEL_POLICY_JSON``), and a non-forced
``get_agent_runtime_settings`` prefers that inline snapshot. A setter that only writes
the draft therefore changes nothing for the running worker. Every setter publishes, so
the supervisor restarts the worker on the new version, whose snapshot has the change.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from koda.services import agent_settings as module

_OPTIONS = [
    {"provider_id": "claude", "model_id": "claude-sonnet-4-6"},
    {"provider_id": "claude", "model_id": "claude-opus-4-6"},
    {"provider_id": "codex", "model_id": "gpt-5.4-mini"},
]


@pytest.fixture
def control_plane(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {
        "policy": {
            "default_provider": "claude",
            "default_models": {"claude": "claude-sonnet-4-6", "codex": "gpt-5.4-mini"},
            "functional_defaults": {"general": {"provider_id": "claude", "model_id": "claude-sonnet-4-6"}},
        },
        "published": [],
    }

    class FakeManager:
        def get_section(self, agent_id: str, section: str) -> dict[str, Any]:
            assert section == "providers"
            return {"data": {"model_policy": copy.deepcopy(state["policy"])}}

        def put_model_policy(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            state["policy"] = copy.deepcopy(payload["policy"])
            return payload

        def publish_agent(self, agent_id: str) -> dict[str, Any]:
            # What the new version carries: the supervisor restarts the worker with it.
            state["published"].append((agent_id, copy.deepcopy(state["policy"]["functional_defaults"]["general"])))
            return {"agent_id": agent_id, "version": len(state["published"]) + 1}

    def effective(agent_id: str) -> dict[str, Any]:
        general = state["policy"]["functional_defaults"]["general"]
        return {
            "agent_id": agent_id,
            "default_provider": general["provider_id"],
            "general_model": general["model_id"],
            "default_models_by_provider": dict(state["policy"]["default_models"]),
            "functional_defaults": copy.deepcopy(state["policy"]["functional_defaults"]),
            "selectable_function_options": {"general": copy.deepcopy(_OPTIONS)},
        }

    module.invalidate_agent_settings_cache()
    monkeypatch.setenv("AGENT_ID", "KODA")
    monkeypatch.delenv("AGENT_SPEC_JSON", raising=False)
    # The snapshot the supervisor inlined when it started this worker.
    monkeypatch.setenv("AGENT_MODEL_POLICY_JSON", json.dumps(state["policy"]))
    monkeypatch.setattr(module, "ControlPlaneManager", FakeManager)
    monkeypatch.setattr(module, "_effective_agent_runtime_settings", effective)
    yield state
    module.invalidate_agent_settings_cache()


def test_general_model_change_is_published(control_plane: dict[str, Any]) -> None:
    updated = module.set_agent_general_model("claude", "claude-opus-4-6")

    assert updated is not None and updated["general_model"] == "claude-opus-4-6"
    assert control_plane["published"] == [("KODA", {"provider_id": "claude", "model_id": "claude-opus-4-6"})]


def test_general_provider_change_is_published(control_plane: dict[str, Any]) -> None:
    updated = module.set_agent_general_provider("codex")

    assert updated is not None and updated["default_provider"] == "codex"
    assert control_plane["published"] == [("KODA", {"provider_id": "codex", "model_id": "gpt-5.4-mini"})]


def test_functional_default_change_is_published_by_default(control_plane: dict[str, Any]) -> None:
    updated = module.set_agent_functional_default("general", "claude", "claude-opus-4-6")

    assert updated is not None and updated["general_model"] == "claude-opus-4-6"
    assert control_plane["published"] == [("KODA", {"provider_id": "claude", "model_id": "claude-opus-4-6"})]
