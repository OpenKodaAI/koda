"""Shared OpenAI-compatible HTTP LLM runner.

Plug-in surface for HTTP-only LLM providers (Perplexity, Mistral, Qwen, Kimi,
Groq, DeepSeek, xAI). Each provider supplies a :class:`ProviderHttpProfile`
declaring its base URL, endpoints and quirks; this module owns the actual
request/response handling, SSE streaming, error classification, capability
probing and cost estimation.

Native OpenAI tool-calling is intentionally *not* used. Koda parses
``<agent_cmd>`` XML from assistant text via ``tool_dispatcher.parse_agent_commands``;
sending a ``tools`` field would compete with that protocol and cause the
model to emit native ``tool_calls`` that cannot be parsed.
"""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

import aiohttp

from koda.config import AGENT_ID, MODEL_PRICING_USD
from koda.logging_config import get_logger
from koda.services.http_client import _check_url_safety
from koda.services.provider_auth import (
    PROVIDER_API_KEY_ENV_KEYS,
    PROVIDER_BASE_URL_ENV_KEYS,
)
from koda.services.provider_env import build_llm_subprocess_env
from koda.services.provider_http_profile import ProviderHttpProfile
from koda.services.provider_runtime import ProviderCapabilities, TurnMode

log = get_logger(__name__)
_agent_id_label = AGENT_ID or "default"

_CAPABILITY_CACHE_TTL_SECONDS = {
    "models_endpoint": 30.0,
    "health_only": 300.0,
    "static": 0.0,
}
_CAPABILITY_CACHE: dict[tuple[str, TurnMode], tuple[float, ProviderCapabilities]] = {}
_CAPABILITY_LOCK = asyncio.Lock()

_SSE_DONE = "[DONE]"
_DEFAULT_MAX_OUTPUT_TOKENS = 4096


def clear_openai_compatible_capability_cache() -> None:
    """Test hook — flushes the cross-provider capability cache."""
    _CAPABILITY_CACHE.clear()


# Capability probing


async def get_openai_compatible_capabilities(profile: ProviderHttpProfile, turn_mode: TurnMode) -> ProviderCapabilities:
    cache_key = (profile.provider_id, turn_mode)
    ttl = _CAPABILITY_CACHE_TTL_SECONDS.get(profile.capability_probe, 0.0)
    cached = _CAPABILITY_CACHE.get(cache_key)
    now = time.monotonic()
    if ttl > 0 and cached and now - cached[0] < ttl:
        return cached[1].clone()

    async with _CAPABILITY_LOCK:
        cached = _CAPABILITY_CACHE.get(cache_key)
        now = time.monotonic()
        if ttl > 0 and cached and now - cached[0] < ttl:
            return cached[1].clone()

        capability = await _probe_capabilities(profile, turn_mode)
        for tm in ("new_turn", "resume_turn"):
            clone = capability.clone()
            clone.turn_mode = tm
            if tm == "resume_turn":
                clone.supports_native_resume = False
                warning = (
                    f"{profile.provider_id} runs HTTP-stateless; the runtime continues "
                    "with a fresh turn after replaying transcript context."
                )
                if warning not in clone.warnings:
                    clone.warnings.append(warning)
            _CAPABILITY_CACHE[(profile.provider_id, tm)] = (now, clone)
        return _CAPABILITY_CACHE[cache_key][1].clone()


