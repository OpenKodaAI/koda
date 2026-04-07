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
