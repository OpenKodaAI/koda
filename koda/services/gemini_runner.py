"""Gemini CLI runner with provider-aware auth probing and streaming support."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from koda.config import AGENT_ID, GEMINI_FIRST_CHUNK_TIMEOUT, GEMINI_TIMEOUT
from koda.logging_config import get_logger
from koda.services.provider_auth import (
    PROVIDER_API_KEY_ENV_KEYS,
    PROVIDER_AUTH_MODE_ENV_KEYS,
    verify_provider_subscription_login,
)
from koda.services.provider_env import build_llm_subprocess_env
from koda.services.provider_runtime import ProviderCapabilities, TurnMode
from koda.utils.process_control import terminate_process_tree

log = get_logger(__name__)
_agent_id_label = AGENT_ID or "default"

_RETRYABLE_PATTERN = re.compile(
    r"overloaded|rate.limit|too many requests|connection|timeout|temporarily unavailable|503|529",
    re.IGNORECASE,
)
_AUTH_PATTERN = re.compile(
    r"authenticate|authentication|unauthorized|not logged in|login required|invalid api key|api key not configured",
    re.IGNORECASE,
)
_ADAPTER_CONTRACT_PATTERN = re.compile(
    r"unexpected argument|unrecognized option|unknown option|invalid value|usage:",
    re.IGNORECASE,
)
_CAPABILITY_CACHE_TTL_SECONDS = 30.0
_CAPABILITY_CACHE: dict[TurnMode, tuple[float, ProviderCapabilities]] = {}
_CAPABILITY_LOCK = asyncio.Lock()


def _configured_auth_mode() -> str:
    return str(os.environ.get(PROVIDER_AUTH_MODE_ENV_KEYS["gemini"], "subscription_login")).strip().lower()


async def _terminate_process(proc: object) -> None:
    await terminate_process_tree(proc)


def _decode_process_output(raw: object) -> str:
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode(errors="replace").strip()
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _classify_error(message: str) -> tuple[str, bool]:
    if not message:
        return "", False
    if _AUTH_PATTERN.search(message):
        return "provider_auth", False
    if _ADAPTER_CONTRACT_PATTERN.search(message):
        return "adapter_contract", False
    if _RETRYABLE_PATTERN.search(message):
        return "transient", True
    return "provider_runtime", False


def _build_prompt(query: str, system_prompt: str | None) -> str:
    if not system_prompt:
        return query
    return (
        "<system_instructions>\n"
        f"{system_prompt.strip()}\n"
        "</system_instructions>\n\n"
        "<user_request>\n"
        f"{query.strip()}\n"
        "</user_request>"
    )


def _effective_approval_mode(permission_mode: str | None, *, dry_run: bool) -> str:
    if dry_run:
        return "plan"
    normalized = str(permission_mode or "").strip().lower()
    if normalized in {"plan", "read_only"}:
        return "plan"
    if normalized in {"acceptedits", "auto_edit"}:
        return "auto_edit"
    if normalized in {"bypasspermissions", "yolo"}:
        return "yolo"
    return "default"


def _build_cmd(
    *,
    model: str,
    work_dir: str,
    prompt: str,
    permission_mode: str | None,
    dry_run: bool,
    output_format: str,
) -> list[str]:
    from koda.services.provider_auth import resolve_provider_command

    approval_mode = _effective_approval_mode(permission_mode, dry_run=dry_run)
    return [
        *resolve_provider_command("gemini"),
        "--model",
        model,
        "--output-format",
        output_format,
        "--approval-mode",
        approval_mode,
        "--include-directories",
        work_dir,
        "--prompt",
        prompt,
    ]


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_extract_text(item) for item in value)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return str(value["text"])
        parts: list[str] = []
        for key in ("content", "message", "messages", "parts", "delta", "output_text", "response", "value"):
            if key in value:
                parts.append(_extract_text(value[key]))
        return "".join(parts)
    return ""


def _parse_json_payload(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    candidates = [line.strip() for line in stripped.splitlines() if line.strip()]
    for candidate in reversed(candidates):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _result_text(payload: dict[str, Any], fallback: str) -> str:
    text = _extract_text(payload)
    if text.strip():
        return text.strip()
    return fallback.strip() or "Task completed (no text output)."


def _cache_capability(capability: ProviderCapabilities) -> None:
    timestamp = time.monotonic()
    for turn_mode in ("new_turn", "resume_turn"):
        clone = capability.clone()
        clone.turn_mode = turn_mode
        if turn_mode == "resume_turn":
            clone.supports_native_resume = False
            warning = "Gemini CLI does not support native resume; the runtime continues with a stateless turn."
            if warning not in clone.warnings:
                clone.warnings.append(warning)
        _CAPABILITY_CACHE[turn_mode] = (timestamp, clone)


async def _probe_gemini_auth_status() -> ProviderCapabilities:
    env = build_llm_subprocess_env(provider="gemini")
    if _configured_auth_mode() == "api_key":
        if not str(env.get(PROVIDER_API_KEY_ENV_KEYS["gemini"]) or "").strip():
            return ProviderCapabilities(
                provider="gemini",
                turn_mode="new_turn",
                status="unavailable",
                can_execute=False,
                supports_native_resume=False,
                errors=["Gemini API key not configured for Google runtime."],
                checked_via="api_key_env",
            )
        return ProviderCapabilities(
            provider="gemini",
            turn_mode="new_turn",
            status="ready",
            can_execute=True,
            supports_native_resume=False,
            checked_via="api_key_env",
        )

    project_id = str(env.get("GOOGLE_CLOUD_PROJECT") or "").strip()
    result = verify_provider_subscription_login("gemini", project_id=project_id, base_env=env)
    if not result.verified:
        return ProviderCapabilities(
            provider="gemini",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[result.last_error or "Gemini CLI is not authenticated."],
            checked_via=result.checked_via,
        )
    return ProviderCapabilities(
        provider="gemini",
        turn_mode="new_turn",
        status="ready",
        can_execute=True,
        supports_native_resume=False,
        checked_via=result.checked_via,
    )


def clear_gemini_capability_cache() -> None:
    _CAPABILITY_CACHE.clear()


def mark_gemini_auth_failed(error_text: str | None = None) -> None:
    _cache_capability(
        ProviderCapabilities(
            provider="gemini",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[error_text or "Gemini authentication failed."],
            checked_via="runtime",
        )
    )


async def get_gemini_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    cached = _CAPABILITY_CACHE.get(turn_mode)
    now = time.monotonic()
    if cached and now - cached[0] < _CAPABILITY_CACHE_TTL_SECONDS:
        return cached[1].clone()

    async with _CAPABILITY_LOCK:
        cached = _CAPABILITY_CACHE.get(turn_mode)
        now = time.monotonic()
        if cached and now - cached[0] < _CAPABILITY_CACHE_TTL_SECONDS:
            return cached[1].clone()

        capability = await _probe_gemini_auth_status()
        _cache_capability(capability)
        return _CAPABILITY_CACHE[turn_mode][1].clone()


async def run_gemini(
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
    runtime_task_id: int | None = None,
) -> dict[str, Any]:
    del session_id, max_budget, max_turns
    capabilities = capabilities or await get_gemini_capabilities(turn_mode)
    if not capabilities.can_execute:
        return {
            "result": capabilities.errors[0] if capabilities.errors else "Gemini runtime unavailable.",
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
            "result": "Google Gemini CLI currently runs here without image attachment support.",
            "session_id": None,
            "cost_usd": 0.0,
            "usage": {},
            "error": True,
            "_retryable": False,
            "_error_kind": "adapter_contract",
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }

    prompt = _build_prompt(query, system_prompt)
    cmd = _build_cmd(
        model=model,
        work_dir=work_dir,
        prompt=prompt,
        permission_mode=permission_mode,
        dry_run=dry_run,
        output_format="json",
    )
    started_at = time.monotonic()
    runtime_env = build_llm_subprocess_env(provider="gemini")
    if runtime_task_id is not None:
        from koda.services.runtime.kernel_subprocess import create_runtime_kernel_process

        proc: Any = create_runtime_kernel_process(
            task_id=runtime_task_id,
            command=cmd,
            cwd=work_dir,
            env=runtime_env,
        )
        proc.start_with_input(b"")
        await proc.wait_started()
        if process_holder is not None:
            process_holder["proc"] = proc
            event = process_holder.get("event")
            if event is not None:
                event.set()
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=GEMINI_TIMEOUT)
        except TimeoutError:
            await _terminate_process(proc)
            await proc.wait()
            return {
                "result": f"Timeout after {GEMINI_TIMEOUT}s. Gemini did not finish the task in time.",
                "session_id": None,
                "cost_usd": 0.0,
                "usage": {},
                "error": True,
                "_retryable": True,
                "_error_kind": "timeout",
                "_turn_mode": turn_mode,
                "_supports_native_resume": capabilities.supports_native_resume,
            }
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env=runtime_env,
            start_new_session=True,
        )
        if process_holder is not None:
            process_holder["proc"] = proc
            event = process_holder.get("event")
            if event is not None:
                event.set()

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=GEMINI_TIMEOUT)
        except TimeoutError:
            await _terminate_process(proc)
            await proc.wait()
            return {
                "result": f"Timeout after {GEMINI_TIMEOUT}s. Gemini did not finish the task in time.",
                "session_id": None,
                "cost_usd": 0.0,
                "usage": {},
                "error": True,
                "_retryable": True,
                "_error_kind": "timeout",
                "_turn_mode": turn_mode,
                "_supports_native_resume": capabilities.supports_native_resume,
            }

    elapsed = time.monotonic() - started_at
    stdout_text = _decode_process_output(stdout)
    stderr_text = _decode_process_output(stderr)
    payload = _parse_json_payload(stdout_text)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    error_text = stderr_text
    if not error_text and isinstance(payload.get("error"), str):
        error_text = str(payload["error"])
    if proc.returncode not in (0, None) and not error_text:
        error_text = stdout_text or f"Gemini CLI exited with code {proc.returncode}."

    from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

    CLAUDE_EXECUTION.labels(agent_id=_agent_id_label, provider="gemini", model=model, streaming="false").observe(
        elapsed
    )
    DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="gemini_cli").observe(elapsed)

    if error_text:
        error_kind, retryable = _classify_error(error_text)
        if error_kind == "provider_auth":
            mark_gemini_auth_failed(error_text)
        DEPENDENCY_REQUESTS.labels(
            agent_id=_agent_id_label,
            dependency="gemini_cli",
            status="retryable" if retryable else "error",
        ).inc()
        return {
            "result": error_text,
            "session_id": None,
            "cost_usd": 0.0,
            "usage": usage,
            "error": True,
            "_retryable": retryable,
            "_error_kind": error_kind,
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }

    DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="gemini_cli", status="success").inc()
    return {
        "result": _result_text(payload, stdout_text),
        "session_id": None,
        "cost_usd": 0.0,
        "usage": usage,
        "error": False,
        "_turn_mode": turn_mode,
        "_supports_native_resume": capabilities.supports_native_resume,
    }


async def run_gemini_streaming(
    query: str,
    work_dir: str,
    model: str,
    session_id: str | None = None,
    max_budget: float = 0.0,
    process_holder: dict | None = None,
    system_prompt: str | None = None,
    image_paths: list[str] | None = None,
    first_chunk_timeout: float = GEMINI_FIRST_CHUNK_TIMEOUT,
    permission_mode: str | None = None,
    max_turns: int = 25,
    metadata_collector: dict | None = None,
    *,
    turn_mode: TurnMode = "new_turn",
    capabilities: ProviderCapabilities | None = None,
    dry_run: bool = False,
    runtime_task_id: int | None = None,
) -> AsyncIterator[str]:
    del session_id, max_budget, max_turns
    capabilities = capabilities or await get_gemini_capabilities(turn_mode)
    if metadata_collector is not None:
        metadata_collector["turn_mode"] = turn_mode
        metadata_collector["supports_native_resume"] = capabilities.supports_native_resume

    if not capabilities.can_execute:
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = "provider_runtime"
            metadata_collector["retryable"] = False
            metadata_collector["error_message"] = (
                capabilities.errors[0] if capabilities.errors else "Gemini runtime unavailable."
            )
        return
    if image_paths:
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = "adapter_contract"
            metadata_collector["retryable"] = False
            metadata_collector["error_message"] = (
                "Google Gemini CLI currently runs here without image attachment support."
            )
        return

    prompt = _build_prompt(query, system_prompt)
    cmd = _build_cmd(
        model=model,
        work_dir=work_dir,
        prompt=prompt,
        permission_mode=permission_mode,
        dry_run=dry_run,
        output_format="text",
    )
    runtime_env = build_llm_subprocess_env(provider="gemini")
    if runtime_task_id is not None:
        from koda.services.runtime.kernel_subprocess import create_runtime_kernel_process

        proc: Any = create_runtime_kernel_process(
            task_id=runtime_task_id,
            command=cmd,
            cwd=work_dir,
            env=runtime_env,
        )
        proc.start_with_input(b"")
        await proc.wait_started()
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env=runtime_env,
            start_new_session=True,
        )
    if process_holder is not None:
        process_holder["proc"] = proc
        event = process_holder.get("event")
        if event is not None:
            event.set()

    started_at = time.monotonic()
    first_chunk_sent = False
    chunks: list[str] = []
    stderr_text = ""

    async def _read_stderr() -> None:
        nonlocal stderr_text
        if proc.stderr is None:
            return
        stderr_payload = await proc.stderr.read()
        stderr_text = _decode_process_output(stderr_payload)

    stderr_task = asyncio.create_task(_read_stderr())
    try:
        while True:
            if proc.stdout is None:
                break
            try:
                line = await asyncio.wait_for(
                    proc.stdout.readline(),
                    timeout=first_chunk_timeout if not first_chunk_sent else GEMINI_TIMEOUT,
                )
            except TimeoutError:
                await _terminate_process(proc)
                await proc.wait()
                if metadata_collector is not None:
                    metadata_collector["error"] = True
                    metadata_collector["error_kind"] = "timeout"
                    metadata_collector["retryable"] = True
                    metadata_collector["error_message"] = "Gemini streaming response timed out."
                return
            if not line:
                break
            text = _decode_process_output(line)
            if not text:
                continue
            first_chunk_sent = True
            chunks.append(text)
            yield text if text.endswith("\n") else f"{text}\n"
        await proc.wait()
        await stderr_task
    finally:
        if not stderr_task.done():
            stderr_task.cancel()

    elapsed = time.monotonic() - started_at
    from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

    CLAUDE_EXECUTION.labels(agent_id=_agent_id_label, provider="gemini", model=model, streaming="true").observe(elapsed)
    DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="gemini_cli").observe(elapsed)

    if proc.returncode not in (0, None):
        message = stderr_text or "".join(chunks).strip() or f"Gemini CLI exited with code {proc.returncode}."
        error_kind, retryable = _classify_error(message)
        if error_kind == "provider_auth":
            mark_gemini_auth_failed(message)
        DEPENDENCY_REQUESTS.labels(
            agent_id=_agent_id_label,
            dependency="gemini_cli",
            status="retryable" if retryable else "error",
        ).inc()
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = error_kind
            metadata_collector["retryable"] = retryable
            metadata_collector["error_message"] = message
        return

    DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="gemini_cli", status="success").inc()
    if metadata_collector is not None:
        metadata_collector["session_id"] = None
        metadata_collector["usage"] = {}
        metadata_collector["cost_usd"] = 0.0
