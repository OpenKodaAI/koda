"""Claude CLI runner with retry logic and streaming support.

Uses tenacity for exponential backoff on transient errors.
"""

import asyncio
import contextlib
import json
import os
import re
import time
from collections.abc import AsyncIterator
from typing import Any, cast

from tenacity import RetryCallState, retry, retry_if_result, stop_after_attempt, wait_exponential

from koda.config import AGENT_ID, CLAUDE_TIMEOUT, FIRST_CHUNK_TIMEOUT, IMAGE_TEMP_DIR, MAX_BUDGET_USD
from koda.logging_config import get_logger
from koda.services.provider_auth import PROVIDER_API_KEY_ENV_KEYS, PROVIDER_AUTH_MODE_ENV_KEYS
from koda.services.provider_env import build_llm_subprocess_env
from koda.services.provider_runtime import ProviderCapabilities, TurnMode
from koda.utils.process_control import terminate_process_tree

log = get_logger(__name__)
_agent_id_label = AGENT_ID or "default"

_RETRYABLE_PATTERN = re.compile(r"overloaded|rate.limit|connection|ECONNRESET", re.IGNORECASE)
_AUTH_PATTERN = re.compile(
    r"failed to authenticate|authentication(?:_error)?|invalid authentication credentials|"
    r"unauthorized|api error:\s*401|not logged in|login required",
    re.IGNORECASE,
)
_ADAPTER_CONTRACT_PATTERN = re.compile(
    r"unexpected argument|unrecognized option|unknown option|invalid value|usage:",
    re.IGNORECASE,
)
_INVALID_SESSION_PATTERN = re.compile(
    r"no conversation found with session id|conversation not found|invalid session id|invalid conversation",
    re.IGNORECASE,
)
_RESULT_ERROR_PREFIX_PATTERN = re.compile(
    r"^(failed to |error:|api error:|usage:|\{.*\"type\"\s*:\s*\"error\")",
    re.IGNORECASE | re.DOTALL,
)
_AUTH_PROBE_TIMEOUT = 3.0
_CAPABILITY_CACHE_TTL_SECONDS = 30.0
_CAPABILITY_CACHE: dict[TurnMode, tuple[float, ProviderCapabilities]] = {}
_CAPABILITY_LOCK = asyncio.Lock()


def _is_retryable(result: dict) -> bool:
    """Check if a result indicates a retryable error."""
    return bool(result.get("_retryable"))


def _return_last_result(retry_state: RetryCallState) -> dict | None:
    """Return the last provider result instead of raising RetryError."""
    if retry_state.outcome is None:
        return None
    return cast("dict", retry_state.outcome.result())


async def _terminate_process(proc: object) -> None:
    """Terminate a subprocess, tolerating AsyncMock-based tests."""
    await terminate_process_tree(proc)


def _decode_process_output(raw: object) -> str:
    """Decode subprocess output defensively for real pipes and AsyncMock tests."""
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode(errors="replace").strip()
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _classify_error(stderr_text: str) -> tuple[str, bool]:
    if not stderr_text:
        return "", False
    if _AUTH_PATTERN.search(stderr_text):
        return "provider_auth", False
    if _INVALID_SESSION_PATTERN.search(stderr_text):
        return "invalid_session", False
    if _ADAPTER_CONTRACT_PATTERN.search(stderr_text):
        return "adapter_contract", False
    if _RETRYABLE_PATTERN.search(stderr_text):
        return "transient", True
    return "provider_runtime", False


def _effective_permission_mode(permission_mode: str | None, *, dry_run: bool) -> str | None:
    """Return the Claude permission mode, forcing dry-run into plan mode."""
    if dry_run:
        return "plan"
    return permission_mode


def _friendly_auth_message(error_text: str | None = None) -> str:
    detail = (error_text or "").strip()
    if detail:
        detail = detail.splitlines()[0][:240]
        return (
            "Claude authentication failed. Reauthenticate the Claude CLI "
            "(for example with `claude auth login`) and try again."
            f"\n\nDetails: {detail}"
        )
    return (
        "Claude authentication failed. Reauthenticate the Claude CLI "
        "(for example with `claude auth login`) and try again."
    )


def _configured_auth_mode() -> str:
    return str(os.environ.get(PROVIDER_AUTH_MODE_ENV_KEYS["claude"], "subscription_login")).strip().lower()


