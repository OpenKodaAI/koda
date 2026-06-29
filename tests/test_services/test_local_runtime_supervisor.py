"""Tests for the local runtime supervisor (auto-spawn opt-in)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import koda.services.local_runtime_supervisor as supervisor_module
from koda.services.local_runtime_supervisor import (
    LocalRuntimeSupervisor,
    _parse_port,
    get_local_runtime_supervisor,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_for_tests()
    yield
    reset_for_tests()


class TestPortParsing:
    def test_parses_port_from_url(self):
        assert _parse_port("http://127.0.0.1:8080", default=80) == 8080

    def test_returns_default_when_no_port(self):
        assert _parse_port("http://localhost", default=8000) == 8000

    def test_returns_default_when_invalid_url(self):
        assert _parse_port("not-a-url", default=8080) == 8080

    def test_returns_default_when_port_is_garbage(self):
        assert _parse_port("http://host:abc", default=8080) == 8080


class TestSingleton:
    def test_returns_same_instance(self):
        a = get_local_runtime_supervisor()
        b = get_local_runtime_supervisor()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = get_local_runtime_supervisor()
        reset_for_tests()
        b = get_local_runtime_supervisor()
        assert a is not b


class TestEnsureRunning:
    @pytest.mark.asyncio
    async def test_skip_when_no_model_configured(self, monkeypatch):
        # No default model → no-op, just returns the configured base URL.
        monkeypatch.setattr(supervisor_module, "LLAMACPP_DEFAULT_MODEL", "")
        sup = LocalRuntimeSupervisor()
        url = await sup.ensure_running("llamacpp")
        assert url.startswith("http://")
        assert sup.status() == {}

    @pytest.mark.asyncio
    async def test_returns_url_when_binary_missing(self, monkeypatch):
        monkeypatch.setattr(supervisor_module, "LLAMACPP_DEFAULT_MODEL", "qwen2.5-7b")
        with patch("koda.services.local_runtime_supervisor.shutil.which", return_value=None):
            sup = LocalRuntimeSupervisor()
            url = await sup.ensure_running("llamacpp")
        assert url.startswith("http://")
        # Process not spawned → status remains empty.
        assert sup.status() == {}

    @pytest.mark.asyncio
    async def test_spawn_path_with_mocked_subprocess(self, monkeypatch):
        monkeypatch.setattr(supervisor_module, "LLAMACPP_DEFAULT_MODEL", "qwen2.5-7b.gguf")
        fake_process = MagicMock()
        fake_process.pid = 99999
        fake_process.poll.return_value = None  # still running
        with (
            patch("koda.services.local_runtime_supervisor.shutil.which", return_value="/usr/bin/llama-server"),
            patch("koda.services.local_runtime_supervisor.subprocess.Popen", return_value=fake_process) as popen,
            patch("koda.services.local_runtime_supervisor._wait_for_health", return_value=True),
            patch.object(LocalRuntimeSupervisor, "_warmup", return_value=None),
        ):
            sup = LocalRuntimeSupervisor()
            url = await sup.ensure_running("llamacpp")
        assert url.startswith("http://")
        popen.assert_called_once()
        status = sup.status()
        assert "llamacpp" in status
        assert status["llamacpp"]["health"] == "ready"
        assert status["llamacpp"]["model"] == "qwen2.5-7b.gguf"
        assert status["llamacpp"]["pid"] == 99999

    @pytest.mark.asyncio
    async def test_health_failure_marks_failed(self, monkeypatch):
        monkeypatch.setattr(supervisor_module, "LLAMACPP_DEFAULT_MODEL", "qwen2.5-7b.gguf")
        fake_process = MagicMock()
        fake_process.pid = 99999
        fake_process.poll.return_value = None
        with (
            patch("koda.services.local_runtime_supervisor.shutil.which", return_value="/usr/bin/llama-server"),
            patch("koda.services.local_runtime_supervisor.subprocess.Popen", return_value=fake_process),
            patch("koda.services.local_runtime_supervisor._wait_for_health", return_value=False),
        ):
            sup = LocalRuntimeSupervisor()
            await sup.ensure_running("llamacpp")
        status = sup.status()
        assert status["llamacpp"]["health"] == "failed"
        assert status["llamacpp"]["failure_reason"]


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_with_no_running_process_is_noop(self):
        sup = LocalRuntimeSupervisor()
        # Should not raise.
        await sup.stop("llamacpp")
        await sup.stop_all()

    @pytest.mark.asyncio
    async def test_status_is_empty_initially(self):
        sup = LocalRuntimeSupervisor()
        assert sup.status() == {}
