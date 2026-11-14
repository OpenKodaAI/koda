"""Shell and git command execution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from koda.config import AGENT_ID, SHELL_TIMEOUT
from koda.internal_rpc.runtime_kernel import is_command_refusal
from koda.logging_config import get_logger
from koda.services.provider_env import (
    build_tool_subprocess_env,
    validate_runtime_path,
    validate_shell_command,
)
from koda.services.runtime.controller import get_runtime_controller
from koda.services.shell_safety import enforce_shell_guardrails

log = get_logger(__name__)

NOT_APPROVED_MESSAGE = "Error: command execution not approved."
BLOCKED_MESSAGE = "Blocked: this command is not allowed for safety reasons."


class ShellCommandRejected(Exception):
    """The approval gate, the command guard or the runtime kernel refused a shell command before it ran."""


def guard_shell_command(command: str, work_dir: str) -> tuple[str, str]:
    """Apply the approval gate and the command guard shared by every shell tool.

    Returns the validated command and working directory. Raises
    :class:`ShellCommandRejected` with the user-facing message; nothing has run
    when it raises.
    """
    from koda.utils.approval import check_execution_approved

    if not check_execution_approved():
        raise ShellCommandRejected(NOT_APPROVED_MESSAGE)
    try:
        validated_command = validate_shell_command(enforce_shell_guardrails(command))
        validated_work_dir = validate_runtime_path(work_dir, allow_empty=True)
    except ValueError as e:
        log.warning("shell_command_blocked", command=command[:100], reason=str(e))
        raise ShellCommandRejected(BLOCKED_MESSAGE) from e
    return validated_command, validated_work_dir


async def execute_in_runtime_kernel(
    command: str,
    work_dir: str,
    *,
    timeout: int,
    env: Mapping[str, str] | None = None,
    command_kind: str = "shell",
) -> dict[str, object]:
    """Run a command that already passed :func:`guard_shell_command` through the kernel's ExecuteCommand.

    The command runs in its own process group. Cancelling this call cancels the
    RPC, and the kernel then kills every process still in that group.

    Raises :class:`ShellCommandRejected` with the command guard's answer when the
    kernel's own command check or network policy refuses the command.
    """
    proc_env = build_tool_subprocess_env(env_overrides=env)
    runtime_kernel = get_runtime_controller().runtime_kernel
    try:
        return await runtime_kernel.execute_command(
            agent_id=AGENT_ID,
            command=command,
            working_directory=work_dir,
            environment_overrides=proc_env,
            timeout_seconds=max(1, int(timeout)),
            purpose="shell",
            env_labels={"command_kind": command_kind},
            start_new_session=True,
        )
    except Exception as e:
        if not is_command_refusal(e):
            raise
        details = getattr(e, "details", None)
        log.warning(
            "shell_command_blocked_by_runtime_kernel",
            command=command[:100],
            command_kind=command_kind,
            reason=str(details() if callable(details) else e)[:200],
        )
        raise ShellCommandRejected(BLOCKED_MESSAGE) from e


async def run_shell_command(
    command: str,
    work_dir: str,
    timeout: int = SHELL_TIMEOUT,
    env: dict[str, str] | None = None,
) -> str:
    """Run a shell command through the runtime kernel and return output."""
    try:
        command, validated_work_dir = guard_shell_command(command, work_dir)
    except ShellCommandRejected as e:
        return str(e)

    try:
        execution = await execute_in_runtime_kernel(command, validated_work_dir, timeout=timeout, env=env)
        if not bool(execution.get("forwarded", False)):
            reason = str(execution.get("reason") or "runtime kernel unavailable")
            log.warning("shell_runtime_kernel_unavailable", command=command[:100], reason=reason)
            return f"Error: {reason}"

        stdout = str(execution.get("stdout") or "")
        stderr = str(execution.get("stderr") or "")
        if bool(execution.get("timed_out", False)):
            timeout_seconds = max(1, int(timeout))
            log.warning("shell_timeout", command=command[:100], timeout=timeout_seconds)
            return f"Timeout after {timeout_seconds}s."

        output = (stdout + stderr).strip()
        if len(output) > 4000:
            output = output[:4000] + "\n… (truncated)"
        exit_code = int(cast(Any, execution.get("exit_code", 0)) or 0)
        return f"Exit {exit_code}:\n{output}" if output else f"Exit {exit_code}: (no output)"
    except ShellCommandRejected as e:
        return str(e)
    except ValueError as e:
        log.warning("shell_command_blocked", command=command[:100], reason=str(e))
        return BLOCKED_MESSAGE
    except Exception as e:
        log.exception("shell_error", command=command[:100])
        return f"Error: {e}"
