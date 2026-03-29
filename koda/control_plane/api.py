"""aiohttp handlers for the control-plane API."""

from __future__ import annotations

import json
import secrets
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiohttp import ContentTypeError, web

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
    list_dashboard_session_summaries,
)
from .manager import get_control_plane_manager
from .onboarding import load_control_plane_openapi_spec, render_setup_page
from .settings import AGENT_SECTIONS, CONTROL_PLANE_API_TOKEN, DOCUMENT_KINDS


def _manager() -> Any:
    return get_control_plane_manager()


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


def _authorize_request(request: web.Request) -> web.Response | None:
    token = CONTROL_PLANE_API_TOKEN.strip()
    if not token:
        return None
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.startswith("Bearer "):
        return web.json_response({"error": "missing control plane token"}, status=401)
    request_token = auth_header.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(request_token, token):
        return web.json_response({"error": "invalid control plane token"}, status=403)
    return None


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
    return web.json_response(_manager().get_onboarding_status())


async def onboarding_bootstrap(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().complete_onboarding(payload))


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
            list_dashboard_session_summaries(
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
        payload = _manager().get_dashboard_session(
            request.match_info["agent_id"],
            request.match_info["session_id"],
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
    except RuntimeError as exc:
        return _service_unavailable(exc)


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


async def get_general_system_settings(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_general_system_settings())


async def put_general_system_settings(request: web.Request) -> web.Response:
    payload = await _json_payload(request)
    return web.json_response(_manager().put_general_system_settings(payload))


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


async def verify_provider_connection(request: web.Request) -> web.Response:
    return web.json_response(_manager().verify_provider_connection(request.match_info["provider_id"]))


async def disconnect_provider_connection(request: web.Request) -> web.Response:
    return web.json_response(_manager().disconnect_provider_connection(request.match_info["provider_id"]))


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
    secret = _manager().get_secret_asset(request.match_info["agent_id"], request.match_info["secret_key"], scope=scope)
    if secret is None:
        return web.json_response(
            {
                "scope": scope,
                "secret_key": request.match_info["secret_key"],
                "preview": "",
            }
        )
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


async def delete_secret(request: web.Request) -> web.Response:
    scope = request.query.get("scope", "agent")
    _manager().delete_secret_asset(request.match_info["agent_id"], request.match_info["secret_key"], scope=scope)
    return web.json_response({"ok": True})


async def get_runtime_access(request: web.Request) -> web.Response:
    return web.json_response(_manager().get_runtime_access(request.match_info["agent_id"]))


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


def register_legacy_bot_aliases(app: web.Application) -> None:
    """Keep legacy /bots surfaces working while /agents remains canonical."""

    aliases: list[tuple[str, str, Callable[[web.Request], Awaitable[web.StreamResponse]]]] = [
        ("get", "/api/control-plane/dashboard/bots/summary", list_dashboard_agent_summaries_route),
        ("get", "/api/control-plane/dashboard/bots/{agent_id}/summary", get_dashboard_agent_summary_route),
        ("get", "/api/control-plane/dashboard/bots/{agent_id}/stats", get_dashboard_agent_stats_route),
        ("get", "/api/control-plane/dashboard/bots/{agent_id}/executions", list_dashboard_agent_executions_route),
        (
            "get",
            "/api/control-plane/dashboard/bots/{agent_id}/executions/{task_id}",
            get_dashboard_execution_detail_route,
        ),
        ("get", "/api/control-plane/dashboard/bots/{agent_id}/sessions", list_dashboard_agent_sessions_route),
        (
            "post",
            "/api/control-plane/dashboard/bots/{agent_id}/sessions/messages",
            post_dashboard_session_message_route,
        ),
        (
            "get",
            "/api/control-plane/dashboard/bots/{agent_id}/sessions/{session_id}",
            get_dashboard_session_detail_route,
        ),
        ("get", "/api/control-plane/dashboard/bots/{agent_id}/dlq", list_dashboard_agent_dlq_route),
        ("get", "/api/control-plane/dashboard/bots/{agent_id}/costs", get_dashboard_agent_costs_route),
        ("get", "/api/control-plane/dashboard/bots/{agent_id}/schedules", list_dashboard_agent_schedules_route),
        ("get", "/api/control-plane/dashboard/bots/{agent_id}/cron", list_dashboard_agent_schedules_route),
        ("get", "/api/control-plane/dashboard/bots/{agent_id}/audit", list_dashboard_audit_route),
        ("get", "/api/control-plane/dashboard/bots/{agent_id}/memory-map", get_dashboard_memory_map),
        ("get", "/api/control-plane/dashboard/bots/{agent_id}/memory-curation", list_dashboard_memory_curation),
        (
            "get",
            "/api/control-plane/dashboard/bots/{agent_id}/memory-curation/{memory_id}",
            get_dashboard_memory_curation_detail,
        ),
        (
            "get",
            "/api/control-plane/dashboard/bots/{agent_id}/memory-curation/clusters/{cluster_id}",
            get_dashboard_memory_curation_cluster,
        ),
        (
            "post",
            "/api/control-plane/dashboard/bots/{agent_id}/memory-curation/actions",
            post_dashboard_memory_curation_action,
        ),
        ("get", "/api/control-plane/bots", list_agents),
        ("post", "/api/control-plane/bots", create_agent),
        ("get", "/api/control-plane/bots/{agent_id}", get_agent),
        ("patch", "/api/control-plane/bots/{agent_id}", patch_agent),
        ("delete", "/api/control-plane/bots/{agent_id}", delete_agent),
        ("post", "/api/control-plane/bots/{agent_id}/clone", clone_agent),
        ("post", "/api/control-plane/bots/{agent_id}/publish", publish_agent),
        ("post", "/api/control-plane/bots/{agent_id}/activate", activate_agent),
        ("post", "/api/control-plane/bots/{agent_id}/pause", pause_agent),
        ("get", "/api/control-plane/bots/{agent_id}/runtime-access", get_runtime_access),
        ("get", "/api/control-plane/bots/{agent_id}/agent-spec", get_agent_spec),
        ("put", "/api/control-plane/bots/{agent_id}/agent-spec", put_agent_spec),
        ("get", "/api/control-plane/bots/{agent_id}/compiled-prompt", get_compiled_prompt),
        ("post", "/api/control-plane/bots/{agent_id}/validate", validate_agent),
        ("post", "/api/control-plane/bots/{agent_id}/publish-checks", publish_checks),
        ("get", "/api/control-plane/bots/{agent_id}/tool-policy", get_tool_policy),
        ("put", "/api/control-plane/bots/{agent_id}/tool-policy", put_tool_policy),
        ("get", "/api/control-plane/bots/{agent_id}/model-policy", get_model_policy),
        ("put", "/api/control-plane/bots/{agent_id}/model-policy", put_model_policy),
        ("get", "/api/control-plane/bots/{agent_id}/autonomy-policy", get_autonomy_policy),
        ("put", "/api/control-plane/bots/{agent_id}/autonomy-policy", put_autonomy_policy),
        ("get", "/api/control-plane/bots/{agent_id}/knowledge-candidates", list_knowledge_candidates),
        (
            "post",
            "/api/control-plane/bots/{agent_id}/knowledge-candidates/{candidate_id}/approve",
            approve_knowledge_candidate,
        ),
        (
            "post",
            "/api/control-plane/bots/{agent_id}/knowledge-candidates/{candidate_id}/reject",
            reject_knowledge_candidate,
        ),
        ("get", "/api/control-plane/bots/{agent_id}/runbooks", list_runbooks),
        ("post", "/api/control-plane/bots/{agent_id}/runbooks/{runbook_id}/revalidate", revalidate_runbook),
        ("get", "/api/control-plane/bots/{agent_id}/retrieval-traces", list_retrieval_traces),
        ("get", "/api/control-plane/bots/{agent_id}/retrieval-traces/{trace_id}", get_retrieval_trace),
        ("get", "/api/control-plane/bots/{agent_id}/answer-traces", list_answer_traces),
        ("get", "/api/control-plane/bots/{agent_id}/answer-traces/{answer_trace_id}", get_answer_trace),
        ("get", "/api/control-plane/bots/{agent_id}/knowledge-graph", list_knowledge_graph),
        ("get", "/api/control-plane/bots/{agent_id}/evaluation-cases", list_evaluation_cases),
        ("post", "/api/control-plane/bots/{agent_id}/evaluation-cases/seed", seed_evaluation_cases),
        ("patch", "/api/control-plane/bots/{agent_id}/evaluation-cases/{case_key}", patch_evaluation_case),
        ("get", "/api/control-plane/bots/{agent_id}/knowledge-evals/runs", list_evaluation_runs),
        ("get", "/api/control-plane/bots/{agent_id}/sections/{section}", get_section),
        ("put", "/api/control-plane/bots/{agent_id}/sections/{section}", put_section),
        ("get", "/api/control-plane/bots/{agent_id}/documents/{kind}", get_document),
        ("post", "/api/control-plane/bots/{agent_id}/documents/{kind}", upsert_document),
        ("put", "/api/control-plane/bots/{agent_id}/documents/{kind}", upsert_document),
        ("delete", "/api/control-plane/bots/{agent_id}/documents/{kind}", delete_document),
        ("get", "/api/control-plane/bots/{agent_id}/knowledge-assets", list_knowledge_assets),
        ("post", "/api/control-plane/bots/{agent_id}/knowledge-assets", create_knowledge_asset),
        ("put", "/api/control-plane/bots/{agent_id}/knowledge-assets/{asset_id}", update_knowledge_asset),
        ("delete", "/api/control-plane/bots/{agent_id}/knowledge-assets/{asset_id}", delete_knowledge_asset),
        ("get", "/api/control-plane/bots/{agent_id}/templates", list_templates),
        ("post", "/api/control-plane/bots/{agent_id}/templates", create_template),
        ("put", "/api/control-plane/bots/{agent_id}/templates/{asset_id}", update_template),
        ("delete", "/api/control-plane/bots/{agent_id}/templates/{asset_id}", delete_template),
        ("get", "/api/control-plane/bots/{agent_id}/skills", list_skills),
        ("post", "/api/control-plane/bots/{agent_id}/skills", create_skill),
        ("put", "/api/control-plane/bots/{agent_id}/skills/{asset_id}", update_skill),
        ("delete", "/api/control-plane/bots/{agent_id}/skills/{asset_id}", delete_skill),
        ("get", "/api/control-plane/bots/{agent_id}/secrets/{secret_key}", get_secret),
        ("put", "/api/control-plane/bots/{agent_id}/secrets/{secret_key}", put_secret),
        ("delete", "/api/control-plane/bots/{agent_id}/secrets/{secret_key}", delete_secret),
    ]

    for method, path, handler in aliases:
        getattr(app.router, f"add_{method}")(path, handler)


def setup_control_plane_routes(app: web.Application) -> None:
    app.router.add_get("/", setup_landing)
    app.router.add_get("/setup", setup_page)
    app.router.add_get("/openapi/control-plane.json", control_plane_openapi)
    app.router.add_get("/api/control-plane/onboarding/status", onboarding_status)
    app.router.add_post("/api/control-plane/onboarding/bootstrap", onboarding_bootstrap)
    app.router.add_get("/api/control-plane/core/providers", get_core_providers)
    app.router.add_get("/api/control-plane/core/tools", get_core_tools)
    app.router.add_get("/api/control-plane/core/policies", get_core_policies)
    app.router.add_get("/api/control-plane/core/capabilities", get_core_capabilities)
    app.router.add_get("/api/control-plane/dashboard/agents/summary", list_dashboard_agent_summaries_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/summary", get_dashboard_agent_summary_route)
    app.router.add_get("/api/control-plane/dashboard/agents/{agent_id}/stats", get_dashboard_agent_stats_route)
    app.router.add_get("/api/control-plane/dashboard/executions", list_dashboard_executions_route)
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

    register_legacy_bot_aliases(app)
