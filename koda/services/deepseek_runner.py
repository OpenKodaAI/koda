"""DeepSeek runner — V3 chat and R1 reasoner, OpenAI-compatible with prompt caching."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from koda.config import DEEPSEEK_FIRST_CHUNK_TIMEOUT, DEEPSEEK_TIMEOUT
from koda.services.openai_compatible_runner import (
    get_openai_compatible_capabilities,
    run_openai_compatible,
    run_openai_compatible_streaming,
)
from koda.services.provider_http_profile import ProviderHttpProfile
from koda.services.provider_runtime import ProviderCapabilities, TurnMode

DEEPSEEK_PROFILE = ProviderHttpProfile(
    provider_id="deepseek",
    base_url=os.environ.get("DEEPSEEK_API_BASE_URL") or "https://api.deepseek.com",
    chat_path="/v1/chat/completions",
    models_path="/v1/models",
    first_chunk_timeout_seconds=float(DEEPSEEK_FIRST_CHUNK_TIMEOUT),
    request_timeout_seconds=float(DEEPSEEK_TIMEOUT),
)


async def get_deepseek_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    return await get_openai_compatible_capabilities(DEEPSEEK_PROFILE, turn_mode)


async def run_deepseek(**kwargs: Any) -> dict[str, Any]:
    return await run_openai_compatible(profile=DEEPSEEK_PROFILE, **kwargs)


async def run_deepseek_streaming(**kwargs: Any) -> AsyncIterator[str]:
    async for chunk in run_openai_compatible_streaming(profile=DEEPSEEK_PROFILE, **kwargs):
        yield chunk
