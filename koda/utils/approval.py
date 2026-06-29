"""Universal approval system for destructive operations.

Provides a @with_approval decorator that classifies commands as READ or WRITE
and requires explicit user confirmation for WRITE operations via InlineKeyboard.
"""

import asyncio
import contextlib
import contextvars
import functools
import secrets
import shlex
import time
from collections.abc import Callable, Coroutine
from dataclasses import asdict, dataclass
from typing import Any, Concatenate, ParamSpec, Protocol, TypeVar, cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from koda.agent_contract import (
    ActionEnvelope,
    normalize_integration_grants,
    resolve_integration_action,
)
from koda.config import (
    AGENT_ID,
    AGENT_RESOURCE_ACCESS_POLICY,
    ALLOWED_DOCKER_CMDS,
    ALLOWED_GIT_CMDS,
    GIT_META_CHARS,
)
from koda.logging_config import get_logger
from koda.services.execution_policy import ApprovalScope, evaluate_execution_policy
from koda.state.approval_grants import (
    cleanup_expired_approval_grants,
    load_approval_grants,
    remove_approval_grant,
    remove_approval_grants,
    replace_approval_grants,
    save_approval_grant,
)
from koda.state.pending_approvals import (
    cleanup_expired_ops,
    load_pending_ops,
    remove_pending_op,
    remove_pending_ops,
    save_pending_op,
)
from koda.telegram_types import BotContext, MessageUpdate
from koda.utils.command_helpers import ensure_canonical_session_id, require_message, require_user_data, require_user_id
from koda.utils.files import safe_resolve
from koda.utils.formatting import escape_html

log = get_logger(__name__)
P = ParamSpec("P")
R = TypeVar("R")


class _TelegramBotLike(Protocol):
    async def send_message(self, *args: Any, **kwargs: Any) -> Any: ...


CommandHandlerFunc = Callable[..., Coroutine[Any, Any, Any]]

# Defense in depth: ContextVar gate

_execution_approved: contextvars.ContextVar[bool] = contextvars.ContextVar("_execution_approved", default=False)


def check_execution_approved() -> bool:
    """Return True if the current execution context has been approved."""
    return _execution_approved.get()


# Pending operations store (in-memory, lost on restart)

_PENDING_OPS: dict[str, dict[str, Any]] = {}
_APPROVAL_GRANTS: dict[str, dict[str, Any]] = {}
APPROVAL_TIMEOUT = 300  # 5 minutes
MAX_PENDING_OPS_PER_USER = 10

_persistence_loaded = False


async def _ensure_persistence_loaded() -> None:
    """Lazy-load persisted pending ops into the in-memory dicts on first use."""
    global _persistence_loaded
    if _persistence_loaded:
        return
    _persistence_loaded = True
    try:
        # Restore user ops
        persisted_user = await load_pending_ops()
        for op_id, entry in persisted_user.items():
            if op_id not in _PENDING_OPS and entry.get("op_type") == "user":
                _PENDING_OPS[op_id] = {
                    "user_id": entry.get("user_id"),
                    "timestamp": entry.get("created_at", time.time()),
                    "cmd_name": entry.get("description", ""),
                    "args": "",
                    "session_id": entry.get("session_id"),
                    "chat_id": entry.get("chat_id"),
                    "agent_id": entry.get("agent_id"),
                    "requests": [
                        _deserialize_agent_approval_request(item)
                        for item in entry.get("requests") or []
                        if isinstance(item, dict)
                    ],
                    "grants": [],
                    "preview_text": str(entry.get("preview_text") or ""),
                    # handler/update/context cannot be restored
                    "handler": None,
                    "update": None,
                    "context": None,
                    "_restored": True,
                }
            elif op_id not in _PENDING_AGENT_CMD_OPS and entry.get("op_type") == "agent_cmd":
                _PENDING_AGENT_CMD_OPS[op_id] = {
                    "user_id": entry.get("user_id"),
                    "timestamp": entry.get("created_at", time.time()),
                    "event": asyncio.Event(),
                    "decision": None,
                    "description": entry.get("description", ""),
                    "agent_id": str(entry.get("agent_id") or "default"),
                    "session_id": str(entry.get("session_id") or "") or None,
                    "chat_id": entry.get("chat_id"),
                    "requests": [
                        _deserialize_agent_approval_request(item)
                        for item in entry.get("requests") or []
                        if isinstance(item, dict)
                    ],
                    "grants": [],
                    "preview_text": str(entry.get("preview_text") or ""),
                    "tool_id": entry.get("tool_id"),
                    "original_params": (
                        entry.get("original_params") if isinstance(entry.get("original_params"), dict) else {}
                    ),
                    "args_schema": entry.get("args_schema") if isinstance(entry.get("args_schema"), dict) else {},
                    "risk_class": entry.get("risk_class"),
                    "trace_id": entry.get("trace_id"),
                    "run_graph_node_id": entry.get("run_graph_node_id"),
                    "edited_params": None,
                    "response_text": None,
                    "rationale": None,
                    "_restored": True,
                }
        persisted_grants = await load_approval_grants()
        for grant_id, entry in persisted_grants.items():
            if grant_id not in _APPROVAL_GRANTS and isinstance(entry, dict):
                _APPROVAL_GRANTS[grant_id] = entry
    except Exception:
        log.warning("Failed to load persisted pending approvals", exc_info=True)


def _cleanup_stale_ops() -> None:
    """Remove pending ops older than APPROVAL_TIMEOUT."""
    now = time.time()
    stale = [k for k, v in _PENDING_OPS.items() if now - v["timestamp"] > APPROVAL_TIMEOUT]
    for k in stale:
        _PENDING_OPS.pop(k, None)


def _cleanup_stale_approval_grants() -> None:
    """Remove expired scoped approval grants from memory."""
    now = time.time()
    expired = [
        grant_id
        for grant_id, entry in _APPROVAL_GRANTS.items()
        if float(entry.get("expires_at") or 0) <= now or int(entry.get("remaining_uses") or 0) <= 0
    ]
    for grant_id in expired:
        _APPROVAL_GRANTS.pop(grant_id, None)


