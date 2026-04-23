"""HTTP health endpoint via aiohttp."""

import os
import shutil
import time
from collections.abc import Iterable
from typing import Any, cast

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

import koda.config as config_module
from koda.internal_rpc.common import parse_boolish
from koda.logging_config import get_logger
from koda.services.queue_manager import active_processes, agent_start_time, get_total_active_task_count
from koda.state.primary import get_primary_state_backend, postgres_primary_mode, run_coro_sync

log = get_logger(__name__)

_runner: web.AppRunner | None = None
_RUNTIME_STARTUP_STATE: dict[str, Any] = {
    "phase": "not_started",
    "updated_at": None,
    "details": {},
    "expected_background_loops": [],
}


def normalize_runtime_kernel_health(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize runtime-kernel health across Python and gRPC implementations."""
    raw = dict(payload or {})
    reported = bool(raw)
    mode = str(raw.get("mode") or "unknown")
    transport = str(raw.get("transport") or "unknown")
    remote = bool(raw.get("remote")) or transport not in {"in-process", "python", "unknown"}
    has_connected = "connected" in raw
    connected = bool(raw.get("connected", remote)) if has_connected else True
    if not remote:
        connected = True
    has_verified = "verified" in raw
    verified = bool(raw.get("verified", remote)) if has_verified else connected
    if not remote:
        verified = True
    base_ready = bool(raw.get("ready", False))
    ready = base_ready and connected
    startup_error = str(raw.get("startup_error") or "").strip() or None
    status = str(raw.get("status") or ("ready" if ready else "not_ready"))
    details = dict(cast(dict[str, Any], raw.get("details") or {}))
    rust_mode = mode == "rust"
    authoritative = parse_boolish(
        raw.get("authoritative", details.get("authoritative")),
        default=ready and (rust_mode or not remote),
    )
    production_ready = parse_boolish(
        raw.get("production_ready", details.get("production_ready")),
        default=ready and authoritative,
    )
    maturity = str(raw.get("maturity") or details.get("maturity") or status or "unknown")
    authority_scope = str(
        raw.get("authority_scope")
        or details.get("authority_scope")
        or ("full_runtime" if authoritative else "unavailable")
    )
    authoritative_ops_value = raw.get("authoritative_operations", details.get("authoritative_operations"))
    if isinstance(authoritative_ops_value, str):
        authoritative_operations = [item.strip() for item in authoritative_ops_value.split(",") if item.strip()]
    elif isinstance(authoritative_ops_value, (list, tuple, set)):
        authoritative_operations = [str(item).strip() for item in authoritative_ops_value if str(item).strip()]
    else:
        authoritative_operations = []
    if rust_mode and not authoritative_operations:
        authoritative_operations = [
            "create_environment",
            "start_task",
            "stream_terminal",
            "open_terminal",
            "write_terminal",
            "resize_terminal",
            "close_terminal",
            "stream_terminal_session",
            "terminate_task",
            "cleanup_environment",
            "start_browser_session",
            "stop_browser_session",
            "get_browser_session",
            "save_checkpoint",
            "get_checkpoint",
            "restore_checkpoint",
        ]
    full_authority = parse_boolish(
        raw.get("full_authority", details.get("full_authority")),
        default=authoritative and rust_mode,
    )
    partial_authority = parse_boolish(
        raw.get("partial_authority", details.get("partial_authority")),
        default=False,
    )
    blockers_value = raw.get("cutover_blockers", details.get("cutover_blockers"))
    if isinstance(blockers_value, str):
        cutover_blockers = [item.strip() for item in blockers_value.split(",") if item.strip()]
    elif isinstance(blockers_value, (list, tuple, set)):
        cutover_blockers = [str(item).strip() for item in blockers_value if str(item).strip()]
    else:
        cutover_blockers = []
    failure_reasons: list[str] = []
    if reported and startup_error:
        failure_reasons.append("runtime_kernel_startup_failed")
    if reported and remote and has_connected and not connected:
        failure_reasons.append("runtime_kernel_disconnected")
    elif reported and remote and connected and not ready:
        failure_reasons.append("runtime_kernel_unready")
    elif reported and not ready:
        failure_reasons.append("runtime_kernel_unavailable")
    cutover_state = str(raw.get("cutover_state") or "")
    if not cutover_state:
        cutover_state = "remote" if remote else "in_process"
        if remote and not connected:
            cutover_state = "remote_disconnected"
        elif remote and connected and not ready:
            cutover_state = "remote_unready"
        elif remote and connected and ready and authoritative:
            cutover_state = "remote_authoritative"
    return {
        **raw,
        "reported": reported,
        "mode": mode,
        "transport": transport,
        "remote": remote,
        "connected": connected,
        "verified": verified,
        "ready": ready,
        "status": status,
        "details": details,
        "authoritative": authoritative,
        "production_ready": production_ready,
        "cutover_allowed": ready and authoritative and production_ready,
        "maturity": maturity,
        "authority_scope": authority_scope,
        "authoritative_operations": authoritative_operations,
        "full_authority": full_authority,
        "partial_authority": partial_authority,
        "cutover_blockers": cutover_blockers,
        "startup_error": startup_error,
        "cutover_state": cutover_state,
        "failure_reasons": failure_reasons,
        "failure_reason": failure_reasons[0] if failure_reasons else None,
    }


def normalize_runtime_surfaces(
    snapshot: dict[str, Any] | None,
    readiness: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize runtime snapshot/readiness payloads without changing HTTP contract shape."""
    runtime_snapshot = dict(snapshot or {})
    runtime_readiness = dict(readiness or {})
    runtime_kernel = normalize_runtime_kernel_health(
        cast(
            dict[str, Any] | None,
            runtime_readiness.get("runtime_kernel")
            or runtime_readiness.get("internal_rpc")
            or runtime_snapshot.get("runtime_kernel")
            or runtime_snapshot.get("internal_rpc"),
        )
    )
    runtime_snapshot["runtime_kernel"] = runtime_kernel
    runtime_snapshot["internal_rpc"] = runtime_kernel
    runtime_readiness["runtime_kernel"] = runtime_kernel
    runtime_readiness["internal_rpc"] = runtime_kernel
    reasons = [str(item) for item in runtime_readiness.get("reasons") or [] if str(item).strip()]
    if runtime_kernel.get("reported") and not runtime_kernel["ready"]:
        if "runtime_kernel_unavailable" not in reasons:
            reasons.append("runtime_kernel_unavailable")
        for item in runtime_kernel.get("failure_reasons") or []:
            item_str = str(item).strip()
            if item_str and item_str not in reasons:
                reasons.append(item_str)
    runtime_readiness["reasons"] = reasons
    runtime_readiness["ready"] = bool(runtime_readiness.get("ready", True)) and (
        not runtime_kernel.get("reported") or bool(runtime_kernel["ready"])
    )
    return runtime_snapshot, runtime_readiness


def describe_runtime_readiness_failure(runtime_readiness: dict[str, Any]) -> str:
    """Map runtime readiness reasons to a stable user-facing failure description."""
    runtime_reasons = {str(item) for item in runtime_readiness.get("reasons") or [] if str(item).strip()}
    runtime_kernel = normalize_runtime_kernel_health(
        cast(dict[str, Any] | None, runtime_readiness.get("runtime_kernel") or runtime_readiness.get("internal_rpc"))
    )
    kernel_reasons = {
        str(item) for item in runtime_kernel.get("failure_reasons") or [] if str(item).strip()
    } | runtime_reasons
    if "runtime_kernel_unavailable" in runtime_reasons:
        if "runtime_kernel_startup_failed" in kernel_reasons:
            return "runtime kernel startup failed"
        if "runtime_kernel_disconnected" in kernel_reasons:
            return "runtime kernel disconnected"
        return "runtime kernel unavailable"
    return "runtime backend unavailable"


def set_runtime_startup_state(
    phase: str,
    *,
    details: dict[str, Any] | None = None,
    expected_background_loops: Iterable[str] | None = None,
) -> None:
    """Publish the current runtime startup phase for pure readiness checks."""
    _RUNTIME_STARTUP_STATE["phase"] = str(phase)
    _RUNTIME_STARTUP_STATE["updated_at"] = int(time.time())
    _RUNTIME_STARTUP_STATE["details"] = dict(details or {})
    if expected_background_loops is not None:
        _RUNTIME_STARTUP_STATE["expected_background_loops"] = sorted({str(item) for item in expected_background_loops})


def get_runtime_startup_state() -> dict[str, Any]:
    return {
        "phase": str(_RUNTIME_STARTUP_STATE.get("phase") or "unknown"),
        "updated_at": _RUNTIME_STARTUP_STATE.get("updated_at"),
        "details": dict(cast(dict[str, Any], _RUNTIME_STARTUP_STATE.get("details") or {})),
        "expected_background_loops": list(
            cast(list[str], _RUNTIME_STARTUP_STATE.get("expected_background_loops") or [])
        ),
    }


def _database_health() -> dict[str, Any]:
    """Return backend-aware database health for runtime readiness."""
    primary_backend = get_primary_state_backend()
    primary_health: dict[str, Any] = {
        "enabled": False,
        "ready": False,
        "pool_active": False,
    }
    if primary_backend is not None:
        try:
            primary_health = dict(run_coro_sync(primary_backend.health()) or primary_health)
        except Exception:
            primary_health = {
                "enabled": True,
                "ready": False,
                "pool_active": False,
                "error": "primary state backend health unavailable",
            }
    return {
        "backend": config_module.STATE_BACKEND,
        "ready": bool(primary_health.get("ready")) if postgres_primary_mode() else False,
        "primary_state_backend": primary_health,
    }


def _get_disk_usage() -> dict:
    """Return disk usage for SCRIPT_DIR as a dict with total/used/free in MB and percent used."""
    try:
        usage = shutil.disk_usage(str(config_module.SCRIPT_DIR))
        return {
            "total_mb": round(usage.total / (1024 * 1024)),
            "used_mb": round(usage.used / (1024 * 1024)),
            "free_mb": round(usage.free / (1024 * 1024)),
            "percent_used": round(usage.used / usage.total * 100, 1),
        }
    except Exception:
        return {"error": "unable to read disk usage"}


def _get_breaker_states() -> dict[str, str]:
    """Lazily import and return circuit breaker states."""
    try:
        from koda.services.resilience import get_breaker_states

        return get_breaker_states()
    except Exception:
        return {}


def _background_loop_health() -> dict[str, Any]:
    try:
        from koda.services.lifecycle_supervisor import get_background_loop_supervisor

        payload = get_background_loop_supervisor().snapshot()
    except Exception:
        payload = {"started": False, "ready": False, "error": "background loop health unavailable", "loops": {}}
    startup = get_runtime_startup_state()
    expected_loops = [str(item) for item in startup.get("expected_background_loops") or []]
    registered_loops = cast(dict[str, Any], payload.get("loops") or {})
    missing_expected_loops = [name for name in expected_loops if name not in registered_loops]
    enforce_expected_loops = str(startup.get("phase") or "") == "ready"
    expected_loops_ready = (not enforce_expected_loops) or not missing_expected_loops
    payload["expected_loops"] = expected_loops
    payload["missing_expected_loops"] = missing_expected_loops
    payload["expected_loops_enforced"] = enforce_expected_loops
    payload["expected_loops_ready"] = expected_loops_ready
    payload["ready"] = bool(payload.get("ready", True)) and expected_loops_ready
    payload["critical_ready"] = bool(payload.get("critical_ready", True)) and expected_loops_ready
    return payload


def _runtime_health_payload() -> tuple[dict[str, Any], dict[str, Any]]:
    """Return runtime snapshot and readiness payloads."""
    try:
        from koda.services.runtime import get_runtime_controller

        controller = get_runtime_controller()
        snapshot_getter = getattr(controller, "get_runtime_health_snapshot", None) or getattr(
            controller,
            "get_runtime_snapshot",
            None,
        )
        readiness = dict(controller.get_runtime_readiness())
        snapshot = dict(snapshot_getter()) if callable(snapshot_getter) else {}
        return normalize_runtime_surfaces(snapshot, readiness)
    except Exception:
        return normalize_runtime_surfaces(
            {"error": "runtime snapshot unavailable"},
            {
                "ready": False,
                "reasons": ["runtime_controller_unavailable"],
                "error": "runtime readiness unavailable",
            },
        )


async def _health_handler(request: web.Request) -> web.Response:
    """Deep health check: DB, circuit breakers, disk, tasks."""
    from koda.services.llm_runner import get_provider_health_snapshot
    from koda.services.scheduled_jobs import get_scheduler_snapshot

    uptime = int(time.time() - agent_start_time)
    active_task_count = get_total_active_task_count()

    database_health = _database_health()
    db_ok = bool(database_health["ready"])
    breaker_states = _get_breaker_states()
    any_breaker_open = any(s == "open" for s in breaker_states.values())
    provider_snapshot = await get_provider_health_snapshot()
    try:
        scheduler_snapshot = get_scheduler_snapshot()
    except Exception:
        scheduler_snapshot = {"error": "scheduler snapshot unavailable"}
    any_provider_ready = any(item.get("can_execute") for item in provider_snapshot.values())

    if not db_ok or (provider_snapshot and not any_provider_ready):
        status = "unhealthy"
    elif any_breaker_open:
        status = "degraded"
    else:
        status = "healthy"
    startup_state = get_runtime_startup_state()
    startup_phase = str(startup_state.get("phase") or "unknown")
    if startup_phase in {"bootstrapping", "not_started", "stopping"} and status == "healthy":
        status = "degraded"
    if startup_phase == "failed":
        status = "unhealthy"

    payload = {
        "status": status,
        "uptime_seconds": uptime,
        "active_processes": len([p for p in active_processes.values() if p.returncode is None]),
        "active_tasks": active_task_count,
        "database": database_health,
        "circuit_breakers": breaker_states,
        "providers": provider_snapshot,
        "scheduler": scheduler_snapshot,
        "disk": _get_disk_usage(),
        "startup": startup_state,
        "background_loops": _background_loop_health(),
    }
    runtime_snapshot, runtime_readiness = _runtime_health_payload()
    payload["runtime"] = runtime_snapshot
    payload["runtime_readiness"] = runtime_readiness
    if not runtime_readiness.get("ready", False) and status == "healthy":
        status = "degraded"
        payload["status"] = status
    try:
        from koda.knowledge.runtime_supervisor import get_knowledge_runtime_supervisor

        payload["knowledge_v2"] = await get_knowledge_runtime_supervisor().health()
    except Exception:
        payload["knowledge_v2"] = {"enabled": False, "ready": False, "error": "knowledge_v2 health unavailable"}
    background_loops = cast(dict[str, Any], payload["background_loops"])
    if not background_loops.get("critical_ready", True) and status == "healthy":
        status = "degraded"
        payload["status"] = status

    http_status = 503 if status == "unhealthy" else 200

    return web.json_response(payload, status=http_status)


async def _ready_handler(request: web.Request) -> web.Response:
    """Readiness check: can we accept requests? Verifies DB connectivity."""
    from koda.services.llm_runner import get_provider_health_snapshot
    from koda.services.scheduled_jobs import get_scheduler_snapshot

    startup_state = get_runtime_startup_state()
    if startup_state.get("phase") != "ready":
        return web.json_response(
            {
                "status": "not ready",
                "reason": "startup_incomplete",
                "startup": startup_state,
            },
            status=503,
        )
    database_health = _database_health()
    if not database_health["ready"]:
        return web.json_response(
            {
                "status": "not ready",
                "reason": "database unreachable",
                "database": database_health,
            },
            status=503,
        )
    provider_snapshot = await get_provider_health_snapshot()
    if provider_snapshot and not any(item.get("can_execute") for item in provider_snapshot.values()):
        return web.json_response(
            {"status": "not ready", "reason": "no provider can execute a new turn", "providers": provider_snapshot},
            status=503,
        )
    try:
        scheduler_snapshot = get_scheduler_snapshot()
    except Exception:
        scheduler_snapshot = {"error": "scheduler snapshot unavailable"}
    payload = {
        "status": "ready",
        "startup": startup_state,
        "database": database_health,
        "providers": provider_snapshot,
        "scheduler": scheduler_snapshot,
        "background_loops": _background_loop_health(),
    }
    runtime_snapshot, runtime_readiness = _runtime_health_payload()
    payload["runtime"] = runtime_snapshot
    payload["runtime_readiness"] = runtime_readiness
    if not runtime_readiness.get("ready", False):
        reason = describe_runtime_readiness_failure(runtime_readiness)
        return web.json_response(
            {
                "status": "not ready",
                "reason": reason,
                "runtime": runtime_snapshot,
                "runtime_readiness": runtime_readiness,
            },
            status=503,
        )
    background_loops = cast(dict[str, Any], payload["background_loops"])
    if not background_loops.get("critical_ready", True):
        return web.json_response(
            {
                "status": "not ready",
                "reason": "background loop supervision unavailable",
                "background_loops": background_loops,
            },
            status=503,
        )
    try:
        from koda.knowledge.runtime_supervisor import get_knowledge_runtime_supervisor

        knowledge_v2_payload = await get_knowledge_runtime_supervisor().health()
        payload["knowledge_v2"] = knowledge_v2_payload
        if knowledge_v2_payload.get("enabled") and not knowledge_v2_payload.get("ready"):
            return web.json_response(
                {
                    "status": "not ready",
                    "reason": "knowledge_v2 backend unavailable",
                    "knowledge_v2": knowledge_v2_payload,
                },
                status=503,
            )
    except Exception:
        payload["knowledge_v2"] = {"enabled": False, "ready": False, "error": "knowledge_v2 health unavailable"}
    return web.json_response(payload)


async def _metrics_handler(request: web.Request) -> web.Response:
    """Prometheus metrics endpoint."""
    return web.Response(body=generate_latest(), content_type=CONTENT_TYPE_LATEST)


async def start_health_server() -> None:
    """Start the health check HTTP server."""
    global _runner
    app = web.Application()
    app.router.add_get("/health", _health_handler)
    app.router.add_get("/ready", _ready_handler)
    app.router.add_get("/metrics", _metrics_handler)
    if config_module.RUNTIME_FRONTEND_API_ENABLED:
        from koda.services.runtime.api import setup_runtime_routes

        setup_runtime_routes(app)

    _runner = web.AppRunner(app)
    await _runner.setup()
    bind_addr = os.environ.get("HEALTH_BIND", "127.0.0.1")
    site = web.TCPSite(_runner, bind_addr, config_module.HEALTH_PORT)
    await site.start()
    log.info("health_server_started", port=config_module.HEALTH_PORT)


async def stop_health_server() -> None:
    """Stop the health check HTTP server."""
    global _runner
    if _runner:
        await _runner.cleanup()
        _runner = None
