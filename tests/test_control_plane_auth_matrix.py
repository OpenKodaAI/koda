"""Auth route matrix for the control-plane HTTP app.

Every route the supervisor serves gets three requests through the production middleware
stack (``ControlPlaneSupervisor.build_app``): one with no credentials, one with an unknown
bearer token and one with a valid operator session. A probe middleware added inside that
stack answers in place of the handler, so no handler runs and nothing is read or written.

Which routes are public is observed, never listed here. The observation is compared with
the records that must agree with it:

- the backend allowlist, ``_PUBLIC_CONTROL_PLANE_API_PATHS``;
- the operations marked ``security: []`` in ``docs/openapi/control-plane.json``;
- the dashboard lists in ``apps/web/src/proxy.ts`` and the BFF catch-all route.

A new route that answers without credentials therefore fails here until the OpenAPI
document marks it public.

One request per route cannot see every URL a dynamic route accepts. The middleware lets a
request through when its decoded path is an allowlist entry or sits under one, while the
router fills a parameter from the still-encoded path, where ``%2F`` stays one segment. A
parameter that starts at or before the end of an allowlist entry can therefore spell that
entry, so such routes are refused on their shape. HEAD routes have no OpenAPI operation of
their own; each must answer exactly like its GET twin.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from koda.control_plane import api as control_plane_api
from koda.control_plane import rate_limit
from koda.control_plane.operator_auth import OperatorAuthContext
from koda.control_plane.supervisor import ControlPlaneSupervisor

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "docs" / "openapi" / "control-plane.json"
WEB_PROXY_PATH = ROOT / "apps" / "web" / "src" / "proxy.ts"
WEB_APP_DIR = ROOT / "apps" / "web" / "src" / "app"
WEB_CATCH_ALL_PATH = WEB_APP_DIR / "api" / "control-plane" / "[...path]" / "route.ts"

CONTROL_PLANE_PREFIX = "/api/control-plane/"
OPERATOR_TOKEN = "route-matrix-operator-token"
UNKNOWN_TOKEN = "route-matrix-unknown-token"
REACHED_HEADER = "X-Route-Matrix-Reached"
UNAUTHORIZED_BODY = {"error": "operator session is required"}
OPENAPI_METHODS = frozenset({"get", "put", "post", "delete", "patch"})
# A protected route that the traversal variants below aim at.
PROTECTED_TARGET = "/api/control-plane/agents"

# Supervisor-internal deploy hooks (docs/operations/cluster-mode.md). The OpenAPI document
# leaves them out; every other registered route must be documented there.
SUPERVISOR_INTERNAL_ROUTES = frozenset(
    {
        ("GET", "/cluster/status"),
        ("POST", "/cluster/drain"),
        ("POST", "/cluster/undrain"),
    }
)

# Paths the BFF catch-all forwards without an operator session although the backend
# requires one. New drift fails the test; resolved drift does not.
KNOWN_BFF_ONLY_PUBLIC_PATHS = frozenset(
    {
        # The catch-all forwards it without a session and the backend answers 401 (F-SET-16).
        "/api/control-plane/onboarding/readiness",
    }
)


@dataclass(frozen=True)
class RouteProbe:
    method: str
    path: str
    url: str
    anonymous_status: int
    anonymous_reached: str | None
    anonymous_body: Any
    unknown_token_status: int
    operator_status: int
    operator_reached: str | None

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path)

    @property
    def identity(self) -> str:
        return f"{self.method} {self.path}"

    @property
    def public(self) -> bool:
        return self.anonymous_reached is not None


@web.middleware
async def _answer_in_place_of_handler(request: web.Request, handler: Any) -> web.StreamResponse:
    """Innermost middleware: a request that gets here has passed every production one."""
    match_info = request.match_info
    if match_info.http_exception is not None:
        return await handler(request)  # the router's own 404 or 405
    route = match_info.route
    assert route.resource is not None
    return web.Response(status=204, headers={REACHED_HEADER: f"{route.method} {route.resource.canonical}"})


class _StubAuthService:
    """Knows one operator session token and nothing else."""

    def resolve_bearer_token(self, token: str) -> OperatorAuthContext | None:
        if token != OPERATOR_TOKEN:
            return None
        return OperatorAuthContext(
            auth_kind="session",
            subject_type="operator",
            user_id="route-matrix-user",
            username="route-matrix",
            email=None,
            display_name=None,
        )


def _build_supervisor_app() -> web.Application:
    with patch("koda.control_plane.supervisor.get_control_plane_manager", return_value=object()):
        supervisor = ControlPlaneSupervisor()
    app = supervisor.build_app()
    app.middlewares.append(_answer_in_place_of_handler)
    return app


def _sample_url(route: web.AbstractRoute) -> str:
    resource = route.resource
    assert resource is not None
    info = resource.get_info()
    if isinstance(resource, web.PlainResource):
        return str(info["path"])
    if isinstance(resource, web.DynamicResource):
        names = list(info["pattern"].groupindex)
        return str(resource.url_for(**{name: f"matrix-{name}" for name in names}))
    raise AssertionError(f"the route matrix cannot build a request for {resource!r}; extend _sample_url")


async def _send(client: TestClient, method: str, url: str, token: str | None) -> tuple[int, str | None, Any]:
    # Every request starts with fresh buckets: hundreds of 401s from one address would
    # otherwise trip the auth-failure limiter and turn into 429s.
    rate_limit.clear_limiters()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with client.request(method, url, headers=headers, allow_redirects=False) as response:
        body: Any = None
        if method != "HEAD" and response.content_type == "application/json":
            body = await response.json()
        return response.status, response.headers.get(REACHED_HEADER), body


async def _probe_routes(app: web.Application, routes: Iterable[web.AbstractRoute]) -> dict[tuple[str, str], RouteProbe]:
    probes: dict[tuple[str, str], RouteProbe] = {}
    targets = [(route.method, route.resource.canonical, _sample_url(route)) for route in routes if route.resource]
    with patch.object(control_plane_api, "_auth_service", _StubAuthService):
        async with TestClient(TestServer(app)) as client:
            for method, path, url in targets:
                anonymous_status, anonymous_reached, anonymous_body = await _send(client, method, url, None)
                unknown_token_status, _, _ = await _send(client, method, url, UNKNOWN_TOKEN)
                operator_status, operator_reached, _ = await _send(client, method, url, OPERATOR_TOKEN)
                probe = RouteProbe(
                    method=method,
                    path=path,
                    url=url,
                    anonymous_status=anonymous_status,
                    anonymous_reached=anonymous_reached,
                    anonymous_body=anonymous_body,
                    unknown_token_status=unknown_token_status,
                    operator_status=operator_status,
                    operator_reached=operator_reached,
                )
                assert probe.key not in probes, f"{probe.identity} is registered twice"
                probes[probe.key] = probe
    rate_limit.clear_limiters()
    return probes


@dataclass(frozen=True)
class RouteMatrix:
    registered_routes: int
    probes: dict[tuple[str, str], RouteProbe]

    def without_head(self) -> dict[tuple[str, str], RouteProbe]:
        return {key: probe for key, probe in self.probes.items() if probe.method != "HEAD"}


@pytest.fixture(scope="module")
def route_matrix() -> RouteMatrix:
    async def run() -> RouteMatrix:
        app = _build_supervisor_app()
        routes = list(app.router.routes())
        return RouteMatrix(registered_routes=len(routes), probes=await _probe_routes(app, routes))

    return asyncio.run(run())


def _openapi_public_operations() -> dict[tuple[str, str], bool]:
    """``(METHOD, path) -> True`` when the operation's effective security allows anonymous calls."""
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    default_security = spec.get("security", [])
    operations: dict[tuple[str, str], bool] = {}
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in OPENAPI_METHODS:
                continue
            security = operation.get("security", default_security)
            operations[(method.upper(), path)] = not security or any(not requirement for requirement in security)
    return operations


