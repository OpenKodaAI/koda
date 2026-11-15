"""``GRPC_TLS_ENABLED`` is gone (M1-E6-T2, D-139).

The switch moved every Python gRPC channel to TLS while only the security and
memory sidecars could serve it, so it broke the runtime-kernel, artifact,
retrieval, policy and bot-gateway connections. Setting it now stops the process
at startup with guidance, and no channel takes a TLS path.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from koda import config
from koda.internal_rpc import common

ROOT = Path(__file__).resolve().parents[1]


def _import_config(**env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "import koda.config"],
        cwd=ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize("value", ["true", "TRUE", " True "])
def test_grpc_tls_enabled_is_refused_at_startup_with_guidance(value: str) -> None:
    result = _import_config(GRPC_TLS_ENABLED=value)

    assert result.returncode != 0
    assert "GRPC_TLS_ENABLED is no longer supported" in result.stderr
    assert "docs/operations/hardening.md" in result.stderr


def test_grpc_tls_disabled_still_starts() -> None:
    assert _import_config(GRPC_TLS_ENABLED="false").returncode == 0


def test_no_channel_takes_a_tls_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # Even with the old flag forced on, every target gets a plaintext channel.
    monkeypatch.setattr(config, "GRPC_TLS_ENABLED", True, raising=False)
    targets = ("memory:50063", "unix:///tmp/koda-test.sock", "ipv4:127.0.0.1:50063,127.0.0.2:50063")
    with (
        patch("grpc.secure_channel") as secure,
        patch("grpc.aio.secure_channel") as secure_aio,
        patch("grpc.insecure_channel") as insecure,
        patch("grpc.aio.insecure_channel") as insecure_aio,
    ):
        for target in targets:
            common.create_grpc_channel(target)
            common.create_grpc_channel(target, async_channel=True)

    secure.assert_not_called()
    secure_aio.assert_not_called()
    assert [call.args[0] for call in insecure.call_args_list] == list(targets)
    assert [call.args[0] for call in insecure_aio.call_args_list] == list(targets)


def test_rust_workspace_does_not_compile_tonic_tls() -> None:
    # No sidecar terminates gRPC TLS any more, so tonic's rustls server stack
    # must not be compiled in, by the workspace or by any crate.
    rust = ROOT / "rust"
    workspace = tomllib.loads((rust / "Cargo.toml").read_text())
    tonic_specs = [workspace["workspace"]["dependencies"]["tonic"]]
    for manifest in sorted(rust.glob("*/Cargo.toml")):
        crate = tomllib.loads(manifest.read_text())
        for table in ("dependencies", "dev-dependencies", "build-dependencies"):
            spec = crate.get(table, {}).get("tonic")
            if isinstance(spec, dict):
                tonic_specs.append(spec)

    assert len(tonic_specs) > 1
    for spec in tonic_specs:
        assert "tls" not in spec.get("features", [])