def _serialize_agent_approval_request(request: dict[str, Any]) -> dict[str, Any]:
    envelope = request.get("envelope")
    if isinstance(envelope, ActionEnvelope):
        serialized_envelope: dict[str, Any] = asdict(envelope)
    elif isinstance(envelope, dict):
        serialized_envelope = dict(envelope)
    else:
        serialized_envelope = {}

    approval_scope = request.get("approval_scope")
    if isinstance(approval_scope, ApprovalScope):
        serialized_scope: dict[str, Any] | None = asdict(approval_scope)
    elif isinstance(approval_scope, dict):
        serialized_scope = dict(approval_scope)
    else:
        serialized_scope = None

    payload = {
        "tool_id": request.get("tool_id"),
        "original_params": request.get("original_params") if isinstance(request.get("original_params"), dict) else None,
        "args_schema": request.get("args_schema") if isinstance(request.get("args_schema"), dict) else None,
        "risk_class": request.get("risk_class"),
        "trace_id": request.get("trace_id"),
        "run_graph_node_id": request.get("run_graph_node_id"),
        "envelope": serialized_envelope,
        "approval_scope": serialized_scope,
    }
    return {key: value for key, value in payload.items() if value not in (None, {}, [], "")}


def _deserialize_agent_approval_request(request: dict[str, Any]) -> dict[str, Any]:
    envelope = request.get("envelope")
    if isinstance(envelope, ActionEnvelope):
        resolved_envelope = envelope
    elif isinstance(envelope, dict):
        resolved_envelope = ActionEnvelope(**envelope)
    else:
        resolved_envelope = None

    approval_scope = request.get("approval_scope")
    if isinstance(approval_scope, ApprovalScope):
        resolved_scope = approval_scope
    elif isinstance(approval_scope, dict):
        resolved_scope = ApprovalScope(
            kind=str(approval_scope.get("kind") or "once"),
            ttl_seconds=int(approval_scope.get("ttl_seconds") or 600),
            max_uses=int(approval_scope.get("max_uses") or 1),
        )
    else:
        resolved_scope = None

    payload: dict[str, Any] = {
        "approval_scope": resolved_scope,
        "tool_id": request.get("tool_id"),
        "original_params": request.get("original_params") if isinstance(request.get("original_params"), dict) else None,
        "args_schema": request.get("args_schema") if isinstance(request.get("args_schema"), dict) else None,
        "risk_class": request.get("risk_class"),
        "trace_id": request.get("trace_id"),
        "run_graph_node_id": request.get("run_graph_node_id"),
    }
    if resolved_envelope is not None:
        payload["envelope"] = resolved_envelope
    return {key: value for key, value in payload.items() if value not in (None, {}, [], "")}


def _current_session_id(user_data: dict[str, Any]) -> str:
    return ensure_canonical_session_id(user_data)


def _current_chat_id(update: MessageUpdate) -> int | None:
    chat = getattr(update, "effective_chat", None)
    chat_id = getattr(chat, "id", None)
    if chat_id is None:
        return None
    try:
        return int(chat_id)
    except (TypeError, ValueError):
        return None


def _manual_approval_requests(
    *,
    policy_evaluation: Any,
) -> list[dict[str, Any]]:
    if policy_evaluation is None or not getattr(policy_evaluation, "envelope", None):
        return []
    request: dict[str, Any] = {
        "envelope": policy_evaluation.envelope,
    }
    if getattr(policy_evaluation, "approval_scope", None) is not None:
        request["approval_scope"] = policy_evaluation.approval_scope
    return [request]


async def revoke_scoped_approval_state(
    *,
    user_id: int,
    agent_id: str,
    session_id: str | None,
    chat_id: int | None = None,
) -> None:
    await remove_pending_ops(user_id=user_id, agent_id=agent_id, session_id=session_id, chat_id=chat_id)
    await remove_approval_grants(user_id=user_id, agent_id=agent_id, session_id=session_id, chat_id=chat_id)
    for grant_id, grant in list(_APPROVAL_GRANTS.items()):
        if int(grant.get("user_id") or 0) != user_id:
            continue
        if str(grant.get("agent_id") or "") != agent_id:
            continue
        if session_id is not None and str(grant.get("session_id") or "") != session_id:
            continue
        if chat_id is not None and int(grant.get("chat_id") or 0) != chat_id:
            continue
        _APPROVAL_GRANTS.pop(grant_id, None)
    for op_id, pending in list(_PENDING_OPS.items()):
        if int(pending.get("user_id") or 0) != user_id:
            continue
        if str(pending.get("agent_id") or agent_id) != agent_id:
            continue
        if session_id is not None and str(pending.get("session_id") or "") != session_id:
            continue
        if chat_id is not None and int(pending.get("chat_id") or 0) != chat_id:
            continue
        _PENDING_OPS.pop(op_id, None)
    for op_id, pending in list(_PENDING_AGENT_CMD_OPS.items()):
        if int(pending.get("user_id") or 0) != user_id:
            continue
        if str(pending.get("agent_id") or agent_id) != agent_id:
            continue
        if session_id is not None and str(pending.get("session_id") or "") != session_id:
            continue
        if chat_id is not None and int(pending.get("chat_id") or 0) != chat_id:
            continue
        _PENDING_AGENT_CMD_OPS.pop(op_id, None)


# READ/WRITE classifiers


def _always_write(_args: str) -> bool:
    return True


def _always_read(_args: str) -> bool:
    return False


def _first_token(args: str) -> str:
    """Return the lowercased first token or empty string."""
    return args.split()[0].lower() if args.strip() else ""


@dataclass(frozen=True, slots=True)
class _OperationalActionResolution:
    """Canonical command/action resolution for Koda-owned operational commands."""

    integration_id: str
    action_id: str
    access_level: str
    path: str | None = None
    deny_reason: str | None = None
    deny_message: str | None = None