async def _probe_capabilities(profile: ProviderHttpProfile, turn_mode: TurnMode) -> ProviderCapabilities:
    api_key, env = _resolve_credentials(profile)
    if not api_key and profile.auth_mode == "api_key":
        return ProviderCapabilities(
            provider=profile.provider_id,
            turn_mode=turn_mode,
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[f"{profile.provider_id} API key not configured."],
            checked_via="api_key_env",
        )

    if profile.capability_probe == "static":
        return ProviderCapabilities(
            provider=profile.provider_id,
            turn_mode=turn_mode,
            status="ready",
            can_execute=True,
            supports_native_resume=False,
            checked_via="static",
        )

    base_url = _resolve_base_url(profile, env)
    safe_base = _check_url_safety(
        base_url, allow_private=profile.allow_private_base_url or _looks_like_override(profile, env)
    )
    if safe_base is not None:
        return ProviderCapabilities(
            provider=profile.provider_id,
            turn_mode=turn_mode,
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[f"{profile.provider_id} base URL blocked: {safe_base}"],
            checked_via="ssrf_check",
        )

    probe_url = profile.models_url() if profile.capability_probe == "models_endpoint" else profile.health_url()
    assert probe_url is not None  # static handled above

    timeout = aiohttp.ClientTimeout(total=10)
    headers = profile.headers(api_key)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(probe_url, headers=headers) as resp,
        ):
            status = resp.status
            body = (await resp.text(encoding="utf-8", errors="replace"))[:512]
    except (TimeoutError, aiohttp.ClientError) as exc:
        return ProviderCapabilities(
            provider=profile.provider_id,
            turn_mode=turn_mode,
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[f"{profile.provider_id} probe failed: {exc}"],
            checked_via=profile.capability_probe,
        )

    if status in (401, 403):
        return ProviderCapabilities(
            provider=profile.provider_id,
            turn_mode=turn_mode,
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[f"{profile.provider_id} authentication failed (HTTP {status})."],
            checked_via=profile.capability_probe,
        )
    if status >= 500:
        return ProviderCapabilities(
            provider=profile.provider_id,
            turn_mode=turn_mode,
            status="degraded",
            can_execute=True,
            supports_native_resume=False,
            warnings=[f"{profile.provider_id} probe returned HTTP {status}; runtime may be flaky."],
            checked_via=profile.capability_probe,
        )
    if status >= 400 and profile.capability_probe == "health_only":
        return ProviderCapabilities(
            provider=profile.provider_id,
            turn_mode=turn_mode,
            status="ready",
            can_execute=True,
            supports_native_resume=False,
            warnings=[f"{profile.provider_id} health probe HTTP {status}; assuming runtime is reachable."],
            checked_via=profile.capability_probe,
        )
    if status >= 400:
        snippet = body.replace("\n", " ").strip()[:160]
        return ProviderCapabilities(
            provider=profile.provider_id,
            turn_mode=turn_mode,
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[f"{profile.provider_id} probe HTTP {status}: {snippet}"],
            checked_via=profile.capability_probe,
        )

    return ProviderCapabilities(
        provider=profile.provider_id,
        turn_mode=turn_mode,
        status="ready",
        can_execute=True,
        supports_native_resume=False,
        checked_via=profile.capability_probe,
    )


# Public runner entrypoints


