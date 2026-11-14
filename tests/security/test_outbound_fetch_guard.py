"""One SSRF probe matrix for the outbound fetches outside the shared web helpers (M1-E3-T8, D-223).

Every listed path goes through ``koda.services.http_client.guarded_urlopen``. Each path
takes the probes its input allows:

- an attacker-chosen URL that names a non-public address literally;
- a public-looking name whose DNS answer is that address;
- DNS rebinding: every safety check sees a public answer, the connection's own lookup
  sees loopback;
- a redirect to another origin;
- ``*_proxy`` environment variables pointing at a recording proxy.

Endpoints the operator configured (local Ollama, the agent runtime API, an operator base
URL, an MCP server inside ``MCP_ALLOWED_PRIVATE_NETWORKS``) hold a private-network grant
for their own origin only: they must keep working, and still refuse the redirect and the
proxy.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from koda.services import http_client

pytestmark = [pytest.mark.security, pytest.mark.guardrail]

PUBLIC_IP = "93.184.216.34"

# Where a hostile URL or DNS answer points. 100.64.0.0/10 also holds cloud metadata
# (100.100.100.200) and is Tailscale's range, so it needs an explicit grant.
PROBE_ADDRESSES = {
    "unspecified": "0.0.0.0",
    "ipv4-mapped-loopback": "::ffff:127.0.0.1",
    "shared-address-space": "100.64.0.1",
    "nat64-loopback": "64:ff9b::7f00:1",
}

_GUARD_WORDING = ("not allowed", "private/reserved", "another origin")
_PROXY_ENV = ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")


# Local servers


Route = tuple[int, dict[str, str], bytes]
_DEFAULT_ROUTE: Route = (200, {"Content-Type": "application/json"}, b'{"secret": "internal"}')


@dataclass
class _Server:
    host: str
    port: int
    hits: list[tuple[str, str]] = field(default_factory=list)

    @property
    def origin(self) -> str:
        return f"http://{self.host}:{self.port}"


@pytest.fixture
def serve() -> Iterator[Callable[..., _Server]]:
    """Start threaded HTTP servers that record every request they answer."""
    started: list[ThreadingHTTPServer] = []

    def start(routes: dict[str, Route] | None = None, *, host: str = "127.0.0.1") -> _Server:
        table = dict(routes or {})
        hits: list[tuple[str, str]] = []

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                hits.append((self.command, self.path))
                status, headers, body = table.get(self.path, _DEFAULT_ROUTE)
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = _answer
            do_POST = _answer

            def log_message(self, *_args: Any) -> None:
                return None

        httpd = ThreadingHTTPServer((host, 0), Handler)
        threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        started.append(httpd)
        return _Server(host=host, port=int(httpd.server_address[1]), hits=hits)

    yield start
    for httpd in started:
        httpd.shutdown()
        httpd.server_close()


def _redirect(location: str, status: int = 302) -> Route:
    return (status, {"Location": location}, b"")


# DNS


def _answer(ip: str, port: Any) -> list[tuple[Any, ...]]:
    if ":" in ip:
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, port or 0, 0, 0))]
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0))]


@pytest.fixture
def fake_dns(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Answer chosen names; ``connect_ip`` is what the connection's own lookup sees.

    Safety checks look names up with keyword or no options; the lookup a connection
    makes passes family and type positionally (``socket.create_connection`` and
    asyncio's ``getaddrinfo`` both do), which is how a rebinding answer reaches only it.
    """
    real_getaddrinfo = socket.getaddrinfo
    table: dict[str, tuple[str, str]] = {}

    def fake(host: Any, port: Any, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        entry = table.get(str(host))
        if entry is None:
            return real_getaddrinfo(host, port, *args, **kwargs)
        check_ip, connect_ip = entry
        return _answer(connect_ip if len(args) >= 2 else check_ip, port)

    monkeypatch.setattr(socket, "getaddrinfo", fake)

    def add(name: str, ip: str, *, connect_ip: str | None = None) -> None:
        table[name] = (ip, connect_ip or ip)

    return add


@pytest.fixture
def loopback_is_public(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let a local server play a public host: only 127.0.0.1 changes class."""
    real = http_client._is_private_ip
    monkeypatch.setattr(http_client, "_is_private_ip", lambda ip: ip != "127.0.0.1" and real(ip))


@pytest.fixture
def recording_proxy(serve: Callable[..., _Server], monkeypatch: pytest.MonkeyPatch) -> _Server:
    proxy = serve()
    for key in _PROXY_ENV:
        monkeypatch.setenv(key, proxy.origin)
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    # urlopen caches its opener with the proxies of its first call; start from none,
    # as a process started with this environment would.
    monkeypatch.setattr(urllib.request, "_opener", None)
    return proxy


def _assert_refused_by_guard(call: Callable[[], Any], *servers: _Server, wording: bool = True) -> str:
    """Run *call*, expect it to fail, and check no request reached *servers*.

    With *wording*, the guard's refusal must show in the error or its causes; paths
    that swallow the cause (a readiness poll answers False) set it to False.
    """
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 - each path raises its own error type
        call()
    messages: list[str] = []
    error: BaseException | None = excinfo.value
    while error is not None:
        messages.append(str(error))
        error = error.__cause__ or error.__context__
    message = " | ".join(messages)
    if wording:
        assert any(word in message.lower() for word in _GUARD_WORDING), message
    for server in servers:
        assert server.hits == [], f"guard let a request through to {server.origin}: {server.hits}"
    return message


def _literal_host(ip: str) -> str:
    return f"[{ip}]" if ":" in ip else ip


# Paths that only reach public addresses


def _mcp_call(url: str) -> Any:
    from koda.services.mcp_client import HttpSseTransport

    return asyncio.run(HttpSseTransport(url).send_request("ping"))


def _generated_image(url: str) -> Any:
    from koda.services.generation_stubs import _download_image_url

    return _download_image_url(url)


def _vendor_verifier(_url: str) -> Any:
    from koda.services.provider_auth import verify_provider_api_key

    result = verify_provider_api_key("mistral", "test-key")
    if not result.verified:
        raise RuntimeError(result.last_error)
    return result


def _ollama_cloud_chat(_url: str) -> Any:
    from koda.services.ollama_runner import _perform_chat_request

    return _perform_chat_request(model="llama3", query="ping", system_prompt=None)


@dataclass(frozen=True)
class _PublicPath:
    call: Callable[[str], Any]
    scheme: str
    fixed_host: str | None = None  # paths whose URL is fixed: only DNS answers can be hostile

    def url(self, host: str, port: int) -> str:
        return f"{self.scheme}://{host}:{port}/rpc"


PUBLIC_PATHS = {
    "mcp_http": _PublicPath(_mcp_call, "http"),
    "generated_image_download": _PublicPath(_generated_image, "https"),
    "provider_api_key_verifier": _PublicPath(_vendor_verifier, "https", fixed_host="api.mistral.ai"),
    "ollama_cloud_chat": _PublicPath(_ollama_cloud_chat, "https", fixed_host="ollama.com"),
}
URL_PATHS = {name: path for name, path in PUBLIC_PATHS.items() if path.fixed_host is None}


@pytest.fixture(autouse=True)
def _ollama_cloud_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_AUTH_MODE", "api_key")
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-cloud-key")


@pytest.mark.parametrize("probe", PROBE_ADDRESSES.values(), ids=PROBE_ADDRESSES.keys())
@pytest.mark.parametrize("path", URL_PATHS.values(), ids=URL_PATHS.keys())
def test_hostile_literal_address_is_refused(path: _PublicPath, probe: str, serve: Callable[..., _Server]) -> None:
    server = serve()
    _assert_refused_by_guard(lambda: path.call(path.url(_literal_host(probe), server.port)), server)


@pytest.mark.parametrize("probe", PROBE_ADDRESSES.values(), ids=PROBE_ADDRESSES.keys())
@pytest.mark.parametrize("path", PUBLIC_PATHS.values(), ids=PUBLIC_PATHS.keys())
def test_hostile_dns_answer_is_refused(
    path: _PublicPath, probe: str, serve: Callable[..., _Server], fake_dns: Callable[..., None]
) -> None:
    server = serve()
    host = path.fixed_host or "public.koda.test"
    fake_dns(host, probe)
    _assert_refused_by_guard(lambda: path.call(path.url(host, server.port)), server)


@pytest.mark.parametrize("path", PUBLIC_PATHS.values(), ids=PUBLIC_PATHS.keys())
def test_dns_rebinding_to_loopback_is_refused_at_connect(
    path: _PublicPath, serve: Callable[..., _Server], fake_dns: Callable[..., None]
) -> None:
    server = serve()
    host = path.fixed_host or "rebind.koda.test"
    fake_dns(host, PUBLIC_IP, connect_ip="127.0.0.1")
    message = _assert_refused_by_guard(lambda: path.call(path.url(host, server.port)), server)
    assert "private/reserved" in message


def _public_mcp_server(serve: Callable[..., _Server], fake_dns: Callable[..., None], routes: dict[str, Route]):
    server = serve(routes)
    fake_dns("public.koda.test", PUBLIC_IP, connect_ip="127.0.0.1")
    return server, f"http://public.koda.test:{server.port}/rpc"


_RPC_RESULT: Route = (200, {"Content-Type": "application/json"}, b'{"jsonrpc": "2.0", "id": 1, "result": {"ok": true}}')


def test_mcp_cross_origin_redirect_is_refused(
    serve: Callable[..., _Server], fake_dns: Callable[..., None], loopback_is_public: None
) -> None:
    other = serve({"/rpc": _RPC_RESULT})
    fake_dns("other.koda.test", PUBLIC_IP, connect_ip="127.0.0.1")
    server, url = _public_mcp_server(
        serve, fake_dns, {"/rpc": _redirect(f"http://other.koda.test:{other.port}/rpc", status=307)}
    )

    _assert_refused_by_guard(lambda: _mcp_call(url), other)
    assert server.hits == [("POST", "/rpc")]


def test_mcp_same_origin_redirect_still_works(
    serve: Callable[..., _Server], fake_dns: Callable[..., None], loopback_is_public: None
) -> None:
    server, url = _public_mcp_server(
        serve, fake_dns, {"/rpc": _redirect("/rpc/v2", status=307), "/rpc/v2": _RPC_RESULT}
    )

    assert _mcp_call(url) == {"ok": True}
    assert server.hits == [("POST", "/rpc"), ("POST", "/rpc/v2")]


def test_mcp_ignores_proxy_environment(
    serve: Callable[..., _Server],
    fake_dns: Callable[..., None],
    loopback_is_public: None,
    recording_proxy: _Server,
) -> None:
    server, url = _public_mcp_server(serve, fake_dns, {"/rpc": _RPC_RESULT})

    assert _mcp_call(url) == {"ok": True}
    assert recording_proxy.hits == []
    assert server.hits == [("POST", "/rpc")]


def test_generated_image_download_uses_the_guard_without_a_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.services import generation_stubs

    calls: list[dict[str, Any]] = []

    def fake_guarded_urlopen(request: urllib.request.Request, timeout: float, **kwargs: Any) -> Any:
        calls.append({"url": request.full_url, **kwargs})
        return http_client.GuardedResponse(request.full_url, 200, "OK", http_client._http_message({}), b"png")

    monkeypatch.setattr(generation_stubs, "guarded_urlopen", fake_guarded_urlopen)

    assert generation_stubs._download_image_url("https://images.example/a.png") == (b"png", "")
    assert calls == [{"url": "https://images.example/a.png", "max_size": generation_stubs._MAX_IMAGE_DOWNLOAD_BYTES}]


# Endpoints the operator configured: a private-network grant for their own origin


_OLLAMA_CHAT: Route = (200, {"Content-Type": "application/json"}, b'{"message": {"content": "pong"}}')
_OLLAMA_TAGS: Route = (200, {"Content-Type": "application/json"}, b'{"models": [{"name": "llama3"}]}')
_RUNTIME_READY: Route = (200, {"Content-Type": "application/json"}, b'{"ready": true}')
_RUNTIME_ACCEPTED: Route = (200, {"Content-Type": "application/json"}, b'{"accepted": true}')
_MODELS: Route = (200, {"Content-Type": "application/json"}, b'{"data": [{"id": "model-a"}]}')


def _control_plane_manager(monkeypatch: pytest.MonkeyPatch) -> Any:
    from koda.control_plane.manager import ControlPlaneManager

    manager = object.__new__(ControlPlaneManager)
    manager._ollama_model_cache = {}
    monkeypatch.setattr("koda.control_plane.lifecycle_events.notify_lifecycle_change", lambda *, reason: None)
    return manager


def _ollama_local_chat(base_url: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    from koda.services.ollama_runner import _perform_chat_request

    monkeypatch.setenv("OLLAMA_AUTH_MODE", "local")
    monkeypatch.setenv("OLLAMA_BASE_URL", base_url)
    payload, auth_mode = _perform_chat_request(model="llama3", query="ping", system_prompt=None)
    assert auth_mode == "local"
    return payload["message"]["content"]


def _ollama_local_verify(base_url: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    from koda.services.provider_auth import verify_provider_local_connection

    result = verify_provider_local_connection("ollama", base_url=base_url)
    if not result.verified:
        raise RuntimeError(result.details.get("raw_error") or result.last_error)
    return result.verified


def _control_plane_ollama_catalog(base_url: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    catalog = _control_plane_manager(monkeypatch)._fetch_ollama_model_catalog(
        auth_mode="local", base_url=base_url, api_key=""
    )
    if not catalog["provider_connected"]:
        raise RuntimeError("Ollama catalog fetch failed")
    return [item["model_id"] for item in catalog["items"]]


def _runtime_readiness(base_url: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    if not _control_plane_manager(monkeypatch)._wait_for_dashboard_runtime_api(base_url, "tok", timeout_seconds=0):
        raise RuntimeError("runtime readiness failed")
    return True


def _runtime_message(base_url: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    return _control_plane_manager(monkeypatch)._post_runtime_session_message(
        agent_id="ATLAS", runtime_base_url=base_url, runtime_token="tok", request_payload={"text": "hi"}
    )


def _verifier_operator_base_url(base_url: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    from koda.services.provider_auth import _verify_openai_compatible_api_key

    result = _verify_openai_compatible_api_key("mistral", "test-key", base_url=base_url)
    if not result.verified:
        raise RuntimeError(result.last_error)
    return result.details["model_ids"]


@dataclass(frozen=True)
class _GrantedPath:
    call: Callable[[str, pytest.MonkeyPatch], Any]
    path: str
    route: Route
    expected: Any


GRANTED_PATHS = {
    "ollama_local_chat": _GrantedPath(_ollama_local_chat, "/api/chat", _OLLAMA_CHAT, "pong"),
    "ollama_local_verify": _GrantedPath(_ollama_local_verify, "/api/tags", _OLLAMA_TAGS, True),
    "control_plane_ollama_catalog": _GrantedPath(_control_plane_ollama_catalog, "/api/tags", _OLLAMA_TAGS, ["llama3"]),
    "control_plane_runtime_readiness": _GrantedPath(_runtime_readiness, "/api/runtime/readiness", _RUNTIME_READY, True),
    "control_plane_runtime_message": _GrantedPath(
        _runtime_message, "/api/runtime/sessions/messages", _RUNTIME_ACCEPTED, {"accepted": True}
    ),
    "provider_verifier_operator_base_url": _GrantedPath(
        _verifier_operator_base_url, "/v1/models", _MODELS, ["model-a"]
    ),
}


@pytest.mark.parametrize("granted", GRANTED_PATHS.values(), ids=GRANTED_PATHS.keys())
def test_configured_local_endpoint_still_works(
    granted: _GrantedPath, serve: Callable[..., _Server], monkeypatch: pytest.MonkeyPatch
) -> None:
    server = serve({granted.path: granted.route})

    assert granted.call(server.origin, monkeypatch) == granted.expected
    assert granted.path in [path for _method, path in server.hits]


@pytest.mark.parametrize("granted", GRANTED_PATHS.values(), ids=GRANTED_PATHS.keys())
def test_configured_endpoint_grant_does_not_follow_cross_origin_redirect(
    granted: _GrantedPath, serve: Callable[..., _Server], monkeypatch: pytest.MonkeyPatch
) -> None:
    other = serve({granted.path: granted.route})
    server = serve({granted.path: _redirect(f"{other.origin}{granted.path}")})

    # The readiness poll and the model catalog report a refused request as "not
    # ready" / "not connected"; the second origin staying untouched is the proof.
    _assert_refused_by_guard(lambda: granted.call(server.origin, monkeypatch), other, wording=False)
    assert granted.path in [path for _method, path in server.hits]


@pytest.mark.parametrize("granted", GRANTED_PATHS.values(), ids=GRANTED_PATHS.keys())
def test_configured_endpoint_ignores_proxy_environment(
    granted: _GrantedPath,
    serve: Callable[..., _Server],
    recording_proxy: _Server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = serve({granted.path: granted.route})

    assert granted.call(server.origin, monkeypatch) == granted.expected
    assert recording_proxy.hits == []


def test_configured_endpoint_must_be_http(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(urllib.error.URLError, match="Only http and https"):
        _ollama_local_chat("file:///etc", monkeypatch)


async def test_sync_callers_on_the_event_loop_thread_still_work(
    serve: Callable[..., _Server], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Ollama capability probe calls the verifier synchronously from a coroutine."""
    server = serve({"/api/tags": _OLLAMA_TAGS})

    assert _ollama_local_verify(server.origin, monkeypatch) is True


# MCP private-network grant (MCP_ALLOWED_PRIVATE_NETWORKS)


@pytest.fixture
def mcp_grant(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    from koda.services import mcp_client

    def grant(*networks: str) -> None:
        monkeypatch.setattr(mcp_client, "MCP_ALLOWED_PRIVATE_NETWORKS", list(networks))

    return grant


def test_tailscale_mcp_server_needs_an_explicit_grant(mcp_grant: Callable[..., None], fake_dns: Callable[..., None]):
    from koda.services.mcp_client import _validate_url

    fake_dns("mcp.tailnet.ts.net", "100.101.102.103")
    for url in ("http://100.101.102.103:8000/mcp", "http://mcp.tailnet.ts.net:8000/mcp"):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_url(url)

    mcp_grant("100.64.0.0/10")
    for url in ("http://100.101.102.103:8000/mcp", "http://mcp.tailnet.ts.net:8000/mcp"):
        _validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/mcp",
        "http://[::ffff:127.0.0.1]:8000/mcp",
        "http://169.254.169.254/latest/meta-data",
        "http://0.0.0.0:8000/mcp",
        "http://224.0.0.1/",
    ],
)
def test_mcp_grant_never_covers_loopback_metadata_or_unspecified(url: str, mcp_grant: Callable[..., None]) -> None:
    from koda.services.mcp_client import _validate_url

    mcp_grant("0.0.0.0/0", "::/0")
    with pytest.raises(ValueError, match="not allowed"):
        _validate_url(url)


def test_mcp_grant_ignores_unparseable_entries(mcp_grant: Callable[..., None]) -> None:
    from koda.services.mcp_client import _validate_url

    mcp_grant("not-a-network", "100.64.0.0/33")
    with pytest.raises(ValueError, match="not allowed"):
        _validate_url("http://100.101.102.103:8000/mcp")


async def test_granted_connector_still_pins_against_rebinding_to_loopback() -> None:
    from unittest.mock import AsyncMock, patch

    grant = (ipaddress.ip_network("100.64.0.0/10"),)
    resolver = http_client._PublicOnlyResolver(grant)
    tailnet = [{"hostname": "h", "host": "100.101.102.103", "port": 80, "family": 2, "proto": 6, "flags": 0}]
    loopback = [{"hostname": "h", "host": "127.0.0.1", "port": 80, "family": 2, "proto": 6, "flags": 0}]
    with patch.object(resolver._resolver, "resolve", AsyncMock(return_value=tailnet)):
        assert await resolver.resolve("h", 80) == tailnet
    with (
        patch.object(resolver._resolver, "resolve", AsyncMock(return_value=loopback)),
        pytest.raises(OSError, match="private/reserved"),
    ):
        await resolver.resolve("h", 80)
    await resolver.close()


def _private_interface_address() -> str | None:
    """A non-loopback private address of this host, or None (then the round trip is skipped)."""
    candidates: list[str] = []
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.254.254.254", 9))  # UDP connect sends nothing; it picks the outgoing address
        candidates.append(str(probe.getsockname()[0]))
    except OSError:
        pass
    finally:
        probe.close()
    for candidate in candidates:
        address = ipaddress.ip_address(candidate)
        if address.is_private and not (address.is_loopback or address.is_link_local or address.is_unspecified):
            return candidate
    return None


def test_mcp_server_on_a_granted_private_network_round_trips(
    serve: Callable[..., _Server], mcp_grant: Callable[..., None]
) -> None:
    address = _private_interface_address()
    if address is None:
        pytest.skip("this host has no non-loopback private address to serve from")
    server = serve({"/rpc": _RPC_RESULT}, host=address)
    url = f"http://{address}:{server.port}/rpc"

    with pytest.raises(ValueError, match="not allowed"):
        _mcp_call(url)
    mcp_grant(f"{address}/32")

    assert _mcp_call(url) == {"ok": True}
    assert server.hits == [("POST", "/rpc")]


# The shared guarded client itself


def test_guarded_urlopen_raises_http_error_with_readable_body(serve: Callable[..., _Server]) -> None:
    server = serve({"/missing": (404, {"Content-Type": "application/json"}, b'{"error": "nope"}')})

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        http_client.guarded_urlopen(urllib.request.Request(f"{server.origin}/missing"), allow_private=True)

    assert excinfo.value.code == 404
    assert excinfo.value.read() == b'{"error": "nope"}'


def test_guarded_urlopen_grant_stops_at_the_configured_origin(serve: Callable[..., _Server]) -> None:
    other = serve()
    server = serve({"/hop": _redirect(f"{other.origin}/secret"), "/same": _redirect("/ok"), "/ok": _MODELS})

    with pytest.raises(http_client.GuardedRequestError, match="another origin"):
        http_client.guarded_urlopen(urllib.request.Request(f"{server.origin}/hop"), allow_private=True)
    response = http_client.guarded_urlopen(urllib.request.Request(f"{server.origin}/same"), allow_private=True)

    assert response.read() == _MODELS[2]
    assert other.hits == []


def test_guarded_urlopen_caps_the_response_size(serve: Callable[..., _Server]) -> None:
    server = serve({"/big": (200, {}, b"x" * 2048)})

    with pytest.raises(http_client.GuardedRequestError, match="too large"):
        http_client.guarded_urlopen(urllib.request.Request(f"{server.origin}/big"), allow_private=True, max_size=1024)


def test_guarded_urlopen_without_redirects_returns_the_3xx(serve: Callable[..., _Server]) -> None:
    server = serve({"/moved": _redirect("http://elsewhere.example/")})

    response = http_client.guarded_urlopen(
        urllib.request.Request(f"{server.origin}/moved"), allow_private=True, follow_redirects=False
    )

    assert response.status == 302
    assert response.headers.get("location") == "http://elsewhere.example/"
