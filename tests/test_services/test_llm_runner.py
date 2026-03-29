"""Tests for provider-neutral LLM runner helpers."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.services.llm_runner import get_provider_health_snapshot, run_llm
from koda.services.provider_runtime import ProviderCapabilities


def _capability(
    provider: str,
    turn_mode: str,
    *,
    status: str = "ready",
    can_execute: bool = True,
    supports_native_resume: bool = True,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> ProviderCapabilities:
    return ProviderCapabilities(
        provider=provider,
        turn_mode=turn_mode,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        can_execute=can_execute,
        supports_native_resume=supports_native_resume,
        warnings=warnings or [],
        errors=errors or [],
    )


class TestRunLLM:
    @pytest.mark.asyncio
    async def test_routes_ollama_to_ollama_runner(self):
        with (
            patch(
                "koda.services.llm_runner.normalize_provider",
                side_effect=lambda provider: str(provider or "claude"),
            ),
            patch(
                "koda.services.llm_runner.get_provider_capabilities",
                new=AsyncMock(return_value=_capability("ollama", "new_turn", supports_native_resume=False)),
            ),
            patch(
                "koda.services.llm_runner.run_ollama",
                new=AsyncMock(return_value={"result": "ok", "session_id": None, "error": False}),
            ) as mock_run_ollama,
        ):
            result = await run_llm(
                provider="ollama",
                query="hello",
                work_dir="/tmp",
                model="qwen3:latest",
            )

        assert result["provider"] == "ollama"
        assert result["error"] is False
        assert mock_run_ollama.await_args.kwargs["turn_mode"] == "new_turn"

    @pytest.mark.asyncio
    async def test_infers_resume_turn_from_provider_session_id(self):
        with (
            patch(
                "koda.services.llm_runner.get_provider_capabilities",
                new=AsyncMock(return_value=_capability("codex", "resume_turn")),
            ),
            patch(
                "koda.services.llm_runner.run_codex",
                new=AsyncMock(return_value={"result": "ok", "session_id": "thread-1", "error": False}),
            ) as mock_run_codex,
        ):
            result = await run_llm(
                provider="codex",
                query="hello",
                work_dir="/tmp",
                model="gpt-5.4-mini",
                provider_session_id="thread-1",
            )

        assert result["turn_mode"] == "resume_turn"
        assert mock_run_codex.await_args.kwargs["turn_mode"] == "resume_turn"

    @pytest.mark.asyncio
    async def test_returns_contract_error_when_resume_capability_is_unavailable(self):
        with patch(
            "koda.services.llm_runner.get_provider_capabilities",
            new=AsyncMock(
                return_value=_capability(
                    "codex",
                    "resume_turn",
                    status="degraded",
                    can_execute=False,
                    supports_native_resume=False,
                    errors=["codex resume unavailable"],
                )
            ),
        ):
            result = await run_llm(
                provider="codex",
                query="hello",
                work_dir="/tmp",
                model="gpt-5.4-mini",
                provider_session_id="thread-1",
            )

        assert result["error"] is True
        assert result["error_kind"] == "adapter_contract"
        assert result["retryable"] is False


class TestProviderHealthSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_marks_provider_degraded_when_only_new_turn_is_available(self):
        async def _mock_capabilities(provider: str, turn_mode: str) -> ProviderCapabilities:
            if provider == "codex" and turn_mode == "resume_turn":
                return _capability(
                    provider,
                    turn_mode,
                    status="degraded",
                    can_execute=False,
                    supports_native_resume=False,
                    warnings=["resume degraded"],
                )
            return _capability(provider, turn_mode)

        with patch("koda.services.llm_runner.get_provider_capabilities", new=_mock_capabilities):
            snapshot = await get_provider_health_snapshot()

        assert snapshot["codex"]["status"] == "degraded"
        assert snapshot["codex"]["can_execute"] is True
        assert snapshot["codex"]["supports_native_resume"] is False
