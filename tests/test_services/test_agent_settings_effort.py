"""Tests for the effort cascade resolver in agent_settings."""

from __future__ import annotations

import copy
import json

from koda.services.agent_settings import (
    _effort_default_from_general_settings,
    _tts_enabled_from_general_settings,
    get_agent_runtime_settings,
    invalidate_agent_settings_cache,
    resolve_effort,
)


def test_effort_default_reads_from_values_models_block() -> None:
    """Ensures we read the modern API shape, not the legacy DB section shape."""
    settings = {
        "values": {
            "models": {"effort_default": {"provider_id": "codex", "model_id": "gpt-5", "value": "high"}},
            "providers": {"effort_defaults": {"WRONG": "should-not-leak"}},
        }
    }
    assert _effort_default_from_general_settings(settings) == {
        "provider_id": "codex",
        "model_id": "gpt-5",
        "value": "high",
    }


def test_effort_default_returns_empty_when_missing() -> None:
    assert _effort_default_from_general_settings({}) == {}
    assert _effort_default_from_general_settings({"values": {"models": {}}}) == {}


def test_tts_enabled_prefers_current_general_settings_over_snapshot_env() -> None:
    settings = {
        "values": {
            "resources": {
                "integrations": {
                    "tts_enabled": True,
                },
            },
        },
    }
    snapshot = {"env": {"TTS_ENABLED": "false"}}

    assert _tts_enabled_from_general_settings(settings, snapshot) is True


def test_tts_enabled_falls_back_to_snapshot_env_when_missing() -> None:
    assert _tts_enabled_from_general_settings({}, {"env": {"TTS_ENABLED": "false"}}) is False


def test_runtime_settings_uses_inline_voice_snapshot(monkeypatch) -> None:
    invalidate_agent_settings_cache()
    monkeypatch.setenv("AGENT_ID", "KODA")
    monkeypatch.setenv("TTS_ENABLED", "false")
    monkeypatch.setenv("TTS_DEFAULT_VOICE", "pf_dora")
    monkeypatch.setenv("KOKORO_DEFAULT_LANGUAGE", "pt-br")
    monkeypatch.setenv(
        "AGENT_SPEC_JSON",
        json.dumps({"voice_policy": {"mode": "voice_active", "max_spoken_chars": 360}}),
    )
    monkeypatch.setenv(
        "AGENT_MODEL_POLICY_JSON",
        json.dumps(
            {
                "default_provider": "codex",
                "default_models": {"codex": "gpt-5.4-mini"},
                "functional_defaults": {
                    "general": {"provider_id": "codex", "model_id": "gpt-5.4-mini"},
                    "audio": {"provider_id": "kokoro", "model_id": "kokoro-v1"},
                },
            }
        ),
    )

    settings = get_agent_runtime_settings()

    assert settings is not None
    assert settings["voice_policy_active"] is True
    assert settings["voice_policy"]["max_spoken_chars"] == 360
    assert settings["tts_enabled"] is True
    assert settings["audio_provider"] == "kokoro"
    invalidate_agent_settings_cache()


def test_set_agent_voice_policy_enabled_publishes_runtime_snapshot(monkeypatch) -> None:
    from koda.services import agent_settings as module

    captured: dict[str, object] = {}

    class FakeManager:
        def get_agent_spec(self, agent_id: str) -> dict[str, object]:
            captured["get_agent_spec"] = agent_id
            return {"voice_policy": {"style": "natural"}}

        def put_agent_spec(self, agent_id: str, payload: dict[str, object]) -> dict[str, object]:
            captured["put_agent_spec"] = (agent_id, payload)
            return payload

        def publish_agent(self, agent_id: str) -> dict[str, object]:
            captured["publish_agent"] = agent_id
            return {"agent_id": agent_id, "version": 3}

    monkeypatch.setattr(
        module,
        "get_agent_runtime_settings",
        lambda *, force_refresh=False: {"agent_id": "KODA", "tts_enabled": False},
    )
    monkeypatch.setattr(module, "ControlPlaneManager", FakeManager)

    updated = module.set_agent_voice_policy_enabled(True)

    assert captured["publish_agent"] == "KODA"
    agent_id, payload = captured["put_agent_spec"]
    assert agent_id == "KODA"
    assert payload == {"voice_policy": {"style": "natural", "mode": "voice_active"}}
    assert updated is not None
    assert updated["voice_policy_active"] is True
    assert updated["tts_enabled"] is True


