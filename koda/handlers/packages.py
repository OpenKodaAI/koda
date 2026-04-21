"""Package manager command handlers: /pip, /npm."""

from telegram import Update
from telegram.ext import ContextTypes

from koda.config import BLOCKED_NPM_PATTERN, BLOCKED_PIP_PATTERN, GIT_META_CHARS, NPM_ENABLED, PIP_ENABLED
from koda.services.shell_runner import run_shell_command
from koda.utils.approval import with_approval
from koda.utils.command_helpers import authorized
from koda.utils.messaging import send_long_message


@authorized
@with_approval("pip")
async def cmd_pip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run a pip command."""
    if not PIP_ENABLED:
        await update.message.reply_text("pip commands are disabled.")
        return

    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text("Usage: /pip <args>\nExample: /pip list, /pip install requests")
        return

    if GIT_META_CHARS.search(args):
        await update.message.reply_text("Shell meta-characters are not allowed in pip commands.")
        return

    if BLOCKED_PIP_PATTERN and BLOCKED_PIP_PATTERN.search(args):
        await update.message.reply_text("Blocked: this pip command is not allowed for safety reasons.")
        return

    work_dir = context.user_data["work_dir"]
    result = await run_shell_command(f"pip {args}", work_dir)
    await send_long_message(update, f"```\n{result}\n```")


@authorized
@with_approval("npm")
async def cmd_npm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run an npm command."""
    if not NPM_ENABLED:
        await update.message.reply_text("npm commands are disabled.")
        return

    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text("Usage: /npm <args>\nExample: /npm list, /npm install lodash")
        return

    if GIT_META_CHARS.search(args):
        await update.message.reply_text("Shell meta-characters are not allowed in npm commands.")
        return

    if BLOCKED_NPM_PATTERN and BLOCKED_NPM_PATTERN.search(args):
        await update.message.reply_text("Blocked: this npm command is not allowed for safety reasons.")
        return

    work_dir = context.user_data["work_dir"]
    result = await run_shell_command(f"npm {args}", work_dir)
    await send_long_message(update, f"```\n{result}\n```")