def _classify_embedded_result_error(result_text: str) -> tuple[str, bool] | None:
    stripped = result_text.strip()
    if not stripped:
        return None
    error_kind, retryable = _classify_error(stripped)
    if error_kind == "provider_auth":
        return error_kind, retryable
    if error_kind == "invalid_session":
        return error_kind, retryable
    if error_kind in {"adapter_contract", "transient"} and _RESULT_ERROR_PREFIX_PATTERN.search(stripped):
        return error_kind, retryable
    return None


def _cache_claude_capability(capabilities: ProviderCapabilities) -> None:
    timestamp = time.monotonic()
    for turn_mode in ("new_turn", "resume_turn"):
        cloned = capabilities.clone()
        cloned.turn_mode = turn_mode
        _CAPABILITY_CACHE[turn_mode] = (timestamp, cloned)


async def _probe_claude_auth_status() -> ProviderCapabilities:
    env = build_llm_subprocess_env(provider="claude")
    if _configured_auth_mode() == "api_key":
        if not str(env.get(PROVIDER_API_KEY_ENV_KEYS["claude"]) or "").strip():
            return ProviderCapabilities(
                provider="claude",
                turn_mode="new_turn",
                status="unavailable",
                can_execute=False,
                supports_native_resume=False,
                errors=["Anthropic API key not configured for Claude runtime."],
                checked_via="api_key_env",
            )
        return ProviderCapabilities(
            provider="claude",
            turn_mode="new_turn",
            status="ready",
            can_execute=True,
            supports_native_resume=True,
            checked_via="api_key_env",
        )
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "auth",
            "status",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_AUTH_PROBE_TIMEOUT)
    except FileNotFoundError:
        return ProviderCapabilities(
            provider="claude",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=["claude not found on PATH"],
            checked_via="auth_status",
        )
    except TimeoutError:
        return ProviderCapabilities(
            provider="claude",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=["claude auth status timed out"],
            checked_via="auth_status",
        )
    except Exception as exc:
        return ProviderCapabilities(
            provider="claude",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[f"failed to probe claude auth status: {exc}"],
            checked_via="auth_status",
        )

    stdout_text = stdout.decode().strip()
    stderr_text = stderr.decode().strip()
    if proc.returncode not in (0, None):
        return ProviderCapabilities(
            provider="claude",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[_friendly_auth_message(stderr_text or stdout_text or "claude auth status failed")],
            checked_via="auth_status",
        )

    try:
        payload = json.loads(stdout_text or "{}")
    except json.JSONDecodeError:
        return ProviderCapabilities(
            provider="claude",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=["claude auth status returned invalid JSON"],
            checked_via="auth_status",
        )

    if not isinstance(payload, dict) or not payload.get("loggedIn"):
        return ProviderCapabilities(
            provider="claude",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[_friendly_auth_message("Claude CLI is not logged in.")],
            checked_via="auth_status",
        )

    return ProviderCapabilities(
        provider="claude",
        turn_mode="new_turn",
        status="ready",
        can_execute=True,
        supports_native_resume=True,
        checked_via="auth_status",
    )


def mark_claude_auth_failed(error_text: str | None = None) -> None:
    """Mark Claude as temporarily unavailable after a runtime auth failure."""
    _cache_claude_capability(
        ProviderCapabilities(
            provider="claude",
            turn_mode="new_turn",
            status="unavailable",
            can_execute=False,
            supports_native_resume=False,
            errors=[_friendly_auth_message(error_text)],
            checked_via="runtime",
        )
    )


def clear_claude_capability_cache() -> None:
    """Reset cached Claude capability probes for tests."""
    _CAPABILITY_CACHE.clear()


async def get_claude_capabilities(turn_mode: TurnMode) -> ProviderCapabilities:
    """Return Claude execution readiness, including login state."""
    cached = _CAPABILITY_CACHE.get(turn_mode)
    now = time.monotonic()
    if cached and now - cached[0] < _CAPABILITY_CACHE_TTL_SECONDS:
        return cached[1].clone()

    async with _CAPABILITY_LOCK:
        cached = _CAPABILITY_CACHE.get(turn_mode)
        now = time.monotonic()
        if cached and now - cached[0] < _CAPABILITY_CACHE_TTL_SECONDS:
            return cached[1].clone()

        capability = await _probe_claude_auth_status()
        _cache_claude_capability(capability)
        return _CAPABILITY_CACHE[turn_mode][1].clone()


