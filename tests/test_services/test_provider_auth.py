"""Tests for provider auth process environment isolation."""

import pytest

from koda.services import provider_auth
from koda.services.provider_auth import build_provider_process_env


def test_subscription_login_process_env_strips_unrelated_sensitive_values():
    env = build_provider_process_env(
        "codex",
        auth_mode="subscription_login",
        base_env={
            "PATH": "/usr/bin",
            "HOME": "/tmp/home",
            "CODEX_HOME": "/tmp/codex",
            "CODEX_BIN": "/opt/bin/codex",
            "OPENAI_API_KEY": "openai-secret",
            "ANTHROPIC_API_KEY": "anthropic-secret",
            "AGENT_TOKEN": "telegram-secret",
            "JIRA_API_TOKEN": "jira-secret",
            "RUNTIME_LOCAL_UI_TOKEN": "runtime-secret",
        },
    )

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/tmp/home"
    assert env["CODEX_HOME"] == "/tmp/codex"
    assert env["CODEX_BIN"] == "/opt/bin/codex"
    assert env["CODEX_AUTH_MODE"] == "subscription_login"
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "AGENT_TOKEN" not in env
    assert "JIRA_API_TOKEN" not in env
    assert "RUNTIME_LOCAL_UI_TOKEN" not in env


def test_provider_process_env_inherits_ambient_safe_path_when_base_env_is_scoped(monkeypatch):
    monkeypatch.setenv("PATH", "/ambient/bin:/usr/bin")
    monkeypatch.setenv("HOME", "/ambient/home")

    env = build_provider_process_env(
        "claude",
        auth_mode="subscription_login",
        base_env={
            "CLAUDE_HOME": "/tmp/claude-home",
            "CLAUDE_CONFIG_DIR": "/tmp/claude-home/.claude",
        },
    )

    assert env["PATH"] == "/ambient/bin:/usr/bin"
    assert env["HOME"] == "/ambient/home"
    assert env["CLAUDE_HOME"] == "/tmp/claude-home"
    assert env["CLAUDE_CONFIG_DIR"] == "/tmp/claude-home/.claude"


def test_provider_login_command_respects_configured_binary_from_scoped_env(monkeypatch):
    seen: list[tuple[str, str | None]] = []

    def fake_which(executable: str, path: str | None = None):
        seen.append((executable, path))
        if executable == "/custom/bin/codex":
            return executable
        return None

    monkeypatch.setattr(provider_auth.shutil, "which", fake_which)

    command = provider_auth.provider_login_command(
        "codex",
        base_env={
            "CODEX_BIN": "/custom/bin/codex",
            "PATH": "/custom/bin:/usr/bin",
        },
    )

    assert command == ("/custom/bin/codex", "login", "--device-auth")
    assert seen == [("/custom/bin/codex", "/custom/bin:/usr/bin")]


def test_provider_process_env_keeps_only_active_provider_credentials():
    env = build_provider_process_env(
        "gemini",
        auth_mode="api_key",
        api_key="gemini-secret",
        project_id="museum-prod",
        base_env={
            "PATH": "/usr/bin",
            "HOME": "/tmp/home",
            "OPENAI_API_KEY": "openai-secret",
            "ANTHROPIC_API_KEY": "anthropic-secret",
            "GOOGLE_CLOUD_PROJECT": "old-project",
        },
    )

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/tmp/home"
    assert env["GEMINI_AUTH_MODE"] == "api_key"
    assert env["GEMINI_API_KEY"] == "gemini-secret"
    assert env["GOOGLE_CLOUD_PROJECT"] == "museum-prod"
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env


def test_ollama_local_process_env_keeps_base_url_without_api_key():
    env = build_provider_process_env(
        "ollama",
        auth_mode="local",
        base_url="http://127.0.0.1:11434",
        base_env={
            "PATH": "/usr/bin",
            "HOME": "/tmp/home",
            "OPENAI_API_KEY": "openai-secret",
            "OLLAMA_API_KEY": "stale-secret",
        },
    )

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/tmp/home"
    assert env["OLLAMA_AUTH_MODE"] == "local"
    assert env["OLLAMA_BASE_URL"] == "http://127.0.0.1:11434"
    assert "OLLAMA_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env


def test_resolve_provider_command_raises_file_not_found_when_cli_missing(monkeypatch):
    monkeypatch.setattr(provider_auth.shutil, "which", lambda *a, **kw: None)

    with pytest.raises(FileNotFoundError, match="claude"):
        provider_auth.resolve_provider_command("claude")


def test_start_login_process_raises_file_not_found_when_cli_missing(monkeypatch):
    monkeypatch.setattr(provider_auth.shutil, "which", lambda *a, **kw: None)

    with pytest.raises(FileNotFoundError):
        provider_auth.start_login_process(
            "claude",
            project_id="",
            base_env={"PATH": "/nonexistent"},
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7-provider HTTP runtime sentinels
# ─────────────────────────────────────────────────────────────────────────────

_HTTP_OPENAI_COMPATIBLE_PROVIDERS = (
    "perplexity",
    "mistral",
    "qwen",
    "kimi",
    "groq",
    "deepseek",
    "xai",
)


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_managed_provider_includes_new_http_provider(provider_id):
    assert provider_id in provider_auth.MANAGED_PROVIDER_IDS


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_provider_api_key_env_key_registered(provider_id):
    assert provider_id in provider_auth.PROVIDER_API_KEY_ENV_KEYS
    assert provider_auth.PROVIDER_API_KEY_ENV_KEYS[provider_id].endswith("_API_KEY")


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_provider_base_url_env_key_registered(provider_id):
    """All 7 new HTTP providers support env override of their base URL."""
    assert provider_id in provider_auth.PROVIDER_BASE_URL_ENV_KEYS


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_new_providers_do_not_advertise_subscription_login(provider_id):
    """None of the 7 new providers expose OAuth subscription login for API access."""
    assert not provider_auth.provider_supports_subscription_login(provider_id)


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_http_verify_profile_registered(provider_id):
    assert provider_id in provider_auth._HTTP_OPENAI_COMPATIBLE_VERIFY_PROFILES
    profile = provider_auth._HTTP_OPENAI_COMPATIBLE_VERIFY_PROFILES[provider_id]
    assert "default_base_url" in profile
    assert profile["default_base_url"].startswith("https://")


def test_perplexity_uses_health_probe_not_models_endpoint():
    """Perplexity has no /v1/models — verify falls back to health probe to avoid burning quota."""
    profile = provider_auth._HTTP_OPENAI_COMPATIBLE_VERIFY_PROFILES["perplexity"]
    assert profile["probe"] == "health"


def test_http_provider_keys_threaded_through_provider_env():
    """Sentinel: provider_env._provider_allowed_keys must include the new API key for HTTP providers."""
    from koda.services.provider_env import _provider_allowed_keys

    source = {"PERPLEXITY_AUTH_MODE": "api_key"}
    allowed = _provider_allowed_keys("perplexity", source)
    assert "PERPLEXITY_API_KEY" in allowed
    assert "PERPLEXITY_AUTH_MODE" in allowed
    assert "PERPLEXITY_API_BASE_URL" in allowed
