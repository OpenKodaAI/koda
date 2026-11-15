"""Authorization matrix for the worker runtime API (M0-E3-T9, R-57).

The worker health server mounts the runtime inspection and control API through
``setup_runtime_routes``. No middleware guards it: each handler checks the
caller itself, through a short-lived ``X-Runtime-Token`` envelope signed with
``RUNTIME_LOCAL_UI_TOKEN``, scoped to one agent and to capabilities (``read``,
``mutate`` or ``attach``). One handler that forgets the check is an open route.

This module pins one authorization decision per route:

* ``RUNTIME_ROUTE_MATRIX`` gives the capability each runtime route requires and
  ``PUBLIC_ROUTES`` the probes that are public on purpose. A route on the worker
  health server app with no entry in either fails the inventory test.
* Every route answers 403, before it does any runtime work, to a request with
  no token, the raw base secret, a forged or tampered token, an expired token, a
  token for another agent, a token without the required capability, or any
  token while the worker has no secret. WebSocket routes refuse the upgrade.
* A read-only token cannot call a ``mutate`` or ``attach`` route.
* A token that holds exactly the required capability passes the check.

Known gap, pinned as a strict xfail (``_EMPTY_AGENT_SCOPE_GAP``): the agent
check is skipped when the token has no agent scope or the worker has no
``AGENT_ID``, so such a token passes on every route.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta
from typing import Any, NamedTuple
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import WSServerHandshakeError, web
from aiohttp.test_utils import TestClient, TestServer

import koda.config as config_module
import koda.services.health as health_module
import koda.services.runtime.api as runtime_api
from koda.services.runtime_access_service import RuntimeAccessService

_SECRET = "matrix-worker-runtime-secret"
_FOREIGN_SECRET = "not-the-worker-secret"
_AGENT = "AGENT_A"
_OTHER_AGENT = "AGENT_B"

READ = "read"
MUTATE = "mutate"
ATTACH = "attach"
_ALL_CAPABILITIES = frozenset({READ, MUTATE, ATTACH})


class Decision(NamedTuple):
    """Capability a route requires, and whether it is a WebSocket upgrade."""

    capability: str
    websocket: bool = False


RUNTIME_ROUTE_MATRIX: dict[tuple[str, str], Decision] = {
    # Inspection reads.
    ("GET", "/api/runtime/readiness"): Decision(READ),
    ("GET", "/api/runtime/queues"): Decision(READ),
    ("GET", "/api/runtime/environments"): Decision(READ),
    ("GET", "/api/runtime/environments/{env_id}"): Decision(READ),
    ("GET", "/api/runtime/schedules"): Decision(READ),
    ("GET", "/api/runtime/schedules/{job_id}"): Decision(READ),
    ("GET", "/api/runtime/schedules/preview"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/run-graph"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/replay"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/sandbox-doctor"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/events"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/artifacts"): Decision(READ),
    ("GET", "/api/runtime/artifacts/{artifact_id}/download"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/checkpoints"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/terminals"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/browser"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/browser/screenshot"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/workspace/tree"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/workspace/file"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/workspace/search"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/workspace/status"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/workspace/diff"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/services"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/resources"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/loop"): Decision(READ),
    ("GET", "/api/runtime/tasks/{task_id}/sessions"): Decision(READ),
    # Event streams. The terminal and browser sockets also need an attach
    # session token (see test_attach_websocket_refuses_an_upgrade_without_its_attach_session).
    ("GET", "/api/runtime/stream"): Decision(READ),
    ("GET", "/ws/runtime"): Decision(READ, websocket=True),
    ("GET", "/ws/runtime/events"): Decision(READ, websocket=True),
    ("GET", "/ws/runtime/tasks/{task_id}/terminals/{terminal_id}"): Decision(READ, websocket=True),
    ("GET", "/ws/runtime/tasks/{task_id}/browser"): Decision(READ, websocket=True),
    # Writes and control.
    ("POST", "/api/runtime/schedules"): Decision(MUTATE),
    ("PATCH", "/api/runtime/schedules/{job_id}"): Decision(MUTATE),
    ("POST", "/api/runtime/schedules/{job_id}/actions/{action}"): Decision(MUTATE),
    ("POST", "/api/runtime/sessions/messages"): Decision(MUTATE),
    ("POST", "/api/runtime/sessions/{session_id}/cancel"): Decision(MUTATE),
    ("POST", "/api/runtime/sessions/{session_id}/pause"): Decision(MUTATE),
    ("POST", "/api/runtime/sessions/{session_id}/resume"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/cancel"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/interrupt"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/retry"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/recover"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/pause"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/resume"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/save"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/pin"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/unpin"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/cleanup"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/cleanup/force"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/workspace/write"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/workspace/create"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/workspace/delete"): Decision(MUTATE),
    ("POST", "/api/runtime/tasks/{task_id}/workspace/rename"): Decision(MUTATE),
    ("POST", "/api/runtime/processes/{process_id}/terminate"): Decision(MUTATE),
    # Operator attach sessions (they hand out a terminal or browser attach token).
    ("POST", "/api/runtime/tasks/{task_id}/attach/terminal"): Decision(ATTACH),
    ("POST", "/api/runtime/tasks/{task_id}/attach/browser"): Decision(ATTACH),
}

# Routes on the worker health server that take no runtime token, with the reason.
PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/health"): "liveness probe for the supervisor and container healthchecks (F-MON-01)",
    ("GET", "/ready"): "readiness probe for the supervisor and orchestrators (F-MON-01)",
    ("GET", "/metrics"): "Prometheus scrape endpoint (F-MON-01)",
}

# Values used to turn a route template into a request path.
_SAMPLE_PATH_PARAMS = {
    "action": "pause",
    "artifact_id": "artifact-1",
    "env_id": "2",
    "job_id": "3",
    "process_id": "5",
    "session_id": "session-1",
    "task_id": "7",
    "terminal_id": "4",
}

_ERRORS = {
    "missing": "missing runtime token",
    "invalid": "invalid runtime token",
    "unconfigured": "runtime UI token is not configured",
}


# --------------------------------------------------------------------------- #
# Worker health server app
# --------------------------------------------------------------------------- #


class _CapturingRunner:
    """Stands in for ``web.AppRunner`` so the test keeps the app it was given."""

    def __init__(self, app: web.Application, *_args: Any, **_kwargs: Any) -> None:
        self.app = app

    async def setup(self) -> None:
        return None

    async def cleanup(self) -> None:
        return None


class _UnboundSite:
    """Stands in for ``web.TCPSite`` so no port is bound."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def start(self) -> None:
        return None