async def run_openai_compatible(
    *,
    profile: ProviderHttpProfile,
    query: str,
    work_dir: str,
    model: str,
    session_id: str | None = None,
    max_budget: float = 0.0,
    process_holder: dict | None = None,
    system_prompt: str | None = None,
    image_paths: list[str] | None = None,
    permission_mode: str | None = None,
    max_turns: int = 25,
    turn_mode: TurnMode = "new_turn",
    capabilities: ProviderCapabilities | None = None,
    dry_run: bool = False,
    runtime_task_id: int | None = None,
    effort: str | int | None = None,
) -> dict[str, Any]:
    """Single-turn chat completion against an OpenAI-compatible endpoint."""
    del work_dir, session_id, permission_mode, max_turns, runtime_task_id
    capabilities = capabilities or await get_openai_compatible_capabilities(profile, turn_mode)
    if not capabilities.can_execute:
        return _error_result(
            profile,
            turn_mode,
            capabilities,
            message=capabilities.errors[0] if capabilities.errors else f"{profile.provider_id} unavailable.",
            error_kind="provider_runtime",
            retryable=False,
        )

    if dry_run:
        return _ok_result(profile, turn_mode, capabilities, text="(dry-run)", usage={}, cost=0.0)

    api_key, env = _resolve_credentials(profile)
    if not api_key and profile.auth_mode == "api_key":
        return _error_result(
            profile,
            turn_mode,
            capabilities,
            message=f"{profile.provider_id} API key not configured.",
            error_kind="provider_auth",
            retryable=False,
        )

    base_url = _resolve_base_url(profile, env)
    safe_error = _check_url_safety(
        base_url, allow_private=profile.allow_private_base_url or _looks_like_override(profile, env)
    )
    if safe_error is not None:
        return _error_result(
            profile,
            turn_mode,
            capabilities,
            message=f"{profile.provider_id} base URL blocked: {safe_error}",
            error_kind="provider_runtime",
            retryable=False,
        )

    payload = _build_chat_payload(
        profile=profile,
        model=model,
        query=query,
        system_prompt=system_prompt,
        image_paths=image_paths,
        max_budget=max_budget,
        stream=False,
        effort=effort,
    )

    started_at = time.monotonic()
    timeout = aiohttp.ClientTimeout(total=profile.request_timeout_seconds)
    chat_url = _join_with_base(base_url, profile.chat_path)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            request_task: asyncio.Task[aiohttp.ClientResponse] = asyncio.create_task(
                session.post(chat_url, headers=profile.headers(api_key), json=payload)
            )
            if process_holder is not None:
                process_holder["task"] = request_task
            try:
                resp = await request_task
            finally:
                if process_holder is not None:
                    process_holder.pop("task", None)
            async with resp:
                status = resp.status
                body_text = await resp.text(encoding="utf-8", errors="replace")
    except asyncio.CancelledError:
        return _error_result(
            profile,
            turn_mode,
            capabilities,
            message=f"{profile.provider_id} request cancelled.",
            error_kind="provider_runtime",
            retryable=False,
        )
    except TimeoutError:
        return _error_result(
            profile,
            turn_mode,
            capabilities,
            message=f"{profile.provider_id} request timed out after {profile.request_timeout_seconds}s.",
            error_kind="transient",
            retryable=True,
        )
    except aiohttp.ClientError as exc:
        return _error_result(
            profile,
            turn_mode,
            capabilities,
            message=f"{profile.provider_id} HTTP error: {exc}",
            error_kind="transient",
            retryable=True,
        )

    if status >= 400:
        kind, retryable = _classify_http_error(status, body_text)
        snippet = _short_error_snippet(body_text)
        return _error_result(
            profile,
            turn_mode,
            capabilities,
            message=f"{profile.provider_id} HTTP {status}: {snippet}",
            error_kind=kind,
            retryable=retryable,
        )

    try:
        data = json.loads(body_text or "{}")
    except json.JSONDecodeError:
        return _error_result(
            profile,
            turn_mode,
            capabilities,
            message=f"{profile.provider_id} returned non-JSON body.",
            error_kind="provider_runtime",
            retryable=False,
        )

    text = _extract_message_text(data)
    citations = _extract_citations(profile, data)
    if citations:
        text = _append_citations_footer(text, citations)
    usage = _normalize_usage(data.get("usage") or {})
    cost = _estimate_cost(model, usage)

    elapsed = time.monotonic() - started_at
    _record_metrics(profile.provider_id, model, elapsed, streaming=False, success=True)

    result = _ok_result(profile, turn_mode, capabilities, text=text, usage=usage, cost=cost)
    if citations:
        metadata = result.setdefault("metadata", {})
        metadata["citations"] = citations
    return result