def _matches_action_pattern(pattern: str, action_id: str) -> bool:
    normalized_pattern = str(pattern or "").strip().lower()
    normalized_action = str(action_id or "").strip().lower()
    if not normalized_pattern or not normalized_action:
        return False
    if normalized_pattern == "*":
        return True
    if normalized_pattern.endswith(".*"):
        prefix = normalized_pattern[:-2]
        return normalized_action == prefix or normalized_action.startswith(prefix + ".")
    if normalized_pattern.endswith("*"):
        return normalized_action.startswith(normalized_pattern[:-1])
    if "." not in normalized_pattern:
        return normalized_action == normalized_pattern or normalized_action.endswith("." + normalized_pattern)
    return normalized_action == normalized_pattern


def _path_allowed(path: str | None, allowed_paths: list[str]) -> bool:
    normalized_path = str(path or "").strip()
    if not normalized_path:
        return False
    for allowed in allowed_paths:
        candidate = str(allowed or "").strip()
        if not candidate:
            continue
        if normalized_path == candidate or normalized_path.startswith(candidate.rstrip("/") + "/"):
            return True
    return False


def _operational_resolution_from_contract(
    command_name: str,
    *,
    raw_args: str,
    path: str | None = None,
) -> _OperationalActionResolution:
    params: dict[str, Any] = {"args": raw_args}
    if path is not None:
        params["path"] = path
    resolved = resolve_integration_action(command_name, params)
    return _OperationalActionResolution(
        integration_id=resolved.integration_id,
        action_id=resolved.action_id,
        access_level=resolved.access_level,
        path=resolved.path or path,
    )


