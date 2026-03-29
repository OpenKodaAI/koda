"""Tests for subprocess environment sanitization helpers."""

from koda.services.provider_env import build_llm_subprocess_env, build_tool_subprocess_env


def test_llm_subprocess_env_keeps_provider_credentials_only():
    env = build_llm_subprocess_env(
        {
            "PATH": "/usr/bin",
            "HOME": "/tmp/home",
            "CLAUDE_AUTH_MODE": "api_key",
            "ANTHROPIC_API_KEY": "anthropic-secret",
            "OPENAI_API_KEY": "openai-secret",
            "AGENT_TOKEN": "telegram-secret",
            "JIRA_API_TOKEN": "jira-secret",
            "RUNTIME_LOCAL_UI_TOKEN": "runtime-secret",
        },
        provider="claude",
    )

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/tmp/home"
    assert env["ANTHROPIC_API_KEY"] == "anthropic-secret"
    assert env["CLAUDE_AUTH_MODE"] == "api_key"
    assert "OPENAI_API_KEY" not in env
    assert "AGENT_TOKEN" not in env
    assert "JIRA_API_TOKEN" not in env
    assert "RUNTIME_LOCAL_UI_TOKEN" not in env


def test_gemini_llm_subprocess_env_keeps_project_only_for_active_provider():
    env = build_llm_subprocess_env(
        {
            "PATH": "/usr/bin",
            "HOME": "/tmp/home",
            "GEMINI_AUTH_MODE": "api_key",
            "GEMINI_API_KEY": "gemini-secret",
            "GOOGLE_CLOUD_PROJECT": "control-plane",
            "OPENAI_API_KEY": "openai-secret",
        },
        provider="gemini",
    )

    assert env["GEMINI_API_KEY"] == "gemini-secret"
    assert env["GOOGLE_CLOUD_PROJECT"] == "control-plane"
    assert "OPENAI_API_KEY" not in env


def test_tool_subprocess_env_keeps_only_safe_base_env_plus_explicit_overrides():
    env = build_tool_subprocess_env(
        {
            "PATH": "/usr/bin",
            "HOME": "/tmp/home",
            "OPENAI_API_KEY": "openai-secret",
            "AGENT_TOKEN": "telegram-secret",
        },
        env_overrides={"LOCAL_FLAG": "enabled", "GWS_CREDENTIALS_FILE": "/tmp/creds.json"},
    )

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/tmp/home"
    assert env["LOCAL_FLAG"] == "enabled"
    assert env["GWS_CREDENTIALS_FILE"] == "/tmp/creds.json"
    assert "OPENAI_API_KEY" not in env
    assert "AGENT_TOKEN" not in env