async def run_openai_compatible_streaming(
    *,
    profile: ProviderHttpProfile,
    query: str,
    work_dir: str,
    model: str,
    session_id: str | None = None,
    max_budget: float = 0.0,
    process_holder: dict | None = None,
    system_prompt: str | None = None,
    image_paths: list[str] | None = None,
    first_chunk_timeout: float | None = None,
    permission_mode: str | None = None,
    max_turns: int = 25,
    metadata_collector: dict | None = None,
    turn_mode: TurnMode = "new_turn",
    capabilities: ProviderCapabilities | None = None,
    dry_run: bool = False,
    runtime_task_id: int | None = None,
    effort: str | int | None = None,
) -> AsyncIterator[str]:
    """Stream one chat completion via SSE, yielding text deltas."""
    del work_dir, session_id, permission_mode, max_turns, runtime_task_id
    capabilities = capabilities or await get_openai_compatible_capabilities(profile, turn_mode)
    if metadata_collector is not None:
        metadata_collector["provider"] = profile.provider_id
        metadata_collector["turn_mode"] = turn_mode
        metadata_collector["supports_native_resume"] = capabilities.supports_native_resume
        if capabilities.warnings:
            warnings = [*metadata_collector.get("warnings", []), *capabilities.warnings]
            metadata_collector["warnings"] = list(dict.fromkeys(warnings))

    if not capabilities.can_execute:
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = "provider_runtime"
            metadata_collector["retryable"] = False
            metadata_collector["error_message"] = (
                capabilities.errors[0] if capabilities.errors else f"{profile.provider_id} unavailable."
            )
        return

    if dry_run:
        if metadata_collector is not None:
            metadata_collector["session_id"] = None
            metadata_collector["usage"] = {}
            metadata_collector["cost_usd"] = 0.0
        yield "(dry-run)\n"
        return

    api_key, env = _resolve_credentials(profile)
    if not api_key and profile.auth_mode == "api_key":
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = "provider_auth"
            metadata_collector["retryable"] = False
            metadata_collector["error_message"] = f"{profile.provider_id} API key not configured."
        return

    base_url = _resolve_base_url(profile, env)
    safe_error = _check_url_safety(
        base_url, allow_private=profile.allow_private_base_url or _looks_like_override(profile, env)
    )
    if safe_error is not None:
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = "provider_runtime"
            metadata_collector["retryable"] = False
            metadata_collector["error_message"] = f"{profile.provider_id} base URL blocked: {safe_error}"
        return

    payload = _build_chat_payload(
        profile=profile,
        model=model,
        query=query,
        system_prompt=system_prompt,
        image_paths=image_paths,
        max_budget=max_budget,
        stream=True,
        effort=effort,
    )

    chat_url = _join_with_base(base_url, profile.chat_path)
    request_timeout = aiohttp.ClientTimeout(
        total=None,
        sock_connect=30,
        sock_read=profile.request_timeout_seconds,
    )
    first_chunk_deadline = first_chunk_timeout or profile.first_chunk_timeout_seconds
    started_at = time.monotonic()
    received_first_chunk = False
    text_buffer: list[str] = []
    citations_collected: list[str] = []
    final_usage: dict[str, Any] = {}

    try:
        async with (
            aiohttp.ClientSession(timeout=request_timeout) as session,
            session.post(chat_url, headers=profile.headers(api_key), json=payload) as resp,
        ):
            if process_holder is not None:
                process_holder["task"] = asyncio.current_task()
            if resp.status >= 400:
                body_text = await resp.text(encoding="utf-8", errors="replace")
                kind, retryable = _classify_http_error(resp.status, body_text)
                if metadata_collector is not None:
                    metadata_collector["error"] = True
                    metadata_collector["error_kind"] = kind
                    metadata_collector["retryable"] = retryable
                    metadata_collector["error_message"] = (
                        f"{profile.provider_id} HTTP {resp.status}: {_short_error_snippet(body_text)}"
                    )
                return

            deadline = time.monotonic() + first_chunk_deadline
            async for raw_line in resp.content:
                if not raw_line:
                    continue
                if not received_first_chunk and time.monotonic() > deadline:
                    if metadata_collector is not None:
                        metadata_collector["error"] = True
                        metadata_collector["error_kind"] = "transient"
                        metadata_collector["retryable"] = True
                        metadata_collector["error_message"] = (
                            f"{profile.provider_id} first-chunk timeout ({first_chunk_deadline}s)."
                        )
                    return

                line = raw_line.decode("utf-8", "replace").rstrip("\r\n")
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data_text = line[5:].lstrip()
                if data_text == _SSE_DONE:
                    break
                try:
                    chunk = json.loads(data_text)
                except json.JSONDecodeError:
                    continue

                delta_text = _extract_delta_text(chunk)
                if delta_text:
                    if not received_first_chunk:
                        received_first_chunk = True
                    text_buffer.append(delta_text)
                    yield delta_text

                chunk_citations = _extract_citations(profile, chunk)
                for citation in chunk_citations:
                    if citation not in citations_collected:
                        citations_collected.append(citation)

                chunk_usage = chunk.get("usage")
                if isinstance(chunk_usage, dict):
                    final_usage = chunk_usage
    except TimeoutError:
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = "transient"
            metadata_collector["retryable"] = True
            metadata_collector["error_message"] = f"{profile.provider_id} stream timed out."
        return
    except aiohttp.ClientError as exc:
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = "transient"
            metadata_collector["retryable"] = True
            metadata_collector["error_message"] = f"{profile.provider_id} stream error: {exc}"
        return
    finally:
        if process_holder is not None:
            process_holder.pop("task", None)

    if citations_collected:
        footer = _build_citations_footer(citations_collected)
        text_buffer.append(footer)
        yield footer

    elapsed = time.monotonic() - started_at

    # Empty-stream guard: server returned 200 but produced zero tokens. This
    # happens with malformed SSE bodies (no ``data:`` lines), early EOF on
    # chunked-encoded responses, or when llama-server crashes mid-request
    # without flushing. The runner used to silently report success with empty
    # output, which let the caller treat the response as a valid empty turn.
    # Flag it as ``transient`` (retryable) since it's almost always a server
    # state problem rather than a contract violation.
    if not received_first_chunk:
        _record_metrics(profile.provider_id, model, elapsed, streaming=True, success=False)
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = "transient"
            metadata_collector["retryable"] = True
            metadata_collector["error_message"] = (
                f"{profile.provider_id} stream produced no tokens (empty body or early EOF)."
            )
        return

    _record_metrics(profile.provider_id, model, elapsed, streaming=True, success=True)

    if metadata_collector is not None:
        usage = _normalize_usage(final_usage)
        metadata_collector["session_id"] = None
        metadata_collector["usage"] = usage
        metadata_collector["cost_usd"] = _estimate_cost(model, usage)
        if citations_collected:
            metadata_collector.setdefault("metadata", {})["citations"] = citations_collected