_OPS_COMMANDS = frozenset(
    {
        "shell",
        "git",
        "docker",
        "pip",
        "npm",
        "http_request",
        "write",
        "edit",
        "rm",
        "mkdir",
        "cat",
    }
)
_OPS_SHELL_READ_CMDS = frozenset(
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
_OPS_GIT_READ_CMDS = frozenset(
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
_OPS_DOCKER_READ_CMDS = frozenset(
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
_OPS_PIP_READ_CMDS = frozenset(
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
_OPS_PIP_WRITE_CMDS = frozenset({"install", "uninstall", "remove", "update", "download", "wheel", "build", "lock"})
_OPS_NPM_READ_CMDS = frozenset(
    {
        "list",
        "ls",
        "view",
        "info",
        "search",
        "explain",
        "help",
        "root",
        "prefix",
        "version",
        "cache",
        "doctor",
        "audit",
        "bin",
    }
)
_OPS_NPM_WRITE_CMDS = frozenset(
    {"install", "i", "add", "update", "remove", "rm", "uninstall", "publish", "pack", "link", "exec", "run", "prune"}
)


def _resolve_operational_command(
    command_name: str,
    raw_args: str,
    *,
    work_dir: str | None = None,
) -> _OperationalActionResolution | None:
    command = str(command_name or "").strip().lower()
    if command not in _OPS_COMMANDS:
        return None

    args = str(raw_args or "").strip()
    if not args:
        return None

    if command in {"shell", "git", "docker", "pip", "npm"} and GIT_META_CHARS.search(args):
        return _OperationalActionResolution(
            integration_id=command,
            action_id=f"{command}.meta",
            access_level="write" if command != "cat" else "read",
            deny_reason="shell_meta_characters",
            deny_message=f"Shell meta-characters are not allowed in {command} commands.",
        )

    pip_guard = _blocked_pattern_for_command("pip")
    if command == "pip" and pip_guard is not None and pip_guard.is_blocked(args):
        return _OperationalActionResolution(
            integration_id="pip",
            action_id="pip.blocked",
            access_level="write",
            deny_reason="pip_blocked_pattern",
            deny_message="Blocked: this pip command is not allowed for safety reasons.",
        )

    npm_guard = _blocked_pattern_for_command("npm")
    if command == "npm" and npm_guard is not None and npm_guard.is_blocked(args):
        return _OperationalActionResolution(
            integration_id="npm",
            action_id="npm.blocked",
            access_level="write",
            deny_reason="npm_blocked_pattern",
            deny_message="Blocked: this npm command is not allowed for safety reasons.",
        )

    tokens = shlex.split(args)
    first = _first_token(args)
    second = str(tokens[1]).strip().lower() if len(tokens) > 1 else ""

    if command == "shell":
        if first not in _OPS_SHELL_READ_CMDS:
            return _OperationalActionResolution(
                integration_id="shell",
                action_id=f"shell.{first or 'unknown'}",
                access_level="write",
                deny_reason="shell_write_not_allowed",
                deny_message="Blocked: /shell is read-only in this release.",
            )
        return _operational_resolution_from_contract("shell", raw_args=args)

    if command == "git":
        if first not in ALLOWED_GIT_CMDS:
            allowed = ", ".join(sorted(ALLOWED_GIT_CMDS))
            return _OperationalActionResolution(
                integration_id="git",
                action_id=f"git.{first or 'unknown'}",
                access_level="write",
                deny_reason="git_subcommand_not_allowed",
                deny_message=(
                    f"Git subcommand <code>{escape_html(first or 'unknown')}</code> is not allowed.\n"
                    f"Allowed: {escape_html(allowed)}"
                ),
            )
        return _operational_resolution_from_contract("git", raw_args=args)

    if command == "docker":
        if first not in ALLOWED_DOCKER_CMDS:
            allowed = ", ".join(sorted(ALLOWED_DOCKER_CMDS))
            return _OperationalActionResolution(
                integration_id="docker",
                action_id=f"docker.{first or 'unknown'}",
                access_level="write",
                deny_reason="docker_subcommand_not_allowed",
                deny_message=(
                    f"Docker subcommand <code>{escape_html(first or 'unknown')}</code> is not allowed.\n"
                    f"Allowed: {escape_html(allowed)}"
                ),
            )
        return _operational_resolution_from_contract("docker", raw_args=args)

    if command == "pip":
        if first in _OPS_PIP_READ_CMDS:
            return _operational_resolution_from_contract("pip", raw_args=args)
        if first in _OPS_PIP_WRITE_CMDS:
            return _operational_resolution_from_contract("pip", raw_args=args)
        return _OperationalActionResolution(
            integration_id="pip",
            action_id=_operational_resolution_from_contract("pip", raw_args=args).action_id,
            access_level="write",
            deny_reason="pip_subcommand_not_allowed",
            deny_message="pip subcommand is not allowed by the registry.",
        )

    if command == "npm":
        if first in _OPS_NPM_READ_CMDS:
            return _operational_resolution_from_contract("npm", raw_args=args)
        if first in _OPS_NPM_WRITE_CMDS:
            return _operational_resolution_from_contract("npm", raw_args=args)
        if first == "cache" and second in {"clean", "clear", "purge", "rm", "remove", "delete"}:
            return _operational_resolution_from_contract("npm", raw_args=args)
        return _OperationalActionResolution(
            integration_id="npm",
            action_id=_operational_resolution_from_contract("npm", raw_args=args).action_id,
            access_level="write",
            deny_reason="npm_subcommand_not_allowed",
            deny_message="npm subcommand is not allowed by the registry.",
        )

    if command in {"write", "edit", "rm", "mkdir", "cat"}:
        if not tokens:
            return None
        resolved_path = None
        if work_dir:
            resolved = safe_resolve(tokens[0], work_dir)
            resolved_path = str(resolved) if resolved is not None else None
        action_id = f"fileops.{command}"
        if resolved_path is None and work_dir:
            return _OperationalActionResolution(
                integration_id="fileops",
                action_id=action_id,
                access_level="write" if command != "cat" else "read",
                path=None,
                deny_reason="path_outside_workdir",
                deny_message="Access denied: path is outside working directory.",
            )
        return _operational_resolution_from_contract(
            command,
            raw_args=args,
            path=resolved_path,
        )

    if command == "http_request":
        tokens = args.split(maxsplit=2)
        if len(tokens) < 2:
            return None
        method = str(tokens[0] or "GET").strip().upper() or "GET"
        url = str(tokens[1] or "").strip()
        if not url:
            return None
        body = tokens[2] if len(tokens) > 2 else None
        resolved_action = resolve_integration_action(
            "http_request",
            {"method": method, "url": url, "body": body},
        )
        return _OperationalActionResolution(
            integration_id=resolved_action.integration_id,
            action_id=resolved_action.action_id,
            access_level=resolved_action.access_level,
            path=resolved_action.path,
        )

    return None


def _canonical_operational_request(command_name: str, raw_args: str) -> tuple[str, str]:
    normalized_command = str(command_name or "").strip().lower()
    args = str(raw_args or "")
    if normalized_command == "http":
        tokens = args.split(maxsplit=2)
        if len(tokens) >= 2:
            return "http_request", args
    return normalized_command, args


def _blocked_pattern_for_command(command_name: str) -> Any | None:
    """Return a guard exposing ``is_blocked(text)`` for the given
    command, or ``None`` when the command has no blocked pattern.

    Guards are sourced from the central
    :mod:`koda.services.blocked_patterns` registry so the approval
    flow uses the same DFA as the handlers and the dispatcher.
    """
    normalized_command = str(command_name or "").strip().lower()
    from koda.services import blocked_patterns

    return {
        "pip": blocked_patterns.PIP_GUARD,
        "npm": blocked_patterns.NPM_GUARD,
    }.get(normalized_command)


def _should_bypass_manual_validation(
    command_name: str,
    args_list: list[str],
) -> bool:
    normalized_command = str(command_name or "").strip().lower()
    if normalized_command == "http":
        return len(args_list) < 2
    if normalized_command != "cron":
        return False
    if not args_list:
        return True

    action = str(args_list[0] or "").strip().lower()
    if action == "list":
        return False
    if action not in {"add", "del", "enable", "disable"}:
        return True
    if action == "add":
        if len(args_list) < 3:
            return True
        rest = " ".join(args_list[1:])
        if rest.startswith('"'):
            end_quote = rest.find('"', 1)
            if end_quote == -1:
                return True
            command = rest[end_quote + 1 :].strip()
        elif rest.startswith("'"):
            end_quote = rest.find("'", 1)
            if end_quote == -1:
                return True
            command = rest[end_quote + 1 :].strip()
        else:
            return True
        if not command:
            return True
        with contextlib.suppress(Exception):
            from koda.services.blocked_patterns import is_blocked_shell

            if GIT_META_CHARS.search(command) or is_blocked_shell(command):
                return True
        return False

    if len(args_list) < 2:
        return True
    try:
        int(str(args_list[1] or "").strip())
    except ValueError:
        return True
    return False


def _policy_params_for_manual_command(
    policy_command_name: str,
    policy_raw_args: str,
    *,
    resolution: _OperationalActionResolution | None,
) -> dict[str, Any]:
    if policy_command_name == "http_request":
        tokens = policy_raw_args.split(maxsplit=2)
        method = str(tokens[0] if tokens else "GET").strip().upper() or "GET"
        url = str(tokens[1] if len(tokens) > 1 else "").strip()
        body = tokens[2] if len(tokens) > 2 else None
        params: dict[str, Any] = {"method": method, "url": url}
        if body is not None:
            params["body"] = body
        return params
    params = {"args": policy_raw_args}
    if resolution and resolution.path:
        params["path"] = resolution.path
    return params


def _evaluate_operational_grant(
    resolution: _OperationalActionResolution,
    *,
    work_dir: str | None = None,
) -> tuple[bool, str | None]:
    access_policy = AGENT_RESOURCE_ACCESS_POLICY if isinstance(AGENT_RESOURCE_ACCESS_POLICY, dict) else {}
    grants = normalize_integration_grants(access_policy.get("integration_grants"))
    grant = grants.get(resolution.integration_id)
    if not grant:
        return True, None

    if grant.get("enabled") is False:
        return False, "Blocked by integration policy: this integration is disabled."

    for pattern in grant.get("deny_actions") or []:
        if _matches_action_pattern(str(pattern), resolution.action_id):
            return False, "Blocked by integration policy: this action is explicitly denied."

    allow_actions = [str(item) for item in grant.get("allow_actions") or []]
    if allow_actions and not any(_matches_action_pattern(pattern, resolution.action_id) for pattern in allow_actions):
        return False, "Blocked by integration policy: this action is outside the granted scope."

    approval_mode = str(grant.get("approval_mode") or "").strip().lower()
    if approval_mode == "read_only" and resolution.access_level != "read":
        return False, "Blocked by integration policy: this grant allows read-only actions only."

    allowed_paths = [str(item) for item in grant.get("allowed_paths") or []]
    if allowed_paths:
        if not resolution.path:
            return False, "Blocked by integration policy: this path is outside the granted scope."
        if not _path_allowed(resolution.path, allowed_paths):
            return False, "Blocked by integration policy: this path is outside the granted scope."

    return True, None


def _resource_policy_for_operational_resolution(
    resolution: _OperationalActionResolution | None,
) -> dict[str, Any]:
    if resolution is None:
        return {}
    grant: dict[str, Any] = {"allow_actions": [resolution.action_id]}
    if resolution.path:
        grant["allowed_paths"] = [resolution.path]
    return {"integration_grants": {resolution.integration_id: grant}}


def _audit_operational_block(command_name: str, reason: str, user_id: int | None) -> None:
    try:
        from koda.services.audit import emit_security

        emit_security("security.command_blocked", user_id=user_id, tool=command_name, reason=reason)
    except Exception:
        log.debug("operational_policy_audit_failed", command=command_name, reason=reason, exc_info=True)


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


# Registry

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
    "docker": _is_docker_write,
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


# Approval keyboard


async def _show_approval_keyboard(
    update: MessageUpdate,
    context: BotContext,
    cmd_name: str,
    raw_args: str,
    handler_func: CommandHandlerFunc,
    *,
    preview_text: str | None = None,
    requests: list[dict[str, Any]] | None = None,
) -> None:
    """Show an InlineKeyboard asking the user to approve/deny the operation."""
    await _ensure_persistence_loaded()
    _cleanup_stale_ops()
    message = require_message(update)
    user_id = require_user_id(update)
    user_data = require_user_data(context)
    session_id = _current_session_id(user_data)
    chat_id = _current_chat_id(update)
    agent_id = AGENT_ID or "default"

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
        "session_id": session_id,
        "chat_id": chat_id,
        "agent_id": agent_id,
        "requests": list(requests or []),
        "grants": [],
    }
    user_data["_pending_op_id"] = op_id

    # Persist to disk
    await save_pending_op(
        op_id,
        {
            "user_id": user_id,
            "chat_id": chat_id,
            "session_id": session_id,
            "agent_id": agent_id,
            "description": f"/{cmd_name} {raw_args}".strip(),
            "op_type": "user",
            "requests": [_serialize_agent_approval_request(item) for item in requests or []],
            "preview_text": preview_text or "",
        },
        APPROVAL_TIMEOUT,
    )

    desc = f"/{cmd_name} {raw_args}".strip()
    keyboard_rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("Aprovar uma vez", callback_data=f"approve:one:{op_id}")]
    ]
    if requests:
        keyboard_rows.append([InlineKeyboardButton("Aprovar escopo", callback_data=f"approve:scope:{op_id}")])
    keyboard_rows.append([InlineKeyboardButton("Negar", callback_data=f"approve:deny:{op_id}")])
    keyboard = InlineKeyboardMarkup(keyboard_rows)
    approval_message = f"Confirmacao necessaria:\n<code>{escape_html(desc)}</code>"
    if preview_text:
        approval_message += f"\n\nPreview:\n<code>{escape_html(preview_text)}</code>"
    await message.reply_text(approval_message, reply_markup=keyboard, parse_mode=ParseMode.HTML)


# Dispatch approved operation


async def dispatch_approved_operation(op_id: str) -> None:
    """Execute a previously-pending operation after approval."""
    pending = _PENDING_OPS.pop(op_id, None)
    if not pending:
        return

    await remove_pending_op(op_id)

    handler = pending["handler"]
    original_update = pending["update"]
    original_context = pending["context"]
    grants = list(pending.get("grants") or [])
    requests = list(pending.get("requests") or [])
    user_id = int(pending.get("user_id") or 0)
    agent_id = str(pending.get("agent_id") or "").strip() or "default"
    session_id = str(pending.get("session_id") or "").strip() or None
    chat_id = pending.get("chat_id")

    original_user_data = require_user_data(original_context)
    original_user_data["_approved"] = True
    _execution_approved.set(True)
    success = False
    try:
        await handler(original_update, original_context)
        success = True
    finally:
        _execution_approved.set(False)
        original_user_data["_approved"] = False
        if success:
            _consume_pending_op_grants(
                grants=grants,
                requests=requests,
                user_id=user_id,
                agent_id=agent_id,
                session_id=session_id,
                chat_id=int(chat_id) if chat_id is not None else None,
            )


# Decorator


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
            context_args = [str(item) for item in (context.args or [])]
            raw_args = " ".join(context_args)
            policy_command_name, policy_raw_args = _canonical_operational_request(command_name, raw_args)
            resolution: _OperationalActionResolution | None = None
            policy_params: dict[str, Any] | None = None

            if not raw_args.strip():
                _execution_approved.set(True)
                try:
                    return await func(update, context, *args, **kwargs)
                finally:
                    _execution_approved.set(False)

            if _should_bypass_manual_validation(command_name, context_args):
                _execution_approved.set(True)
                try:
                    return await func(update, context, *args, **kwargs)
                finally:
                    _execution_approved.set(False)

            if policy_command_name in _OPS_COMMANDS:
                resolution = _resolve_operational_command(
                    policy_command_name,
                    policy_raw_args,
                    work_dir=str(user_data.get("work_dir") or "").strip() or None,
                )
                policy_params = _policy_params_for_manual_command(
                    policy_command_name,
                    policy_raw_args,
                    resolution=resolution,
                )
                if resolution and resolution.deny_reason:
                    user_id = None
                    with contextlib.suppress(Exception):
                        user_id = require_user_id(update)
                    _audit_operational_block(command_name, resolution.deny_reason, user_id)
                    await require_message(update).reply_text(
                        resolution.deny_message or "Blocked by integration policy.",
                        parse_mode=ParseMode.HTML,
                    )
                    return None
                if resolution:
                    allowed, deny_message = _evaluate_operational_grant(
                        resolution,
                        work_dir=str(user_data.get("work_dir") or "").strip() or None,
                    )
                    if not allowed:
                        user_id = None
                        with contextlib.suppress(Exception):
                            user_id = require_user_id(update)
                        _audit_operational_block(command_name, "integration_policy", user_id)
                        await require_message(update).reply_text(
                            deny_message or "Blocked by integration policy.",
                            parse_mode=ParseMode.HTML,
                        )
                        return None

            policy_evaluation = None
            approval_grant = None
            requested_scope: ApprovalScope | None = None
            approval_requests: list[dict[str, Any]] = []
            if policy_command_name in _OPS_COMMANDS:
                manual_tool_policy = {"allowed_tool_ids": [policy_command_name]}
                policy_evaluation = evaluate_execution_policy(
                    policy_command_name,
                    policy_params or {"args": policy_raw_args},
                    task_kind="general",
                    tool_policy=manual_tool_policy,
                    resource_access_policy=_resource_policy_for_operational_resolution(resolution),
                    known_tool=True,
                )
                requested_scope = policy_evaluation.approval_scope
                approval_requests = _manual_approval_requests(policy_evaluation=policy_evaluation)
                if requested_scope is not None:
                    current_session_id = str(user_data.get("session_id") or "").strip() or None
                    current_chat_id = _current_chat_id(update)
                    approval_grant = peek_agent_approval_grant(
                        user_id=require_user_id(update),
                        agent_id=AGENT_ID or "default",
                        envelope=policy_evaluation.envelope,
                        approval_scope=requested_scope,
                        session_id=current_session_id,
                        chat_id=current_chat_id,
                    )
                    if approval_grant is not None:
                        policy_evaluation = evaluate_execution_policy(
                            policy_command_name,
                            policy_params or {"args": policy_raw_args},
                            task_kind="general",
                            tool_policy=manual_tool_policy,
                            resource_access_policy=_resource_policy_for_operational_resolution(resolution),
                            known_tool=True,
                            approval_grant=approval_grant,
                        )
                if policy_evaluation.decision == "deny":
                    user_id = None
                    with contextlib.suppress(Exception):
                        user_id = require_user_id(update)
                    _audit_operational_block(command_name, policy_evaluation.reason_code, user_id)
                    await require_message(update).reply_text(
                        policy_evaluation.reason,
                        parse_mode=ParseMode.HTML,
                    )
                    return None

                if user_data.get("_approved"):
                    user_data["_approved"] = False
                    _execution_approved.set(True)
                    try:
                        return await func(update, context, *args, **kwargs)
                    finally:
                        _execution_approved.set(False)

                if policy_evaluation.requires_confirmation:
                    await _show_approval_keyboard(
                        update,
                        context,
                        command_name,
                        raw_args,
                        func,
                        preview_text=policy_evaluation.preview_text,
                        requests=approval_requests,
                    )
                    return None

            # READ operations → execute directly
            if (
                policy_evaluation
                and policy_evaluation.decision == "allow"
                and resolution
                and resolution.access_level == "read"
            ):
                _execution_approved.set(True)
                try:
                    result = await func(update, context, *args, **kwargs)
                finally:
                    _execution_approved.set(False)
                if approval_grant is not None and requested_scope is not None:
                    consume_agent_approval_grant(
                        user_id=require_user_id(update),
                        agent_id=AGENT_ID or "default",
                        envelope=policy_evaluation.envelope,
                        approval_scope=requested_scope,
                        session_id=str(user_data.get("session_id") or "").strip() or None,
                        chat_id=_current_chat_id(update),
                    )
                return result

            if not is_write_operation(policy_command_name, policy_raw_args):
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

            if policy_evaluation and policy_evaluation.decision == "allow":
                _execution_approved.set(True)
                try:
                    result = await func(update, context, *args, **kwargs)
                finally:
                    _execution_approved.set(False)
                if approval_grant is not None and requested_scope is not None:
                    consume_agent_approval_grant(
                        user_id=require_user_id(update),
                        agent_id=AGENT_ID or "default",
                        envelope=policy_evaluation.envelope,
                        approval_scope=requested_scope,
                        session_id=str(user_data.get("session_id") or "").strip() or None,
                        chat_id=_current_chat_id(update),
                    )
                return result

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
    user_data.pop("_approved", None)
    user_data.pop("_pending_op_id", None)


def _grant_matches(
    grant: dict[str, Any],
    *,
    envelope: ActionEnvelope,
    approval_scope: ApprovalScope | None,
    session_id: str | None = None,
    chat_id: int | None = None,
) -> bool:
    if session_id is not None and str(grant.get("session_id") or "") != session_id:
        return False
    if chat_id is not None and int(grant.get("chat_id") or 0) != chat_id:
        return False
    if str(grant.get("kind") or "approve_once") == "approve_once":
        return str(grant.get("exact_fingerprint") or "") == (
            f"{envelope.resource_scope_fingerprint}:{envelope.params_fingerprint}"
        )
    if approval_scope is None:
        return False
    return str(grant.get("scope_fingerprint") or "") == envelope.resource_scope_fingerprint


def _issue_agent_approval_grants(
    *,
    user_id: int,
    agent_id: str,
    session_id: str | None = None,
    chat_id: int | None = None,
    requests: list[dict[str, Any]],
    decision: str,
    issued_by_op_id: str | None = None,
) -> list[dict[str, Any]]:
    grants: list[dict[str, Any]] = []
    scope_kind = "approve_scope" if decision == "approved_scope" else "approve_once"
    for request in requests:
        resolved_request = _deserialize_agent_approval_request(request)
        envelope = resolved_request.get("envelope")
        if not isinstance(envelope, ActionEnvelope):
            continue
        resolved_envelope = envelope
        resolved_scope = cast(ApprovalScope | None, resolved_request.get("approval_scope"))
        grant_id = secrets.token_urlsafe(10)
        created_at = time.time()
        ttl_seconds = resolved_scope.ttl_seconds if resolved_scope is not None else 600
        max_uses = resolved_scope.max_uses if scope_kind == "approve_scope" and resolved_scope is not None else 1
        grant = {
            "grant_id": grant_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "session_id": session_id,
            "chat_id": chat_id,
            "kind": scope_kind,
            "max_uses": max_uses,
            "remaining_uses": max_uses,
            "created_at": created_at,
            "expires_at": created_at + ttl_seconds,
            "issued_by_op_id": issued_by_op_id,
            "resource_scope_fingerprint": resolved_envelope.resource_scope_fingerprint,
            "params_fingerprint": resolved_envelope.params_fingerprint,
            "exact_fingerprint": (
                f"{resolved_envelope.resource_scope_fingerprint}:{resolved_envelope.params_fingerprint}"
            ),
            "scope_fingerprint": resolved_envelope.resource_scope_fingerprint,
        }
        _APPROVAL_GRANTS[grant_id] = grant
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(save_approval_grant(grant_id, grant, ttl_seconds))
        except RuntimeError:
            pass
        grants.append(grant)
    return grants


def match_agent_approval_grant(
    grants: list[dict[str, Any]] | None,
    *,
    envelope: ActionEnvelope,
    approval_scope: ApprovalScope | None,
    session_id: str | None = None,
    chat_id: int | None = None,
) -> dict[str, Any] | None:
    for grant in grants or []:
        if not isinstance(grant, dict):
            continue
        matches = _grant_matches(
            grant,
            envelope=envelope,
            approval_scope=approval_scope,
            session_id=session_id,
            chat_id=chat_id,
        )
        if matches:
            return dict(grant)
    return None


def consume_agent_approval_grant(
    *,
    user_id: int,
    agent_id: str,
    envelope: ActionEnvelope,
    approval_scope: ApprovalScope | None,
    session_id: str | None = None,
    chat_id: int | None = None,
) -> dict[str, Any] | None:
    _cleanup_stale_approval_grants()
    for grant_id, grant in list(_APPROVAL_GRANTS.items()):
        if int(grant.get("user_id") or 0) != user_id:
            continue
        if str(grant.get("agent_id") or "") != agent_id:
            continue
        if not _grant_matches(
            grant,
            envelope=envelope,
            approval_scope=approval_scope,
            session_id=session_id,
            chat_id=chat_id,
        ):
            continue
        grant["remaining_uses"] = int(grant.get("remaining_uses") or 1) - 1
        if int(grant["remaining_uses"]) <= 0 or str(grant.get("kind") or "") == "approve_once":
            _APPROVAL_GRANTS.pop(grant_id, None)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(remove_approval_grant(grant_id))
            except RuntimeError:
                pass
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(replace_approval_grants(dict(_APPROVAL_GRANTS)))
            except RuntimeError:
                pass
        return dict(grant)
    return None


def peek_agent_approval_grant(
    *,
    user_id: int,
    agent_id: str,
    envelope: ActionEnvelope,
    approval_scope: ApprovalScope | None,
    session_id: str | None = None,
    chat_id: int | None = None,
) -> dict[str, Any] | None:
    _cleanup_stale_approval_grants()
    for grant in _APPROVAL_GRANTS.values():
        if int(grant.get("user_id") or 0) != user_id:
            continue
        if str(grant.get("agent_id") or "") != agent_id:
            continue
        if not _grant_matches(
            grant,
            envelope=envelope,
            approval_scope=approval_scope,
            session_id=session_id,
            chat_id=chat_id,
        ):
            continue
        return dict(grant)
    return None


def _consume_pending_op_grants(
    *,
    grants: list[dict[str, Any]],
    requests: list[dict[str, Any]],
    user_id: int,
    agent_id: str,
    session_id: str | None,
    chat_id: int | None,
) -> None:
    if not grants and not requests:
        return
    for request in requests:
        resolved_request = _deserialize_agent_approval_request(request)
        envelope = resolved_request.get("envelope")
        approval_scope = cast(ApprovalScope | None, resolved_request.get("approval_scope"))
        if not isinstance(envelope, ActionEnvelope):
            continue
        consume_agent_approval_grant(
            user_id=user_id,
            agent_id=agent_id,
            envelope=envelope,
            approval_scope=approval_scope,
            session_id=session_id,
            chat_id=chat_id,
        )


async def rotate_session_approval_state(
    *,
    user_data: dict[str, Any],
    user_id: int,
    chat_id: int | None,
    agent_id: str | None = None,
) -> tuple[str | None, str]:
    previous_session_id = str(user_data.get("session_id") or "").strip() or None
    resolved_agent_id = str(agent_id or AGENT_ID or "default")
    await revoke_scoped_approval_state(
        user_id=user_id,
        agent_id=resolved_agent_id,
        session_id=previous_session_id,
        chat_id=chat_id,
    )
    user_data["session_id"] = None
    user_data["provider_sessions"] = {}
    user_data["_supervised_session_id"] = None
    user_data["_supervised_provider"] = None
    reset_approval_state(user_data)
    next_session_id = _current_session_id(user_data)
    return previous_session_id, next_session_id


# Agent-cmd approval (for agent loop tool calls)

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
    """Periodically clean stale pending operations.

    Runs forever as the awaited body of a managed background loop. The
    ``BackgroundLoopSupervisor`` treats *any* runner that returns as
    "loop_returned" and restarts it after the configured delay, so this
    coroutine must await the actual cleanup loop directly instead of
    spawning a detached task and returning — otherwise the supervisor
    relaunches us every ``restart_delay_seconds`` and floods the log with
    ``background_loop_returned`` warnings.
    """
    while True:
        await asyncio.sleep(60)
        _cleanup_stale_ops()
        _cleanup_stale_agent_cmd_ops()
        _cleanup_stale_approval_grants()
        await cleanup_expired_ops()
        await cleanup_expired_approval_grants()


async def request_agent_cmd_approval(
    telegram_bot: _TelegramBotLike,
    chat_id: int,
    user_id: int,
    description: str,
    *,
    agent_id: str = "default",
    session_id: str | None = None,
    requests: list[dict[str, Any]] | None = None,
    preview_text: str | None = None,
    task_id: int | None = None,
    tool_id: str | None = None,
    original_params: dict[str, Any] | None = None,
    args_schema: dict[str, Any] | None = None,
    risk_class: str | None = None,
    trace_id: str | None = None,
    run_graph_node_id: str | None = None,
) -> str:
    """Show inline keyboard for agent-cmd write approval. Returns op_id."""
    await _ensure_persistence_loaded()
    _cleanup_stale_agent_cmd_ops()

    op_id = secrets.token_urlsafe(8)
    event = asyncio.Event()

    _PENDING_AGENT_CMD_OPS[op_id] = {
        "user_id": user_id,
        "timestamp": time.time(),
        "event": event,
        "decision": None,
        "description": description,
        "agent_id": agent_id,
        "session_id": session_id,
        "chat_id": chat_id,
        "task_id": task_id,
        "requests": list(requests or []),
        "grants": [],
        "preview_text": preview_text or "",
        "tool_id": tool_id,
        "original_params": dict(original_params or {}),
        "args_schema": dict(args_schema or {}),
        "risk_class": risk_class,
        "trace_id": trace_id,
        "run_graph_node_id": run_graph_node_id,
        "edited_params": None,
        "response_text": None,
        "rationale": None,
    }

    # Persist to disk
    await save_pending_op(
        op_id,
        {
            "user_id": user_id,
            "description": description,
            "op_type": "agent_cmd",
            "agent_id": agent_id,
            "session_id": session_id,
            "chat_id": chat_id,
            "requests": [_serialize_agent_approval_request(item) for item in requests or []],
            "preview_text": preview_text or "",
            "tool_id": tool_id,
            "original_params": dict(original_params or {}),
            "args_schema": dict(args_schema or {}),
            "risk_class": risk_class,
            "trace_id": trace_id,
            "run_graph_node_id": run_graph_node_id,
        },
        APPROVAL_TIMEOUT,
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Aprovar", callback_data=f"acmd:ok:{op_id}"),
                InlineKeyboardButton("Aprovar escopo", callback_data=f"acmd:scope:{op_id}"),
            ],
            [InlineKeyboardButton("Negar", callback_data=f"acmd:no:{op_id}")],
        ]
    )
    message = f"Confirmacao necessaria:\n<code>{escape_html(description)}</code>"
    if preview_text:
        message += f"\n\nPreview:\n<code>{escape_html(preview_text)}</code>"

    await telegram_bot.send_message(
        chat_id=chat_id,
        text=message,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )

    try:
        from koda.services.approval_broker import publish_approval_required

        await publish_approval_required(
            approval_id=op_id,
            session_id=session_id,
            task_id=task_id,
            description=description,
            preview_text=preview_text,
        )
    except Exception:
        log.debug("approval_broker_publish_failed", exc_info=True)

    return op_id