async def _build_worker_health_app() -> web.Application:
    """Return the app ``start_health_server`` builds, with the runtime API on."""
    with (
        patch.object(health_module.web, "AppRunner", _CapturingRunner),
        patch.object(health_module.web, "TCPSite", _UnboundSite),
        patch.object(config_module, "RUNTIME_FRONTEND_API_ENABLED", True),
        patch.object(health_module, "_runner", None),
    ):
        await health_module.start_health_server()
        runner = health_module._runner
    assert isinstance(runner, _CapturingRunner)
    return runner.app


def _registered_routes(app: web.Application) -> dict[tuple[str, str], Callable[..., Any]]:
    routes: dict[tuple[str, str], Callable[..., Any]] = {}
    for route in app.router.routes():
        assert route.resource is not None, f"route without a resource: {route!r}"
        key = (route.method, route.resource.canonical)
        assert key not in routes, f"route registered twice: {key[0]} {key[1]}"
        routes[key] = route.handler
    return routes


def _routes_without_decision(app: web.Application) -> list[str]:
    """Registered routes that are neither in the matrix nor on the public list.

    aiohttp registers a HEAD twin for every GET route and serves it with the GET
    handler, so a HEAD route inherits the decision of its GET twin.
    """
    routes = _registered_routes(app)
    decided = set(RUNTIME_ROUTE_MATRIX) | set(PUBLIC_ROUTES)
    undecided: list[str] = []
    for (method, path), handler in sorted(routes.items()):
        if method == "HEAD" and ("GET", path) in decided and routes.get(("GET", path)) is handler:
            continue
        if (method, path) not in decided:
            undecided.append(f"{method} {path}")
    return undecided


