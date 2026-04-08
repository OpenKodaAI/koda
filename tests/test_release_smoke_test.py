from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import scripts.release_smoke_test as release_smoke_test


def test_run_smoke_creates_output_root_before_tempdir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    manifest_path = root / "packages" / "cli" / "release" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "images": {
                    "app": "ghcr.io/openkodaai/koda-app:test",
                    "web": "ghcr.io/openkodaai/koda-web:test",
                    "memory": "ghcr.io/openkodaai/koda-memory:test",
                    "security": "ghcr.io/openkodaai/koda-security:test",
                }
            }
        ),
        encoding="utf-8",
    )

    cli_tarball = tmp_path / "koda-cli.tgz"
    cli_tarball.write_text("placeholder", encoding="utf-8")
    install_dir = tmp_path / "install"
    fake_bin = tmp_path / "npm-prefix" / "bin" / "koda"
    fake_bin.parent.mkdir(parents=True, exist_ok=True)
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)

    commands: list[list[str]] = []

    monkeypatch.setattr(release_smoke_test, "ROOT", root)
    monkeypatch.setattr(release_smoke_test, "install_cli", lambda *_args, **_kwargs: fake_bin)

    def fake_run(
        cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(release_smoke_test, "run", fake_run)

    release_smoke_test.run_smoke(cli_tarball, install_dir, build_images=False)

    assert (root / "output").exists()
    assert any(len(command) > 1 and command[1] == "install" for command in commands)


def test_run_surfaces_stdout_and_stderr_on_failure(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        release_smoke_test.run(
            ["python3", "-c", "import sys; print('hello'); print('boom', file=sys.stderr); raise SystemExit(7)"],
            cwd=tmp_path,
        )

    message = str(excinfo.value)
    assert "Command failed with exit code 7" in message
    assert "stdout:" in message
    assert "hello" in message
    assert "stderr:" in message
    assert "boom" in message
