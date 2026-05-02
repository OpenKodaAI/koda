"""Kimi (Moonshot AI) runner — OpenAI-compatible chat with 128K context."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from koda.config import KIMI_FIRST_CHUNK_TIMEOUT, KIMI_TIMEOUT
from koda.services.openai_compatible_runner import (
    get_openai_compatible_capabilities,
    run_openai_compatible,
    run_openai_compatible_streaming,
)
from koda.services.provider_http_profile import ProviderHttpProfile
from koda.services.provider_runtime import ProviderCapabilities, TurnMode

KIMI_PROFILE = ProviderHttpProfile(
    provider_id="kimi",
    base_url=os.environ.get("KIMI_API_BASE_URL") or "https://api.moonshot.ai",
    chat_path="/v1/chat/completions",
    models_path="/v1/models",
    first_chunk_timeout_seconds=float(KIMI_FIRST_CHUNK_TIMEOUT),
    request_timeout_seconds=float(KIMI_TIMEOUT),
    # Kimi K2 family is natively multimodal (text + image input). Older
    # `kimi-vision-*` and `moonshot-v1-vision-*` SKUs are kept for
    # operators still pinned to those snapshots.
    vision_models=frozenset(
        {
            "kimi-k2.6",
            "kimi-k2.5",
            "kimi-latest",
            "kimi-latest-vision",
            "kimi-vision-2024-12-09",
            "moonshot-v1-vision-preview",
        }
    ),
)


async def get_kimi_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    return await get_openai_compatible_capabilities(KIMI_PROFILE, turn_mode)


async def run_kimi(**kwargs: Any) -> dict[str, Any]:
    return await run_openai_compatible(profile=KIMI_PROFILE, **kwargs)


async def run_kimi_streaming(**kwargs: Any) -> AsyncIterator[str]:
    async for chunk in run_openai_compatible_streaming(profile=KIMI_PROFILE, **kwargs):
        yield chunk
