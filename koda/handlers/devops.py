"""Local runtime command handlers."""

from telegram import Update
from telegram.ext import ContextTypes

from koda.config import (
    ALLOWED_DOCKER_CMDS,
    DOCKER_ENABLED,
)
from koda.services.blocked_patterns import is_blocked_docker
from koda.services.cli_runner import run_cli_command
from koda.utils.approval import with_approval
from koda.utils.command_helpers import authorized
from koda.utils.messaging import send_long_message


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
        is_blocked=is_blocked_docker,
        allowed_cmds=ALLOWED_DOCKER_CMDS,
    )
    await send_long_message(update, f"```\n{result}\n```")
