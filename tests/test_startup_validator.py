"""Tests for startup configuration validator."""

from unittest.mock import patch

import pytest

from koda.startup_validator import StartupValidationError, validate_startup_config

# Base patches: disable all optional features and set minimal valid config.
# Tests override individual values to trigger specific warnings.
_BASE = {
    "koda.config.ALLOWED_USER_IDS": {123},
    "koda.config.AVAILABLE_PROVIDERS": ["claude"],
    "koda.config.DEFAULT_PROVIDER": "claude",
    "koda.config.CODEX_APPROVAL_POLICY": "never",
    "koda.config.OLLAMA_ENABLED": False,
    "koda.config.OLLAMA_BASE_URL": "",
    "koda.config.GWS_ENABLED": False,
    "koda.config.GWS_CREDENTIALS_FILE": None,
    "koda.config.JIRA_ENABLED": False,
    "koda.config.JIRA_URL": "",
    "koda.config.JIRA_API_TOKEN": "",
    "koda.config.ELEVENLABS_ENABLED": False,
    "koda.config.ELEVENLABS_API_KEY": None,
    "koda.config.POSTGRES_ENABLED": False,
    "koda.config.POSTGRES_URL": "",
    "koda.config.POSTGRES_AVAILABLE_ENVS": [],
    "koda.config.POSTGRES_SSH_ENABLED": False,
    "koda.config.POSTGRES_SSH_HOST": "",
    "koda.config.POSTGRES_SSH_KEY_FILE": "",
    "koda.config.KOKORO_ENABLED": False,
    "koda.config.KOKORO_VOICES_PATH": "",
    "koda.config.SCHEDULER_ENABLED": False,
}


def _patch_all(**overrides: object):
    """Return a context manager that patches all config values, with overrides."""
    merged = {**_BASE, **overrides}
    ctx = [patch(k, v) for k, v in merged.items()]
    import contextlib

    return contextlib.ExitStack(), ctx


class TestStartupValidator:
    """Startup configuration validation tests."""

    def _run(self, **overrides: object) -> list[str]:
        merged = {**_BASE, **overrides}
        patches = [patch(k, v) for k, v in merged.items()]
        for p in patches:
            p.start()
        try:
            return validate_startup_config()
        finally:
            for p in patches:
                p.stop()

    def test_all_disabled_no_warnings(self) -> None:
        warnings = self._run()
        assert warnings == []

    def test_no_allowed_users_raises(self) -> None:
        with pytest.raises(StartupValidationError, match="ALLOWED_USER_IDS"):
            self._run(**{"koda.config.ALLOWED_USER_IDS": set()})

    def test_no_providers_raises(self) -> None:
        with pytest.raises(StartupValidationError, match="No LLM providers"):
            self._run(**{"koda.config.AVAILABLE_PROVIDERS": []})

    def test_default_provider_not_available(self) -> None:
        warnings = self._run(
            **{
                "koda.config.DEFAULT_PROVIDER": "gemini",
                "koda.config.AVAILABLE_PROVIDERS": ["claude"],
            }
        )
        assert any("DEFAULT_PROVIDER" in w for w in warnings)

    def test_ollama_enabled_no_url(self) -> None:
        warnings = self._run(
            **{
                "koda.config.OLLAMA_ENABLED": True,
                "koda.config.OLLAMA_BASE_URL": "",
            }
        )
        assert any("OLLAMA_BASE_URL" in w for w in warnings)

    def test_gws_enabled_no_credentials(self) -> None:
        warnings = self._run(
            **{
                "koda.config.GWS_ENABLED": True,
                "koda.config.GWS_CREDENTIALS_FILE": None,
            }
        )
        assert any("GWS_CREDENTIALS_FILE" in w for w in warnings)

    def test_gws_credentials_file_missing(self) -> None:
        warnings = self._run(
            **{
                "koda.config.GWS_ENABLED": True,
                "koda.config.GWS_CREDENTIALS_FILE": "/nonexistent/creds.json",
            }
        )
        assert any("does not exist" in w for w in warnings)

    def test_jira_enabled_no_url(self) -> None:
        warnings = self._run(
            **{
                "koda.config.JIRA_ENABLED": True,
                "koda.config.JIRA_URL": "",
                "koda.config.JIRA_API_TOKEN": "",
            }
        )
        assert any("JIRA_URL" in w for w in warnings)

    def test_elevenlabs_enabled_no_key(self) -> None:
        warnings = self._run(
            **{
                "koda.config.ELEVENLABS_ENABLED": True,
                "koda.config.ELEVENLABS_API_KEY": None,
            }
        )
        assert any("ELEVENLABS_API_KEY" in w for w in warnings)

    def test_postgres_enabled_no_url(self) -> None:
        warnings = self._run(
            **{
                "koda.config.POSTGRES_ENABLED": True,
                "koda.config.POSTGRES_URL": "",
                "koda.config.POSTGRES_AVAILABLE_ENVS": [],
            }
        )
        assert any("POSTGRES_URL" in w for w in warnings)

    def test_postgres_ssh_no_host(self) -> None:
        warnings = self._run(
            **{
                "koda.config.POSTGRES_SSH_ENABLED": True,
                "koda.config.POSTGRES_SSH_HOST": "",
            }
        )
        assert any("POSTGRES_SSH_HOST" in w for w in warnings)

    def test_postgres_ssh_key_missing(self) -> None:
        warnings = self._run(
            **{
                "koda.config.POSTGRES_SSH_ENABLED": True,
                "koda.config.POSTGRES_SSH_HOST": "example.com",
                "koda.config.POSTGRES_SSH_KEY_FILE": "/nonexistent/key.pem",
            }
        )
        assert any("does not exist" in w for w in warnings)

    def test_kokoro_voices_path_missing(self) -> None:
        warnings = self._run(
            **{
                "koda.config.KOKORO_ENABLED": True,
                "koda.config.KOKORO_VOICES_PATH": "/nonexistent/voices",
            }
        )
        assert any("KOKORO_VOICES_PATH" in w for w in warnings)

    def test_invalid_codex_approval_policy(self) -> None:
        warnings = self._run(**{"koda.config.CODEX_APPROVAL_POLICY": "bogus-value"})
        assert any("CODEX_APPROVAL_POLICY" in w for w in warnings)

    def test_valid_codex_approval_policy_no_warning(self) -> None:
        warnings = self._run(**{"koda.config.CODEX_APPROVAL_POLICY": "auto-edit"})
        assert not any("CODEX_APPROVAL_POLICY" in w for w in warnings)