def _concrete_path(template: str) -> str:
    try:
        return template.format_map(_SAMPLE_PATH_PARAMS)
    except KeyError as exc:
        raise AssertionError(f"add a sample value for {exc} to _SAMPLE_PATH_PARAMS") from exc


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #


def _token(
    *capabilities: str,
    agent: str = _AGENT,
    secret: str = _SECRET,
    sensitive: bool = False,
) -> str:
    _envelope, token = RuntimeAccessService(secret).issue(
        agent_scope=agent,
        capabilities=capabilities,
        sensitive_allowed=sensitive,
    )
    return token


class _OneHourAgo(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        return datetime.now(tz) - timedelta(hours=1)


def _expired_token(*capabilities: str) -> str:
    # ``issue`` enforces a 60 s minimum lifetime, so sign it an hour in the past.
    with patch("koda.services.runtime_access_service.datetime", _OneHourAgo):
        return _token(*capabilities)


def _signed_with_an_empty_key(*capabilities: str) -> str:
    """A token signed with an empty key, as anyone can compute one.

    RuntimeAccessService refuses an empty key (M1-E1-T6), but HMAC does not, so re-sign a
    genuine payload by hand.
    """
    encoded_payload, _signature = _token(*capabilities).split(".", 1)
    payload = base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4))
    signature = base64.urlsafe_b64encode(hmac.new(b"", payload, hashlib.sha256).digest()).decode().rstrip("=")
    return f"{encoded_payload}.{signature}"


def _tampered_token() -> str:
    """A genuine read token whose payload was edited to grant every capability."""
    encoded_payload, signature = _token(READ).split(".", 1)
    payload = json.loads(base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4)))
    payload["capabilities"] = sorted(_ALL_CAPABILITIES)
    edited = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{edited}.{signature}"


class Rejection(NamedTuple):
    headers: dict[str, str]
    error: str
    worker_secret: str = _SECRET
    worker_agent: str | None = _AGENT


# ``RuntimeAccessService.authorize`` compares agent scopes only when both sides
# have one: ``if envelope.agent_scope and agent_scope not in {"", envelope.agent_scope}``.
_EMPTY_AGENT_SCOPE_GAP = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "New defect found in the M0-E3-T9 review, not yet registered (no D- id or owning task; it needs a new "
        "SEC task, and M1-E1-T6 already changes koda/services/runtime_access_service.py): "
        "RuntimeAccessService.authorize treats an empty agent scope as a wildcard on both sides. A token "
        "signed without an agent scope passes on every worker, and a worker without AGENT_ID accepts a token "
        "for any agent. RUNTIME_LOCAL_UI_TOKEN is one global secret, so the agent scope is the only boundary "
        "between agents. No issuer signs an empty scope today and the supervisor always sets AGENT_ID. "
        "The fix must also re-sign the tokens in tests/test_services/runtime/test_api.py, which use an empty scope."
    ),
)


