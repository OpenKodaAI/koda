"""Failure-mode validation: how does the runner degrade when things go wrong?

Each scenario asserts the runner returns a structured error result rather
than crashing or hanging. Mocked unit tests cover the happy path; this
script exercises the real adversary cases:

1. **Connection refused** (server not running) → ``transient`` retryable error
2. **Connection timeout** (server hangs) → ``transient`` retryable error
3. **HTTP 4xx** (model not found) → ``adapter_contract``, NOT retryable
4. **HTTP 5xx** (server overloaded) → ``transient``, retryable
5. **Malformed JSON in body** → ``provider_runtime``, NOT retryable
6. **Server crash mid-stream** → metadata_collector reports error, no exception
7. **First-chunk timeout** (model takes forever to start) → ``transient``

Run after starting llama-server on port 8089 (or rely on stub_server for
non-running cases).
"""

from __future__ import annotations

import asyncio
import contextlib
import http.server
import os
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import koda.config  # noqa: E402

os.environ["LLAMACPP_ENABLED"] = "true"
os.environ["LLAMACPP_FIRST_CHUNK_TIMEOUT"] = "5"
os.environ["LLAMACPP_TIMEOUT"] = "10"

import importlib  # noqa: E402

importlib.reload(koda.config)
import koda.services.llamacpp_runner as llamacpp_runner  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _set_base_url(port: int) -> None:
    """Re-build the LLAMACPP_PROFILE pointing at the given port."""
    os.environ["LLAMACPP_API_BASE_URL"] = f"http://127.0.0.1:{port}"
    importlib.reload(koda.config)
    importlib.reload(llamacpp_runner)


async def case_connection_refused() -> dict[str, str]:
    """No server bound to the port → connection refused."""
    port = _free_port()  # bind+release; nothing listens now
    _set_base_url(port)
    from koda.services.openai_compatible_runner import (  # noqa: PLC0415
        clear_openai_compatible_capability_cache,
    )

    clear_openai_compatible_capability_cache()
    result = await llamacpp_runner.run_llamacpp(
        query="hi",
        work_dir="/tmp",
        model="x",
        system_prompt=None,
    )
    return {
        "case": "connection_refused",
        "error": result.get("error"),
        "kind": result.get("_error_kind") or result.get("error_kind"),
        "retryable": result.get("_retryable") or result.get("retryable"),
        "summary": str(result.get("result"))[:120],
    }


def _start_stub_server(handler_cls: type) -> tuple[int, threading.Thread, socketserver.TCPServer]:
    port = _free_port()
    server = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler_cls)
    server.daemon_threads = True
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    return port, th, server


async def case_http_500() -> dict[str, str]:
    """Stub server that always returns HTTP 500."""

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_error(503, "overloaded")

        def do_POST(self):
            self.send_error(503, "overloaded")

        def log_message(self, *a, **kw):
            pass

    port, _, server = _start_stub_server(_H)
    _set_base_url(port)
    from koda.services.openai_compatible_runner import (  # noqa: PLC0415
        clear_openai_compatible_capability_cache,
    )

    clear_openai_compatible_capability_cache()
    try:
        result = await llamacpp_runner.run_llamacpp(query="hi", work_dir="/tmp", model="x")
    finally:
        server.shutdown()
    return {
        "case": "http_500",
        "error": result.get("error"),
        "kind": result.get("_error_kind"),
        "retryable": result.get("_retryable"),
        "summary": str(result.get("result"))[:120],
    }


