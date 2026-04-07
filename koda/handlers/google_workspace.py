"""Google Workspace command handlers: /gws, /gmail, /gcal, /gdrive, /gsheets."""

import json
import os
from contextlib import contextmanager

from telegram import Update
from telegram.ext import ContextTypes

from koda.agent_contract import canonicalize_gws_command_args
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


def _legacy_gws_env() -> dict[str, str] | None:
    """Return env dict with credentials path, or None."""
    if GWS_CREDENTIALS_FILE:
        return {
            "GOOGLE_APPLICATION_CREDENTIALS": GWS_CREDENTIALS_FILE,
            "GWS_CREDENTIALS_FILE": GWS_CREDENTIALS_FILE,
        }
    key_content = os.environ.get("GWS_SERVICE_ACCOUNT_KEY", "")
    if key_content:
        import tempfile

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, prefix="gws_sa_")  # noqa: SIM115
        tmp.write(key_content)
        tmp.close()
        return {
            "GOOGLE_APPLICATION_CREDENTIALS": tmp.name,
            "GWS_CREDENTIALS_FILE": tmp.name,
        }
    return None


def _gws_env() -> dict[str, str] | None:
    return _legacy_gws_env()


@contextmanager
def _gws_env_context():
    current_agent = str(os.environ.get("AGENT_ID") or "").strip().upper()
    if current_agent:
        from koda.services.core_connection_broker import get_core_connection_broker

        with get_core_connection_broker().materialize_cli_environment(
            "gws",
            agent_id=current_agent,
        ) as (_resolved, env):
            yield env
        return
    yield _legacy_gws_env()


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
    *,
    service: str | None = None,
) -> None:
    """Shared logic for all GWS commands."""
    if not GWS_ENABLED:
        await update.message.reply_text("Google Workspace CLI is disabled.")
        return

    if not args:
        await update.message.reply_text(f"Usage: {usage_hint}")
        return

    work_dir = context.user_data["work_dir"]
    command_args = canonicalize_gws_command_args(service, args) if service else args
    try:
        with _gws_env_context() as env:
            result = await run_cli_command(
                "gws",
                command_args,
                work_dir,
                blocked_pattern=BLOCKED_GWS_PATTERN,
                timeout=GWS_TIMEOUT,
                env=env,
            )
    except RuntimeError as exc:
        await update.message.reply_text(str(exc))
        return
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
    await _run_gws(
        update,
        context,
        args,
        "/gmail <resource.method> [--params ...]",
        service="gmail",
    )


@authorized
@with_approval("gcal")
async def cmd_gcal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calendar shortcut: /gcal ... -> gws calendar ..."""
    args = " ".join(context.args) if context.args else ""
    await _run_gws(
        update,
        context,
        args,
        "/gcal <resource.method> [--params ...]",
        service="calendar",
    )


@authorized
@with_approval("gdrive")
async def cmd_gdrive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Drive shortcut: /gdrive ... -> gws drive ..."""
    args = " ".join(context.args) if context.args else ""
    await _run_gws(
        update,
        context,
        args,
        "/gdrive <resource.method> [--params ...]",
        service="drive",
    )


@authorized
@with_approval("gsheets")
async def cmd_gsheets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sheets shortcut: /gsheets ... -> gws sheets ..."""
    args = " ".join(context.args) if context.args else ""
    await _run_gws(
        update,
        context,
        args,
        "/gsheets <resource.method> [--params ...]",
        service="sheets",
    )