@retry(
    retry=retry_if_result(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry_error_callback=_return_last_result,
)
async def run_claude(
    query: str,
    work_dir: str,
    model: str,
    session_id: str | None = None,
    max_budget: float = MAX_BUDGET_USD,
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
) -> dict:
    """Run claude CLI and return parsed result.

    Returns dict with keys: result, session_id, cost_usd, error
    """
    capabilities = capabilities or await get_claude_capabilities(turn_mode)
    if not capabilities.can_execute:
        return {
            "result": capabilities.errors[0] if capabilities.errors else "Claude runtime unavailable.",
            "session_id": session_id,
            "cost_usd": 0.0,
            "error": True,
            "_retryable": False,
            "_error_kind": "provider_runtime",
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }

    cmd = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--max-turns",
        str(max_turns),
    ]

    effective_permission_mode = _effective_permission_mode(permission_mode, dry_run=dry_run)
    if effective_permission_mode:
        cmd.extend(["--permission-mode", effective_permission_mode])

    if max_budget > 0:
        cmd.extend(["--max-budget-usd", str(max_budget)])

    if session_id:
        cmd.extend(["--resume", session_id])

    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    if image_paths:
        cmd.extend(["--add-dir", str(IMAGE_TEMP_DIR)])

    from koda.services.resilience import check_breaker, claude_cli_breaker, record_failure, record_success

    breaker_err = check_breaker(claude_cli_breaker)
    if breaker_err:
        return {
            "result": breaker_err,
            "session_id": session_id,
            "cost_usd": 0.0,
            "error": True,
            "_retryable": False,
            "_error_kind": "provider_runtime",
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }

    log.info(
        "claude_cli_start",
        model=model,
        session_id=session_id,
        work_dir=work_dir,
        has_images=bool(image_paths),
    )

    _cli_start = time.monotonic()

    runtime_env = build_llm_subprocess_env(provider="claude")
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
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=CLAUDE_TIMEOUT)
        except TimeoutError:
            await _terminate_process(proc)
            await proc.wait()
            _elapsed = time.monotonic() - _cli_start
            log.warning("claude_cli_timeout", timeout=CLAUDE_TIMEOUT)
            record_failure(claude_cli_breaker)
            from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

            CLAUDE_EXECUTION.labels(
                agent_id=_agent_id_label, provider="claude", model=model, streaming="false"
            ).observe(_elapsed)
            DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="claude_cli", status="timeout").inc()
            DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="claude_cli").observe(_elapsed)
            return {
                "result": f"Timeout after {CLAUDE_TIMEOUT}s. The query was too complex or Claude got stuck.",
                "session_id": session_id,
                "cost_usd": 0.0,
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
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=query.encode()),
                timeout=CLAUDE_TIMEOUT,
            )
        except TimeoutError:
            await _terminate_process(proc)
            await proc.wait()
            _elapsed = time.monotonic() - _cli_start
            log.warning("claude_cli_timeout", timeout=CLAUDE_TIMEOUT)
            record_failure(claude_cli_breaker)
            from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

            CLAUDE_EXECUTION.labels(
                agent_id=_agent_id_label, provider="claude", model=model, streaming="false"
            ).observe(_elapsed)
            DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="claude_cli", status="timeout").inc()
            DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="claude_cli").observe(_elapsed)
            return {
                "result": f"Timeout after {CLAUDE_TIMEOUT}s. The query was too complex or Claude got stuck.",
                "session_id": session_id,
                "cost_usd": 0.0,
                "error": True,
                "_retryable": True,
                "_error_kind": "timeout",
                "_turn_mode": turn_mode,
                "_supports_native_resume": capabilities.supports_native_resume,
            }

    _elapsed = time.monotonic() - _cli_start
    stdout_text = stdout.decode().strip()
    stderr_text = stderr.decode().strip()

    if proc.returncode != 0 and not stdout_text:
        from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

        CLAUDE_EXECUTION.labels(agent_id=_agent_id_label, provider="claude", model=model, streaming="false").observe(
            _elapsed
        )
        DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="claude_cli").observe(_elapsed)
        record_failure(claude_cli_breaker)
        error_kind, retryable = _classify_error(stderr_text)
        if error_kind == "provider_auth":
            mark_claude_auth_failed(stderr_text)
        if retryable:
            log.info("claude_cli_retryable_error", stderr=stderr_text[:200])
            DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="claude_cli", status="retryable").inc()
            return {
                "result": f"Claude CLI error (exit {proc.returncode}):\n{stderr_text or 'Unknown error'}",
                "session_id": session_id,
                "cost_usd": 0.0,
                "error": True,
                "_retryable": True,
                "_error_kind": error_kind,
                "_turn_mode": turn_mode,
                "_supports_native_resume": capabilities.supports_native_resume,
            }
        log.error("claude_cli_error", returncode=proc.returncode, stderr=stderr_text[:500])
        DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="claude_cli", status="error").inc()
        return {
            "result": f"Claude CLI error (exit {proc.returncode}):\n{stderr_text or 'Unknown error'}",
            "session_id": session_id,
            "cost_usd": 0.0,
            "error": True,
            "_retryable": False,
            "_error_kind": error_kind or "provider_runtime",
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }

    # Parse JSON output
    try:
        data = json.loads(stdout_text)
    except json.JSONDecodeError:
        lines = stdout_text.strip().split("\n")
        for line in reversed(lines):
            try:
                data = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        else:
            return {
                "result": stdout_text or stderr_text or "No output from Claude.",
                "session_id": session_id,
                "cost_usd": 0.0,
                "error": False,
            }

    result_text = data.get("result") or data.get("response") or ""
    # Never return raw JSON stdout as user-visible result
    if not result_text:
        result_text = "Task completed (no text output)."
    new_session_id = data.get("session_id", session_id)
    cost = data.get("total_cost_usd", data.get("cost_usd", 0.0))
    stop_reason = data.get("stop_reason", "")

    # Extract tool_use blocks from all JSON lines in stdout (for artifact sending)
    tool_uses: list[dict] = []
    for raw_line in stdout_text.strip().split("\n"):
        try:
            line_data = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            continue
        if line_data.get("type") == "assistant":
            for block in line_data.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_uses.append(block)

    from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

    CLAUDE_EXECUTION.labels(agent_id=_agent_id_label, provider="claude", model=model, streaming="false").observe(
        _elapsed
    )
    DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="claude_cli").observe(_elapsed)

    embedded_error = _classify_embedded_result_error(result_text)
    if embedded_error is not None:
        error_kind, retryable = embedded_error
        if error_kind == "provider_auth":
            mark_claude_auth_failed(result_text)
            result_text = _friendly_auth_message(result_text)
        record_failure(claude_cli_breaker)
        dep_status = "retryable" if retryable else "error"
        DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="claude_cli", status=dep_status).inc()
        return {
            "result": result_text,
            "session_id": data.get("session_id", session_id),
            "cost_usd": float(data.get("total_cost_usd", data.get("cost_usd", 0.0)) or 0.0),
            "error": True,
            "_retryable": retryable,
            "_error_kind": error_kind,
            "_stop_reason": data.get("stop_reason", "error") or "error",
            "_turn_mode": turn_mode,
            "_supports_native_resume": capabilities.supports_native_resume,
        }

    log.info("claude_cli_complete", cost_usd=float(cost) if cost else 0.0, session_id=new_session_id)
    record_success(claude_cli_breaker)
    DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="claude_cli", status="success").inc()
    return {
        "result": result_text,
        "session_id": new_session_id,
        "cost_usd": float(cost) if cost else 0.0,
        "error": False,
        "_stop_reason": stop_reason,
        "_tool_uses": tool_uses,
        "_turn_mode": turn_mode,
        "_supports_native_resume": capabilities.supports_native_resume,
    }


