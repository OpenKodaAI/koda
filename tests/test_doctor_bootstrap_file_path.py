"""`koda doctor` and `scripts/doctor.py` still show where the setup code is.

Before login, onboarding/status answers only `has_owner` and
`bootstrap_required` (D-050), so both doctors read the bootstrap file path from
the public auth/status, which names it only while no owner exists. These tests
run the doctors against the real control-plane routes and middlewares.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from koda.control_plane import api as control_plane_api
from koda.control_plane import operator_auth as operator_auth_mod

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "packages" / "cli" / "bin" / "koda.mjs"
OWNER_STATES = pytest.mark.parametrize("owner_exists", [False, True], ids=["before-setup", "after-setup"])


@pytest.fixture
def bootstrap_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "control_plane" / "bootstrap.txt"


@pytest.fixture
async def control_plane(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    bootstrap_path: Path,
) -> AsyncIterator[TestServer]:
    """The public status routes behind the real middlewares, owner state from the test's parameter."""
    owner_exists: bool = request.node.callspec.params["owner_exists"]
    monkeypatch.setattr(operator_auth_mod.OperatorAuthService, "has_owner", lambda self: owner_exists)
    monkeypatch.setattr(operator_auth_mod, "ensure_bootstrap_file", lambda **_: None)
    monkeypatch.setattr(operator_auth_mod, "bootstrap_file_path", lambda: bootstrap_path)
    service = operator_auth_mod.OperatorAuthService()
    monkeypatch.setattr(control_plane_api, "_auth_service", lambda: service)
    monkeypatch.setattr(control_plane_api, "_manager", MagicMock)

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "healthy"})

    async def dashboard(_request: web.Request) -> web.Response:
        return web.Response(text="<html></html>", content_type="text/html")

    app = web.Application(
        middlewares=[
            control_plane_api.control_plane_error_middleware,
            control_plane_api.control_plane_auth_middleware,
        ]
    )
    app.router.add_get("/health", health)
    app.router.add_get("/", dashboard)
    app.router.add_get("/api/control-plane/onboarding/status", control_plane_api.onboarding_status)
    app.router.add_get("/api/control-plane/auth/status", control_plane_api.auth_status)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        yield server
    finally:
        await server.close()


def _expected_onboarding(owner_exists: bool, bootstrap_path: Path) -> dict[str, Any]:
    return {
        "has_owner": owner_exists,
        "bootstrap_required": not owner_exists,
        # The file exists only until the owner registers.
        "bootstrap_file_path": None if owner_exists else str(bootstrap_path),
    }


@OWNER_STATES
@pytest.mark.skipif(shutil.which("node") is None, reason="node is required to run the Koda CLI")
async def test_cli_doctor_reports_the_bootstrap_file_path_from_the_public_auth_status(
    control_plane: TestServer,
    tmp_path: Path,
    bootstrap_path: Path,
    owner_exists: bool,
) -> None:
    install_dir = tmp_path / "koda-install"
    install_dir.mkdir()
    port = control_plane.port
    (install_dir / ".env").write_text(f"CONTROL_PLANE_PORT={port}\nWEB_PORT={port}\n", encoding="utf-8")

    process = await asyncio.create_subprocess_exec(
        "node",
        str(CLI),
        "doctor",
        "--dir",
        str(install_dir),
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

    assert process.returncode == 0, stderr.decode()
    onboarding = json.loads(stdout)["checks"]["onboarding"]
    assert onboarding == {"ok": True, "status": 200, **_expected_onboarding(owner_exists, bootstrap_path)}


def _load_doctor_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("doctor_script", ROOT / "scripts" / "doctor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@OWNER_STATES
async def test_doctor_script_reports_the_bootstrap_file_path_from_the_public_auth_status(
    control_plane: TestServer,
    monkeypatch: pytest.MonkeyPatch,
    bootstrap_path: Path,
    owner_exists: bool,
) -> None:
    for name in ("http_proxy", "HTTP_PROXY"):
        monkeypatch.delenv(name, raising=False)
    module = _load_doctor_script()
    base_url = f"http://127.0.0.1:{control_plane.port}"

    with patch.object(module, "check_socket", return_value={"ok": True}):
        # urllib blocks, so the doctor runs in a thread while the loop serves it.
        payload = await asyncio.to_thread(
            module.run_doctor,
            env={"CONTROL_PLANE_API_TOKEN": "operator-token"},
            base_url=base_url,
            dashboard_url=base_url,
        )

    onboarding = next(check for check in payload["checks"] if check["name"] == "onboarding_status")
    assert onboarding == {"name": "onboarding_status", "ok": True, **_expected_onboarding(owner_exists, bootstrap_path)}
