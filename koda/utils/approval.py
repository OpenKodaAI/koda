"""Universal approval system for destructive operations.

Provides a @with_approval decorator that classifies commands as READ or WRITE
and requires explicit user confirmation for WRITE operations via InlineKeyboard.
"""

import asyncio
import contextvars
import functools
import secrets
import time
from collections.abc import Callable, Coroutine
from typing import Any, Concatenate, ParamSpec, Protocol, TypeVar, cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from koda.logging_config import get_logger
from koda.telegram_types import BotContext, MessageUpdate
from koda.utils.command_helpers import require_message, require_user_data, require_user_id
from koda.utils.formatting import escape_html

log = get_logger(__name__)
P = ParamSpec("P")
R = TypeVar("R")


class _TelegramBotLike(Protocol):
    async def send_message(self, *args: Any, **kwargs: Any) -> Any: ...


CommandHandlerFunc = Callable[..., Coroutine[Any, Any, Any]]

# ---------------------------------------------------------------------------
# Defense in depth: ContextVar gate
# ---------------------------------------------------------------------------

_execution_approved: contextvars.ContextVar[bool] = contextvars.ContextVar("_execution_approved", default=False)


def check_execution_approved() -> bool:
    """Return True if the current execution context has been approved."""
    return _execution_approved.get()


# ---------------------------------------------------------------------------
# Pending operations store (in-memory, lost on restart)
# ---------------------------------------------------------------------------

_PENDING_OPS: dict[str, dict[str, Any]] = {}
APPROVAL_TIMEOUT = 300  # 5 minutes
MAX_PENDING_OPS_PER_USER = 10


def _cleanup_stale_ops() -> None:
    """Remove pending ops older than APPROVAL_TIMEOUT."""
    now = time.time()
    stale = [k for k, v in _PENDING_OPS.items() if now - v["timestamp"] > APPROVAL_TIMEOUT]
    for k in stale:
        _PENDING_OPS.pop(k, None)


# ---------------------------------------------------------------------------
# READ/WRITE classifiers
# ---------------------------------------------------------------------------


def _always_write(_args: str) -> bool:
    return True


def _always_read(_args: str) -> bool:
    return False


def _first_token(args: str) -> str:
    """Return the lowercased first token or empty string."""
    return args.split()[0].lower() if args.strip() else ""


_SHELL_READ_CMDS = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "grep",
        "find",
        "wc",
        "file",
        "stat",
        "which",
        "whoami",
        "hostname",
        "uname",
        "date",
        "echo",
        "pwd",
        "df",
        "du",
        "free",
        "uptime",
        "id",
        "groups",
        "less",
        "more",
        "diff",
        "sort",
        "uniq",
        "tr",
        "cut",
        "test",
        "true",
        "false",
        "man",
        "help",
        "type",
        "readlink",
        "realpath",
        "basename",
        "dirname",
        "tree",
    }
)


def _is_shell_write(args: str) -> bool:
    first = _first_token(args)
    return first not in _SHELL_READ_CMDS


_GIT_READ_CMDS = frozenset(
    {
        "status",
        "log",
        "diff",
        "show",
        "fetch",
        "blame",
        "shortlog",
        "describe",
        "rev-parse",
        "ls-files",
        "ls-tree",
        "ls-remote",
        "reflog",
    }
)


def _is_git_write(args: str) -> bool:
    first = _first_token(args)
    return first not in _GIT_READ_CMDS


_GH_READ_PREFIXES = frozenset(
    {
        "pr list",
        "pr view",
        "pr diff",
        "pr checks",
        "pr status",
        "issue list",
        "issue view",
        "issue status",
        "repo list",
        "repo view",
        "release list",
        "release view",
        "run list",
        "run view",
    }
)


def _is_gh_write(args: str) -> bool:
    lower = args.lower().strip()
    return not any(lower.startswith(p) for p in _GH_READ_PREFIXES)


def _is_glab_write(args: str) -> bool:
    # Same logic as gh
    return _is_gh_write(args)


_DOCKER_READ_CMDS = frozenset(
    {
        "ps",
        "images",
        "logs",
        "inspect",
        "stats",
        "top",
        "port",
        "info",
        "version",
        "search",
        "history",
        "events",
        "diff",
    }
)


def _is_docker_write(args: str) -> bool:
    first = _first_token(args)
    return first not in _DOCKER_READ_CMDS


_GWS_READ_ACTIONS = frozenset(
    {
        "list",
        "get",
        "search",
        "schema",
    }
)


def _is_gws_write(args: str) -> bool:
    """Classify GWS commands. Format: '<service> <resource.method> ...'
    or '<resource.method> ...'. We look at the last part of the method name."""
    parts = args.strip().split()
    if len(parts) < 1:
        return True
    # The method is usually something like 'users.messages.list' or 'events.list'
    # Find the token that contains a dot (resource.method)
    for part in parts:
        if "." in part:
            action = part.rsplit(".", 1)[-1].lower()
            return action not in _GWS_READ_ACTIONS
    # No dotted token found — treat as write to be safe
    return True


