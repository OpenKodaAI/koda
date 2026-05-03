"""Tests for provider auth process environment isolation."""

from typing import cast

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


# 7-provider HTTP runtime sentinels

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


# Gemini API key verification — must use header, never query string


def test_gemini_api_key_verify_uses_header_not_query_string(monkeypatch):
    """Regression: Gemini verify must pass the API key via `x-goog-api-key`
    header, never `?key=...` in the URL.

    Google explicitly recommends the header form because query strings end up
    in proxy access logs, browser history, and Referer headers — leaking the
    API key. See https://ai.google.dev/gemini-api/docs/api-key.
    """
    from urllib import request as urllib_request

    captured: dict[str, object] = {}

    class _FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return self._body

    def _fake_urlopen(request, timeout=10):  # noqa: ARG001
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        return _FakeResponse(b'{"models": [{"name": "models/gemini-1.5-pro"}]}')

    monkeypatch.setattr(urllib_request, "urlopen", _fake_urlopen)

    result = provider_auth.verify_provider_api_key(
        "gemini",
        "AIza-test-secret-key",
    )

    url = str(captured["url"])
    headers = cast(dict, captured["headers"])

    assert result.verified, f"verify must succeed when models list is returned, got {result.last_error!r}"
    # Hard contract: API key must NOT appear in the URL.
    assert "AIza-test-secret-key" not in url, (
        "Regression: Gemini API key must not appear in the request URL. "
        "Use the `x-goog-api-key` header instead — query strings leak into logs."
    )
    assert "key=" not in url, f"Regression: Gemini verify URL must not include a `?key=` query parameter; got {url!r}"
    # And it must be in the right header.
    assert headers.get("x-goog-api-key") == "AIza-test-secret-key", (
        f"Gemini API key must be sent via the x-goog-api-key header; got headers={headers!r}"
    )
    # Project ID is not relevant to API key auth — it's a Vertex AI concept.
    assert result.account_label == "Google AI Studio"
    assert result.details == {}


# Native HTTP provider verify contracts (auth header + URL)


class _CapturedResponse:
    """Minimal stub for `urllib.request.urlopen` context manager."""

    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return self._body


def _patch_urlopen(monkeypatch, body: bytes = b'{"data": []}'):
    """Patch `urlopen` and return the dict that captures each call."""
    from urllib import request as urllib_request

    captured: dict[str, object] = {}

    def _fake(request, timeout=10):  # noqa: ARG001
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["method"] = request.get_method()
        return _CapturedResponse(body)

    monkeypatch.setattr(urllib_request, "urlopen", _fake)
    return captured


@pytest.mark.parametrize(
    ("provider_id", "secret", "expected_url", "expected_auth_header"),
    [
        # Anthropic: x-api-key header. Docs: https://docs.anthropic.com/en/api/getting-started
        (
            "claude",
            "sk-ant-api03-test",
            "https://api.anthropic.com/v1/models",
            ("x-api-key", "sk-ant-api03-test"),
        ),
        # OpenAI: Bearer token. Docs: https://platform.openai.com/docs/api-reference/authentication
        (
            "codex",
            "sk-openai-test",
            "https://api.openai.com/v1/models",
            ("authorization", "Bearer sk-openai-test"),
        ),
        # ElevenLabs: xi-api-key header (custom). Docs: https://elevenlabs.io/docs/api-reference/authentication
        (
            "elevenlabs",
            "xi-test-key",
            "https://api.elevenlabs.io/v1/models",
            ("xi-api-key", "xi-test-key"),
        ),
    ],
)
def test_native_provider_api_key_verify_contract(provider_id, secret, expected_url, expected_auth_header, monkeypatch):
    """Each native provider must verify against its documented endpoint and auth header."""
    captured = _patch_urlopen(monkeypatch)

    result = provider_auth.verify_provider_api_key(provider_id, secret)

    assert result.verified, f"{provider_id} verify must succeed on 200 response"
    assert captured["url"] == expected_url, (
        f"{provider_id} verify URL must be {expected_url!r}, got {captured['url']!r}"
    )
    headers = cast(dict, captured["headers"])
    header_name, header_value = expected_auth_header
    assert headers.get(header_name) == header_value, (
        f"{provider_id} verify must send `{header_name}: {header_value}`; got headers={headers!r}"
    )
    # Secrets must never end up in the URL — that leaks them into proxy logs.
    assert secret not in str(captured["url"]), f"{provider_id} API key leaked into the verify URL: {captured['url']!r}"


def test_claude_verify_includes_anthropic_version_header(monkeypatch):
    """Anthropic's docs require an `anthropic-version` header on every request."""
    captured = _patch_urlopen(monkeypatch)

    provider_auth.verify_provider_api_key("claude", "sk-ant-api03-test")

    headers = cast(dict, captured["headers"])
    assert headers.get("anthropic-version"), (
        f"Claude verify must send the `anthropic-version` header (Anthropic API contract); got headers={headers!r}"
    )


def test_claude_oauth_token_verify_uses_bearer_authorization(monkeypatch):
    """Claude OAuth tokens (sk-ant-oat*) must go through `Authorization: Bearer`,
    not `x-api-key` (the OAuth issuer's contract)."""
    captured = _patch_urlopen(monkeypatch)

    provider_auth.verify_provider_api_key("claude", "sk-ant-oat-test-token")

    headers = cast(dict, captured["headers"])
    assert headers.get("authorization") == "Bearer sk-ant-oat-test-token", (
        f"OAuth tokens must use Bearer auth; got headers={headers!r}"
    )
    # And must NOT also send x-api-key — that would be a contract violation.
    assert "x-api-key" not in headers


