"""Artifact-engine client selection for the Rust migration seam."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Protocol

from koda import config
from koda.internal_rpc.common import (
    EngineSelection,
    ensure_generated_proto_path,
    normalize_internal_service_probe,
    resolve_grpc_target,
)
from koda.internal_rpc.metadata import build_rpc_metadata


class ArtifactEngineClient(Protocol):
    """Behavior expected from the artifact-engine adapter."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def put_artifact(
        self,
        *,
        path: str,
        logical_filename: str | None = None,
        object_key: str = "",
        mime_type: str = "",
        source_metadata_json: str = "",
        purpose: str = "",
    ) -> dict[str, object]: ...

    async def generate_evidence_by_artifact_id(self, *, artifact_id: str) -> dict[str, object]: ...

    async def get_artifact_metadata_by_artifact_id(self, *, artifact_id: str) -> dict[str, object]: ...

    def health(self) -> dict[str, object]: ...


class GrpcArtifactEngineClient:
    """Future Rust artifact client over internal gRPC."""

    def __init__(self, *, selection: EngineSelection) -> None:
        self.selection = selection
        self._target, self._transport = resolve_grpc_target(config.ARTIFACT_GRPC_TARGET)
        self._channel: Any | None = None
        self._stub: Any | None = None
        self._metadata_pb2: Any | None = None
        self._artifact_pb2: Any | None = None
        self._startup_error: str | None = None
        self._last_health: dict[str, object] = {
            "service": "artifact",
            "mode": self.selection.mode,
            "implementation": "grpc-artifact-engine-client",
            "transport": self._transport,
            "configured_target": self._target,
            "deadline_ms": config.INTERNAL_RPC_DEADLINE_MS,
            "connected": False,
            "verified": False,
            "ready": False,
            "startup_error": None,
            "selection_reason": self.selection.reason,
            "agent_id": self.selection.agent_id,
        }

    def _rpc_metadata(self) -> tuple[tuple[str, str], ...]:
        extra = {
            "x-internal-rpc-mode": self.selection.mode,
            "x-engine-selection-reason": self.selection.reason,
        }
        return build_rpc_metadata(
            agent_id=self.selection.agent_id,
            extra=extra,
        )

    def _request_metadata(self) -> Any | None:
        if self._metadata_pb2 is None:
            return None
        request_metadata_type = getattr(self._metadata_pb2, "RequestMetadata", None)
        if request_metadata_type is None:
            return None
        return request_metadata_type(
            agent_id=self.selection.agent_id or "",
            labels={
                "engine_selection_reason": self.selection.reason,
                "internal_rpc_mode": self.selection.mode,
            },
        )

    def _build_request(self, factory: Any, /, **kwargs: object) -> Any:
        request_metadata = self._request_metadata()
        if request_metadata is not None:
            try:
                return factory(metadata=request_metadata, **kwargs)
            except TypeError:
                pass
        return factory(**kwargs)

    async def _probe_health(self) -> None:
        if self._stub is None or self._metadata_pb2 is None:
            return
        response = await self._stub.Health(
            self._metadata_pb2.HealthRequest(),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        self._last_health = normalize_internal_service_probe(
            base_health=self._last_health,
            service=response.service,
            ready=bool(response.ready),
            status=response.status,
            details=dict(response.details),
        )

    async def start(self) -> None:
        try:
            import grpc.aio as grpc_aio

            ensure_generated_proto_path()
            from artifact.v1 import artifact_pb2, artifact_pb2_grpc
            from common.v1 import metadata_pb2
        except Exception as exc:  # pragma: no cover - import failure depends on environment
            self._startup_error = f"{type(exc).__name__}: {exc}"
            self._last_health = {
                **self._last_health,
                "startup_error": self._startup_error,
                "ready": False,
            }
            raise RuntimeError("grpc_artifact_engine_client_requires_grpcio") from exc
        self._channel = grpc_aio.insecure_channel(self._target)
        self._metadata_pb2 = metadata_pb2
        self._artifact_pb2 = artifact_pb2
        self._stub = artifact_pb2_grpc.ArtifactEngineServiceStub(self._channel)
        await self._probe_health()

    async def stop(self) -> None:
        if self._channel is None:
            return
        channel = self._channel
        self._channel = None
        self._stub = None
        await channel.close()

    async def put_artifact(
        self,
        *,
        path: str,
        logical_filename: str | None = None,
        object_key: str = "",
        mime_type: str = "",
        source_metadata_json: str = "",
        purpose: str = "",
    ) -> dict[str, object]:
        if self._stub is None or self._artifact_pb2 is None:
            raise RuntimeError("grpc_artifact_engine_unavailable")
        artifact_pb2 = self._artifact_pb2
        assert artifact_pb2 is not None
        path_obj = Path(path)
        logical_filename = (logical_filename or path_obj.name or "artifact").strip() or "artifact"
        source_metadata_json = source_metadata_json or ""
        chunk_size = 256 * 1024
        request_metadata = self._request_metadata()

        async def _requests() -> Any:
            with path_obj.open("rb") as handle:
                first_chunk = True
                while True:
                    chunk_metadata: Any = request_metadata
                    request_kwargs = {
                        "agent_id": self.selection.agent_id or "",
                        "logical_filename": logical_filename if first_chunk else "",
                        "object_key": object_key if first_chunk else "",
                        "mime_type": mime_type if first_chunk else "",
                        "source_metadata_json": source_metadata_json if first_chunk else "",
                        "purpose": purpose if first_chunk else "",
                    }
                    if chunk_metadata is not None:
                        request_kwargs["metadata"] = chunk_metadata
                    chunk = await asyncio.to_thread(handle.read, chunk_size)
                    if not chunk:
                        if first_chunk:
                            yield artifact_pb2.PutArtifactRequest(**request_kwargs, data=b"")
                        break
                    yield artifact_pb2.PutArtifactRequest(**request_kwargs, data=chunk)
                    first_chunk = False

        response = await self._stub.PutArtifact(
            _requests(),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        artifact = response.artifact
        return {
            "artifact_id": str(getattr(artifact, "artifact_id", "") or ""),
            "object_key": str(getattr(artifact, "object_key", "") or ""),
            "content_hash": str(getattr(artifact, "content_hash", "") or ""),
            "mime_type": str(getattr(artifact, "mime_type", "") or ""),
            "metadata_json": str(getattr(response, "metadata_json", "") or ""),
            "upload_outcome": str(getattr(response, "upload_outcome", "") or ""),
        }

    async def generate_evidence_by_artifact_id(self, *, artifact_id: str) -> dict[str, object]:
        if self._stub is None or self._artifact_pb2 is None:
            raise RuntimeError("grpc_artifact_engine_unavailable")
        response = await self._stub.GenerateEvidenceByArtifactId(
            self._build_request(
                self._artifact_pb2.GenerateEvidenceByArtifactIdRequest,
                agent_id=self.selection.agent_id or "",
                artifact_id=artifact_id,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        return {"evidence_json": str(getattr(response, "evidence_json", "") or "")}

    async def get_artifact_metadata_by_artifact_id(self, *, artifact_id: str) -> dict[str, object]:
        if self._stub is None or self._artifact_pb2 is None:
            raise RuntimeError("grpc_artifact_engine_unavailable")
        response = await self._stub.GetArtifactMetadataByArtifactId(
            self._build_request(
                self._artifact_pb2.GetArtifactMetadataByArtifactIdRequest,
                agent_id=self.selection.agent_id or "",
                artifact_id=artifact_id,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        artifact = response.artifact
        return {
            "artifact_id": str(getattr(artifact, "artifact_id", "") or ""),
            "object_key": str(getattr(artifact, "object_key", "") or ""),
            "content_hash": str(getattr(artifact, "content_hash", "") or ""),
            "mime_type": str(getattr(artifact, "mime_type", "") or ""),
            "metadata_json": str(getattr(response, "metadata_json", "") or ""),
        }

    def health(self) -> dict[str, object]:
        connected = self._channel is not None
        return {
            **self._last_health,
            "connected": connected,
            "ready": bool(self._last_health.get("ready")) and connected and self._startup_error is None,
            "production_ready": bool(self._last_health.get("production_ready"))
            and connected
            and self._startup_error is None,
            "cutover_allowed": bool(self._last_health.get("cutover_allowed"))
            and connected
            and self._startup_error is None,
            "startup_error": self._startup_error,
        }


def build_artifact_engine_client(*, agent_id: str | None = None) -> ArtifactEngineClient:
    """Build the Rust artifact-engine client."""

    normalized_agent_id = str(agent_id or "").strip().lower() or None
    selection = EngineSelection(
        backend="grpc",
        reason="rust-default",
        mode="rust",
        agent_id=normalized_agent_id,
    )
    return GrpcArtifactEngineClient(selection=selection)