def test_set_agent_voice_default_allows_elevenlabs_audio_outside_general_catalog(monkeypatch) -> None:
    from koda.services import agent_settings as module

    settings = {
        "agent_id": "KODA",
        "providers_section": {},
        "selectable_function_options": {"audio": []},
        "tts_voice_language": "pt-br",
    }
    captured: dict[str, object] = {"published": []}

    class FakeManager:
        section = {
            "elevenlabs_default_voice": "",
            "elevenlabs_default_language": "",
            "model_policy": {
                "default_provider": "codex",
                "functional_defaults": {
                    "general": {"provider_id": "codex", "model_id": "gpt-5.4-mini"},
                },
            },
        }
        spec = {"voice_policy": {"style": "natural"}}

        def get_agent_spec(self, agent_id: str) -> dict[str, object]:
            captured["get_agent_spec"] = agent_id
            return copy.deepcopy(self.spec)

        def put_agent_spec(self, agent_id: str, payload: dict[str, object]) -> dict[str, object]:
            captured["put_agent_spec"] = (agent_id, copy.deepcopy(payload))
            self.spec.update(copy.deepcopy(payload))
            return payload

        def get_section(self, agent_id: str, section: str) -> dict[str, object]:
            captured["get_section"] = (agent_id, section)
            return {"data": copy.deepcopy(self.section)}

        def put_section(self, agent_id: str, section: str, payload: dict[str, object]) -> dict[str, object]:
            captured["put_section"] = (agent_id, section, copy.deepcopy(payload))
            self.section = copy.deepcopy(payload["data"])  # type: ignore[index]
            return payload

        def put_model_policy(self, agent_id: str, payload: dict[str, object]) -> dict[str, object]:
            captured["put_model_policy"] = (agent_id, copy.deepcopy(payload))
            self.section["model_policy"] = copy.deepcopy(payload["policy"])  # type: ignore[index]
            return payload

        def publish_agent(self, agent_id: str) -> dict[str, object]:
            captured["published"].append(agent_id)  # type: ignore[union-attr]
            return {"agent_id": agent_id, "version": 4}

    monkeypatch.setattr(module, "get_agent_runtime_settings", lambda *, force_refresh=False: copy.deepcopy(settings))
    monkeypatch.setattr(module, "ControlPlaneManager", FakeManager)

    updated = module.set_agent_voice_default(
        "nPczCjzI2devNBz1zQrb",
        voice_label="Brian",
        voice_language="pt-br",
    )

    assert updated is not None
    assert updated["tts_voice"] == "nPczCjzI2devNBz1zQrb"
    assert updated["tts_voice_label"] == "Brian"
    assert updated["tts_voice_language"] == "pt-br"
    _, policy_payload = captured["put_model_policy"]
    audio_default = policy_payload["policy"]["functional_defaults"]["audio"]  # type: ignore[index]
    assert audio_default == {"provider_id": "elevenlabs", "model_id": "eleven_flash_v2_5"}
    assert captured["published"] == ["KODA"]


def test_resolve_effort_returns_agent_override_when_present() -> None:
    settings = {
        "effort_override": {"provider_id": "codex", "model_id": "gpt-5", "value": "high"},
        "effort_default_global": {"provider_id": "codex", "model_id": "gpt-5", "value": "low"},
    }
    assert resolve_effort(settings, "codex", "gpt-5") == "high"


def test_resolve_effort_falls_back_to_global_default() -> None:
    settings = {
        "effort_override": {},
        "effort_default_global": {"provider_id": "codex", "model_id": "gpt-5", "value": "low"},
    }
    assert resolve_effort(settings, "codex", "gpt-5") == "low"


def test_resolve_effort_falls_back_to_catalog_default() -> None:
    settings = {"effort_override": {}, "effort_default_global": {}}
    assert resolve_effort(settings, "codex", "gpt-5") == "medium"


def test_resolve_effort_returns_none_when_model_has_no_capability() -> None:
    settings = {"effort_override": {}, "effort_default_global": {}}
    assert resolve_effort(settings, "mistral", "mistral-large-latest") is None


def test_resolve_effort_handles_none_settings_with_catalog_default() -> None:
    assert resolve_effort(None, "claude", "claude-opus-4-7") == "xhigh"


def test_resolve_effort_skips_invalid_enum_values() -> None:
    settings = {
        "effort_override": {"provider_id": "codex", "model_id": "gpt-5", "value": "WRONG"},
        "effort_default_global": {"provider_id": "codex", "model_id": "gpt-5", "value": "low"},
    }
    assert resolve_effort(settings, "codex", "gpt-5") == "low"


def test_resolve_effort_skips_invalid_deepseek_values() -> None:
    settings = {
        "effort_override": {"provider_id": "deepseek", "model_id": "deepseek-v4-pro", "value": "medium"},
        "effort_default_global": {"provider_id": "deepseek", "model_id": "deepseek-v4-pro", "value": "max"},
    }
    assert resolve_effort(settings, "deepseek", "deepseek-v4-pro") == "max"


def test_resolve_effort_accepts_legacy_maps() -> None:
    settings = {
        "effort_overrides": {"deepseek:deepseek-v4-pro": "max"},
        "effort_defaults_global": {},
    }
    assert resolve_effort(settings, "deepseek", "deepseek-v4-pro") == "max"


def test_resolve_effort_skips_string_for_token_kind_when_not_numeric() -> None:
    settings = {
        "effort_override": {"provider_id": "deepseek", "model_id": "deepseek-v4-pro", "value": "low"},
        "effort_default_global": {},
    }
    assert resolve_effort(settings, "deepseek", "deepseek-v4-pro") == "high"  # catalog default
