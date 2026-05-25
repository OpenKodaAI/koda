"""llama.cpp runner — Metal-accelerated local inference via ``llama-server``.

``llama-server`` is the OpenAI-compatible HTTP server bundled with
``llama.cpp``. On Apple Silicon it uses the Metal backend automatically when
the binary is built with Metal support (``brew install llama.cpp`` ships a
Metal build). Koda treats it like any other OpenAI-compatible provider via
:mod:`koda.services.openai_compatible_runner`, with two extensions:

1. ``auth_mode="local"`` skips the API-key requirement (operators can still
   provide ``LLAMACPP_API_KEY`` for proxied setups).
2. ``extra_payload`` carries the GBNF grammar from
   :mod:`koda.services.structured_decoding` when
   ``STRUCTURED_DECODING_ENABLED`` is true, eliminating malformed
   ``<agent_cmd>`` blocks from small models.

When ``LOCAL_RUNTIME_AUTO_SPAWN`` is on, the supervisor in
:mod:`koda.services.local_runtime_supervisor` ensures ``llama-server`` is
running before the first request lands.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from koda.config import (
    LLAMACPP_API_BASE_URL,
    LLAMACPP_FIRST_CHUNK_TIMEOUT,
    LLAMACPP_GRAMMAR_FILE,
    LLAMACPP_TIMEOUT,
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
    extras = payload_extras_for_provider(
        "llamacpp",
        enabled=STRUCTURED_DECODING_ENABLED,
        grammar_override_path=LLAMACPP_GRAMMAR_FILE or None,
    )
    return ProviderHttpProfile(
        provider_id="llamacpp",
        base_url=LLAMACPP_API_BASE_URL or "http://127.0.0.1:8080",
        chat_path="/v1/chat/completions",
        models_path="/v1/models",
        first_chunk_timeout_seconds=float(LLAMACPP_FIRST_CHUNK_TIMEOUT),
        request_timeout_seconds=float(LLAMACPP_TIMEOUT),
        allow_private_base_url=True,
        capability_probe="models_endpoint",
        extra_payload=extras,
        auth_mode="local",
    )


LLAMACPP_PROFILE: ProviderHttpProfile = _build_profile()


async def _ensure_runtime() -> None:
    """Spawn ``llama-server`` via the supervisor when auto-spawn is effective.

    Auto-spawn fires when the operator explicitly opted in
    (``LOCAL_RUNTIME_AUTO_SPAWN=true``) OR when ``LOCAL_AUTO_OPTIMIZE`` is on
    (default), the llamacpp provider is enabled, and the binary is already
    on the PATH. The runtime_capabilities helper encapsulates that policy.
    """
    from koda.services.runtime_capabilities import effective_auto_spawn  # noqa: PLC0415

    if not effective_auto_spawn("llamacpp"):
        return
    from koda.services.local_runtime_supervisor import get_local_runtime_supervisor  # noqa: PLC0415

    supervisor = get_local_runtime_supervisor()
    await supervisor.ensure_running("llamacpp")


async def get_llamacpp_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    return await get_openai_compatible_capabilities(LLAMACPP_PROFILE, turn_mode)


async def run_llamacpp(**kwargs: Any) -> dict[str, Any]:
    await _ensure_runtime()
    return await run_openai_compatible(profile=LLAMACPP_PROFILE, **kwargs)


async def run_llamacpp_streaming(**kwargs: Any) -> AsyncIterator[str]:
    await _ensure_runtime()
    async for chunk in run_openai_compatible_streaming(profile=LLAMACPP_PROFILE, **kwargs):
        yield chunk
