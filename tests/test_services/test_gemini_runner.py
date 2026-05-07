"""Tests for the Gemini CLI runner."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.gemini_runner import (
    clear_gemini_capability_cache,
    get_gemini_capabilities,
    run_gemini,
)
from koda.services.provider_runtime import ProviderCapabilities


@pytest.fixture(autouse=True)
def _clear_capabilities():
    clear_gemini_capability_cache()
    yield
    clear_gemini_capability_cache()


def _ready_capability(turn_mode: str) -> ProviderCapabilities:
    return ProviderCapabilities(
        provider="gemini",
        turn_mode=turn_mode,  # type: ignore[arg-type]
        status="ready",
        can_execute=True,
        supports_native_resume=False,
    )


class TestGeminiCapabilities:
    @pytest.mark.asyncio
    async def test_api_key_mode_is_ready_when_key_exists(self, monkeypatch):
        monkeypatch.setenv("GEMINI_AUTH_MODE", "api_key")
        monkeypatch.setenv("GEMINI_API_KEY", "secret")

        capabilities = await get_gemini_capabilities("new_turn")

        assert capabilities.status == "ready"
        assert capabilities.can_execute is True
        assert capabilities.checked_via == "api_key_env"


class TestRunGemini:
    @pytest.mark.asyncio
    async def test_successful_run(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(
                json.dumps({"response": "Hello from Gemini", "usage": {"input_tokens": 5}}).encode(),
                b"",
            )
        )
        mock_proc.returncode = 0

        with patch("koda.services.gemini_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_gemini(
                query="hi",
                work_dir="/tmp",
                model="gemini-2.5-flash",
                turn_mode="new_turn",
                capabilities=_ready_capability("new_turn"),
            )

        assert result["error"] is False
        assert result["result"] == "Hello from Gemini"
        assert result["usage"] == {"input_tokens": 5}
        assert result["session_id"] is None

    @pytest.mark.asyncio
    async def test_image_requests_are_rejected_cleanly(self):
        result = await run_gemini(
            query="describe image",
            work_dir="/tmp",
            model="gemini-2.5-flash",
            image_paths=["/tmp/image.png"],
            turn_mode="new_turn",
            capabilities=_ready_capability("new_turn"),
        )

        assert result["error"] is True
        assert result["_error_kind"] == "adapter_contract"