def _openapi_drift(probes: dict[tuple[str, str], RouteProbe], openapi: dict[tuple[str, str], bool]) -> list[str]:
    problems = []
    for key, probe in sorted(probes.items()):
        if probe.method == "HEAD" or key in SUPERVISOR_INTERNAL_ROUTES:
            continue
        documented_public = openapi.get(key)
        if documented_public is None:
            problems.append(f"{probe.identity}: registered but missing from the OpenAPI document")
        elif probe.public and not documented_public:
            problems.append(f"{probe.identity}: answers without credentials but the OpenAPI requires bearerAuth")
        elif documented_public and not probe.public:
            problems.append(f"{probe.identity}: the OpenAPI marks it security: [] but it requires an operator session")
    return problems


def _head_drift(probes: dict[tuple[str, str], RouteProbe]) -> list[str]:
    """HEAD routes whose anonymous answer differs from the GET route aiohttp runs for them."""
    problems = []
    for _key, probe in sorted(probes.items()):
        if probe.method != "HEAD":
            continue
        twin = probes.get(("GET", probe.path))
        if twin is None:
            problems.append(f"{probe.identity}: no GET twin to take its security from; extend the matrix")
        elif probe.public and not twin.public:
            problems.append(
                f"{probe.identity}: answers without credentials, but GET {probe.path} requires an operator session"
            )
        elif twin.public and not probe.public:
            problems.append(
                f"{probe.identity}: requires an operator session, but GET {probe.path} answers without credentials"
            )
    return problems


