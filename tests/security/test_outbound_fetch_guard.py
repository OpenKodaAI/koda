"""One SSRF probe matrix for the outbound fetches outside the shared web helpers (M1-E3-T8, D-223).

Every listed path goes through ``koda.services.http_client.guarded_urlopen``. Each path
takes the probes its input allows:

- an attacker-chosen URL that names a non-public address literally;
- a public-looking name whose DNS answer is that address;
- DNS rebinding: every safety check sees a public answer, the connection's own lookup
  sees loopback;
- a redirect to another origin;
- ``*_proxy`` environment variables pointing at a recording proxy.

The https paths run against local TLS servers whose certificate a per-session test CA
signs; aiohttp trusts that CA only for the test that asks for it (the ``tls`` fixture),
and the fake DNS sends a fixed vendor host (``api.mistral.ai``, ``ollama.com``) to the
local server's port.

Endpoints the operator configured (local Ollama, the agent runtime API, an operator base
URL, an MCP server inside ``MCP_ALLOWED_PRIVATE_NETWORKS``) hold a private-network grant
for their own origin only: they must keep working, and still refuse the redirect and the
proxy.
"""

from __future__ import annotations

import asyncio
import datetime
import ipaddress
import socket
import ssl
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from koda.services import http_client

pytestmark = [pytest.mark.security, pytest.mark.guardrail]

ROOT = Path(__file__).resolve().parents[2]
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
# A route header that makes the server send its body without Content-Length, ended by
# closing the connection (the server speaks HTTP/1.0); the header itself is not sent.
_UNSIZED = "X-Test-Unsized"


