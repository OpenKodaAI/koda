"""Provider-neutral LLM runner helpers."""

from __future__ import annotations

import contextlib
import functools
import importlib
import json
import os
import re
from collections.abc import AsyncIterator
from types import ModuleType
from typing import Any, cast

from koda.config import (
    AGENT_ID,
    AVAILABLE_PROVIDERS,
    CODEX_FIRST_CHUNK_TIMEOUT,
    FIRST_CHUNK_TIMEOUT,
    GEMINI_FIRST_CHUNK_TIMEOUT,
    LLAMACPP_FIRST_CHUNK_TIMEOUT,
    MLX_FIRST_CHUNK_TIMEOUT,
    PROVIDER_DEFAULT_MODELS,
    PROVIDER_FALLBACK_ORDER,
    PROVIDER_MODELS,
    TRANSCRIPT_REPLAY_LIMIT,
)
from koda.services.llamacpp_runner import (
    get_llamacpp_capabilities,
    run_llamacpp,
    run_llamacpp_streaming,
)
from koda.services.mlx_runner import (
    get_mlx_capabilities,
    run_mlx,
    run_mlx_streaming,
)
from koda.services.model_router import estimate_model
from koda.services.openai_compatible_runner import (
    OPENAI_COMPATIBLE_PROVIDERS,
    get_capabilities_for_provider,
    run_for_provider,
    run_streaming_for_provider,
)
from koda.services.provider_runtime import (
    ProviderCapabilities,
    TurnMode,
    infer_turn_mode,
    summarize_provider_health,
)
from koda.state.history_store import get_recent_session_transcript
from koda.utils.command_helpers import normalize_provider

# Native CLI / subprocess runners are loaded lazily. Each is a few hundred
# to ~1k lines of process-management logic. Deferring the import means an
# agent talking to a single provider (the common case) never pays the cost
# of loading the others.

_NATIVE_PROVIDER_MODULES: dict[str, str] = {
    "claude": "koda.services.claude_runner",
    "codex": "koda.services.codex_runner",
    "gemini": "koda.services.gemini_runner",
    "ollama": "koda.services.ollama_runner",
}

_NATIVE_FIRST_CHUNK_TIMEOUTS: dict[str, float] = {
    "claude": float(FIRST_CHUNK_TIMEOUT),
    "codex": float(CODEX_FIRST_CHUNK_TIMEOUT),
    "gemini": float(GEMINI_FIRST_CHUNK_TIMEOUT),
    "ollama": float(FIRST_CHUNK_TIMEOUT),
}


@functools.cache
def _native_runner(provider: str) -> ModuleType:
    """Return the lazily-loaded module for a native CLI/subprocess runner."""
    module_path = _NATIVE_PROVIDER_MODULES.get(provider)
    if module_path is None:
        raise KeyError(f"No native runner registered for provider {provider!r}")
    return importlib.import_module(module_path)


_agent_id_label = AGENT_ID or "default"

_COMMON_RETRY_PATTERN = re.compile(
    r"overloaded|rate.limit|too many requests|connection|timeout|temporarily unavailable|503|529",
    re.IGNORECASE,
)
_LOCAL_RUNTIME_RETRY_PATTERN = re.compile(
    (
        r"overloaded|rate.limit|too many requests|connection|timeout|temporarily unavailable|503|529|"
        r"connection refused|cuda|metal|out of memory|loading model|model not loaded"
    ),
    re.IGNORECASE,
)
_RETRYABLE_PATTERNS: dict[str, re.Pattern[str]] = {
    "claude": _COMMON_RETRY_PATTERN,
    "codex": _COMMON_RETRY_PATTERN,
    "gemini": _COMMON_RETRY_PATTERN,
    "ollama": re.compile(
        (
            r"overloaded|rate.limit|too many requests|connection|timeout|temporarily unavailable|503|529|"
            r"connection refused"
        ),
        re.IGNORECASE,
    ),
    "llamacpp": _LOCAL_RUNTIME_RETRY_PATTERN,
    "mlx": _LOCAL_RUNTIME_RETRY_PATTERN,
    "perplexity": _COMMON_RETRY_PATTERN,
    "mistral": _COMMON_RETRY_PATTERN,
    "qwen": _COMMON_RETRY_PATTERN,
    "kimi": _COMMON_RETRY_PATTERN,
    "groq": _COMMON_RETRY_PATTERN,
    "deepseek": _COMMON_RETRY_PATTERN,
    "xai": _COMMON_RETRY_PATTERN,
}