_ATLASSIAN_READ_ACTIONS = frozenset(
    {
        "search",
        "get",
        "list",
        "comments",
        "comment_get",
        "view",
        "analyze",
        "attachments",
        "links",
        "view_video",
        "view_image",
        "view_audio",
        "transitions",
    }
)


def _is_atlassian_write(args: str) -> bool:
    """Classify Jira/Confluence commands. Format: '<resource> <action> ...'."""
    parts = args.strip().split()
    if len(parts) < 2:
        return True  # Can't determine — safe default
    action = parts[1].lower()
    return action not in _ATLASSIAN_READ_ACTIONS


_PKG_READ_CMDS = frozenset(
    {
        "list",
        "show",
        "search",
        "info",
        "outdated",
        "audit",
        "check",
        "view",
        "ls",
        "explain",
        "find",
        "help",
        "config",
        "cache",
        "doctor",
        "pack",
        "prefix",
        "root",
        "run-script",
        "version",
    }
)


def _is_pkg_write(args: str) -> bool:
    first = _first_token(args)
    return first not in _PKG_READ_CMDS


def _is_http_write(args: str) -> bool:
    first = _first_token(args).upper()
    return first not in {"GET", "HEAD", "OPTIONS"}


def _is_cron_write(args: str) -> bool:
    first = _first_token(args)
    return first != "list"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

WRITE_CLASSIFIERS: dict[str, Callable[[str], bool]] = {
    # Always WRITE
    "rm": _always_write,
    "write": _always_write,
    "edit": _always_write,
    "mkdir": _always_write,
    # Always READ
    "cat": _always_read,
    "ls": _always_read,
    "search": _always_read,
    "fetch": _always_read,
    "curl": _always_read,
    "browse": _always_read,
    "screenshot": _always_read,
    # Classified by args
    "shell": _is_shell_write,
    "git": _is_git_write,
    "gh": _is_gh_write,
    "glab": _is_glab_write,
    "docker": _is_docker_write,
    "gws": _is_gws_write,
    "gmail": _is_gws_write,
    "gcal": _is_gws_write,
    "gdrive": _is_gws_write,
    "gsheets": _is_gws_write,
    "jira": _is_atlassian_write,
    "jissue": _is_atlassian_write,
    "jboard": _is_atlassian_write,
    "jsprint": _is_atlassian_write,
    "confluence": _is_atlassian_write,
    "pip": _is_pkg_write,
    "npm": _is_pkg_write,
    "http": _is_http_write,
    "cron": _is_cron_write,
    "click": _always_write,
    "type": _always_write,
    "js": _always_write,
}


def is_write_operation(command_name: str, args: str) -> bool:
    """Return True if the command+args constitutes a WRITE operation.

    Unknown commands default to True (safe default).
    """
    classifier = WRITE_CLASSIFIERS.get(command_name)
    if classifier is None:
        return True  # Unknown command → assume write
    return bool(classifier(args))


# ---------------------------------------------------------------------------
# Approval keyboard
# ---------------------------------------------------------------------------