# Helpers


def _resolve_credentials(profile: ProviderHttpProfile) -> tuple[str, dict[str, str]]:
    env = build_llm_subprocess_env(provider=profile.provider_id)
    key_env = PROVIDER_API_KEY_ENV_KEYS.get(cast(Any, profile.provider_id))
    api_key = ""
    if key_env:
        api_key = str(env.get(key_env) or os.environ.get(key_env) or "").strip()
    return api_key, env


def _resolve_base_url(profile: ProviderHttpProfile, env: dict[str, str]) -> str:
    base_url_env = PROVIDER_BASE_URL_ENV_KEYS.get(cast(Any, profile.provider_id))
    if base_url_env:
        override = str(env.get(base_url_env) or os.environ.get(base_url_env) or "").strip()
        if override:
            return override
    return profile.base_url


def _looks_like_override(profile: ProviderHttpProfile, env: dict[str, str]) -> bool:
    base_url_env = PROVIDER_BASE_URL_ENV_KEYS.get(cast(Any, profile.provider_id))
    if not base_url_env:
        return False
    override = str(env.get(base_url_env) or os.environ.get(base_url_env) or "").strip()
    return bool(override) and override != profile.base_url


def _join_with_base(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def _build_chat_payload(
    *,
    profile: ProviderHttpProfile,
    model: str,
    query: str,
    system_prompt: str | None,
    image_paths: list[str] | None,
    max_budget: float,
    stream: bool,
    effort: str | int | None = None,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    if system_prompt and system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})

    user_content = _build_user_content(profile, model, query, image_paths)
    messages.append({"role": "user", "content": user_content})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "max_tokens": _DEFAULT_MAX_OUTPUT_TOKENS,
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}
    for key, value in profile.extra_payload:
        payload[key] = value
    if effort is not None:
        from koda.provider_models import get_model_effort_capability

        cap = get_model_effort_capability(profile.provider_id, model)
        if cap is not None:
            if cap["kind"] == "enum" and isinstance(effort, str) and effort in cap["values"]:
                if profile.provider_id == "xai":
                    payload["reasoning"] = {"effort": effort}
                else:
                    payload["reasoning_effort"] = effort
                if profile.provider_id == "deepseek":
                    payload["thinking"] = {"type": "enabled"}
            elif cap["kind"] == "tokens":
                try:
                    budget = int(effort)
                except (TypeError, ValueError):
                    budget = None
                if budget is not None and cap["min"] <= budget <= cap["max"]:
                    payload["thinking"] = {"type": "enabled", "budget_tokens": budget}
    del max_budget  # cost is enforced via budget service, not at the request layer
    return payload


def _build_user_content(
    profile: ProviderHttpProfile,
    model: str,
    query: str,
    image_paths: list[str] | None,
) -> Any:
    if not image_paths or model not in profile.vision_models:
        return query.strip()

    blocks: list[dict[str, Any]] = [{"type": "text", "text": query.strip()}]
    for path in image_paths:
        try:
            data_uri = _load_image_data_uri(path)
        except OSError as exc:
            log.warning("openai_compatible_image_skip", path=path, error=str(exc))
            continue
        blocks.append({"type": "image_url", "image_url": {"url": data_uri}})
    return blocks


