"""Tests for the Ollama API runner."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.services.ollama_runner import (
    clear_ollama_capability_cache,
    get_ollama_capabilities,
    run_ollama,
)
from koda.services.provider_runtime import ProviderCapabilities


@pytest.fixture(autouse=True)
def _clear_capabilities():
    clear_ollama_capability_cache()
    yield
    clear_ollama_capability_cache()


def _ready_capability(turn_mode: str) -> ProviderCapabilities:
    return ProviderCapabilities(
        provider="ollama",
        turn_mode=turn_mode,  # type: ignore[arg-type]
        status="ready",
        can_execute=True,
        supports_native_resume=False,
    )


class TestOllamaCapabilities:
    @pytest.mark.asyncio
    async def test_local_mode_is_ready_when_probe_succeeds(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_AUTH_MODE", "local")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

        with patch(
            "koda.services.ollama_runner.verify_provider_local_connection",
            return_value=type(
                "ProbeResult",
                (),
                {"verified": True, "last_error": "", "checked_via": "local_probe"},
            )(),
        ):
            capabilities = await get_ollama_capabilities("new_turn")

        assert capabilities.status == "ready"
        assert capabilities.can_execute is True
        assert capabilities.checked_via == "local_probe"


class TestOllamaBaseUrlResolution:
    """Regression tests: api_key mode must always target Ollama Cloud,
    even when the host process has a stale ``OLLAMA_BASE_URL`` pointing at
    localhost from a prior local-mode setup. Without these guards, every
    chat request fails with ``<urlopen error [Errno 61] Connection refused>``.
    """

    def test_configured_base_url_returns_cloud_in_api_key_mode_regardless_of_env(self, monkeypatch):
        from koda.services.ollama_runner import _configured_base_url

        # Even with a stale localhost env from a prior local setup, api_key
        # mode must hardcode the cloud endpoint.
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        assert _configured_base_url("api_key") == "https://ollama.com"

        # And the docker-host alias is similarly ignored in api_key mode.
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
        assert _configured_base_url("api_key") == "https://ollama.com"

    def test_configured_base_url_preserves_local_overrides_in_local_mode(self, monkeypatch):
        from koda.services.ollama_runner import _configured_base_url

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        assert _configured_base_url("local") == "http://127.0.0.1:11434"

    @pytest.mark.asyncio
    async def test_chat_request_targets_cloud_in_api_key_mode_even_with_localhost_env(self, monkeypatch):
        """End-to-end: even when the operator's ``OLLAMA_BASE_URL`` is stuck
        on localhost, the runtime chat call must hit ``https://ollama.com``
        once they've connected via API key.
        """
        import io
        import json

        from koda.services import ollama_runner

        # Simulate a stale localhost env carried from a previous local-mode
        # configuration. After clicking "Connect" with an API key the user
        # expects the runtime to pivot to the cloud endpoint.
        monkeypatch.setenv("OLLAMA_AUTH_MODE", "api_key")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        monkeypatch.setenv("OLLAMA_API_KEY", "ollama-cloud-key")

        captured: dict[str, object] = {}

        class _Resp:
            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "message": {"role": "assistant", "content": "ok"},
                        "prompt_eval_count": 1,
                        "eval_count": 1,
                    }
                ).encode("utf-8")

        def _fake_urlopen(request, timeout=None):  # noqa: ARG001
            captured["url"] = request.full_url
            captured["headers"] = {key.lower(): value for key, value in request.header_items()}
            return _Resp()

        monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
        # The runner imports urlopen via the ``urllib_request`` alias.
        monkeypatch.setattr(ollama_runner.urllib_request, "urlopen", _fake_urlopen)

        result = await run_ollama(
            query="hi",
            work_dir="/tmp",
            model="qwen3:latest",
            turn_mode="new_turn",
            capabilities=_ready_capability("new_turn"),
        )

        url = str(captured.get("url", ""))
        assert result["error"] is False, f"chat call failed: {result}"
        assert url.startswith("https://ollama.com/"), f"api_key mode must route chat to Ollama Cloud, got {url!r}"
        assert "localhost" not in url, "Regression: a stale localhost env leaked into the cloud chat URL"
        # The Bearer auth header must travel with the request.
        headers = captured.get("headers") or {}
        assert isinstance(headers, dict)
        assert headers.get("authorization") == "Bearer ollama-cloud-key"
        # Suppress the unused stdlib import (we monkey-patched the module
        # import path instead).
        del io


class TestRunOllama:
    @pytest.mark.asyncio
    async def test_successful_run(self):
        with patch(
            "koda.services.ollama_runner.asyncio.to_thread",
            new=AsyncMock(
                return_value=(
                    {
                        "message": {"role": "assistant", "content": "Hello from Ollama"},
                        "prompt_eval_count": 7,
                        "eval_count": 13,
                    },
                    "local",
                )
            ),
        ):
            result = await run_ollama(
                query="hi",
                work_dir="/tmp",
                model="qwen3:latest",
                turn_mode="new_turn",
                capabilities=_ready_capability("new_turn"),
            )

        assert result["error"] is False
        assert result["result"] == "Hello from Ollama"
        assert result["usage"] == {"input_tokens": 7, "output_tokens": 13}
        assert result["session_id"] is None

    @pytest.mark.asyncio
    async def test_image_requests_are_rejected_cleanly(self):
        result = await run_ollama(
            query="describe image",
            work_dir="/tmp",
            model="qwen3:latest",
            image_paths=["/tmp/image.png"],
            turn_mode="new_turn",
            capabilities=_ready_capability("new_turn"),
        )

        assert result["error"] is True
        assert result["_error_kind"] == "adapter_contract"
