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
