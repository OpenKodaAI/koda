"""`koda uninstall` keeps data volumes unless --purge is passed.

Drives the real CLI (packages/cli/bin/koda.mjs) against a fake ``docker``
executable that records its arguments, so no Docker daemon is needed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "packages" / "cli" / "bin" / "koda.mjs"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required to run the Koda CLI")


@pytest.fixture
def fake_docker(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker-calls.log"
    script = bin_dir / "docker"
    script.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit 0\n', encoding="utf-8")
    script.chmod(0o755)
    return log


def _install_dir(tmp_path: Path) -> Path:
    install_dir = tmp_path / "koda-install"
    (install_dir / "bundle").mkdir(parents=True)
    (install_dir / "bundle" / "docker-compose.release.yml").write_text("services: {}\n", encoding="utf-8")
    (install_dir / ".env").write_text("POSTGRES_PASSWORD=keep-me\n", encoding="utf-8")
    return install_dir


def _run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"}
    return subprocess.run(
        ["node", str(CLI), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _compose_down_calls(log: Path) -> list[list[str]]:
    calls = [line.split() for line in log.read_text(encoding="utf-8").splitlines()]
    return [call for call in calls if "compose" in call and "down" in call]


def test_uninstall_without_purge_keeps_volumes_and_env(tmp_path: Path, fake_docker: Path) -> None:
    install_dir = _install_dir(tmp_path)

    result = _run_cli(tmp_path, "uninstall", "--dir", str(install_dir))

    assert result.returncode == 0, result.stderr
    downs = _compose_down_calls(fake_docker)
    assert len(downs) == 1
    assert "-v" not in downs[0] and "--volumes" not in downs[0]
    assert "--remove-orphans" in downs[0]
    assert (install_dir / ".env").read_text(encoding="utf-8") == "POSTGRES_PASSWORD=keep-me\n"
    assert "koda up" in result.stdout


def test_uninstall_with_purge_removes_volumes_and_install_dir(tmp_path: Path, fake_docker: Path) -> None:
    install_dir = _install_dir(tmp_path)

    result = _run_cli(tmp_path, "uninstall", "--dir", str(install_dir), "--purge")

    assert result.returncode == 0, result.stderr
    downs = _compose_down_calls(fake_docker)
    assert len(downs) == 1
    assert "-v" in downs[0]
    assert not install_dir.exists()


def test_purge_refuses_to_delete_a_directory_that_is_not_a_koda_install(tmp_path: Path, fake_docker: Path) -> None:
    unrelated = tmp_path / "home-like-dir"
    unrelated.mkdir()
    (unrelated / "precious.txt").write_text("do not delete", encoding="utf-8")

    result = _run_cli(tmp_path, "uninstall", "--dir", str(unrelated), "--purge")

    assert result.returncode == 0, result.stderr
    assert (unrelated / "precious.txt").read_text(encoding="utf-8") == "do not delete"
    assert "No Koda install found" in result.stdout
    assert not fake_docker.exists() or not _compose_down_calls(fake_docker)
