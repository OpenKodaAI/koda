"""Automation command handlers: /cron, /search, /fetch, /http, /curl."""

from telegram import Update
from telegram.ext import ContextTypes

from koda.services.http_client import fetch_url, make_http_request, search_web
from koda.utils.approval import with_approval
from koda.utils.command_helpers import authorized
from koda.utils.messaging import send_long_message


@authorized
@with_approval("cron")
async def cmd_cron(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manage cron jobs: list, add, del, toggle."""
    args = context.args or []

    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "/cron list - List your legacy cron jobs\n"
            '/cron add "*/5 * * * *" <command> - Add a legacy read-only cron job\n'
            "/cron del <id> - Delete a legacy cron job\n"
            "/cron enable <id> - Enable a legacy cron job\n"
            "/cron disable <id> - Disable a legacy cron job\n"
            "Use /jobs for the unified scheduler."
        )
        return

    action = args[0].lower()

    if action == "list":
        from koda.services.cron_store import list_cron_jobs

        user_id = update.effective_user.id
        jobs = list_cron_jobs(user_id)
        if not jobs:
            await update.message.reply_text("No cron jobs configured. (legacy wrapper)")
            return

        lines = ["Your legacy cron jobs:\n"]
        for job_id, expr, cmd, desc, enabled in jobs:
            status = "ON" if enabled else "OFF"
            label = f" ({desc})" if desc else ""
            lines.append(f"#{job_id} [{status}] `{expr}` → {cmd}{label}")
        await send_long_message(update, "\n".join(lines))

    elif action == "add":
        if len(args) < 3:
            await update.message.reply_text('Usage: /cron add "*/5 * * * *" <command>\nQuote the cron expression.')
            return

        # Parse cron expression (may be quoted)
        rest = " ".join(args[1:])
        # Try to extract quoted cron expression
        if rest.startswith('"'):
            end_quote = rest.find('"', 1)
            if end_quote == -1:
                await update.message.reply_text("Missing closing quote for cron expression.")
                return
            cron_expr = rest[1:end_quote]
            command = rest[end_quote + 1 :].strip()
        elif rest.startswith("'"):
            end_quote = rest.find("'", 1)
            if end_quote == -1:
                await update.message.reply_text("Missing closing quote for cron expression.")
                return
            cron_expr = rest[1:end_quote]
            command = rest[end_quote + 1 :].strip()
        else:
            await update.message.reply_text('Please quote the cron expression: /cron add "*/5 * * * *" echo hello')
            return

        if not command:
            await update.message.reply_text("No command specified after cron expression.")
            return

        # Validate command against shell security filters (before croniter check)
        from koda.config import BLOCKED_SHELL_PATTERN, GIT_META_CHARS

        if GIT_META_CHARS.search(command):
            await update.message.reply_text("Shell meta-characters are not allowed in cron commands.")
            return
        if BLOCKED_SHELL_PATTERN.search(command):
            await update.message.reply_text("Blocked: this command is not allowed for safety reasons.")
            return

        # Validate cron expression
        try:
            from croniter import croniter

            if not croniter.is_valid(cron_expr):
                await update.message.reply_text(f"Invalid cron expression: {cron_expr}")
                return
        except ImportError:
            await update.message.reply_text("croniter not installed. Cannot validate cron expressions.")
            return

        # Validate minimum interval (60 seconds)
        from datetime import UTC, datetime

        cron = croniter(cron_expr, datetime.now(UTC))
        next1 = cron.get_next(datetime)
        next2 = cron.get_next(datetime)
        interval = (next2 - next1).total_seconds()
        if interval < 60:
            await update.message.reply_text("Minimum cron interval is 1 minute.")
            return

        from koda.services.cron_store import create_cron_job

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        from koda.utils.command_helpers import init_user_data

        init_user_data(context.user_data, user_id=user_id)
        work_dir = context.user_data.get("work_dir", "/tmp")
        try:
            job_id = create_cron_job(user_id, chat_id, cron_expr, command, work_dir=work_dir)
        except ValueError as e:
            await update.message.reply_text(str(e))
            return
        await update.message.reply_text(
            f"Legacy cron job #{job_id} created in validation mode: `{cron_expr}` → {command}\n"
            "A safe dry-run is running now. If validation passes, the job will be activated automatically."
        )

    elif action == "del":
        if len(args) < 2:
            await update.message.reply_text("Usage: /cron del <id>")
            return
        try:
            job_id = int(args[1])
        except ValueError:
            await update.message.reply_text("Invalid job ID.")
            return

        from koda.services.cron_store import cancel_cron_task, delete_cron_job

        user_id = update.effective_user.id
        if delete_cron_job(user_id, job_id):
            cancel_cron_task(job_id)
            await update.message.reply_text(f"Cron job #{job_id} deleted.")
        else:
            await update.message.reply_text(f"Cron job #{job_id} not found.")

    elif action in ("enable", "disable"):
        if len(args) < 2:
            await update.message.reply_text(f"Usage: /cron {action} <id>")
            return
        try:
            job_id = int(args[1])
        except ValueError:
            await update.message.reply_text("Invalid job ID.")
            return

        from koda.services.cron_store import (
            cancel_cron_task,
            get_cron_job,
            schedule_cron_task,
            toggle_cron_job,
        )

        user_id = update.effective_user.id
        enabled = action == "enable"
        if toggle_cron_job(user_id, job_id, enabled):
            if enabled:
                job = get_cron_job(job_id)
                if job:
                    schedule_cron_task(job_id, context.bot, job[2], job[3], job[4], work_dir=job[7] or "/tmp")
            else:
                cancel_cron_task(job_id)
            await update.message.reply_text(f"Cron job #{job_id} {'enabled' if enabled else 'disabled'}.")
        else:
            await update.message.reply_text(f"Cron job #{job_id} not found.")

    else:
        await update.message.reply_text(f"Unknown action: {action}. Use: list, add, del, enable, disable")


@authorized
@with_approval("search")
async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search the web using DuckDuckGo."""
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return

    await update.message.reply_text("Searching...")
    result = await search_web(query)
    await send_long_message(update, result)


@authorized
@with_approval("fetch")
async def cmd_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch a URL and return its content."""
    url = " ".join(context.args) if context.args else ""
    if not url:
        await update.message.reply_text("Usage: /fetch <url>")
        return

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    await update.message.reply_text("Fetching...")
    result = await fetch_url(url)
    await send_long_message(update, result)


@authorized
@with_approval("http")
async def cmd_http(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Make an HTTP request: /http GET https://example.com."""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /http <METHOD> <URL> [body]\nExample: /http GET https://api.example.com"
        )
        return

    method = args[0].upper()
    url = args[1]
    body = " ".join(args[2:]) if len(args) > 2 else None

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    result = await make_http_request(method, url, body=body)
    await send_long_message(update, f"```\n{result}\n```")


@authorized
@with_approval("curl")
async def cmd_curl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Simplified curl: /curl <url>."""
    url = " ".join(context.args) if context.args else ""
    if not url:
        await update.message.reply_text("Usage: /curl <url>")
        return

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    result = await fetch_url(url)
    await send_long_message(update, f"```\n{result}\n```")
