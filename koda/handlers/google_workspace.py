"""Google Workspace command handlers: /gws, /gmail, /gcal, /gdrive, /gsheets."""

import json

from telegram import Update
from telegram.ext import ContextTypes

from koda.config import (
    BLOCKED_GWS_PATTERN,
    GWS_CREDENTIALS_FILE,
    GWS_ENABLED,
    GWS_TIMEOUT,
)
from koda.services.cli_runner import run_cli_command
from koda.utils.approval import with_approval
from koda.utils.command_helpers import authorized
from koda.utils.messaging import send_long_message


def _gws_env() -> dict[str, str] | None:
    """Return env dict with credentials path, or None."""
    if GWS_CREDENTIALS_FILE:
        return {"GOOGLE_APPLICATION_CREDENTIALS": GWS_CREDENTIALS_FILE}
    return None


def _format_gws_output(raw: str) -> str:
    """Pretty-print JSON output if possible, otherwise return raw."""
    # Try to extract JSON from the output (after "Exit N:\n")
    lines = raw.split("\n", 1)
    if len(lines) < 2:
        return raw

    prefix = lines[0]  # "Exit 0:" etc.
    body = lines[1].strip()

    try:
        parsed = json.loads(body)
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
        if len(formatted) > 3500:
            formatted = formatted[:3500] + "\n\u2026 (truncated)"
        return f"{prefix}\n{formatted}"
    except (json.JSONDecodeError, ValueError):
        return raw


async def _run_gws(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    args: str,
    usage_hint: str,
) -> None:
    """Shared logic for all GWS commands."""
    if not GWS_ENABLED:
        await update.message.reply_text("Google Workspace CLI is disabled.")
        return

    if not args:
        await update.message.reply_text(f"Usage: {usage_hint}")
        return

    work_dir = context.user_data["work_dir"]
    result = await run_cli_command(
        "gws",
        args,
        work_dir,
        blocked_pattern=BLOCKED_GWS_PATTERN,
        timeout=GWS_TIMEOUT,
        env=_gws_env(),
    )
    formatted = _format_gws_output(result)
    await send_long_message(update, f"```\n{formatted}\n```")


@authorized
@with_approval("gws")
async def cmd_gws(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run a Google Workspace CLI command."""
    args = " ".join(context.args) if context.args else ""
    await _run_gws(update, context, args, "/gws <service> <resource.method> [--params ...]")


@authorized
@with_approval("gmail")
async def cmd_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gmail shortcut: /gmail ... -> gws gmail ..."""
    args = " ".join(context.args) if context.args else ""
    await _run_gws(update, context, f"gmail {args}" if args else "", "/gmail <resource.method> [--params ...]")


@authorized
@with_approval("gcal")
async def cmd_gcal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calendar shortcut: /gcal ... -> gws calendar ..."""
    args = " ".join(context.args) if context.args else ""
    await _run_gws(update, context, f"calendar {args}" if args else "", "/gcal <resource.method> [--params ...]")


@authorized
@with_approval("gdrive")
async def cmd_gdrive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Drive shortcut: /gdrive ... -> gws drive ..."""
    args = " ".join(context.args) if context.args else ""
    await _run_gws(update, context, f"drive {args}" if args else "", "/gdrive <resource.method> [--params ...]")


@authorized
@with_approval("gsheets")
async def cmd_gsheets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sheets shortcut: /gsheets ... -> gws sheets ..."""
    args = " ".join(context.args) if context.args else ""
    await _run_gws(update, context, f"sheets {args}" if args else "", "/gsheets <resource.method> [--params ...]")
