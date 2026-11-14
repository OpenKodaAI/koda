"""Tests for the shared OpenAI-compatible HTTP runner."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from aiohttp import web

from koda.services.openai_compatible_runner import (
    OPENAI_COMPATIBLE_PROVIDERS,
    _append_citations_footer,
    _build_chat_payload,
    _build_citations_footer,
    _build_user_content,
    _classify_http_error,
    _estimate_cost,
    _extract_citations,
    _extract_delta_text,
    _extract_message_text,
    _extract_tool_calls,
    _normalize_usage,
    _profile_headers,
    clear_openai_compatible_capability_cache,
    get_provider_profile,
)
from koda.services.provider_auth import PROVIDER_BASE_URL_ENV_KEYS
from koda.services.provider_http_profile import ProviderHttpProfile
from koda.services.provider_runtime import ProviderCapabilities


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_openai_compatible_capability_cache()
    yield
    clear_openai_compatible_capability_cache()


@pytest.fixture
def perplexity_profile() -> ProviderHttpProfile:
    return ProviderHttpProfile(
        provider_id="perplexity",
        base_url="https://api.perplexity.ai",
        chat_path="/chat/completions",
        models_path=None,
        capability_probe="health_only",
        first_chunk_timeout_seconds=60.0,
    )


@pytest.fixture
def mistral_profile() -> ProviderHttpProfile:
    return ProviderHttpProfile(
        provider_id="mistral",
        base_url="https://api.mistral.ai",
        chat_path="/v1/chat/completions",
        models_path="/v1/models",
        vision_models=frozenset({"pixtral-large-latest"}),
    )


@pytest.fixture
def ready_capability() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider="generic",
        turn_mode="new_turn",
        status="ready",
        can_execute=True,
        supports_native_resume=False,
    )


# Pure-function tests


class TestPayloadBuilder:
    def test_no_tools_field_in_payload_by_default(self, mistral_profile):
        """XML fallback remains the default when no registry schemas are supplied."""
        payload = _build_chat_payload(
            profile=mistral_profile,
            model="mistral-large-latest",
            query="hi",
            system_prompt="you are helpful",
            image_paths=None,
            max_budget=0.0,
            stream=False,
        )
        assert "tools" not in payload
        assert "tool_choice" not in payload
        assert payload["model"] == "mistral-large-latest"
        assert payload["stream"] is False
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"

    def test_native_tools_field_in_payload_when_supplied(self, mistral_profile):
        tool_schema = {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }
        payload = _build_chat_payload(
            profile=mistral_profile,
            model="mistral-large-latest",
            query="hi",
            system_prompt="you are helpful",
            image_paths=None,
            max_budget=0.0,
            stream=False,
            native_tools=[tool_schema],
            native_tool_choice="auto",
        )
        assert payload["tools"] == [tool_schema]
        assert payload["tool_choice"] == "auto"

    def test_streaming_payload_includes_usage_options(self, mistral_profile):
        payload = _build_chat_payload(
            profile=mistral_profile,
            model="mistral-large-latest",
            query="hi",
            system_prompt=None,
            image_paths=None,
            max_budget=0.0,
            stream=True,
        )
        assert payload["stream"] is True
        assert payload["stream_options"] == {"include_usage": True}

    def test_vision_payload_for_vision_model(self, mistral_profile, tmp_path):
        image = tmp_path / "img.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        payload = _build_chat_payload(
            profile=mistral_profile,
            model="pixtral-large-latest",
            query="describe",
            system_prompt=None,
            image_paths=[str(image)],
            max_budget=0.0,
            stream=False,
        )
        user_content = payload["messages"][0]["content"]
        assert isinstance(user_content, list)
        assert any(item.get("type") == "image_url" for item in user_content)
        assert any(item.get("type") == "text" for item in user_content)

    def test_no_vision_blocks_for_non_vision_model(self, mistral_profile, tmp_path):
        image = tmp_path / "img.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        payload = _build_chat_payload(
            profile=mistral_profile,
            model="mistral-large-latest",  # not in vision_models
            query="describe",
            system_prompt=None,
            image_paths=[str(image)],
            max_budget=0.0,
            stream=False,
        )
        user_content = payload["messages"][0]["content"]
        assert isinstance(user_content, str)
        assert user_content == "describe"

    def test_effort_enum_injects_reasoning_effort(self):
        from koda.services.openai_compatible_runner import get_provider_profile

        payload = _build_chat_payload(
            profile=get_provider_profile("perplexity"),
            model="sonar-reasoning",
            query="hi",
            system_prompt=None,
            image_paths=None,
            max_budget=0.0,
            stream=False,
            effort="high",
        )
        assert payload["reasoning_effort"] == "high"
        assert "thinking" not in payload

        payload = _build_chat_payload(
            profile=get_provider_profile("deepseek"),
            model="deepseek-v4-pro",
            query="hi",
            system_prompt=None,
            image_paths=None,
            max_budget=0.0,
            stream=False,
            effort="max",
        )
        assert payload["reasoning_effort"] == "max"
        assert payload["thinking"] == {"type": "enabled"}

        payload = _build_chat_payload(
            profile=get_provider_profile("xai"),
            model="grok-4.20-multi-agent",
            query="hi",
            system_prompt=None,
            image_paths=None,
            max_budget=0.0,
            stream=False,
            effort="xhigh",
        )
        assert payload["reasoning"] == {"effort": "xhigh"}
        assert "reasoning_effort" not in payload

    def test_effort_skipped_when_model_has_no_capability(self, mistral_profile):
        payload = _build_chat_payload(
            profile=mistral_profile,
            model="mistral-large-latest",
            query="hi",
            system_prompt=None,
            image_paths=None,
            max_budget=0.0,
            stream=False,
            effort="high",
        )
        assert "reasoning_effort" not in payload
        assert "thinking" not in payload

    def test_effort_skipped_when_value_is_invalid(self):
        from koda.services.openai_compatible_runner import get_provider_profile

        payload = _build_chat_payload(
            profile=get_provider_profile("perplexity"),
            model="sonar-reasoning",
            query="hi",
            system_prompt=None,
            image_paths=None,
            max_budget=0.0,
            stream=False,
            effort="WRONG",
        )
        assert "reasoning_effort" not in payload

        payload = _build_chat_payload(
            profile=get_provider_profile("deepseek"),
            model="deepseek-v4-pro",
            query="hi",
            system_prompt=None,
            image_paths=None,
            max_budget=0.0,
            stream=False,
            effort="low",
        )
        assert "thinking" not in payload
        assert "reasoning_effort" not in payload

        payload = _build_chat_payload(
            profile=get_provider_profile("xai"),
            model="grok-4.20-multi-agent",
            query="hi",
            system_prompt=None,
            image_paths=None,
            max_budget=0.0,
            stream=False,
            effort="max",
        )
        assert "reasoning" not in payload
        assert "reasoning_effort" not in payload


class TestUsageAndCost:
    def test_normalize_usage_with_openai_keys(self):
        out = _normalize_usage({"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
        assert out == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}

    def test_normalize_usage_with_anthropic_keys(self):
        out = _normalize_usage({"input_tokens": 100, "output_tokens": 50})
        assert out == {"input_tokens": 100, "output_tokens": 50}

    def test_normalize_usage_with_cached_tokens(self):
        out = _normalize_usage(
            {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "prompt_tokens_details": {"cached_tokens": 30},
            }
        )
        assert out["cached_input_tokens"] == 30
        assert out["input_tokens"] == 100

    def test_estimate_cost_zero_when_no_usage(self):
        assert _estimate_cost("any-model", {}) == 0.0

    def test_estimate_cost_uses_general_model_metadata(self, monkeypatch):
        monkeypatch.setattr("koda.services.openai_compatible_runner.MODEL_PRICING_USD", {})
        usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        cost = _estimate_cost("mistral-large-latest", usage)
        assert cost == pytest.approx(2.0 + 6.0, rel=1e-3)

    def test_estimate_cost_handles_cached_tokens(self, monkeypatch):
        monkeypatch.setattr("koda.services.openai_compatible_runner.MODEL_PRICING_USD", {})
        usage = {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cached_input_tokens": 500_000,
        }
        cost = _estimate_cost("deepseek-chat", usage)
        # 500k fresh @ 0.27 + 500k cached @ 0.07 + 1M output @ 1.10
        expected = (0.5 * 0.27) + (0.5 * 0.07) + (1.0 * 1.10)
        assert cost == pytest.approx(expected, rel=1e-3)


class TestErrorClassification:
    def test_401_is_provider_auth_not_retryable(self):
        kind, retryable = _classify_http_error(401, "Unauthorized")
        assert kind == "provider_auth"
        assert retryable is False

    def test_403_is_provider_auth(self):
        kind, retryable = _classify_http_error(403, "Forbidden")
        assert kind == "provider_auth"
        assert retryable is False

    def test_429_is_retryable_transient(self):
        kind, retryable = _classify_http_error(429, "Too Many Requests")
        assert kind == "transient"
        assert retryable is True

    def test_500_is_retryable_transient(self):
        kind, retryable = _classify_http_error(500, "Internal Server Error")
        assert kind == "transient"
        assert retryable is True

    def test_400_with_model_mention_is_adapter_contract(self):
        kind, retryable = _classify_http_error(400, "Invalid model: foo-bar")
        assert kind == "adapter_contract"
        assert retryable is False


class TestMessageExtraction:
    def test_extract_message_text_string_content(self):
        data = {"choices": [{"message": {"content": "Hello"}}]}
        assert _extract_message_text(data) == "Hello"

    def test_extract_message_text_list_content(self):
        data = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "First"},
                            {"type": "text", "text": "Second"},
                        ]
                    }
                }
            ]
        }
        assert "First" in _extract_message_text(data)
        assert "Second" in _extract_message_text(data)

    def test_extract_delta_text_string(self):
        chunk = {"choices": [{"delta": {"content": "tok"}}]}
        assert _extract_delta_text(chunk) == "tok"

    def test_extract_delta_text_empty_when_no_choices(self):
        assert _extract_delta_text({"choices": []}) == ""

    def test_extract_tool_calls_normalizes_function_arguments(self):
        data = {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "web_search",
                                    "arguments": '{"query": "phase 1"}',
                                },
                            }
                        ],
                    }
                }
            ]
        }
        calls = _extract_tool_calls(data)
        assert calls == [
            {
                "source": "openai_compatible_tool_call",
                "id": "call_1",
                "type": "function",
                "name": "web_search",
                "arguments": {"query": "phase 1"},
                "arguments_json": '{"query": "phase 1"}',
                "function": {"name": "web_search", "arguments": {"query": "phase 1"}},
            }
        ]


class TestCitations:
    def test_extract_top_level_citations(self, perplexity_profile):
        data = {"citations": ["https://a.com", {"url": "https://b.com", "title": "B"}]}
        result = _extract_citations(perplexity_profile, data)
        assert "https://a.com" in result
        assert any("https://b.com" in c for c in result)

    def test_extract_no_citations_returns_empty(self, perplexity_profile):
        assert _extract_citations(perplexity_profile, {"choices": [{"message": {"content": "hi"}}]}) == []

    def test_build_citations_footer(self):
        footer = _build_citations_footer(["https://a.com", "B — https://b.com"])
        assert "Fontes:" in footer
        assert "[1] https://a.com" in footer
        assert "[2] B — https://b.com" in footer

    def test_append_citations_footer(self):
        result = _append_citations_footer("Main answer", ["https://a.com"])
        assert result.startswith("Main answer")
        assert "Fontes:" in result
        assert "[1] https://a.com" in result


# Integration tests with mocked HTTP


class TestRunOpenAICompatible:
    @pytest.mark.asyncio
    async def test_returns_error_when_no_api_key(self, mistral_profile, ready_capability, monkeypatch):
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        # Mock build_llm_subprocess_env to return empty dict (no key)
        with patch(
            "koda.services.openai_compatible_runner.build_llm_subprocess_env",
            return_value={},
        ):
            from koda.services.openai_compatible_runner import run_openai_compatible

            result = await run_openai_compatible(
                profile=mistral_profile,
                query="hi",
                work_dir="/tmp",
                model="mistral-large-latest",
                turn_mode="new_turn",
                capabilities=ready_capability,
            )
        assert result["error"] is True
        assert result["_error_kind"] == "provider_auth"
        assert "API key" in result["result"]

    @pytest.mark.asyncio
    async def test_dry_run_returns_placeholder(self, mistral_profile, ready_capability):
        with patch(
            "koda.services.openai_compatible_runner.build_llm_subprocess_env",
            return_value={"MISTRAL_API_KEY": "sk-test"},
        ):
            from koda.services.openai_compatible_runner import run_openai_compatible

            result = await run_openai_compatible(
                profile=mistral_profile,
                query="hi",
                work_dir="/tmp",
                model="mistral-large-latest",
                turn_mode="new_turn",
                capabilities=ready_capability,
                dry_run=True,
            )
        assert result["error"] is False
        assert result["result"] == "(dry-run)"

    @pytest.mark.asyncio
    async def test_returns_error_when_capabilities_block_execution(self, mistral_profile):
        unavailable = ProviderCapabilities(
            provider="mistral",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=["Mistral runtime unavailable."],
        )
        from koda.services.openai_compatible_runner import run_openai_compatible

        result = await run_openai_compatible(
            profile=mistral_profile,
            query="hi",
            work_dir="/tmp",
            model="mistral-large-latest",
            turn_mode="new_turn",
            capabilities=unavailable,
        )
        assert result["error"] is True
        assert "unavailable" in result["result"].lower()


class TestRunOpenAICompatibleCancellation:
    """A /cancel reaches the non-streaming runner as a cancel of its calling task (D-009)."""

    @staticmethod
    @contextlib.asynccontextmanager
    async def _hanging_server() -> AsyncIterator[tuple[str, asyncio.Event]]:
        """Serve a chat endpoint that accepts the request and never answers."""
        request_received = asyncio.Event()
        release = asyncio.Event()

        async def _chat(_request: web.Request) -> web.Response:
            request_received.set()
            await release.wait()
            return web.json_response({})

        app = web.Application()
        app.router.add_post("/v1/chat/completions", _chat)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = runner.addresses[0][1]
        try:
            yield f"http://127.0.0.1:{port}", request_received
        finally:
            release.set()
            await runner.cleanup()

    @staticmethod
    def _local_profile(base_url: str) -> ProviderHttpProfile:
        return ProviderHttpProfile(
            provider_id="mistral",
            base_url=base_url,
            chat_path="/v1/chat/completions",
            models_path="/v1/models",
            allow_private_base_url=True,
        )

    @pytest.mark.asyncio
    async def test_cancelling_the_calling_task_propagates(self, ready_capability):
        """The cancel must stop the caller, not turn into an error result it then reports."""
        from koda.services.openai_compatible_runner import run_openai_compatible

        async with self._hanging_server() as (base_url, request_received):
            with patch(
                "koda.services.openai_compatible_runner.build_llm_subprocess_env",
                return_value={"MISTRAL_API_KEY": "sk-test"},
            ):
                run = asyncio.create_task(
                    run_openai_compatible(
                        profile=self._local_profile(base_url),
                        query="hi",
                        work_dir="/tmp",
                        model="mistral-large-latest",
                        turn_mode="new_turn",
                        capabilities=ready_capability,
                        process_holder={},
                    )
                )
                await asyncio.wait_for(request_received.wait(), timeout=10)
                run.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(run, timeout=10)

        assert run.cancelled()

    @pytest.mark.asyncio
    async def test_cancelling_only_the_request_task_returns_an_error_result(self, ready_capability):
        from koda.services.openai_compatible_runner import run_openai_compatible

        process_holder: dict = {}
        async with self._hanging_server() as (base_url, request_received):
            with patch(
                "koda.services.openai_compatible_runner.build_llm_subprocess_env",
                return_value={"MISTRAL_API_KEY": "sk-test"},
            ):
                run = asyncio.create_task(
                    run_openai_compatible(
                        profile=self._local_profile(base_url),
                        query="hi",
                        work_dir="/tmp",
                        model="mistral-large-latest",
                        turn_mode="new_turn",
                        capabilities=ready_capability,
                        process_holder=process_holder,
                    )
                )
                await asyncio.wait_for(request_received.wait(), timeout=10)
                process_holder["task"].cancel()
                result = await asyncio.wait_for(run, timeout=10)

        assert result["error"] is True
        assert result["result"] == "mistral request cancelled."
        assert "task" not in process_holder


class TestUserContentBuilder:
    def test_text_only_returns_string(self, mistral_profile):
        content = _build_user_content(mistral_profile, "mistral-small-latest", "hello", None)
        assert content == "hello"

    def test_text_and_image_returns_blocks_for_vision_model(self, mistral_profile, tmp_path):
        image = tmp_path / "x.png"
        image.write_bytes(b"\x89PNG" + b"\x00" * 32)
        content = _build_user_content(mistral_profile, "pixtral-large-latest", "describe", [str(image)])
        assert isinstance(content, list)
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/")

    def test_image_skipped_for_non_vision_model(self, mistral_profile, tmp_path):
        image = tmp_path / "x.png"
        image.write_bytes(b"\x89PNG" + b"\x00" * 32)
        content = _build_user_content(mistral_profile, "mistral-large-latest", "describe", [str(image)])
        assert isinstance(content, str)


class TestProviderHttpProfile:
    def test_chat_url_joins_correctly(self, mistral_profile):
        assert mistral_profile.chat_url() == "https://api.mistral.ai/v1/chat/completions"

    def test_models_url_returns_none_when_absent(self, perplexity_profile):
        assert perplexity_profile.models_url() is None

    def test_health_url(self, perplexity_profile):
        assert perplexity_profile.health_url() == "https://api.perplexity.ai/"

    def test_headers_format_bearer(self, mistral_profile):
        headers = mistral_profile.headers("sk-key-abc")
        assert headers["Authorization"] == "Bearer sk-key-abc"
        assert headers["Content-Type"] == "application/json"

    def test_openrouter_profile_urls_match_docs(self):
        profile = get_provider_profile("openrouter")

        assert profile.chat_url() == "https://openrouter.ai/api/v1/chat/completions"
        assert profile.models_url() == "https://openrouter.ai/api/v1/models"
        assert profile.health_url() == "https://openrouter.ai/api/v1/key"
        assert profile.capability_probe == "health_only"

    def test_openrouter_headers_include_optional_attribution(self):
        profile = get_provider_profile("openrouter")
        env = {
            "OPENROUTER_HTTP_REFERER": "https://koda.example",
            "OPENROUTER_APP_TITLE": "Koda",
            "OPENROUTER_APP_CATEGORIES": "cli-agent,personal-agent",
        }

        headers = _profile_headers(profile, "sk-or-v1-test", env)

        assert headers["Authorization"] == "Bearer sk-or-v1-test"
        assert headers["HTTP-Referer"] == "https://koda.example"
        assert headers["X-OpenRouter-Title"] == "Koda"
        assert headers["X-OpenRouter-Categories"] == "cli-agent,personal-agent"


# SSRF: provider calls to a non-private base URL stay on public addresses


_PROVIDER_HOST = "provider.koda.test"


def _completion(text: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": text}}], "usage": {}}


async def _start_provider_server(*, redirect_chat: bool = False, redirect_models: bool = False):
    """Loopback stand-in for a provider; records every path it serves."""
    from aiohttp import web

    hits: list[str] = []

    async def models(request):
        hits.append(request.path)
        if redirect_models:
            raise web.HTTPTemporaryRedirect("/internal")
        return web.json_response({"data": []})

    async def chat(request):
        hits.append(request.path)
        if redirect_chat:
            raise web.HTTPTemporaryRedirect("/internal")  # 307 keeps the POST and its headers
        return web.json_response(_completion("reached"))

    async def internal(request):
        hits.append(request.path)
        return web.json_response(_completion("internal-secret"))

    async def internal_page(request):
        hits.append(request.path)
        # A probe that reached this would copy the body into ProviderCapabilities.errors.
        return web.Response(status=404, text="internal-secret")

    app = web.Application()
    app.router.add_get("/v1/models", models)
    app.router.add_post("/v1/chat/completions", chat)
    app.router.add_post("/internal", internal)
    app.router.add_get("/internal", internal_page)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, runner.addresses[0][1], hits


def _provider_dns(*, precheck_ip: str, connect_ip: str):
    """Fake DNS for the provider host.

    ``_check_url_safety`` resolves with no port while aiohttp resolves with the
    request port, so the two lookups can get different answers, as they do when
    a TTL-0 rebinding server changes its answer between check and connect.
    """
    import socket as socket_module

    real_getaddrinfo = socket_module.getaddrinfo

    def fake(host, service, *args, **kwargs):
        if host != _PROVIDER_HOST:
            return real_getaddrinfo(host, service, *args, **kwargs)
        ip = precheck_ip if service is None else connect_ip
        return [(socket_module.AF_INET, socket_module.SOCK_STREAM, 6, "", (ip, service or 0))]

    return patch.object(socket_module, "getaddrinfo", fake)


def _local_provider_profile(port: int) -> ProviderHttpProfile:
    return ProviderHttpProfile(provider_id="generic", base_url=f"http://{_PROVIDER_HOST}:{port}", auth_mode="local")


def _no_provider_env():
    return patch("koda.services.openai_compatible_runner.build_llm_subprocess_env", return_value={})


def _loopback_counts_as_public():
    """Let the guarded client reach the loopback test server, so only redirect handling is under test."""
    return patch("koda.services.http_client._is_private_ip", lambda ip: False)


class TestProviderRequestsStayOnPublicAddresses:
    @pytest.mark.asyncio
    async def test_chat_request_is_pinned_against_dns_rebinding(self, ready_capability):
        from koda.services.openai_compatible_runner import run_openai_compatible

        runner, port, hits = await _start_provider_server()
        try:
            with _no_provider_env(), _provider_dns(precheck_ip="93.184.216.34", connect_ip="127.0.0.1"):
                result = await run_openai_compatible(
                    profile=_local_provider_profile(port),
                    query="hi",
                    work_dir="/tmp",
                    model="m",
                    capabilities=ready_capability,
                )
        finally:
            await runner.cleanup()

        assert hits == []
        assert result["error"] is True
        assert "private/reserved" in result["result"]

    @pytest.mark.asyncio
    async def test_capability_probe_is_pinned_against_dns_rebinding(self):
        from koda.services.openai_compatible_runner import _probe_capabilities

        runner, port, hits = await _start_provider_server()
        try:
            with _no_provider_env(), _provider_dns(precheck_ip="93.184.216.34", connect_ip="127.0.0.1"):
                capability = await _probe_capabilities(_local_provider_profile(port), "new_turn")
        finally:
            await runner.cleanup()

        assert hits == []
        assert capability.can_execute is False
        assert "private/reserved" in capability.errors[0]

    @pytest.mark.asyncio
    async def test_chat_request_does_not_follow_unchecked_redirects(self, ready_capability):
        from koda.services.openai_compatible_runner import run_openai_compatible

        runner, port, hits = await _start_provider_server(redirect_chat=True)
        try:
            with (
                _no_provider_env(),
                _loopback_counts_as_public(),
                _provider_dns(precheck_ip="127.0.0.1", connect_ip="127.0.0.1"),
            ):
                result = await run_openai_compatible(
                    profile=_local_provider_profile(port),
                    query="hi",
                    work_dir="/tmp",
                    model="m",
                    capabilities=ready_capability,
                )
        finally:
            await runner.cleanup()

        assert hits == ["/v1/chat/completions"]
        assert result["error"] is True
        assert "HTTP 307" in result["result"]
        assert "internal-secret" not in result["result"]

    @pytest.mark.asyncio
    async def test_streaming_request_does_not_follow_unchecked_redirects(self, ready_capability):
        from koda.services.openai_compatible_runner import run_openai_compatible_streaming

        runner, port, hits = await _start_provider_server(redirect_chat=True)
        collector: dict = {}
        try:
            with (
                _no_provider_env(),
                _loopback_counts_as_public(),
                _provider_dns(precheck_ip="127.0.0.1", connect_ip="127.0.0.1"),
            ):
                chunks = [
                    chunk
                    async for chunk in run_openai_compatible_streaming(
                        profile=_local_provider_profile(port),
                        query="hi",
                        work_dir="/tmp",
                        model="m",
                        capabilities=ready_capability,
                        metadata_collector=collector,
                    )
                ]
        finally:
            await runner.cleanup()

        assert hits == ["/v1/chat/completions"]
        assert chunks == []
        assert collector["error"] is True
        assert "HTTP 307" in collector["error_message"]

    @pytest.mark.asyncio
    async def test_capability_probe_does_not_follow_unchecked_redirects(self):
        from koda.services.openai_compatible_runner import _probe_capabilities

        runner, port, hits = await _start_provider_server(redirect_models=True)
        try:
            with (
                _no_provider_env(),
                _loopback_counts_as_public(),
                _provider_dns(precheck_ip="127.0.0.1", connect_ip="127.0.0.1"),
            ):
                capability = await _probe_capabilities(_local_provider_profile(port), "new_turn")
        finally:
            await runner.cleanup()

        assert hits == ["/v1/models"]
        assert not any("internal-secret" in message for message in [*capability.errors, *capability.warnings])


class TestProcessEnvBaseUrlIsAnOperatorOverride:
    """A base URL from ``.env`` or the process env counts as an override, like a control-plane one.

    The profile builders read the same variable into ``profile.base_url``, so the
    override has to be judged against the vendor default, not against the profile.
    """

    @pytest.fixture(autouse=True)
    def _fresh_profiles(self):
        from koda.services.openai_compatible_runner import reset_provider_profile_cache

        reset_provider_profile_cache()
        yield
        reset_provider_profile_cache()

    @pytest.mark.parametrize("provider_id", sorted(OPENAI_COMPATIBLE_PROVIDERS))
    def test_process_env_base_url_may_point_at_private_hosts(self, provider_id, monkeypatch):
        from koda.services.openai_compatible_runner import _allows_private_base_url

        monkeypatch.setenv(PROVIDER_BASE_URL_ENV_KEYS[provider_id], "http://100.100.1.1:8000")
        profile = get_provider_profile(provider_id)

        assert profile.base_url == "http://100.100.1.1:8000"
        assert _allows_private_base_url(profile, {}) is True

    @pytest.mark.parametrize("provider_id", sorted(OPENAI_COMPATIBLE_PROVIDERS))
    def test_vendor_default_base_url_stays_guarded(self, provider_id, monkeypatch):
        from koda.services.openai_compatible_runner import _allows_private_base_url, reset_provider_profile_cache

        env_key = PROVIDER_BASE_URL_ENV_KEYS[provider_id]
        monkeypatch.delenv(env_key, raising=False)
        vendor_default = get_provider_profile(provider_id).base_url
        assert _allows_private_base_url(get_provider_profile(provider_id), {}) is False

        for configured in (vendor_default, vendor_default + "/"):
            monkeypatch.setenv(env_key, configured)
            reset_provider_profile_cache()
            assert _allows_private_base_url(get_provider_profile(provider_id), {}) is False

    @pytest.mark.asyncio
    async def test_probe_reaches_process_env_base_url_on_a_private_host(self, monkeypatch):
        from koda.services.openai_compatible_runner import _probe_capabilities

        runner, port, hits = await _start_provider_server()
        monkeypatch.setenv("DEEPSEEK_API_BASE_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        try:
            capability = await _probe_capabilities(get_provider_profile("deepseek"), "new_turn")
        finally:
            await runner.cleanup()

        assert capability.errors == []
        assert capability.can_execute is True
        assert hits == ["/v1/models"]
