"""Mistral La Plateforme runner — OpenAI-compatible chat, vision via Pixtral."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from koda.config import MISTRAL_FIRST_CHUNK_TIMEOUT, MISTRAL_TIMEOUT
from koda.services.openai_compatible_runner import (
    get_openai_compatible_capabilities,
    run_openai_compatible,
    run_openai_compatible_streaming,
)
from koda.services.provider_http_profile import ProviderHttpProfile
from koda.services.provider_runtime import ProviderCapabilities, TurnMode

MISTRAL_PROFILE = ProviderHttpProfile(
    provider_id="mistral",
    base_url=os.environ.get("MISTRAL_API_BASE_URL") or "https://api.mistral.ai",
    chat_path="/v1/chat/completions",
    models_path="/v1/models",
    first_chunk_timeout_seconds=float(MISTRAL_FIRST_CHUNK_TIMEOUT),
    request_timeout_seconds=float(MISTRAL_TIMEOUT),
    vision_models=frozenset(
        {
            "pixtral-large-latest",
            "pixtral-large-2411",
            "pixtral-12b-2409",
            "pixtral-12b",
            "pixtral-12b-latest",
        }
    ),
)


async def get_mistral_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    return await get_openai_compatible_capabilities(MISTRAL_PROFILE, turn_mode)


async def run_mistral(**kwargs: Any) -> dict[str, Any]:
    return await run_openai_compatible(profile=MISTRAL_PROFILE, **kwargs)


async def run_mistral_streaming(**kwargs: Any) -> AsyncIterator[str]:
    async for chunk in run_openai_compatible_streaming(profile=MISTRAL_PROFILE, **kwargs):
        yield chunk
