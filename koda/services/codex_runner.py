"""Codex CLI runner with compatibility-aware command building and parsing."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import time
from collections.abc import AsyncIterator
from typing import Any, cast

from koda.config import (
    AGENT_ID,
    CODEX_APPROVAL_POLICY,
    CODEX_BIN,
    CODEX_FIRST_CHUNK_TIMEOUT,
    CODEX_SANDBOX,
    CODEX_SKIP_GIT_REPO_CHECK,
    CODEX_TIMEOUT,
    MODEL_PRICING_USD,
)
from koda.logging_config import get_logger
from koda.services.provider_auth import PROVIDER_API_KEY_ENV_KEYS, PROVIDER_AUTH_MODE_ENV_KEYS
from koda.services.provider_env import build_llm_subprocess_env
from koda.services.provider_runtime import ProviderCapabilities, ProviderStatus, TurnMode
from koda.utils.process_control import terminate_process_tree

log = get_logger(__name__)
_agent_id_label = AGENT_ID or "default"

_HELP_TIMEOUT = 3.0
_RETRYABLE_PATTERN = re.compile(
    r"overloaded|rate.limit|too many requests|connection|econnreset|timeout|temporarily unavailable|503|529",
    re.IGNORECASE,
)
_AUTH_PATTERN = re.compile(
    r"failed to authenticate|authentication(?:_error)?|invalid authentication credentials|"
    r"unauthorized|api error:\s*401|not logged in|login required",
    re.IGNORECASE,
)
_ADAPTER_CONTRACT_PATTERN = re.compile(
    (
        r"unexpected argument|unrecognized option|unknown option|invalid value|"
        r"usage:\s+codex\b|for more information, try '--help'"
    ),
    re.IGNORECASE,
)
_RESULT_ERROR_PREFIX_PATTERN = re.compile(
    r"^(failed to |error:|api error:|usage:|\{.*\"type\"\s*:\s*\"error\")",
    re.IGNORECASE | re.DOTALL,
)
_CAPABILITY_CACHE: dict[TurnMode, ProviderCapabilities] = {}
_CAPABILITY_LOCK = asyncio.Lock()
_AUTH_CAPABILITY_CACHE: tuple[float, bool, str] | None = None
_REQUIRED_HELP_TOKENS: dict[TurnMode, tuple[str, ...]] = {
    "new_turn": ("--json", "--model", "--cd", "--sandbox"),
    "resume_turn": ("--json", "--model"),
}
_AUTH_STATUS_TIMEOUT = 3.0
_AUTH_STATUS_TTL_SECONDS = 30.0


def _configured_auth_mode() -> str:
    return str(os.environ.get(PROVIDER_AUTH_MODE_ENV_KEYS["codex"], "subscription_login")).strip().lower()


def _required_help_tokens(turn_mode: TurnMode) -> tuple[str, ...]:
    tokens = list(_REQUIRED_HELP_TOKENS[turn_mode])
    if CODEX_SKIP_GIT_REPO_CHECK:
        tokens.append("--skip-git-repo-check")
    return tuple(tokens)


def _is_retryable_message(message: str) -> bool:
    return bool(_RETRYABLE_PATTERN.search(message))


def _classify_error(message: str) -> tuple[str, bool]:
    if not message:
        return "", False
    if _AUTH_PATTERN.search(message):
        return "provider_auth", False
    if _ADAPTER_CONTRACT_PATTERN.search(message):
        return "adapter_contract", False
    if _is_retryable_message(message):
        return "transient", True
    return "provider_runtime", False


def _decode_process_output(raw: object) -> str:
    """Decode subprocess output defensively for real pipes and AsyncMock tests."""
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode(errors="replace").strip()
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _estimate_cost_from_usage(model: str, usage: dict[str, Any] | None) -> float:
    if not usage:
        return 0.0
    pricing = MODEL_PRICING_USD.get(model) or MODEL_PRICING_USD.get(f"codex:{model}")
    if not isinstance(pricing, dict):
        return 0.0

    input_tokens = int(usage.get("input_tokens") or usage.get("input") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("output") or usage.get("completion_tokens") or 0)
    cached_input_tokens = int(
        usage.get("cached_input_tokens") or usage.get("cached_input") or usage.get("cached_prompt_tokens") or 0
    )

    input_rate = float(pricing.get("input", 0.0))
    output_rate = float(pricing.get("output", 0.0))
    cached_input_rate = float(pricing.get("cached_input", input_rate))
    return (
        (input_tokens / 1_000_000) * input_rate
        + (output_tokens / 1_000_000) * output_rate
        + (cached_input_tokens / 1_000_000) * cached_input_rate
    )


async def _terminate_process(proc: object) -> None:
    """Terminate a subprocess, tolerating AsyncMock-based tests."""
    await terminate_process_tree(proc)


async def _read_help_text(turn_mode: TurnMode) -> tuple[str, str]:
    cmd = [CODEX_BIN, "exec", "--help"] if turn_mode == "new_turn" else [CODEX_BIN, "exec", "resume", "--help"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=build_llm_subprocess_env(provider="codex"),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_HELP_TIMEOUT)
    except TimeoutError:
        await _terminate_process(proc)
        await proc.wait()
        raise
    return stdout.decode(), stderr.decode()


async def _read_login_status() -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        CODEX_BIN,
        "login",
        "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=build_llm_subprocess_env(provider="codex"),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_AUTH_STATUS_TIMEOUT)
    except TimeoutError:
        await _terminate_process(proc)
        await proc.wait()
        raise
    return proc.returncode or 0, stdout.decode(), stderr.decode()


def _build_codex_overrides(system_prompt: str | None) -> list[str]:
    args: list[str] = []
    if system_prompt:
        args.extend(["-c", f"developer_instructions={json.dumps(system_prompt)}"])
    if CODEX_APPROVAL_POLICY:
        args.extend(["-c", f"approval_policy={json.dumps(CODEX_APPROVAL_POLICY)}"])
    return args


def _friendly_auth_message(error_text: str | None = None) -> str:
    detail = (error_text or "").strip()
    if detail:
        detail = detail.splitlines()[0][:240]
        return (
            "Codex authentication failed. Reauthenticate the Codex CLI "
            "(for example with `codex login`) and try again."
            f"\n\nDetails: {detail}"
        )
    return "Codex authentication failed. Reauthenticate the Codex CLI (for example with `codex login`) and try again."


def _classify_embedded_result_error(result_text: str) -> tuple[str, bool] | None:
    stripped = result_text.strip()
    if not stripped:
        return None
    error_kind, retryable = _classify_error(stripped)
    if error_kind == "provider_auth":
        return error_kind, retryable
    if error_kind in {"adapter_contract", "transient"} and _RESULT_ERROR_PREFIX_PATTERN.search(stripped):
        return error_kind, retryable
    return None


def _build_new_turn_cmd(
    model: str,
    work_dir: str,
    system_prompt: str | None,
    image_paths: list[str] | None,
    *,
    sandbox: str | None = None,
) -> list[str]:
    resolved_sandbox = sandbox or CODEX_SANDBOX
    cmd = [
        CODEX_BIN,
        "exec",
        "--json",
        "--cd",
        work_dir,
        "--model",
        model,
        "--sandbox",
        resolved_sandbox,
    ]
    if CODEX_SKIP_GIT_REPO_CHECK:
        cmd.append("--skip-git-repo-check")
    cmd.extend(_build_codex_overrides(system_prompt))
    if image_paths:
        cmd.extend(["--image", *image_paths])
    cmd.append("-")
    return cmd


def _build_resume_turn_cmd(
    model: str,
    session_id: str,
    system_prompt: str | None,
    image_paths: list[str] | None,
) -> list[str]:
    cmd = [CODEX_BIN, "exec", "resume", "--json", "--model", model]
    if CODEX_SKIP_GIT_REPO_CHECK:
        cmd.append("--skip-git-repo-check")
    if CODEX_SANDBOX == "danger-full-access":
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    cmd.extend(_build_codex_overrides(system_prompt))
    if image_paths:
        cmd.extend(["--image", *image_paths])
    cmd.extend([session_id, "-"])
    return cmd


def _build_cmd(
    turn_mode: TurnMode,
    model: str,
    work_dir: str,
    session_id: str | None,
    system_prompt: str | None,
    image_paths: list[str] | None,
    *,
    dry_run: bool = False,
) -> list[str]:
    if turn_mode == "resume_turn":
        if not session_id:
            raise ValueError("resume_turn requires a provider session id")
        if dry_run:
            raise ValueError("codex dry-run requires a fresh new_turn so read-only sandbox can be enforced")
        return _build_resume_turn_cmd(model, session_id, system_prompt, image_paths)
    sandbox = "read-only" if dry_run else CODEX_SANDBOX
    return _build_new_turn_cmd(model, work_dir, system_prompt, image_paths, sandbox=sandbox)


def _capability_from_help(turn_mode: TurnMode, help_text: str) -> ProviderCapabilities:
    missing = [token for token in _required_help_tokens(turn_mode) if token not in help_text]
    if turn_mode == "new_turn":
        if missing:
            return ProviderCapabilities(
                provider="codex",
                turn_mode=turn_mode,
                status="unavailable",
                can_execute=False,
                supports_native_resume=False,
                errors=[f"codex exec is missing required options: {', '.join(missing)}"],
                checked_via="help",
            )
        return ProviderCapabilities(
            provider="codex",
            turn_mode=turn_mode,
            status="ready",
            can_execute=True,
            supports_native_resume=False,
            checked_via="help",
        )

    warnings: list[str] = []
    errors: list[str] = []
    can_execute = True
    supports_native_resume = True
    status: ProviderStatus = "ready"

    if missing:
        can_execute = False
        supports_native_resume = False
        status = "degraded"
        errors.append(f"codex exec resume is missing required options: {', '.join(missing)}")

    if CODEX_SANDBOX != "danger-full-access":
        can_execute = False
        supports_native_resume = False
        status = "degraded"
        warnings.append(
            f"codex resume degraded: sandbox '{CODEX_SANDBOX}' is not supported safely by the resume subcommand"
        )

    if "--dangerously-bypass-approvals-and-sandbox" not in help_text:
        can_execute = False
        supports_native_resume = False
        status = "degraded"
        errors.append("codex exec resume does not expose the danger-full-access execution flag")

    return ProviderCapabilities(
        provider="codex",
        turn_mode=turn_mode,
        status=status,
        can_execute=can_execute,
        supports_native_resume=supports_native_resume,
        warnings=warnings,
        errors=errors,
        checked_via="help",
    )


async def get_codex_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    """Return cached Codex compatibility information for one turn mode."""
    cached = _CAPABILITY_CACHE.get(turn_mode)
    if cached is None:
        async with _CAPABILITY_LOCK:
            cached = _CAPABILITY_CACHE.get(turn_mode)
            if cached is None:
                try:
                    stdout_text, stderr_text = await _read_help_text(turn_mode)
                    help_text = "\n".join(part for part in (stdout_text, stderr_text) if part).strip()
                    capabilities = _capability_from_help(turn_mode, help_text)
                except FileNotFoundError:
                    status: ProviderStatus = "unavailable" if turn_mode == "new_turn" else "degraded"
                    capabilities = ProviderCapabilities(
                        provider="codex",
                        turn_mode=turn_mode,
                        status=status,
                        can_execute=False,
                        supports_native_resume=False,
                        errors=[f"{CODEX_BIN} not found on PATH"],
                        checked_via="help",
                    )
                except TimeoutError:
                    status = "unavailable" if turn_mode == "new_turn" else "degraded"
                    capabilities = ProviderCapabilities(
                        provider="codex",
                        turn_mode=turn_mode,
                        status=status,
                        can_execute=False,
                        supports_native_resume=False,
                        errors=[f"{CODEX_BIN} --help timed out while probing {turn_mode}"],
                        checked_via="help",
                    )
                except Exception as exc:
                    status = "unavailable" if turn_mode == "new_turn" else "degraded"
                    capabilities = ProviderCapabilities(
                        provider="codex",
                        turn_mode=turn_mode,
                        status=status,
                        can_execute=False,
                        supports_native_resume=False,
                        errors=[f"failed to probe codex {turn_mode}: {exc}"],
                        checked_via="help",
                    )

                _CAPABILITY_CACHE[turn_mode] = capabilities
                cached = capabilities

    auth_ok, auth_checked_via, auth_error = await _get_codex_auth_status()
    cached = cached.clone()
    cached.checked_via = f"{cached.checked_via}+{auth_checked_via}"
    if auth_ok:
        return cached

    warnings = list(cached.warnings)
    errors = list(cached.errors)
    errors.append(_friendly_auth_message(auth_error))
    return ProviderCapabilities(
        provider="codex",
        turn_mode=turn_mode,
        status="unavailable",
        can_execute=False,
        supports_native_resume=False,
        warnings=warnings,
        errors=errors,
        checked_via=cached.checked_via,
    )


def clear_codex_capability_cache() -> None:
    """Reset cached Codex capability probes for tests."""
    _CAPABILITY_CACHE.clear()
    global _AUTH_CAPABILITY_CACHE
    _AUTH_CAPABILITY_CACHE = None


async def _get_codex_auth_status() -> tuple[bool, str, str]:
    global _AUTH_CAPABILITY_CACHE
    now = time.monotonic()
    if _AUTH_CAPABILITY_CACHE and now - _AUTH_CAPABILITY_CACHE[0] < _AUTH_STATUS_TTL_SECONDS:
        return _AUTH_CAPABILITY_CACHE[1], "login_status", _AUTH_CAPABILITY_CACHE[2]

    async with _CAPABILITY_LOCK:
        # Double-check after acquiring lock
        now = time.monotonic()
        if _AUTH_CAPABILITY_CACHE and now - _AUTH_CAPABILITY_CACHE[0] < _AUTH_STATUS_TTL_SECONDS:
            return _AUTH_CAPABILITY_CACHE[1], "login_status", _AUTH_CAPABILITY_CACHE[2]

        if _configured_auth_mode() == "api_key":
            env = build_llm_subprocess_env(provider="codex")
            api_key = str(env.get(PROVIDER_API_KEY_ENV_KEYS["codex"]) or "").strip()
            if api_key:
                result = (True, "api_key_env", "")
            else:
                result = (False, "api_key_env", "OpenAI API key not configured for Codex runtime.")
        else:
            try:
                returncode, stdout_text, stderr_text = await _read_login_status()
            except FileNotFoundError:
                result = (False, "login_status", f"{CODEX_BIN} not found on PATH")
            except TimeoutError:
                result = (False, "login_status", f"{CODEX_BIN} login status timed out")
            except Exception as exc:
                result = (False, "login_status", f"failed to probe codex login status: {exc}")
            else:
                message = (stdout_text or stderr_text).strip()
                lower = message.lower()
                if returncode == 0 and "logged in" in lower and "api key" not in lower:
                    result = (True, "login_status", "")
                elif returncode == 0 and "api key" in lower:
                    result = (
                        False,
                        "login_status",
                        "Codex está autenticado via API key, mas o modo ativo exige login do ChatGPT.",
                    )
                else:
                    result = (False, "login_status", message or "Codex CLI is not logged in.")

        _AUTH_CAPABILITY_CACHE = (now, result[0], result[2])
        return result


def mark_codex_auth_failed(error_text: str | None = None) -> None:
    """Mark Codex as temporarily unavailable after a runtime auth failure."""
    global _AUTH_CAPABILITY_CACHE
    _AUTH_CAPABILITY_CACHE = (time.monotonic(), False, error_text or "Codex authentication failed.")


def _collect_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_collect_text(item) for item in value)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return str(value["text"])
        parts: list[str] = []
        for key in ("content", "message", "messages", "parts", "delta", "output_text", "value"):
            if key in value:
                parts.append(_collect_text(value[key]))
        return "".join(parts)
    return ""


def _extract_agent_text(item: dict[str, Any]) -> str:
    for key in ("text", "message", "content", "output_text", "parts"):
        if key in item:
            text = _collect_text(item[key])
            if text:
                return text
    return ""


def _extract_error_message(event: dict[str, Any]) -> str:
    if isinstance(event.get("message"), str):
        return str(event["message"])
    if isinstance(event.get("error"), str):
        return str(event["error"])
    if isinstance(event.get("error"), dict):
        err = event["error"]
        return str(err.get("message") or err.get("error") or err)
    if isinstance(event.get("details"), dict):
        return str(event["details"].get("message") or "")
    return ""


def _parse_usage(event: dict[str, Any]) -> dict[str, Any]:
    usage = event.get("usage")
    return usage if isinstance(usage, dict) else {}


def _compatibility_error(
    capabilities: ProviderCapabilities,
    session_id: str | None,
) -> dict[str, Any]:
    message = capabilities.errors[0] if capabilities.errors else "Codex runtime unavailable for this turn mode."
    if capabilities.warnings:
        message = f"{message}\n" + "\n".join(capabilities.warnings)
    return {
        "result": message,
        "session_id": session_id,
        "cost_usd": 0.0,
        "usage": {},
        "error": True,
        "_retryable": False,
        "_error_kind": "adapter_contract" if capabilities.turn_mode == "resume_turn" else "provider_runtime",
        "_turn_mode": capabilities.turn_mode,
        "_supports_native_resume": capabilities.supports_native_resume,
    }


async def run_codex(
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
    """Run Codex CLI and return a normalized result dict."""
    del max_budget, permission_mode, max_turns
    from koda.services.resilience import check_breaker, codex_cli_breaker, record_failure, record_success

    capabilities = capabilities or await get_codex_capabilities(turn_mode)
    if not capabilities.can_execute:
        return _compatibility_error(capabilities, session_id)

    breaker_err = check_breaker(codex_cli_breaker)
    if breaker_err:
        return {
            "result": breaker_err,
            "session_id": session_id,
            "cost_usd": 0.0,
            "usage": {},
            "error": True,
            "_retryable": False,
            "_error_kind": "provider_runtime",
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }

    try:
        cmd = _build_cmd(
            turn_mode,
            model,
            work_dir,
            session_id,
            system_prompt,
            image_paths,
            dry_run=dry_run,
        )
    except ValueError as exc:
        return {
            "result": str(exc),
            "session_id": session_id,
            "cost_usd": 0.0,
            "usage": {},
            "error": True,
            "_retryable": False,
            "_error_kind": "adapter_contract",
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }
    log.info(
        "codex_cli_start",
        model=model,
        session_id=session_id,
        work_dir=work_dir,
        has_images=bool(image_paths),
        turn_mode=turn_mode,
    )

    started_at = time.monotonic()
    runtime_env = build_llm_subprocess_env(provider="codex")
    if runtime_task_id is not None:
        from koda.services.runtime.kernel_subprocess import create_runtime_kernel_process

        proc: Any = create_runtime_kernel_process(
            task_id=runtime_task_id,
            command=cmd,
            cwd=work_dir,
            env=runtime_env,
        )
        proc.start_with_input(query.encode())
        await proc.wait_started()
        if process_holder is not None:
            process_holder["proc"] = proc
            event = process_holder.get("event")
            if event is not None:
                event.set()
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=CODEX_TIMEOUT)
        except TimeoutError:
            await _terminate_process(proc)
            await proc.wait()
            elapsed = time.monotonic() - started_at
            record_failure(codex_cli_breaker)
            from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

            CLAUDE_EXECUTION.labels(agent_id=_agent_id_label, provider="codex", model=model, streaming="false").observe(
                elapsed
            )
            DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="codex_cli", status="timeout").inc()
            DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="codex_cli").observe(elapsed)
            return {
                "result": f"Timeout after {CODEX_TIMEOUT}s. Codex did not finish the task in time.",
                "session_id": session_id,
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
            stdin=asyncio.subprocess.PIPE,
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
            stdout, stderr = await asyncio.wait_for(proc.communicate(input=query.encode()), timeout=CODEX_TIMEOUT)
        except TimeoutError:
            await _terminate_process(proc)
            await proc.wait()
            elapsed = time.monotonic() - started_at
            record_failure(codex_cli_breaker)
            from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

            CLAUDE_EXECUTION.labels(agent_id=_agent_id_label, provider="codex", model=model, streaming="false").observe(
                elapsed
            )
            DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="codex_cli", status="timeout").inc()
            DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="codex_cli").observe(elapsed)
            return {
                "result": f"Timeout after {CODEX_TIMEOUT}s. Codex did not finish the task in time.",
                "session_id": session_id,
                "cost_usd": 0.0,
                "usage": {},
                "error": True,
                "_retryable": True,
                "_error_kind": "timeout",
                "_turn_mode": turn_mode,
                "_supports_native_resume": capabilities.supports_native_resume,
            }

    elapsed = time.monotonic() - started_at
    stdout_text = stdout.decode().strip()
    stderr_text = stderr.decode().strip()
    lines = [line for line in stdout_text.splitlines() if line.strip()]

    native_items: list[dict[str, Any]] = []
    agent_messages: list[str] = []
    usage: dict[str, Any] = {}
    provider_session_id = session_id
    stop_reason = ""
    error_message = ""

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type")
        if event_type == "thread.started":
            provider_session_id = event.get("thread_id") or provider_session_id
        elif event_type in {"item.completed", "item.updated"}:
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            if event_type == "item.completed":
                native_items.append(item)
            if item.get("type") == "agent_message":
                text = _extract_agent_text(item)
                if text:
                    agent_messages.append(text)
        elif event_type == "turn.completed":
            usage = _parse_usage(event)
            stop_reason = str(event.get("stop_reason") or "completed")
        elif event_type in {"turn.failed", "error"}:
            error_message = _extract_error_message(event) or stderr_text or "Codex failed to execute the task."
            stop_reason = "error"

    if proc.returncode not in (0, None) and not error_message:
        error_message = stderr_text or f"Codex CLI exited with code {proc.returncode}."
        stop_reason = "error"

    cost_usd = _estimate_cost_from_usage(model, usage)

    from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

    CLAUDE_EXECUTION.labels(agent_id=_agent_id_label, provider="codex", model=model, streaming="false").observe(elapsed)
    DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="codex_cli").observe(elapsed)

    result_text = agent_messages[-1] if agent_messages else "Task completed (no text output)."
    embedded_error = _classify_embedded_result_error(result_text)
    if error_message:
        record_failure(codex_cli_breaker)
        error_kind, retryable = _classify_error(error_message)
        if error_kind == "provider_auth":
            mark_codex_auth_failed(error_message)
            error_message = _friendly_auth_message(error_message)
        dep_status = "retryable" if retryable else "error"
        DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="codex_cli", status=dep_status).inc()
        return {
            "result": error_message,
            "session_id": provider_session_id,
            "cost_usd": cost_usd,
            "usage": usage,
            "error": True,
            "_retryable": retryable,
            "_error_kind": error_kind,
            "_stop_reason": stop_reason,
            "_native_items": native_items,
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }

    if embedded_error is not None:
        error_kind, retryable = embedded_error
        if error_kind == "provider_auth":
            mark_codex_auth_failed(result_text)
            result_text = _friendly_auth_message(result_text)
        record_failure(codex_cli_breaker)
        dep_status = "retryable" if retryable else "error"
        DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="codex_cli", status=dep_status).inc()
        return {
            "result": result_text,
            "session_id": provider_session_id,
            "cost_usd": cost_usd,
            "usage": usage,
            "error": True,
            "_retryable": retryable,
            "_error_kind": error_kind,
            "_stop_reason": stop_reason or "error",
            "_native_items": native_items,
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }
    record_success(codex_cli_breaker)
    DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="codex_cli", status="success").inc()
    return {
        "result": result_text,
        "session_id": provider_session_id,
        "cost_usd": cost_usd,
        "usage": usage,
        "error": False,
        "_stop_reason": stop_reason or "completed",
        "_native_items": native_items,
        "_turn_mode": turn_mode,
        "_supports_native_resume": capabilities.supports_native_resume,
    }


async def run_codex_streaming(
    query: str,
    work_dir: str,
    model: str,
    session_id: str | None = None,
    max_budget: float = 0.0,
    process_holder: dict | None = None,
    system_prompt: str | None = None,
    image_paths: list[str] | None = None,
    first_chunk_timeout: float = CODEX_FIRST_CHUNK_TIMEOUT,
    permission_mode: str | None = None,
    max_turns: int = 25,
    metadata_collector: dict | None = None,
    *,
    turn_mode: TurnMode = "new_turn",
    capabilities: ProviderCapabilities | None = None,
    dry_run: bool = False,
    runtime_task_id: int | None = None,
) -> AsyncIterator[str]:
    """Run Codex CLI in JSONL streaming mode."""
    del max_budget, permission_mode, max_turns
    from koda.services.resilience import check_breaker, codex_cli_breaker, record_failure, record_success

    capabilities = capabilities or await get_codex_capabilities(turn_mode)
    if metadata_collector is not None:
        metadata_collector["turn_mode"] = turn_mode
        metadata_collector["supports_native_resume"] = capabilities.supports_native_resume

    if not capabilities.can_execute:
        if metadata_collector is not None:
            compat_error = _compatibility_error(capabilities, session_id)
            metadata_collector["error_message"] = compat_error["result"]
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = compat_error["_error_kind"]
            metadata_collector["retryable"] = False
        return

    breaker_err = check_breaker(codex_cli_breaker)
    if breaker_err:
        if metadata_collector is not None:
            metadata_collector["error_message"] = breaker_err
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = "provider_runtime"
            metadata_collector["retryable"] = False
        return

    try:
        cmd = _build_cmd(
            turn_mode,
            model,
            work_dir,
            session_id,
            system_prompt,
            image_paths,
            dry_run=dry_run,
        )
    except ValueError as exc:
        if metadata_collector is not None:
            metadata_collector["error_message"] = str(exc)
            metadata_collector["error"] = True
            metadata_collector["error_kind"] = "adapter_contract"
            metadata_collector["retryable"] = False
        return
    runtime_env = build_llm_subprocess_env(provider="codex")
    if runtime_task_id is not None:
        from koda.services.runtime.kernel_subprocess import create_runtime_kernel_process

        proc: Any = create_runtime_kernel_process(
            task_id=runtime_task_id,
            command=cmd,
            cwd=work_dir,
            env=runtime_env,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env=runtime_env,
            start_new_session=True,
        )

    if process_holder is not None:
        process_holder["proc"] = proc

    if proc.stdin:
        proc.stdin.write(query.encode())
        await proc.stdin.drain()
        proc.stdin.close()
        await proc.stdin.wait_closed()
    if process_holder is not None:
        event = process_holder.get("event")
        if event is not None:
            event.set()

    yielded_any = False
    received_any_event = False
    started_at = time.monotonic()
    emitted_lengths: dict[str, int] = {}

    try:
        assert proc.stdout is not None
        first_content_deadline = time.monotonic() + first_chunk_timeout
        while True:
            if not yielded_any:
                remaining = first_content_deadline - time.monotonic()
                if remaining <= 0 and not received_any_event:
                    await _terminate_process(proc)
                    await proc.wait()
                    if metadata_collector is not None:
                        metadata_collector["error"] = True
                        metadata_collector["error_message"] = (
                            f"Timeout after {first_chunk_timeout}s waiting for Codex to start streaming."
                        )
                        metadata_collector["error_kind"] = "timeout"
                        metadata_collector["retryable"] = True
                    break
                line_timeout = CODEX_TIMEOUT if received_any_event else max(0.1, min(remaining, CODEX_TIMEOUT))
            else:
                line_timeout = CODEX_TIMEOUT

            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=line_timeout)
            except TimeoutError:
                await _terminate_process(proc)
                await proc.wait()
                if metadata_collector is not None:
                    metadata_collector["error"] = True
                    metadata_collector["error_message"] = f"Timeout after {line_timeout:.1f}s waiting for Codex."
                    metadata_collector["error_kind"] = "timeout"
                    metadata_collector["retryable"] = True
                break

            if not line:
                break

            line_text = line.decode().strip()
            if not line_text:
                continue

            try:
                event = json.loads(line_text)
            except json.JSONDecodeError:
                continue

            received_any_event = True
            event_type = event.get("type")

            if event_type == "thread.started" and metadata_collector is not None:
                metadata_collector["session_id"] = event.get("thread_id") or session_id
                continue

            if event_type in {"item.updated", "item.completed"}:
                item = event.get("item")
                if not isinstance(item, dict):
                    continue
                if metadata_collector is not None and event_type == "item.completed":
                    metadata_collector.setdefault("native_items", []).append(item)
                if item.get("type") == "agent_message":
                    item_id = str(item.get("id") or event.get("item_id") or len(emitted_lengths))
                    text = _extract_agent_text(item)
                    previous = emitted_lengths.get(item_id, 0)
                    if text and len(text) > previous:
                        delta = text[previous:]
                        emitted_lengths[item_id] = len(text)
                        if delta:
                            yielded_any = True
                            yield delta
                continue

            if event_type == "turn.completed":
                usage = _parse_usage(event)
                if metadata_collector is not None:
                    metadata_collector["usage"] = usage
                    metadata_collector["cost_usd"] = _estimate_cost_from_usage(model, usage)
                    metadata_collector["stop_reason"] = str(event.get("stop_reason") or "completed")
                    last_message = ""
                    if metadata_collector.get("native_items"):
                        with contextlib.suppress(Exception):
                            item = cast(dict[str, Any], metadata_collector["native_items"][-1])
                            if item.get("type") == "agent_message":
                                last_message = _extract_agent_text(item)
                    embedded_error = _classify_embedded_result_error(last_message)
                    if embedded_error is not None:
                        error_kind, retryable = embedded_error
                        if error_kind == "provider_auth":
                            mark_codex_auth_failed(last_message)
                            last_message = _friendly_auth_message(last_message)
                        metadata_collector["error"] = True
                        metadata_collector["error_message"] = last_message
                        metadata_collector["error_kind"] = error_kind
                        metadata_collector["retryable"] = retryable
                        metadata_collector["stop_reason"] = "error"
                continue

            if event_type in {"turn.failed", "error"} and metadata_collector is not None:
                error_message = _extract_error_message(event)
                error_kind, retryable = _classify_error(error_message)
                if error_kind == "provider_auth":
                    mark_codex_auth_failed(error_message)
                    error_message = _friendly_auth_message(error_message)
                metadata_collector["error"] = True
                metadata_collector["error_message"] = error_message
                metadata_collector["error_kind"] = error_kind
                metadata_collector["retryable"] = retryable
                metadata_collector["stop_reason"] = "error"
                continue

    finally:
        with contextlib.suppress(Exception):
            await proc.wait()

        elapsed = time.monotonic() - started_at
        from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

        CLAUDE_EXECUTION.labels(agent_id=_agent_id_label, provider="codex", model=model, streaming="true").observe(
            elapsed
        )
        DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="codex_cli").observe(elapsed)
        if yielded_any and proc.returncode in (0, None):
            record_success(codex_cli_breaker)
            DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="codex_cli", status="success").inc()
        else:
            record_failure(codex_cli_breaker)
            status = "error"
            if metadata_collector and metadata_collector.get("retryable"):
                status = "retryable"
            DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="codex_cli", status=status).inc()

        if metadata_collector is not None and proc.stderr:
            with contextlib.suppress(Exception):
                stderr_data = await proc.stderr.read()
                stderr_text = _decode_process_output(stderr_data)
                if stderr_text and not metadata_collector.get("error_message"):
                    error_kind, retryable = _classify_error(stderr_text)
                    if error_kind == "provider_auth":
                        mark_codex_auth_failed(stderr_text)
                        stderr_text = _friendly_auth_message(stderr_text)
                    metadata_collector["error_message"] = stderr_text
                    metadata_collector["error"] = True
                    metadata_collector["error_kind"] = error_kind
                    metadata_collector["retryable"] = retryable
