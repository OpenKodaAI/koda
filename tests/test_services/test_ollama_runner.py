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
