"""Provider-neutral LLM runner helpers."""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections.abc import AsyncIterator
from typing import Any

from koda.config import (
    AGENT_ID,
    AVAILABLE_PROVIDERS,
    CODEX_FIRST_CHUNK_TIMEOUT,
    FIRST_CHUNK_TIMEOUT,
    GEMINI_FIRST_CHUNK_TIMEOUT,
    PROVIDER_DEFAULT_MODELS,
    PROVIDER_FALLBACK_ORDER,
    PROVIDER_MODELS,
    TRANSCRIPT_REPLAY_LIMIT,
)
from koda.services.claude_runner import (
    get_claude_capabilities,
    run_claude,
    run_claude_streaming,
)
from koda.services.codex_runner import (
    get_codex_capabilities,
    run_codex,
    run_codex_streaming,
)
from koda.services.gemini_runner import (
    get_gemini_capabilities,
    run_gemini,
    run_gemini_streaming,
)
from koda.services.model_router import estimate_model
from koda.services.ollama_runner import (
    get_ollama_capabilities,
    run_ollama,
    run_ollama_streaming,
)
from koda.services.provider_runtime import (
    ProviderCapabilities,
    TurnMode,
    infer_turn_mode,
    summarize_provider_health,
)
from koda.state.history_store import get_recent_session_transcript
from koda.utils.command_helpers import normalize_provider

_agent_id_label = AGENT_ID or "default"

_RETRYABLE_PATTERNS: dict[str, re.Pattern[str]] = {
    "claude": re.compile(
        r"overloaded|rate.limit|too many requests|connection|timeout|temporarily unavailable|503|529",
        re.IGNORECASE,
    ),
    "codex": re.compile(
        r"overloaded|rate.limit|too many requests|connection|timeout|temporarily unavailable|503|529",
        re.IGNORECASE,
    ),
    "gemini": re.compile(
        r"overloaded|rate.limit|too many requests|connection|timeout|temporarily unavailable|503|529",
        re.IGNORECASE,
    ),
    "ollama": re.compile(
        (
            r"overloaded|rate.limit|too many requests|connection|timeout|temporarily unavailable|503|529|"
            r"connection refused"
        ),
        re.IGNORECASE,
    ),
}


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
) -> list[str]:
    """Return the provider execution order for one task."""
    primary = normalize_provider(primary_provider)
    eligibility_map = get_provider_runtime_eligibility(eligibility)
    ordered: list[str] = []
    for provider in [primary, *PROVIDER_FALLBACK_ORDER]:
        if provider in AVAILABLE_PROVIDERS and provider not in ordered:
            provider_eligibility = eligibility_map.get(provider)
            if provider_eligibility is not None and not bool(provider_eligibility.get("eligible", False)):
                continue
            ordered.append(provider)
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
    if normalized == "ollama":
        return await get_ollama_capabilities(turn_mode)
    if normalized == "gemini":
        return await get_gemini_capabilities(turn_mode)
    if normalized == "codex":
        return await get_codex_capabilities(turn_mode)
    return await get_claude_capabilities(turn_mode)


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
    if normalized == "ollama":
        result = await run_ollama(
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
    elif normalized == "gemini":
        result = await run_gemini(
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
        )
    elif normalized == "codex":
        result = await run_codex(
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
        )
    else:
        result = await run_claude(
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
        )
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

    if normalized == "ollama":
        async for chunk in run_ollama_streaming(
            query=query,
            work_dir=work_dir,
            model=model,
            session_id=provider_session_id,
            max_budget=max_budget,
            process_holder=process_holder,
            system_prompt=system_prompt,
            image_paths=image_paths,
            first_chunk_timeout=first_chunk_timeout if first_chunk_timeout is not None else FIRST_CHUNK_TIMEOUT,
            permission_mode=permission_mode,
            max_turns=max_turns,
            metadata_collector=metadata_collector,
            turn_mode=resolved_turn_mode,
            capabilities=capabilities,
            dry_run=dry_run,
        ):
            yield chunk
        return
    if normalized == "gemini":
        async for chunk in run_gemini_streaming(
            query=query,
            work_dir=work_dir,
            model=model,
            session_id=provider_session_id,
            max_budget=max_budget,
            process_holder=process_holder,
            system_prompt=system_prompt,
            image_paths=image_paths,
            first_chunk_timeout=(
                first_chunk_timeout if first_chunk_timeout is not None else GEMINI_FIRST_CHUNK_TIMEOUT
            ),
            permission_mode=permission_mode,
            max_turns=max_turns,
            metadata_collector=metadata_collector,
            turn_mode=resolved_turn_mode,
            capabilities=capabilities,
            dry_run=dry_run,
            runtime_task_id=runtime_task_id,
        ):
            yield chunk
        return
    if normalized == "codex":
        async for chunk in run_codex_streaming(
            query=query,
            work_dir=work_dir,
            model=model,
            session_id=provider_session_id,
            max_budget=max_budget,
            process_holder=process_holder,
            system_prompt=system_prompt,
            image_paths=image_paths,
            first_chunk_timeout=(first_chunk_timeout if first_chunk_timeout is not None else CODEX_FIRST_CHUNK_TIMEOUT),
            permission_mode=permission_mode,
            max_turns=max_turns,
            metadata_collector=metadata_collector,
            turn_mode=resolved_turn_mode,
            capabilities=capabilities,
            dry_run=dry_run,
            runtime_task_id=runtime_task_id,
        ):
            yield chunk
        return
    async for chunk in run_claude_streaming(
        query=query,
        work_dir=work_dir,
        model=model,
        session_id=provider_session_id,
        max_budget=max_budget,
        process_holder=process_holder,
        system_prompt=system_prompt,
        image_paths=image_paths,
        first_chunk_timeout=first_chunk_timeout if first_chunk_timeout is not None else FIRST_CHUNK_TIMEOUT,
        permission_mode=permission_mode,
        max_turns=max_turns,
        metadata_collector=metadata_collector,
        turn_mode=resolved_turn_mode,
        capabilities=capabilities,
        dry_run=dry_run,
        runtime_task_id=runtime_task_id,
    ):
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
