"""`koda auth issue-code` keeps working while CONTROL_PLANE_API_TOKEN is being rotated.

During a rotation `.env` holds a comma-separated list (`new-token,old-token`,
see `.env.example`). The control plane accepts each token of the list on its
own (``parse_api_tokens``), so the CLI must send one token, not the raw list.

The real CLI (packages/cli/bin/koda.mjs) runs against the real control-plane
auth middleware and bootstrap-code route. The database holds no operator, so
only the break-glass tokens authenticate, and the code store is stubbed. A fake
``docker`` that always fails stands in for the app container, so the setup
code can only come from the API.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from koda.control_plane import api as control_plane_api
from koda.control_plane import operator_auth as operator_auth_mod
from koda.control_plane.settings import parse_api_tokens

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "packages" / "cli" / "bin" / "koda.mjs"
SETUP_CODE = "ABCD-EFGH-JKLM"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required to run the Koda CLI")


class _ControlPlane:
    def __init__(self, server: TestServer, received: list[str]) -> None:
        self.server = server
        self.received = received


@pytest.fixture
async def control_plane(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[_ControlPlane]:
    """The bootstrap-code route behind the real middlewares, configured with the test's token list."""
    configured: str = request.node.callspec.params["configured"]
    tokens, _ignored = parse_api_tokens(configured)
    monkeypatch.setattr(operator_auth_mod, "CONTROL_PLANE_API_TOKENS", tokens)
    # A fresh install: no owner, no sessions, no personal tokens.
    monkeypatch.setattr(operator_auth_mod, "fetch_one", lambda *_args, **_kwargs: None)

    def issue_bootstrap_code(self: Any, *, label: str = "cli", actor: str | None = None) -> dict[str, Any]:
        return {"code": SETUP_CODE, "expires_at": "2026-11-14T15:00:00+00:00", "label": label}

    monkeypatch.setattr(operator_auth_mod.OperatorAuthService, "issue_bootstrap_code", issue_bootstrap_code)
    service = operator_auth_mod.OperatorAuthService()
    monkeypatch.setattr(control_plane_api, "_auth_service", lambda: service)

    received: list[str] = []

    @web.middleware
    async def record_authorization(req: web.Request, handler: Any) -> web.StreamResponse:
        if req.path == "/api/control-plane/auth/bootstrap/codes":
            received.append(req.headers.get("Authorization", ""))
        return await handler(req)

    app = web.Application(
        middlewares=[
            record_authorization,
            control_plane_api.control_plane_error_middleware,
            control_plane_api.control_plane_auth_middleware,
        ]
    )
    app.router.add_post("/api/control-plane/auth/bootstrap/codes", control_plane_api.auth_issue_bootstrap_code)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        yield _ControlPlane(server, received)
    finally:
        await server.close()


@pytest.fixture
def fake_docker(tmp_path: Path) -> Path:
    """A ``docker`` that records its arguments and fails, so the container fallback never yields a code."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker-calls.log"
    script = bin_dir / "docker"
    script.write_text(
        f'#!/bin/sh\necho "$@" >> "{log}"\necho "fake docker: no app container" >&2\nexit 1\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return log


async def _issue_code(tmp_path: Path, port: int, configured: str) -> tuple[int, str, str]:
    install_dir = tmp_path / "koda-install"
    install_dir.mkdir()
    (install_dir / ".env").write_text(
        f"CONTROL_PLANE_PORT={port}\nWEB_PORT={port}\nCONTROL_PLANE_API_TOKEN={configured}\n",
        encoding="utf-8",
    )
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"}
    process = await asyncio.create_subprocess_exec(
        "node",
        str(CLI),
        "auth",
        "issue-code",
        "--dir",
        str(install_dir),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    return int(process.returncode or 0), stdout.decode(), stderr.decode()


@pytest.mark.parametrize(
    ("configured", "expected_bearer"),
    [
        ("new-recovery-token,old-recovery-token", "new-recovery-token"),
        (" new-recovery-token , old-recovery-token ", "new-recovery-token"),
        # The control plane never accepts an unedited placeholder, so the CLI skips it like the server does.
        ("replace-with-a-random-token,new-recovery-token", "new-recovery-token"),
        ("only-recovery-token", "only-recovery-token"),
    ],
    ids=["new-old-rotation", "spaces-around-tokens", "placeholder-first", "single-token"],
)
async def test_auth_issue_code_sends_one_token_of_the_configured_list(
    control_plane: _ControlPlane,
    fake_docker: Path,
    tmp_path: Path,
    configured: str,
    expected_bearer: str,
) -> None:
    returncode, stdout, stderr = await _issue_code(tmp_path, control_plane.server.port, configured)

    assert control_plane.received == [f"Bearer {expected_bearer}"]
    assert returncode == 0, stderr
    assert f"Setup code: {SETUP_CODE}" in stdout
    # The code came from the API: no warning about a failed API call, and no container fallback.
    assert "Note:" not in stdout
    assert not fake_docker.exists()


@pytest.mark.parametrize("configured", ["replace-with-a-random-token", " , "], ids=["placeholder", "empty-list"])
async def test_auth_issue_code_without_a_usable_token_skips_the_api(
    control_plane: _ControlPlane,
    fake_docker: Path,
    tmp_path: Path,
    configured: str,
) -> None:
    returncode, _stdout, stderr = await _issue_code(tmp_path, control_plane.server.port, configured)

    assert control_plane.received == []
    assert returncode == 1
    assert "CONTROL_PLANE_API_TOKEN has no usable token." in stderr
    # The CLI still tried the app container before giving up.
    assert "exec" in fake_docker.read_text(encoding="utf-8")