def _load_image_data_uri(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_message_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [str(item.get("text", "")) for item in content if isinstance(item, dict) and item.get("type") == "text"]
        return "\n".join(part for part in parts if part).strip()
    return ""


def _extract_delta_text(chunk: dict[str, Any]) -> str:
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    delta = first.get("delta")
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text", "")) for item in content if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""


def _extract_citations(profile: ProviderHttpProfile, payload: dict[str, Any]) -> list[str]:
    if profile.citations_extractor is not None:
        try:
            return list(profile.citations_extractor(payload))
        except Exception:
            return []

    citations: list[str] = []
    raw_top = payload.get("citations")
    if isinstance(raw_top, list):
        for entry in raw_top:
            text = _stringify_citation(entry)
            if text:
                citations.append(text)

    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            for source in (choice.get("message") or {}, choice.get("delta") or {}):
                if not isinstance(source, dict):
                    continue
                raw = source.get("citations")
                if isinstance(raw, list):
                    for entry in raw:
                        text = _stringify_citation(entry)
                        if text and text not in citations:
                            citations.append(text)
    return citations


def _stringify_citation(entry: Any) -> str:
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict):
        url = entry.get("url") or entry.get("source") or ""
        title = entry.get("title") or entry.get("name") or ""
        url_text = str(url).strip()
        title_text = str(title).strip()
        if url_text and title_text:
            return f"{title_text} — {url_text}"
        return url_text or title_text
    return ""


def _build_citations_footer(citations: list[str]) -> str:
    if not citations:
        return ""
    lines = ["", "", "---", "Fontes:"]
    for index, citation in enumerate(citations, 1):
        lines.append(f"[{index}] {citation}")
    return "\n".join(lines) + "\n"


def _append_citations_footer(text: str, citations: list[str]) -> str:
    footer = _build_citations_footer(citations)
    if not footer:
        return text
    return f"{text}{footer}" if text.endswith("\n") else f"{text}\n{footer}"


def _normalize_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {}
    out: dict[str, Any] = {}
    prompt = usage.get("prompt_tokens") or usage.get("input_tokens")
    completion = usage.get("completion_tokens") or usage.get("output_tokens")
    cached = (
        (
            usage.get("prompt_tokens_details", {}).get("cached_tokens")
            if isinstance(usage.get("prompt_tokens_details"), dict)
            else None
        )
        or usage.get("cached_tokens")
        or usage.get("cached_input_tokens")
    )
    if isinstance(prompt, int):
        out["input_tokens"] = prompt
    if isinstance(completion, int):
        out["output_tokens"] = completion
    if isinstance(cached, int):
        out["cached_input_tokens"] = cached
    total = usage.get("total_tokens")
    if isinstance(total, int):
        out["total_tokens"] = total
    return out


def _estimate_cost(model: str, usage: dict[str, Any]) -> float:
    if not usage:
        return 0.0
    pricing = MODEL_PRICING_USD.get(model) if isinstance(MODEL_PRICING_USD, dict) else None
    if not isinstance(pricing, dict):
        try:
            from koda.provider_models import _GENERAL_MODEL_METADATA  # noqa: PLC0415
        except Exception:
            return 0.0
        candidate = None
        for (_, model_id), meta in _GENERAL_MODEL_METADATA.items():
            if model_id == model:
                candidate = meta
                break
        if not candidate:
            return 0.0
        pricing = {
            "input": float(candidate.get("input_cost_per_1m", 0.0)),
            "output": float(candidate.get("output_cost_per_1m", 0.0)),
            "cached_input": float(candidate.get("cached_input_cost_per_1m", candidate.get("input_cost_per_1m", 0.0))),
        }

    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cached_input_tokens = int(usage.get("cached_input_tokens") or 0)
    if cached_input_tokens > input_tokens:
        cached_input_tokens = input_tokens
    fresh_input = max(input_tokens - cached_input_tokens, 0)

    input_rate = float(pricing.get("input", 0.0))
    output_rate = float(pricing.get("output", 0.0))
    cached_rate = float(pricing.get("cached_input", input_rate))
    return (
        (fresh_input / 1_000_000) * input_rate
        + (cached_input_tokens / 1_000_000) * cached_rate
        + (output_tokens / 1_000_000) * output_rate
    )


def _classify_http_error(status: int, body: str) -> tuple[str, bool]:
    if status in (401, 403):
        return "provider_auth", False
    if status == 429:
        return "transient", True
    if 500 <= status < 600:
        return "transient", True
    if status == 400 and "model" in body.lower():
        return "adapter_contract", False
    return "provider_runtime", False