def resolve_agent_cmd_approval(
    op_id: str,
    decision: str,
    *,
    grants: list[dict[str, Any]] | None = None,
    edited_params: dict[str, Any] | None = None,
    response_text: str | None = None,
    rationale: str | None = None,
) -> None:
    """Set decision and signal the waiting coroutine."""
    op = _PENDING_AGENT_CMD_OPS.get(op_id)
    if op:
        op["decision"] = decision
        if grants is not None:
            op["grants"] = list(grants)
        if edited_params is not None:
            op["edited_params"] = dict(edited_params)
        if response_text is not None:
            op["response_text"] = response_text
        if rationale is not None:
            op["rationale"] = rationale
        op["event"].set()
        try:
            from koda.services.approval_broker import spawn_publish_resolved

            spawn_publish_resolved(
                approval_id=op_id,
                decision=decision,
                session_id=str(op.get("session_id") or "").strip() or None,
                task_id=op.get("task_id"),
            )
        except Exception:
            log.debug("approval_broker_spawn_resolved_failed", exc_info=True)


def get_agent_cmd_decision(op_id: str) -> dict[str, Any] | None:
    """Read the decision envelope after the event has fired."""
    op = _PENDING_AGENT_CMD_OPS.get(op_id)
    if op:
        result: dict[str, Any] = {
            "decision": cast(str | None, op.get("decision")),
            "grants": list(op.get("grants") or []),
        }
        if isinstance(op.get("edited_params"), dict):
            result["edited_params"] = op["edited_params"]
        if str(op.get("response_text") or ""):
            result["response_text"] = str(op.get("response_text") or "")
        if str(op.get("rationale") or ""):
            result["rationale"] = str(op.get("rationale") or "")
        return result
    return None


def cleanup_agent_cmd_op(op_id: str) -> None:
    """Remove a completed agent-cmd op from the pending store."""
    _PENDING_AGENT_CMD_OPS.pop(op_id, None)
    # Fire-and-forget persistence removal; tolerate missing event loop.
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(remove_pending_op(op_id))
    except RuntimeError:
        pass