@pytest.mark.parametrize(
    ("provider_id", "expected_default_base_url"),
    [
        # OpenAI-compatible providers: each docs page is the source of truth.
        # Perplexity docs: https://docs.perplexity.ai/getting-started/quickstart
        ("perplexity", "https://api.perplexity.ai"),
        # Mistral docs: https://docs.mistral.ai/api/
        ("mistral", "https://api.mistral.ai"),
        # Qwen / Alibaba DashScope International: https://www.alibabacloud.com/help/en/model-studio/developer-reference/compatibility-of-openai-with-dashscope
        ("qwen", "https://dashscope-intl.aliyuncs.com"),
        # Moonshot/Kimi docs: https://platform.moonshot.ai/docs
        ("kimi", "https://api.moonshot.ai"),
        # Groq docs: https://console.groq.com/docs/openai (note the /openai prefix)
        ("groq", "https://api.groq.com/openai"),
        # DeepSeek docs: https://api-docs.deepseek.com/
        ("deepseek", "https://api.deepseek.com"),
        # xAI docs: https://docs.x.ai/api
        ("xai", "https://api.x.ai"),
    ],
)
def test_openai_compatible_default_base_url_matches_docs(provider_id, expected_default_base_url):
    """Each OpenAI-compatible provider's default base URL must match its
    official documentation. Drift between code and docs causes silent
    routing bugs and confusing 404s for end users."""
    profile = provider_auth._HTTP_OPENAI_COMPATIBLE_VERIFY_PROFILES[provider_id]
    assert profile["default_base_url"] == expected_default_base_url, (
        f"{provider_id}: documented base URL is {expected_default_base_url!r}, "
        f"profile says {profile['default_base_url']!r}"
    )


@pytest.mark.parametrize(
    "provider_id",
    ["mistral", "qwen", "kimi", "groq", "deepseek", "xai"],
)
def test_openai_compatible_models_probe_uses_bearer_auth(provider_id, monkeypatch):
    """All OpenAI-compatible verify calls must use `Authorization: Bearer <key>`.

    This is the spec for any provider that advertises OpenAI compatibility.
    """
    captured = _patch_urlopen(monkeypatch)

    provider_auth.verify_provider_api_key(provider_id, "test-bearer-secret")

    headers = cast(dict, captured["headers"])
    assert headers.get("authorization") == "Bearer test-bearer-secret", (
        f"{provider_id} must verify with `Authorization: Bearer <key>`; got headers={headers!r}"
    )
    # Secret must not leak into the URL.
    assert "test-bearer-secret" not in str(captured["url"])


def test_ollama_api_key_verify_ignores_localhost_caller_base_url(monkeypatch):
    """Regression: even when a caller passes a localhost ``base_url`` in
    api_key mode, the verify must hit Ollama Cloud — not the local daemon.

    The bug: ``ollama_runner._probe_ollama_auth_status`` defaults its
    ``base_url`` to ``http://localhost:11434`` when ``OLLAMA_BASE_URL`` isn't
    exported into the process, then passes it into
    ``verify_provider_api_key``. Without this guard, ``ollama_api_url`` would
    happily build ``http://localhost:11434/api/tags`` and the cloud verify
    would fail with ``<urlopen error [Errno 61] Connection refused>``.
    """
    captured = _patch_urlopen(monkeypatch, b'{"models": []}')

    result = provider_auth.verify_provider_api_key(
        "ollama",
        "ollama-cloud-key",
        base_url="http://localhost:11434",  # ← stray localhost from runtime probe
    )

    url = str(captured["url"])
    assert result.verified is True
    assert url.startswith("https://ollama.com/"), f"api_key verify must target Ollama Cloud, got {url!r}"
    assert "localhost" not in url, "Regression: a stray localhost base_url leaked into the cloud verify URL"
    headers = cast(dict, captured["headers"])
    assert headers.get("authorization") == "Bearer ollama-cloud-key"


def test_ollama_api_key_verify_ignores_docker_host_alias_base_url(monkeypatch):
    """Same defense for the Docker host alias — ``host.docker.internal`` is
    only meaningful for local-mode Ollama; api_key mode must always go cloud.
    """
    captured = _patch_urlopen(monkeypatch, b'{"models": []}')

    provider_auth.verify_provider_api_key(
        "ollama",
        "ollama-cloud-key",
        base_url="http://host.docker.internal:11434",
    )

    url = str(captured["url"])
    assert url.startswith("https://ollama.com/"), f"api_key verify must target Ollama Cloud, got {url!r}"


def test_runtime_profile_and_verify_profile_share_base_url():
    """Runtime adapter (`*_runner.py`) and credential verifier
    (`provider_auth._HTTP_OPENAI_COMPATIBLE_VERIFY_PROFILES`) must agree on
    each provider's default base URL — otherwise verify says "OK" against one
    endpoint while runtime fails against another."""
    from koda.services.openai_compatible_runner import (
        OPENAI_COMPATIBLE_PROVIDERS,
        get_provider_profile,
    )

    runtime_profiles = {provider_id: get_provider_profile(provider_id) for provider_id in OPENAI_COMPATIBLE_PROVIDERS}
    for provider_id, runtime in runtime_profiles.items():
        verify_default = provider_auth._HTTP_OPENAI_COMPATIBLE_VERIFY_PROFILES[provider_id]["default_base_url"]
        assert runtime.base_url == verify_default, (
            f"{provider_id}: runtime base_url={runtime.base_url!r} but "
            f"verify default={verify_default!r} — these must match."
        )
