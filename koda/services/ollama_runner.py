"""Ollama API runner with local/server and cloud API-key auth support."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from koda.config import AGENT_ID, OLLAMA_TIMEOUT
from koda.logging_config import get_logger
from koda.services.provider_auth import (
    PROVIDER_API_KEY_ENV_KEYS,
    PROVIDER_AUTH_MODE_ENV_KEYS,
    PROVIDER_BASE_URL_ENV_KEYS,
    ollama_api_url,
    verify_provider_api_key,
    verify_provider_local_connection,
)
from koda.services.provider_env import build_llm_subprocess_env
from koda.services.provider_runtime import ProviderCapabilities, TurnMode

log = get_logger(__name__)
_agent_id_label = AGENT_ID or "default"

_RETRYABLE_PATTERN = re.compile(
    r"overloaded|rate.limit|too many requests|connection|timeout|temporarily unavailable|503|529|connection refused",
    re.IGNORECASE,
)
_AUTH_PATTERN = re.compile(
    r"authenticate|authentication|unauthorized|invalid api key|forbidden|401|403",
    re.IGNORECASE,
)
_CAPABILITY_CACHE_TTL_SECONDS = 30.0
_CAPABILITY_CACHE: dict[TurnMode, tuple[float, ProviderCapabilities]] = {}
_CAPABILITY_LOCK = asyncio.Lock()


def _configured_auth_mode() -> str:
    return str(os.environ.get(PROVIDER_AUTH_MODE_ENV_KEYS["ollama"], "local")).strip().lower()


def _configured_base_url() -> str:
    return str(os.environ.get(PROVIDER_BASE_URL_ENV_KEYS["ollama"], "http://localhost:11434")).strip()


def _request_headers(env: dict[str, str]) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "User-Agent": "koda/runtime"}
    auth_mode = str(env.get(PROVIDER_AUTH_MODE_ENV_KEYS["ollama"]) or "local").strip().lower()
    if auth_mode == "api_key":
        api_key = str(env.get(PROVIDER_API_KEY_ENV_KEYS["ollama"]) or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _classify_error(message: str) -> tuple[str, bool]:
    if not message:
        return "", False
    if _AUTH_PATTERN.search(message):
        return "provider_auth", False
    if _RETRYABLE_PATTERN.search(message):
        return "transient", True
    return "provider_runtime", False


def _cache_capability(capability: ProviderCapabilities) -> None:
    timestamp = time.monotonic()
    for turn_mode in ("new_turn", "resume_turn"):
        clone = capability.clone()
        clone.turn_mode = turn_mode
        if turn_mode == "resume_turn":
            clone.supports_native_resume = False
            warning = "Ollama does not support native resume; the runtime continues with a stateless turn."
            if warning not in clone.warnings:
                clone.warnings.append(warning)
        _CAPABILITY_CACHE[turn_mode] = (timestamp, clone)


async def _probe_ollama_auth_status() -> ProviderCapabilities:
    env = build_llm_subprocess_env(provider="ollama")
    auth_mode = _configured_auth_mode()
    base_url = _configured_base_url()
    if auth_mode == "api_key":
        api_key = str(env.get(PROVIDER_API_KEY_ENV_KEYS["ollama"]) or "").strip()
        if not api_key:
            return ProviderCapabilities(
                provider="ollama",
                turn_mode="new_turn",
                status="unavailable",
                can_execute=False,
                supports_native_resume=False,
                errors=["Ollama API key not configured for cloud runtime."],
                checked_via="api_key_env",
            )
        result = verify_provider_api_key("ollama", api_key, base_url=base_url)
        if not result.verified:
            return ProviderCapabilities(
                provider="ollama",
                turn_mode="new_turn",
                status="unavailable",
                can_execute=False,
                supports_native_resume=False,
                errors=[result.last_error or "Ollama cloud connection unavailable."],
                checked_via=result.checked_via,
            )
        return ProviderCapabilities(
            provider="ollama",
            turn_mode="new_turn",
            status="ready",
            can_execute=True,
            supports_native_resume=False,
            checked_via=result.checked_via,
        )

    result = verify_provider_local_connection("ollama", base_url=base_url)
    if not result.verified:
        return ProviderCapabilities(
            provider="ollama",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[result.last_error or "Ollama local server unavailable."],
            checked_via=result.checked_via,
        )
    return ProviderCapabilities(
        provider="ollama",
        turn_mode="new_turn",
        status="ready",
        can_execute=True,
        supports_native_resume=False,
        checked_via=result.checked_via,
    )


def clear_ollama_capability_cache() -> None:
    _CAPABILITY_CACHE.clear()


async def get_ollama_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    cached = _CAPABILITY_CACHE.get(turn_mode)
    now = time.monotonic()
    if cached and now - cached[0] < _CAPABILITY_CACHE_TTL_SECONDS:
        return cached[1].clone()

    async with _CAPABILITY_LOCK:
        cached = _CAPABILITY_CACHE.get(turn_mode)
        now = time.monotonic()
        if cached and now - cached[0] < _CAPABILITY_CACHE_TTL_SECONDS:
            return cached[1].clone()

        capability = await _probe_ollama_auth_status()
        _cache_capability(capability)
        return _CAPABILITY_CACHE[turn_mode][1].clone()


def _build_messages(query: str, system_prompt: str | None) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if system_prompt and system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.append({"role": "user", "content": query.strip()})
    return messages


def _perform_chat_request(
    *,
    model: str,
    query: str,
    system_prompt: str | None,
) -> tuple[dict[str, Any], str]:
    env = build_llm_subprocess_env(provider="ollama")
    auth_mode = str(env.get(PROVIDER_AUTH_MODE_ENV_KEYS["ollama"]) or "local").strip().lower()
    base_url = str(env.get(PROVIDER_BASE_URL_ENV_KEYS["ollama"]) or _configured_base_url()).strip()
    payload = {
        "model": model,
        "messages": _build_messages(query, system_prompt),
        "stream": False,
    }
    request = urllib_request.Request(
        ollama_api_url(base_url, "chat", auth_mode=auth_mode),
        data=json.dumps(payload).encode("utf-8"),
        headers=_request_headers(env),
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
        body = response.read().decode("utf-8")
    return json.loads(body or "{}"), auth_mode


def _usage_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    prompt_eval_count = payload.get("prompt_eval_count")
    eval_count = payload.get("eval_count")
    if isinstance(prompt_eval_count, int):
        usage["input_tokens"] = prompt_eval_count
    if isinstance(eval_count, int):
        usage["output_tokens"] = eval_count
    if isinstance(payload.get("total_duration"), int):
        usage["total_duration_ns"] = int(payload["total_duration"])
    return usage


def _result_text(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    if isinstance(payload.get("response"), str) and str(payload["response"]).strip():
        return str(payload["response"]).strip()
    return "Task completed (no text output)."


async def run_ollama(
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
    *,
    turn_mode: TurnMode = "new_turn",
    capabilities: ProviderCapabilities | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    del work_dir, session_id, max_budget, process_holder, permission_mode, max_turns, dry_run
    capabilities = capabilities or await get_ollama_capabilities(turn_mode)
    if not capabilities.can_execute:
        return {
            "result": capabilities.errors[0] if capabilities.errors else "Ollama runtime unavailable.",
            "session_id": None,
            "cost_usd": 0.0,
            "usage": {},
            "error": True,
            "_retryable": False,
            "_error_kind": "provider_runtime",
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }
    if image_paths:
        return {
            "result": "Ollama runtime currently runs here without image attachment support.",
            "session_id": None,
            "cost_usd": 0.0,
            "usage": {},
            "error": True,
            "_retryable": False,
            "_error_kind": "adapter_contract",
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }

    started_at = time.monotonic()
    try:
        payload, _auth_mode = await asyncio.to_thread(
            _perform_chat_request,
            model=model,
            query=query,
            system_prompt=system_prompt,
        )
    except urllib_error.HTTPError as exc:
        message = exc.read().decode("utf-8", "replace").strip() or str(exc)
        error_kind, retryable = _classify_error(message)
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
    except Exception as exc:
        message = str(exc)
        error_kind, retryable = _classify_error(message)
        return {
            "result": message,
            "session_id": None,
            "cost_usd": 0.0,
            "usage": {},
            "error": True,
            "_retryable": retryable,
            "_error_kind": error_kind or "provider_runtime",
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }

    elapsed = time.monotonic() - started_at
    from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

    CLAUDE_EXECUTION.labels(agent_id=_agent_id_label, provider="ollama", model=model, streaming="false").observe(
        elapsed
    )
    DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="ollama_api").observe(elapsed)
    DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="ollama_api", status="success").inc()
    return {
        "result": _result_text(payload),
        "session_id": None,
        "cost_usd": 0.0,
        "usage": _usage_from_payload(payload),
        "error": False,
        "_turn_mode": turn_mode,
        "_supports_native_resume": capabilities.supports_native_resume,
    }


async def run_ollama_streaming(
    query: str,
    work_dir: str,
    model: str,
    session_id: str | None = None,
    max_budget: float = 0.0,
    process_holder: dict | None = None,
    system_prompt: str | None = None,
    image_paths: list[str] | None = None,
    first_chunk_timeout: float = OLLAMA_TIMEOUT,
    permission_mode: str | None = None,
    max_turns: int = 25,
    metadata_collector: dict | None = None,
    *,
    turn_mode: TurnMode = "new_turn",
    capabilities: ProviderCapabilities | None = None,
    dry_run: bool = False,
) -> AsyncIterator[str]:
    del first_chunk_timeout
    capabilities = capabilities or await get_ollama_capabilities(turn_mode)
    if metadata_collector is not None:
        metadata_collector["turn_mode"] = turn_mode
        metadata_collector["supports_native_resume"] = capabilities.supports_native_resume

    result = await run_ollama(
        query=query,
        work_dir=work_dir,
        model=model,
        session_id=session_id,
        max_budget=max_budget,
        process_holder=process_holder,
        system_prompt=system_prompt,
        image_paths=image_paths,
        permission_mode=permission_mode,
        max_turns=max_turns,
        turn_mode=turn_mode,
        capabilities=capabilities,
        dry_run=dry_run,
    )
    if result.get("error"):
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = result.get("_error_kind", "provider_runtime")
            metadata_collector["retryable"] = bool(result.get("_retryable"))
            metadata_collector["error_message"] = str(result.get("result") or "Ollama runtime unavailable.")
        return

    if metadata_collector is not None:
        metadata_collector["session_id"] = None
        metadata_collector["usage"] = result.get("usage") or {}
        metadata_collector["cost_usd"] = 0.0

    text = str(result.get("result") or "").strip()
    if text:
        yield text if text.endswith("\n") else f"{text}\n"