def _rejection(case: str, required: str) -> Rejection:
    all_caps = sorted(_ALL_CAPABILITIES)
    if case == "no-token":
        return Rejection({}, _ERRORS["missing"])
    if case == "raw-base-secret":
        return Rejection({"X-Runtime-Token": _SECRET}, _ERRORS["invalid"])
    if case == "forged-signature":
        return Rejection({"X-Runtime-Token": _token(*all_caps, secret=_FOREIGN_SECRET)}, _ERRORS["invalid"])
    if case == "tampered-payload":
        return Rejection({"X-Runtime-Token": _tampered_token()}, _ERRORS["invalid"])
    if case == "expired":
        return Rejection({"X-Runtime-Token": _expired_token(*all_caps)}, _ERRORS["invalid"])
    if case == "other-agent":
        return Rejection({"X-Runtime-Token": _token(*all_caps, agent=_OTHER_AGENT)}, _ERRORS["invalid"])
    if case == "lacks-capability":
        others = sorted(_ALL_CAPABILITIES - {required})
        return Rejection({"X-Runtime-Token": _token(*others)}, _ERRORS["invalid"])
    if case == "worker-without-secret":
        # The worker never signs with an empty key, so a token signed with one is refused too.
        return Rejection(
            {"X-Runtime-Token": _signed_with_an_empty_key(*all_caps)},
            _ERRORS["unconfigured"],
            worker_secret="",
        )
    if case == "token-without-agent-scope":
        return Rejection({"X-Runtime-Token": _token(*all_caps, agent="")}, _ERRORS["invalid"])
    if case == "worker-without-agent-id":
        return Rejection(
            {"X-Runtime-Token": _token(*all_caps, agent=_OTHER_AGENT)},
            _ERRORS["invalid"],
            worker_agent=None,
        )
    if case == "worker-with-empty-agent-id":
        # ``AGENT_ID=`` in the environment gives an empty string, not None.
        return Rejection(
            {"X-Runtime-Token": _token(*all_caps, agent=_OTHER_AGENT)},
            _ERRORS["invalid"],
            worker_agent="",
        )
    raise AssertionError(f"unknown rejection case {case}")


_REJECTION_CASES = (
    "no-token",
    "raw-base-secret",
    "forged-signature",
    "tampered-payload",
    "expired",
    "other-agent",
    "lacks-capability",
    "worker-without-secret",
    pytest.param("token-without-agent-scope", marks=_EMPTY_AGENT_SCOPE_GAP, id="token-without-agent-scope"),
    pytest.param("worker-without-agent-id", marks=_EMPTY_AGENT_SCOPE_GAP, id="worker-without-agent-id"),
    pytest.param("worker-with-empty-agent-id", marks=_EMPTY_AGENT_SCOPE_GAP, id="worker-with-empty-agent-id"),
)


# --------------------------------------------------------------------------- #
# Fixtures and request helper
# --------------------------------------------------------------------------- #


class _RuntimeReached(RuntimeError):
    """Raised by the runtime controller stub when a request should never have reached it."""