def _dynamic_routes_that_can_spell_a_public_path(
    resources: Iterable[web.AbstractResource], public_paths: Iterable[str]
) -> list[str]:
    """Dynamic routes with a parameter that some value turns into an allowlisted path.

    ``literal`` is the route up to its first parameter. When ``P + "/"`` starts with it, a
    value (with ``%2F`` for each slash) makes the decoded path ``P`` or ``P/...``.
    """
    problems = []
    entries = sorted(public_paths)
    for resource in resources:
        if not isinstance(resource, web.DynamicResource):
            continue
        literal = resource.canonical.partition("{")[0]
        problems += [
            f"{resource.canonical}: a parameter can spell the public path {public}"
            for public in entries
            if f"{public}/".startswith(literal)
        ]
    return problems


def _ts_string_set(path: Path, const_name: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"const {const_name} = new Set\(\[(.*?)\]\)", text, re.DOTALL)
    assert match, f"{const_name} not found in {path.relative_to(ROOT)}"
    entries = set(re.findall(r'"([^"]+)"', match.group(1)))
    assert entries, f"{const_name} in {path.relative_to(ROOT)} is empty"
    return entries


def _backend_allowlist() -> set[str]:
    return set(control_plane_api._PUBLIC_CONTROL_PLANE_API_PATHS)


def test_every_registered_route_is_probed_through_the_supervisor_stack(route_matrix: RouteMatrix) -> None:
    probes = route_matrix.probes
    assert len(probes) == route_matrix.registered_routes
    # The supervisor adds its own routes next to the API ones; both must be in the matrix.
    assert ("GET", "/health") in probes
    assert ("GET", PROTECTED_TARGET) in probes

    problems = []
    for probe in probes.values():
        if probe.operator_reached != probe.identity:
            problems.append(
                f"{probe.identity} ({probe.url}): an operator session got {probe.operator_status}, "
                f"reached {probe.operator_reached!r}"
            )
        elif probe.public:
            if probe.anonymous_reached != probe.identity:
                problems.append(f"{probe.identity}: an anonymous request reached {probe.anonymous_reached!r}")
        elif probe.anonymous_status != 401 or probe.unknown_token_status != 401:
            problems.append(
                f"{probe.identity}: expected 401 without a valid session, got {probe.anonymous_status} "
                f"(no token) and {probe.unknown_token_status} (unknown token)"
            )
        elif probe.method != "HEAD" and probe.anonymous_body != UNAUTHORIZED_BODY:
            problems.append(f"{probe.identity}: 401 body {probe.anonymous_body!r}")
    assert problems == [], "\n".join(problems)