_OPENAI_COMPATIBLE_TIMEOUT_CONSTS: dict[str, str] = {
    "deepseek": "DEEPSEEK_FIRST_CHUNK_TIMEOUT",
    "groq": "GROQ_FIRST_CHUNK_TIMEOUT",
    "kimi": "KIMI_FIRST_CHUNK_TIMEOUT",
    "mistral": "MISTRAL_FIRST_CHUNK_TIMEOUT",
    "perplexity": "PERPLEXITY_FIRST_CHUNK_TIMEOUT",
    "qwen": "QWEN_FIRST_CHUNK_TIMEOUT",
    "xai": "XAI_FIRST_CHUNK_TIMEOUT",
}


def _build_http_provider_runners() -> dict[str, dict[str, Any]]:
    """Assemble the dispatch table for HTTP-only providers.

    Local OpenAI-compatible runtimes (llamacpp, mlx) keep their own modules
    because they own extra logic (auto-spawn supervisors, structured-decoding
    grammar plumbing). The seven cloud OpenAI-compatible providers are
    served by a single shared adapter via the registry in
    :mod:`koda.services.openai_compatible_runner` — bound here with
    :func:`functools.partial` so each provider keeps a stable callable.
    """
    from koda import config as _config

    runners: dict[str, dict[str, Any]] = {
        "llamacpp": {
            "run": run_llamacpp,
            "stream": run_llamacpp_streaming,
            "capabilities": get_llamacpp_capabilities,
            "first_chunk_timeout": float(LLAMACPP_FIRST_CHUNK_TIMEOUT),
        },
        "mlx": {
            "run": run_mlx,
            "stream": run_mlx_streaming,
            "capabilities": get_mlx_capabilities,
            "first_chunk_timeout": float(MLX_FIRST_CHUNK_TIMEOUT),
        },
    }
    for provider_id in OPENAI_COMPATIBLE_PROVIDERS:
        timeout_value = float(getattr(_config, _OPENAI_COMPATIBLE_TIMEOUT_CONSTS[provider_id]))
        runners[provider_id] = {
            "run": functools.partial(run_for_provider, provider_id),
            "stream": functools.partial(run_streaming_for_provider, provider_id),
            "capabilities": functools.partial(get_capabilities_for_provider, provider_id),
            "first_chunk_timeout": timeout_value,
        }
    return runners


_HTTP_PROVIDER_RUNNERS: dict[str, dict[str, Any]] = _build_http_provider_runners()


