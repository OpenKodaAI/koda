"""Security-guard client for the Rust security service."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from koda import config
from koda.internal_rpc.common import create_grpc_channel, ensure_generated_proto_path, resolve_grpc_target
from koda.internal_rpc.metadata import build_rpc_metadata


class SecurityGuardClient:
    """Sync gRPC client for low-level security guards."""

    def __init__(self) -> None:
        self._target, self._transport = resolve_grpc_target(config.SECURITY_GRPC_TARGET)
        self._channel: Any | None = None
        self._stub: Any | None = None
        self._metadata_pb2: Any | None = None
        self._security_pb2: Any | None = None

    def _ensure_channel_ready(self) -> None:
        import grpc

        if self._channel is None:
            raise RuntimeError("security_guard_channel_unavailable")
        try:
            grpc.channel_ready_future(self._channel).result(timeout=0.5)
        except grpc.FutureTimeoutError:
            raise RuntimeError("security_guard_service_unavailable") from None

    def _ensure_started(self) -> None:
        if self._stub is not None:
            return

        ensure_generated_proto_path()
        from common.v1 import metadata_pb2
        from security.v1 import security_pb2, security_pb2_grpc

        self._channel = create_grpc_channel(self._target)
        self._metadata_pb2 = metadata_pb2
        self._security_pb2 = security_pb2
        self._stub = security_pb2_grpc.SecurityGuardServiceStub(self._channel)
        self._ensure_channel_ready()

    def _rpc_metadata(self) -> tuple[tuple[str, str], ...]:
        return build_rpc_metadata(extra={"x-internal-rpc-mode": config.INTERNAL_RPC_MODE})

    def _request_metadata(self) -> Any | None:
        if self._metadata_pb2 is None:
            return None
        request_metadata_type = getattr(self._metadata_pb2, "RequestMetadata", None)
        if request_metadata_type is None:
            return None
        return request_metadata_type(labels={"internal_rpc_mode": config.INTERNAL_RPC_MODE})

    def _rpc_client(self) -> tuple[Any, Any]:
        assert self._stub is not None
        assert self._security_pb2 is not None
        return self._stub, self._security_pb2

    def _build_request(self, factory: Any, /, **kwargs: object) -> Any:
        request_metadata = self._request_metadata()
        if request_metadata is not None:
            try:
                return factory(metadata=request_metadata, **kwargs)
            except TypeError:
                pass
        return factory(**kwargs)

    def validate_shell_command(self, command: str) -> str:
        self._ensure_started()
        stub, security_pb2 = self._rpc_client()
        response = stub.ValidateShellCommand(
            self._build_request(security_pb2.ValidateShellCommandRequest, command=command),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        return str(response.command)

    def sanitize_environment(
        self,
        *,
        base_env: Mapping[str, str],
        allowed_provider_keys: list[str],
        env_overrides: Mapping[str, str],
    ) -> dict[str, str]:
        self._ensure_started()
        stub, security_pb2 = self._rpc_client()
        response = stub.SanitizeEnvironment(
            self._build_request(
                security_pb2.SanitizeEnvironmentRequest,
                base_env={str(key): str(value) for key, value in base_env.items()},
                allowed_provider_keys=[str(item) for item in allowed_provider_keys],
                env_overrides={str(key): str(value) for key, value in env_overrides.items()},
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        return {str(key): str(value) for key, value in dict(response.env).items()}

    def validate_runtime_path(self, value: str, *, allow_empty: bool = False) -> str:
        self._ensure_started()
        stub, security_pb2 = self._rpc_client()
        response = stub.ValidateRuntimePath(
            self._build_request(
                security_pb2.ValidateRuntimePathRequest,
                value=value,
                allow_empty=allow_empty,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        return str(response.value)

    def validate_object_key(self, *, agent_id: str, object_key: str) -> str:
        self._ensure_started()
        stub, security_pb2 = self._rpc_client()
        response = stub.ValidateObjectKey(
            self._build_request(
                security_pb2.ValidateObjectKeyRequest,
                agent_id=agent_id,
                object_key=object_key,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        return str(response.object_key)

    def redact_value(self, value: Any, *, key_hint: str | None = None) -> Any:
        self._ensure_started()
        stub, security_pb2 = self._rpc_client()
        response = stub.RedactValue(
            self._build_request(
                security_pb2.RedactValueRequest,
                value_json=json.dumps(value, ensure_ascii=False, default=str),
                key_hint=key_hint or "",
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        return json.loads(str(response.value_json or "null") or "null")

    def validate_file_policy(self, *, path: str, require_file: bool = True) -> str:
        self._ensure_started()
        stub, security_pb2 = self._rpc_client()
        response = stub.ValidateFilePolicy(
            self._build_request(
                security_pb2.ValidateFilePolicyRequest,
                path=path,
                require_file=require_file,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        return str(response.canonical_path)


_SECURITY_GUARD_CLIENT: SecurityGuardClient | None = None


def get_security_guard_client() -> SecurityGuardClient:
    global _SECURITY_GUARD_CLIENT
    if _SECURITY_GUARD_CLIENT is None:
        _SECURITY_GUARD_CLIENT = SecurityGuardClient()
    return _SECURITY_GUARD_CLIENT
