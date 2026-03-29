"""Shell and git command execution."""

from __future__ import annotations

from typing import Any, cast

from koda.config import AGENT_ID, SHELL_TIMEOUT
from koda.logging_config import get_logger
from koda.services.provider_env import (
    build_tool_subprocess_env,
    validate_runtime_path,
    validate_shell_command,
)
from koda.services.runtime.controller import get_runtime_controller

log = get_logger(__name__)


async def run_shell_command(
    command: str,
    work_dir: str,
    timeout: int = SHELL_TIMEOUT,
    env: dict[str, str] | None = None,
) -> str:
    """Run a shell command through the runtime kernel and return output."""
    from koda.utils.approval import check_execution_approved

    if not check_execution_approved():
        return "Error: command execution not approved."

    try:
        command = validate_shell_command(command)
        validated_work_dir = validate_runtime_path(work_dir, allow_empty=True)
        proc_env = build_tool_subprocess_env(env_overrides=env)
        runtime_kernel = get_runtime_controller().runtime_kernel
        execution = await runtime_kernel.execute_command(
            agent_id=AGENT_ID,
            command=command,
            working_directory=validated_work_dir,
            environment_overrides=proc_env,
            timeout_seconds=max(1, int(timeout)),
            purpose="shell",
            env_labels={"command_kind": "shell"},
            start_new_session=True,
        )
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
    except ValueError as e:
        log.warning("shell_command_blocked", command=command[:100], reason=str(e))
        return f"Blocked: {e}"
    except Exception as e:
        log.exception("shell_error", command=command[:100])
        return f"Error: {e}"
