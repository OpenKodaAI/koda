"""HTTP endpoints for runtime inspection and control."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import cast
from uuid import uuid4

from aiohttp import WSMsgType, web

import koda.services.health as health_module
from koda.config import AGENT_ID, RUNTIME_LOCAL_UI_TOKEN
from koda.logging_config import get_logger
from koda.services.metrics import RUNTIME_WS_CLIENTS_ACTIVE
from koda.services.runtime.constants import MUTATION_BLOCKED_PHASES
from koda.services.runtime.controller import get_runtime_controller
from koda.services.runtime.redaction import redact_value
from koda.services.runtime_access_service import RuntimeAccessService

log = get_logger(__name__)


class _SilentRuntimeMessage:
    """Minimal Telegram message stand-in for dashboard-originated turns."""

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.message_id = int(hashlib.sha1(text.encode()).hexdigest()[:8], 16) or 1

    async def edit_text(self, text: str, *_args: object, **_kwargs: object) -> _SilentRuntimeMessage:
        self.text = text
        return self

    async def delete(self, *_args: object, **_kwargs: object) -> None:
        return None


class _SilentRuntimeBot:
    """No-op agent surface so dashboard chat does not emit Telegram side effects."""

    async def send_message(self, *_args: object, text: str = "", **_kwargs: object) -> _SilentRuntimeMessage:
        return _SilentRuntimeMessage(text=text)

    async def send_document(
        self,
        *_args: object,
        caption: str | None = None,
        **_kwargs: object,
    ) -> _SilentRuntimeMessage:
        return _SilentRuntimeMessage(text=caption or "")

    async def send_voice(self, *_args: object, caption: str | None = None, **_kwargs: object) -> _SilentRuntimeMessage:
        return _SilentRuntimeMessage(text=caption or "")

    async def send_chat_action(self, *_args: object, **_kwargs: object) -> None:
        return None

    async def delete_message(self, *_args: object, **_kwargs: object) -> None:
        return None


def _authorize_runtime_access(
    request: web.Request,
    *,
    capability: str = "read",
) -> web.Response | None:
    token = RUNTIME_LOCAL_UI_TOKEN.strip()
    if not token:
        return web.json_response({"error": "runtime UI token is not configured"}, status=403)
    headers = getattr(request, "headers", {})
    request_token = headers.get("X-Runtime-Token", "").strip()
    if not request_token:
        return web.json_response({"error": "missing runtime token"}, status=403)
    envelope = RuntimeAccessService(token).authorize(
        request_token,
        agent_scope=str(AGENT_ID or "").strip().upper(),
        capability=capability,
    )
    if envelope is None:
        return web.json_response({"error": "invalid runtime token"}, status=403)
    return None


def _is_mutation_allowed(task_id: int) -> tuple[bool, str | None]:
    controller = get_runtime_controller()
    task = controller.store.get_task_runtime(task_id)
    phase = str(task.get("current_phase") or "") if task else ""
    if phase in MUTATION_BLOCKED_PHASES:
        return False, phase
    return True, phase


def _authorize_mutation(request: web.Request) -> web.Response | None:
    return _authorize_runtime_access(request, capability="mutate")


async def _json_payload(request: web.Request) -> dict[str, object]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text="invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise web.HTTPBadRequest(text="JSON payload must be an object")
    return cast(dict[str, object], payload)


def _dashboard_actor_id(*, namespace: str, session_id: str) -> int:
    seed = f"{AGENT_ID}:{namespace}:{session_id}".encode()
    return 1_000_000_000 + int(hashlib.sha1(seed).hexdigest()[:12], 16) % 900_000_000


def _include_sensitive(request: web.Request) -> bool:
    return request.query.get("include_sensitive", "false").strip().lower() == "true"


def _authorize_sensitive_runtime_access(request: web.Request, *, agent_scope: str) -> web.Response | None:
    if not _include_sensitive(request):
        return None
    scope_token = request.headers.get("X-Runtime-Access-Scope", "").strip()
    if not scope_token:
        return web.json_response({"error": "sensitive runtime access requires scoped token"}, status=403)
    token = RUNTIME_LOCAL_UI_TOKEN.strip()
    envelope = RuntimeAccessService(token).authorize(
        scope_token,
        agent_scope=agent_scope,
        sensitive_required=True,
    )
    if envelope is None:
        return web.json_response({"error": "invalid runtime access scope"}, status=403)
    return None


def _parse_positive_int(
    raw_value: str | None,
    *,
    name: str,
    default: int,
    minimum: int = 1,
    maximum: int = 1000,
) -> int:
    if raw_value is None or raw_value == "":
        value = default
    else:
        value = int(raw_value)
    if value < minimum or value > maximum:
        raise web.HTTPBadRequest(text=f"invalid {name}")
    return value


def _tail_text(path: Path, *, max_bytes: int = 4096) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        data = handle.read()
    return data.decode("utf-8", errors="replace")


def _latest_browser_preview_path(task_id: int) -> Path | None:
    controller = get_runtime_controller()
    image_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    candidates: list[Path] = []

    for artifact in controller.store.list_artifacts(task_id):
        path_value = artifact.get("path")
        if not path_value:
            continue
        path = Path(str(path_value))
        if path.is_file() and path.suffix.lower() in image_suffixes:
            candidates.append(path)

    task_root = controller.runtime_root / "tasks" / str(task_id)
    if task_root.exists():
        for relative in ("browser", "artifacts", "checkpoints"):
            base = task_root / relative
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file() and path.suffix.lower() in image_suffixes:
                    candidates.append(path)

    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _browser_payload(task_id: int) -> dict[str, object]:
    controller = get_runtime_controller()
    browser = dict(controller.get_browser_snapshot(task_id))
    preview_path = _latest_browser_preview_path(task_id)
    browser["screenshot_url"] = f"/api/runtime/tasks/{task_id}/browser/screenshot"
    browser["preview_url"] = str(browser["screenshot_url"])
    browser["preview_available"] = preview_path is not None or (
        bool(browser) and not bool(browser.get("session_persisted_only"))
    )
    if preview_path is not None:
        browser["preview_path"] = str(preview_path)
    return browser


async def _runtime_queues(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    return web.json_response({"items": get_runtime_controller().store.list_runtime_queues()})


async def _runtime_environments(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    return web.json_response({"items": get_runtime_controller().store.list_environments()})


async def _runtime_readiness(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    controller = get_runtime_controller()
    snapshot_getter = getattr(controller, "get_runtime_health_snapshot", None) or getattr(
        controller,
        "get_runtime_snapshot",
        None,
    )
    runtime_snapshot, payload = health_module.normalize_runtime_surfaces(
        dict(snapshot_getter()) if callable(snapshot_getter) else {},
        dict(controller.get_runtime_readiness()),
    )
    try:
        payload["startup"] = health_module.get_runtime_startup_state()
    except Exception:
        log.exception("runtime_readiness_startup_state_failed")
        payload["startup"] = {"phase": "unknown", "details": {}, "expected_background_loops": []}
    try:
        payload["background_loops"] = health_module._background_loop_health()
    except Exception:
        log.exception("runtime_readiness_background_loops_failed")
        payload["background_loops"] = {
            "started": False,
            "ready": False,
            "critical_ready": False,
            "error": "background loop health unavailable",
            "loops": {},
        }
    try:
        from koda.knowledge.runtime_supervisor import get_knowledge_runtime_supervisor

        resolved_agent_id = str(AGENT_ID or "").strip() or None
        payload["knowledge_v2"] = await get_knowledge_runtime_supervisor(resolved_agent_id).health()
    except Exception:
        log.exception("runtime_readiness_knowledge_v2_failed")
        payload["knowledge_v2"] = {
            "storage_mode": "unknown",
            "primary_read_enabled": False,
            "external_read_enabled": False,
            "primary_backend": {"enabled": False, "ready": False, "pool_active": False},
            "object_store": {"enabled": False, "ready": False},
            "ingest_worker": {"enabled": False, "ready": False, "queue": {"enabled": False, "ready": False}},
        }
    payload["runtime"] = runtime_snapshot
    payload["runtime_kernel"] = cast(dict[str, object], payload.get("runtime_kernel") or {})
    payload["ready"] = bool(payload.get("ready", True)) and bool(
        payload["background_loops"].get("critical_ready", True)
    )
    payload["ready"] = payload["ready"] and str(payload["startup"].get("phase") or "") == "ready"
    payload["status"] = "ready" if payload["ready"] else "not_ready"
    if not payload["ready"] and not payload.get("reason"):
        reasons = [str(item) for item in payload.get("reasons") or [] if str(item).strip()]
        if str(payload["startup"].get("phase") or "") != "ready":
            payload["reason"] = "startup_incomplete"
        elif not bool(payload["background_loops"].get("critical_ready", True)):
            payload["reason"] = "background_loop_supervision_unavailable"
        elif reasons:
            payload["reason"] = reasons[0]
    return web.json_response(payload)


async def _runtime_environment_detail(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    env_id = int(request.match_info["env_id"])
    env = get_runtime_controller().store.get_environment(env_id)
    if env is None:
        return web.json_response({"error": "environment not found"}, status=404)
    return web.json_response(env)


async def _runtime_task_detail(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    controller = get_runtime_controller()
    task = controller.store.get_task_runtime(task_id)
    if task is None:
        return web.json_response({"error": "task not found"}, status=404)
    sensitive_auth = _authorize_sensitive_runtime_access(
        request,
        agent_scope=str(task.get("agent_id") or AGENT_ID or "").strip().upper(),
    )
    if sensitive_auth is not None:
        return sensitive_auth
    episode = None
    retrieval_trace = None
    answer_trace = None
    artifact_evidence: list[dict[str, object]] = []
    asset_refs: list[dict[str, object]] = []
    runtime_kernel_snapshot: dict[str, object] | None = None
    resolved_agent_id = str(task.get("agent_id") or AGENT_ID or "").strip() or None
    try:
        runtime_kernel_snapshot = await controller.get_runtime_kernel_snapshot(task_id=task_id)
    except Exception:
        log.exception("runtime_task_detail_kernel_snapshot_failed", task_id=task_id)
    try:
        from koda.state.knowledge_governance_store import get_latest_execution_episode

        episode = get_latest_execution_episode(task_id) or episode
    except Exception:
        log.exception("runtime_task_detail_episode_load_failed", task_id=task_id)
    try:
        from koda.knowledge.repository import KnowledgeRepository
        from koda.knowledge.storage_v2 import KnowledgeStorageV2

        storage = KnowledgeStorageV2(KnowledgeRepository(resolved_agent_id), resolved_agent_id)
        retrieval_trace_id = (
            int(episode["retrieval_trace_id"]) if episode and episode.get("retrieval_trace_id") else None
        )
        if retrieval_trace_id is not None:
            try:
                retrieval_trace = await storage.get_retrieval_trace_async(retrieval_trace_id) or retrieval_trace
            except Exception:
                log.exception("runtime_task_detail_retrieval_trace_load_failed", task_id=task_id)
        if retrieval_trace is None:
            try:
                trace_rows = await storage.list_retrieval_traces_async(task_id=task_id, limit=1)
                if trace_rows:
                    retrieval_trace = trace_rows[0]
            except Exception:
                log.exception("runtime_task_detail_retrieval_trace_list_failed", task_id=task_id)
        try:
            answer_trace = await storage.get_latest_answer_trace_async(task_id) or answer_trace
        except Exception:
            log.exception("runtime_task_detail_answer_trace_load_failed", task_id=task_id)
        try:
            artifact_evidence = (
                cast(
                    list[dict[str, object]],
                    await storage.list_artifact_evidence_rows_async(
                        task_id=task_id,
                        project_key=str(task.get("project_key") or ""),
                        workspace_fingerprint=str(task.get("workspace_fingerprint") or ""),
                        limit=40,
                    ),
                )
                or artifact_evidence
            )
        except Exception:
            log.exception("runtime_task_detail_artifact_evidence_load_failed", task_id=task_id)
    except Exception:
        log.exception("runtime_task_detail_knowledge_storage_init_failed", task_id=task_id)
    try:
        from koda.services.agent_asset_registry import get_agent_asset_registry

        asset_refs = cast(
            list[dict[str, object]],
            await get_agent_asset_registry(str(task.get("agent_id") or AGENT_ID or "").strip() or None).search(
                query=str(task.get("query_text") or ""),
                user_id=int(task.get("user_id") or 0),
                work_dir=str(task.get("work_dir") or ""),
                project_key=str(task.get("project_key") or ""),
                workspace_fingerprint=str(task.get("workspace_fingerprint") or ""),
                task_id=task_id,
                limit=8,
            ),
        )
    except Exception:
        log.exception("runtime_task_detail_asset_registry_failed", task_id=task_id)
    from koda.knowledge.presentation import redact_runtime_knowledge_payload

    return web.json_response(
        {
            "task": task,
            "environment": controller.store.get_environment_by_task(task_id),
            "runtime_kernel": runtime_kernel_snapshot,
            "warnings": controller.store.list_warnings(task_id),
            "guardrails": controller.list_guardrail_hits(task_id),
            "knowledge": redact_runtime_knowledge_payload(
                episode=episode,
                retrieval_trace=retrieval_trace,
                answer_trace=answer_trace,
                artifact_evidence=artifact_evidence,
                include_sensitive=_include_sensitive(request),
            ),
            "asset_refs": asset_refs,
        }
    )


async def _runtime_task_events(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    after_seq = _parse_positive_int(request.query.get("after_seq"), name="after_seq", default=0, minimum=0)
    items = get_runtime_controller().store.list_events(task_id=task_id, after_seq=after_seq)
    return web.json_response({"items": items})


async def _runtime_task_artifacts(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    return web.json_response({"items": get_runtime_controller().store.list_artifacts(task_id)})


async def _runtime_task_checkpoints(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    return web.json_response({"items": get_runtime_controller().store.list_checkpoints(task_id)})


async def _runtime_task_terminals(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    controller = get_runtime_controller()
    terminals = controller.store.list_terminals(task_id)
    enriched = []
    for terminal in terminals:
        path = terminal.get("path")
        preview = ""
        if path and Path(str(path)).exists():
            preview = _tail_text(Path(str(path)))
        enriched.append({**terminal, "preview": redact_value(preview)})
    return web.json_response({"items": enriched})


async def _runtime_task_browser(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    controller = get_runtime_controller()
    return web.json_response(
        {
            "browser": _browser_payload(task_id),
            "sessions": controller.store.list_browser_sessions(task_id),
        }
    )


async def _runtime_task_browser_screenshot(request: web.Request) -> web.StreamResponse:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    controller = get_runtime_controller()
    env = controller.store.get_environment_by_task(task_id)
    if env is None:
        return web.json_response({"error": "environment not found"}, status=404)
    preview_path = _latest_browser_preview_path(task_id)
    if preview_path is not None:
        response = web.FileResponse(preview_path)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response
    browser_snapshot = controller.get_browser_snapshot(task_id)
    if browser_snapshot.get("screenshot_path"):
        screenshot_path = Path(str(browser_snapshot["screenshot_path"]))
        if screenshot_path.is_file():
            response = web.FileResponse(screenshot_path)
            response.headers["Cache-Control"] = "no-store, max-age=0"
            return response
    return web.json_response({"error": "browser screenshot unavailable"}, status=404)


async def _runtime_task_workspace_tree(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    relative_path = request.query.get("path", "")
    return web.json_response(
        {"items": get_runtime_controller().get_workspace_tree(task_id, relative_path=relative_path)}
    )


async def _runtime_task_workspace_file(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    relative_path = request.query.get("path", "")
    if not relative_path:
        return web.json_response({"error": "missing path"}, status=400)
    try:
        payload = get_runtime_controller().read_workspace_file(task_id, relative_path=relative_path)
    except (FileNotFoundError, ValueError) as exc:
        return web.json_response({"error": str(exc)}, status=404)
    return web.json_response(payload or {"error": "environment not found"})


async def _runtime_task_workspace_status(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    return web.json_response(get_runtime_controller().get_workspace_status(task_id))


async def _runtime_task_workspace_diff(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    relative_path = request.query.get("path")
    return web.json_response(get_runtime_controller().get_workspace_diff(task_id, relative_path=relative_path))


async def _runtime_task_services(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    return web.json_response({"items": get_runtime_controller().list_service_endpoints(task_id)})


async def _runtime_task_resources(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    return web.json_response({"items": get_runtime_controller().list_resource_samples(task_id)})


async def _runtime_task_loop(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    controller = get_runtime_controller()
    return web.json_response(
        {
            "cycles": controller.list_loop_cycles(task_id),
            "guardrails": controller.list_guardrail_hits(task_id),
        }
    )


async def _runtime_task_sessions(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    return web.json_response(get_runtime_controller().list_sessions(task_id))


async def _runtime_stream_sse(request: web.Request) -> web.StreamResponse:
    auth = _authorize_runtime_access(request)
    if auth:
        return auth
    task_id = request.query.get("task_id")
    env_id = request.query.get("env_id")
    after_seq = _parse_positive_int(request.query.get("after_seq"), name="after_seq", default=0, minimum=0)
    controller = get_runtime_controller()
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
    await response.prepare(request)
    async for event in controller.events.iter_events(
        task_id=int(task_id) if task_id else None,
        env_id=int(env_id) if env_id else None,
        after_seq=after_seq,
    ):
        await response.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
    return response


async def _runtime_stream_ws(request: web.Request) -> web.WebSocketResponse:
    auth = _authorize_runtime_access(request)
    if auth:
        raise web.HTTPForbidden(text=json.dumps({"error": "invalid runtime token"}))
    task_id = request.query.get("task_id")
    env_id = request.query.get("env_id")
    after_seq = _parse_positive_int(request.query.get("after_seq"), name="after_seq", default=0, minimum=0)
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    controller = get_runtime_controller()
    RUNTIME_WS_CLIENTS_ACTIVE.inc()
    try:
        async for event in controller.events.iter_events(
            task_id=int(task_id) if task_id else None,
            env_id=int(env_id) if env_id else None,
            after_seq=after_seq,
        ):
            await ws.send_json(event)
    finally:
        RUNTIME_WS_CLIENTS_ACTIVE.dec()
    return ws


async def _runtime_terminal_ws(request: web.Request) -> web.WebSocketResponse:
    auth = _authorize_runtime_access(request)
    if auth:
        raise web.HTTPForbidden(text=json.dumps({"error": "invalid runtime token"}))
    task_id = int(request.match_info["task_id"])
    terminal_id = int(request.match_info["terminal_id"])
    token = request.query.get("token", "")
    session = get_runtime_controller().authorize_attach(token=token, attach_kind="terminal")
    if session is None or int(session["task_id"]) != task_id or int(session.get("terminal_id") or 0) != terminal_id:
        raise web.HTTPForbidden(text="invalid terminal attach session")
    controller = get_runtime_controller()
    can_write = bool(int(session.get("can_write") or 0))
    after_offset = int(request.query.get("after_offset", "0"))
    terminal_row = next(
        (item for item in controller.store.list_terminals(task_id) if int(item["id"]) == terminal_id),
        None,
    )
    kernel_session_id = str(request.query.get("session_id", "") or "").strip()
    if not kernel_session_id and terminal_row is not None:
        kernel_session_id = controller._terminal_kernel_session_id(terminal_row)
    kernel_backed = bool(kernel_session_id) and controller._runtime_kernel_terminal_authoritative()
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    RUNTIME_WS_CLIENTS_ACTIVE.inc()

    async def _consume_client() -> None:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            if not can_write:
                continue
            if kernel_backed:
                payload: object
                try:
                    payload = json.loads(msg.data)
                except Exception:
                    payload = msg.data
                if isinstance(payload, dict) and str(payload.get("type") or "") == "resize":
                    await controller.resize_terminal_session(
                        task_id=task_id,
                        terminal_id=terminal_id,
                        cols=int(payload.get("cols") or 120),
                        rows=int(payload.get("rows") or 40),
                    )
                    continue
                if isinstance(payload, dict) and str(payload.get("type") or "") == "close":
                    await controller.close_terminal_session(
                        task_id=task_id,
                        terminal_id=terminal_id,
                        force=bool(payload.get("force", False)),
                    )
                    await ws.close()
                    continue
                if isinstance(payload, dict) and str(payload.get("type") or "") == "input":
                    raw_text = str(payload.get("data") or "")
                else:
                    raw_text = msg.data
                await controller.write_terminal_input(task_id=task_id, terminal_id=terminal_id, text=raw_text)
                continue
            await controller.write_terminal_input(task_id=task_id, terminal_id=terminal_id, text=msg.data)

    reader_task = asyncio.create_task(_consume_client())
    try:
        if kernel_backed:
            async for payload in controller.iter_terminal_stream(
                task_id=task_id,
                terminal_id=terminal_id,
                after_offset=after_offset,
            ):
                outbound = dict(payload)
                if "data" in outbound:
                    outbound["data"] = redact_value(outbound["data"])
                await ws.send_json(outbound)
        else:
            async for payload in controller.iter_terminal_stream(
                task_id=task_id,
                terminal_id=terminal_id,
                after_offset=after_offset,
            ):
                outbound = dict(payload)
                if "data" in outbound:
                    outbound["data"] = redact_value(outbound["data"])
                await ws.send_json(outbound)
    finally:
        reader_task.cancel()
        await controller.close_attach_session(token=token)
        RUNTIME_WS_CLIENTS_ACTIVE.dec()
    return ws


async def _runtime_browser_ws(request: web.Request) -> web.WebSocketResponse:
    auth = _authorize_runtime_access(request)
    if auth:
        raise web.HTTPForbidden(text=json.dumps({"error": "invalid runtime token"}))
    task_id = int(request.match_info["task_id"])
    token = request.query.get("token", "")
    session = get_runtime_controller().authorize_attach(token=token, attach_kind="browser")
    if session is None or int(session["task_id"]) != task_id:
        raise web.HTTPForbidden(text="invalid browser attach session")
    controller = get_runtime_controller()
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    RUNTIME_WS_CLIENTS_ACTIVE.inc()
    try:
        while not ws.closed:
            await ws.send_json({"type": "browser.snapshot", "browser": _browser_payload(task_id)})
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                if msg.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                    break
            except TimeoutError:
                continue
    finally:
        await controller.close_attach_session(token=token)
        RUNTIME_WS_CLIENTS_ACTIVE.dec()
    return ws


async def _runtime_cancel(request: web.Request) -> web.Response:
    auth = _authorize_mutation(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    allowed, phase = _is_mutation_allowed(task_id)
    if not allowed:
        return web.json_response({"error": f"mutations blocked during {phase}"}, status=409)
    result = await get_runtime_controller().cancel_task(task_id=task_id, actor="runtime_api")
    if result is None:
        return web.json_response({"error": "task not found"}, status=404)
    return web.json_response(result)


async def _runtime_retry(request: web.Request) -> web.Response:
    auth = _authorize_mutation(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    allowed, phase = _is_mutation_allowed(task_id)
    if not allowed:
        return web.json_response({"error": f"mutations blocked during {phase}"}, status=409)
    result = await get_runtime_controller().retry_task(task_id=task_id, actor="runtime_api")
    if result is None:
        return web.json_response({"error": "retry unavailable"}, status=409)
    return web.json_response(result)


async def _runtime_recover(request: web.Request) -> web.Response:
    auth = _authorize_mutation(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    result = await get_runtime_controller().recover_task(task_id=task_id, actor="runtime_api")
    if result is None:
        return web.json_response({"error": "recover unavailable"}, status=409)
    return web.json_response(result)


async def _runtime_send_session_message(request: web.Request) -> web.Response:
    auth = _authorize_mutation(request)
    if auth:
        return auth

    controller = get_runtime_controller()
    application = getattr(controller, "_application", None)
    if application is None:
        return web.json_response({"error": "runtime application is not ready"}, status=503)

    payload = await _json_payload(request)
    text = str(payload.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "text is required"}, status=400)

    session_id = str(payload.get("session_id") or "").strip() or f"session-{uuid4().hex}"
    user_id = _dashboard_actor_id(namespace="dashboard-user", session_id=session_id)
    chat_id = -_dashboard_actor_id(namespace="dashboard-chat", session_id=session_id)

    from koda.services.queue_manager import build_runtime_context, enqueue_dashboard_chat_task
    from koda.state.history_store import get_session_runtime_defaults
    from koda.utils.command_helpers import get_provider_model, init_user_data, normalize_provider

    context = build_runtime_context(application, user_id, bot_override=_SilentRuntimeBot())
    init_user_data(context.user_data, user_id=user_id)
    context.user_data["session_id"] = session_id

    remembered = get_session_runtime_defaults(session_id)
    if remembered:
        remembered_provider, remembered_model = remembered
        if remembered_provider:
            normalized_provider = normalize_provider(remembered_provider)
            context.user_data["provider"] = normalized_provider
            if remembered_model:
                context.user_data.setdefault("manual_models_by_provider", {})[normalized_provider] = remembered_model
                context.user_data["model"] = remembered_model

    provider = normalize_provider(cast(str | None, context.user_data.get("provider")))
    model = get_provider_model(context.user_data, provider)
    work_dir = str(context.user_data.get("work_dir") or "")

    task_id = await enqueue_dashboard_chat_task(
        application=application,
        user_id=user_id,
        chat_id=chat_id,
        query_text=text,
        provider=provider,
        model=model,
        work_dir=work_dir,
        session_id=session_id,
        bot_override=_SilentRuntimeBot(),
    )
    return web.json_response(
        {
            "accepted": True,
            "session_id": session_id,
            "task_id": task_id,
        },
        status=202,
    )


async def _runtime_pause(request: web.Request) -> web.Response:
    auth = _authorize_mutation(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    reason = request.query.get("reason", "paused from runtime API")
    ok = await get_runtime_controller().pause_environment(task_id=task_id, reason=reason)
    return web.json_response({"ok": ok})


async def _runtime_resume(request: web.Request) -> web.Response:
    auth = _authorize_mutation(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    ok = await get_runtime_controller().resume_environment(task_id=task_id)
    return web.json_response({"ok": ok})


async def _runtime_save(request: web.Request) -> web.Response:
    auth = _authorize_mutation(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    env = await get_runtime_controller().save_snapshot(task_id=task_id)
    if env is None:
        return web.json_response({"error": "environment not found"}, status=404)
    return web.json_response({"ok": True, "environment": env})


async def _runtime_attach_terminal(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request, capability="attach")
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    controller = get_runtime_controller()
    terminal_id = request.query.get("terminal_id")
    can_write = request.query.get("write", "true").lower() == "true"
    terminal_row: dict[str, object] | None = None
    if terminal_id:
        terminals = controller.store.list_terminals(task_id)
        terminal_row = next((item for item in terminals if int(item["id"]) == int(terminal_id)), None)
    if terminal_row is None:
        terminal_row = await controller.start_operator_terminal(task_id=task_id)
    if terminal_row is None:
        return web.json_response({"error": "unable to start terminal"}, status=409)
    terminal_row_id = int(cast(int | str, terminal_row["id"]))
    attach = await controller.create_attach_session(
        task_id=task_id,
        attach_kind="terminal",
        terminal_id=terminal_row_id,
        can_write=can_write,
    )
    if attach is None:
        return web.json_response({"error": "unable to create attach session"}, status=409)
    return web.json_response(
        {
            "attach": attach,
            "terminal": {
                **terminal_row,
                **(
                    {"kernel_session_id": attach["kernel_session_id"]}
                    if str(attach.get("kernel_session_id") or "").strip()
                    else {}
                ),
            },
            "ws_url": (
                f"/ws/runtime/tasks/{task_id}/terminals/{terminal_row_id}?token={attach['token']}"
                + (
                    f"&session_id={attach['kernel_session_id']}"
                    if str(attach.get("kernel_session_id") or "").strip()
                    else ""
                )
            ),
        }
    )


async def _runtime_attach_browser(request: web.Request) -> web.Response:
    auth = _authorize_runtime_access(request, capability="attach")
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    controller = get_runtime_controller()
    attach = await controller.create_attach_session(task_id=task_id, attach_kind="browser", can_write=False)
    if attach is None:
        return web.json_response({"error": "environment not found"}, status=404)
    browser = controller.get_browser_snapshot(task_id)
    return web.json_response(
        {
            "attach": attach,
            "browser": _browser_payload(task_id),
            "ws_url": f"/ws/runtime/tasks/{task_id}/browser?token={attach['token']}",
            "novnc_url": browser.get("novnc_url"),
        }
    )


async def _runtime_pin(request: web.Request, *, pinned: bool) -> web.Response:
    auth = _authorize_mutation(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    result = await get_runtime_controller().pin_environment(task_id=task_id, pinned=pinned)
    if not result:
        return web.json_response({"error": "environment not found"}, status=404)
    return web.json_response({"ok": True, "pinned": pinned})


async def _runtime_cleanup(request: web.Request, *, force: bool) -> web.Response:
    auth = _authorize_mutation(request)
    if auth:
        return auth
    task_id = int(request.match_info["task_id"])
    allowed, phase = _is_mutation_allowed(task_id)
    if not allowed and not force:
        return web.json_response({"error": f"mutations blocked during {phase}"}, status=409)
    result = await get_runtime_controller().request_cleanup(task_id=task_id, force=force)
    if not result:
        return web.json_response({"error": "cleanup blocked"}, status=409)
    return web.json_response({"ok": True, "force": force})


async def _runtime_pin_true(request: web.Request) -> web.Response:
    return await _runtime_pin(request, pinned=True)


async def _runtime_pin_false(request: web.Request) -> web.Response:
    return await _runtime_pin(request, pinned=False)


async def _runtime_cleanup_normal(request: web.Request) -> web.Response:
    return await _runtime_cleanup(request, force=False)


async def _runtime_cleanup_force(request: web.Request) -> web.Response:
    return await _runtime_cleanup(request, force=True)


async def _runtime_process_terminate(request: web.Request) -> web.Response:
    auth = _authorize_mutation(request)
    if auth:
        return auth
    process_id = int(request.match_info["process_id"])
    force = request.query.get("force", "false").lower() == "true"
    result = await get_runtime_controller().terminate_process(process_id=process_id, force=force)
    if result is None:
        return web.json_response({"error": "process not found"}, status=404)
    if not result.get("ok"):
        return web.json_response(result, status=409)
    return web.json_response(result)


def setup_runtime_routes(app: web.Application) -> None:
    """Register runtime inspection routes on the shared aiohttp app."""
    app.router.add_get("/api/runtime/readiness", _runtime_readiness)
    app.router.add_get("/api/runtime/queues", _runtime_queues)
    app.router.add_get("/api/runtime/environments", _runtime_environments)
    app.router.add_get("/api/runtime/environments/{env_id:\\d+}", _runtime_environment_detail)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}", _runtime_task_detail)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/events", _runtime_task_events)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/artifacts", _runtime_task_artifacts)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/checkpoints", _runtime_task_checkpoints)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/terminals", _runtime_task_terminals)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/browser", _runtime_task_browser)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/browser/screenshot", _runtime_task_browser_screenshot)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/workspace/tree", _runtime_task_workspace_tree)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/workspace/file", _runtime_task_workspace_file)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/workspace/status", _runtime_task_workspace_status)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/workspace/diff", _runtime_task_workspace_diff)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/services", _runtime_task_services)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/resources", _runtime_task_resources)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/loop", _runtime_task_loop)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/sessions", _runtime_task_sessions)
    app.router.add_get("/api/runtime/stream", _runtime_stream_sse)
    app.router.add_get("/ws/runtime", _runtime_stream_ws)
    app.router.add_get("/ws/runtime/events", _runtime_stream_ws)
    app.router.add_get("/ws/runtime/tasks/{task_id:\\d+}/terminals/{terminal_id:\\d+}", _runtime_terminal_ws)
    app.router.add_get("/ws/runtime/tasks/{task_id:\\d+}/browser", _runtime_browser_ws)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/cancel", _runtime_cancel)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/retry", _runtime_retry)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/recover", _runtime_recover)
    app.router.add_post("/api/runtime/sessions/messages", _runtime_send_session_message)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/pause", _runtime_pause)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/resume", _runtime_resume)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/save", _runtime_save)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/attach/terminal", _runtime_attach_terminal)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/attach/browser", _runtime_attach_browser)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/pin", _runtime_pin_true)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/unpin", _runtime_pin_false)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/cleanup", _runtime_cleanup_normal)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/cleanup/force", _runtime_cleanup_force)
    app.router.add_post("/api/runtime/processes/{process_id:\\d+}/terminate", _runtime_process_terminate)
