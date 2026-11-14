"""The control-plane entrypoints configure logging before anything logs (D-049, M1-E1-T4).

Each test starts a real entrypoint (``python -m koda.control_plane``'s ``main`` and
``launcher.py``) in a subprocess with a stand-in supervisor, then reads what the process
wrote. The stand-in writes the first-boot setup code the way the real control plane does,
logs secrets under redacted keys and logs an exception from a frame that holds the code.

The code must reach stderr once, in the banner, and never stdout, where the structured log
goes, nor a traceback. ``LOG_FORMAT=json`` must turn every stdout line into a JSON object.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_STAND_IN = """
import logging
import sys

import koda.control_plane.supervisor as supervisor
import koda.services.browser_bootstrap as browser_bootstrap
from koda.logging_config import get_logger

log = get_logger("entrypoint_under_test")


def browser_stand_in():
    # The first thing the real entrypoint runs; anything it logs must already be configured.
    log.info("browser_bootstrap_checked")


def fail_with(code):
    raise RuntimeError("supervisor failed")


async def supervisor_stand_in():
    from koda.control_plane.bootstrap_file import ensure_bootstrap_file

    log.info("supervisor_started")
    code = ensure_bootstrap_file(has_owner=False)
    log.info("operator_login_attempt", code=code, password="hunter2-password", token="tok-secret-value")
    try:
        fail_with(code)
    except RuntimeError:
        log.exception("supervisor_crashed")
    # An OAuth callback carries its authorization code in the query string.
    logging.getLogger("aiohttp.access").info("GET /oauth/callback?code=oauth-code-value 200")


browser_bootstrap.ensure_browser_installed_in_background = browser_stand_in
supervisor.run_supervisor = supervisor_stand_in
"""

_ENTRYPOINTS = {
    "python -m koda.control_plane": "from koda.control_plane.__main__ import main\nmain()\n",
    "launcher.py": f"import runpy\nrunpy.run_path({str(REPO_ROOT / 'launcher.py')!r}, run_name='__main__')\n",
}

_SECRETS = ("hunter2-password", "tok-secret-value", "oauth-code-value")


def _run(entrypoint: str, tmp_path: Path, log_format: str) -> tuple[str, str, str]:
    """Run an entrypoint with the stand-in supervisor; return (stdout, stderr, setup code)."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("CONTROL_PLANE_BOOTSTRAP")}
    env.update({"STATE_ROOT_DIR": str(tmp_path / "state"), "LOG_FORMAT": log_format, "HOME": str(tmp_path)})
    result = subprocess.run(
        [sys.executable, "-c", _STAND_IN + _ENTRYPOINTS[entrypoint]],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    bootstrap = tmp_path / "state" / "control_plane" / "bootstrap.txt"
    code = bootstrap.read_text(encoding="utf-8").splitlines()[0]
    assert len(code) == 14, code
    return result.stdout, result.stderr, code


def _json_lines(stdout: str) -> list[dict[str, Any]]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    assert lines, "the entrypoint logged nothing"
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pytest.fail(f"LOG_FORMAT=json did not take effect; stdout line is not JSON: {line!r}")
    return events


@pytest.mark.parametrize("entrypoint", sorted(_ENTRYPOINTS))
def test_log_format_json_takes_effect_and_redacts(entrypoint: str, tmp_path: Path) -> None:
    stdout, stderr, code = _run(entrypoint, tmp_path, "json")

    assert code not in stdout
    events = _json_lines(stdout)
    names = [event.get("event") for event in events]
    expected = ["supervisor_started", "bootstrap_file_written", "operator_login_attempt", "supervisor_crashed"]
    if entrypoint == "python -m koda.control_plane":
        expected.insert(0, "browser_bootstrap_checked")
    assert names == expected

    (written,) = [event for event in events if event["event"] == "bootstrap_file_written"]
    assert written["code_source"] == "generated"
    (attempt,) = [event for event in events if event["event"] == "operator_login_attempt"]
    assert attempt["code"] == attempt["password"] == attempt["token"] == "***"

    for secret in _SECRETS:
        assert secret not in stdout
        assert secret not in stderr


@pytest.mark.parametrize("entrypoint", sorted(_ENTRYPOINTS))
def test_console_logs_carry_no_setup_code_and_no_traceback_locals(entrypoint: str, tmp_path: Path) -> None:
    stdout, stderr, code = _run(entrypoint, tmp_path, "console")

    assert code not in stdout
    for secret in _SECRETS:
        assert secret not in stdout
        assert secret not in stderr
    assert "bootstrap_file_written" in stdout
    assert "supervisor_crashed" in stdout
    # The traceback is printed, without the frame's local variables.
    assert "locals" not in stdout
    assert "RuntimeError: supervisor failed" in stdout


@pytest.mark.parametrize("log_format", ["json", "console"])
def test_the_setup_code_appears_once_in_a_console_banner(log_format: str, tmp_path: Path) -> None:
    stdout, stderr, code = _run("python -m koda.control_plane", tmp_path, log_format)

    assert stderr.count(code) == 1
    banner = stderr[stderr.index("Koda setup code") :]
    assert code in banner
    assert "/setup" in banner
    assert str(tmp_path / "state" / "control_plane" / "bootstrap.txt") in banner