def test_routes_answering_without_credentials_match_openapi_security_none(route_matrix: RouteMatrix) -> None:
    problems = _openapi_drift(route_matrix.probes, _openapi_public_operations())
    assert problems == [], "\n".join(problems)


def test_head_routes_answer_like_their_get_twin(route_matrix: RouteMatrix) -> None:
    assert any(probe.method == "HEAD" for probe in route_matrix.probes.values())
    problems = _head_drift(route_matrix.probes)
    assert problems == [], "\n".join(problems)


def test_no_dynamic_route_can_spell_a_public_path() -> None:
    resources = list(_build_supervisor_app().router.resources())
    assert any(isinstance(resource, web.DynamicResource) for resource in resources)
    problems = _dynamic_routes_that_can_spell_a_public_path(resources, _backend_allowlist())
    assert problems == [], (
        "the auth middleware would let some values of these parameters through without credentials; "
        "give each route a literal part that leaves every allowlist entry first:\n" + "\n".join(problems)
    )


def test_supervisor_internal_routes_are_registered_and_left_out_of_openapi(route_matrix: RouteMatrix) -> None:
    openapi = _openapi_public_operations()
    for key in SUPERVISOR_INTERNAL_ROUTES:
        assert key in route_matrix.probes, f"{key} is no longer registered; drop it from SUPERVISOR_INTERNAL_ROUTES"
        assert key not in openapi, f"{key} is documented now; drop it from SUPERVISOR_INTERNAL_ROUTES"


def test_backend_allowlist_equals_openapi_security_none_set() -> None:
    documented_public = {
        path
        for (_method, path), public in _openapi_public_operations().items()
        if public and path.startswith(CONTROL_PLANE_PREFIX)
    }
    assert _backend_allowlist() == documented_public


def test_backend_allowlist_entries_are_registered_public_routes(route_matrix: RouteMatrix) -> None:
    public_paths = {probe.path for probe in route_matrix.without_head().values() if probe.public}
    assert _backend_allowlist() - public_paths == set(), "allowlist entries that match no registered route"


def test_web_proxy_public_list_equals_backend_allowlist() -> None:
    assert _ts_string_set(WEB_PROXY_PATH, "PUBLIC_CONTROL_PLANE_PATHS") == _backend_allowlist()


def test_bff_catch_all_public_list_differs_from_backend_only_as_recorded() -> None:
    catch_all = {
        f"{CONTROL_PLANE_PREFIX}{entry}" for entry in _ts_string_set(WEB_CATCH_ALL_PATH, "PUBLIC_CONTROL_PLANE_PATHS")
    }
    backend = _backend_allowlist()

    assert catch_all - backend <= KNOWN_BFF_ONLY_PUBLIC_PATHS, "new BFF-only public path"
    # A public backend path the catch-all would reject must have its own BFF route,
    # which Next.js serves before the catch-all.
    missing_routes = [
        path for path in sorted(backend - catch_all) if not (WEB_APP_DIR / path.lstrip("/") / "route.ts").is_file()
    ]
    assert missing_routes == [], "public backend paths that the dashboard rejects before login"


@pytest.mark.xfail(
    strict=True,
    reason="D-033: /cluster/* sit outside /api/control-plane/, so the auth middleware skips them",
)
def test_cluster_drain_endpoints_require_an_operator_session(route_matrix: RouteMatrix) -> None:
    assert not route_matrix.probes[("POST", "/cluster/drain")].public
    assert not route_matrix.probes[("POST", "/cluster/undrain")].public


