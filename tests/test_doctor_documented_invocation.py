"""`python3 scripts/doctor.py` works the way the install docs run it.

The docs run doctor from a source checkout with the system Python
(`docs/install/local.md`, "Doctor"). That puts `scripts/` first on
`sys.path`, not the checkout, and the system Python usually lacks Koda's
dependencies. These tests run the script as a subprocess against a healthy
native install: the control plane, the dashboard and Postgres answer, and
object storage is off (`OBJECT_STORAGE_REQUIRED=false`).

``python -S`` stands in for a system Python: it starts without site-packages,
so neither Koda's dependencies nor its installed package are importable, and
its ``sys.prefix`` is the base interpreter, not Koda's virtualenv.

Skipping the sandbox check is only for such a foreign interpreter. In Koda's
own environment a missing dependency is a broken install and fails doctor;
the last tests pin that rule in-process.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCTOR = REPO_ROOT / "scripts" / "doctor.py"
PROXY_VARIABLES = ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")
# What the sandbox doctor reads. Doctor hands it the --env-file values, so the
# test .env pins them; koda.config would otherwise fill BROWSER_ALLOW_PRIVATE_NETWORK
# from the shell or the checkout's own .env.
SANDBOX_INPUT_PREFIXES = ("KODA_MCP_", "SANDBOX_", "KODA_CHANNEL_")
SANDBOX_INPUTS = (
    "BROWSER_ALLOW_PRIVATE_NETWORK",
    "KODA_CGROUP_ROOT",
    "KODA_REMOTE_SESSION",
    "KODA_EXPLICIT_REMOTE_POLICY",
)


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
    cgroup_root = tmp_path / "cgroup"
    cgroup_root.mkdir(exist_ok=True)
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
                # The sandbox inputs, so its result does not depend on the developer's machine.
                "BROWSER_ALLOW_PRIVATE_NETWORK=false",
                "KODA_MCP_ALLOW_PRIVATE_EGRESS=false",
                "KODA_MCP_ISOLATION=native",
                "KODA_MCP_NETWORK_MODE=egress_allowlist",
                "KODA_MCP_RISK_CLASS=read_context",
                "KODA_CHANNEL_TYPE=local",
                f"KODA_CGROUP_ROOT={cgroup_root}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return env_file


def _subprocess_env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in PROXY_VARIABLES
        and key != "PYTHONPATH"
        and key not in SANDBOX_INPUTS
        and not key.startswith(SANDBOX_INPUT_PREFIXES)
    }
    env["HOME"] = str(tmp_path / "home")
    env.update(overrides)
    return env


async def _run_doctor(
    python_args: list[str],
    tmp_path: Path,
    port: int,
    *extra_args: str,
    env_overrides: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], str]:
    env_file = _native_env_file(tmp_path, port)
    env = _subprocess_env(tmp_path, **(env_overrides or {}))
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
    assert sandbox["failed_checks"] == []
    assert payload["sandbox_doctor"]["schema_version"] == "sandbox_doctor.v1"
    assert returncode == 0, stderr


async def test_doctor_sandbox_result_ignores_the_shell_and_the_checkout_env(
    native_install: TestServer, tmp_path: Path
) -> None:
    """A developer's own BROWSER_ALLOW_PRIVATE_NETWORK=true must not change what the test .env says."""
    returncode, payload, stderr = await _run_doctor(
        [sys.executable], tmp_path, native_install.port, env_overrides={"BROWSER_ALLOW_PRIVATE_NETWORK": "true"}
    )

    assert _check(payload, "sandbox_doctor")["failed_checks"] == []
    assert returncode == 0, stderr


def _blocked_module_dir(tmp_path: Path, module: str) -> Path:
    """A PYTHONPATH entry that makes ``module`` look uninstalled, as in a venv that lost one dependency."""
    blocked = tmp_path / "blocked-modules"
    package = blocked / module
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        f"raise ModuleNotFoundError({f'No module named {module!r}'!r}, name={module!r})\n", encoding="utf-8"
    )
    return blocked


