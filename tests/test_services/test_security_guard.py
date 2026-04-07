"""Tests for the Rust-backed security guard client."""

from __future__ import annotations

from unittest.mock import patch

import grpc
import pytest

from koda.internal_rpc.security_guard import SecurityGuardClient


class _FakeUnaryCallable:
    def __call__(self, request, timeout=None, metadata=None):  # noqa: ANN001
        return None


class _FakeChannel:
    def unary_unary(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeUnaryCallable()

    def stream_unary(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeUnaryCallable()

    def unary_stream(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeUnaryCallable()

    def stream_stream(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeUnaryCallable()

    def close(self) -> None:
        return None


class _UnreadyFuture:
    def result(self, timeout=None):  # noqa: ANN001
        raise grpc.FutureTimeoutError()


def test_security_guard_client_fails_closed_without_external_service():
    with (
        patch("grpc.insecure_channel", return_value=_FakeChannel()),
        patch("grpc.channel_ready_future", return_value=_UnreadyFuture()),
    ):
        client = SecurityGuardClient()

        with pytest.raises(RuntimeError, match="security_guard_service_unavailable"):
            client.validate_shell_command("echo hi")


class TestValidateRuntimePathFailsClosed:
    """validate_runtime_path must fail closed when service is unavailable."""

    def test_fails_closed_channel_unavailable(self):
        with (
            patch("grpc.insecure_channel", return_value=_FakeChannel()),
            patch("grpc.channel_ready_future", return_value=_UnreadyFuture()),
        ):
            client = SecurityGuardClient()
            with pytest.raises(RuntimeError, match="security_guard_service_unavailable"):
                client.validate_runtime_path("/some/path")

    def test_fails_closed_with_allow_empty(self):
        with (
            patch("grpc.insecure_channel", return_value=_FakeChannel()),
            patch("grpc.channel_ready_future", return_value=_UnreadyFuture()),
        ):
            client = SecurityGuardClient()
            with pytest.raises(RuntimeError, match="security_guard_service_unavailable"):
                client.validate_runtime_path("", allow_empty=True)


class TestValidateFilePolicyFailsClosed:
    """validate_file_policy must fail closed when service is unavailable."""

    def test_fails_closed_channel_unavailable(self):
        with (
            patch("grpc.insecure_channel", return_value=_FakeChannel()),
            patch("grpc.channel_ready_future", return_value=_UnreadyFuture()),
        ):
            client = SecurityGuardClient()
            with pytest.raises(RuntimeError, match="security_guard_service_unavailable"):
                client.validate_file_policy(path="/etc/passwd")

    def test_fails_closed_require_file_false(self):
        with (
            patch("grpc.insecure_channel", return_value=_FakeChannel()),
            patch("grpc.channel_ready_future", return_value=_UnreadyFuture()),
        ):
            client = SecurityGuardClient()
            with pytest.raises(RuntimeError, match="security_guard_service_unavailable"):
                client.validate_file_policy(path="/tmp/test", require_file=False)


class TestRedactValueFailsClosed:
    """redact_value must fail closed when service is unavailable."""

    def test_fails_closed_channel_unavailable(self):
        with (
            patch("grpc.insecure_channel", return_value=_FakeChannel()),
            patch("grpc.channel_ready_future", return_value=_UnreadyFuture()),
        ):
            client = SecurityGuardClient()
            with pytest.raises(RuntimeError, match="security_guard_service_unavailable"):
                client.redact_value("secret_value", key_hint="password")

    def test_fails_closed_without_key_hint(self):
        with (
            patch("grpc.insecure_channel", return_value=_FakeChannel()),
            patch("grpc.channel_ready_future", return_value=_UnreadyFuture()),
        ):
            client = SecurityGuardClient()
            with pytest.raises(RuntimeError, match="security_guard_service_unavailable"):
                client.redact_value({"nested": "data"})


class TestValidateObjectKeyFailsClosed:
    """validate_object_key must fail closed when service is unavailable."""

    def test_fails_closed_channel_unavailable(self):
        with (
            patch("grpc.insecure_channel", return_value=_FakeChannel()),
            patch("grpc.channel_ready_future", return_value=_UnreadyFuture()),
        ):
            client = SecurityGuardClient()
            with pytest.raises(RuntimeError, match="security_guard_service_unavailable"):
                client.validate_object_key(agent_id="agent1", object_key="files/test.txt")


class TestTimeoutBehavior:
    """gRPC deadline exceeded must raise, not silently pass."""

    def test_channel_not_set_raises(self):
        """If _channel is None, _ensure_channel_ready raises RuntimeError."""
        client = SecurityGuardClient()
        # _channel is None by default, so _ensure_channel_ready should raise
        with pytest.raises(RuntimeError, match="security_guard_channel_unavailable"):
            client._ensure_channel_ready()

    def test_future_timeout_raises_service_unavailable(self):
        """FutureTimeoutError in channel readiness must raise service unavailable."""
        with (
            patch("grpc.insecure_channel", return_value=_FakeChannel()),
            patch("grpc.channel_ready_future", return_value=_UnreadyFuture()),
        ):
            client = SecurityGuardClient()
            with pytest.raises(RuntimeError, match="security_guard_service_unavailable"):
                client.sanitize_environment(
                    base_env={"PATH": "/usr/bin"},
                    allowed_provider_keys=["OPENAI_API_KEY"],
                    env_overrides={},
                )