async def test_matrix_flags_new_routes_that_answer_without_credentials() -> None:
    """Adding an unauthenticated route must fail the matrix, even when it is documented."""

    async def new_handler(_request: web.Request) -> web.Response:
        raise AssertionError("the probe answers before any handler runs")

    app = _build_supervisor_app()
    under_public_prefix = f"{sorted(_backend_allowlist())[0]}/details"
    new_routes = [
        app.router.add_get(under_public_prefix, new_handler),
        app.router.add_get("/debug/state", new_handler),
        app.router.add_get("/api/control-plane/matrix-new", new_handler),
    ]
    probes = await _probe_routes(app, new_routes)

    # The author documents all three in the OpenAPI as ordinary, bearer-protected routes.
    assert _openapi_drift(probes, {key: False for key in probes}) == [
        f"GET {under_public_prefix}: answers without credentials but the OpenAPI requires bearerAuth",
        "GET /debug/state: answers without credentials but the OpenAPI requires bearerAuth",
    ]
    # Left undocumented, all three fail.
    assert len(_openapi_drift(probes, {})) == 3


async def test_matrix_flags_dynamic_routes_whose_parameter_can_spell_a_public_path() -> None:
    """The sample request of such a route gets 401; other values reach the handler anonymously."""

    async def new_handler(_request: web.Request) -> web.Response:
        raise AssertionError("the probe answers before any handler runs")

    public = sorted(_backend_allowlist())[0]
    parent, _, last = public.rpartition("/")
    encoded_tail = urllib.parse.quote(public.removeprefix(CONTROL_PLANE_PREFIX), safe="")
    # (route, a URL of that route that the middleware treats as public)
    aligned = [
        (f"{parent}/{{provider}}/start", f"{parent}/{last}/start"),
        (f"{CONTROL_PLANE_PREFIX}{{section}}/items", f"{CONTROL_PLANE_PREFIX}{encoded_tail}/items"),
        (f"{public}{{suffix}}", f"{public}%2Fdetails"),
    ]
    clear = f"{PROTECTED_TARGET}/{{item}}/details"

    app = _build_supervisor_app()
    new_routes = [app.router.add_get(path, new_handler) for path, _ in aligned]
    new_routes.append(app.router.add_get(clear, new_handler))

    assert _dynamic_routes_that_can_spell_a_public_path(
        [route.resource for route in new_routes if route.resource is not None], [public]
    ) == [f"{path}: a parameter can spell the public path {public}" for path, _ in aligned]

    # The one-request-per-route matrix sees nothing wrong with any of them...
    probes = await _probe_routes(app, new_routes)
    assert all(not probe.public for probe in probes.values())
    assert _openapi_drift(probes, {key: False for key in probes}) == []
    # ...yet each aligned route reaches its handler without credentials.
    async with TestServer(app) as server:
        for path, url in aligned:
            rate_limit.clear_limiters()
            status, headers = await _raw_get(server, url)
            assert (status, headers.get(REACHED_HEADER)) == (204, f"GET {path}"), url
    rate_limit.clear_limiters()


async def test_matrix_flags_head_requests_that_skip_the_auth_check() -> None:
    """aiohttp runs the GET handler for HEAD, so a HEAD request must be refused when GET is."""

    @web.middleware
    async def auth_skipping_head(request: web.Request, handler: Any) -> web.StreamResponse:
        if request.method == "HEAD":
            return await handler(request)
        return await control_plane_api.control_plane_auth_middleware(request, handler)

    with patch("koda.control_plane.supervisor.control_plane_auth_middleware", auth_skipping_head):
        app = _build_supervisor_app()
    routes = [
        route
        for route in app.router.routes()
        if route.resource is not None and route.resource.canonical == PROTECTED_TARGET
    ]
    probes = await _probe_routes(app, routes)

    assert {probe.method for probe in probes.values()} >= {"GET", "HEAD"}
    # The OpenAPI comparison leaves HEAD out, so only the twin check sees the bypass.
    assert _openapi_drift(probes, {key: False for key in probes}) == []
    assert _head_drift(probes) == [
        f"HEAD {PROTECTED_TARGET}: answers without credentials, but GET {PROTECTED_TARGET} requires an operator session"
    ]


