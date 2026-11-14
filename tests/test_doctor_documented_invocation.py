"""`python3 scripts/doctor.py` works the way the install docs run it.

The docs run doctor from a source checkout with the system Python
(`docs/install/local.md`, "Doctor"). That puts `scripts/` first on
`sys.path`, not the checkout, and the system Python usually lacks Koda's
dependencies. These tests run the script as a subprocess against a healthy
native install: the control plane, the dashboard and Postgres answer, and
object storage is off (`OBJECT_STORAGE_REQUIRED=false`).

``python -S`` stands in for a system Python: it starts without site-packages,
so neither Koda's dependencies nor its installed package are importable.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCTOR = REPO_ROOT / "scripts" / "doctor.py"
PROXY_VARIABLES = ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")


@pytest.fixture
async def native_install() -> AsyncIterator[TestServer]:
    """One local server for the control plane, the dashboard and the Postgres port."""

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "healthy"})

    async def dashboard(_request: web.Request) -> web.Response:
        return web.Response(text="<html></html>", content_type="text/html")

    async def onboarding_status(_request: web.Request) -> web.Response:
        return web.json_response({"has_owner": True, "bootstrap_required": False})

    async def auth_status(_request: web.Request) -> web.Response:
        return web.json_response({"has_owner": True})

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/", dashboard)
    app.router.add_get("/api/control-plane/onboarding/status", onboarding_status)
    app.router.add_get("/api/control-plane/auth/status", auth_status)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        yield server
    finally:
        await server.close()


def _native_env_file(tmp_path: Path, port: int) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                f"CONTROL_PLANE_PORT={port}",
                f"WEB_PORT={port}",
                "CONTROL_PLANE_API_TOKEN=" + "c" * 64,
                "RUNTIME_LOCAL_UI_TOKEN=" + "r" * 64,
                "OBJECT_STORAGE_REQUIRED=false",
                f"KNOWLEDGE_V2_POSTGRES_DSN=postgresql://koda:4b1f0c2e9d8a7f6e5d4c3b2a19081726@127.0.0.1:{port}/koda",
                f"STATE_ROOT_DIR={tmp_path / 'state'}",
                f"RUNTIME_EPHEMERAL_ROOT={tmp_path / 'runtime'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return env_file


async def _run_doctor(
    python_args: list[str], tmp_path: Path, port: int, *extra_args: str
) -> tuple[int, dict[str, Any], str]:
    env_file = _native_env_file(tmp_path, port)
    env = {key: value for key, value in os.environ.items() if key not in PROXY_VARIABLES and key != "PYTHONPATH"}
    env["HOME"] = str(tmp_path / "home")
    base_url = f"http://127.0.0.1:{port}"
    process = await asyncio.create_subprocess_exec(
        *python_args,
        str(DOCTOR),
        "--env-file",
        str(env_file),
        "--base-url",
        base_url,
        "--dashboard-url",
        base_url,
        *extra_args,
        cwd=str(tmp_path),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
    return int(process.returncode or 0), json.loads(stdout), stderr.decode()


def _check(payload: dict[str, Any], name: str) -> dict[str, Any]:
    return next(check for check in payload["checks"] if check["name"] == name)


async def test_doctor_run_with_a_bare_system_python_exits_zero_on_a_healthy_native_install(
    native_install: TestServer, tmp_path: Path
) -> None:
    returncode, payload, stderr = await _run_doctor([sys.executable, "-S"], tmp_path, native_install.port)

    assert returncode == 0, stderr
    assert payload["ok"] is True
    # Object storage is off on this install: still reported, but not required.
    assert payload["object_storage_required"] is False
    assert [check["name"] for check in payload["checks"] if not check.get("ok")] == [
        "object_storage_endpoint",
        "object_storage_bucket",
        "object_storage_access_key",
        "object_storage_secret_key",
        "object_storage_socket",
    ]
    assert all(check["required"] is False for check in payload["checks"] if not check.get("ok"))
    sandbox = _check(payload, "sandbox_doctor")
    # Koda itself is importable from the checkout; only its third-party dependencies are missing here.
    assert sandbox["status"] == "skipped"
    assert "No module named 'koda'" not in json.dumps(payload)
    assert "uv run python scripts/doctor.py" in sandbox["user_action"]


async def test_doctor_strict_still_requires_the_sandbox_check(native_install: TestServer, tmp_path: Path) -> None:
    """The pre-deploy gate does not pass on a sandbox check that could not run."""
    returncode, payload, _stderr = await _run_doctor([sys.executable, "-S"], tmp_path, native_install.port, "--strict")

    assert returncode == 1
    sandbox = _check(payload, "sandbox_doctor")
    assert sandbox["status"] == "skipped"
    assert sandbox["ok"] is False


async def test_doctor_run_with_koda_dependencies_evaluates_the_sandbox(
    native_install: TestServer, tmp_path: Path
) -> None:
    """The interpreter that has Koda's dependencies runs the real sandbox doctor from the script."""
    returncode, payload, stderr = await _run_doctor([sys.executable], tmp_path, native_install.port)

    sandbox = _check(payload, "sandbox_doctor")
    assert sandbox["status"] in {"passed", "degraded"}, payload["sandbox_doctor"]
    assert payload["sandbox_doctor"]["schema_version"] == "sandbox_doctor.v1"
    assert returncode == 0, stderr
