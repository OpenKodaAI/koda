"""Atlassian command handlers: /jira, /jissue, /jboard, /jsprint, /confluence."""

import json

from telegram import Update
from telegram.ext import ContextTypes

from koda.config import (
    BLOCKED_CONFLUENCE_PATTERN,
    BLOCKED_JIRA_PATTERN,
    CONFLUENCE_ENABLED,
    JIRA_ENABLED,
)
from koda.services.atlassian_client import (
    get_confluence_service,
    get_jira_service,
    parse_atlassian_args,
)
from koda.utils.approval import with_approval
from koda.utils.command_helpers import authorized
from koda.utils.messaging import send_long_message


def _format_atlassian_output(raw: str) -> str:
    """Pretty-print JSON output if possible, otherwise return raw.

    The service layer already truncates at 4000 chars, so this only
    re-indents JSON for readability without further truncation.
    """
    lines = raw.split("\n", 1)
    if len(lines) < 2:
        return raw

    prefix = lines[0]
    body = lines[1].strip()

    try:
        parsed = json.loads(body)
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
        return f"{prefix}\n{formatted}"
    except (json.JSONDecodeError, ValueError):
        return raw


async def _run_jira(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    args: str,
    usage_hint: str,
) -> None:
    """Shared logic for all Jira commands."""
    if not JIRA_ENABLED:
        await update.message.reply_text("Jira integration is disabled.")
        return

    if not args:
        await update.message.reply_text(f"Usage: {usage_hint}")
        return

    if BLOCKED_JIRA_PATTERN and BLOCKED_JIRA_PATTERN.search(args):
        await update.message.reply_text("This Jira operation is blocked for safety.")
        return

    try:
        resource, action, params = parse_atlassian_args(args)
    except ValueError as e:
        await update.message.reply_text(f"Parse error: {e}")
        return

    result = await get_jira_service().execute(resource, action, params)
    formatted = _format_atlassian_output(result)
    await send_long_message(update, f"```\n{formatted}\n```")


async def _run_confluence(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    args: str,
    usage_hint: str,
) -> None:
    """Shared logic for Confluence commands."""
    if not CONFLUENCE_ENABLED:
        await update.message.reply_text("Confluence integration is disabled.")
        return

    if not args:
        await update.message.reply_text(f"Usage: {usage_hint}")
        return

    if BLOCKED_CONFLUENCE_PATTERN and BLOCKED_CONFLUENCE_PATTERN.search(args):
        await update.message.reply_text("This Confluence operation is blocked for safety.")
        return

    try:
        resource, action, params = parse_atlassian_args(args)
    except ValueError as e:
        await update.message.reply_text(f"Parse error: {e}")
        return

    result = await get_confluence_service().execute(resource, action, params)
    formatted = _format_atlassian_output(result)
    await send_long_message(update, f"```\n{formatted}\n```")


@authorized
@with_approval("jira")
async def cmd_jira(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run a Jira command: /jira <resource> <action> [--key value ...]."""
    args = " ".join(context.args) if context.args else ""
    await _run_jira(update, context, args, "/jira <resource> <action> [--key value ...]")


@authorized
@with_approval("jissue")
async def cmd_jissue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Issue shortcut: /jissue ... -> issues ..."""
    args = " ".join(context.args) if context.args else ""
    await _run_jira(update, context, f"issues {args}" if args else "", "/jissue <action> [--key value ...]")


@authorized
@with_approval("jboard")
async def cmd_jboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Board shortcut: /jboard ... -> boards ..."""
    args = " ".join(context.args) if context.args else ""
    await _run_jira(update, context, f"boards {args}" if args else "", "/jboard <action> [--key value ...]")


@authorized
@with_approval("jsprint")
async def cmd_jsprint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sprint shortcut: /jsprint ... -> sprints ..."""
    args = " ".join(context.args) if context.args else ""
    await _run_jira(update, context, f"sprints {args}" if args else "", "/jsprint <action> [--key value ...]")


@authorized
@with_approval("confluence")
async def cmd_confluence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run a Confluence command: /confluence <resource> <action> [--key value ...]."""
    args = " ".join(context.args) if context.args else ""
    await _run_confluence(update, context, args, "/confluence <resource> <action> [--key value ...]")
