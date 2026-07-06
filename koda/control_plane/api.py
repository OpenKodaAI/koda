"""aiohttp handlers for the control-plane API."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import hashlib
import json
import mimetypes
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from aiohttp import ClientConnectionResetError, ContentTypeError, web
from aiohttp.multipart import BodyPartReader

from koda.logging_config import get_logger
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
    DOCUMENT_KINDS,
)

log = get_logger(__name__)

_CLIENT_DISCONNECT_ERRORS = (
    BrokenPipeError,
    ClientConnectionResetError,
    ConnectionAbortedError,
    ConnectionResetError,
)
_MAX_DASHBOARD_PAGE_OFFSET = 100_000


def _manager() -> Any:
    return get_control_plane_manager()


def _auth_service() -> OperatorAuthService:
    return get_operator_auth_service()


def _request_transport_open(request: web.Request) -> bool:
    transport = request.transport
    return transport is not None and not transport.is_closing()


async def _write_stream_or_closed(response: web.StreamResponse, data: bytes) -> bool:
    try:
        await response.write(data)
    except _CLIENT_DISCONNECT_ERRORS:
        return False
    return True


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


def _wants_paginated_response(request: web.Request) -> bool:
    raw = str(request.query.get("paged") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _paginated_list_payload(items: list[Any], *, limit: int, offset: int) -> dict[str, Any]:
    page_items = items[:limit]
    has_more = len(items) > limit
    return {
        "items": page_items,
        "page": {
            "limit": limit,
            "offset": offset,
            "returned": len(page_items),
            "next_offset": offset + len(page_items) if has_more else None,
            "has_more": has_more,
            "total": None,
        },
    }


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
    "/api/control-plane/auth/password/recover",
)


def _is_public_control_plane_api_path(path: str) -> bool:
    return any(path == candidate or path.startswith(f"{candidate}/") for candidate in _PUBLIC_CONTROL_PLANE_API_PATHS)


def _optional_auth_context(request: web.Request) -> OperatorAuthContext | None:
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.startswith("Bearer "):
        return None
    request_token = auth_header.removeprefix("Bearer ").strip()
    if not request_token:
        return None
    return _auth_service().resolve_bearer_token(request_token)


def _authorize_request(request: web.Request) -> web.Response | None:
    context = _optional_auth_context(request)
    if context is None:
        return web.json_response({"error": "operator session is required"}, status=401)
    request["operator_auth"] = context
    return None


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


async def _dashboard_squad_thread_access(
    request: web.Request,
    thread_id: str,
    *,
    require_write: bool = False,
    break_glass_reason: str | None = None,
) -> tuple[Any | None, web.Response | None]:
    """Authorize an operator dashboard request against a squad thread.

    The dashboard authenticates a human operator, not an agent runtime. This
    helper makes that actor explicit before any thread message/task/artifact
    data is read.
    """
    from koda.squads import (
        SquadAccessError,
        SquadPrincipal,
        SquadResourceNotFoundError,
        get_squad_access_service,
        get_squad_thread_store,
    )

    thread_store = get_squad_thread_store()
    access_service = get_squad_access_service()
    if thread_store is None or access_service is None:
        return None, _service_unavailable(RuntimeError("squad access service unavailable"))
    thread = await thread_store.get_thread(thread_id)
    if thread is None:
        return None, web.json_response({"error": "thread not found"}, status=404)
    auth = _require_auth_context(request)
    principal = SquadPrincipal.workspace_operator(
        auth.username or "operator",
        workspace_id=thread.workspace_id,
        break_glass_reason=break_glass_reason,
    )
    try:
        access = await access_service.require_thread_access_for_principal(
            thread_id=thread_id,
            principal=principal,
            require_write=require_write,
        )
    except SquadResourceNotFoundError:
        return None, web.json_response({"error": "thread not found"}, status=404)
    except SquadAccessError as exc:
        return None, web.json_response({"error": str(exc)}, status=403)
    return access, None


async def _dashboard_squad_task_access(
    request: web.Request,
    task_id: str,
    *,
    require_write: bool = False,
) -> tuple[tuple[Any, dict[str, Any]] | None, web.Response | None]:
    from koda.squads import (
        SquadAccessError,
        SquadPrincipal,
        SquadResourceNotFoundError,
        get_squad_access_service,
        get_squad_task_store,
    )

    task_store = get_squad_task_store()
    access_service = get_squad_access_service()
    if task_store is None or access_service is None:
        return None, _service_unavailable(RuntimeError("squad access service unavailable"))
    task = await task_store.get_task(task_id)
    if task is None:
        return None, web.json_response({"error": "task not found"}, status=404)
    auth = _require_auth_context(request)
    principal = SquadPrincipal.workspace_operator(
        auth.username or "operator",
        workspace_id=(
            await access_service.require_thread_access_for_principal(
                thread_id=task.thread_id,
                principal=SquadPrincipal.system(),
            )
        ).thread.workspace_id,
    )
    try:
        access_task = await access_service.require_task_access_for_principal(
            task_id=task_id,
            principal=principal,
            require_write=require_write,
        )
    except SquadResourceNotFoundError:
        return None, web.json_response({"error": "task not found"}, status=404)
    except SquadAccessError as exc:
        return None, web.json_response({"error": str(exc)}, status=403)
    return access_task, None


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


def _download_filename(value: object, fallback: str) -> str:
    filename = Path(str(value or fallback)).name.strip() or fallback
    return filename.replace("\r", "").replace("\n", "").replace('"', "")


def _download_content_disposition(filename: str) -> str:
    ascii_filename = filename.encode("ascii", errors="ignore").decode("ascii").strip() or "artifact"
    return f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{urllib.parse.quote(filename)}"


def _is_path_under_any_root(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except (OSError, ValueError):
            continue
    return False


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


def _parse_optional_int(value: str | None, *, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be greater than or equal to 0")
    return parsed


def _matches_agent_search(agent: dict[str, Any], query: str) -> bool:
    appearance = agent.get("appearance")
    organization = agent.get("organization")
    values = [
        agent.get("id"),
        agent.get("display_name"),
    ]
    if isinstance(appearance, dict):
        values.append(appearance.get("label"))
    if isinstance(organization, dict):
        values.extend(
            [
                organization.get("workspace_id"),
                organization.get("workspace_name"),
                organization.get("squad_id"),
                organization.get("squad_name"),
            ]
        )
    haystack = " ".join(str(value) for value in values if value)
    return query in haystack.lower()


async def list_agents(request: web.Request) -> web.Response:
    items = _manager().list_agents()
    raw_query = (request.query.get("q") or request.query.get("search") or "").strip()
    if raw_query:
        query = raw_query.lower()
        items = [item for item in items if _matches_agent_search(item, query)]

    total = len(items)
    offset = _parse_optional_int(request.query.get("offset"), name="offset") or 0
    requested_limit = _parse_optional_int(request.query.get("limit"), name="limit")
    if requested_limit is None:
        page = items[offset:] if offset else items
        limit = len(page)
    else:
        limit = min(requested_limit, 100)
        page = items[offset : offset + limit]

    return web.json_response(
        {
            "items": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(page) < total,
        }
    )


async def setup_landing(request: web.Request) -> web.Response:
    raise web.HTTPFound("/setup")


async def setup_page(request: web.Request) -> web.Response:
    return web.Response(text=render_setup_page(request), content_type="text/html")


async def onboarding_status(request: web.Request) -> web.Response:
    # This endpoint is a *health snapshot* polled by the CLI, setup wizard
    # and release smoke. A transient failure (seed race, lazy provider row,
    # storage not yet reachable) should degrade the payload but keep a 2xx
    # — fail-closed with 4xx/5xx here makes ``koda install --headless``
    # abort mid-bootstrap instead of letting the caller re-poll.
    try:
        payload = dict(_manager().get_onboarding_status())
        payload.update(_auth_service().onboarding_payload())
        return web.json_response(payload)
    except Exception as exc:
        log.warning(
            "onboarding_status_degraded",
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
        return web.json_response(
            {
                "status": "degraded",
                "error": "onboarding_status_failed",
                "message": f"{type(exc).__name__}: {exc}",
                "ready": False,
                "providers": [],
                "agents": [],
                "storage": {"database": {"ready": False}, "object_storage": {"ready": False}},
                "system": {},
            }
        )


async def onboarding_readiness(request: web.Request) -> web.Response:
    try:
        return web.json_response(_manager().get_onboarding_readiness())
    except Exception as exc:
        log.warning("onboarding_readiness_degraded", error_type=type(exc).__name__, error=str(exc), exc_info=True)
        return web.json_response(
            {
                "schema_version": "onboarding_readiness.v1",
                "status": "failed",
                "checks": [],
                "summary": {"passed": 0, "warning": 0, "failed": 1, "pending": 0},
                "error": {
                    "code": "onboarding.readiness_failed",
                    "category": "internal",
                    "message": f"{type(exc).__name__}: {exc}",
                    "retryable": True,
                    "user_action": "Retry readiness or run the setup doctor.",
                },
            }
        )


async def onboarding_first_task(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    payload = await _json_payload(request)
    try:
        return web.json_response(_manager().create_onboarding_first_task(payload), status=201)
    except ValueError as exc:
        return web.json_response(
            {
                "error": {
                    "code": "onboarding.first_task_invalid",
                    "category": "validation",
                    "message": str(exc),
                    "retryable": True,
                    "user_action": "Select an active agent and try again.",
                }
            },
            status=400,
        )
    except Exception as exc:
        return web.json_response(
            {
                "error": {
                    "code": "onboarding.first_task_failed",
                    "category": "dependency_unavailable",
                    "message": str(exc),
                    "retryable": True,
                    "user_action": "Start the runtime or inspect runtime readiness.",
                }
            },
            status=503,
        )


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


async def auth_update_profile(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(
        _auth_service().update_profile(
            _require_auth_context(request),
            display_name=str(payload.get("display_name") or ""),
        )
    )


async def _read_profile_photo_payload(request: web.Request) -> bytes | None:
    content_type = (request.content_type or "").lower()
    if content_type.startswith("multipart/"):
        from aiohttp.multipart import BodyPartReader

        try:
            reader = await request.multipart()
        except Exception as exc:
            raise ValueError(f"invalid multipart payload: {exc}") from exc
        async for part in reader:
            if not isinstance(part, BodyPartReader):
                continue
            if part.name in {"photo", "file"}:
                return await part.read(decode=False)
        return None
    return await request.read()


async def auth_upload_profile_photo(request: web.Request) -> web.Response:
    from .operator_profile_photos import InvalidProfilePhotoError, ProfilePhotoTooLargeError

    raw = await _read_profile_photo_payload(request)
    if not raw:
        return web.json_response({"error": "no image payload"}, status=400)
    try:
        payload = _auth_service().set_profile_photo(_require_auth_context(request), raw=raw)
    except ProfilePhotoTooLargeError as exc:
        return web.json_response({"error": str(exc)}, status=413)
    except InvalidProfilePhotoError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(payload, status=201)


async def auth_get_profile_photo(request: web.Request) -> web.StreamResponse:
    requested_hash = str(request.query.get("v") or "").strip()
    try:
        data, content_hash = _auth_service().get_profile_photo(
            _require_auth_context(request),
            requested_hash=requested_hash,
        )
    except FileNotFoundError:
        return web.json_response({"error": "profile photo not found"}, status=404)

    etag = f'"{content_hash}"'
    if request.headers.get("If-None-Match", "").strip() == etag:
        return web.Response(status=304, headers={"ETag": etag})

    return web.Response(
        body=data,
        content_type="image/jpeg",
        headers={
            "Content-Length": str(len(data)),
            "ETag": etag,
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


async def auth_delete_profile_photo(request: web.Request) -> web.Response:
    return web.json_response(_auth_service().delete_profile_photo(_require_auth_context(request)))


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


async def list_workspace_directory_roots(request: web.Request) -> web.Response:
    return web.json_response(_manager().list_workspace_directory_roots())


async def list_workspace_directory(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().list_workspace_directory(payload))


async def scan_workspace_directory_route(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().scan_workspace_directory(payload))


async def import_workspace_from_directory_route(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().import_workspace_from_directory(payload), status=201)


async def patch_workspace(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().update_workspace(request.match_info["workspace_id"], payload))


async def delete_workspace(request: web.Request) -> web.Response:
    _manager().delete_workspace(request.match_info["workspace_id"])
    return web.json_response({"ok": True})


async def rescan_workspace_route(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().rescan_workspace(request.match_info["workspace_id"], payload))


async def import_workspace_config_route(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().import_workspace_config(request.match_info["workspace_id"], payload))


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
    removed = _manager().delete_agent(request.match_info["agent_id"])
    return web.json_response({"ok": True, "deleted": removed})


async def list_dashboard_squads_overview_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    workspace_id = (request.query.get("workspace_id") or "").strip() or None
    from koda.squads import list_squad_overviews_default

    try:
        overviews = await list_squad_overviews_default(workspace_id=workspace_id)
    except Exception as exc:
        return _service_unavailable(RuntimeError(str(exc)))
    if overviews is None:
        return web.json_response({"items": [], "count": 0, "available": False})
    items = []
    for ov in overviews:
        items.append(
            {
                "squadId": ov.squad_id,
                "workspaceId": ov.workspace_id,
                "coordinatorAgentId": ov.coordinator_agent_id,
                "threadCounts": ov.thread_counts,
                "taskCounts": ov.task_counts,
                "memberCount": ov.member_count,
                "lastActiveAt": ov.last_active_at.isoformat() if ov.last_active_at else None,
                "totalCostUsd": str(ov.total_cost_usd),
            }
        )
    return web.json_response({"items": items, "count": len(items), "available": True})


async def stream_dashboard_squad_thread_events_route(request: web.Request) -> web.StreamResponse:
    if (resp := _authorize_request(request)) is not None:
        return resp
    thread_id = request.match_info["thread_id"]
    _access, access_resp = await _dashboard_squad_thread_access(request, thread_id)
    if access_resp is not None:
        return access_resp

    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA  # noqa: F401  - parity with siblings

    if not POSTGRES_URL:
        return web.json_response(
            {"error": "POSTGRES_URL is not configured"},
            status=503,
        )
    from koda.squads import get_squad_event_hub

    hub = get_squad_event_hub()
    if hub is None:
        return web.json_response({"error": "squad event hub unavailable"}, status=503)

    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
    try:
        await response.prepare(request)
    except _CLIENT_DISCONNECT_ERRORS:
        return response
    loop = asyncio.get_running_loop()
    queue = await hub.subscribe(thread_id, maxsize=64)
    try:
        # Initial hello so the client unblocks readyState=open quickly.
        if not await _write_stream_or_closed(response, b": connected\n\n"):
            return response
        last_heartbeat = loop.time()
        while _request_transport_open(request):
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
            except TimeoutError:
                if loop.time() - last_heartbeat > 14:
                    if not await _write_stream_or_closed(response, b": ping\n\n"):
                        break
                    last_heartbeat = loop.time()
                continue
            event_type = str(event.get("event_type") or "update")
            payload_bytes = (f"event: {event_type}\ndata: {json.dumps(event)}\n\n").encode()
            if not await _write_stream_or_closed(response, payload_bytes):
                break
    except asyncio.CancelledError:
        pass
    finally:
        hub.unsubscribe(thread_id, queue)
        with contextlib.suppress(Exception, *_CLIENT_DISCONNECT_ERRORS):
            await response.write_eof()
    return response


async def _watch_dashboard_squad_delivery_synthesis(
    *,
    thread_id: str,
    parent_message_id: str,
    coordinator_agent_id: str,
    application: Any | None,
) -> None:
    try:
        from koda.squads import dispatch_squad_turn, get_squad_task_store, get_squad_thread_store

        thread_store = get_squad_thread_store()
        task_store = get_squad_task_store()
        if thread_store is None or task_store is None:
            return
        thread = await thread_store.get_thread(thread_id)
        if thread is None or not coordinator_agent_id:
            return
        for attempt in range(90):
            open_tasks = await task_store.list_tasks(
                thread_id=thread_id,
                status=["pending", "claimed", "in_progress", "blocked"],
                limit=1,
            )
            if not open_tasks:
                break
            await asyncio.sleep(2.0 if attempt > 0 else 1.0)
        else:
            await thread_store.post_thread_message(
                thread_id=thread_id,
                from_agent="system",
                content="[synthesis_blocked] open squad tasks did not close before watcher timeout",
                message_type="system_event",
                metadata={
                    "event_type": "synthesis_blocked",
                    "parent_message_id": parent_message_id,
                    "coordinator_agent_id": coordinator_agent_id,
                },
            )
            return

        synthesis_idempotency_key = f"squad_synthesis:{thread_id}:{parent_message_id}:{coordinator_agent_id}"
        history = await thread_store.thread_history(thread_id=thread_id, limit=160)
        for message in history:
            raw_metadata = message.get("metadata")
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            if metadata.get("idempotency_key") == synthesis_idempotency_key:
                return

        visible_results: list[str] = []
        confirmed_results: list[str] = []
        for message in reversed(history):
            if message.get("type") != "task_result":
                continue
            raw_metadata = message.get("metadata")
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            if metadata.get("parent_message_id") != parent_message_id:
                continue
            task_id = str(metadata.get("squad_task_id") or "").strip()
            if not task_id:
                continue
            agent = str(message.get("from") or "agent").strip() or "agent"
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            visible_results.append(f"{agent} / {task_id}:\n{content[:1500]}")
            first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
            if first_line:
                confirmed_results.append(f"- {agent} / {task_id}: {first_line[:500]}")
        if not visible_results:
            return

        confirmed_results_block = "\n".join(confirmed_results) or "- Nenhum resultado textual confirmado."
        visible_results_block = "\n\n".join(visible_results)
        synthesis_query = (
            "Todos os task_result abertos deste ciclo já foram recebidos. "
            "Sintetize a entrega final para o usuário usando obrigatoriamente todos os resultados visíveis abaixo. "
            "Não use apenas o último resultado e declare divergências ou lacunas se houver. "
            "Preserve literalmente marcadores, IDs, labels de aceite e tokens de verificação presentes nos resultados; "
            "não os traduza, normalize ou parafraseie. "
            "Formato obrigatório da resposta final: comece com a seção 'Resultados confirmados:' e copie "
            "literalmente cada linha confirmada abaixo antes da síntese profissional.\n\n"
            f"Resultados confirmados:\n{confirmed_results_block}\n\n"
            f"Resultados visíveis deste ciclo:\n{visible_results_block}"
        )
        await dispatch_squad_turn(
            target_agent_id=coordinator_agent_id,
            thread=thread,
            thread_store=thread_store,
            query_text=synthesis_query,
            parent_message_id=parent_message_id,
            metadata={
                "from_agent": "squad_delivery_watcher",
                "source": "dashboard_delivery_watcher",
                "delivery_intent": "final_synthesis",
                "idempotency_key": synthesis_idempotency_key,
                "parent_message_id": parent_message_id,
            },
            application=application,
            user_id=int(thread.owner_user_id or 0),
            chat_id=int(thread.telegram_chat_id or 0),
            delegation_chain=["squad_delivery_watcher"],
            delegation_request_id=synthesis_idempotency_key,
            delegation_origin_agent_id="squad_delivery_watcher",
            telegram_message_thread_id=thread.telegram_message_thread_id,
        )
    except Exception:
        log.exception(
            "dashboard_squad_delivery_synthesis_watch_failed",
            thread_id=thread_id,
            parent_message_id=parent_message_id,
        )


async def post_dashboard_squad_thread_message_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    thread_id = request.match_info["thread_id"]
    try:
        payload = await _json_payload(request)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    content = (payload.get("content") or "").strip() if isinstance(payload.get("content"), str) else ""
    if not content:
        return web.json_response({"error": "content is required"}, status=400)
    access, access_resp = await _dashboard_squad_thread_access(request, thread_id, require_write=True)
    if access_resp is not None:
        return access_resp
    if access is None:
        return web.json_response({"error": "thread access unavailable"}, status=503)
    if access.thread.status != "open":
        return web.json_response({"error": f"thread is {access.thread.status}"}, status=409)
    raw_from = payload.get("from_agent")
    ctx = _request_auth_context(request)
    from_agent = f"operator:{ctx.username}" if ctx is not None else "operator"
    raw_meta = payload.get("metadata")
    metadata: dict[str, Any] = dict(raw_meta) if isinstance(raw_meta, dict) else {}
    metadata["via"] = "web_dashboard"
    metadata["actor_type"] = "operator"
    if isinstance(raw_from, str) and raw_from.strip() and raw_from.strip() != from_agent:
        metadata["requested_from_agent"] = raw_from.strip()
    raw_targets = payload.get("targetAgentIds", payload.get("target_agent_ids"))
    target_agent_ids: list[str] = []
    if isinstance(raw_targets, list):
        seen_targets: set[str] = set()
        for item in raw_targets:
            agent_id = str(item or "").strip()
            key = agent_id.lower()
            if not agent_id or key in seen_targets:
                continue
            seen_targets.add(key)
            target_agent_ids.append(agent_id)
    if len(target_agent_ids) > 8:
        return web.json_response({"error": "targetAgentIds is limited to 8 agents"}, status=400)
    reply_to_message_id = payload.get("replyToMessageId", payload.get("reply_to_message_id"))
    reply_to_ref: str | None = None
    if reply_to_message_id is not None:
        from koda.squads import message_ref

        reply_to_ref = message_ref(reply_to_message_id)
        if reply_to_ref is None:
            return web.json_response(
                {
                    "error": {
                        "code": "reply.parent_not_found",
                        "message": "replyToMessageId is invalid.",
                    }
                },
                status=400,
            )
        metadata["in_reply_to"] = reply_to_ref
        metadata["reply_to_message_id"] = reply_to_ref
    raw_reply_kind = payload.get("replyKind", payload.get("reply_kind"))
    reply_kind = str(raw_reply_kind or ("agent_request" if target_agent_ids else "user_input")).strip()
    metadata["reply_kind"] = reply_kind
    metadata["reply_contract_version"] = "thread_reply.v1"
    raw_reply_target = payload.get("replyTargetAgentId", payload.get("reply_to_agent_id"))
    if not target_agent_ids and isinstance(raw_reply_target, str) and raw_reply_target.strip():
        target_agent_ids = [raw_reply_target.strip()]
    deadline_value = payload.get("requiresResponseBy", payload.get("requires_response_by"))
    deadline: datetime | None = None
    if isinstance(deadline_value, str) and deadline_value.strip():
        try:
            deadline = datetime.fromisoformat(deadline_value.strip().replace("Z", "+00:00"))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
        except ValueError:
            return web.json_response(
                {
                    "error": {
                        "code": "reply.policy_denied",
                        "message": "requiresResponseBy must be an ISO timestamp.",
                    }
                },
                status=400,
            )
        metadata["requires_response_by"] = deadline.isoformat()

    from koda.squads import get_squad_thread_store, sync_thread_participants_from_squad

    store = get_squad_thread_store()
    if store is None:
        return _service_unavailable(RuntimeError("squad thread store unavailable"))
    synced_participants: list[Any] | None = None
    try:
        synced_participants = await sync_thread_participants_from_squad(store, thread=access.thread)
    except Exception:
        log.exception("dashboard_squad_participant_sync_failed", thread_id=thread_id)
    if target_agent_ids:
        participants_for_validation = synced_participants or await store.list_participants(thread_id=thread_id)
        active_participants = {p.agent_id for p in participants_for_validation if p.left_at is None and not p.paused}
        if access.thread.coordinator_agent_id:
            active_participants.add(access.thread.coordinator_agent_id)
        invalid_targets = [agent_id for agent_id in target_agent_ids if agent_id not in active_participants]
        if invalid_targets:
            return web.json_response(
                {
                    "error": {
                        "code": "reply.target_not_participant",
                        "message": f"Target agent is not an active participant: {', '.join(invalid_targets)}.",
                    }
                },
                status=400,
            )
    try:
        message_id = await store.post_thread_message(
            thread_id=thread_id,
            from_agent=from_agent,
            content=content,
            message_type="user_input",
            metadata=metadata,
            to_agent_ids=target_agent_ids,
            in_reply_to=reply_to_ref,
            requires_response_by=deadline,
            payload={
                "text": content,
                "reply_kind": reply_kind,
                "target_agent_ids": target_agent_ids,
                "reply_to_message_id": reply_to_ref,
            },
        )
    except KeyError:
        return web.json_response({"error": "thread not found"}, status=404)
    except (ValueError, RuntimeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    reply_obligations: list[dict[str, Any]] = []
    if target_agent_ids:
        try:
            from koda.squads import ThreadReplyError, get_thread_reply_service

            reply_service = get_thread_reply_service(store)
            if reply_service is None:
                raise ThreadReplyError("reply.policy_denied", "Thread reply service is unavailable.")
            obligations = await reply_service.create_obligations(
                thread_id=thread_id,
                source_message_id=message_id,
                target_agent_ids=target_agent_ids,
                source_agent_id=from_agent,
                requires_response_by=deadline_value if isinstance(deadline_value, str) else deadline,
                metadata={
                    "origin": "dashboard",
                    "reply_kind": reply_kind,
                    "reply_to_message_id": reply_to_ref,
                    "correlation_id": f"reply:{thread_id}:{message_id}",
                },
            )
            reply_obligations = [item.to_dict() for item in obligations]
        except ThreadReplyError as exc:
            return web.json_response({"error": exc.to_error_envelope()}, status=400)
    await store.notify_event(
        thread_id=thread_id,
        event_type="reply_added" if reply_to_ref or target_agent_ids else "message_added",
        data={
            "message_id": message_id,
            "from_agent": from_agent,
            "in_reply_to": reply_to_ref,
            "target_agent_ids": target_agent_ids,
            "reply_obligations": reply_obligations,
        },
    )
    coordination_payload: dict[str, Any] | None = None
    try:
        from koda.config import SQUAD_COORDINATOR_MODE
        from koda.squads import (
            SquadCoordinatorEngine,
            build_squad_capability_summaries,
            dispatch_squad_turn,
            get_squad_mention_resolver,
            get_squad_semantic_router,
            get_squad_task_store,
            get_squad_triage_service,
            record_squad_mention_unresolved,
            record_squad_routing_decision,
            select_targets,
            should_use_coordinator_engine,
        )

        thread = await store.get_thread(thread_id)
        participants = synced_participants or await store.list_participants(thread_id=thread_id)
        participant_ids = [p.agent_id for p in participants if p.left_at is None]
        if thread is not None and target_agent_ids:
            dispatches = []
            for target in target_agent_ids:
                obligation_key = f"reply:{thread_id}:{message_id}:{target}"
                result = await dispatch_squad_turn(
                    target_agent_id=target,
                    thread=thread,
                    thread_store=store,
                    query_text=content,
                    parent_message_id=f"msg-{message_id}",
                    metadata={
                        "from_user": from_agent,
                        "source": "web_reply",
                        "delivery_intent": "reply_required",
                        "reply_contract_version": "thread_reply.v1",
                        "reply_kind": reply_kind,
                        "reply_to_message_id": reply_to_ref,
                        "correlation_id": obligation_key,
                    },
                    application=request.app.get("telegram_application"),
                    user_id=thread.owner_user_id,
                    chat_id=thread.telegram_chat_id or 0,
                    delegation_chain=["squad_router"],
                    delegation_request_id=obligation_key,
                    delegation_origin_agent_id=from_agent,
                    telegram_message_thread_id=thread.telegram_message_thread_id,
                )
                dispatches.append(result.to_dict())
            return web.json_response(
                {
                    "messageId": message_id,
                    "fromAgent": from_agent,
                    "reply": {
                        "schemaVersion": "thread_reply.v1",
                        "inReplyTo": reply_to_ref,
                        "targets": target_agent_ids,
                        "obligations": reply_obligations,
                        "dispatches": dispatches,
                    },
                }
            )
        capability_hints: dict[str, str] = {}
        capability_summaries: list[Any] = []
        semantic_result: Any | None = None
        if thread is not None:
            capability_summaries = await build_squad_capability_summaries(
                squad_id=thread.squad_id,
                participant_agent_ids=participant_ids,
                coordinator_agent_id=thread.coordinator_agent_id,
            )
            capability_hints = {
                summary.agent_id: " ".join(str(value) for value in summary.to_dict().values())
                for summary in capability_summaries
            }
            semantic_result = await get_squad_semantic_router().rank_agents(
                content,
                capability_summaries,
                squad_id=thread.squad_id,
                coordinator_agent_id=thread.coordinator_agent_id,
            )
        mention_resolution = None
        triage_result = None
        if thread is not None:
            mention_resolution = await get_squad_mention_resolver().resolve(
                content,
                participants=participants,
                channel="web",
                channel_context={},
                capability_summaries=capability_summaries,
            )
            triage_result = await get_squad_triage_service().triage_user_input(
                thread_store=store,
                thread=thread,
                participants=participants,
                text=content,
                user_input_message_id=f"msg-{message_id}",
                channel="web",
                channel_context={},
                capability_summaries=capability_summaries,
                semantic_result=semantic_result,
                execution_targets=mention_resolution.resolved_agent_ids
                if mention_resolution.has_resolved_mentions
                else [],
                routing_source="web_mention" if mention_resolution.has_resolved_mentions else "triage",
                allow_proposals=not mention_resolution.has_mentions,
            )
            if mention_resolution.has_mentions and (
                (mention_resolution.unresolved or mention_resolution.ambiguous)
                and not mention_resolution.has_resolved_mentions
            ):
                await record_squad_mention_unresolved(
                    store,
                    thread_id=thread_id,
                    unresolved=mention_resolution.unresolved,
                    ambiguous=mention_resolution.ambiguous,
                    parent_message_id=f"msg-{message_id}",
                    channel="web",
                )
                return web.json_response(
                    {
                        "messageId": message_id,
                        "fromAgent": from_agent,
                        "routing": {
                            "source": "mention_unresolved",
                            "mentionResolution": mention_resolution.to_dict(),
                        },
                    }
                )
            if mention_resolution.has_resolved_mentions:
                targets = [
                    agent_id for agent_id in mention_resolution.resolved_agent_ids if agent_id in participant_ids
                ]
                await record_squad_routing_decision(
                    store,
                    thread_id=thread_id,
                    source="web_mention",
                    targets=targets,
                    parent_message_id=f"msg-{message_id}",
                    metadata={"mention_resolution": mention_resolution.to_dict()},
                )
                dispatches = [
                    (
                        await dispatch_squad_turn(
                            target_agent_id=target,
                            thread=thread,
                            thread_store=store,
                            query_text=content,
                            parent_message_id=f"msg-{message_id}",
                            metadata={"from_user": from_agent, "source": "web_mention", "delivery_intent": "execution"},
                            application=request.app.get("telegram_application"),
                            user_id=thread.owner_user_id,
                            chat_id=thread.telegram_chat_id or 0,
                            delegation_chain=["squad_router"],
                            telegram_message_thread_id=thread.telegram_message_thread_id,
                        )
                    ).to_dict()
                    for target in targets
                ]
                return web.json_response(
                    {
                        "messageId": message_id,
                        "fromAgent": from_agent,
                        "routing": {
                            "source": "web_mention",
                            "targets": targets,
                            "dispatches": dispatches,
                        },
                    }
                )
        if (
            thread is not None
            and SQUAD_COORDINATOR_MODE == "supervisor"
            and thread.coordinator_agent_id
            and should_use_coordinator_engine(
                content,
                participant_agent_ids=participant_ids,
                coordinator_agent_id=thread.coordinator_agent_id,
                semantic_result=semantic_result,
            )
        ):
            task_store = get_squad_task_store()
            if task_store is not None:
                resolved_thread = thread
                coordinator_id = resolved_thread.coordinator_agent_id
                if not coordinator_id:
                    raise RuntimeError("coordinator unavailable")
                engine = SquadCoordinatorEngine(thread_store=store, task_store=task_store)

                async def dispatch_task(task_request: Any) -> str | int | None:
                    result = await dispatch_squad_turn(
                        target_agent_id=task_request.agent_id,
                        thread=resolved_thread,
                        thread_store=store,
                        query_text=task_request.content,
                        parent_message_id=f"msg-{message_id}",
                        metadata={**dict(task_request.metadata or {}), "from_agent": coordinator_id},
                        application=request.app.get("telegram_application"),
                        user_id=resolved_thread.owner_user_id,
                        chat_id=resolved_thread.telegram_chat_id or 0,
                        squad_task_id=task_request.task_descriptor.id,
                        delegation_chain=[coordinator_id],
                        delegation_request_id=task_request.request_id,
                        delegation_origin_agent_id=coordinator_id,
                        telegram_message_thread_id=resolved_thread.telegram_message_thread_id,
                    )
                    return result.enqueued_task_id or result.message_id

                execution = await engine.coordinate_user_input(
                    text=content,
                    thread=resolved_thread,
                    participants=participants,
                    coordinator_agent_id=coordinator_id,
                    capability_hints=capability_hints,
                    capability_summaries=capability_summaries,
                    semantic_result=semantic_result,
                    dispatch=dispatch_task,
                    parent_message_id=f"msg-{message_id}",
                    user_id=resolved_thread.owner_user_id,
                    chat_id=resolved_thread.telegram_chat_id or 0,
                    telegram_message_thread_id=resolved_thread.telegram_message_thread_id,
                    awareness_agent_ids=triage_result.awareness_agent_ids if triage_result is not None else None,
                    contribution_proposals=[item.to_dict() for item in triage_result.proposal_candidates]
                    if triage_result is not None
                    else None,
                )
                if execution.coordinated:
                    await record_squad_routing_decision(
                        store,
                        thread_id=thread_id,
                        source="coordinator_engine",
                        targets=execution.dispatched_agents,
                        parent_message_id=f"msg-{message_id}",
                        metadata={"mode": execution.decision.mode, "task_ids": execution.task_ids},
                    )
                    coordination_payload = {
                        "mode": execution.decision.mode,
                        "tasks": execution.task_ids,
                        "agents": execution.dispatched_agents,
                    }
                    asyncio.create_task(
                        _watch_dashboard_squad_delivery_synthesis(
                            thread_id=thread_id,
                            parent_message_id=f"msg-{message_id}",
                            coordinator_agent_id=coordinator_id,
                            application=request.app.get("telegram_application"),
                        )
                    )
                    return web.json_response(
                        {"messageId": message_id, "fromAgent": from_agent, "coordination": coordination_payload}
                    )
        if (
            thread is not None
            and not thread.coordinator_agent_id
            and triage_result is not None
            and triage_result.proposal_candidates
        ):
            targets = [triage_result.proposal_candidates[0].agent_id]
        else:
            targets = select_targets(
                content,
                participant_agent_ids=participant_ids,
                coordinator_agent_id=thread.coordinator_agent_id if thread is not None else None,
                capability_hints=capability_hints,
                semantic_result=semantic_result,
                explicit_mention_agent_ids=mention_resolution.resolved_agent_ids if mention_resolution else None,
            )
        routing_source = (
            "proposal_arbitration"
            if thread is not None
            and not thread.coordinator_agent_id
            and triage_result is not None
            and triage_result.proposal_candidates
            else "semantic"
            if semantic_result is not None
            and getattr(semantic_result, "available", False)
            and targets == semantic_result.top_agents(include_coordinator=False)
            else "coordinator"
            if thread is not None and thread.coordinator_agent_id and targets == [thread.coordinator_agent_id]
            else "fallback"
        )
        if thread is not None:
            await record_squad_routing_decision(
                store,
                thread_id=thread_id,
                source=routing_source,
                targets=targets,
                parent_message_id=f"msg-{message_id}",
                metadata={
                    "semantic_result": semantic_result.to_dict() if semantic_result is not None else None,
                    "triage": triage_result.to_dict() if triage_result is not None else None,
                },
            )
        for target in targets:
            if thread is None:
                continue
            await dispatch_squad_turn(
                target_agent_id=target,
                thread=thread,
                thread_store=store,
                query_text=content,
                parent_message_id=f"msg-{message_id}",
                metadata={"from_user": from_agent, "source": routing_source, "delivery_intent": "execution"},
                application=request.app.get("telegram_application"),
                user_id=thread.owner_user_id,
                chat_id=thread.telegram_chat_id or 0,
                delegation_chain=["squad_router"],
                telegram_message_thread_id=thread.telegram_message_thread_id,
            )
    except Exception:
        log.exception("dashboard_squad_message_route_failed", thread_id=thread_id)
    payload_out: dict[str, Any] = {"messageId": message_id, "fromAgent": from_agent}
    if reply_to_ref or target_agent_ids:
        payload_out["reply"] = {
            "schemaVersion": "thread_reply.v1",
            "inReplyTo": reply_to_ref,
            "targets": target_agent_ids,
            "obligations": reply_obligations,
        }
    if coordination_payload is not None:
        payload_out["coordination"] = coordination_payload
    return web.json_response(payload_out)


def _serialize_task_for_dashboard(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "threadId": task.thread_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "kind": task.kind,
        "assignedAgentId": task.assigned_agent_id,
        "assignerAgentId": task.assigner_agent_id,
        "version": task.version,
        "claimToken": task.claim_token,
        "claimExpiresAt": task.claim_expires_at.isoformat() if task.claim_expires_at else None,
        "completedAt": task.completed_at.isoformat() if task.completed_at else None,
        "errorMessage": task.error_message,
        "resultSummary": task.result_summary,
    }


async def post_dashboard_squad_task_claim_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    task_id = request.match_info["task_id"]
    try:
        payload = await _json_payload(request)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    agent_id = (payload.get("agent_id") or "").strip() if isinstance(payload.get("agent_id"), str) else ""
    if not agent_id:
        return web.json_response({"error": "agent_id is required"}, status=400)
    _access_task, access_resp = await _dashboard_squad_task_access(request, task_id, require_write=True)
    if access_resp is not None:
        return access_resp
    ttl_seconds = _parse_optional_int(payload.get("ttl_seconds"), name="ttl_seconds") or 300

    from koda.squads import TaskClaimConflictError, TaskNotFoundError, get_squad_task_store

    store = get_squad_task_store()
    if store is None:
        return _service_unavailable(RuntimeError("squad task store unavailable"))
    try:
        task = await store.claim_task(
            task_id=task_id,
            agent_id=agent_id,
            ttl_seconds=max(1, min(ttl_seconds, 3600)),
        )
    except TaskNotFoundError:
        return web.json_response({"error": "task not found"}, status=404)
    except TaskClaimConflictError as exc:
        return web.json_response({"error": str(exc)}, status=409)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    await _notify_task_update(task, event="claimed")
    return web.json_response({"task": _serialize_task_for_dashboard(task)})


async def post_dashboard_squad_task_complete_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    task_id = request.match_info["task_id"]
    try:
        payload = await _json_payload(request)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    agent_id = (payload.get("agent_id") or "").strip() if isinstance(payload.get("agent_id"), str) else ""
    if not agent_id:
        return web.json_response({"error": "agent_id is required"}, status=400)
    access_task, access_resp = await _dashboard_squad_task_access(request, task_id, require_write=True)
    if access_resp is not None:
        return access_resp
    operator_reason = (payload.get("reason") or "").strip() if isinstance(payload.get("reason"), str) else ""
    coordinator_override = bool(payload.get("coordinator_override"))
    if access_task is not None:
        _access, task_row = access_task
        if (
            task_row.get("assigned_agent_id")
            and task_row.get("assigned_agent_id") != agent_id
            and (not coordinator_override or not operator_reason)
        ):
            return web.json_response(
                {"error": "operator override requires coordinator_override=true and reason"},
                status=403,
            )
    raw_summary = payload.get("result_summary")
    result_summary = raw_summary.strip() if isinstance(raw_summary, str) and raw_summary.strip() else None

    from koda.squads import (
        IllegalTransitionError,
        TaskNotFoundError,
        TaskOwnershipError,
        get_squad_task_store,
    )

    store = get_squad_task_store()
    if store is None:
        return _service_unavailable(RuntimeError("squad task store unavailable"))
    try:
        if coordinator_override:
            task = await store.update_task_status(
                task_id=task_id,
                new_status="done",
                agent_id=agent_id,
                result_summary=result_summary,
                metadata_patch={
                    "operator_override": True,
                    "operator_reason": operator_reason,
                    "actor_type": "operator",
                },
                coordinator_override=True,
            )
        else:
            task = await store.complete_task(
                task_id=task_id,
                agent_id=agent_id,
                result_summary=result_summary,
            )
    except TaskNotFoundError:
        return web.json_response({"error": "task not found"}, status=404)
    except IllegalTransitionError as exc:
        return web.json_response({"error": str(exc)}, status=409)
    except TaskOwnershipError as exc:
        return web.json_response({"error": str(exc)}, status=403)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    await _notify_task_update(task, event="completed")
    return web.json_response({"task": _serialize_task_for_dashboard(task)})


async def post_dashboard_squad_task_escalate_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    task_id = request.match_info["task_id"]
    try:
        payload = await _json_payload(request)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    agent_id = (payload.get("agent_id") or "").strip() if isinstance(payload.get("agent_id"), str) else ""
    reason = (payload.get("reason") or "").strip() if isinstance(payload.get("reason"), str) else ""
    if not agent_id:
        return web.json_response({"error": "agent_id is required"}, status=400)
    if not reason:
        return web.json_response({"error": "reason is required"}, status=400)
    _access_task, access_resp = await _dashboard_squad_task_access(request, task_id, require_write=True)
    if access_resp is not None:
        return access_resp

    from koda.squads import (
        IllegalTransitionError,
        TaskNotFoundError,
        TaskOwnershipError,
        get_squad_task_store,
    )

    store = get_squad_task_store()
    if store is None:
        return _service_unavailable(RuntimeError("squad task store unavailable"))
    try:
        task = await store.escalate_task(
            task_id=task_id,
            agent_id=agent_id,
            reason=reason,
        )
    except TaskNotFoundError:
        return web.json_response({"error": "task not found"}, status=404)
    except IllegalTransitionError as exc:
        return web.json_response({"error": str(exc)}, status=409)
    except TaskOwnershipError as exc:
        return web.json_response({"error": str(exc)}, status=403)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    await _notify_task_update(task, event="escalated")
    return web.json_response({"task": _serialize_task_for_dashboard(task)})


async def _notify_task_update(task: Any, *, event: str) -> None:
    """Fire-and-forget pg_notify for a task mutation. Logs on failure."""
    from koda.squads import get_squad_thread_store

    store = get_squad_thread_store()
    if store is None:
        return
    await store.notify_event(
        thread_id=task.thread_id,
        event_type="task_updated",
        data={
            "task_id": task.id,
            "status": task.status,
            "version": task.version,
            "assigned_agent_id": task.assigned_agent_id,
            "kind_event": event,
        },
    )


async def get_dashboard_squad_metrics_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    squad_id = request.match_info["squad_id"]

    from koda.squads import get_squad_metrics_default

    try:
        metrics = await get_squad_metrics_default(squad_id=squad_id)
    except Exception as exc:
        return _service_unavailable(RuntimeError(str(exc)))
    if metrics is None:
        return web.json_response({"available": False})
    return web.json_response(
        {
            "available": True,
            "squadId": metrics.squad_id,
            "workspaceIds": metrics.workspace_ids,
            "totalCostUsd": str(metrics.total_cost_usd),
            "openThreadCount": metrics.open_thread_count,
            "completedThreadCount": metrics.completed_thread_count,
            "costByAgent": [
                {
                    "agentId": row.agent_id,
                    "costUsd": str(row.cost_usd),
                    "queryCount": row.query_count,
                }
                for row in metrics.cost_by_agent
            ],
            "taskCountByStatus": metrics.task_count_by_status,
            "lastActiveAt": metrics.last_active_at.isoformat() if metrics.last_active_at else None,
        }
    )


async def list_dashboard_squad_activity_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    squad_id = request.match_info["squad_id"]
    limit = _parse_optional_int(request.query.get("limit"), name="limit") or 50

    from koda.squads import list_squad_activity_default

    try:
        entries = await list_squad_activity_default(
            squad_id=squad_id,
            limit=max(1, min(limit, 500)),
        )
    except Exception as exc:
        return _service_unavailable(RuntimeError(str(exc)))
    if entries is None:
        return web.json_response({"items": [], "count": 0, "available": False})
    items = [
        {
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "source": e.source,
            "eventType": e.event_type,
            "actor": e.actor,
            "summary": e.summary,
            "threadId": e.thread_id,
            "payload": e.payload,
        }
        for e in entries
    ]
    return web.json_response({"items": items, "count": len(items), "available": True})


async def list_dashboard_squad_threads_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    squad_id = request.match_info["squad_id"]
    workspace_id = (request.query.get("workspace_id") or "").strip() or None
    status = (request.query.get("status") or "").strip() or None
    limit = _parse_optional_int(request.query.get("limit"), name="limit") or 50

    from koda.squads import list_squad_threads_default

    try:
        threads = await list_squad_threads_default(
            squad_id=squad_id,
            workspace_id=workspace_id,
            status=status,
            limit=max(1, min(limit, 200)),
        )
    except Exception as exc:
        return _service_unavailable(RuntimeError(str(exc)))
    if threads is None:
        return web.json_response({"items": [], "count": 0, "available": False})
    items = [
        {
            "id": t.id,
            "workspaceId": t.workspace_id,
            "squadId": t.squad_id,
            "title": t.title,
            "status": t.status,
            "coordinatorAgentId": t.coordinator_agent_id,
            "currentOwnerAgentId": t.current_owner_agent_id,
            "telegramChatId": t.telegram_chat_id,
            "telegramMessageThreadId": t.telegram_message_thread_id,
            "costUsdAccum": str(t.cost_usd_accum),
            "photoUrl": (
                str(t.metadata.get("photo_url"))
                if isinstance(t.metadata, dict) and t.metadata.get("photo_url")
                else None
            ),
            "createdAt": t.created_at.isoformat() if t.created_at else None,
            "updatedAt": t.updated_at.isoformat() if t.updated_at else None,
            "completedAt": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in threads
    ]
    return web.json_response({"items": items, "count": len(items), "available": True})


async def get_dashboard_squad_thread_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    thread_id = request.match_info["thread_id"]
    message_limit = _parse_optional_int(request.query.get("message_limit"), name="message_limit") or 30
    task_limit = _parse_optional_int(request.query.get("task_limit"), name="task_limit") or 30
    before_message_id = _parse_optional_int(
        request.query.get("before") or request.query.get("before_id"),
        name="before",
    )
    break_glass_reason = (request.query.get("break_glass_reason") or "").strip() or None
    access, access_resp = await _dashboard_squad_thread_access(
        request,
        thread_id,
        break_glass_reason=break_glass_reason,
    )
    if access_resp is not None:
        return access_resp
    if access is None:
        return web.json_response({"error": "thread access unavailable"}, status=503)
    from koda.squads import get_squad_access_service, get_squad_thread_store, get_thread_overview_default

    try:
        overview = await get_thread_overview_default(
            thread_id,
            message_limit=max(1, min(message_limit, 200)),
            task_limit=max(1, min(task_limit, 200)),
        )
    except Exception as exc:
        return _service_unavailable(RuntimeError(str(exc)))
    if overview is None:
        return web.json_response({"error": "thread not found"}, status=404)
    thread = overview.thread
    recent_messages = overview.recent_messages
    recent_message_page: dict[str, Any] = {
        "limit": max(1, min(message_limit, 200)),
        "returned": len(recent_messages),
        "nextCursor": None,
        "hasMore": False,
    }
    try:
        access_service = get_squad_access_service()
        thread_store = get_squad_thread_store()
        if access_service is not None and thread_store is not None:
            bounded_message_limit = max(1, min(message_limit, 200))
            recent_messages = await thread_store.thread_history(
                thread_id=thread_id,
                limit=bounded_message_limit + 1,
                before_id=before_message_id,
                visible_after=access_service.visible_after_for(access),
            )
            recent_messages = access_service.redact_messages(access, recent_messages)
            has_more_messages = len(recent_messages) > bounded_message_limit
            if has_more_messages:
                recent_messages = recent_messages[:bounded_message_limit]
            recent_messages = sorted(recent_messages, key=lambda message: int(message.get("id") or 0))
            recent_message_page = {
                "limit": bounded_message_limit,
                "returned": len(recent_messages),
                "nextCursor": str(recent_messages[0]["id"]) if has_more_messages and recent_messages else None,
                "hasMore": has_more_messages,
            }
    except Exception:
        log.exception("dashboard_squad_thread_history_access_filter_failed", thread_id=thread_id)
    artifacts_payload: list[dict[str, Any]] = []
    try:
        from koda.squads import get_squad_artifact_store

        artifact_store = get_squad_artifact_store()
        if artifact_store is not None and not access.redacted:
            artifacts_payload = [
                {
                    "artifactId": artifact.artifact_id,
                    "threadId": artifact.thread_id,
                    "taskId": artifact.task_id,
                    "ownerAgentId": artifact.owner_agent_id,
                    "version": artifact.version,
                    "kind": artifact.kind,
                    "pathOrUri": Path(artifact.path_or_uri).name or artifact.kind or "artifact",
                    "downloadUrl": (
                        "/api/control-plane/dashboard/squads/threads/"
                        f"{thread_id}/artifacts/{urllib.parse.quote(artifact.artifact_id, safe='')}/download"
                    ),
                    "visibleToSquad": artifact.visible_to_squad,
                    "metadata": artifact.metadata,
                }
                for artifact in await artifact_store.list_for_thread(thread_id=thread_id, include_private=False)
            ]
    except Exception:
        log.exception("dashboard_squad_artifact_list_failed", thread_id=thread_id)
    thread_metadata = thread.metadata if isinstance(thread.metadata, dict) else {}
    photo_url = thread_metadata.get("photo_url") if thread_metadata else None
    return web.json_response(
        {
            "thread": {
                "id": thread.id,
                "workspaceId": thread.workspace_id,
                "squadId": thread.squad_id,
                "title": thread.title,
                "status": thread.status,
                "ownerUserId": thread.owner_user_id,
                "coordinatorAgentId": thread.coordinator_agent_id,
                "currentOwnerAgentId": thread.current_owner_agent_id,
                "telegramChatId": thread.telegram_chat_id,
                "telegramMessageThreadId": thread.telegram_message_thread_id,
                "budgetUsdCap": str(thread.budget_usd_cap) if thread.budget_usd_cap is not None else None,
                "costUsdAccum": str(thread.cost_usd_accum),
                "photoUrl": photo_url if isinstance(photo_url, str) else None,
                "metadata": thread_metadata,
                "createdAt": thread.created_at.isoformat() if thread.created_at else None,
                "updatedAt": thread.updated_at.isoformat() if thread.updated_at else None,
            },
            "coordinatorAgentId": overview.coordinator_agent_id,
            "participants": [
                {
                    "agentId": p.agent_id,
                    "role": p.role,
                    "joinedAt": p.joined_at.isoformat() if p.joined_at else None,
                    "leftAt": p.left_at.isoformat() if p.left_at else None,
                }
                for p in overview.participants
            ],
            "recentMessages": [
                {
                    "id": m["id"],
                    "messageUuid": m.get("message_uuid"),
                    "from": m["from"],
                    "to": m["to"],
                    "toAgentIds": m.get("to_agent_ids") or [],
                    "content": m["content"],
                    "type": m["type"],
                    "payload": m.get("payload") or {},
                    "metadata": m["metadata"],
                    "causationId": m.get("causation_id"),
                    "correlationId": m.get("correlation_id"),
                    "inReplyTo": m.get("in_reply_to"),
                    "requiresResponseBy": (
                        m["requires_response_by"].isoformat()
                        if hasattr(m.get("requires_response_by"), "isoformat")
                        else m.get("requires_response_by")
                    ),
                    "idempotencyKey": m.get("idempotency_key"),
                    "replyObligations": m.get("reply_obligations") or [],
                    "resolvedReplyObligations": m.get("resolved_reply_obligations") or [],
                    "replySummary": m.get("reply_summary") or {},
                    "createdAt": m["created_at"].isoformat() if m.get("created_at") else None,
                }
                for m in recent_messages
            ],
            "page": recent_message_page,
            "activeTasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "assignedAgentId": t.assigned_agent_id,
                    "assignerAgentId": t.assigner_agent_id,
                    "kind": t.kind,
                    "version": t.version,
                }
                for t in overview.active_tasks
            ],
            "artifacts": artifacts_payload,
            "openTaskCount": overview.open_task_count,
            "doneTaskCount": overview.done_task_count,
        }
    )


async def list_dashboard_agent_summaries_route(request: web.Request) -> web.Response:
    try:
        recent_task_limit = _bounded_int(
            request.query.get("recentTaskLimit") or request.query.get("recent_task_limit"),
            name="recentTaskLimit",
            default=5,
            minimum=0,
            maximum=25,
        )
        items = list_dashboard_agent_summaries(_query_agent_ids(request) or None, recent_task_limit=recent_task_limit)
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
        recent_task_limit = _bounded_int(
            request.query.get("recentTaskLimit") or request.query.get("recent_task_limit"),
            name="recentTaskLimit",
            default=5,
            minimum=0,
            maximum=25,
        )
        payload = dict(
            _manager().get_dashboard_agent_summary(
                request.match_info["agent_id"],
                recent_task_limit=recent_task_limit,
            )
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)
    payload.pop("agent", None)
    return web.json_response(payload)


async def get_dashboard_agent_summary_route(request: web.Request) -> web.Response:
    try:
        recent_task_limit = _bounded_int(
            request.query.get("recentTaskLimit") or request.query.get("recent_task_limit"),
            name="recentTaskLimit",
            default=5,
            minimum=0,
            maximum=25,
        )
        return web.json_response(
            _manager().get_dashboard_agent_summary(
                request.match_info["agent_id"],
                recent_task_limit=recent_task_limit,
            )
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_agent_executions_route(request: web.Request) -> web.Response:
    try:
        paged = _wants_paginated_response(request)
        limit = _bounded_int(request.query.get("limit"), name="limit", default=50, maximum=200)
        offset = _bounded_int(
            request.query.get("offset"),
            name="offset",
            default=0,
            minimum=0,
            maximum=_MAX_DASHBOARD_PAGE_OFFSET,
        )
        items = _manager().list_dashboard_executions(
            request.match_info["agent_id"],
            status=request.query.get("status") or None,
            search=request.query.get("search") or None,
            session_id=request.query.get("sessionId") or request.query.get("session_id") or None,
            limit=limit + 1 if paged else limit,
            offset=offset,
        )
        return web.json_response(_paginated_list_payload(items, limit=limit, offset=offset) if paged else items)
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_executions_route(request: web.Request) -> web.Response:
    agent_ids = _query_agent_ids(request)
    if not agent_ids:
        agent_ids = [item["id"] for item in _manager().list_agents()]
    paged = _wants_paginated_response(request)
    limit = _bounded_int(request.query.get("limit"), name="limit", default=50, maximum=200)
    offset = _bounded_int(
        request.query.get("offset"),
        name="offset",
        default=0,
        minimum=0,
        maximum=_MAX_DASHBOARD_PAGE_OFFSET,
    )
    try:
        items = list_dashboard_execution_summaries(
            agent_ids=agent_ids,
            status=request.query.get("status") or None,
            search=request.query.get("search") or None,
            session_id=request.query.get("sessionId") or None,
            limit=limit + 1 if paged else limit,
            offset=offset,
        )
        return web.json_response(_paginated_list_payload(items, limit=limit, offset=offset) if paged else items)
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


async def get_dashboard_execution_run_graph_route(request: web.Request) -> web.Response:
    task_id = _bounded_int(request.match_info["task_id"], name="task_id", default=1)
    try:
        payload = _manager().get_dashboard_execution_run_graph(request.match_info["agent_id"], task_id)
    except RuntimeError as exc:
        return _service_unavailable(exc)
    if payload is None:
        return web.json_response({"error": "execution not found"}, status=404)
    return web.json_response(payload)


async def get_dashboard_execution_replay_route(request: web.Request) -> web.Response:
    task_id = _bounded_int(request.match_info["task_id"], name="task_id", default=1)
    try:
        payload = _manager().get_dashboard_execution_replay(request.match_info["agent_id"], task_id)
    except RuntimeError as exc:
        return _service_unavailable(exc)
    if payload is None:
        return web.json_response({"error": "execution not found"}, status=404)
    return web.json_response(payload)


async def get_dashboard_execution_sandbox_doctor_route(request: web.Request) -> web.Response:
    task_id = _bounded_int(request.match_info["task_id"], name="task_id", default=1)
    try:
        payload = _manager().get_dashboard_execution_sandbox_doctor(request.match_info["agent_id"], task_id)
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
        paged = _wants_paginated_response(request)
        limit = _bounded_int(request.query.get("limit"), name="limit", default=50, maximum=200)
        offset = _bounded_int(
            request.query.get("offset"),
            name="offset",
            default=0,
            minimum=0,
            maximum=_MAX_DASHBOARD_PAGE_OFFSET,
        )
        items = _manager().list_dashboard_sessions(
            request.match_info["agent_id"],
            limit=limit + 1 if paged else limit,
            offset=offset,
            search=request.query.get("search") or None,
        )
        return web.json_response(_paginated_list_payload(items, limit=limit, offset=offset) if paged else items)
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_sessions_route(request: web.Request) -> web.Response:
    agent_ids = _query_agent_ids(request)
    if not agent_ids:
        agent_ids = [item["id"] for item in _manager().list_agents()]
    paged = _wants_paginated_response(request)
    limit = _bounded_int(request.query.get("limit"), name="limit", default=50, maximum=200)
    offset = _bounded_int(
        request.query.get("offset"),
        name="offset",
        default=0,
        minimum=0,
        maximum=_MAX_DASHBOARD_PAGE_OFFSET,
    )
    try:
        items = _manager().list_dashboard_session_summaries(
            agent_ids=agent_ids,
            limit=limit + 1 if paged else limit,
            offset=offset,
            search=request.query.get("search") or None,
        )
        return web.json_response(_paginated_list_payload(items, limit=limit, offset=offset) if paged else items)
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


async def delete_dashboard_session_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    try:
        deleted = _manager().delete_dashboard_session(
            request.match_info["agent_id"],
            request.match_info["session_id"],
        )
    except RuntimeError as exc:
        return _service_unavailable(exc)
    return web.json_response({"ok": True, "deleted": deleted})


async def patch_dashboard_room_route(request: web.Request) -> web.Response:
    """Patch room metadata (title, coordinator, status)."""
    if (resp := _authorize_request(request)) is not None:
        return resp
    payload = await _json_payload(request)
    thread_id = request.match_info["thread_id"]

    from koda.squads.threads import get_squad_thread_store

    thread_store = get_squad_thread_store()
    if thread_store is None:
        return web.json_response(
            {"error": "thread store is not configured (POSTGRES_URL missing)"},
            status=503,
        )

    title = payload.get("title")
    if title is not None:
        title = str(title).strip()
        if not title:
            return web.json_response({"error": "title cannot be empty"}, status=400)
    raw_coordinator = payload.get("coordinatorAgentId", payload.get("coordinator_agent_id"))
    clear_coordinator = bool(payload.get("clearCoordinator") or payload.get("clear_coordinator"))
    coordinator: str | None = None
    if not clear_coordinator and raw_coordinator is not None:
        coordinator = str(raw_coordinator).strip() or None

    metadata_patch: dict[str, Any] = {}
    if "photoUrl" in payload or "photo_url" in payload:
        photo = payload.get("photoUrl", payload.get("photo_url"))
        if photo is None or (isinstance(photo, str) and not photo.strip()):
            metadata_patch["photo_url"] = None
        else:
            metadata_patch["photo_url"] = str(photo).strip()
    if isinstance(payload.get("metadata"), dict):
        for key, value in payload["metadata"].items():
            metadata_patch[str(key)] = value

    has_metadata_change = title is not None or coordinator is not None or clear_coordinator or bool(metadata_patch)
    if has_metadata_change:
        try:
            await thread_store.update_thread(
                thread_id,
                title=title,
                coordinator_agent_id=coordinator,
                clear_coordinator=clear_coordinator,
                metadata_patch=metadata_patch or None,
            )
        except KeyError:
            return web.json_response({"error": "thread not found"}, status=404)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

    new_status = payload.get("status")
    if new_status is not None:
        new_status = str(new_status).strip()
        try:
            await thread_store.update_thread_status(thread_id, new_status)
        except KeyError:
            return web.json_response({"error": "thread not found"}, status=404)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

    return web.json_response({"ok": True})


async def add_dashboard_room_participant_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    payload = await _json_payload(request)
    thread_id = request.match_info["thread_id"]
    agent_id = str(payload.get("agentId") or payload.get("agent_id") or "").strip()
    role = str(payload.get("role") or "worker").strip() or "worker"
    if not agent_id:
        return web.json_response({"error": "agentId is required"}, status=400)

    from koda.squads.threads import get_squad_thread_store

    thread_store = get_squad_thread_store()
    if thread_store is None:
        return web.json_response(
            {"error": "thread store is not configured (POSTGRES_URL missing)"},
            status=503,
        )

    try:
        await thread_store.add_participant(thread_id=thread_id, agent_id=agent_id, role=role)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)

    # Reuse the existing room-creation activation contract: any agent assigned
    # to a room is implicitly meant to participate, so flip status to active.
    with contextlib.suppress(ValueError, RuntimeError):
        _manager().update_agent(agent_id, {"status": "active"})
    return web.json_response({"ok": True}, status=201)


async def patch_dashboard_room_participant_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    payload = await _json_payload(request)
    thread_id = request.match_info["thread_id"]
    agent_id = request.match_info["agent_id"]
    role = str(payload.get("role") or "").strip()
    if not role:
        return web.json_response({"error": "role is required"}, status=400)

    from koda.squads.threads import get_squad_thread_store

    thread_store = get_squad_thread_store()
    if thread_store is None:
        return web.json_response(
            {"error": "thread store is not configured (POSTGRES_URL missing)"},
            status=503,
        )

    try:
        await thread_store.add_participant(thread_id=thread_id, agent_id=agent_id, role=role)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)

    # Promoting a participant to coordinator also pins them as the room's
    # coordinator at the thread level so the next coordinator-aware lookup
    # picks them up without an extra round-trip.
    if role == "coordinator":
        with contextlib.suppress(KeyError, ValueError):
            await thread_store.update_thread(thread_id, coordinator_agent_id=agent_id)
    return web.json_response({"ok": True})


async def remove_dashboard_room_participant_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    thread_id = request.match_info["thread_id"]
    agent_id = request.match_info["agent_id"]

    from koda.squads.threads import get_squad_thread_store

    thread_store = get_squad_thread_store()
    if thread_store is None:
        return web.json_response(
            {"error": "thread store is not configured (POSTGRES_URL missing)"},
            status=503,
        )

    removed = await thread_store.remove_participant(thread_id=thread_id, agent_id=agent_id)
    return web.json_response({"ok": True, "removed": removed})


def _photo_url_for(thread_id: str, content_hash: str) -> str:
    """Build the operator-visible URL we expose for a stored room photo.

    The hash is a query param so each new upload produces a fresh URL —
    paired with the immutable Cache-Control on the GET, that gives us
    aggressive browser/CDN caching without staleness on edits.
    """
    return f"/api/control-plane/dashboard/squads/threads/{thread_id}/photo?v={content_hash}"


async def upload_dashboard_room_photo_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    thread_id = request.match_info["thread_id"]

    from koda.squads import get_squad_thread_store
    from koda.squads.room_photos import (
        InvalidPhotoError,
        PhotoTooLargeError,
        save_room_photo,
    )

    thread_store = get_squad_thread_store()
    if thread_store is None:
        return web.json_response(
            {"error": "thread store is not configured (POSTGRES_URL missing)"},
            status=503,
        )

    raw: bytes | None = None
    content_type = (request.content_type or "").lower()
    if content_type.startswith("multipart/"):
        from aiohttp.multipart import BodyPartReader

        try:
            reader = await request.multipart()
        except Exception as exc:
            return web.json_response({"error": f"invalid multipart payload: {exc}"}, status=400)
        async for part in reader:
            if not isinstance(part, BodyPartReader):
                continue
            if part.name in ("photo", "file"):
                raw = await part.read(decode=False)
                break
    else:
        raw = await request.read()

    if not raw:
        return web.json_response({"error": "no image payload"}, status=400)

    try:
        stored = save_room_photo(thread_id, raw)
    except PhotoTooLargeError as exc:
        return web.json_response({"error": str(exc)}, status=413)
    except InvalidPhotoError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)

    photo_url = _photo_url_for(thread_id, stored.content_hash)
    try:
        await thread_store.update_thread(
            thread_id,
            metadata_patch={
                "photo_url": photo_url,
                "photo_hash": stored.content_hash,
            },
        )
    except KeyError:
        return web.json_response({"error": "thread not found"}, status=404)

    return web.json_response(
        {
            "ok": True,
            "photoUrl": photo_url,
            "photoHash": stored.content_hash,
            "byteSize": stored.byte_size,
        },
        status=201,
    )


async def get_dashboard_room_photo_route(request: web.Request) -> web.StreamResponse:
    if (resp := _authorize_request(request)) is not None:
        return resp
    thread_id = request.match_info["thread_id"]

    from koda.squads.room_photos import read_room_photo

    try:
        data = read_room_photo(thread_id)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    if data is None:
        return web.json_response({"error": "photo not found"}, status=404)

    etag = '"' + hashlib.sha256(data).hexdigest()[:16] + '"'
    if_none_match = request.headers.get("If-None-Match")
    if if_none_match and if_none_match.strip() == etag:
        return web.Response(status=304, headers={"ETag": etag})

    response = web.Response(
        body=data,
        content_type="image/jpeg",
        headers={
            "Content-Length": str(len(data)),
            "ETag": etag,
            # The URL itself carries a content hash (`?v=`), so the asset is
            # immutable for that URL: tell the browser/CDN it can cache for a
            # year and never revalidate.
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
    return response


async def delete_dashboard_room_photo_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    thread_id = request.match_info["thread_id"]

    from koda.squads import get_squad_thread_store
    from koda.squads.room_photos import delete_room_photo

    thread_store = get_squad_thread_store()
    if thread_store is None:
        return web.json_response(
            {"error": "thread store is not configured (POSTGRES_URL missing)"},
            status=503,
        )
    try:
        removed = delete_room_photo(thread_id)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    try:
        await thread_store.update_thread(
            thread_id,
            metadata_patch={"photo_url": None, "photo_hash": None},
        )
    except KeyError:
        return web.json_response({"error": "thread not found"}, status=404)
    return web.json_response({"ok": True, "removed": removed})


async def archive_dashboard_room_route(request: web.Request) -> web.Response:
    """Soft-delete a room by transitioning it to the archived status."""
    if (resp := _authorize_request(request)) is not None:
        return resp
    thread_id = request.match_info["thread_id"]

    from koda.squads.threads import get_squad_thread_store

    thread_store = get_squad_thread_store()
    if thread_store is None:
        return web.json_response(
            {"error": "thread store is not configured (POSTGRES_URL missing)"},
            status=503,
        )

    try:
        await thread_store.update_thread_status(thread_id, "archived")
    except KeyError:
        return web.json_response({"error": "thread not found"}, status=404)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response({"ok": True})


async def create_dashboard_room_route(request: web.Request) -> web.Response:
    """Atomically create a multi-agent room from the sessions UI.

    Steps: pick (or default) the workspace → create squad → assign each
    selected agent to the squad → open an initial thread with those agents
    as participants. The first agent in the list becomes the coordinator.
    """
    if (resp := _authorize_request(request)) is not None:
        return resp
    payload = await _json_payload(request)
    name = str(payload.get("name") or "").strip()
    description = str(payload.get("description") or "").strip()
    raw_agent_ids = payload.get("agentIds") or payload.get("agent_ids") or []
    if not isinstance(raw_agent_ids, list):
        return web.json_response({"error": "agentIds must be an array"}, status=400)
    agent_ids = [str(x).strip() for x in raw_agent_ids if str(x or "").strip()]
    if not name:
        return web.json_response({"error": "name is required"}, status=400)
    if not agent_ids:
        return web.json_response({"error": "at least one agent is required"}, status=400)
    workspace_id = str(payload.get("workspaceId") or payload.get("workspace_id") or "").strip() or None

    manager = _manager()

    if workspace_id is None:
        workspaces = (manager.list_workspaces() or {}).get("items") or []
        if not workspaces:
            return web.json_response({"error": "no workspace available"}, status=400)
        workspace_id = str(workspaces[0]["id"])

    try:
        squad = manager.create_workspace_squad(
            workspace_id,
            {"name": name, "description": description},
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except RuntimeError as exc:
        return _service_unavailable(exc)
    squad_id = str(squad["id"])

    assignment_failures: list[str] = []
    for agent_id in agent_ids:
        try:
            # Activate the agent at the same time as the squad assignment so a
            # freshly-created room can actually dispatch — paused agents would
            # receive the routing decision but never execute.
            manager.update_agent(
                agent_id,
                {
                    "organization": {
                        "workspace_id": workspace_id,
                        "squad_id": squad_id,
                    },
                    "status": "active",
                },
            )
        except (ValueError, RuntimeError) as exc:
            assignment_failures.append(f"{agent_id}: {exc}")

    from koda.squads.threads import get_squad_thread_store

    thread_store = get_squad_thread_store()
    if thread_store is None:
        return web.json_response(
            {"error": "thread store is not configured (POSTGRES_URL missing)"},
            status=503,
        )

    coordinator = agent_ids[0]
    participants = [(aid, "coordinator" if aid == coordinator else "worker") for aid in agent_ids]
    try:
        thread = await thread_store.create_thread(
            workspace_id=workspace_id,
            squad_id=squad_id,
            title=name,
            coordinator_agent_id=coordinator,
            participants=participants,
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except Exception as exc:  # pragma: no cover - last-ditch error path
        return web.json_response(
            {"error": f"thread creation failed: {exc}"},
            status=500,
        )

    response_body: dict[str, Any] = {
        "threadId": thread.id,
        "squadId": squad_id,
        "workspaceId": workspace_id,
    }
    if assignment_failures:
        response_body["warnings"] = assignment_failures
    return web.json_response(response_body, status=201)


async def post_dashboard_session_message_route(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    manager = _manager()
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            functools.partial(
                manager.send_dashboard_session_message,
                request.match_info["agent_id"],
                text=str(payload.get("text") or ""),
                session_id=str(payload.get("session_id") or "").strip() or None,
            ),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except RuntimeError as exc:
        return _service_unavailable(exc)
    return web.json_response(result, status=202)


async def download_dashboard_runtime_artifact_route(request: web.Request) -> web.StreamResponse:
    artifact_id_raw = str(request.match_info["artifact_id"] or "").strip()
    if not artifact_id_raw.isdigit():
        return web.json_response({"error": "artifact not found"}, status=404)

    artifact = _manager().get_dashboard_runtime_artifact_for_download(
        request.match_info["agent_id"],
        int(artifact_id_raw),
    )
    if artifact is None:
        return web.json_response({"error": "artifact not found"}, status=404)

    path = Path(str(artifact.get("path") or "").strip())
    if not path.is_file():
        return web.json_response({"error": "artifact file not found"}, status=404)

    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
    mime_type = str(metadata.get("mime_type") or "").strip() or mimetypes.guess_type(str(path))[0]
    filename = _download_filename(artifact.get("label"), path.name)
    headers = {
        "Content-Disposition": _download_content_disposition(filename),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    if mime_type:
        headers["Content-Type"] = mime_type
    return web.FileResponse(path=path, headers=headers)


async def download_dashboard_squad_artifact_route(request: web.Request) -> web.StreamResponse:
    if (resp := _authorize_request(request)) is not None:
        return resp
    thread_id = request.match_info["thread_id"]
    artifact_id = str(request.match_info["artifact_id"] or "").strip()
    access, access_resp = await _dashboard_squad_thread_access(request, thread_id)
    if access_resp is not None:
        return access_resp
    if access is None or access.redacted:
        return web.json_response({"error": "artifact not found"}, status=404)

    from koda.config import ARTIFACT_CACHE_DIR, DEFAULT_WORK_DIR, RUNTIME_ROOT_DIR
    from koda.squads import get_squad_artifact_store

    store = get_squad_artifact_store()
    if store is None:
        return _service_unavailable(RuntimeError("squad artifact store unavailable"))
    artifact = await store.get_artifact(artifact_id)
    if artifact is None or artifact.thread_id != thread_id or not artifact.visible_to_squad:
        return web.json_response({"error": "artifact not found"}, status=404)
    path = Path(artifact.path_or_uri).expanduser()
    if not _is_path_under_any_root(path, [RUNTIME_ROOT_DIR, ARTIFACT_CACHE_DIR, Path(DEFAULT_WORK_DIR)]):
        return web.json_response({"error": "artifact path is outside allowed runtime roots"}, status=403)
    if not path.is_file():
        return web.json_response({"error": "artifact file not found"}, status=404)
    filename = _download_filename(artifact.metadata.get("label"), path.name)
    mime_type = str(artifact.metadata.get("mime_type") or "").strip() or mimetypes.guess_type(str(path))[0]
    headers = {
        "Content-Disposition": _download_content_disposition(filename),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    if mime_type:
        headers["Content-Type"] = mime_type
    return web.FileResponse(path=path, headers=headers)


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


async def list_agent_tools_catalog_route(request: web.Request) -> web.Response:  # noqa: ARG001
    try:
        from koda.utils.approval import _OPS_COMMANDS, WRITE_CLASSIFIERS
    except ImportError:
        return web.json_response({"items": []})

    tool_descriptions = {
        "shell": "Execute shell commands in the agent workspace",
        "git": "Git operations (status, log, diff, commit, push)",
        "docker": "Docker container operations",
        "pip": "Python package manager",
        "npm": "Node package manager",
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
    edited_params = payload.get("edited_params")
    response_text = str(payload.get("response_text") or "").strip() or None
    if not raw_decision:
        return web.json_response({"error": "missing decision"}, status=400)
    if edited_params is not None and not isinstance(edited_params, dict):
        return web.json_response({"error": "edited_params must be an object"}, status=400)
    try:
        summary = await resolve_approval(
            approval_id=approval_id,
            decision=raw_decision,
            rationale=rationale,
            edited_params=edited_params,
            response_text=response_text,
        )
    except KeyError:
        return web.json_response({"error": "approval not found"}, status=404)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response({"approval": summary})


async def list_dashboard_agent_dlq_route(request: web.Request) -> web.Response:
    try:
        paged = _wants_paginated_response(request)
        limit = _bounded_int(request.query.get("limit"), name="limit", default=50, maximum=200)
        offset = _bounded_int(
            request.query.get("offset"),
            name="offset",
            default=0,
            minimum=0,
            maximum=_MAX_DASHBOARD_PAGE_OFFSET,
        )
        items = _manager().list_dashboard_dlq(
            request.match_info["agent_id"],
            limit=limit + 1 if paged else limit,
            offset=offset,
            retry_eligible=_query_bool(request, "retryEligible"),
        )
        return web.json_response(_paginated_list_payload(items, limit=limit, offset=offset) if paged else items)
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_dlq_route(request: web.Request) -> web.Response:
    agent_ids = _query_agent_ids(request)
    if not agent_ids:
        agent_ids = [item["id"] for item in _manager().list_agents()]
    paged = _wants_paginated_response(request)
    limit = _bounded_int(request.query.get("limit"), name="limit", default=50, maximum=200)
    offset = _bounded_int(
        request.query.get("offset"),
        name="offset",
        default=0,
        minimum=0,
        maximum=_MAX_DASHBOARD_PAGE_OFFSET,
    )
    try:
        items = list_dashboard_dlq(
            agent_ids=agent_ids,
            limit=limit + 1 if paged else limit,
            offset=offset,
            retry_eligible=_query_bool(request, "retryEligible"),
        )
        return web.json_response(_paginated_list_payload(items, limit=limit, offset=offset) if paged else items)
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
        paged = _wants_paginated_response(request)
        limit = _bounded_int(request.query.get("limit"), name="limit", default=50, maximum=200)
        offset = _bounded_int(
            request.query.get("offset"),
            name="offset",
            default=0,
            minimum=0,
            maximum=_MAX_DASHBOARD_PAGE_OFFSET,
        )
        items = list_dashboard_schedules(
            _query_agent_ids(request) or None,
            limit=limit + 1 if paged else limit,
            offset=offset,
        )
        return web.json_response(_paginated_list_payload(items, limit=limit, offset=offset) if paged else items)
    except RuntimeError as exc:
        return _service_unavailable(exc)


async def list_dashboard_agent_schedules_route(request: web.Request) -> web.Response:
    try:
        paged = _wants_paginated_response(request)
        limit = _bounded_int(request.query.get("limit"), name="limit", default=50, maximum=200)
        offset = _bounded_int(
            request.query.get("offset"),
            name="offset",
            default=0,
            minimum=0,
            maximum=_MAX_DASHBOARD_PAGE_OFFSET,
        )
        items = _manager().list_dashboard_schedules(
            request.match_info["agent_id"],
            limit=limit + 1 if paged else limit,
            offset=offset,
        )
        return web.json_response(_paginated_list_payload(items, limit=limit, offset=offset) if paged else items)
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


async def get_persistence_diagnostics(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_persistence_diagnostics())


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
    provider_id = request.match_info["provider_id"]
    session_id = request.match_info["session_id"]
    manager = _manager()
    # The submit call blocks on the CLI subprocess for up to 45 seconds; run
    # it in the default thread pool so the event loop stays responsive to the
    # frontend's 2.5s polling of the same login session.
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            functools.partial(manager.submit_provider_login_code, provider_id, session_id, payload),
        )
    except KeyError:
        raise web.HTTPNotFound(
            text=json.dumps({"error": "login_session_expired"}), content_type="application/json"
        ) from None
    return web.json_response(result)


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


def _channel_gateway_error(code: str, message: str) -> dict[str, Any]:
    category = "permission" if code in {"channel.identity_unknown", "channel.policy_denied"} else "validation"
    return {
        "error": {
            "code": code,
            "category": category,
            "message": message,
            "retryable": code != "channel.policy_denied",
            "user_action": "Open the channel gateway panel and review the sender.",
        }
    }


async def get_channel_gateway_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    return web.json_response(_manager().get_channel_gateway_state(request.match_info["agent_id"]))


async def create_channel_gateway_pairing_code_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    payload = await _json_payload(request)
    payload.setdefault("created_by", _resolve_owner_user_id(request) or "")
    return web.json_response(
        _manager().create_channel_gateway_pairing_code(request.match_info["agent_id"], payload), status=201
    )


async def list_channel_gateway_unknown_senders_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    return web.json_response(_manager().list_channel_gateway_unknown_senders(request.match_info["agent_id"]))


async def approve_channel_gateway_identity_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    payload = await _json_payload(request)
    payload.setdefault("approved_by", _resolve_owner_user_id(request) or "")
    try:
        return web.json_response(
            _manager().approve_channel_gateway_identity(
                request.match_info["agent_id"],
                request.match_info["identity_id"],
                payload,
            )
        )
    except KeyError:
        return web.json_response(
            _channel_gateway_error("channel.identity_unknown", "Channel identity not found."), status=404
        )


async def block_channel_gateway_identity_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    payload = await _json_payload(request)
    payload.setdefault("blocked_by", _resolve_owner_user_id(request) or "")
    try:
        return web.json_response(
            _manager().block_channel_gateway_identity(
                request.match_info["agent_id"],
                request.match_info["identity_id"],
                payload,
            )
        )
    except KeyError:
        return web.json_response(
            _channel_gateway_error("channel.identity_unknown", "Channel identity not found."), status=404
        )


async def revoke_channel_gateway_identity_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    payload = await _json_payload(request) if request.can_read_body else {}
    payload.setdefault("revoked_by", _resolve_owner_user_id(request) or "")
    try:
        return web.json_response(
            _manager().revoke_channel_gateway_identity(
                request.match_info["agent_id"],
                request.match_info["identity_id"],
                payload,
            )
        )
    except KeyError:
        return web.json_response(
            _channel_gateway_error("channel.identity_unknown", "Channel identity not found."), status=404
        )


def _skill_package_error_status(code: str) -> int:
    if code == "skill.validation_failed":
        return 400
    if code in {"skill.scan_denied", "skill.policy_denied", "skill.tool_conflict", "skill.rollback_unavailable"}:
        return 409
    return 500


async def list_skill_packages(request: web.Request) -> web.Response:
    from koda.skills._package import list_skill_package_locks

    return web.json_response({"items": list_skill_package_locks(request.match_info["agent_id"])})


async def list_skill_registry_route(request: web.Request) -> web.Response:
    from koda.skills._package import list_skill_registry

    return web.json_response(list_skill_registry(request.match_info["agent_id"]))


async def run_skill_package_evals_route(request: web.Request) -> web.Response:
    from koda.skills._package import SkillPackageError, run_skill_package_evals, skill_package_error_response

    try:
        result = run_skill_package_evals(request.match_info["agent_id"], request.match_info["package_id"])
    except SkillPackageError as exc:
        response = skill_package_error_response(exc)
        return web.json_response(response, status=_skill_package_error_status(str(response["error"].get("code") or "")))
    return web.json_response(result, status=201)


async def scan_skill_package_route(request: web.Request) -> web.Response:
    from koda.skills._package import SkillPackageError, scan_skill_package, skill_package_error_response

    payload = await _json_payload(request)
    package_path = str(payload.get("path") or "").strip()
    if not package_path:
        return web.json_response(
            {
                "ok": False,
                "error": {
                    "code": "skill.validation_failed",
                    "category": "validation",
                    "message": "Package path is required.",
                    "retryable": False,
                    "user_action": "Provide a local path to a koda-skill.yaml package.",
                },
            },
            status=400,
        )
    try:
        scan = scan_skill_package(package_path, agent_id=request.match_info["agent_id"])
    except SkillPackageError as exc:
        response = skill_package_error_response(exc)
        return web.json_response(response, status=_skill_package_error_status(str(response["error"].get("code") or "")))
    return web.json_response({"ok": True, "scan": scan.to_dict()})


async def install_skill_package_route(request: web.Request) -> web.Response:
    from koda.skills._package import SkillPackageError, install_skill_package, skill_package_error_response

    payload = await _json_payload(request)
    package_path = str(payload.get("path") or "").strip()
    if not package_path:
        return web.json_response(
            {
                "ok": False,
                "error": {
                    "code": "skill.validation_failed",
                    "category": "validation",
                    "message": "Package path is required.",
                    "retryable": False,
                    "user_action": "Provide a local path to a koda-skill.yaml package.",
                },
            },
            status=400,
        )
    try:
        result = install_skill_package(
            package_path,
            agent_id=request.match_info["agent_id"],
            review_accepted=bool(payload.get("review_accepted")),
            review_note=str(payload.get("review_note") or ""),
        )
    except SkillPackageError as exc:
        response = skill_package_error_response(exc)
        return web.json_response(response, status=_skill_package_error_status(str(response["error"].get("code") or "")))
    return web.json_response(result, status=201)


async def uninstall_skill_package_route(request: web.Request) -> web.Response:
    from koda.skills._package import SkillPackageError, skill_package_error_response, uninstall_skill_package

    try:
        result = uninstall_skill_package(request.match_info["agent_id"], request.match_info["package_id"])
    except SkillPackageError as exc:
        response = skill_package_error_response(exc)
        return web.json_response(response, status=_skill_package_error_status(str(response["error"].get("code") or "")))
    return web.json_response(result)


async def rollback_skill_package_route(request: web.Request) -> web.Response:
    from koda.skills._package import SkillPackageError, rollback_skill_package, skill_package_error_response

    try:
        result = rollback_skill_package(request.match_info["agent_id"], request.match_info["package_id"])
    except SkillPackageError as exc:
        response = skill_package_error_response(exc)
        return web.json_response(response, status=_skill_package_error_status(str(response["error"].get("code") or "")))
    return web.json_response(result)


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


def _improvement_proposal_error_response(exc: Exception) -> web.Response:
    from koda.memory.safety import MemorySafetyError
    from koda.services.improvement_proposals import (
        ImprovementProposalError,
        ImprovementProposalNotFound,
        InvalidImprovementProposalTransition,
    )

    def _envelope(
        *,
        code: str,
        category: str,
        message: str,
        user_action: str,
        retryable: bool = False,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "category": category,
            "message": message,
            "retryable": retryable,
            "user_action": user_action,
        }

    if isinstance(exc, ImprovementProposalNotFound):
        return web.json_response(
            {
                "error": _envelope(
                    code="improvement_proposal.not_found",
                    category="validation",
                    message="Improvement proposal not found.",
                    user_action="Refresh the proposal queue and retry with an existing proposal.",
                )
            },
            status=404,
        )
    if isinstance(exc, MemorySafetyError):
        return web.json_response({"error": exc.error_envelope()}, status=409)
    if isinstance(exc, KeyError):
        return web.json_response(
            {
                "error": _envelope(
                    code="improvement_proposal.agent_not_found",
                    category="configuration",
                    message="Agent or improvement proposal not found.",
                    user_action="Verify the agent id and proposal id, then retry.",
                )
            },
            status=404,
        )
    if isinstance(exc, InvalidImprovementProposalTransition):
        return web.json_response(
            {
                "error": _envelope(
                    code="improvement_proposal.invalid_transition",
                    category="policy_denied",
                    message=str(exc),
                    user_action="Review the proposal status, validation result, RunGraph evidence, and rollback plan.",
                )
            },
            status=409,
        )
    if isinstance(exc, ImprovementProposalError):
        return web.json_response(
            {
                "error": _envelope(
                    code="improvement_proposal.validation",
                    category="validation",
                    message=str(exc),
                    user_action="Fix the proposal payload and submit it again.",
                )
            },
            status=400,
        )
    raise exc


async def list_improvement_proposals(request: web.Request) -> web.Response:
    try:
        limit = _bounded_int(request.query.get("limit"), name="limit", default=50, maximum=500)
        return web.json_response(
            _manager().list_improvement_proposals(
                request.match_info["agent_id"],
                status=request.query.get("status"),
                proposal_type=request.query.get("proposal_type"),
                limit=limit,
            )
        )
    except Exception as exc:
        return _improvement_proposal_error_response(exc)


async def create_improvement_proposal(request: web.Request) -> web.Response:
    try:
        payload = await _json_payload(request)
        return web.json_response(
            _manager().create_improvement_proposal(request.match_info["agent_id"], payload),
            status=201,
        )
    except Exception as exc:
        return _improvement_proposal_error_response(exc)


async def get_improvement_proposal(request: web.Request) -> web.Response:
    try:
        return web.json_response(
            _manager().get_improvement_proposal(
                request.match_info["agent_id"],
                request.match_info["proposal_id"],
            )
        )
    except Exception as exc:
        return _improvement_proposal_error_response(exc)


async def approve_improvement_proposal(request: web.Request) -> web.Response:
    try:
        payload = await _json_payload(request)
        return web.json_response(
            _manager().approve_improvement_proposal(
                request.match_info["agent_id"],
                request.match_info["proposal_id"],
                reviewer=str(payload.get("reviewer") or request.query.get("reviewer") or "control-plane"),
                note=str(payload.get("note") or ""),
            )
        )
    except Exception as exc:
        return _improvement_proposal_error_response(exc)


async def reject_improvement_proposal(request: web.Request) -> web.Response:
    try:
        payload = await _json_payload(request)
        return web.json_response(
            _manager().reject_improvement_proposal(
                request.match_info["agent_id"],
                request.match_info["proposal_id"],
                reviewer=str(payload.get("reviewer") or request.query.get("reviewer") or "control-plane"),
                note=str(payload.get("note") or ""),
            )
        )
    except Exception as exc:
        return _improvement_proposal_error_response(exc)


async def validate_improvement_proposal(request: web.Request) -> web.Response:
    try:
        payload = await _json_payload(request)
        return web.json_response(
            _manager().validate_improvement_proposal(
                request.match_info["agent_id"],
                request.match_info["proposal_id"],
                payload,
            )
        )
    except Exception as exc:
        return _improvement_proposal_error_response(exc)


async def apply_improvement_proposal(request: web.Request) -> web.Response:
    try:
        payload = await _json_payload(request)
        return web.json_response(
            _manager().apply_improvement_proposal(
                request.match_info["agent_id"],
                request.match_info["proposal_id"],
                reviewer=str(payload.get("reviewer") or request.query.get("reviewer") or "control-plane"),
                note=str(payload.get("note") or ""),
            )
        )
    except Exception as exc:
        return _improvement_proposal_error_response(exc)


async def rollback_improvement_proposal(request: web.Request) -> web.Response:
    try:
        payload = await _json_payload(request)
        return web.json_response(
            _manager().rollback_improvement_proposal(
                request.match_info["agent_id"],
                request.match_info["proposal_id"],
                reviewer=str(payload.get("reviewer") or request.query.get("reviewer") or "control-plane"),
                note=str(payload.get("note") or ""),
            )
        )
    except Exception as exc:
        return _improvement_proposal_error_response(exc)


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


async def list_eval_cases_route(request: web.Request) -> web.Response:
    limit = _bounded_int(request.query.get("limit"), name="limit", default=100)
    return web.json_response(_manager().list_eval_cases(request.match_info["agent_id"], limit=limit))


async def create_eval_case_from_run_route(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    try:
        task_id = int(payload.get("task_id") or request.query.get("task_id") or 0)
    except (TypeError, ValueError):
        task_id = 0
    if task_id <= 0:
        return web.json_response(
            {
                "error": {
                    "code": "eval.validation_failed",
                    "category": "validation",
                    "message": "task_id is required.",
                    "retryable": False,
                    "user_action": "Open an execution detail and create the eval from that run.",
                }
            },
            status=400,
        )
    try:
        return web.json_response(
            _manager().create_eval_case_from_run(request.match_info["agent_id"], task_id, payload),
            status=201,
        )
    except KeyError:
        return web.json_response(
            {
                "error": {
                    "code": "eval.source_run_not_found",
                    "category": "validation",
                    "message": "Source execution was not found.",
                    "retryable": False,
                    "user_action": "Refresh executions and choose a run that still exists.",
                }
            },
            status=404,
        )


async def patch_eval_case_route(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    try:
        return web.json_response(
            _manager().update_eval_case(
                request.match_info["agent_id"],
                request.match_info["case_key"],
                payload,
            )
        )
    except KeyError:
        return web.json_response({"error": "evaluation case not found"}, status=404)


async def list_eval_runs_route(request: web.Request) -> web.Response:
    limit = _bounded_int(request.query.get("limit"), name="limit", default=50)
    return web.json_response(_manager().list_eval_runs(request.match_info["agent_id"], limit=limit))


async def run_eval_suite_route(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().run_eval_suite(request.match_info["agent_id"], payload), status=201)


async def get_eval_run_route(request: web.Request) -> web.Response:
    try:
        return web.json_response(_manager().get_eval_run(request.match_info["agent_id"], request.match_info["run_id"]))
    except KeyError:
        return web.json_response({"error": "eval run not found"}, status=404)


async def create_trajectory_export_route(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    try:
        return web.json_response(
            _manager().create_trajectory_export(request.match_info["agent_id"], payload),
            status=201,
        )
    except ValueError as exc:
        return web.json_response(
            {
                "error": {
                    "code": "trajectory.validation_failed",
                    "category": "validation",
                    "message": str(exc),
                    "retryable": False,
                    "user_action": "Provide task_id or a case_key with a source task.",
                }
            },
            status=400,
        )
    except KeyError:
        return web.json_response(
            {
                "error": {
                    "code": "trajectory.source_run_not_found",
                    "category": "validation",
                    "message": "Source execution was not found.",
                    "retryable": False,
                    "user_action": "Refresh executions and choose a run that still exists.",
                }
            },
            status=404,
        )


async def get_release_quality_latest_route(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_release_quality_latest(request.match_info["agent_id"]))


async def get_quality_cockpit_overview_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    return web.json_response(_manager().get_quality_cockpit_overview())


async def get_quality_cockpit_agent_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    try:
        return web.json_response(_manager().get_quality_cockpit_agent(request.match_info["agent_id"]))
    except KeyError:
        return web.json_response({"error": "agent not found"}, status=404)


async def create_quality_failure_proposal_route(request: web.Request) -> web.Response:
    if (resp := _authorize_request(request)) is not None:
        return resp
    payload = await _json_payload(request)
    agent_id = str(payload.get("agent_id") or payload.get("agentId") or request.query.get("agent_id") or "").strip()
    if not agent_id:
        return web.json_response(
            {
                "error": {
                    "code": "quality_cockpit.validation_failed",
                    "category": "validation",
                    "message": "agent_id is required.",
                    "retryable": False,
                    "user_action": "Select the affected agent and retry.",
                }
            },
            status=400,
        )
    try:
        return web.json_response(
            _manager().create_quality_failure_proposal(
                agent_id=agent_id,
                failure_id=request.match_info["failure_id"],
                requested_by=str(payload.get("requested_by") or "quality_cockpit"),
            ),
            status=201,
        )
    except KeyError:
        return web.json_response(
            {
                "error": {
                    "code": "quality_cockpit.failure_not_found",
                    "category": "not_found",
                    "message": "Quality failure was not found for the selected agent.",
                    "retryable": False,
                    "user_action": "Refresh the quality cockpit and choose a current failure.",
                }
            },
            status=404,
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
    model_id = request.rel_url.query.get("model_id", "")
    manager = _manager()
    voices = await asyncio.get_event_loop().run_in_executor(
        None, lambda: manager.get_elevenlabs_voice_catalog(language=language, model_id=model_id)
    )
    return web.json_response(voices)


async def get_ollama_models(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    # Resolve connection inputs on the event loop (they touch the DB through
    # `_merged_global_env`), then hand only the blocking HTTP probe off to a
    # worker thread. Running the DB bits inside `run_in_executor` would escape
    # the async loop that owns the asyncpg connection pool, raising
    # `no running event loop` / `connection was closed in the middle of operation`.
    auth_mode, base_url, api_key = manager._resolve_ollama_connection_inputs(
        env=manager._merged_global_env(),
    )
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: manager._fetch_ollama_model_catalog(
            auth_mode=auth_mode,
            base_url=base_url,
            api_key=api_key,
        ),
    )
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


async def get_supertonic_models(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        manager.get_supertonic_model_catalog,
    )
    return web.json_response(payload)


async def start_supertonic_model_download(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    model_id = request.match_info["model_id"]
    try:
        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: manager.start_supertonic_model_download(model_id),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(payload, status=202)


async def get_supertonic_voices(request: web.Request) -> web.Response:
    import asyncio

    model_id = request.rel_url.query.get("model_id", "")
    language = request.rel_url.query.get("language", "")
    manager = _manager()
    try:
        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: manager.get_supertonic_voice_catalog(model_id=model_id, language=language),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(payload)


async def start_supertonic_voice_download(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    model_id = request.rel_url.query.get("model_id", "")
    try:
        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: manager.start_supertonic_voice_download(request.match_info["voice_id"], model_id=model_id),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(payload, status=202)


async def get_embedding_models(request: web.Request) -> web.Response:
    """Curated embedding-model catalog with installation status + active job."""
    import asyncio

    del request
    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: manager.get_embedding_model_catalog(),
    )
    return web.json_response(payload)


async def start_embedding_model_download(request: web.Request) -> web.Response:
    """Spawn a background download for the requested embedding model.

    Idempotent: if the model is already on disk, returns a completed job
    record so the UI's toast pattern still resolves cleanly.
    """
    import asyncio

    manager = _manager()
    model_id = request.match_info["model_id"]
    try:
        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: manager.start_embedding_model_download(model_id),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(payload, status=202)


async def select_embedding_model(request: web.Request) -> web.Response:
    """Persist the operator's choice. Refuses uninstalled models."""
    import asyncio

    manager = _manager()
    model_id = request.match_info["model_id"]
    try:
        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: manager.select_embedding_model(model_id),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(payload)


