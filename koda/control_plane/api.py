"""aiohttp handlers for the control-plane API."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiohttp import ContentTypeError, web

from koda.services.http_client import inspect_url
from koda.services.link_analyzer import fetch_link_metadata

from .dashboard_memory import (
    apply_memory_curation_action,
    get_memory_curation_cluster_payload,
    get_memory_curation_detail_payload,
    get_memory_map_payload,
    list_memory_curation_payload,
)
from .dashboard_service import (
    get_dashboard_cost_insights,
    list_dashboard_agent_summaries,
    list_dashboard_dlq,
    list_dashboard_execution_summaries,
    list_dashboard_schedules,
)
from .manager import GeneralPayloadValidationError, get_control_plane_manager
from .onboarding import load_control_plane_openapi_spec, render_setup_page
from .operator_auth import OperatorAuthContext, OperatorAuthService, get_operator_auth_service
from .settings import (
    AGENT_SECTIONS,
    CONTROL_PLANE_AUTH_MODE,
    DOCUMENT_KINDS,
)


def _manager() -> Any:
    return get_control_plane_manager()


def _auth_service() -> OperatorAuthService:
    return get_operator_auth_service()


async def _json_payload(request: web.Request) -> dict[str, Any]:
    if request.can_read_body:
        try:
            payload = await request.json()
        except (ContentTypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON payload") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON payload must be an object")
        return cast(dict[str, Any], payload)
    return {}


def _bounded_int(raw_value: str | None, *, name: str, default: int, minimum: int = 1, maximum: int = 1000) -> int:
    if raw_value is None or raw_value == "":
        value = default
    else:
        value = int(raw_value)
    if value < minimum or value > maximum:
        raise ValueError(f"invalid {name}")
    return value


def _clip_preview_text(value: Any, *, limit: int) -> str | None:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


_PUBLIC_CONTROL_PLANE_API_PATHS: tuple[str, ...] = (
    "/api/control-plane/onboarding/status",
    "/api/control-plane/auth/status",
    "/api/control-plane/auth/bootstrap/exchange",
    "/api/control-plane/auth/login",
    "/api/control-plane/auth/register-owner",
    "/api/control-plane/auth/legacy/exchange",
    "/api/control-plane/auth/password/recover",
)


def _is_public_control_plane_api_path(path: str) -> bool:
    return any(path == candidate or path.startswith(f"{candidate}/") for candidate in _PUBLIC_CONTROL_PLANE_API_PATHS)


def _development_auth_enabled() -> bool:
    return CONTROL_PLANE_AUTH_MODE == "development" and os.environ.get("NODE_ENV", "").strip().lower() != "production"


def _optional_auth_context(request: web.Request) -> OperatorAuthContext | None:
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.startswith("Bearer "):
        return None
    request_token = auth_header.removeprefix("Bearer ").strip()
    if not request_token:
        return None
    return _auth_service().resolve_bearer_token(request_token)


def _authorize_request(request: web.Request) -> web.Response | None:
    if CONTROL_PLANE_AUTH_MODE == "open" or _development_auth_enabled():
        request["operator_auth"] = OperatorAuthContext(
            auth_kind="development",
            subject_type="development",
            user_id=None,
            username="dev",
            email=None,
            display_name="Development Operator",
        )
        return None
    if CONTROL_PLANE_AUTH_MODE == "token":
        context = _optional_auth_context(request)
        if context is None:
            return web.json_response({"error": "operator session is required"}, status=401)
        request["operator_auth"] = context
        return None
    # Unknown mode — fail closed. settings.py validates at boot, so this is a
    # defence-in-depth check.
    return web.json_response({"error": "operator session is required"}, status=401)


def _request_auth_context(request: web.Request) -> OperatorAuthContext | None:
    cached = request.get("operator_auth")
    if isinstance(cached, OperatorAuthContext):
        return cached
    context = _optional_auth_context(request)
    if context is not None:
        request["operator_auth"] = context
    return context


def _require_auth_context(request: web.Request) -> OperatorAuthContext:
    context = _request_auth_context(request)
    if context is None:
        raise ValueError("operator session is required")
    return context


def _query_agent_ids(request: web.Request) -> list[str]:
    agent_ids = [value for value in request.query.getall("agent", []) if value]
    agent_id = request.query.get("agent_id")
    if agent_id:
        agent_ids.append(agent_id)
    return agent_ids


def _query_bool(request: web.Request, key: str) -> bool | None:
    if key not in request.query:
        return None
    raw = str(request.query.get(key, "")).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid {key}")


def _optional_bool(raw_value: str | None, *, name: str) -> bool | None:
    if raw_value is None or raw_value == "":
        return None
    raw = str(raw_value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid {name}")


def _service_unavailable(exc: RuntimeError) -> web.Response:
    return web.json_response({"error": str(exc)}, status=503)


@web.middleware
async def control_plane_auth_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    if request.path.startswith("/api/control-plane/"):
        if _is_public_control_plane_api_path(request.path):
            context = _optional_auth_context(request)
            if context is not None:
                request["operator_auth"] = context
            return await handler(request)
        response = _authorize_request(request)
        if response is not None:
            return response
    return await handler(request)


def _is_conflict_error(exc: Exception) -> bool:
    name = exc.__class__.__name__
    message = str(exc).lower()
    return (
        name in {"IntegrityError", "UniqueViolationError"}
        or "duplicate key" in message
        or "unique constraint" in message
    )


@web.middleware
async def control_plane_error_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    try:
        return await handler(request)
    except KeyError:
        return web.json_response({"error": "agent or asset not found"}, status=404)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except Exception as exc:
        if _is_conflict_error(exc):
            return web.json_response({"error": str(exc)}, status=409)
        raise


async def list_agents(request: web.Request) -> web.Response:
    return web.json_response({"items": _manager().list_agents()})


async def setup_landing(request: web.Request) -> web.Response:
    raise web.HTTPFound("/setup")


async def setup_page(request: web.Request) -> web.Response:
    return web.Response(text=render_setup_page(request), content_type="text/html")


async def onboarding_status(request: web.Request) -> web.Response:
    payload = dict(_manager().get_onboarding_status())
    payload.update(_auth_service().onboarding_payload())
    return web.json_response(payload)


async def onboarding_bootstrap(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "error": "onboarding_bootstrap_removed",
            "message": (
                "The combined onboarding bootstrap is no longer used. "
                "Create the owner account via /api/control-plane/auth/register-owner, "
                "then configure providers/agents/integrations from the dashboard."
            ),
        },
        status=410,
    )


def _extract_request_origin(request: web.Request) -> tuple[str | None, str | None]:
    """Return (remote_ip, forwarded_for) for bootstrap loopback checks."""
    return request.remote, request.headers.get("X-Forwarded-For")


async def auth_status(request: web.Request) -> web.Response:
    return web.json_response(_auth_service().auth_status(_request_auth_context(request)))


async def auth_bootstrap_exchange(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_auth_service().exchange_bootstrap_code(str(payload.get("code") or "")))


async def auth_register_owner(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    remote_ip, forwarded_for = _extract_request_origin(request)
    return web.json_response(
        _auth_service().register_owner(
            registration_token=str(payload.get("registration_token") or ""),
            bootstrap_code=str(payload.get("bootstrap_code") or ""),
            username=str(payload.get("username") or ""),
            email=str(payload.get("email") or ""),
            password=str(payload.get("password") or ""),
            display_name=str(payload.get("display_name") or ""),
            remote_ip=remote_ip,
            forwarded_for=forwarded_for,
        ),
        status=201,
    )


async def auth_password_recover(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(
        _auth_service().reset_password_with_recovery_code(
            identifier=str(payload.get("identifier") or ""),
            recovery_code=str(payload.get("recovery_code") or ""),
            new_password=str(payload.get("new_password") or ""),
        )
    )


async def auth_password_change(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(
        _auth_service().change_password(
            _require_auth_context(request),
            current_password=str(payload.get("current_password") or ""),
            new_password=str(payload.get("new_password") or ""),
        )
    )


async def auth_recovery_codes_summary(request: web.Request) -> web.Response:
    return web.json_response(_auth_service().recovery_codes_summary(_require_auth_context(request)))


async def auth_recovery_codes_regenerate(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(
        _auth_service().regenerate_recovery_codes(
            _require_auth_context(request),
            current_password=str(payload.get("current_password") or ""),
        ),
        status=201,
    )


async def auth_login(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(
        _auth_service().login(
            identifier=str(payload.get("identifier") or ""),
            password=str(payload.get("password") or ""),
        )
    )


async def auth_logout(request: web.Request) -> web.Response:
    auth_header = request.headers.get("Authorization", "").strip()
    token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""
    return web.json_response(_auth_service().logout(token))


async def auth_issue_bootstrap_code(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    context = _request_auth_context(request)
    return web.json_response(
        _auth_service().issue_bootstrap_code(
            label=str(payload.get("label") or "cli"),
            actor=context.user_id if context and context.user_id else context.display_name if context else None,
        ),
        status=201,
    )


async def auth_legacy_exchange(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_auth_service().exchange_legacy_token(str(payload.get("token") or "")))


async def auth_list_tokens(request: web.Request) -> web.Response:
    return web.json_response(_auth_service().list_personal_tokens(_require_auth_context(request)))


async def auth_create_token(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    raw_scopes = payload.get("scopes")
    scopes = [str(item).strip() for item in raw_scopes] if isinstance(raw_scopes, list) else None
    return web.json_response(
        _auth_service().issue_personal_token(
            _require_auth_context(request),
            token_name=str(payload.get("token_name") or payload.get("name") or "CLI token"),
            expires_in_days=int(payload.get("expires_in_days") or 0) or None,
            scopes=scopes,
        ),
        status=201,
    )


async def auth_delete_token(request: web.Request) -> web.Response:
    return web.json_response(
        _auth_service().revoke_personal_token(_require_auth_context(request), request.match_info["token_id"])
    )


async def auth_list_sessions(request: web.Request) -> web.Response:
    return web.json_response(_auth_service().list_sessions(_require_auth_context(request)))


async def auth_delete_session(request: web.Request) -> web.Response:
    return web.json_response(
        _auth_service().revoke_session(
            _require_auth_context(request),
            request.match_info["session_id"],
        )
    )


async def control_plane_openapi(request: web.Request) -> web.Response:
    return web.json_response(load_control_plane_openapi_spec())


async def create_agent(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().create_agent(payload), status=201)


async def get_agent(request: web.Request) -> web.Response:
    agent = _manager().get_agent(request.match_info["agent_id"])
    if agent is None:
        return web.json_response({"error": "agent not found"}, status=404)
    return web.json_response(agent)


async def patch_agent(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().update_agent(request.match_info["agent_id"], payload))


async def list_workspaces(request: web.Request) -> web.Response:
    return web.json_response(_manager().list_workspaces())


async def create_workspace(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().create_workspace(payload), status=201)


async def patch_workspace(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().update_workspace(request.match_info["workspace_id"], payload))


async def delete_workspace(request: web.Request) -> web.Response:
    _manager().delete_workspace(request.match_info["workspace_id"])
    return web.json_response({"ok": True})


async def create_squad(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(
        _manager().create_workspace_squad(request.match_info["workspace_id"], payload),
        status=201,
    )


async def patch_squad(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(
        _manager().update_workspace_squad(
            request.match_info["workspace_id"],
            request.match_info["squad_id"],
            payload,
        )
    )


async def get_workspace_spec(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_workspace_spec(request.match_info["workspace_id"]))


async def put_workspace_spec(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().update_workspace_spec(request.match_info["workspace_id"], payload))


async def get_squad_spec(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().get_squad_spec(
            request.match_info["workspace_id"],
            request.match_info["squad_id"],
        )
    )


async def put_squad_spec(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(
        _manager().update_squad_spec(
            request.match_info["workspace_id"],
            request.match_info["squad_id"],
            payload,
        )
    )


async def delete_squad(request: web.Request) -> web.Response:
    _manager().delete_workspace_squad(request.match_info["workspace_id"], request.match_info["squad_id"])
    return web.json_response({"ok": True})


async def delete_agent(request: web.Request) -> web.Response:
    _manager().archive_agent(request.match_info["agent_id"])
    return web.json_response({"ok": True})


async def list_dashboard_agent_summaries_route(request: web.Request) -> web.Response:
    try:
        items = list_dashboard_agent_summaries(_query_agent_ids(request) or None)
        catalog = {str(item["id"]): item for item in _manager().list_agents()}
        return web.json_response(
            [
                {
                    **item,
                    "agent": catalog.get(str(item.get("agentId") or "")),
                }
                for item in items
            ]
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def get_dashboard_agent_stats_route(request: web.Request) -> web.Response:
    try:
        payload = dict(_manager().get_dashboard_agent_summary(request.match_info["agent_id"]))
    except RuntimeError as exc:
        return _service_unavailable(exc)
    payload.pop("agent", None)
    return web.json_response(payload)


async def get_dashboard_agent_summary_route(request: web.Request) -> web.Response:
    try:
        return web.json_response(_manager().get_dashboard_agent_summary(request.match_info["agent_id"]))
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_agent_executions_route(request: web.Request) -> web.Response:
    try:
        limit = _bounded_int(request.query.get("limit"), name="limit", default=50)
        offset = _bounded_int(request.query.get("offset"), name="offset", default=0, minimum=0)
        return web.json_response(
            _manager().list_dashboard_executions(
                request.match_info["agent_id"],
                status=request.query.get("status") or None,
                search=request.query.get("search") or None,
                session_id=request.query.get("sessionId") or request.query.get("session_id") or None,
                limit=limit,
                offset=offset,
            )
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_executions_route(request: web.Request) -> web.Response:
    agent_ids = _query_agent_ids(request)
    if not agent_ids:
        agent_ids = [item["id"] for item in _manager().list_agents()]
    limit = _bounded_int(request.query.get("limit"), name="limit", default=50)
    offset = _bounded_int(request.query.get("offset"), name="offset", default=0, minimum=0)
    try:
        return web.json_response(
            list_dashboard_execution_summaries(
                agent_ids=agent_ids,
                status=request.query.get("status") or None,
                search=request.query.get("search") or None,
                session_id=request.query.get("sessionId") or None,
                limit=limit,
                offset=offset,
            )
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def get_dashboard_execution_detail_route(request: web.Request) -> web.Response:
    task_id = _bounded_int(request.match_info["task_id"], name="task_id", default=1)
    try:
        payload = _manager().get_dashboard_execution(request.match_info["agent_id"], task_id)
    except RuntimeError as exc:
        return _service_unavailable(exc)
    if payload is None:
        return web.json_response({"error": "execution not found"}, status=404)
    return web.json_response(payload)


async def get_dashboard_link_preview_route(request: web.Request) -> web.Response:
    raw_url = str(request.query.get("url") or "").strip()
    if not raw_url:
        return web.json_response({"error": "url is required"}, status=400)

    metadata = await inspect_url(raw_url)
    if isinstance(metadata, str):
        status = 400 if metadata.startswith("Error:") else 502
        return web.json_response({"error": metadata.removeprefix("Error: ").strip()}, status=status)

    preview = await fetch_link_metadata(metadata.final_url)
    parsed = urllib.parse.urlparse(metadata.final_url)
    return web.json_response(
        {
            "url": raw_url,
            "final_url": metadata.final_url,
            "domain": parsed.hostname or None,
            "status": metadata.status,
            "content_type": metadata.content_type or None,
            "content_length": metadata.content_length,
            "title": _clip_preview_text(preview.title, limit=180),
            "description": _clip_preview_text(preview.description, limit=320),
            "site_name": _clip_preview_text(preview.site_name, limit=120),
            "image_url": str(preview.thumbnail_url or "").strip() or None,
            "link_type": getattr(preview.link_type, "value", str(preview.link_type or "article")),
            "duration": str(preview.duration or "").strip() or None,
            "has_transcript": bool(preview.has_transcript),
        }
    )


async def list_dashboard_agent_sessions_route(request: web.Request) -> web.Response:
    try:
        limit = _bounded_int(request.query.get("limit"), name="limit", default=50)
        offset = _bounded_int(request.query.get("offset"), name="offset", default=0, minimum=0)
        return web.json_response(
            _manager().list_dashboard_sessions(
                request.match_info["agent_id"],
                limit=limit,
                offset=offset,
                search=request.query.get("search") or None,
            )
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_sessions_route(request: web.Request) -> web.Response:
    agent_ids = _query_agent_ids(request)
    if not agent_ids:
        agent_ids = [item["id"] for item in _manager().list_agents()]
    limit = _bounded_int(request.query.get("limit"), name="limit", default=50)
    offset = _bounded_int(request.query.get("offset"), name="offset", default=0, minimum=0)
    try:
        return web.json_response(
            _manager().list_dashboard_session_summaries(
                agent_ids=agent_ids,
                limit=limit,
                offset=offset,
                search=request.query.get("search") or None,
            )
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def get_dashboard_session_detail_route(request: web.Request) -> web.Response:
    try:
        limit_param = request.query.get("limit")
        limit = _bounded_int(limit_param, name="limit", default=40, minimum=1) if limit_param is not None else None
        payload = _manager().get_dashboard_session(
            request.match_info["agent_id"],
            request.match_info["session_id"],
            limit=limit,
            before=request.query.get("before") or None,
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)
    if payload is None:
        return web.json_response({"error": "session not found"}, status=404)
    return web.json_response(payload)


async def post_dashboard_session_message_route(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    try:
        result = _manager().send_dashboard_session_message(
            request.match_info["agent_id"],
            text=str(payload.get("text") or ""),
            session_id=str(payload.get("session_id") or "").strip() or None,
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)
    return web.json_response(result, status=202)


async def list_dashboard_session_approvals_route(request: web.Request) -> web.Response:
    from koda.services.approval_broker import list_pending_for_session

    agent_id = request.match_info["agent_id"]
    session_id = request.match_info.get("session_id")
    items = list_pending_for_session(agent_id=agent_id, session_id=session_id)
    return web.json_response({"items": items})


async def list_dashboard_agent_approvals_route(request: web.Request) -> web.Response:
    from koda.services.approval_broker import list_pending_for_session

    agent_id = request.match_info["agent_id"]
    items = list_pending_for_session(agent_id=agent_id, session_id=None)
    return web.json_response({"items": items})


async def list_skills_catalog_route(request: web.Request) -> web.Response:  # noqa: ARG001
    import re

    from koda.services.templates import _SKILL_TEMPLATES

    when_to_use_re = re.compile(r"<when_to_use>\s*(.*?)\s*</when_to_use>", re.DOTALL)
    items: list[dict[str, Any]] = []
    for name, content in sorted(_SKILL_TEMPLATES.items()):
        match = when_to_use_re.search(content)
        description = match.group(1).strip().split(". ")[0] if match else ""
        items.append(
            {
                "id": name,
                "title": name.replace("-", " ").replace("_", " "),
                "description": description,
                "category": "skill",
            }
        )
    return web.json_response({"items": items})


async def list_agent_tools_catalog_route(request: web.Request) -> web.Response:  # noqa: ARG001
    try:
        from koda.utils.approval import _OPS_COMMANDS, WRITE_CLASSIFIERS
    except ImportError:
        return web.json_response({"items": []})

    tool_descriptions = {
        "shell": "Execute shell commands in the agent workspace",
        "git": "Git operations (status, log, diff, commit, push)",
        "gh": "GitHub CLI operations (PRs, issues, releases)",
        "glab": "GitLab CLI operations",
        "docker": "Docker container operations",
        "pip": "Python package manager",
        "npm": "Node package manager",
        "gws": "Google Workspace (Gmail, Calendar, Drive, Sheets)",
        "jira": "Jira issue tracker",
        "confluence": "Confluence wiki",
        "http_request": "HTTP request (GET/POST/etc)",
        "cron": "Scheduled jobs",
        "write": "Write a file",
        "edit": "Edit a file",
        "rm": "Remove a file",
        "mkdir": "Create a directory",
        "cat": "Read a file",
        "search": "Search the web or docs",
        "fetch": "Fetch a URL",
        "curl": "HTTP request via curl",
        "browse": "Browser automation",
        "screenshot": "Capture a screenshot",
    }

    items = []
    for tool_id in sorted(set(_OPS_COMMANDS) | set(WRITE_CLASSIFIERS.keys())):
        items.append(
            {
                "id": tool_id,
                "title": tool_id,
                "description": tool_descriptions.get(tool_id, ""),
                "category": "tool",
            }
        )
    return web.json_response({"items": items})


async def post_dashboard_approval_route(request: web.Request) -> web.Response:
    from koda.services.approval_broker import resolve_approval

    payload = await _json_payload(request)
    approval_id = request.match_info["approval_id"]
    raw_decision = str(payload.get("decision") or "").strip()
    rationale = str(payload.get("rationale") or "").strip() or None
    if not raw_decision:
        return web.json_response({"error": "missing decision"}, status=400)
    try:
        summary = await resolve_approval(
            approval_id=approval_id,
            decision=raw_decision,
            rationale=rationale,
        )
    except KeyError:
        return web.json_response({"error": "approval not found"}, status=404)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response({"approval": summary})


async def list_dashboard_agent_dlq_route(request: web.Request) -> web.Response:
    try:
        limit = _bounded_int(request.query.get("limit"), name="limit", default=50)
        return web.json_response(
            _manager().list_dashboard_dlq(
                request.match_info["agent_id"],
                limit=limit,
                retry_eligible=_query_bool(request, "retryEligible"),
            )
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_dlq_route(request: web.Request) -> web.Response:
    agent_ids = _query_agent_ids(request)
    if not agent_ids:
        agent_ids = [item["id"] for item in _manager().list_agents()]
    limit = _bounded_int(request.query.get("limit"), name="limit", default=50)
    try:
        return web.json_response(
            list_dashboard_dlq(
                agent_ids=agent_ids,
                limit=limit,
                retry_eligible=_query_bool(request, "retryEligible"),
            )
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_costs_route(request: web.Request) -> web.Response:
    agent_ids = _query_agent_ids(request)
    if not agent_ids:
        agent_ids = [item["id"] for item in _manager().list_agents()]
    try:
        return web.json_response(
            get_dashboard_cost_insights(
                agent_ids=agent_ids,
                period=request.query.get("period", "30d"),
                group_by=request.query.get("groupBy", "auto"),
                model=request.query.get("model") or None,
                task_type=request.query.get("taskType") or None,
                from_date=request.query.get("from") or None,
                to_date=request.query.get("to") or None,
            )
        )
    except Exception as exc:
        return _service_unavailable(RuntimeError(str(exc)))


async def get_dashboard_agent_costs_route(request: web.Request) -> web.Response:
    try:
        days = _bounded_int(request.query.get("days"), name="days", default=30, maximum=3650)
        return web.json_response(_manager().get_dashboard_costs(request.match_info["agent_id"], days=days))
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_schedules_route(request: web.Request) -> web.Response:
    try:
        return web.json_response(list_dashboard_schedules(_query_agent_ids(request) or None))
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_agent_schedules_route(request: web.Request) -> web.Response:
    try:
        return web.json_response(_manager().list_dashboard_schedules(request.match_info["agent_id"]))
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_audit_route(request: web.Request) -> web.Response:
    try:
        if request.query.get("types") == "1":
            return web.json_response(_manager().list_dashboard_audit_types(request.match_info["agent_id"]))
        limit = _bounded_int(request.query.get("limit"), name="limit", default=50)
        offset = _bounded_int(request.query.get("offset"), name="offset", default=0, minimum=0)
        user_id_raw = request.query.get("userId") or request.query.get("user_id")
        user_id = int(user_id_raw) if user_id_raw else None
        return web.json_response(
            _manager().list_dashboard_audit(
                request.match_info["agent_id"],
                limit=limit,
                offset=offset,
                event_type=request.query.get("eventType") or request.query.get("event_type") or None,
                user_id=user_id,
            )
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def clone_agent(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().clone_agent(request.match_info["agent_id"], payload), status=201)


async def publish_agent(request: web.Request) -> web.Response:
    checks = _manager().publish_checks(request.match_info["agent_id"])
    if checks["errors"]:
        return web.json_response(
            {
                **checks,
                "error": "; ".join(str(item) for item in checks["errors"]),
            },
            status=400,
        )
    return web.json_response(_manager().publish_agent(request.match_info["agent_id"]))


async def activate_agent(request: web.Request) -> web.Response:
    return web.json_response(_manager().activate_agent(request.match_info["agent_id"]))


async def pause_agent(request: web.Request) -> web.Response:
    return web.json_response(_manager().pause_agent(request.match_info["agent_id"]))


async def get_global_defaults(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_global_defaults())


async def patch_global_defaults(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().patch_global_defaults(payload))


async def get_system_settings(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_system_settings())


async def put_system_settings(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().put_system_settings(payload))


async def oauth_relay_handler(request: web.Request) -> web.Response:
    """Proxy an OAuth callback from the host browser to the CLI subprocess inside Docker.

    The CLI starts a local HTTP server on a random port. The browser redirects to
    localhost:PORT which doesn't reach the container. This relay receives the callback
    on the control plane port (exposed) and forwards it to the CLI's internal server.
    """
    session_id = request.match_info["session_id"]

    from koda.services.provider_auth import clear_oauth_relay_target, get_oauth_relay_target

    target = get_oauth_relay_target(session_id)
    if not target:
        return web.Response(
            status=404,
            text="OAuth relay session not found or expired.",
            content_type="text/plain",
        )

    # Forward all query parameters to the internal callback
    internal_url = target
    if request.query_string:
        separator = "&" if "?" in internal_url else "?"
        internal_url = f"{internal_url}{separator}{request.query_string}"

    try:
        import aiohttp as aio

        async with (
            aio.ClientSession() as session,
            session.get(internal_url, timeout=aio.ClientTimeout(total=10)) as resp,
        ):
            body = await resp.text()
            clear_oauth_relay_target(session_id)
            # Return the CLI's response (usually HTML with a success message)
            return web.Response(
                status=resp.status,
                text=body,
                content_type=resp.content_type or "text/html",
            )
    except Exception as exc:
        return web.Response(
            status=502,
            text=f"Failed to reach CLI auth server: {exc}",
            content_type="text/plain",
        )


async def get_general_system_settings(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_general_system_settings())


async def put_general_system_settings(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    try:
        return web.json_response(_manager().put_general_system_settings(payload))
    except GeneralPayloadValidationError as exc:
        return web.json_response({"errors": exc.errors}, status=400)


async def get_provider_connection(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_provider_connection(request.match_info["provider_id"]))


async def put_provider_api_key_connection(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().put_provider_api_key_connection(request.match_info["provider_id"], payload))


async def put_provider_local_connection(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().put_provider_local_connection(request.match_info["provider_id"], payload))


async def start_provider_login(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().start_provider_login(request.match_info["provider_id"], payload), status=201)


async def get_provider_login_session(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().get_provider_login_session(
            request.match_info["provider_id"],
            request.match_info["session_id"],
        )
    )


async def submit_provider_login_code(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(
        _manager().submit_provider_login_code(
            request.match_info["provider_id"],
            request.match_info["session_id"],
            payload,
        )
    )


async def verify_provider_connection(request: web.Request) -> web.Response:
    return web.json_response(_manager().verify_provider_connection(request.match_info["provider_id"]))


async def get_integration_health(request: web.Request) -> web.Response:
    return web.json_response(_manager().verify_connection_default(f"core:{request.match_info['integration_id']}"))


async def disconnect_provider_connection(request: web.Request) -> web.Response:
    return web.json_response(_manager().disconnect_provider_connection(request.match_info["provider_id"]))


async def set_integration_system_enabled(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(
        _manager().set_integration_system_enabled(
            request.match_info["integration_id"],
            bool(payload.get("enabled")),
        )
    )


async def get_global_secret(request: web.Request) -> web.Response:
    secret = _manager().get_global_secret_asset(request.match_info["secret_key"])
    if secret is None:
        return web.json_response({"scope": "global", "secret_key": request.match_info["secret_key"], "preview": ""})
    return web.json_response(secret)


async def put_global_secret(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().upsert_global_secret_asset(request.match_info["secret_key"], payload))


async def delete_global_secret(request: web.Request) -> web.Response:
    _manager().delete_global_secret_asset(request.match_info["secret_key"])
    return web.json_response({"ok": True})


async def get_section(request: web.Request) -> web.Response:
    section = request.match_info["section"]
    if section not in AGENT_SECTIONS:
        return web.json_response({"error": "unknown section"}, status=404)
    return web.json_response(_manager().get_section(request.match_info["agent_id"], section))


async def put_section(request: web.Request) -> web.Response:
    section = request.match_info["section"]
    if section not in AGENT_SECTIONS:
        return web.json_response({"error": "unknown section"}, status=404)
    payload = await _json_payload(request)
    return web.json_response(_manager().put_section(request.match_info["agent_id"], section, payload))


async def get_document(request: web.Request) -> web.Response:
    kind = request.match_info["kind"]
    if kind not in DOCUMENT_KINDS:
        return web.json_response({"error": "unknown document kind"}, status=404)
    document = _manager().get_document(request.match_info["agent_id"], kind)
    if document is None:
        return web.json_response({"agent_id": request.match_info["agent_id"], "kind": kind, "content_md": ""})
    return web.json_response(document)


async def upsert_document(request: web.Request) -> web.Response:
    kind = request.match_info["kind"]
    if kind not in DOCUMENT_KINDS:
        return web.json_response({"error": "unknown document kind"}, status=404)
    payload = await _json_payload(request)
    return web.json_response(_manager().upsert_document(request.match_info["agent_id"], kind, payload))


async def delete_document(request: web.Request) -> web.Response:
    kind = request.match_info["kind"]
    if kind not in DOCUMENT_KINDS:
        return web.json_response({"error": "unknown document kind"}, status=404)
    _manager().delete_document(request.match_info["agent_id"], kind)
    return web.json_response({"ok": True})


async def list_knowledge_assets(request: web.Request) -> web.Response:
    return web.json_response({"items": _manager().list_knowledge_assets(request.match_info["agent_id"])})


async def create_knowledge_asset(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().upsert_knowledge_asset(request.match_info["agent_id"], payload), status=201)


async def update_knowledge_asset(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    payload.setdefault("id", int(request.match_info["asset_id"]))
    return web.json_response(_manager().upsert_knowledge_asset(request.match_info["agent_id"], payload))


async def delete_knowledge_asset(request: web.Request) -> web.Response:
    _manager().delete_knowledge_asset(request.match_info["agent_id"], int(request.match_info["asset_id"]))
    return web.json_response({"ok": True})


async def list_templates(request: web.Request) -> web.Response:
    return web.json_response({"items": _manager().list_template_assets(request.match_info["agent_id"])})


async def create_template(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().upsert_template_asset(request.match_info["agent_id"], payload), status=201)


async def update_template(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    payload.setdefault("id", int(request.match_info["asset_id"]))
    return web.json_response(_manager().upsert_template_asset(request.match_info["agent_id"], payload))


async def delete_template(request: web.Request) -> web.Response:
    _manager().delete_template_asset(request.match_info["agent_id"], int(request.match_info["asset_id"]))
    return web.json_response({"ok": True})


async def list_skills(request: web.Request) -> web.Response:
    return web.json_response({"items": _manager().list_skill_assets(request.match_info["agent_id"])})


async def create_skill(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().upsert_skill_asset(request.match_info["agent_id"], payload), status=201)


async def update_skill(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    payload.setdefault("id", int(request.match_info["asset_id"]))
    return web.json_response(_manager().upsert_skill_asset(request.match_info["agent_id"], payload))


async def delete_skill(request: web.Request) -> web.Response:
    _manager().delete_skill_asset(request.match_info["agent_id"], int(request.match_info["asset_id"]))
    return web.json_response({"ok": True})


async def get_secret(request: web.Request) -> web.Response:
    scope = request.query.get("scope", "agent")
    include_value = request.query.get("include_value", "").lower() == "true"
    agent_id = request.match_info["agent_id"]
    secret_key = request.match_info["secret_key"]
    secret = _manager().get_secret_asset(agent_id, secret_key, scope=scope)
    if secret is None:
        return web.json_response(
            {
                "scope": scope,
                "secret_key": secret_key,
                "preview": "",
            }
        )
    if include_value:
        # get_decrypted_secret_value always uses the agent scope_id; this is
        # safe because get_secret_asset above already rejects non-agent scopes.
        decrypted = _manager().get_decrypted_secret_value(agent_id, secret_key)
        if decrypted is not None:
            secret = {**secret, "value": decrypted}
    return web.json_response(secret)


async def put_secret(request: web.Request) -> web.Response:
    scope = request.query.get("scope", "agent")
    payload = await _json_payload(request)
    return web.json_response(
        _manager().upsert_secret_asset(
            request.match_info["agent_id"],
            request.match_info["secret_key"],
            payload,
            scope=scope,
        )
    )


async def get_telegram_bot_info(request: web.Request) -> web.Response:
    """Return Telegram bot info (username, name) by decrypting the AGENT_TOKEN and calling getMe."""

    agent_id = request.match_info["agent_id"]
    manager = _manager()
    token = manager.get_decrypted_secret_value(agent_id, "AGENT_TOKEN")
    if not token:
        return web.json_response({"ok": False, "error": "no_token"}, status=404)

    bot_info: dict[str, Any] = {"ok": False}
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/getMe")
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
            if data.get("ok") and data.get("result"):
                bot_info = {
                    "ok": True,
                    "bot_username": data["result"].get("username", ""),
                    "bot_name": data["result"].get("first_name", ""),
                }
    except Exception:
        return web.json_response({"ok": False, "error": "telegram_unreachable"}, status=502)

    if not bot_info.get("ok"):
        return web.json_response({"ok": False, "error": "telegram_unreachable"}, status=502)

    # Resolve allowed user IDs to Telegram usernames
    allowed_raw = manager.get_decrypted_secret_value(agent_id, "ALLOWED_USER_IDS") or ""
    user_ids = [uid.strip() for uid in allowed_raw.split(",") if uid.strip()]
    allowed_users: list[dict[str, str]] = []
    for uid in user_ids:
        user_entry: dict[str, str] = {"id": uid, "name": ""}
        try:
            chat_req = urllib.request.Request(f"https://api.telegram.org/bot{token}/getChat?chat_id={uid}")
            with urllib.request.urlopen(chat_req, timeout=5) as chat_resp:  # noqa: S310
                chat_data = json.loads(chat_resp.read().decode())
                if chat_data.get("ok") and chat_data.get("result"):
                    result = chat_data["result"]
                    parts = [result.get("first_name", ""), result.get("last_name", "")]
                    display = " ".join(p for p in parts if p) or uid
                    username = result.get("username", "")
                    user_entry["name"] = f"@{username}" if username else display
        except Exception:
            pass
        allowed_users.append(user_entry)

    bot_info["allowed_users"] = allowed_users
    return web.json_response(bot_info)


async def delete_secret(request: web.Request) -> web.Response:
    scope = request.query.get("scope", "agent")
    _manager().delete_secret_asset(request.match_info["agent_id"], request.match_info["secret_key"], scope=scope)
    return web.json_response({"ok": True})


async def get_runtime_access(request: web.Request) -> web.Response:
    capability = str(request.query.get("capability") or "read").strip().lower() or "read"
    if capability not in {"read", "mutate", "attach"}:
        raise ValueError("invalid capability")
    include_sensitive = _query_bool(request, "include_sensitive") or False
    return web.json_response(
        _manager().get_runtime_access(
            request.match_info["agent_id"],
            capability=capability,
            include_sensitive=include_sensitive,
        )
    )


async def get_core_providers(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_core_providers())


async def get_core_tools(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_core_tools())


async def get_core_policies(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_core_policies())


async def get_core_capabilities(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_core_capabilities())


async def get_agent_spec(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_agent_spec(request.match_info["agent_id"]))


async def put_agent_spec(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().put_agent_spec(request.match_info["agent_id"], payload))


async def get_compiled_prompt(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_compiled_prompt(request.match_info["agent_id"]))


async def validate_agent(request: web.Request) -> web.Response:
    return web.json_response(_manager().validate_agent(request.match_info["agent_id"]))


async def publish_checks(request: web.Request) -> web.Response:
    checks = _manager().publish_checks(request.match_info["agent_id"])
    return web.json_response(checks, status=200 if checks["ok"] else 400)


async def get_tool_policy(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_tool_policy(request.match_info["agent_id"]))


async def put_tool_policy(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().put_tool_policy(request.match_info["agent_id"], payload))


async def get_model_policy(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_model_policy(request.match_info["agent_id"]))


async def put_model_policy(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().put_model_policy(request.match_info["agent_id"], payload))


async def get_autonomy_policy(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_autonomy_policy(request.match_info["agent_id"]))


async def put_autonomy_policy(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().put_autonomy_policy(request.match_info["agent_id"], payload))


async def get_execution_policy(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_execution_policy(request.match_info["agent_id"]))


async def put_execution_policy(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().put_execution_policy(request.match_info["agent_id"], payload))


async def get_execution_policy_catalog(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_execution_policy_catalog(request.match_info["agent_id"]))


async def evaluate_execution_policy(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().evaluate_execution_policy(request.match_info["agent_id"], payload))


async def list_knowledge_candidates(request: web.Request) -> web.Response:
    review_status = request.query.get("review_status", "pending")
    limit = int(request.query.get("limit", "20"))
    return web.json_response(
        {
            "items": _manager().list_knowledge_candidates(
                request.match_info["agent_id"],
                review_status=review_status,
                limit=limit,
            )
        }
    )


async def approve_knowledge_candidate(request: web.Request) -> web.Response:
    reviewer = request.query.get("reviewer", "control-plane")
    promoted_id = _manager().approve_knowledge_candidate(
        request.match_info["agent_id"],
        int(request.match_info["candidate_id"]),
        reviewer=reviewer,
    )
    if promoted_id is None:
        return web.json_response({"error": "candidate not found or no longer approvable"}, status=404)
    return web.json_response({"ok": True, "promoted_id": promoted_id})


async def reject_knowledge_candidate(request: web.Request) -> web.Response:
    reviewer = request.query.get("reviewer", "control-plane")
    ok = _manager().reject_knowledge_candidate(
        request.match_info["agent_id"],
        int(request.match_info["candidate_id"]),
        reviewer=reviewer,
    )
    if not ok:
        return web.json_response({"error": "candidate not found"}, status=404)
    return web.json_response({"ok": True})


async def list_runbooks(request: web.Request) -> web.Response:
    limit = int(request.query.get("limit", "50"))
    status = request.query.get("status")
    return web.json_response(
        {
            "items": _manager().list_runbooks(
                request.match_info["agent_id"],
                status=status,
                limit=limit,
            )
        }
    )


async def revalidate_runbook(request: web.Request) -> web.Response:
    reviewer = request.query.get("reviewer", "control-plane")
    ok = _manager().revalidate_runbook(
        request.match_info["agent_id"],
        int(request.match_info["runbook_id"]),
        reviewer=reviewer,
    )
    if not ok:
        return web.json_response({"error": "runbook not found"}, status=404)
    return web.json_response({"ok": True})


async def list_retrieval_traces(request: web.Request) -> web.Response:
    limit = _bounded_int(request.query.get("limit"), name="limit", default=50)
    task_id_raw = request.query.get("task_id")
    strategy = request.query.get("strategy")
    experiment_key = request.query.get("experiment_key")
    trace_role = request.query.get("trace_role")
    task_id = _bounded_int(task_id_raw, name="task_id", default=1, minimum=1) if task_id_raw else None
    return web.json_response(
        {
            "items": await _manager().list_retrieval_traces_async(
                request.match_info["agent_id"],
                task_id=task_id,
                strategy=strategy,
                experiment_key=experiment_key,
                trace_role=trace_role,
                limit=limit,
            )
        }
    )


async def list_answer_traces(request: web.Request) -> web.Response:
    limit = _bounded_int(request.query.get("limit"), name="limit", default=50)
    task_id_raw = request.query.get("task_id")
    task_id = _bounded_int(task_id_raw, name="task_id", default=1, minimum=1) if task_id_raw else None
    return web.json_response(
        {
            "items": await _manager().list_answer_traces_async(
                request.match_info["agent_id"], task_id=task_id, limit=limit
            )
        }
    )


async def get_retrieval_trace(request: web.Request) -> web.Response:
    trace = await _manager().get_retrieval_trace_async(
        request.match_info["agent_id"],
        int(request.match_info["trace_id"]),
    )
    if trace is None:
        return web.json_response({"error": "trace not found"}, status=404)
    return web.json_response(trace)


async def get_answer_trace(request: web.Request) -> web.Response:
    trace = await _manager().get_answer_trace_async(
        request.match_info["agent_id"],
        int(request.match_info["answer_trace_id"]),
    )
    if trace is None:
        return web.json_response({"error": "answer trace not found"}, status=404)
    return web.json_response(trace)


async def list_knowledge_graph(request: web.Request) -> web.Response:
    limit = _bounded_int(request.query.get("limit"), name="limit", default=200, maximum=2000)
    entity_type = request.query.get("entity_type")
    return web.json_response(
        await _manager().list_knowledge_graph_async(
            request.match_info["agent_id"], entity_type=entity_type, limit=limit
        )
    )


async def list_evaluation_cases(request: web.Request) -> web.Response:
    limit = _bounded_int(request.query.get("limit"), name="limit", default=100)
    return web.json_response({"items": _manager().list_evaluation_cases(request.match_info["agent_id"], limit=limit)})


async def seed_evaluation_cases(request: web.Request) -> web.Response:
    limit = _bounded_int(request.query.get("limit"), name="limit", default=50)
    return web.json_response(_manager().seed_evaluation_cases(request.match_info["agent_id"], limit=limit))


async def patch_evaluation_case(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(
        _manager().update_evaluation_case(
            request.match_info["agent_id"],
            request.match_info["case_key"],
            payload,
        )
    )


async def list_evaluation_runs(request: web.Request) -> web.Response:
    limit = _bounded_int(request.query.get("limit"), name="limit", default=100)
    case_key = request.query.get("case_key")
    strategy = request.query.get("strategy")
    return web.json_response(
        {
            "items": _manager().list_evaluation_runs(
                request.match_info["agent_id"],
                case_key=case_key,
                strategy=strategy,
                limit=limit,
            )
        }
    )


async def get_dashboard_memory_map(request: web.Request) -> web.Response:
    user_id_raw = request.query.get("userId") or request.query.get("user_id")
    try:
        include_inactive_value = request.query.get("includeInactive") or request.query.get("include_inactive") or ""
        return web.json_response(
            get_memory_map_payload(
                request.match_info["agent_id"],
                user_id=int(user_id_raw) if user_id_raw else None,
                session_id=request.query.get("sessionId") or request.query.get("session_id") or None,
                days=_bounded_int(request.query.get("days"), name="days", default=30, maximum=3650),
                include_inactive=include_inactive_value.lower() in {"1", "true", "yes", "on"},
                limit=_bounded_int(request.query.get("limit"), name="limit", default=160, maximum=1200),
            )
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_memory_curation(request: web.Request) -> web.Response:
    try:
        return web.json_response(
            list_memory_curation_payload(
                request.match_info["agent_id"],
                search=request.query.get("search") or request.query.get("q") or request.query.get("query") or None,
                status=request.query.get("status") or request.query.get("memory_status") or None,
                memory_type=request.query.get("type") or request.query.get("memory_type") or None,
                kind=request.query.get("kind") or None,
                limit=_bounded_int(request.query.get("limit"), name="limit", default=200, maximum=2000),
                offset=_bounded_int(request.query.get("offset"), name="offset", default=0, minimum=0, maximum=100000),
            )
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def get_dashboard_memory_curation_detail(request: web.Request) -> web.Response:
    try:
        detail = get_memory_curation_detail_payload(
            request.match_info["agent_id"],
            int(request.match_info["memory_id"]),
        )
    except KeyError:
        return web.json_response({"error": "memory not found"}, status=404)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except RuntimeError as exc:
        return _service_unavailable(exc)
    return web.json_response(detail)


async def get_dashboard_memory_curation_cluster(request: web.Request) -> web.Response:
    try:
        detail = get_memory_curation_cluster_payload(
            request.match_info["agent_id"],
            request.match_info["cluster_id"],
        )
    except KeyError:
        return web.json_response({"error": "cluster not found"}, status=404)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except RuntimeError as exc:
        return _service_unavailable(exc)
    return web.json_response(detail)


async def post_dashboard_memory_curation_action(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    try:
        result = apply_memory_curation_action(request.match_info["agent_id"], payload)
    except KeyError as exc:
        target = str(exc).strip("'") or "memory target not found"
        return web.json_response({"error": target}, status=404)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except RuntimeError as exc:
        return _service_unavailable(exc)
    return web.json_response({"ok": True, **result})


async def get_elevenlabs_voices(request: web.Request) -> web.Response:
    import asyncio

    language = request.rel_url.query.get("language", "")
    manager = _manager()
    voices = await asyncio.get_event_loop().run_in_executor(
        None, lambda: manager.get_elevenlabs_voice_catalog(language=language)
    )
    return web.json_response(voices)


async def get_ollama_models(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(None, manager.get_ollama_model_catalog)
    return web.json_response(payload)


async def get_kokoro_voices(request: web.Request) -> web.Response:
    import asyncio

    language = request.rel_url.query.get("language", "")
    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: manager.get_kokoro_voice_catalog(language=language),
    )
    return web.json_response(payload)


async def start_kokoro_voice_download(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: manager.start_kokoro_voice_download(request.match_info["voice_id"]),
    )
    return web.json_response(payload, status=202)


async def get_provider_download_job(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: manager.get_provider_download_job(
            request.match_info["provider_id"],
            request.match_info["job_id"],
        ),
    )
    return web.json_response(payload)


# ------------------------------------------------------------------ #
#  MCP Server Catalog / Agent Connections / Tool Policies              #
# ------------------------------------------------------------------ #


async def list_mcp_catalog(request: web.Request) -> web.Response:
    return web.json_response(_manager().list_mcp_catalog())


async def get_mcp_catalog_entry(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_mcp_catalog_entry(request.match_info["server_key"]))


async def put_mcp_catalog_entry(request: web.Request) -> web.Response:
    payload = await request.json()
    return web.json_response(_manager().upsert_mcp_catalog_entry(request.match_info["server_key"], payload))


async def delete_mcp_catalog_entry(request: web.Request) -> web.Response:
    return web.json_response(_manager().delete_mcp_catalog_entry(request.match_info["server_key"]))


async def list_mcp_connections(request: web.Request) -> web.Response:
    return web.json_response(_manager().list_mcp_agent_connections(request.match_info["agent_id"]))


def _mcp_connection_key(request: web.Request) -> str:
    raw = str(request.match_info.get("server_key") or request.match_info["connection_key"])
    return raw.removeprefix("mcp:") if raw.startswith("mcp:") else raw


async def list_connection_catalog(request: web.Request) -> web.Response:
    return web.json_response(_manager().list_connection_catalog())


async def list_connection_defaults_route(request: web.Request) -> web.Response:
    return web.json_response(_manager().list_connection_defaults())


async def get_connection_default_route(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_connection_default(request.match_info["connection_key"]))


async def put_connection_default_route(request: web.Request) -> web.Response:
    payload = await request.json()
    return web.json_response(
        _manager().put_connection_default(
            request.match_info["connection_key"],
            payload,
        )
    )


async def delete_connection_default_route(request: web.Request) -> web.Response:
    return web.json_response(_manager().delete_connection_default(request.match_info["connection_key"]))


async def verify_connection_default_route(request: web.Request) -> web.Response:
    return web.json_response(_manager().verify_connection_default(request.match_info["connection_key"]))


async def list_agent_connections_route(request: web.Request) -> web.Response:
    return web.json_response(_manager().list_agent_connections(request.match_info["agent_id"]))


async def get_agent_connection_route(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().get_agent_connection(request.match_info["agent_id"], request.match_info["connection_key"])
    )


async def put_agent_connection_route(request: web.Request) -> web.Response:
    payload = await request.json()
    return web.json_response(
        _manager().put_agent_connection(
            request.match_info["agent_id"],
            request.match_info["connection_key"],
            payload,
        )
    )


async def delete_agent_connection_route(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().delete_agent_connection(request.match_info["agent_id"], request.match_info["connection_key"])
    )


async def verify_agent_connection_route(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().verify_agent_connection(request.match_info["agent_id"], request.match_info["connection_key"])
    )


async def get_agent_connection_tools_route(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().get_agent_connection_tools(request.match_info["agent_id"], request.match_info["connection_key"])
    )


async def discover_agent_connection_tools_route(request: web.Request) -> web.Response:
    try:
        payload = _manager().discover_agent_connection_tools(
            request.match_info["agent_id"],
            request.match_info["connection_key"],
        )
    except ValueError as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=400)
    return web.json_response(payload)


async def import_agent_connection_default_route(request: web.Request) -> web.Response:
    try:
        payload = _manager().import_agent_connection_default(
            request.match_info["agent_id"],
            request.match_info["connection_key"],
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(payload)


async def list_agent_connection_tool_policies_route(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().list_agent_connection_tool_policies(
            request.match_info["agent_id"],
            request.match_info["connection_key"],
        )
    )


async def put_agent_connection_tool_policy_route(request: web.Request) -> web.Response:
    payload = await request.json()
    policy = str(payload.get("policy", "auto"))
    try:
        result = _manager().upsert_agent_connection_tool_policy(
            request.match_info["agent_id"],
            request.match_info["connection_key"],
            request.match_info["tool_name"],
            policy,
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(result)


async def delete_agent_connection_tool_policy_route(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().delete_agent_connection_tool_policy(
            request.match_info["agent_id"],
            request.match_info["connection_key"],
            request.match_info["tool_name"],
        )
    )


async def get_mcp_connection(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().get_mcp_agent_connection(request.match_info["agent_id"], _mcp_connection_key(request))
    )


async def put_mcp_connection(request: web.Request) -> web.Response:
    payload = await request.json()
    return web.json_response(
        _manager().upsert_mcp_agent_connection(request.match_info["agent_id"], _mcp_connection_key(request), payload)
    )


async def delete_mcp_connection(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().delete_mcp_agent_connection(request.match_info["agent_id"], _mcp_connection_key(request))
    )


async def test_mcp_connection_route(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().test_mcp_connection(request.match_info["agent_id"], _mcp_connection_key(request))
    )


async def discover_mcp_tools_route(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().discover_mcp_tools(request.match_info["agent_id"], _mcp_connection_key(request))
    )


async def list_mcp_tool_policies(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().list_mcp_tool_policies(request.match_info["agent_id"], _mcp_connection_key(request))
    )


async def put_mcp_tool_policy(request: web.Request) -> web.Response:
    payload = await request.json()
    policy = str(payload.get("policy", "auto"))
    return web.json_response(
        _manager().upsert_mcp_tool_policy(
            request.match_info["agent_id"],
            _mcp_connection_key(request),
            request.match_info["tool_name"],
            policy,
        )
    )


async def delete_mcp_tool_policy(request: web.Request) -> web.Response:
    return web.json_response(
        _manager().delete_mcp_tool_policy(
            request.match_info["agent_id"],
            _mcp_connection_key(request),
            request.match_info["tool_name"],
        )
    )


# ------------------------------------------------------------------ #
#  MCP OAuth                                                           #
# ------------------------------------------------------------------ #


async def start_oauth_flow_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    payload = await request.json()
    from koda.services.mcp_oauth import start_oauth_flow

    frontend_callback_uri = str(payload.get("frontend_callback_uri") or payload.get("redirect_uri") or "")
    redirect_uri = str(payload.get("redirect_uri") or frontend_callback_uri)
    result = await start_oauth_flow(
        agent_id,
        server_key,
        frontend_callback_uri=frontend_callback_uri,
        redirect_uri=redirect_uri,
    )
    return web.json_response(result, status=201)


async def handle_oauth_callback_route(request: web.Request) -> web.Response:
    state = request.query.get("state", "")
    code = request.query.get("code", "")
    error = request.query.get("error", "")
    from koda.services.mcp_oauth import handle_oauth_callback

    result = await handle_oauth_callback(state, code, error=error or None)
    wants_json = request.query.get("mode") == "json" or "application/json" in request.headers.get("Accept", "")
    if wants_json:
        status = 200 if result.get("success") else 400
        return web.json_response(result, status=status)

    frontend_target = str(
        result.get("frontend_callback_uri") or request.query.get("frontend_callback_uri") or ""
    ).strip()
    if not frontend_target:
        return web.json_response(result, status=200 if result.get("success") else 400)
    if result.get("success"):
        raise web.HTTPFound(
            f"{frontend_target}?status=success&server_key={result['server_key']}&agent_id={result['agent_id']}"
        )
    raise web.HTTPFound(f"{frontend_target}?status=error&error={result.get('error', 'token_exchange_failed')}")


async def refresh_oauth_token_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    from koda.services.mcp_oauth import refresh_oauth_token

    result = await refresh_oauth_token(agent_id, server_key)
    return web.json_response(result)


async def revoke_oauth_token_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    from koda.services.mcp_oauth import revoke_oauth_token

    result = await revoke_oauth_token(agent_id, server_key)
    return web.json_response(result)


async def get_oauth_status_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    return web.json_response(_manager().get_oauth_token_status(agent_id, server_key))


def setup_control_plane_routes(app: web.Application) -> None:
    # OAuth relay for CLI-based provider auth inside Docker
    app.router.add_get("/api/control-plane/oauth-relay/{session_id}", oauth_relay_handler)

    app.router.add_get("/", setup_landing)
    app.router.add_get("/setup", setup_page)
    app.router.add_get("/openapi/control-plane.json", control_plane_openapi)
    app.router.add_get("/api/control-plane/onboarding/status", onboarding_status)
    app.router.add_post("/api/control-plane/onboarding/bootstrap", onboarding_bootstrap)
    app.router.add_get("/api/control-plane/auth/status", auth_status)
    app.router.add_post("/api/control-plane/auth/bootstrap/exchange", auth_bootstrap_exchange)
    app.router.add_post("/api/control-plane/auth/bootstrap/codes", auth_issue_bootstrap_code)
    app.router.add_post("/api/control-plane/auth/register-owner", auth_register_owner)
    app.router.add_post("/api/control-plane/auth/login", auth_login)
    app.router.add_post("/api/control-plane/auth/logout", auth_logout)
    app.router.add_post("/api/control-plane/auth/legacy/exchange", auth_legacy_exchange)
    app.router.add_post("/api/control-plane/auth/password/recover", auth_password_recover)
    app.router.add_post("/api/control-plane/auth/password/change", auth_password_change)
    app.router.add_get("/api/control-plane/auth/recovery-codes", auth_recovery_codes_summary)
    app.router.add_post("/api/control-plane/auth/recovery-codes/regenerate", auth_recovery_codes_regenerate)
    app.router.add_get("/api/control-plane/auth/tokens", auth_list_tokens)
    app.router.add_post("/api/control-plane/auth/tokens", auth_create_token)
    app.router.add_delete("/api/control-plane/auth/tokens/{token_id}", auth_delete_token)
    app.router.add_get("/api/control-plane/auth/sessions", auth_list_sessions)
    app.router.add_delete("/api/control-plane/auth/sessions/{session_id}", auth_delete_session)
    app.router.add_get("/api/control-plane/core/providers", get_core_providers)
    app.router.add_get("/api/control-plane/core/tools", get_core_tools)
    app.router.add_post("/api/control-plane/integrations/{integration_id}/system", set_integration_system_enabled)
    app.router.add_get("/api/control-plane/integrations/{integration_id}/health", get_integration_health)
    app.router.add_get("/api/control-plane/core/policies", get_core_policies)
    app.router.add_get("/api/control-plane/core/capabilities", get_core_capabilities)
    app.router.add_get("/api/control-plane/dashboard/agents/summary", list_dashboard_agent_summaries_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/summary", get_dashboard_agent_summary_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/stats", get_dashboard_agent_stats_route)
    app.router.add_get("/api/control-plane/dashboard/executions", list_dashboard_executions_route)
    app.router.add_get("/api/control-plane/dashboard/link-preview", get_dashboard_link_preview_route)
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/executions", list_dashboard_agent_executions_route
    )
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/executions/{task_id}",
        get_dashboard_execution_detail_route,
    )
    app.router.add_get("/api/control-plane/dashboard/sessions", list_dashboard_sessions_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/sessions", list_dashboard_agent_sessions_route)
    app.router.add_post(
        "/api/control-plane/dashboard/agents/{agent_id}/sessions/messages",
        post_dashboard_session_message_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/sessions/{session_id}",
        get_dashboard_session_detail_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/sessions/{session_id}/approvals",
        list_dashboard_session_approvals_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/approvals",
        list_dashboard_agent_approvals_route,
    )
    app.router.add_post(
        "/api/control-plane/dashboard/agents/{agent_id}/approvals/{approval_id}",
        post_dashboard_approval_route,
    )
    app.router.add_get(
        "/api/control-plane/skills",
        list_skills_catalog_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/tools",
        list_agent_tools_catalog_route,
    )
    app.router.add_get("/api/control-plane/dashboard/dlq", list_dashboard_dlq_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/dlq", list_dashboard_agent_dlq_route)
    app.router.add_get("/api/control-plane/dashboard/costs", list_dashboard_costs_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/costs", get_dashboard_agent_costs_route)
    app.router.add_get("/api/control-plane/dashboard/schedules", list_dashboard_schedules_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/schedules", list_dashboard_agent_schedules_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/cron", list_dashboard_agent_schedules_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/audit", list_dashboard_audit_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/memory-map", get_dashboard_memory_map)
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/memory-curation",
        list_dashboard_memory_curation,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/memory-curation/{memory_id}",
        get_dashboard_memory_curation_detail,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/memory-curation/clusters/{cluster_id}",
        get_dashboard_memory_curation_cluster,
    )
    app.router.add_post(
        "/api/control-plane/dashboard/agents/{agent_id}/memory-curation/actions",
        post_dashboard_memory_curation_action,
    )

    app.router.add_get("/api/control-plane/agents", list_agents)
    app.router.add_post("/api/control-plane/agents", create_agent)
    app.router.add_get("/api/control-plane/agents/{agent_id}", get_agent)
    app.router.add_patch("/api/control-plane/agents/{agent_id}", patch_agent)
    app.router.add_delete("/api/control-plane/agents/{agent_id}", delete_agent)
    app.router.add_get("/api/control-plane/workspaces", list_workspaces)
    app.router.add_post("/api/control-plane/workspaces", create_workspace)
    app.router.add_patch("/api/control-plane/workspaces/{workspace_id}", patch_workspace)
    app.router.add_delete("/api/control-plane/workspaces/{workspace_id}", delete_workspace)
    app.router.add_post("/api/control-plane/workspaces/{workspace_id}/squads", create_squad)
    app.router.add_patch("/api/control-plane/workspaces/{workspace_id}/squads/{squad_id}", patch_squad)
    app.router.add_delete("/api/control-plane/workspaces/{workspace_id}/squads/{squad_id}", delete_squad)
    app.router.add_get("/api/control-plane/workspaces/{workspace_id}/spec", get_workspace_spec)
    app.router.add_put("/api/control-plane/workspaces/{workspace_id}/spec", put_workspace_spec)
    app.router.add_get("/api/control-plane/workspaces/{workspace_id}/squads/{squad_id}/spec", get_squad_spec)
    app.router.add_put("/api/control-plane/workspaces/{workspace_id}/squads/{squad_id}/spec", put_squad_spec)
    app.router.add_post("/api/control-plane/agents/{agent_id}/clone", clone_agent)
    app.router.add_post("/api/control-plane/agents/{agent_id}/publish", publish_agent)
    app.router.add_post("/api/control-plane/agents/{agent_id}/activate", activate_agent)
    app.router.add_post("/api/control-plane/agents/{agent_id}/pause", pause_agent)
    app.router.add_get("/api/control-plane/agents/{agent_id}/runtime-access", get_runtime_access)
    app.router.add_get("/api/control-plane/agents/{agent_id}/agent-spec", get_agent_spec)
    app.router.add_put("/api/control-plane/agents/{agent_id}/agent-spec", put_agent_spec)
    app.router.add_get("/api/control-plane/agents/{agent_id}/compiled-prompt", get_compiled_prompt)
    app.router.add_post("/api/control-plane/agents/{agent_id}/validate", validate_agent)
    app.router.add_post("/api/control-plane/agents/{agent_id}/publish-checks", publish_checks)
    app.router.add_get("/api/control-plane/agents/{agent_id}/tool-policy", get_tool_policy)
    app.router.add_put("/api/control-plane/agents/{agent_id}/tool-policy", put_tool_policy)
    app.router.add_get("/api/control-plane/agents/{agent_id}/model-policy", get_model_policy)
    app.router.add_put("/api/control-plane/agents/{agent_id}/model-policy", put_model_policy)
    app.router.add_get("/api/control-plane/agents/{agent_id}/autonomy-policy", get_autonomy_policy)
    app.router.add_put("/api/control-plane/agents/{agent_id}/autonomy-policy", put_autonomy_policy)
    app.router.add_get("/api/control-plane/agents/{agent_id}/execution-policy", get_execution_policy)
    app.router.add_put("/api/control-plane/agents/{agent_id}/execution-policy", put_execution_policy)
    app.router.add_get("/api/control-plane/agents/{agent_id}/policy-catalog", get_execution_policy_catalog)
    app.router.add_post("/api/control-plane/agents/{agent_id}/execution-policy/evaluate", evaluate_execution_policy)
    app.router.add_get("/api/control-plane/agents/{agent_id}/knowledge-candidates", list_knowledge_candidates)
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/knowledge-candidates/{candidate_id}/approve",
        approve_knowledge_candidate,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/knowledge-candidates/{candidate_id}/reject",
        reject_knowledge_candidate,
    )
    app.router.add_get("/api/control-plane/agents/{agent_id}/runbooks", list_runbooks)
    app.router.add_post("/api/control-plane/agents/{agent_id}/runbooks/{runbook_id}/revalidate", revalidate_runbook)
    app.router.add_get("/api/control-plane/agents/{agent_id}/retrieval-traces", list_retrieval_traces)
    app.router.add_get("/api/control-plane/agents/{agent_id}/retrieval-traces/{trace_id}", get_retrieval_trace)
    app.router.add_get("/api/control-plane/agents/{agent_id}/answer-traces", list_answer_traces)
    app.router.add_get("/api/control-plane/agents/{agent_id}/answer-traces/{answer_trace_id}", get_answer_trace)
    app.router.add_get("/api/control-plane/agents/{agent_id}/knowledge-graph", list_knowledge_graph)
    app.router.add_get("/api/control-plane/agents/{agent_id}/evaluation-cases", list_evaluation_cases)
    app.router.add_post("/api/control-plane/agents/{agent_id}/evaluation-cases/seed", seed_evaluation_cases)
    app.router.add_patch("/api/control-plane/agents/{agent_id}/evaluation-cases/{case_key}", patch_evaluation_case)
    app.router.add_get("/api/control-plane/agents/{agent_id}/knowledge-evals/runs", list_evaluation_runs)

    app.router.add_get("/api/control-plane/global-defaults", get_global_defaults)
    app.router.add_patch("/api/control-plane/global-defaults", patch_global_defaults)
    app.router.add_get("/api/control-plane/system-settings", get_system_settings)
    app.router.add_put("/api/control-plane/system-settings", put_system_settings)
    app.router.add_get("/api/control-plane/system-settings/general", get_general_system_settings)
    app.router.add_put("/api/control-plane/system-settings/general", put_general_system_settings)
    app.router.add_get("/api/control-plane/providers/{provider_id}/connection", get_provider_connection)
    app.router.add_put(
        "/api/control-plane/providers/{provider_id}/connection/api-key",
        put_provider_api_key_connection,
    )
    app.router.add_put(
        "/api/control-plane/providers/{provider_id}/connection/local",
        put_provider_local_connection,
    )
    app.router.add_post(
        "/api/control-plane/providers/{provider_id}/connection/login/start",
        start_provider_login,
    )
    app.router.add_get(
        "/api/control-plane/providers/{provider_id}/connection/login/{session_id}",
        get_provider_login_session,
    )
    app.router.add_post(
        "/api/control-plane/providers/{provider_id}/connection/login/{session_id}/code",
        submit_provider_login_code,
    )
    app.router.add_post(
        "/api/control-plane/providers/{provider_id}/connection/verify",
        verify_provider_connection,
    )
    app.router.add_post(
        "/api/control-plane/providers/{provider_id}/connection/disconnect",
        disconnect_provider_connection,
    )
    app.router.add_get("/api/control-plane/providers/elevenlabs/voices", get_elevenlabs_voices)
    app.router.add_get("/api/control-plane/providers/kokoro/voices", get_kokoro_voices)
    app.router.add_post(
        "/api/control-plane/providers/kokoro/voices/{voice_id}/download",
        start_kokoro_voice_download,
    )
    app.router.add_get(
        "/api/control-plane/providers/{provider_id}/downloads/{job_id}",
        get_provider_download_job,
    )
    app.router.add_get("/api/control-plane/providers/ollama/models", get_ollama_models)
    app.router.add_get("/api/control-plane/system-settings/secrets/{secret_key}", get_global_secret)
    app.router.add_put("/api/control-plane/system-settings/secrets/{secret_key}", put_global_secret)
    app.router.add_delete("/api/control-plane/system-settings/secrets/{secret_key}", delete_global_secret)

    app.router.add_get("/api/control-plane/agents/{agent_id}/sections/{section}", get_section)
    app.router.add_put("/api/control-plane/agents/{agent_id}/sections/{section}", put_section)

    app.router.add_get("/api/control-plane/agents/{agent_id}/documents/{kind}", get_document)
    app.router.add_post("/api/control-plane/agents/{agent_id}/documents/{kind}", upsert_document)
    app.router.add_put("/api/control-plane/agents/{agent_id}/documents/{kind}", upsert_document)
    app.router.add_delete("/api/control-plane/agents/{agent_id}/documents/{kind}", delete_document)

    app.router.add_get("/api/control-plane/agents/{agent_id}/knowledge-assets", list_knowledge_assets)
    app.router.add_post("/api/control-plane/agents/{agent_id}/knowledge-assets", create_knowledge_asset)
    app.router.add_put("/api/control-plane/agents/{agent_id}/knowledge-assets/{asset_id}", update_knowledge_asset)
    app.router.add_delete("/api/control-plane/agents/{agent_id}/knowledge-assets/{asset_id}", delete_knowledge_asset)

    app.router.add_get("/api/control-plane/agents/{agent_id}/templates", list_templates)
    app.router.add_post("/api/control-plane/agents/{agent_id}/templates", create_template)
    app.router.add_put("/api/control-plane/agents/{agent_id}/templates/{asset_id}", update_template)
    app.router.add_delete("/api/control-plane/agents/{agent_id}/templates/{asset_id}", delete_template)

    app.router.add_get("/api/control-plane/agents/{agent_id}/skills", list_skills)
    app.router.add_post("/api/control-plane/agents/{agent_id}/skills", create_skill)
    app.router.add_put("/api/control-plane/agents/{agent_id}/skills/{asset_id}", update_skill)
    app.router.add_delete("/api/control-plane/agents/{agent_id}/skills/{asset_id}", delete_skill)

    app.router.add_get("/api/control-plane/agents/{agent_id}/secrets/{secret_key}", get_secret)
    app.router.add_put("/api/control-plane/agents/{agent_id}/secrets/{secret_key}", put_secret)
    app.router.add_delete("/api/control-plane/agents/{agent_id}/secrets/{secret_key}", delete_secret)
    app.router.add_get("/api/control-plane/agents/{agent_id}/telegram/bot-info", get_telegram_bot_info)

    # --- Unified Agent Connections ---
    app.router.add_get("/api/control-plane/connections/catalog", list_connection_catalog)
    app.router.add_get("/api/control-plane/connections/defaults", list_connection_defaults_route)
    app.router.add_get(
        "/api/control-plane/connections/defaults/{connection_key}",
        get_connection_default_route,
    )
    app.router.add_put(
        "/api/control-plane/connections/defaults/{connection_key}",
        put_connection_default_route,
    )
    app.router.add_delete(
        "/api/control-plane/connections/defaults/{connection_key}",
        delete_connection_default_route,
    )
    app.router.add_post(
        "/api/control-plane/connections/defaults/{connection_key}/verify",
        verify_connection_default_route,
    )
    app.router.add_get("/api/control-plane/agents/{agent_id}/connections", list_agent_connections_route)
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}",
        get_agent_connection_route,
    )
    app.router.add_put(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}",
        put_agent_connection_route,
    )
    app.router.add_delete(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}",
        delete_agent_connection_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/verify",
        verify_agent_connection_route,
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/tools",
        get_agent_connection_tools_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/discover-tools",
        discover_agent_connection_tools_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/import-default",
        import_agent_connection_default_route,
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/policies",
        list_agent_connection_tool_policies_route,
    )
    app.router.add_put(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/policies/{tool_name}",
        put_agent_connection_tool_policy_route,
    )
    app.router.add_delete(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/policies/{tool_name}",
        delete_agent_connection_tool_policy_route,
    )

    # --- MCP Server Catalog ---
    app.router.add_get("/api/control-plane/mcp/catalog", list_mcp_catalog)
    app.router.add_get("/api/control-plane/mcp/catalog/{server_key}", get_mcp_catalog_entry)
    app.router.add_put("/api/control-plane/mcp/catalog/{server_key}", put_mcp_catalog_entry)
    app.router.add_delete("/api/control-plane/mcp/catalog/{server_key}", delete_mcp_catalog_entry)

    # --- MCP Agent Connections ---
    app.router.add_get("/api/control-plane/agents/{agent_id}/mcp/connections", list_mcp_connections)
    app.router.add_get("/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}", get_mcp_connection)
    app.router.add_put("/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}", put_mcp_connection)
    app.router.add_delete("/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}", delete_mcp_connection)
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/test", test_mcp_connection_route
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/discover", discover_mcp_tools_route
    )

    # --- MCP Tool Policies ---
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/policies", list_mcp_tool_policies
    )
    app.router.add_put(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/policies/{tool_name}", put_mcp_tool_policy
    )
    app.router.add_delete(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/policies/{tool_name}", delete_mcp_tool_policy
    )

    # --- MCP OAuth ---
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/oauth/start", start_oauth_flow_route
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/oauth/start", start_oauth_flow_route
    )
    app.router.add_get("/api/control-plane/mcp/oauth/callback", handle_oauth_callback_route)
    app.router.add_get("/api/control-plane/connections/oauth/callback", handle_oauth_callback_route)
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/oauth/refresh", refresh_oauth_token_route
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/oauth/refresh", refresh_oauth_token_route
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/oauth/revoke", revoke_oauth_token_route
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/oauth/revoke", revoke_oauth_token_route
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/oauth/status", get_oauth_status_route
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/oauth/status", get_oauth_status_route
    )