def get_provider_runtime_eligibility(
    payload: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return the provider runtime eligibility map from payload or snapshot env."""
    if isinstance(payload, dict):
        return {
            str(provider_id).strip().lower(): dict(value)
            for provider_id, value in payload.items()
            if isinstance(value, dict)
        }
    raw = (
        os.environ.get("AGENT_PROVIDER_RUNTIME_ELIGIBILITY_JSON", "")
        or os.environ.get("PROVIDER_RUNTIME_ELIGIBILITY_JSON", "")
    ).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(provider_id).strip().lower(): dict(value)
        for provider_id, value in parsed.items()
        if isinstance(value, dict)
    }


def get_provider_fallback_chain(
    primary_provider: str,
    *,
    eligibility: dict[str, dict[str, Any]] | None = None,
    query: str = "",
    has_images: bool = False,
    prefer_local_below: float | None = None,
) -> list[str]:
    """Return the provider execution order for one task.

    When ``query`` is supplied and the cascade-routing policy is enabled
    (``LOCAL_PREFER_BELOW_COMPLEXITY > 0`` or a per-agent override), the
    chain is reordered to prefer local runtimes for low-complexity queries.
    """
    primary = normalize_provider(primary_provider)
    eligibility_map = get_provider_runtime_eligibility(eligibility)
    ordered: list[str] = []
    for provider in [primary, *PROVIDER_FALLBACK_ORDER]:
        if provider in AVAILABLE_PROVIDERS and provider not in ordered:
            provider_eligibility = eligibility_map.get(provider)
            if provider_eligibility is not None and not bool(provider_eligibility.get("eligible", False)):
                continue
            ordered.append(provider)

    if query:
        # Lazy import keeps the policy module out of import-time cycles when
        # the cascade feature is off (the common case).
        from koda.services.local_routing_policy import adjust_chain_for_local_preference  # noqa: PLC0415

        ordered = adjust_chain_for_local_preference(
            ordered,
            query=query,
            has_images=has_images,
            prefer_below=prefer_local_below,
            eligibility=eligibility_map,
        )
    return ordered


def resolve_provider_model(
    provider: str,
    *,
    preferred_model: str | None = None,
    query: str = "",
    auto_model: bool = False,
    has_images: bool = False,
) -> str:
    """Resolve a usable model for the chosen provider."""
    normalized = normalize_provider(provider)
    available_models = PROVIDER_MODELS.get(normalized, [])
    if auto_model:
        return estimate_model(query, provider=normalized, has_images=has_images)
    if preferred_model in available_models:
        return str(preferred_model)
    return PROVIDER_DEFAULT_MODELS.get(normalized, estimate_model(query, provider=normalized, has_images=has_images))


def is_retryable_provider_error(provider: str, error_message: str | None) -> bool:
    """Classify provider errors consistently for task retry/fallback handling."""
    if not error_message:
        return False
    pattern = _RETRYABLE_PATTERNS.get(normalize_provider(provider), _RETRYABLE_PATTERNS["claude"])
    return bool(pattern.search(error_message))


async def get_provider_capabilities(provider: str, turn_mode: TurnMode) -> ProviderCapabilities:
    """Return runtime compatibility for one provider and turn mode."""
    normalized = normalize_provider(provider)
    http_runner = _HTTP_PROVIDER_RUNNERS.get(normalized)
    if http_runner is not None:
        capabilities: ProviderCapabilities = await http_runner["capabilities"](turn_mode)
        return capabilities
    native_provider = normalized if normalized in _NATIVE_PROVIDER_MODULES else "claude"
    runner = _native_runner(native_provider)
    capabilities_fn = getattr(runner, f"get_{native_provider}_capabilities")
    return cast("ProviderCapabilities", await capabilities_fn(turn_mode))


async def get_provider_health_snapshot() -> dict[str, dict[str, Any]]:
    """Return aggregated provider runtime compatibility state."""
    snapshot: dict[str, dict[str, Any]] = {}
    for provider in AVAILABLE_PROVIDERS:
        turn_capabilities: dict[TurnMode, ProviderCapabilities] = {
            "new_turn": await get_provider_capabilities(provider, "new_turn"),
            "resume_turn": await get_provider_capabilities(provider, "resume_turn"),
        }
        snapshot[provider] = summarize_provider_health(provider, turn_capabilities)
    return snapshot


async def warm_provider_capabilities() -> dict[str, dict[str, Any]]:
    """Warm provider compatibility checks and publish health/audit metrics."""
    snapshot = await get_provider_health_snapshot()
    from koda.services import audit, metrics

    state_map = {"unavailable": 0, "degraded": 1, "ready": 2}
    for provider, provider_snapshot in snapshot.items():
        for turn_mode, turn_snapshot in provider_snapshot["turn_modes"].items():
            metrics.PROVIDER_COMPATIBILITY_STATE.labels(
                agent_id=_agent_id_label,
                provider=provider,
                turn_mode=turn_mode,
            ).set(state_map[turn_snapshot["status"]])
            audit.emit_task_lifecycle(
                f"system.provider_{turn_snapshot['status']}",
                provider=provider,
                turn_mode=turn_mode,
                checked_via=turn_snapshot["checked_via"],
                warnings=turn_snapshot["warnings"],
                errors=turn_snapshot["errors"],
            )
    return snapshot


def build_bootstrap_prompt(
    *,
    user_id: int,
    canonical_session_id: str,
    current_query: str,
    from_provider: str,
    to_provider: str,
    transcript_limit: int = TRANSCRIPT_REPLAY_LIMIT,
    extra_context: str | None = None,
) -> str:
    """Build a bootstrap prompt when switching providers without native resume state."""
    transcript: list[tuple[str, str, str | None, str, str | None]] = []
    with contextlib.suppress(RuntimeError):
        transcript = get_recent_session_transcript(user_id, canonical_session_id, limit=transcript_limit)
    lines = [
        "You are continuing an existing conversation inside a provider-neutral coding session.",
        f"Canonical session id: {canonical_session_id}",
        f"Previous provider: {from_provider}",
        f"Current provider: {to_provider}",
        "",
        "Keep the same memory, context, working assumptions, and conversation state.",
    ]
    if extra_context:
        lines.extend(["", "Runtime handoff context:", extra_context.strip()])
    if transcript:
        lines.extend(["", "Recent transcript:"])
        for timestamp, provider, model, query_text, response_text in transcript:
            lines.extend(
                [
                    f"[{timestamp}] USER ({provider}/{model or 'unknown'}):",
                    query_text.strip()[:6000],
                    f"[{timestamp}] ASSISTANT ({provider}/{model or 'unknown'}):",
                    (response_text or "").strip()[:10000],
                    "",
                ]
            )
    lines.extend(["Current user request:", current_query.strip()])
    return "\n".join(lines).strip()


async def run_llm(
    *,
    provider: str,
    query: str,
    work_dir: str,
    model: str,
    provider_session_id: str | None = None,
    max_budget: float = 0.0,
    process_holder: dict | None = None,
    system_prompt: str | None = None,
    image_paths: list[str] | None = None,
    permission_mode: str | None = None,
    max_turns: int = 25,
    turn_mode: TurnMode | None = None,
    dry_run: bool = False,
    runtime_task_id: int | None = None,
    effort: str | int | None = None,
) -> dict[str, Any]:
    """Run one non-streaming LLM turn through the selected provider."""
    normalized = normalize_provider(provider)
    resolved_turn_mode = turn_mode or infer_turn_mode(provider_session_id)
    capabilities = await get_provider_capabilities(normalized, resolved_turn_mode)
    if not capabilities.can_execute:
        error_kind = "adapter_contract" if resolved_turn_mode == "resume_turn" else "provider_runtime"
        message = capabilities.errors[0] if capabilities.errors else f"{normalized} runtime unavailable."
        if capabilities.warnings:
            message = f"{message}\n" + "\n".join(capabilities.warnings)
        return {
            "provider": normalized,
            "result": message,
            "session_id": provider_session_id,
            "provider_session_id": provider_session_id,
            "cost_usd": 0.0,
            "usage": {},
            "error": True,
            "turn_mode": resolved_turn_mode,
            "supports_native_resume": capabilities.supports_native_resume,
            "error_kind": error_kind,
            "retryable": False,
            "warnings": list(capabilities.warnings),
        }
    http_runner = _HTTP_PROVIDER_RUNNERS.get(normalized)
    if http_runner is not None:
        result_obj: dict[str, Any] = await http_runner["run"](
            query=query,
            work_dir=work_dir,
            model=model,
            session_id=provider_session_id,
            max_budget=max_budget,
            process_holder=process_holder,
            system_prompt=system_prompt,
            image_paths=image_paths,
            permission_mode=permission_mode,
            max_turns=max_turns,
            turn_mode=resolved_turn_mode,
            capabilities=capabilities,
            dry_run=dry_run,
            runtime_task_id=runtime_task_id,
            effort=effort,
        )
        result = result_obj
    else:
        target = normalized if normalized in _NATIVE_PROVIDER_MODULES else "claude"
        runner = _native_runner(target)
        run_fn = getattr(runner, f"run_{target}")
        kwargs: dict[str, Any] = dict(
            query=query,
            work_dir=work_dir,
            model=model,
            session_id=provider_session_id,
            max_budget=max_budget,
            process_holder=process_holder,
            system_prompt=system_prompt,
            image_paths=image_paths,
            permission_mode=permission_mode,
            max_turns=max_turns,
            turn_mode=resolved_turn_mode,
            capabilities=capabilities,
            dry_run=dry_run,
        )
        # ollama_runner predates the runtime_task_id / effort knobs and
        # rejects them as unexpected keyword arguments.
        if target != "ollama":
            kwargs["runtime_task_id"] = runtime_task_id
            kwargs["effort"] = effort
        result = await run_fn(**kwargs)
    result["provider"] = normalized
    result["provider_session_id"] = result.get("session_id")
    result["turn_mode"] = result.get("_turn_mode", resolved_turn_mode)
    result["supports_native_resume"] = result.get("_supports_native_resume", capabilities.supports_native_resume)
    result["error_kind"] = result.get("_error_kind", "")
    result["retryable"] = bool(result.get("_retryable"))
    result["warnings"] = list(dict.fromkeys([*capabilities.warnings, *(result.get("warnings") or [])]))
    return result


async def run_llm_streaming(
    *,
    provider: str,
    query: str,
    work_dir: str,
    model: str,
    provider_session_id: str | None = None,
    max_budget: float = 0.0,
    process_holder: dict | None = None,
    system_prompt: str | None = None,
    image_paths: list[str] | None = None,
    first_chunk_timeout: float | None = None,
    permission_mode: str | None = None,
    max_turns: int = 25,
    metadata_collector: dict | None = None,
    turn_mode: TurnMode | None = None,
    dry_run: bool = False,
    runtime_task_id: int | None = None,
    effort: str | int | None = None,
) -> AsyncIterator[str]:
    """Stream one LLM turn through the selected provider."""
    normalized = normalize_provider(provider)
    resolved_turn_mode = turn_mode or infer_turn_mode(provider_session_id)
    capabilities = await get_provider_capabilities(normalized, resolved_turn_mode)
    if metadata_collector is not None:
        metadata_collector["provider"] = normalized
        metadata_collector["turn_mode"] = resolved_turn_mode
        metadata_collector["supports_native_resume"] = capabilities.supports_native_resume
        if capabilities.warnings:
            warnings = [*metadata_collector.get("warnings", []), *capabilities.warnings]
            metadata_collector["warnings"] = list(dict.fromkeys(warnings))

    if not capabilities.can_execute:
        if metadata_collector is not None:
            error_kind = "adapter_contract" if resolved_turn_mode == "resume_turn" else "provider_runtime"
            message = capabilities.errors[0] if capabilities.errors else f"{normalized} runtime unavailable."
            if capabilities.warnings:
                message = f"{message}\n" + "\n".join(capabilities.warnings)
            metadata_collector["error"] = True
            metadata_collector["error_message"] = message
            metadata_collector["error_kind"] = error_kind
            metadata_collector["retryable"] = False
        return

    http_runner = _HTTP_PROVIDER_RUNNERS.get(normalized)
    if http_runner is not None:
        effective_first_chunk = (
            first_chunk_timeout if first_chunk_timeout is not None else float(http_runner["first_chunk_timeout"])
        )
        async for chunk in http_runner["stream"](
            query=query,
            work_dir=work_dir,
            model=model,
            session_id=provider_session_id,
            max_budget=max_budget,
            process_holder=process_holder,
            system_prompt=system_prompt,
            image_paths=image_paths,
            first_chunk_timeout=effective_first_chunk,
            permission_mode=permission_mode,
            max_turns=max_turns,
            metadata_collector=metadata_collector,
            turn_mode=resolved_turn_mode,
            capabilities=capabilities,
            dry_run=dry_run,
            runtime_task_id=runtime_task_id,
            effort=effort,
        ):
            yield chunk
        return
    target = normalized if normalized in _NATIVE_PROVIDER_MODULES else "claude"
    runner = _native_runner(target)
    stream_fn = getattr(runner, f"run_{target}_streaming")
    effective_first_chunk = (
        first_chunk_timeout if first_chunk_timeout is not None else _NATIVE_FIRST_CHUNK_TIMEOUTS[target]
    )
    kwargs: dict[str, Any] = dict(
        query=query,
        work_dir=work_dir,
        model=model,
        session_id=provider_session_id,
        max_budget=max_budget,
        process_holder=process_holder,
        system_prompt=system_prompt,
        image_paths=image_paths,
        first_chunk_timeout=effective_first_chunk,
        permission_mode=permission_mode,
        max_turns=max_turns,
        metadata_collector=metadata_collector,
        turn_mode=resolved_turn_mode,
        capabilities=capabilities,
        dry_run=dry_run,
    )
    if target != "ollama":
        kwargs["runtime_task_id"] = runtime_task_id
        kwargs["effort"] = effort
    async for chunk in stream_fn(**kwargs):
        yield chunk


def summarize_native_items(native_items: list[dict[str, Any]]) -> str:
    """Build a compact provider-agnostic summary from native execution items."""
    categories: list[str] = []
    for item in native_items:
        item_type = str(item.get("type") or "")
        if item_type == "command_execution":
            command = item.get("command") or item.get("input", {}).get("command") or item.get("title") or "shell"
            categories.append(f"shell({command})")
        elif item_type in {"mcp_tool_call", "web_search", "todo_list"}:
            categories.append(item_type.replace("_", " "))
        elif item_type == "file_change":
            kind = item.get("kind") or item.get("change_type") or "changed"
            path = item.get("path") or item.get("file_path") or "file"
            categories.append(f"{kind} {path}")
    if not categories:
        return ""
    unique = list(dict.fromkeys(categories))
    return "Tools: " + ", ".join(unique[:6])


def serialize_usage(usage: dict[str, Any] | None) -> str:
    """Serialize usage metadata consistently."""
    return json.dumps(usage or {}, default=str)