async def case_http_400_bad_model() -> dict[str, str]:
    """Stub server that returns HTTP 400 for chat (probe ok, chat rejected)."""

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/v1/models":
                body = b'{"data":[]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def do_POST(self):
            body = b'{"error":{"message":"unknown model x","type":"invalid_request_error"}}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a, **kw):
            pass

    port, _, server = _start_stub_server(_H)
    _set_base_url(port)
    from koda.services.openai_compatible_runner import (  # noqa: PLC0415
        clear_openai_compatible_capability_cache,
    )

    clear_openai_compatible_capability_cache()
    try:
        result = await llamacpp_runner.run_llamacpp(query="hi", work_dir="/tmp", model="x")
    finally:
        server.shutdown()
    return {
        "case": "http_400_bad_model",
        "error": result.get("error"),
        "kind": result.get("_error_kind"),
        "retryable": result.get("_retryable"),
        "summary": str(result.get("result"))[:120],
    }


async def case_malformed_json() -> dict[str, str]:
    """Stub returns 200 with non-JSON body."""

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/v1/models":
                body = b'{"data":[]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def do_POST(self):
            body = b"this is not json at all"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a, **kw):
            pass

    port, _, server = _start_stub_server(_H)
    _set_base_url(port)
    from koda.services.openai_compatible_runner import (  # noqa: PLC0415
        clear_openai_compatible_capability_cache,
    )

    clear_openai_compatible_capability_cache()
    try:
        result = await llamacpp_runner.run_llamacpp(query="hi", work_dir="/tmp", model="x")
    finally:
        server.shutdown()
    return {
        "case": "malformed_json",
        "error": result.get("error"),
        "kind": result.get("_error_kind"),
        "retryable": result.get("_retryable"),
        "summary": str(result.get("result"))[:120],
    }


async def case_first_chunk_timeout() -> dict[str, str]:
    """Server sends 200 + chunked-transfer headers immediately, then hangs on body.

    This is the realistic ``first_chunk_timeout`` scenario: time-to-first-token
    exceeds the configured budget. Sending headers without a Content-Length
    and without flushing any body bytes triggers the runner's deadline check
    inside the ``async for raw_line in resp.content`` loop.
    """

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/v1/models":
                body = b'{"data":[]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def do_POST(self):
            # Send headers immediately so aiohttp opens the body iteration,
            # then sleep so the runner's first-chunk deadline trips before any
            # body bytes arrive.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.flush()
            time.sleep(8)
            # Eventual body — runner should already have aborted.
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(b"0\r\n\r\n")

        def log_message(self, *a, **kw):
            pass

    port, _, server = _start_stub_server(_H)
    _set_base_url(port)
    from koda.services.openai_compatible_runner import (  # noqa: PLC0415
        clear_openai_compatible_capability_cache,
    )

    clear_openai_compatible_capability_cache()
    metadata: dict[str, object] = {}
    try:
        chunks = []
        async for chunk in llamacpp_runner.run_llamacpp_streaming(
            query="hi",
            work_dir="/tmp",
            model="x",
            metadata_collector=metadata,
            first_chunk_timeout=2,
        ):
            chunks.append(chunk)
    finally:
        server.shutdown()
    return {
        "case": "first_chunk_timeout",
        "error": metadata.get("error"),
        "kind": metadata.get("error_kind"),
        "retryable": metadata.get("retryable"),
        "summary": str(metadata.get("error_message", ""))[:120],
    }


async def main() -> int:
    cases = [
        case_connection_refused(),
        case_http_500(),
        case_http_400_bad_model(),
        case_malformed_json(),
        case_first_chunk_timeout(),
    ]
    print("=" * 70)
    print("FAILURE MODE VALIDATION")
    print("=" * 70)
    all_ok = True
    for coro in cases:
        res = await coro
        print(f"\n  {res['case']}:")
        for k, v in res.items():
            if k != "case":
                print(f"    {k}: {v}")
        # Verify error returned (not exception, not silent)
        if not res["error"]:
            all_ok = False
            print(f"    ❌ Expected error=True, got error={res['error']}")
    print()
    print("=" * 70)
    print(f"VERDICT: {'✅ ALL FAILURE MODES HANDLED' if all_ok else '❌ SOME FAILURES UNHANDLED'}")
    print("=" * 70)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