async def delete_embedding_model(request: web.Request) -> web.Response:
    """Drop a downloaded embedding model's cache directory."""
    import asyncio

    manager = _manager()
    model_id = request.match_info["model_id"]
    try:
        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: manager.delete_embedding_model_asset(model_id),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(payload)


async def get_provider_download_job(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    try:
        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: manager.get_provider_download_job(
                request.match_info["provider_id"],
                request.match_info["job_id"],
            ),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except KeyError:
        return web.json_response({"error": "download job not found"}, status=404)
    return web.json_response(payload)


async def cancel_provider_download_job(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    try:
        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: manager.cancel_provider_download_job(
                request.match_info["provider_id"],
                request.match_info["job_id"],
            ),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except KeyError:
        return web.json_response({"error": "download job not found"}, status=404)
    return web.json_response(payload)


async def list_active_provider_downloads(request: web.Request) -> web.Response:
    """Active downloads across providers — used by the UI to rebind sticky
    toasts after a page reload so progress UI survives F5 mid-download."""
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        manager.list_active_provider_downloads,
    )
    return web.json_response({"items": payload})


async def get_kokoro_model(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        manager.get_kokoro_model_status,
    )
    return web.json_response(payload)


async def start_kokoro_model_download(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        manager.start_kokoro_model_download,
    )
    return web.json_response(payload, status=202)


async def get_whisper_models(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        manager.get_whisper_catalog,
    )
    return web.json_response(payload)


async def start_whisper_model_download(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: manager.start_whisper_model_download(request.match_info["variant_id"]),
    )
    return web.json_response(payload, status=202)


async def delete_kokoro_model(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        manager.delete_kokoro_model_asset,
    )
    return web.json_response(payload)


async def delete_kokoro_voice(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: manager.delete_kokoro_voice_asset(request.match_info["voice_id"]),
    )
    return web.json_response(payload)


async def delete_supertonic_model(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    try:
        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: manager.delete_supertonic_model_asset(request.match_info["model_id"]),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(payload)


async def delete_supertonic_voice(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    model_id = request.rel_url.query.get("model_id", "")
    try:
        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: manager.delete_supertonic_voice_asset(request.match_info["voice_id"], model_id=model_id),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(payload)


async def import_supertonic_voice(request: web.Request) -> web.Response:
    import asyncio

    reader = await request.multipart()
    raw_file = b""
    model_id = ""
    name = ""
    async for raw_field in reader:
        if not isinstance(raw_field, BodyPartReader):
            continue
        field = raw_field
        if field.name == "file":
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                total += len(chunk)
                if total > 1_100_000:
                    return web.json_response({"error": "Supertonic voice JSON is too large"}, status=400)
                chunks.append(chunk)
            raw_file = b"".join(chunks)
        elif field.name == "model_id":
            model_id = (await field.text()).strip()
        elif field.name == "name":
            name = (await field.text()).strip()
    if not raw_file:
        return web.json_response({"error": "file is required"}, status=400)

    manager = _manager()
    try:
        payload = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: manager.import_supertonic_voice_asset(raw_file, model_id=model_id, name=name),
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(payload, status=201)


async def delete_whisper_model(request: web.Request) -> web.Response:
    import asyncio

    manager = _manager()
    payload = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: manager.delete_whisper_model_asset(request.match_info["variant_id"]),
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
    try:
        result = await start_oauth_flow(
            agent_id,
            server_key,
            frontend_callback_uri=frontend_callback_uri,
            redirect_uri=redirect_uri,
        )
    except KeyError:
        return web.json_response({"error": "agent_not_found"}, status=404)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
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


# ------------------------------------------------------------------ #
#  MCP Capabilities (Tools + Resources + Prompts)                      #
# ------------------------------------------------------------------ #


async def get_mcp_capabilities_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    return web.json_response(_manager().get_mcp_capability_snapshot(agent_id, server_key))


async def discover_mcp_capabilities_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    return web.json_response(_manager().discover_mcp_capabilities(agent_id, server_key, force_refresh=True))


async def list_mcp_resources_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    return web.json_response({"resources": _manager().list_mcp_resources(agent_id, server_key)})


async def list_mcp_prompts_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    return web.json_response({"prompts": _manager().list_mcp_prompts(agent_id, server_key)})


async def read_mcp_resource_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    payload = await request.json()
    uri = str(payload.get("uri") or "")
    return web.json_response(_manager().read_mcp_resource(agent_id, server_key, uri))


async def render_mcp_prompt_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    prompt_name = request.match_info["prompt_name"]
    payload = await request.json() if request.body_exists else {}
    arguments = payload.get("arguments") if isinstance(payload, dict) else None
    return web.json_response(_manager().render_mcp_prompt(agent_id, server_key, prompt_name, arguments or {}))


# ------------------------------------------------------------------ #
#  MCP Capability Policies (unified tool/resource/prompt)            #
# ------------------------------------------------------------------ #


async def list_mcp_capability_policies_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    return web.json_response(_manager().list_mcp_capability_policies(agent_id, server_key))


async def put_mcp_capability_policy_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    capability_kind = request.match_info["capability_kind"]
    capability_name = request.match_info["capability_name"]
    payload = await request.json()
    policy = str(payload.get("policy") or "auto")
    exposure_mode = payload.get("exposure_mode")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
    return web.json_response(
        _manager().upsert_mcp_capability_policy(
            agent_id,
            server_key,
            capability_kind,
            capability_name,
            policy,
            exposure_mode=exposure_mode,
            metadata=metadata,
        )
    )


async def delete_mcp_capability_policy_route(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    server_key = _mcp_connection_key(request)
    capability_kind = request.match_info["capability_kind"]
    capability_name = request.match_info["capability_name"]
    return web.json_response(
        _manager().delete_mcp_capability_policy(agent_id, server_key, capability_kind, capability_name)
    )


# ------------------------------------------------------------------ #
#  Custom MCP Servers (system-wide + per-agent)                      #
# ------------------------------------------------------------------ #


async def list_custom_mcp_servers_route(request: web.Request) -> web.Response:
    agent_id = request.query.get("agent_id") or None
    return web.json_response({"servers": _manager().list_custom_mcp_servers(agent_id=agent_id)})


async def get_custom_mcp_server_route(request: web.Request) -> web.Response:
    server_key = request.match_info["server_key"]
    agent_id = request.query.get("agent_id") or None
    entry = _manager().get_custom_mcp_server(server_key, agent_id=agent_id)
    if entry is None:
        return web.json_response({"error": "not_found", "server_key": server_key}, status=404)
    return web.json_response(entry)


async def register_custom_mcp_server_route(request: web.Request) -> web.Response:
    payload = await request.json()
    agent_id = payload.get("agent_id") or request.query.get("agent_id") or None
    owner_user_id = _resolve_owner_user_id(request)
    try:
        result = _manager().register_custom_mcp_server(
            payload.get("server") or payload,
            agent_id=agent_id,
            owner_user_id=owner_user_id,
        )
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response(result)


async def import_claude_desktop_mcp_route(request: web.Request) -> web.Response:
    payload = await request.json()
    agent_id = payload.get("agent_id") or request.query.get("agent_id") or None
    owner_user_id = _resolve_owner_user_id(request)
    raw = payload.get("payload") or payload
    if not isinstance(raw, dict):
        return web.json_response({"error": "payload must be an object"}, status=400)
    return web.json_response(_manager().import_claude_desktop_mcp(raw, agent_id=agent_id, owner_user_id=owner_user_id))


async def delete_custom_mcp_server_route(request: web.Request) -> web.Response:
    server_key = request.match_info["server_key"]
    agent_id = request.query.get("agent_id") or None
    return web.json_response(_manager().delete_custom_mcp_server(server_key, agent_id=agent_id))


def _resolve_owner_user_id(request: web.Request) -> str | None:
    """Best-effort owner identification for audit trail.

    Returns the operator user_id when an authenticated session is present.
    """
    try:
        session = getattr(request, "operator_session", None)
        if session is None:
            return None
        return getattr(session, "user_id", None) or session.get("user_id") if isinstance(session, dict) else None
    except Exception:
        return None


def setup_control_plane_routes(app: web.Application) -> None:
    # OAuth relay for CLI-based provider auth inside Docker
    app.router.add_get("/api/control-plane/oauth-relay/{session_id}", oauth_relay_handler)

    app.router.add_get("/", setup_landing)
    app.router.add_get("/setup", setup_page)
    app.router.add_get("/openapi/control-plane.json", control_plane_openapi)
    app.router.add_get("/api/control-plane/onboarding/status", onboarding_status)
    app.router.add_get("/api/control-plane/onboarding/readiness", onboarding_readiness)
    app.router.add_post("/api/control-plane/onboarding/first-task", onboarding_first_task)
    app.router.add_post("/api/control-plane/onboarding/bootstrap", onboarding_bootstrap)
    app.router.add_get("/api/control-plane/auth/status", auth_status)
    app.router.add_post("/api/control-plane/auth/bootstrap/exchange", auth_bootstrap_exchange)
    app.router.add_post("/api/control-plane/auth/bootstrap/codes", auth_issue_bootstrap_code)
    app.router.add_post("/api/control-plane/auth/register-owner", auth_register_owner)
    app.router.add_post("/api/control-plane/auth/login", auth_login)
    app.router.add_post("/api/control-plane/auth/logout", auth_logout)
    app.router.add_patch("/api/control-plane/auth/profile", auth_update_profile)
    app.router.add_post("/api/control-plane/auth/profile/photo", auth_upload_profile_photo)
    app.router.add_get("/api/control-plane/auth/profile/photo", auth_get_profile_photo)
    app.router.add_delete("/api/control-plane/auth/profile/photo", auth_delete_profile_photo)
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
    app.router.add_get("/api/control-plane/dashboard/squads/overview", list_dashboard_squads_overview_route)
    app.router.add_post(
        "/api/control-plane/dashboard/rooms",
        create_dashboard_room_route,
    )
    app.router.add_patch(
        "/api/control-plane/dashboard/squads/threads/{thread_id}",
        patch_dashboard_room_route,
    )
    app.router.add_delete(
        "/api/control-plane/dashboard/squads/threads/{thread_id}",
        archive_dashboard_room_route,
    )
    app.router.add_post(
        "/api/control-plane/dashboard/squads/threads/{thread_id}/participants",
        add_dashboard_room_participant_route,
    )
    app.router.add_patch(
        "/api/control-plane/dashboard/squads/threads/{thread_id}/participants/{agent_id}",
        patch_dashboard_room_participant_route,
    )
    app.router.add_delete(
        "/api/control-plane/dashboard/squads/threads/{thread_id}/participants/{agent_id}",
        remove_dashboard_room_participant_route,
    )
    app.router.add_post(
        "/api/control-plane/dashboard/squads/threads/{thread_id}/photo",
        upload_dashboard_room_photo_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/squads/threads/{thread_id}/photo",
        get_dashboard_room_photo_route,
    )
    app.router.add_delete(
        "/api/control-plane/dashboard/squads/threads/{thread_id}/photo",
        delete_dashboard_room_photo_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/squads/{squad_id}/threads",
        list_dashboard_squad_threads_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/squads/{squad_id}/activity",
        list_dashboard_squad_activity_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/squads/{squad_id}/metrics",
        get_dashboard_squad_metrics_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/squads/threads/{thread_id}",
        get_dashboard_squad_thread_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/squads/threads/{thread_id}/events",
        stream_dashboard_squad_thread_events_route,
    )
    app.router.add_post(
        "/api/control-plane/dashboard/squads/threads/{thread_id}/messages",
        post_dashboard_squad_thread_message_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/squads/threads/{thread_id}/artifacts/{artifact_id}/download",
        download_dashboard_squad_artifact_route,
    )
    app.router.add_post(
        "/api/control-plane/dashboard/squads/tasks/{task_id}/claim",
        post_dashboard_squad_task_claim_route,
    )
    app.router.add_post(
        "/api/control-plane/dashboard/squads/tasks/{task_id}/complete",
        post_dashboard_squad_task_complete_route,
    )
    app.router.add_post(
        "/api/control-plane/dashboard/squads/tasks/{task_id}/escalate",
        post_dashboard_squad_task_escalate_route,
    )
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
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/executions/{task_id}/run-graph",
        get_dashboard_execution_run_graph_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/executions/{task_id}/replay",
        get_dashboard_execution_replay_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/executions/{task_id}/sandbox-doctor",
        get_dashboard_execution_sandbox_doctor_route,
    )
    app.router.add_get("/api/control-plane/dashboard/sessions", list_dashboard_sessions_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/sessions", list_dashboard_agent_sessions_route)
    app.router.add_post(
        "/api/control-plane/dashboard/agents/{agent_id}/sessions/messages",
        post_dashboard_session_message_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/artifacts/{artifact_id}/download",
        download_dashboard_runtime_artifact_route,
    )
    app.router.add_get(
        "/api/control-plane/dashboard/agents/{agent_id}/sessions/{session_id}",
        get_dashboard_session_detail_route,
    )
    app.router.add_delete(
        "/api/control-plane/dashboard/agents/{agent_id}/sessions/{session_id}",
        delete_dashboard_session_route,
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
    app.router.add_get("/api/control-plane/workspaces/directory-roots", list_workspace_directory_roots)
    app.router.add_post("/api/control-plane/workspaces/list-directory", list_workspace_directory)
    app.router.add_post("/api/control-plane/workspaces/scan-directory", scan_workspace_directory_route)
    app.router.add_post("/api/control-plane/workspaces/import", import_workspace_from_directory_route)
    app.router.add_patch("/api/control-plane/workspaces/{workspace_id}", patch_workspace)
    app.router.add_delete("/api/control-plane/workspaces/{workspace_id}", delete_workspace)
    app.router.add_post("/api/control-plane/workspaces/{workspace_id}/rescan", rescan_workspace_route)
    app.router.add_post("/api/control-plane/workspaces/{workspace_id}/import-config", import_workspace_config_route)
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
    app.router.add_get("/api/control-plane/agents/{agent_id}/improvement-proposals", list_improvement_proposals)
    app.router.add_post("/api/control-plane/agents/{agent_id}/improvement-proposals", create_improvement_proposal)
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}",
        get_improvement_proposal,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}/approve",
        approve_improvement_proposal,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}/reject",
        reject_improvement_proposal,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}/validate",
        validate_improvement_proposal,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}/apply",
        apply_improvement_proposal,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/improvement-proposals/{proposal_id}/rollback",
        rollback_improvement_proposal,
    )
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
    app.router.add_get("/api/control-plane/agents/{agent_id}/evals/cases", list_eval_cases_route)
    app.router.add_post("/api/control-plane/agents/{agent_id}/evals/cases/from-run", create_eval_case_from_run_route)
    app.router.add_patch("/api/control-plane/agents/{agent_id}/evals/cases/{case_key}", patch_eval_case_route)
    app.router.add_get("/api/control-plane/agents/{agent_id}/evals/runs", list_eval_runs_route)
    app.router.add_post("/api/control-plane/agents/{agent_id}/evals/runs", run_eval_suite_route)
    app.router.add_get("/api/control-plane/agents/{agent_id}/evals/runs/{run_id}", get_eval_run_route)
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/evals/trajectory-exports",
        create_trajectory_export_route,
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/evals/release-quality/latest",
        get_release_quality_latest_route,
    )
    app.router.add_get("/api/control-plane/dashboard/quality/overview", get_quality_cockpit_overview_route)
    app.router.add_get("/api/control-plane/dashboard/quality/agents/{agent_id}", get_quality_cockpit_agent_route)
    app.router.add_post(
        "/api/control-plane/dashboard/quality/failures/{failure_id}/proposal",
        create_quality_failure_proposal_route,
    )

    app.router.add_get("/api/control-plane/global-defaults", get_global_defaults)
    app.router.add_patch("/api/control-plane/global-defaults", patch_global_defaults)
    app.router.add_get("/api/control-plane/system-settings", get_system_settings)
    app.router.add_put("/api/control-plane/system-settings", put_system_settings)
    app.router.add_get("/api/control-plane/system-settings/general", get_general_system_settings)
    app.router.add_put("/api/control-plane/system-settings/general", put_general_system_settings)
    app.router.add_get("/api/control-plane/_diag/persistence", get_persistence_diagnostics)
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
    app.router.add_get("/api/control-plane/providers/kokoro/model", get_kokoro_model)
    app.router.add_post(
        "/api/control-plane/providers/kokoro/model/download",
        start_kokoro_model_download,
    )
    app.router.add_get("/api/control-plane/providers/supertonic/models", get_supertonic_models)
    app.router.add_post(
        "/api/control-plane/providers/supertonic/models/{model_id}/download",
        start_supertonic_model_download,
    )
    app.router.add_get("/api/control-plane/providers/supertonic/voices", get_supertonic_voices)
    app.router.add_post(
        "/api/control-plane/providers/supertonic/voices/{voice_id}/download",
        start_supertonic_voice_download,
    )
    app.router.add_post(
        "/api/control-plane/providers/supertonic/voices/import",
        import_supertonic_voice,
    )
    app.router.add_get(
        "/api/control-plane/providers/embedding/models",
        get_embedding_models,
    )
    app.router.add_post(
        "/api/control-plane/providers/embedding/models/{model_id}/download",
        start_embedding_model_download,
    )
    app.router.add_post(
        "/api/control-plane/providers/embedding/models/{model_id}/select",
        select_embedding_model,
    )
    app.router.add_delete(
        "/api/control-plane/providers/embedding/models/{model_id}",
        delete_embedding_model,
    )
    app.router.add_get("/api/control-plane/providers/whispercpp/models", get_whisper_models)
    app.router.add_post(
        "/api/control-plane/providers/whispercpp/models/{variant_id}/download",
        start_whisper_model_download,
    )
    # DELETE counterparts — remove a downloaded asset from disk. Idempotent.
    app.router.add_delete(
        "/api/control-plane/providers/kokoro/model",
        delete_kokoro_model,
    )
    app.router.add_delete(
        "/api/control-plane/providers/kokoro/voices/{voice_id}",
        delete_kokoro_voice,
    )
    app.router.add_delete(
        "/api/control-plane/providers/supertonic/models/{model_id}",
        delete_supertonic_model,
    )
    app.router.add_delete(
        "/api/control-plane/providers/supertonic/voices/{voice_id}",
        delete_supertonic_voice,
    )
    app.router.add_delete(
        "/api/control-plane/providers/whispercpp/models/{variant_id}",
        delete_whisper_model,
    )
    app.router.add_get(
        "/api/control-plane/providers/downloads/active",
        list_active_provider_downloads,
    )
    app.router.add_get(
        "/api/control-plane/providers/{provider_id}/downloads/{job_id}",
        get_provider_download_job,
    )
    app.router.add_post(
        "/api/control-plane/providers/{provider_id}/downloads/{job_id}/cancel",
        cancel_provider_download_job,
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
    app.router.add_get("/api/control-plane/agents/{agent_id}/channels/gateway", get_channel_gateway_route)
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/channels/gateway/pairing-codes",
        create_channel_gateway_pairing_code_route,
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/channels/gateway/unknown-senders",
        list_channel_gateway_unknown_senders_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/channels/gateway/identities/{identity_id}/approve",
        approve_channel_gateway_identity_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/channels/gateway/identities/{identity_id}/block",
        block_channel_gateway_identity_route,
    )
    app.router.add_delete(
        "/api/control-plane/agents/{agent_id}/channels/gateway/identities/{identity_id}",
        revoke_channel_gateway_identity_route,
    )
    app.router.add_get("/api/control-plane/agents/{agent_id}/skills/packages", list_skill_packages)
    app.router.add_get("/api/control-plane/agents/{agent_id}/skills/registry", list_skill_registry_route)
    app.router.add_post("/api/control-plane/agents/{agent_id}/skills/packages/scan", scan_skill_package_route)
    app.router.add_post("/api/control-plane/agents/{agent_id}/skills/packages/install", install_skill_package_route)
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/skills/packages/{package_id}/evals/run",
        run_skill_package_evals_route,
    )
    app.router.add_delete(
        "/api/control-plane/agents/{agent_id}/skills/packages/{package_id}",
        uninstall_skill_package_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/skills/packages/{package_id}/rollback",
        rollback_skill_package_route,
    )

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

    # --- MCP Capabilities (tools + resources + prompts) ---
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/capabilities",
        get_mcp_capabilities_route,
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/capabilities",
        get_mcp_capabilities_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/capabilities/discover",
        discover_mcp_capabilities_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/capabilities/discover",
        discover_mcp_capabilities_route,
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/resources",
        list_mcp_resources_route,
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/resources",
        list_mcp_resources_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/resources/read",
        read_mcp_resource_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/resources/read",
        read_mcp_resource_route,
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/prompts",
        list_mcp_prompts_route,
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/prompts",
        list_mcp_prompts_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/prompts/{prompt_name}/render",
        render_mcp_prompt_route,
    )
    app.router.add_post(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/prompts/{prompt_name}/render",
        render_mcp_prompt_route,
    )

    # --- MCP Capability Policies (tool/resource/prompt) ---
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/capability-policies",
        list_mcp_capability_policies_route,
    )
    app.router.add_get(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/capability-policies",
        list_mcp_capability_policies_route,
    )
    app.router.add_put(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/capability-policies/{capability_kind}/{capability_name}",
        put_mcp_capability_policy_route,
    )
    app.router.add_put(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/capability-policies/{capability_kind}/{capability_name}",
        put_mcp_capability_policy_route,
    )
    app.router.add_delete(
        "/api/control-plane/agents/{agent_id}/mcp/connections/{server_key}/capability-policies/{capability_kind}/{capability_name}",
        delete_mcp_capability_policy_route,
    )
    app.router.add_delete(
        "/api/control-plane/agents/{agent_id}/connections/{connection_key}/capability-policies/{capability_kind}/{capability_name}",
        delete_mcp_capability_policy_route,
    )

    # --- Custom MCP Servers (system-wide + per-agent JSON registration) ---
    app.router.add_get("/api/control-plane/mcp/servers", list_custom_mcp_servers_route)
    app.router.add_post("/api/control-plane/mcp/servers", register_custom_mcp_server_route)
    app.router.add_post("/api/control-plane/mcp/servers/import", import_claude_desktop_mcp_route)
    app.router.add_get("/api/control-plane/mcp/servers/{server_key}", get_custom_mcp_server_route)
    app.router.add_delete("/api/control-plane/mcp/servers/{server_key}", delete_custom_mcp_server_route)