@pytest.fixture
def controller_factory(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Configure the worker secret and agent; record any reach into the runtime."""
    factory = MagicMock(name="get_runtime_controller")
    monkeypatch.setattr(runtime_api, "RUNTIME_LOCAL_UI_TOKEN", _SECRET)
    monkeypatch.setattr(runtime_api, "AGENT_ID", _AGENT)
    monkeypatch.setattr(runtime_api, "get_runtime_controller", factory)
    return factory


@pytest.fixture
async def worker_app() -> web.Application:
    return await _build_worker_health_app()


@pytest.fixture
async def client(worker_app: web.Application, controller_factory: MagicMock) -> AsyncIterator[TestClient]:
    async with TestClient(TestServer(worker_app)) as test_client:
        yield test_client


async def _send(
    client: TestClient,
    method: str,
    template: str,
    decision: Decision,
    headers: dict[str, str],
) -> tuple[int, object]:
    """Send one request; a WebSocket route is called as an upgrade."""
    path = _concrete_path(template)
    if decision.websocket and method == "GET":
        try:
            ws = await client.ws_connect(path, headers=headers)
        except WSServerHandshakeError as exc:
            return exc.status, None
        await ws.close()
        return 101, None
    async with client.request(method, path, headers=headers) as response:
        if response.content_type == "application/json":
            return response.status, await response.json()
        return response.status, await response.text()


def _route_params(*capabilities: str) -> list[Any]:
    return [
        pytest.param(method, path, decision, id=f"{method} {path}")
        for (method, path), decision in RUNTIME_ROUTE_MATRIX.items()
        if not capabilities or decision.capability in capabilities
    ]


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #


async def test_every_registered_route_has_an_authorization_decision(worker_app: web.Application) -> None:
    assert _routes_without_decision(worker_app) == []
    registered = set(_registered_routes(worker_app))
    stale = sorted(f"{method} {path}" for method, path in {*RUNTIME_ROUTE_MATRIX, *PUBLIC_ROUTES} - registered)
    assert stale == [], "matrix entries for routes the worker no longer registers"


def test_setup_runtime_routes_registers_exactly_the_matrix() -> None:
    # The public list only covers the probes; no runtime route may hide in it.
    app = web.Application()
    runtime_api.setup_runtime_routes(app)
    registered = {key for key in _registered_routes(app) if key[0] != "HEAD"}
    assert registered == set(RUNTIME_ROUTE_MATRIX)
    assert not set(PUBLIC_ROUTES) & registered


async def test_a_route_registered_without_a_decision_fails_the_inventory() -> None:
    async def _undecided(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app = await _build_worker_health_app()
    before = _routes_without_decision(app)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/undecided", _undecided)
    app.router.add_post("/api/runtime/undecided", _undecided)

    added = [route for route in _routes_without_decision(app) if route not in before]
    assert added == [
        "GET /api/runtime/tasks/{task_id}/undecided",
        "HEAD /api/runtime/tasks/{task_id}/undecided",
        "POST /api/runtime/undecided",
    ]


# --------------------------------------------------------------------------- #
# Token checks, per route
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("case", _REJECTION_CASES)
@pytest.mark.parametrize(("method", "path", "decision"), _route_params())
async def test_route_rejects_a_request_without_a_valid_token(
    client: TestClient,
    controller_factory: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    decision: Decision,
    case: str,
) -> None:
    rejection = _rejection(case, decision.capability)
    monkeypatch.setattr(runtime_api, "RUNTIME_LOCAL_UI_TOKEN", rejection.worker_secret)
    monkeypatch.setattr(runtime_api, "AGENT_ID", rejection.worker_agent)
    # A request that wrongly passes the check stops at the runtime (aiohttp answers
    # 500) instead of running the rest of the handler against a stub.
    controller_factory.side_effect = _RuntimeReached(f"{method} {path} reached the runtime")

    status, body = await _send(client, method, path, decision, rejection.headers)

    assert status == 403
    if not decision.websocket:
        assert body == {"error": rejection.error}
    assert not controller_factory.called, "the route reached the runtime before the token check"


@pytest.mark.parametrize(("method", "path", "decision"), _route_params(READ))
async def test_head_request_without_a_token_is_rejected(
    client: TestClient,
    controller_factory: MagicMock,
    method: str,
    path: str,
    decision: Decision,
) -> None:
    # aiohttp answers HEAD with the GET handler, so it must carry the same check.
    status, _body = await _send(client, "HEAD", path, decision, {})

    assert status == 403
    assert not controller_factory.called


@pytest.mark.parametrize(("method", "path", "decision"), _route_params(MUTATE, ATTACH))
async def test_read_only_token_cannot_call_a_privileged_route(
    client: TestClient,
    controller_factory: MagicMock,
    method: str,
    path: str,
    decision: Decision,
) -> None:
    status, body = await _send(client, method, path, decision, {"X-Runtime-Token": _token(READ)})

    assert status == 403
    assert body == {"error": _ERRORS["invalid"]}
    assert not controller_factory.called


@pytest.mark.parametrize(("method", "path", "decision"), _route_params())
async def test_token_with_the_required_capability_passes_the_check(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    decision: Decision,
) -> None:
    """The real check accepts the token, and asks for exactly the matrix capability.

    The handler stops right after the check, so no runtime work runs.
    """
    real_check = runtime_api._authorize_runtime_access
    outcomes: list[tuple[str, bool]] = []

    def _recording_check(request: web.Request, *, capability: str = READ) -> web.Response | None:
        rejection = real_check(request, capability=capability)
        outcomes.append((capability, rejection is None))
        return rejection or web.json_response({"authorized": capability})

    monkeypatch.setattr(runtime_api, "_authorize_runtime_access", _recording_check)

    status, body = await _send(client, method, path, decision, {"X-Runtime-Token": _token(decision.capability)})

    assert outcomes == [(decision.capability, True)]
    if not decision.websocket:
        assert (status, body) == (200, {"authorized": decision.capability})


# --------------------------------------------------------------------------- #
# Second-layer checks
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("path", "attach_kind", "session"),
    [
        pytest.param("/ws/runtime/tasks/7/terminals/4", "terminal", None, id="terminal-no-session"),
        pytest.param(
            "/ws/runtime/tasks/7/terminals/4",
            "terminal",
            {"task_id": 8, "terminal_id": 4},
            id="terminal-session-for-another-task",
        ),
        pytest.param(
            "/ws/runtime/tasks/7/terminals/4",
            "terminal",
            {"task_id": 7, "terminal_id": 5},
            id="terminal-session-for-another-terminal",
        ),
        pytest.param("/ws/runtime/tasks/7/browser", "browser", None, id="browser-no-session"),
        pytest.param("/ws/runtime/tasks/7/browser", "browser", {"task_id": 8}, id="browser-session-for-another-task"),
    ],
)
async def test_attach_websocket_refuses_an_upgrade_without_its_attach_session(
    client: TestClient,
    controller_factory: MagicMock,
    path: str,
    attach_kind: str,
    session: dict[str, int] | None,
) -> None:
    controller = controller_factory.return_value
    controller.authorize_attach.return_value = session
    headers = {"X-Runtime-Token": _token(READ), "X-Koda-Attach-Token": "attach-token"}

    with pytest.raises(WSServerHandshakeError) as excinfo:
        await client.ws_connect(path, headers=headers)

    assert excinfo.value.status == 403
    controller.authorize_attach.assert_called_once_with(token="attach-token", attach_kind=attach_kind)
    controller.close_attach_session.assert_not_called()


def _scope_headers(case: str) -> dict[str, str]:
    if case == "no-scope-token":
        return {}
    if case == "scope-not-sensitive":
        return {"X-Runtime-Access-Scope": _token(READ)}
    if case == "other-agent":
        return {"X-Runtime-Access-Scope": _token(READ, agent=_OTHER_AGENT, sensitive=True)}
    if case == "forged-signature":
        return {"X-Runtime-Access-Scope": _token(READ, secret=_FOREIGN_SECRET, sensitive=True)}
    if case == "scope-without-agent-scope":
        return {"X-Runtime-Access-Scope": _token(READ, agent="", sensitive=True)}
    raise AssertionError(f"unknown scope case {case}")


@pytest.mark.parametrize(
    "case",
    [
        "no-scope-token",
        "scope-not-sensitive",
        "other-agent",
        "forged-signature",
        pytest.param("scope-without-agent-scope", marks=_EMPTY_AGENT_SCOPE_GAP, id="scope-without-agent-scope"),
    ],
)
async def test_task_detail_sensitive_view_requires_a_sensitive_scope_token(
    client: TestClient,
    controller_factory: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    controller = controller_factory.return_value
    controller.store.get_task_runtime.return_value = {"id": 7, "agent_id": _AGENT}
    headers = {"X-Runtime-Token": _token(READ), **_scope_headers(case)}
    real_check = runtime_api._authorize_sensitive_runtime_access

    def _stop_after_the_check(request: web.Request, *, agent_scope: str) -> web.Response:
        # A scope the real check accepts ends the handler here, before the sensitive reads.
        return real_check(request, agent_scope=agent_scope) or web.json_response({"sensitive": "authorized"})

    monkeypatch.setattr(runtime_api, "_authorize_sensitive_runtime_access", _stop_after_the_check)

    async with client.get("/api/runtime/tasks/7?include_sensitive=true", headers=headers) as response:
        assert response.status == 403
        body = await response.json()

    expected = (
        "sensitive runtime access requires scoped token" if case == "no-scope-token" else "invalid runtime access scope"
    )
    assert body == {"error": expected}
    controller.store.get_task_runtime.assert_called_once_with(7)
