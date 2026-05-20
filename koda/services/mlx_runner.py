"""MLX runner — Apple-native local inference via ``mlx-openai-server``.

MLX is Apple's machine-learning framework with first-class Metal support and
a unified-memory architecture that removes the PCIe bottleneck present on
discrete-GPU stacks. ``mlx-openai-server`` (``python -m mlx_lm.server``)
exposes an OpenAI-compatible HTTP surface, so Koda plugs in via
:mod:`koda.services.openai_compatible_runner` with ``auth_mode="local"``.

MLX server-side support for grammar / regex constraints is not yet
finalized as of early 2026, so constrained decoding stays a no-op for this
provider; structured-output reliability for MLX must come from prompt
engineering and tool-loop validation in :mod:`koda.services.tool_dispatcher`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from koda.config import (
    MLX_API_BASE_URL,
    MLX_FIRST_CHUNK_TIMEOUT,
    MLX_TIMEOUT,
    STRUCTURED_DECODING_ENABLED,
)
from koda.services.openai_compatible_runner import (
    get_openai_compatible_capabilities,
    run_openai_compatible,
    run_openai_compatible_streaming,
)
from koda.services.provider_http_profile import ProviderHttpProfile
from koda.services.provider_runtime import ProviderCapabilities, TurnMode
from koda.services.structured_decoding import payload_extras_for_provider


def _build_profile() -> ProviderHttpProfile:
    extras = payload_extras_for_provider("mlx", enabled=STRUCTURED_DECODING_ENABLED)
    return ProviderHttpProfile(
        provider_id="mlx",
        base_url=MLX_API_BASE_URL or "http://127.0.0.1:8000",
        chat_path="/v1/chat/completions",
        models_path="/v1/models",
        first_chunk_timeout_seconds=float(MLX_FIRST_CHUNK_TIMEOUT),
        request_timeout_seconds=float(MLX_TIMEOUT),
        allow_private_base_url=True,
        capability_probe="models_endpoint",
        extra_payload=extras,
        auth_mode="local",
    )


MLX_PROFILE: ProviderHttpProfile = _build_profile()


async def _ensure_runtime() -> None:
    """Spawn ``mlx-openai-server`` via the supervisor when auto-spawn is effective."""
    from koda.services.runtime_capabilities import effective_auto_spawn  # noqa: PLC0415

    if not effective_auto_spawn("mlx"):
        return
    from koda.services.local_runtime_supervisor import get_local_runtime_supervisor  # noqa: PLC0415

    supervisor = get_local_runtime_supervisor()
    await supervisor.ensure_running("mlx")


async def get_mlx_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    return await get_openai_compatible_capabilities(MLX_PROFILE, turn_mode)


async def run_mlx(**kwargs: Any) -> dict[str, Any]:
    await _ensure_runtime()
    return await run_openai_compatible(profile=MLX_PROFILE, **kwargs)


async def run_mlx_streaming(**kwargs: Any) -> AsyncIterator[str]:
    await _ensure_runtime()
    async for chunk in run_openai_compatible_streaming(profile=MLX_PROFILE, **kwargs):
        yield chunk
