"""xAI Grok runner — OpenAI-compatible chat with vision support on grok-*-vision."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from koda.config import XAI_FIRST_CHUNK_TIMEOUT, XAI_TIMEOUT
from koda.services.openai_compatible_runner import (
    get_openai_compatible_capabilities,
    run_openai_compatible,
    run_openai_compatible_streaming,
)
from koda.services.provider_http_profile import ProviderHttpProfile
from koda.services.provider_runtime import ProviderCapabilities, TurnMode

XAI_PROFILE = ProviderHttpProfile(
    provider_id="xai",
    base_url=os.environ.get("XAI_API_BASE_URL") or "https://api.x.ai",
    chat_path="/v1/chat/completions",
    models_path="/v1/models",
    first_chunk_timeout_seconds=float(XAI_FIRST_CHUNK_TIMEOUT),
    request_timeout_seconds=float(XAI_TIMEOUT),
    # Grok 4.x is multimodal end-to-end (vision is a default capability,
    # not a separate `*-vision` SKU as in Grok 2/3). Keep the older
    # vision-only SKUs for operators still pinned to legacy snapshots.
    vision_models=frozenset(
        {
            "grok-4.3",
            "grok-4.1-fast",
            "grok-4-fast",
            "grok-4-0709",
            "grok-4-vision-0709",
            "grok-2-vision-1212",
            "grok-vision-beta",
        }
    ),
)


async def get_xai_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    return await get_openai_compatible_capabilities(XAI_PROFILE, turn_mode)


async def run_xai(**kwargs: Any) -> dict[str, Any]:
    return await run_openai_compatible(profile=XAI_PROFILE, **kwargs)


async def run_xai_streaming(**kwargs: Any) -> AsyncIterator[str]:
    async for chunk in run_openai_compatible_streaming(profile=XAI_PROFILE, **kwargs):
        yield chunk