@dataclass
class _Server:
    host: str
    port: int
    hits: list[tuple[str, str]] = field(default_factory=list)
    bodies: list[bytes] = field(default_factory=list)
    scheme: str = "http"

    @property
    def origin(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"


@pytest.fixture
def serve() -> Iterator[Callable[..., _Server]]:
    """Start threaded HTTP servers that record every request they answer.

    With *tls* (the ``tls`` fixture's server context) the server speaks https. A
    ``CONNECT`` is recorded too, so a proxy server sees an https request tunnelled to it.
    """
    started: list[ThreadingHTTPServer] = []

    def start(
        routes: dict[str, Route] | None = None, *, host: str = "127.0.0.1", tls: ssl.SSLContext | None = None
    ) -> _Server:
        table = dict(routes or {})
        hits: list[tuple[str, str]] = []
        bodies: list[bytes] = []

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                bodies.append(self.rfile.read(length) if length else b"")
                hits.append((self.command, self.path))
                status, headers, body = table.get(self.path, _DEFAULT_ROUTE)
                self.send_response(status)
                for key, value in headers.items():
                    if key != _UNSIZED:
                        self.send_header(key, value)
                if _UNSIZED not in headers:
                    self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = _answer
            do_POST = _answer
            do_CONNECT = _answer

            def log_message(self, *_args: Any) -> None:
                return None

        httpd = ThreadingHTTPServer((host, 0), Handler)
        if tls is not None:
            httpd.socket = tls.wrap_socket(httpd.socket, server_side=True)
        threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        started.append(httpd)
        return _Server(
            host=host,
            port=int(httpd.server_address[1]),
            hits=hits,
            bodies=bodies,
            scheme="https" if tls is not None else "http",
        )

    yield start
    for httpd in started:
        httpd.shutdown()
        httpd.server_close()


def _redirect(location: str, status: int = 302) -> Route:
    return (status, {"Location": location}, b"")


# TLS

# Every name an https server in this file answers for.
_TLS_NAMES = ("public.koda.test", "other.koda.test", "api.mistral.ai", "api.perplexity.ai", "ollama.com")


@dataclass(frozen=True)
class _Pki:
    ca_file: str
    cert_file: str
    key_file: str


@pytest.fixture(scope="session")
def pki(tmp_path_factory: pytest.TempPathFactory) -> _Pki:
    """A throwaway CA and a server certificate it signs for :data:`_TLS_NAMES`."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.datetime.now(datetime.UTC)
    not_before, not_after = now - datetime.timedelta(minutes=5), now + datetime.timedelta(days=1)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Koda outbound guard test CA")])
    ca_cert = (
        x509.CertificateBuilder(issuer_name=ca_name, subject_name=ca_name)
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        x509.CertificateBuilder(
            issuer_name=ca_name, subject_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _TLS_NAMES[0])])
        )
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name) for name in _TLS_NAMES]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    directory = tmp_path_factory.mktemp("outbound-guard-pki")
    ca_file, cert_file, key_file = directory / "ca.pem", directory / "cert.pem", directory / "key.pem"
    ca_file.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return _Pki(ca_file=str(ca_file), cert_file=str(cert_file), key_file=str(key_file))


@pytest.fixture
def tls(pki: _Pki, monkeypatch: pytest.MonkeyPatch) -> ssl.SSLContext:
    """The server context for ``serve(..., tls=tls)``; aiohttp trusts the test CA meanwhile.

    aiohttp verifies https with one module-level default context; it is swapped for a
    context that trusts the test CA only (hostname and chain still verified), so the
    guard's TLS path runs unchanged.
    """
    import aiohttp.connector

    monkeypatch.setattr(aiohttp.connector, "_SSL_CONTEXT_VERIFIED", ssl.create_default_context(cafile=pki.ca_file))
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(pki.cert_file, pki.key_file)
    return server


# DNS


Answers = str | tuple[str, ...]


def _answer(ips: Answers, port: Any) -> list[tuple[Any, ...]]:
    answers: list[tuple[Any, ...]] = []
    for ip in (ips,) if isinstance(ips, str) else ips:
        if ":" in ip:
            answers.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, port or 0, 0, 0)))
        else:
            answers.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0)))
    return answers


@pytest.fixture
def fake_dns(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Answer chosen names; ``connect_ip`` is what the connection's own lookup sees.

    Safety checks look names up with keyword or no options; the lookup a connection
    makes passes family and type positionally (``socket.create_connection`` and
    asyncio's ``getaddrinfo`` both do), which is how a rebinding answer reaches only it.
    ``connect_port`` sends that connection to another port (a fixed vendor URL's 443 to
    a local server). A tuple of addresses answers with all of them (A and AAAA).
    """
    real_getaddrinfo = socket.getaddrinfo
    table: dict[str, tuple[Answers, Answers, int | None]] = {}

    def fake(host: Any, port: Any, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        entry = table.get(str(host))
        if entry is None:
            return real_getaddrinfo(host, port, *args, **kwargs)
        check_ips, connect_ips, connect_port = entry
        if len(args) >= 2:
            return _answer(connect_ips, connect_port or port)
        return _answer(check_ips, port)

    monkeypatch.setattr(socket, "getaddrinfo", fake)

    def add(name: str, ip: Answers, *, connect_ip: Answers | None = None, connect_port: int | None = None) -> None:
        table[name] = (ip, connect_ip or ip, connect_port)

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


# What the servers answer when a request succeeds

_RPC_RESULT: Route = (200, {"Content-Type": "application/json"}, b'{"jsonrpc": "2.0", "id": 1, "result": {"ok": true}}')
_IMAGE: Route = (200, {"Content-Type": "image/png"}, b"\x89PNG\r\n")
_OLLAMA_CHAT: Route = (200, {"Content-Type": "application/json"}, b'{"message": {"content": "pong"}}')
_OLLAMA_TAGS: Route = (200, {"Content-Type": "application/json"}, b'{"models": [{"name": "llama3"}]}')
_RUNTIME_READY: Route = (200, {"Content-Type": "application/json"}, b'{"ready": true}')
_RUNTIME_ACCEPTED: Route = (200, {"Content-Type": "application/json"}, b'{"accepted": true}')
_MODELS: Route = (200, {"Content-Type": "application/json"}, b'{"data": [{"id": "model-a"}]}')


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


def _same(value: Any) -> Any:
    return value


@dataclass(frozen=True)
class _PublicPath:
    call: Callable[[str], Any]
    scheme: str
    fixed_host: str | None = None  # paths whose URL is fixed: only DNS answers can be hostile
    # A successful round trip: the request the call makes, what the server answers, and
    # what the call then returns (through *result*).
    method: str = "GET"
    path: str = "/rpc"
    answer: Route = _DEFAULT_ROUTE
    result: Callable[[Any], Any] = _same
    expected: Any = None

    def url(self, host: str, port: int) -> str:
        return f"{self.scheme}://{host}:{port}{self.path}"


PUBLIC_PATHS = {
    "mcp_http": _PublicPath(_mcp_call, "http", method="POST", answer=_RPC_RESULT, expected={"ok": True}),
    "generated_image_download": _PublicPath(
        _generated_image, "https", path="/image.png", answer=_IMAGE, expected=(_IMAGE[2], "image/png")
    ),
    "provider_api_key_verifier": _PublicPath(
        _vendor_verifier,
        "https",
        fixed_host="api.mistral.ai",
        path="/v1/models",
        answer=_MODELS,
        result=lambda result: result.details["model_ids"],
        expected=["model-a"],
    ),
    "ollama_cloud_chat": _PublicPath(
        _ollama_cloud_chat,
        "https",
        fixed_host="ollama.com",
        method="POST",
        path="/api/chat",
        answer=_OLLAMA_CHAT,
        result=lambda result: (result[0]["message"]["content"], result[1]),
        expected=("pong", "api_key"),
    ),
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


def _serve_as(
    path: _PublicPath,
    routes: dict[str, Route],
    serve: Callable[..., _Server],
    fake_dns: Callable[..., None],
    tls: ssl.SSLContext,
) -> tuple[_Server, str]:
    """Serve *routes* as the host *path* talks to (its fixed vendor host, or a public name).

    The safety checks see a public answer; the connection reaches the local server.
    """
    server = serve(routes, tls=tls if path.scheme == "https" else None)
    host = path.fixed_host or "public.koda.test"
    fake_dns(host, PUBLIC_IP, connect_ip="127.0.0.1", connect_port=server.port)
    return server, path.url(host, server.port)


@pytest.mark.parametrize("path", PUBLIC_PATHS.values(), ids=PUBLIC_PATHS.keys())
def test_public_path_cross_origin_redirect_is_refused(
    path: _PublicPath,
    serve: Callable[..., _Server],
    fake_dns: Callable[..., None],
    loopback_is_public: None,
    tls: ssl.SSLContext,
) -> None:
    """A redirect to another public origin is refused before anything (or any key) reaches it."""
    other = serve({path.path: path.answer}, tls=tls if path.scheme == "https" else None)
    fake_dns("other.koda.test", PUBLIC_IP, connect_ip="127.0.0.1")
    elsewhere = f"{path.scheme}://other.koda.test:{other.port}{path.path}"
    status = 307 if path.method == "POST" else 302
    server, url = _serve_as(path, {path.path: _redirect(elsewhere, status=status)}, serve, fake_dns, tls)

    message = _assert_refused_by_guard(lambda: path.call(url), other)
    assert "another origin" in message
    assert server.hits == [(path.method, path.path)]


@pytest.mark.parametrize("path", PUBLIC_PATHS.values(), ids=PUBLIC_PATHS.keys())
def test_public_path_ignores_proxy_environment(
    path: _PublicPath,
    serve: Callable[..., _Server],
    fake_dns: Callable[..., None],
    loopback_is_public: None,
    tls: ssl.SSLContext,
    recording_proxy: _Server,
) -> None:
    server, url = _serve_as(path, {path.path: path.answer}, serve, fake_dns, tls)

    assert path.result(path.call(url)) == path.expected
    assert recording_proxy.hits == []
    assert server.hits == [(path.method, path.path)]


def test_vendor_health_probe_reports_a_redirect_without_following_it(
    serve: Callable[..., _Server],
    fake_dns: Callable[..., None],
    loopback_is_public: None,
    tls: ssl.SSLContext,
) -> None:
    """Perplexity's key check only asks whether the host answers: a 3xx is an answer."""
    from koda.services.provider_auth import verify_provider_api_key

    other = serve({"/": (200, {"Content-Type": "application/json"}, b"{}")}, tls=tls)
    fake_dns("other.koda.test", PUBLIC_IP, connect_ip="127.0.0.1")
    server = serve({"/": _redirect(f"https://other.koda.test:{other.port}/")}, tls=tls)
    fake_dns("api.perplexity.ai", PUBLIC_IP, connect_ip="127.0.0.1", connect_port=server.port)

    result = verify_provider_api_key("perplexity", "test-key")

    assert result.verified is True, result.last_error
    assert result.details["http_status"] == 302
    assert server.hits == [("GET", "/")]
    assert other.hits == []


def test_operator_health_probe_reports_a_redirect_without_following_it(serve: Callable[..., _Server]) -> None:
    from koda.services.provider_auth import verify_provider_api_key

    server = serve({"/": _redirect("/elsewhere"), "/elsewhere": (500, {}, b"")})

    result = verify_provider_api_key("perplexity", "test-key", base_url=server.origin)

    assert result.verified is True, result.last_error
    assert result.details["http_status"] == 302
    assert server.hits == [("GET", "/")]


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


def _documented_mcp_grant() -> list[str]:
    """The ``MCP_ALLOWED_PRIVATE_NETWORKS`` example in ``.env.example``."""
    prefix = "# MCP_ALLOWED_PRIVATE_NETWORKS="
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return [entry.strip() for entry in line.removeprefix(prefix).split(",")]
    raise AssertionError(".env.example documents no MCP_ALLOWED_PRIVATE_NETWORKS example")


def test_documented_tailscale_grant_admits_dual_stack_nodes(
    mcp_grant: Callable[..., None], fake_dns: Callable[..., None]
) -> None:
    """MagicDNS answers A and AAAA for a node; the documented grant must cover both."""
    from koda.services.mcp_client import _validate_url

    fake_dns("mcp.tailnet.ts.net", ("100.101.102.103", "fd7a:115c:a1e0::1234"))
    url = "http://mcp.tailnet.ts.net:8000/mcp"

    # One answer outside the grant refuses the host, so the IPv4 range alone is not enough.
    mcp_grant("100.64.0.0/10")
    with pytest.raises(ValueError, match="not allowed"):
        _validate_url(url)

    documented = _documented_mcp_grant()
    mcp_grant(*documented)
    _validate_url(url)
    _validate_url("http://[fd7a:115c:a1e0::1234]:8000/mcp")
    reference = (ROOT / "docs" / "config" / "reference.md").read_text(encoding="utf-8")
    assert ",".join(documented) in reference


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/mcp",
        "http://[::ffff:127.0.0.1]:8000/mcp",
        "http://169.254.169.254/latest/meta-data",
        "http://0.0.0.0:8000/mcp",
        "http://224.0.0.1/",
        # Cloud metadata outside link-local: Alibaba Cloud, and AWS IMDS over IPv6.
        "http://100.100.100.200/latest/meta-data/",
        "http://[::ffff:100.100.100.200]/latest/meta-data/",
        "http://[64:ff9b::6464:64c8]/latest/meta-data/",
        "http://[fd00:ec2::254]/latest/meta-data/",
    ],
)
def test_mcp_grant_never_covers_loopback_metadata_or_unspecified(url: str, mcp_grant: Callable[..., None]) -> None:
    from koda.services.mcp_client import _validate_url

    mcp_grant("0.0.0.0/0", "::/0")
    with pytest.raises(ValueError, match="not allowed"):
        _validate_url(url)


@pytest.mark.parametrize(
    ("grant", "metadata", "neighbour"),
    [
        ("100.64.0.0/10", "100.100.100.200", "100.100.100.201"),
        ("fd00::/8", "fd00:ec2::254", "fd00:ec2::253"),
    ],
    ids=["tailscale-range-alibaba-metadata", "ula-range-aws-ipv6-imds"],
)
async def test_grant_covers_its_range_except_the_metadata_address(
    grant: str, metadata: str, neighbour: str, mcp_grant: Callable[..., None], fake_dns: Callable[..., None]
) -> None:
    """A plausible grant still refuses the metadata address inside it, at check and at connect."""
    from unittest.mock import AsyncMock, patch

    from koda.services.mcp_client import _validate_url

    mcp_grant(grant)
    fake_dns("metadata.koda.test", metadata)
    fake_dns("neighbour.koda.test", neighbour)
    for url in (f"http://{_literal_host(metadata)}/latest/meta-data/", "http://metadata.koda.test/latest/meta-data/"):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_url(url)
    _validate_url(f"http://{_literal_host(neighbour)}/mcp")
    _validate_url("http://neighbour.koda.test/mcp")

    resolver = http_client._PublicOnlyResolver((ipaddress.ip_network(grant),))
    family = socket.AF_INET6 if ":" in metadata else socket.AF_INET
    answer = [{"hostname": "h", "host": metadata, "port": 80, "family": family, "proto": 6, "flags": 0}]
    with (
        patch.object(resolver._resolver, "resolve", AsyncMock(return_value=answer)),
        pytest.raises(OSError, match="private/reserved"),
    ):
        await resolver.resolve("h", 80)
    await resolver.close()


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


def test_guarded_urlopen_public_only_stops_at_the_origin(
    serve: Callable[..., _Server], loopback_is_public: None
) -> None:
    """Without a grant, a redirect is followed within its origin and refused beyond it."""
    other = serve()
    server = serve({"/hop": _redirect(f"{other.origin}/secret"), "/same": _redirect("/ok"), "/ok": _MODELS})

    with pytest.raises(http_client.GuardedRequestError, match="another origin"):
        http_client.guarded_urlopen(urllib.request.Request(f"{server.origin}/hop"))
    response = http_client.guarded_urlopen(urllib.request.Request(f"{server.origin}/same"))

    assert response.read() == _MODELS[2]
    assert other.hits == []
    assert server.hits == [("GET", "/hop"), ("GET", "/same"), ("GET", "/ok")]


def test_guarded_urlopen_public_only_ignores_proxy_environment(
    serve: Callable[..., _Server], loopback_is_public: None, recording_proxy: _Server
) -> None:
    server = serve({"/ok": _MODELS})

    assert http_client.guarded_urlopen(urllib.request.Request(f"{server.origin}/ok")).read() == _MODELS[2]
    assert recording_proxy.hits == []
    assert server.hits == [("GET", "/ok")]


def test_guarded_urlopen_timeout_is_a_url_error() -> None:
    """A server that never answers times out as a URLError, which callers already catch."""
    silent = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    silent.bind(("127.0.0.1", 0))
    silent.listen(1)  # the kernel completes the handshake; nothing ever answers
    try:
        url = f"http://127.0.0.1:{silent.getsockname()[1]}/slow"
        with pytest.raises(urllib.error.URLError, match="timed out"):
            http_client.guarded_urlopen(urllib.request.Request(url), timeout=0.3, allow_private=True)
    finally:
        silent.close()


def test_guarded_urlopen_refuses_a_redirect_without_location(serve: Callable[..., _Server]) -> None:
    server = serve({"/moved": (302, {}, b"")})

    with pytest.raises(http_client.GuardedRequestError, match="missing Location"):
        http_client.guarded_urlopen(urllib.request.Request(f"{server.origin}/moved"), allow_private=True)


def test_guarded_urlopen_stops_a_redirect_loop(serve: Callable[..., _Server]) -> None:
    server = serve({"/loop": _redirect("/loop")})

    with pytest.raises(http_client.GuardedRequestError, match="Too many redirects"):
        http_client.guarded_urlopen(urllib.request.Request(f"{server.origin}/loop"), allow_private=True)
    assert len(server.hits) == 11  # the request and the ten redirects it may follow


def test_guarded_urlopen_caps_a_response_without_content_length(serve: Callable[..., _Server]) -> None:
    """A body with no Content-Length is counted while it streams in."""
    server = serve({"/stream": (200, {_UNSIZED: "1"}, b"x" * 200_000), "/small": (200, {_UNSIZED: "1"}, b"y" * 512)})

    with pytest.raises(http_client.GuardedRequestError, match="exceeded size limit"):
        http_client.guarded_urlopen(
            urllib.request.Request(f"{server.origin}/stream"), allow_private=True, max_size=1024
        )
    response = http_client.guarded_urlopen(
        urllib.request.Request(f"{server.origin}/small"), allow_private=True, max_size=1024
    )
    assert response.headers.get("Content-Length") is None
    assert response.read() == b"y" * 512


@pytest.mark.parametrize(
    ("status", "method_after"),
    [(301, "GET"), (302, "GET"), (303, "GET"), (307, "POST"), (308, "POST")],
)
def test_guarded_urlopen_redirected_post_method(status: int, method_after: str, serve: Callable[..., _Server]) -> None:
    """301, 302 and 303 after a POST continue as a GET without the body; 307 and 308 resend it."""
    server = serve({"/form": _redirect("/done", status=status), "/done": _MODELS})
    body = b'{"text": "hi"}'

    request = urllib.request.Request(f"{server.origin}/form", data=body, method="POST")
    response = http_client.guarded_urlopen(request, allow_private=True)

    assert response.read() == _MODELS[2]
    assert server.hits == [("POST", "/form"), (method_after, "/done")]
    assert server.bodies == [body, body if method_after == "POST" else b""]


def test_guarded_urlopen_sends_bytes_bodies_only(serve: Callable[..., _Server]) -> None:
    server = serve()
    request = urllib.request.Request(f"{server.origin}/rpc", data="text", method="POST")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="bytes request bodies only"):
        http_client.guarded_urlopen(request, allow_private=True)
    assert server.hits == []