async def test_doctor_in_koda_environment_with_a_missing_dependency_fails_the_sandbox_check(
    native_install: TestServer, tmp_path: Path
) -> None:
    """Koda's own interpreter missing a dependency is a broken install, not a foreign python3: doctor fails."""
    blocked = _blocked_module_dir(tmp_path, "structlog")

    returncode, payload, _stderr = await _run_doctor(
        [sys.executable], tmp_path, native_install.port, env_overrides={"PYTHONPATH": str(blocked)}
    )

    sandbox = _check(payload, "sandbox_doctor")
    assert sandbox["status"] == "unavailable"
    assert sandbox["ok"] is False
    assert "structlog" in json.dumps(payload["sandbox_doctor"])
    assert payload["ok"] is False
    assert returncode == 1


def _load_doctor() -> ModuleType:
    spec = importlib.util.spec_from_file_location("doctor_under_test", DOCTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raise(exc: BaseException) -> Any:
    def raiser() -> Any:
        raise exc

    return raiser


@pytest.mark.parametrize("missing", ["koda", "koda.services"])
def test_a_missing_koda_package_fails_the_sandbox_check_under_any_interpreter(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    """Without Koda itself on the path doctor is not run from a checkout: skipping would hide that."""
    doctor = _load_doctor()
    monkeypatch.setattr(
        doctor, "_import_sandbox_doctor", _raise(ModuleNotFoundError(f"No module named {missing!r}", name=missing))
    )
    monkeypatch.setattr(doctor, "_is_koda_environment", lambda: False, raising=False)

    assert doctor.build_sandbox_doctor({})["status"] == "unavailable"


@pytest.mark.parametrize(("koda_environment", "status"), [(False, "skipped"), (True, "unavailable")])
def test_a_missing_dependency_skips_the_sandbox_check_only_outside_koda_environment(
    monkeypatch: pytest.MonkeyPatch, koda_environment: bool, status: str
) -> None:
    doctor = _load_doctor()
    monkeypatch.setattr(
        doctor, "_import_sandbox_doctor", _raise(ModuleNotFoundError("No module named 'structlog'", name="structlog"))
    )
    monkeypatch.setattr(doctor, "_is_koda_environment", lambda: koda_environment, raising=False)

    assert doctor.build_sandbox_doctor({})["status"] == status


@pytest.mark.parametrize(
    ("prefix", "variables", "installed", "expected"),
    [
        ("checkout/.venv", {}, False, True),
        ("elsewhere/venv", {"VIRTUAL_ENV": "{tmp}/elsewhere/venv"}, False, True),
        # uv reads a relative UV_PROJECT_ENVIRONMENT against the project root.
        ("checkout/envs/koda", {"UV_PROJECT_ENVIRONMENT": "envs/koda"}, False, True),
        ("elsewhere/venv", {}, True, True),
        # An active virtualenv that is not the one running doctor says nothing about this interpreter.
        (
            "usr",
            {"VIRTUAL_ENV": "{tmp}/checkout/.venv", "UV_PROJECT_ENVIRONMENT": "{tmp}/checkout/.venv"},
            False,
            False,
        ),
        ("usr", {}, False, False),
    ],
    ids=[
        "checkout-venv",
        "active-virtualenv",
        "uv-project-environment",
        "koda-installed",
        "other-interpreter-with-venv-active",
        "system-python",
    ],
)
def test_koda_environment_is_the_interpreter_koda_is_installed_for(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    prefix: str,
    variables: dict[str, str],
    installed: bool,
    expected: bool,
) -> None:
    doctor = _load_doctor()
    monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path / "checkout")
    monkeypatch.setattr(sys, "prefix", str(tmp_path / prefix))
    monkeypatch.setattr(doctor, "_koda_installed", lambda: installed)
    for name in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in variables.items():
        monkeypatch.setenv(name, value.format(tmp=tmp_path))

    assert doctor._is_koda_environment() is expected