async def _show_approval_keyboard(
    update: MessageUpdate,
    context: BotContext,
    cmd_name: str,
    raw_args: str,
    handler_func: CommandHandlerFunc,
) -> None:
    """Show an InlineKeyboard asking the user to approve/deny the operation."""
    _cleanup_stale_ops()
    message = require_message(update)
    user_id = require_user_id(update)
    user_data = require_user_data(context)

    # Limit pending ops per user to prevent memory DoS
    user_pending = sum(1 for v in _PENDING_OPS.values() if v.get("user_id") == user_id)
    if user_pending >= MAX_PENDING_OPS_PER_USER:
        await message.reply_text("Too many pending operations. Please approve or deny existing ones first.")
        return

    op_id = f"{int(time.time())}_{user_id}_{secrets.token_urlsafe(16)}"
    _PENDING_OPS[op_id] = {
        "handler": handler_func,
        "update": update,
        "context": context,
        "args": raw_args,
        "cmd_name": cmd_name,
        "user_id": user_id,
        "timestamp": time.time(),
    }
    user_data["_pending_op_id"] = op_id

    desc = f"/{cmd_name} {raw_args}".strip()
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Aprovar este", callback_data=f"approve:one:{op_id}"),
                InlineKeyboardButton("Aprovar todos", callback_data=f"approve:all:{op_id}"),
            ],
            [InlineKeyboardButton("Negar", callback_data=f"approve:deny:{op_id}")],
        ]
    )
    await message.reply_text(
        f"Confirmacao necessaria:\n<code>{escape_html(desc)}</code>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Dispatch approved operation
# ---------------------------------------------------------------------------


async def dispatch_approved_operation(op_id: str) -> None:
    """Execute a previously-pending operation after approval."""
    pending = _PENDING_OPS.pop(op_id, None)
    if not pending:
        return

    handler = pending["handler"]
    original_update = pending["update"]
    original_context = pending["context"]

    original_user_data = require_user_data(original_context)
    original_user_data["_approved"] = True
    _execution_approved.set(True)
    try:
        await handler(original_update, original_context)
    finally:
        _execution_approved.set(False)
        original_user_data["_approved"] = False


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def with_approval(
    command_name: str,
) -> Callable[
    [Callable[Concatenate[MessageUpdate, BotContext, P], Coroutine[Any, Any, R]]],
    Callable[Concatenate[MessageUpdate, BotContext, P], Coroutine[Any, Any, R | None]],
]:
    """Decorator that gates WRITE operations behind user approval.

    Must be applied AFTER @authorized (i.e., listed below it):
        @authorized
        @with_approval("rm")
        async def cmd_rm(...):
    """

    def decorator(
        func: Callable[Concatenate[MessageUpdate, BotContext, P], Coroutine[Any, Any, R]],
    ) -> Callable[Concatenate[MessageUpdate, BotContext, P], Coroutine[Any, Any, R | None]]:
        @functools.wraps(func)
        async def wrapper(
            update: MessageUpdate,
            context: BotContext,
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> R | None:
            user_data = require_user_data(context)
            raw_args = " ".join(context.args or [])

            # READ operations → execute directly
            if not is_write_operation(command_name, raw_args):
                _execution_approved.set(True)
                try:
                    return await func(update, context, *args, **kwargs)
                finally:
                    _execution_approved.set(False)

            # "Approve all" active → execute directly
            if user_data.get("_approve_all"):
                _execution_approved.set(True)
                try:
                    return await func(update, context, *args, **kwargs)
                finally:
                    _execution_approved.set(False)

            # Already approved (re-invocation from callback) → execute
            if user_data.get("_approved"):
                user_data["_approved"] = False  # reset immediately
                _execution_approved.set(True)
                try:
                    return await func(update, context, *args, **kwargs)
                finally:
                    _execution_approved.set(False)

            # Needs approval → show keyboard, store, return
            await _show_approval_keyboard(update, context, command_name, raw_args, func)
            return None

        return cast(
            Callable[Concatenate[MessageUpdate, BotContext, P], Coroutine[Any, Any, R | None]],
            wrapper,
        )

    return decorator


def reset_approval_state(user_data: dict) -> None:
    """Clear all approval-related state from user_data (e.g., on /newsession)."""
    user_data.pop("_approve_all", None)
    user_data.pop("_approved", None)
    user_data.pop("_pending_op_id", None)
    user_data.pop("_approve_all_agent_tools", None)


# ---------------------------------------------------------------------------
# Agent-cmd approval (for agent loop tool calls)
# ---------------------------------------------------------------------------

_PENDING_AGENT_CMD_OPS: dict[str, dict[str, Any]] = {}


def _cleanup_stale_agent_cmd_ops() -> None:
    """Remove stale agent-cmd ops and signal their events with timeout."""
    now = time.time()
    stale = [k for k, v in _PENDING_AGENT_CMD_OPS.items() if now - v["timestamp"] > APPROVAL_TIMEOUT]
    for k in stale:
        op = _PENDING_AGENT_CMD_OPS.pop(k, None)
        if op and not op["event"].is_set():
            op["decision"] = "timeout"
            op["event"].set()


_approval_cleanup_task: asyncio.Task | None = None


async def start_approval_cleanup() -> None:
    """Spawn a background task that periodically cleans stale pending operations."""
    global _approval_cleanup_task

    async def _loop() -> None:
        while True:
            await asyncio.sleep(60)
            _cleanup_stale_ops()
            _cleanup_stale_agent_cmd_ops()

    _approval_cleanup_task = asyncio.create_task(_loop())


async def request_agent_cmd_approval(
    telegram_bot: _TelegramBotLike,
    chat_id: int,
    user_id: int,
    description: str,
) -> str:
    """Show inline keyboard for agent-cmd write approval. Returns op_id."""
    _cleanup_stale_agent_cmd_ops()

    op_id = secrets.token_urlsafe(8)
    event = asyncio.Event()

    _PENDING_AGENT_CMD_OPS[op_id] = {
        "user_id": user_id,
        "timestamp": time.time(),
        "event": event,
        "decision": None,
        "description": description,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Aprovar", callback_data=f"acmd:ok:{op_id}"),
                InlineKeyboardButton("Aprovar todos", callback_data=f"acmd:all:{op_id}"),
            ],
            [InlineKeyboardButton("Negar", callback_data=f"acmd:no:{op_id}")],
        ]
    )

    await telegram_bot.send_message(
        chat_id=chat_id,
        text=f"Confirmacao necessaria:\n<code>{escape_html(description)}</code>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )

    return op_id


def resolve_agent_cmd_approval(op_id: str, decision: str) -> None:
    """Set decision and signal the waiting coroutine."""
    op = _PENDING_AGENT_CMD_OPS.get(op_id)
    if op:
        op["decision"] = decision
        op["event"].set()


def get_agent_cmd_decision(op_id: str) -> str | None:
    """Read the decision after the event has fired."""
    op = _PENDING_AGENT_CMD_OPS.get(op_id)
    if op:
        return cast(str | None, op["decision"])
    return None


def cleanup_agent_cmd_op(op_id: str) -> None:
    """Remove a completed agent-cmd op from the pending store."""
    _PENDING_AGENT_CMD_OPS.pop(op_id, None)
