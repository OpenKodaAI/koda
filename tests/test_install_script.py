"""``scripts/install.sh`` prerequisite logic (M7-E2-T4, D-218, F-PLT-22).

The script is sourced (``main`` runs only when it is executed), so each
function is exercised on its own with fake ``node``/``npm`` binaries and
fixture ``os-release`` files. Nothing here installs anything.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install.sh"


# Every command the installer could change the host with is a stub that fails,
# so a regression that runs ``main`` on ``source`` cannot install anything.
_HOST_CHANGING_TOOLS = ("apt-get", "curl", "docker", "gpg", "koda", "npm", "sudo")


def _run(tmp_path: Path, snippet: str, *, path_prefix: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    for name in _HOST_CHANGING_TOOLS:
        stub = stubs / name
        stub.write_text(f"#!/bin/sh\necho 'stub {name} refused' >&2\nexit 97\n", encoding="utf-8")
        stub.chmod(0o755)
    env["PATH"] = f"{stubs}:{env['PATH']}"
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}:{env['PATH']}"
    return subprocess.run(
        ["bash", "-c", f'source "{SCRIPT}"; {snippet}'],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


def _fake_node(tmp_path: Path, version: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, output in (("node", version), ("npm", "10.2.0")):
        tool = bin_dir / name
        tool.write_text(f"#!/bin/sh\necho {output}\n", encoding="utf-8")
        tool.chmod(0o755)
    return bin_dir


def _os_release(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "os-release"
    path.write_text(body, encoding="utf-8")
    return path


def test_sourcing_the_script_does_not_run_the_installer(tmp_path: Path) -> None:
    result = _run(tmp_path, "echo sourced")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "sourced"


@pytest.mark.parametrize("version", ["v12.22.9", "v18.19.1", "v19.9.0"])
def test_an_old_node_aborts_with_a_clear_message(tmp_path: Path, version: str) -> None:
    result = _run(tmp_path, "ensure_node_npm", path_prefix=_fake_node(tmp_path, version))

    assert result.returncode != 0
    assert "Node.js 20 or later" in result.stderr
    assert version in result.stderr


@pytest.mark.parametrize("version", ["v20.0.0", "v22.11.0", "v24.1.0"])
def test_node_20_or_later_is_accepted_as_is(tmp_path: Path, version: str) -> None:
    result = _run(tmp_path, "ensure_node_npm && echo ok", path_prefix=_fake_node(tmp_path, version))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_an_old_node_aborts_before_docker_is_installed(tmp_path: Path) -> None:
    snippet = "ensure_docker() { echo DOCKER_INSTALL_STARTED; }; main"
    result = _run(tmp_path, snippet, path_prefix=_fake_node(tmp_path, "v18.19.1"))

    assert result.returncode != 0
    assert "Node.js 20 or later" in result.stderr
    assert "DOCKER_INSTALL_STARTED" not in result.stdout


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("ID=debian\nVERSION_CODENAME=bookworm\n", "debian bookworm"),
        ("ID=ubuntu\nVERSION_CODENAME=noble\nUBUNTU_CODENAME=noble\n", "ubuntu noble"),
        ('ID=linuxmint\nID_LIKE="ubuntu debian"\nVERSION_CODENAME=wilma\nUBUNTU_CODENAME=noble\n', "ubuntu noble"),
        ("ID=raspbian\nID_LIKE=debian\nVERSION_CODENAME=bookworm\n", "debian bookworm"),
    ],
)
def test_docker_apt_repository_follows_the_distro(tmp_path: Path, body: str, expected: str) -> None:
    result = _run(tmp_path, f'docker_apt_repo "{_os_release(tmp_path, body)}"')

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_an_unsupported_distro_aborts_with_a_clear_message(tmp_path: Path) -> None:
    os_release = _os_release(tmp_path, "ID=fedora\nVERSION_ID=41\n")
    result = _run(tmp_path, f'docker_apt_repo "{os_release}"')

    assert result.returncode != 0
    assert "fedora" in result.stderr
    assert "Debian or Ubuntu" in result.stderr


def test_missing_node_is_installed_from_nodesource() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "deb.nodesource.com" in text
    assert "apt-get install -y nodejs npm" not in text