def _build_cmd(
    model: str,
    max_budget: float,
    session_id: str | None,
    system_prompt: str | None,
    image_paths: list[str] | None,
    permission_mode: str | None = None,
    max_turns: int = 25,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Build the Claude CLI command list."""
    cmd = [
        "claude",
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--model",
        model,
        "--max-turns",
        str(max_turns),
    ]

    effective_permission_mode = _effective_permission_mode(permission_mode, dry_run=dry_run)
    if effective_permission_mode:
        cmd.extend(["--permission-mode", effective_permission_mode])

    if max_budget > 0:
        cmd.extend(["--max-budget-usd", str(max_budget)])

    if session_id:
        cmd.extend(["--resume", session_id])

    if system_prompt:
        cmd.extend(["--append-system-prompt", system_prompt])

    if image_paths:
        cmd.extend(["--add-dir", str(IMAGE_TEMP_DIR)])

    return cmd


async def run_claude_streaming(
    query: str,
    work_dir: str,
    model: str,
    session_id: str | None = None,
    max_budget: float = MAX_BUDGET_USD,
    process_holder: dict | None = None,
    system_prompt: str | None = None,
    image_paths: list[str] | None = None,
    first_chunk_timeout: float = FIRST_CHUNK_TIMEOUT,
    permission_mode: str | None = None,
    max_turns: int = 25,
    metadata_collector: dict | None = None,
    *,
    turn_mode: TurnMode = "new_turn",
    capabilities: ProviderCapabilities | None = None,
    dry_run: bool = False,
    runtime_task_id: int | None = None,
) -> AsyncIterator[str]:
    """Run claude CLI in streaming mode, yielding text chunks as they arrive.

    Reads stdout line-by-line and yields text content from stream-json output.
    If metadata_collector is provided, it will be populated with:
      - tool_uses: list of tool_use blocks from assistant events
      - session_id: from the result event
      - cost_usd: from the result event
      - stop_reason: from the result event (e.g. "max_turns", "end_turn")
    """
    capabilities = capabilities or await get_claude_capabilities(turn_mode)
    if metadata_collector is not None:
        metadata_collector["turn_mode"] = turn_mode
        metadata_collector["supports_native_resume"] = capabilities.supports_native_resume
    if not capabilities.can_execute:
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_message"] = (
                capabilities.errors[0] if capabilities.errors else "Claude runtime unavailable."
            )
            metadata_collector["error_kind"] = "provider_runtime"
            metadata_collector["retryable"] = False
        return

    cmd = _build_cmd(
        model,
        max_budget,
        session_id,
        system_prompt,
        image_paths,
        permission_mode=permission_mode,
        max_turns=max_turns,
        dry_run=dry_run,
    )

    from koda.services.resilience import check_breaker, claude_cli_breaker, record_failure, record_success

    breaker_err = check_breaker(claude_cli_breaker)
    if breaker_err:
        if metadata_collector is not None:
            metadata_collector["error"] = True
            metadata_collector["error_message"] = breaker_err
            metadata_collector["error_kind"] = "provider_runtime"
            metadata_collector["retryable"] = False
        return

    log.info(
        "claude_cli_streaming_start",
        model=model,
        session_id=session_id,
        work_dir=work_dir,
    )

    _stream_start = time.monotonic()

    runtime_env = build_llm_subprocess_env(provider="claude")
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

    # Increase the stdout stream buffer limit to handle large JSON lines
    # (e.g., Write tool_use blocks with large file contents can exceed 64KB default)
    if proc.stdout and hasattr(proc.stdout, "_limit"):
        proc.stdout._limit = 10 * 1024 * 1024  # 10 MB

    # Write query to stdin and close
    if proc.stdin:
        proc.stdin.write(query.encode())
        await proc.stdin.drain()
        proc.stdin.close()
        await proc.stdin.wait_closed()
    if process_holder is not None:
        event = process_holder.get("event")
        if event is not None:
            event.set()

    # Read stdout line by line
    yielded_any = False
    received_any_event = False
    try:

        async def _read_lines() -> AsyncIterator[str]:
            nonlocal yielded_any, received_any_event
            first_content_deadline = time.monotonic() + first_chunk_timeout
            assert proc.stdout is not None
            while True:
                if not yielded_any:
                    remaining = first_content_deadline - time.monotonic()
                    if remaining <= 0:
                        # Only kill if we haven't received any events at all.
                        # If tool_use events arrived, Claude is working — use CLAUDE_TIMEOUT.
                        if not received_any_event:
                            log.warning(
                                "streaming_first_chunk_timeout",
                                timeout=first_chunk_timeout,
                            )
                            await _terminate_process(proc)
                            await proc.wait()
                            if metadata_collector is not None:
                                metadata_collector["error"] = True
                                metadata_collector["error_message"] = (
                                    f"Timeout after {first_chunk_timeout}s waiting for Claude to start streaming."
                                )
                                metadata_collector["error_kind"] = "timeout"
                                metadata_collector["retryable"] = True
                            return
                        line_timeout: float = float(CLAUDE_TIMEOUT)
                    else:
                        line_timeout = min(remaining, CLAUDE_TIMEOUT)
                else:
                    line_timeout = float(CLAUDE_TIMEOUT)

                try:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=line_timeout,
                    )
                except ValueError:
                    # LimitOverrunError: JSON line exceeds buffer (Write with large file)
                    log.warning("streaming_line_buffer_overflow")
                    if metadata_collector is not None:
                        metadata_collector.setdefault("warnings", []).append("buffer overflow (content truncated)")
                    continue
                except TimeoutError:
                    if not yielded_any and not received_any_event:
                        log.warning(
                            "streaming_first_chunk_timeout",
                            timeout=first_chunk_timeout,
                        )
                    await _terminate_process(proc)
                    await proc.wait()
                    if metadata_collector is not None:
                        metadata_collector["error"] = True
                        metadata_collector["error_message"] = f"Timeout after {line_timeout:.1f}s waiting for Claude."
                        metadata_collector["error_kind"] = "timeout"
                        metadata_collector["retryable"] = True
                    return

                if not line:
                    break

                line_text = line.decode().strip()
                if not line_text:
                    continue

                try:
                    data = json.loads(line_text)
                except json.JSONDecodeError:
                    continue

                # Any valid JSON line means the CLI is alive
                received_any_event = True

                # Handle different stream event types.
                # The CLI emits "assistant" events with message.content
                # arrays (not raw API content_block_delta events).
                event_type = data.get("type", "")

                if event_type == "assistant" and "message" in data:
                    # Extract text from message content blocks

                    content = data["message"].get("content", [])
                    for block in content:
                        if block.get("type") == "text" and block.get("text"):
                            yielded_any = True
                            yield block["text"]
                        elif block.get("type") == "tool_use" and metadata_collector is not None:
                            metadata_collector.setdefault("tool_uses", []).append(block)
                elif event_type == "content_block_delta":
                    # Raw API streaming format (kept for compatibility)
                    delta = data.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yielded_any = True
                            yield text
                elif event_type == "result":
                    # Capture metadata from result event
                    if metadata_collector is not None:
                        metadata_collector["session_id"] = data.get("session_id")
                        raw_cost = data.get("total_cost_usd", data.get("cost_usd", 0.0))
                        metadata_collector["cost_usd"] = float(raw_cost or 0.0)
                        metadata_collector["stop_reason"] = data.get("stop_reason", "")
                    # Final result — only yield if no text was received
                    # from assistant events (avoids duplicating the text)
                    result_text = data.get("result", "")
                    embedded_error = _classify_embedded_result_error(result_text)
                    if embedded_error is not None:
                        error_kind, retryable = embedded_error
                        if metadata_collector is not None:
                            metadata_collector["error"] = True
                            metadata_collector["error_kind"] = error_kind
                            metadata_collector["retryable"] = retryable
                            metadata_collector["error_message"] = (
                                _friendly_auth_message(result_text) if error_kind == "provider_auth" else result_text
                            )
                            metadata_collector["stop_reason"] = data.get("stop_reason", "error") or "error"
                        if error_kind == "provider_auth":
                            mark_claude_auth_failed(result_text)
                        continue
                    if result_text and not yielded_any:
                        yielded_any = True
                        yield result_text

        async for chunk in _read_lines():
            yield chunk

    finally:
        # Wait for process to finish
        with contextlib.suppress(Exception):
            await proc.wait()
        # Record streaming metrics
        _stream_elapsed = time.monotonic() - _stream_start
        from koda.services.metrics import CLAUDE_EXECUTION, DEPENDENCY_LATENCY, DEPENDENCY_REQUESTS

        CLAUDE_EXECUTION.labels(agent_id=_agent_id_label, provider="claude", model=model, streaming="true").observe(
            _stream_elapsed
        )
        _dep_status = "success" if yielded_any else "error"
        DEPENDENCY_REQUESTS.labels(agent_id=_agent_id_label, dependency="claude_cli", status=_dep_status).inc()
        DEPENDENCY_LATENCY.labels(agent_id=_agent_id_label, dependency="claude_cli").observe(_stream_elapsed)
        if yielded_any:
            record_success(claude_cli_breaker)
        else:
            record_failure(claude_cli_breaker)

        # Log stderr when streaming produced no content
        if not yielded_any and proc.stderr:
            try:
                stderr_data = await proc.stderr.read()
                stderr_text = _decode_process_output(stderr_data)
                if stderr_text:
                    if metadata_collector is not None and not metadata_collector.get("error_message"):
                        error_kind, retryable = _classify_error(stderr_text)
                        if error_kind == "provider_auth":
                            mark_claude_auth_failed(stderr_text)
                            stderr_text = _friendly_auth_message(stderr_text)
                        metadata_collector["error"] = True
                        metadata_collector["error_message"] = stderr_text
                        metadata_collector["error_kind"] = error_kind
                        metadata_collector["retryable"] = retryable
                    log.error(
                        "streaming_no_output",
                        stderr=stderr_text[:500],
                        returncode=proc.returncode,
                    )
            except Exception:
                pass