def _short_error_snippet(body: str) -> str:
    text = body.strip().replace("\n", " ")
    return (text[:200] + "…") if len(text) > 200 else text


def _ok_result(
    profile: ProviderHttpProfile,
    turn_mode: TurnMode,
    capabilities: ProviderCapabilities,
    *,
    text: str,
    usage: dict[str, Any],
    cost: float,
) -> dict[str, Any]:
    return {
        "result": text or "Task completed (no text output).",
        "session_id": None,
        "cost_usd": float(cost),
        "usage": usage,
        "error": False,
        "_turn_mode": turn_mode,
        "_supports_native_resume": capabilities.supports_native_resume,
    }


def _error_result(
    profile: ProviderHttpProfile,
    turn_mode: TurnMode,
    capabilities: ProviderCapabilities,
    *,
    message: str,
    error_kind: str,
    retryable: bool,
) -> dict[str, Any]:
    return {
        "result": message,
        "session_id": None,
        "cost_usd": 0.0,
        "usage": {},
        "error": True,
        "_retryable": retryable,
        "_error_kind": error_kind,
        "_turn_mode": turn_mode,
        "_supports_native_resume": capabilities.supports_native_resume,
    }


def _record_metrics(provider_id: str, model: str, elapsed: float, *, streaming: bool, success: bool) -> None:
    try:
        from koda.services.metrics import (  # noqa: PLC0415
            CLAUDE_EXECUTION,
            DEPENDENCY_LATENCY,
            DEPENDENCY_REQUESTS,
        )
    except Exception:
        return
    streaming_label = "true" if streaming else "false"
    status_label = "success" if success else "error"
    try:
        CLAUDE_EXECUTION.labels(
            agent_id=_agent_id_label, provider=provider_id, model=model, streaming=streaming_label
        ).observe(elapsed)
        DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency=f"{provider_id}_api").observe(elapsed)
        DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency=f"{provider_id}_api", status=status_label).inc()
    except Exception:
        pass


# Profile registry for cloud OpenAI-compatible providers.
#
# Each builder reads its env-var override (and timeout config) on first lookup
# rather than at import time. Adding a new OpenAI-compatible provider means
# adding one builder + one registry entry — no new module file required.


def _build_deepseek_profile() -> ProviderHttpProfile:
    from koda.config import DEEPSEEK_FIRST_CHUNK_TIMEOUT, DEEPSEEK_TIMEOUT

    return ProviderHttpProfile(
        provider_id="deepseek",
        base_url=os.environ.get("DEEPSEEK_API_BASE_URL") or "https://api.deepseek.com",
        chat_path="/v1/chat/completions",
        models_path="/v1/models",
        first_chunk_timeout_seconds=float(DEEPSEEK_FIRST_CHUNK_TIMEOUT),
        request_timeout_seconds=float(DEEPSEEK_TIMEOUT),
    )


