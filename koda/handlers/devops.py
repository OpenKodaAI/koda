"""DevOps command handlers: /gh, /glab, /docker."""

import os
from contextlib import contextmanager, nullcontext

from telegram import Update
from telegram.ext import ContextTypes

from koda.config import (
    ALLOWED_DOCKER_CMDS,
    BLOCKED_DOCKER_PATTERN,
    BLOCKED_GH_PATTERN,
    BLOCKED_GLAB_PATTERN,
    DOCKER_ENABLED,
    GH_ENABLED,
    GLAB_ENABLED,
)
from koda.services.cli_runner import run_cli_command
from koda.utils.approval import with_approval
from koda.utils.command_helpers import authorized
from koda.utils.messaging import send_long_message


@contextmanager
def _core_cli_env_context(integration_id: str):
    current_agent = str(os.environ.get("AGENT_ID") or "").strip().upper()
    if not current_agent:
        with nullcontext(None) as env:
            yield env
        return

    from koda.services.core_connection_broker import get_core_connection_broker

    with get_core_connection_broker().materialize_cli_environment(integration_id, agent_id=current_agent) as (
        _resolved,
        env,
    ):
        yield env


@authorized
@with_approval("gh")
async def cmd_gh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run a GitHub CLI command."""
    if not GH_ENABLED:
        await update.message.reply_text("GitHub CLI is disabled.")
        return

    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text("Usage: /gh <args>\nExample: /gh pr list")
        return

    work_dir = context.user_data["work_dir"]
    try:
        with _core_cli_env_context("gh") as env:
            result = await run_cli_command("gh", args, work_dir, blocked_pattern=BLOCKED_GH_PATTERN, env=env)
    except RuntimeError as exc:
        await update.message.reply_text(str(exc))
        return
    await send_long_message(update, f"```\n{result}\n```")


@authorized
@with_approval("glab")
async def cmd_glab(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run a GitLab CLI command."""
    if not GLAB_ENABLED:
        await update.message.reply_text("GitLab CLI is disabled.")
        return

    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text("Usage: /glab <args>\nExample: /glab mr list")
        return

    work_dir = context.user_data["work_dir"]
    try:
        with _core_cli_env_context("glab") as env:
            result = await run_cli_command("glab", args, work_dir, blocked_pattern=BLOCKED_GLAB_PATTERN, env=env)
    except RuntimeError as exc:
        await update.message.reply_text(str(exc))
        return
    await send_long_message(update, f"```\n{result}\n```")


@authorized
@with_approval("docker")
async def cmd_docker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run a Docker command."""
    if not DOCKER_ENABLED:
        await update.message.reply_text("Docker commands are disabled.")
        return

    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text("Usage: /docker <args>\nExample: /docker ps")
        return

    work_dir = context.user_data["work_dir"]
    result = await run_cli_command(
        "docker",
        args,
        work_dir,
        blocked_pattern=BLOCKED_DOCKER_PATTERN,
        allowed_cmds=ALLOWED_DOCKER_CMDS,
    )
    await send_long_message(update, f"```\n{result}\n```")