def _variant_cases() -> list[tuple[str, int]]:
    """``(request target, expected status)``; none of them may reach a handler anonymously."""
    target_tail = PROTECTED_TARGET.removeprefix(CONTROL_PLANE_PREFIX)
    cases: list[tuple[str, int]] = []
    for public in sorted(_backend_allowlist()):
        parent, _, last = public.rpartition("/")
        ups = "/".join([".."] * len(public.removeprefix(CONTROL_PLANE_PREFIX).split("/")))
        cases += [
            # A sub-path of an allowlist entry is public by prefix, and nothing is registered there.
            (f"{public}/x", 404),
            (f"{public}/", 404),
            # A longer or differently cased name is not the entry.
            (f"{public}x", 401),
            (f"{public};x", 401),
            (f"{parent}/{last.upper()}", 401),
            (public.upper(), 404),
            # Dot segments from the public entry to a protected route, plain and encoded.
            (f"{public}/{ups}/{target_tail}", 404),
            (f"{public}/{ups.replace('..', '%2e%2e')}/{target_tail}", 404),
            (f"{public}%2F{ups.replace('/', '%2F')}%2F{target_tail}", 404),
        ]
    cases += [
        # Other spellings of the protected route itself.
        (f"/{PROTECTED_TARGET}", 404),
        (PROTECTED_TARGET.replace("/api/", "/api//", 1), 404),
        (PROTECTED_TARGET.replace("/control-plane/", "/control-plane//", 1), 401),
        (f"{PROTECTED_TARGET}/", 401),
        (PROTECTED_TARGET.replace("control-plane", "control%2Dplane", 1), 401),
        (PROTECTED_TARGET.replace("/api/", "/api%2F", 1), 401),
        (f"/x/..{PROTECTED_TARGET}", 404),
        (f"/health/..{PROTECTED_TARGET}", 404),
        (f"{PROTECTED_TARGET}?next={sorted(_backend_allowlist())[0]}", 401),
        (CONTROL_PLANE_PREFIX.rstrip("/"), 404),
    ]
    return cases


async def _raw_get(server: TestServer, target: str) -> tuple[int, dict[str, str]]:
    """Send ``target`` byte for byte; the aiohttp client would normalise dot segments."""
    reader, writer = await asyncio.open_connection(server.host, server.port)
    try:
        writer.write(f"GET {target} HTTP/1.1\r\nHost: matrix\r\nConnection: close\r\n\r\n".encode("ascii"))
        await writer.drain()
        raw = await reader.read()
    finally:
        writer.close()
        await writer.wait_closed()
    head = raw.split(b"\r\n\r\n", 1)[0].decode("latin-1").split("\r\n")
    status = int(head[0].split(" ", 2)[1])
    headers = dict(line.split(": ", 1) for line in head[1:] if ": " in line)
    return status, headers


async def test_path_variants_never_reach_a_handler_without_credentials() -> None:
    cases = _variant_cases()
    app = _build_supervisor_app()
    observed = []
    async with TestServer(app) as server:
        for target in [PROTECTED_TARGET, *(target for target, _ in cases)]:
            rate_limit.clear_limiters()
            status, headers = await _raw_get(server, target)
            observed.append((target, status, headers.get(REACHED_HEADER)))
    rate_limit.clear_limiters()

    assert observed[0] == (PROTECTED_TARGET, 401, None), "PROTECTED_TARGET must be a protected route"
    assert observed[1:] == [(target, expected, None) for target, expected in cases]
