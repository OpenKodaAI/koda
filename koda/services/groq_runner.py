"""Groq runner — ultra-low-latency LPU inference, OpenAI-compatible API."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from koda.config import GROQ_FIRST_CHUNK_TIMEOUT, GROQ_TIMEOUT
from koda.services.openai_compatible_runner import (
    get_openai_compatible_capabilities,
    run_openai_compatible,
    run_openai_compatible_streaming,
)
from koda.services.provider_http_profile import ProviderHttpProfile
from koda.services.provider_runtime import ProviderCapabilities, TurnMode

GROQ_PROFILE = ProviderHttpProfile(
    provider_id="groq",
    base_url=os.environ.get("GROQ_API_BASE_URL") or "https://api.groq.com/openai",
    chat_path="/v1/chat/completions",
    models_path="/v1/models",
    first_chunk_timeout_seconds=float(GROQ_FIRST_CHUNK_TIMEOUT),
    request_timeout_seconds=float(GROQ_TIMEOUT),
    vision_models=frozenset(
        {
            "llama-3.2-11b-vision-preview",
            "llama-3.2-90b-vision-preview",
        }
    ),
)


async def get_groq_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    return await get_openai_compatible_capabilities(GROQ_PROFILE, turn_mode)


async def run_groq(**kwargs: Any) -> dict[str, Any]:
    return await run_openai_compatible(profile=GROQ_PROFILE, **kwargs)


async def run_groq_streaming(**kwargs: Any) -> AsyncIterator[str]:
    async for chunk in run_openai_compatible_streaming(profile=GROQ_PROFILE, **kwargs):
        yield chunk
