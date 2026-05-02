"""Qwen runner — Alibaba DashScope International, OpenAI-compatible mode."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from koda.config import QWEN_FIRST_CHUNK_TIMEOUT, QWEN_TIMEOUT
from koda.services.openai_compatible_runner import (
    get_openai_compatible_capabilities,
    run_openai_compatible,
    run_openai_compatible_streaming,
)
from koda.services.provider_http_profile import ProviderHttpProfile
from koda.services.provider_runtime import ProviderCapabilities, TurnMode

QWEN_PROFILE = ProviderHttpProfile(
    provider_id="qwen",
    base_url=os.environ.get("QWEN_API_BASE_URL") or "https://dashscope-intl.aliyuncs.com",
    chat_path="/compatible-mode/v1/chat/completions",
    models_path="/compatible-mode/v1/models",
    first_chunk_timeout_seconds=float(QWEN_FIRST_CHUNK_TIMEOUT),
    request_timeout_seconds=float(QWEN_TIMEOUT),
    # Vision-capable Qwen models declared in the catalog. The qwen3-vl-*
    # variants were missing previously, which caused image inputs to be
    # silently dropped before reaching DashScope.
    vision_models=frozenset(
        {
            "qwen3-vl-max",
            "qwen3-vl-plus",
            "qwen3-vl-flash",
            "qwen-vl-max",
            "qwen-vl-max-latest",
            "qwen-vl-plus",
            "qwen-vl-plus-latest",
            "qwen2-vl-72b-instruct",
            "qwen2.5-vl-72b-instruct",
            "qvq-72b-preview",
        }
    ),
)


async def get_qwen_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    return await get_openai_compatible_capabilities(QWEN_PROFILE, turn_mode)


async def run_qwen(**kwargs: Any) -> dict[str, Any]:
    return await run_openai_compatible(profile=QWEN_PROFILE, **kwargs)


async def run_qwen_streaming(**kwargs: Any) -> AsyncIterator[str]:
    async for chunk in run_openai_compatible_streaming(profile=QWEN_PROFILE, **kwargs):
        yield chunk