def _build_groq_profile() -> ProviderHttpProfile:
    from koda.config import GROQ_FIRST_CHUNK_TIMEOUT, GROQ_TIMEOUT

    return ProviderHttpProfile(
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


def _build_kimi_profile() -> ProviderHttpProfile:
    from koda.config import KIMI_FIRST_CHUNK_TIMEOUT, KIMI_TIMEOUT

    return ProviderHttpProfile(
        provider_id="kimi",
        base_url=os.environ.get("KIMI_API_BASE_URL") or "https://api.moonshot.ai",
        chat_path="/v1/chat/completions",
        models_path="/v1/models",
        first_chunk_timeout_seconds=float(KIMI_FIRST_CHUNK_TIMEOUT),
        request_timeout_seconds=float(KIMI_TIMEOUT),
        # Kimi K2 family is natively multimodal; the kimi-vision-* and
        # moonshot-v1-vision-* SKUs are kept for operators pinned to those
        # snapshots.
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


def _build_mistral_profile() -> ProviderHttpProfile:
    from koda.config import MISTRAL_FIRST_CHUNK_TIMEOUT, MISTRAL_TIMEOUT

    return ProviderHttpProfile(
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


def _build_perplexity_profile() -> ProviderHttpProfile:
    from koda.config import PERPLEXITY_FIRST_CHUNK_TIMEOUT, PERPLEXITY_TIMEOUT

    return ProviderHttpProfile(
        provider_id="perplexity",
        base_url=os.environ.get("PERPLEXITY_API_BASE_URL") or "https://api.perplexity.ai",
        chat_path="/chat/completions",
        models_path=None,
        capability_probe="health_only",
        health_path="/",
        first_chunk_timeout_seconds=float(PERPLEXITY_FIRST_CHUNK_TIMEOUT),
        request_timeout_seconds=float(PERPLEXITY_TIMEOUT),
    )


def _build_qwen_profile() -> ProviderHttpProfile:
    from koda.config import QWEN_FIRST_CHUNK_TIMEOUT, QWEN_TIMEOUT

    return ProviderHttpProfile(
        provider_id="qwen",
        base_url=os.environ.get("QWEN_API_BASE_URL") or "https://dashscope-intl.aliyuncs.com",
        chat_path="/compatible-mode/v1/chat/completions",
        models_path="/compatible-mode/v1/models",
        first_chunk_timeout_seconds=float(QWEN_FIRST_CHUNK_TIMEOUT),
        request_timeout_seconds=float(QWEN_TIMEOUT),
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


def _build_xai_profile() -> ProviderHttpProfile:
    from koda.config import XAI_FIRST_CHUNK_TIMEOUT, XAI_TIMEOUT

    return ProviderHttpProfile(
        provider_id="xai",
        base_url=os.environ.get("XAI_API_BASE_URL") or "https://api.x.ai",
        chat_path="/v1/chat/completions",
        models_path="/v1/models",
        first_chunk_timeout_seconds=float(XAI_FIRST_CHUNK_TIMEOUT),
        request_timeout_seconds=float(XAI_TIMEOUT),
        # Grok 4.x is multimodal end-to-end; older `*-vision` SKUs stay
        # listed for operators still pinned to legacy snapshots.
        vision_models=frozenset(
            {
                "grok-4.3",
                "grok-4.20-multi-agent",
                "grok-4.1-fast",
                "grok-4-fast",
                "grok-4-0709",
                "grok-4-vision-0709",
                "grok-2-vision-1212",
                "grok-vision-beta",
            }
        ),
    )


_PROFILE_BUILDERS: dict[str, Callable[[], ProviderHttpProfile]] = {
    "deepseek": _build_deepseek_profile,
    "groq": _build_groq_profile,
    "kimi": _build_kimi_profile,
    "mistral": _build_mistral_profile,
    "perplexity": _build_perplexity_profile,
    "qwen": _build_qwen_profile,
    "xai": _build_xai_profile,
}

OPENAI_COMPATIBLE_PROVIDERS: frozenset[str] = frozenset(_PROFILE_BUILDERS)
"""Provider IDs handled by the cloud OpenAI-compatible registry."""

_PROFILE_CACHE: dict[str, ProviderHttpProfile] = {}


def get_provider_profile(provider_id: str) -> ProviderHttpProfile:
    """Return the cached :class:`ProviderHttpProfile` for an OpenAI-compatible provider."""
    cached = _PROFILE_CACHE.get(provider_id)
    if cached is not None:
        return cached
    builder = _PROFILE_BUILDERS.get(provider_id)
    if builder is None:
        raise KeyError(f"No OpenAI-compatible profile registered for provider {provider_id!r}")
    profile = builder()
    _PROFILE_CACHE[provider_id] = profile
    return profile


def reset_provider_profile_cache() -> None:
    """Test hook — drop cached profiles so env-var overrides can be re-read."""
    _PROFILE_CACHE.clear()


async def get_capabilities_for_provider(provider_id: str, turn_mode: TurnMode) -> ProviderCapabilities:
    """Probe runtime capabilities for a registered OpenAI-compatible provider."""
    return await get_openai_compatible_capabilities(get_provider_profile(provider_id), turn_mode)


async def run_for_provider(provider_id: str, **kwargs: Any) -> dict[str, Any]:
    """Run one non-streaming turn against a registered OpenAI-compatible provider."""
    return await run_openai_compatible(profile=get_provider_profile(provider_id), **kwargs)


async def run_streaming_for_provider(provider_id: str, **kwargs: Any) -> AsyncIterator[str]:
    """Run a streaming turn against a registered OpenAI-compatible provider."""
    async for chunk in run_openai_compatible_streaming(profile=get_provider_profile(provider_id), **kwargs):
        yield chunk
