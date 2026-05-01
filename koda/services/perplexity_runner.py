"""Perplexity Sonar runner — OpenAI-compatible chat with native web search."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from koda.config import PERPLEXITY_FIRST_CHUNK_TIMEOUT, PERPLEXITY_TIMEOUT
from koda.services.openai_compatible_runner import (
    get_openai_compatible_capabilities,
    run_openai_compatible,
    run_openai_compatible_streaming,
)
from koda.services.provider_http_profile import ProviderHttpProfile
from koda.services.provider_runtime import ProviderCapabilities, TurnMode

PERPLEXITY_PROFILE = ProviderHttpProfile(
    provider_id="perplexity",
    base_url=os.environ.get("PERPLEXITY_API_BASE_URL") or "https://api.perplexity.ai",
    chat_path="/chat/completions",
    models_path=None,
    capability_probe="health_only",
    health_path="/",
    first_chunk_timeout_seconds=float(PERPLEXITY_FIRST_CHUNK_TIMEOUT),
    request_timeout_seconds=float(PERPLEXITY_TIMEOUT),
)


async def get_perplexity_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    return await get_openai_compatible_capabilities(PERPLEXITY_PROFILE, turn_mode)


async def run_perplexity(**kwargs: Any) -> dict[str, Any]:
    return await run_openai_compatible(profile=PERPLEXITY_PROFILE, **kwargs)


async def run_perplexity_streaming(**kwargs: Any) -> AsyncIterator[str]:
    async for chunk in run_openai_compatible_streaming(profile=PERPLEXITY_PROFILE, **kwargs):
        yield chunk
