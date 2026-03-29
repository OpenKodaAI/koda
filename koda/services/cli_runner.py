"""Generic CLI runner for gh/glab/docker with security checks."""

import asyncio
import re
import shlex
from dataclasses import dataclass

from koda.config import GIT_META_CHARS
from koda.logging_config import get_logger
from koda.services.provider_env import build_tool_subprocess_env
from koda.utils.process_control import terminate_process_tree

log = get_logger(__name__)

# Dangerous patterns that should never be allowed in CLI args
_DANGEROUS_PATTERNS = re.compile(
    r"rm\s+-rf|mkfs|dd\s+if=|shutdown|reboot|curl.*\|.*sh|wget.*\|.*sh|>\s*/dev/sd",
    re.I,
)


@dataclass
class CliCommandResult:
    binary: str
    args: str
    text: str
    exit_code: int | None = None
    timed_out: bool = False
    blocked: bool = False
    error: bool = False
    truncated: bool = False


async def run_cli_command_detailed(
    binary: str,
    args: str,
    work_dir: str,
    *,
    blocked_pattern: re.Pattern | None = None,
    allowed_cmds: set[str] | None = None,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> CliCommandResult:
    """Run a CLI command and return structured execution details."""
    if not args.strip():
        return CliCommandResult(binary=binary, args=args, text=f"Usage: /{binary} <args>", blocked=True)

    if GIT_META_CHARS.search(args):
        log.warning("cli_metachar_blocked", binary=binary, args=args[:100])
        return CliCommandResult(
            binary=binary,
            args=args,
            text="Shell meta-characters are not allowed.",
            blocked=True,
        )

    if _DANGEROUS_PATTERNS.search(args):
        log.warning("cli_dangerous_blocked", binary=binary, args=args[:100])
        return CliCommandResult(
            binary=binary,
            args=args,
            text="Blocked: this command is not allowed for safety reasons.",
            blocked=True,
        )

    if blocked_pattern and blocked_pattern.search(args):
        log.warning("cli_blocked_pattern", binary=binary, args=args[:100])
        return CliCommandResult(
            binary=binary,
            args=args,
            text="Blocked: this command pattern is not allowed.",
            blocked=True,
        )

    first_token = args.split()[0]
    if allowed_cmds and first_token not in allowed_cmds:
        return CliCommandResult(
            binary=binary,
            args=args,
            text=f"Subcommand `{first_token}` is not allowed.\nAllowed: {', '.join(sorted(allowed_cmds))}",
            blocked=True,
        )

    from koda.utils.approval import check_execution_approved

    if not check_execution_approved():
        return CliCommandResult(
            binary=binary,
            args=args,
            text="Error: command execution not approved.",
            blocked=True,
            error=True,
        )

    argv = [binary] + shlex.split(args)
    try:
        proc_env = build_tool_subprocess_env(env_overrides=env)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env=proc_env,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except TimeoutError:
            await terminate_process_tree(proc)
            await proc.wait()
            log.warning("cli_timeout", binary=binary, timeout=timeout)
            return CliCommandResult(
                binary=binary,
                args=args,
                text=f"Timeout after {timeout}s.",
                timed_out=True,
                error=True,
            )

        output = (stdout.decode() + stderr.decode()).strip()
        truncated = False
        if len(output) > 4000:
            output = output[:4000] + "\n… (truncated)"
            truncated = True
        text = f"Exit {proc.returncode}:\n{output}" if output else f"Exit {proc.returncode}: (no output)"
        return CliCommandResult(
            binary=binary,
            args=args,
            text=text,
            exit_code=proc.returncode,
            error=proc.returncode != 0,
            truncated=truncated,
        )
    except Exception as e:
        log.exception("cli_exec_error", binary=binary)
        return CliCommandResult(
            binary=binary,
            args=args,
            text=f"Error: {e}",
            error=True,
        )


async def run_cli_command(
    binary: str,
    args: str,
    work_dir: str,
    *,
    blocked_pattern: re.Pattern | None = None,
    allowed_cmds: set[str] | None = None,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> str:
    """Run a CLI command with safety checks.

    Args:
        binary: CLI binary name (gh, glab, docker, gws).
        args: Arguments string.
        work_dir: Working directory.
        blocked_pattern: Optional regex to block specific arg patterns.
        allowed_cmds: Optional set of allowed subcommands (first token).
        timeout: Execution timeout in seconds.
        env: Optional extra environment variables for the subprocess.

    Returns:
        Command output string.
    """
    result = await run_cli_command_detailed(
        binary,
        args,
        work_dir,
        blocked_pattern=blocked_pattern,
        allowed_cmds=allowed_cmds,
        timeout=timeout,
        env=env,
    )
    return result.text
