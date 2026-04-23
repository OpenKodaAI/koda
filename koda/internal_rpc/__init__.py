"""Internal RPC adapters for Rust-backed runtime services."""

from koda.internal_rpc.artifact_engine import (
    ArtifactEngineClient,
    GrpcArtifactEngineClient,
    build_artifact_engine_client,
)
from koda.internal_rpc.common import (
    normalize_agent_scope,
    resolve_grpc_target,
)
from koda.internal_rpc.memory_engine import (
    GrpcMemoryEngineClient,
    MemoryEngineClient,
    build_memory_engine_client,
)
from koda.internal_rpc.metadata import build_rpc_metadata
from koda.internal_rpc.retrieval_engine import (
    GrpcRetrievalEngineClient,
    RetrievalEngineClient,
    build_retrieval_engine_client,
)
from koda.internal_rpc.runtime_kernel import (
    GrpcRuntimeKernelClient,
    RuntimeKernelClient,
    build_runtime_kernel_client,
)
from koda.internal_rpc.security_guard import (
    SecurityGuardClient,
    get_security_guard_client,
)

__all__ = [
    "ArtifactEngineClient",
    "GrpcRuntimeKernelClient",
    "GrpcArtifactEngineClient",
    "GrpcMemoryEngineClient",
    "GrpcRetrievalEngineClient",
    "MemoryEngineClient",
    "RetrievalEngineClient",
    "RuntimeKernelClient",
    "SecurityGuardClient",
    "build_rpc_metadata",
    "build_artifact_engine_client",
    "build_memory_engine_client",
    "build_retrieval_engine_client",
    "build_runtime_kernel_client",
    "get_security_guard_client",
    "normalize_agent_scope",
    "resolve_grpc_target",
]
