import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from koda import config
from koda.internal_rpc.artifact_engine import GrpcArtifactEngineClient, build_artifact_engine_client
from koda.internal_rpc.common import EngineSelection, resolve_grpc_target
from koda.internal_rpc.memory_engine import GrpcMemoryEngineClient, build_memory_engine_client
from koda.internal_rpc.retrieval_engine import GrpcRetrievalEngineClient, build_retrieval_engine_client
from koda.internal_rpc.runtime_kernel import GrpcRuntimeKernelClient, build_runtime_kernel_client
from koda.knowledge.types import QueryEnvelope, RetrievalStrategy


class _DummyStore:
    pass


def test_resolve_grpc_target_uses_uds_for_absolute_paths() -> None:
    target, transport = resolve_grpc_target("/tmp/koda/runtime-kernel.sock")

    assert transport == "grpc-uds"
    assert target == "unix:///tmp/koda/runtime-kernel.sock"


def test_resolve_grpc_target_preserves_explicit_unix_scheme() -> None:
    target, transport = resolve_grpc_target("unix:///tmp/koda/runtime-kernel.sock")

    assert transport == "grpc-uds"
    assert target == "unix:///tmp/koda/runtime-kernel.sock"


def test_build_runtime_kernel_client_uses_grpc_in_rust_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(config, "INTERNAL_RPC_MODE", "rust")
    monkeypatch.setattr(config, "AGENT_ID", "AGENT_A")
    monkeypatch.setattr(config, "RUNTIME_KERNEL_SOCKET", str(tmp_path / "rpc" / "runtime-kernel.sock"))

    client = build_runtime_kernel_client(runtime_root=tmp_path, store=_DummyStore())

    assert isinstance(client, GrpcRuntimeKernelClient)
    health = client.health()
    assert health["transport"] == "grpc-uds"
    assert str(health["configured_target"]).startswith("unix://")


def test_grpc_runtime_kernel_health_defaults_ready_rust_probe_to_authoritative(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(config, "INTERNAL_RPC_MODE", "rust")
    monkeypatch.setattr(config, "RUNTIME_KERNEL_SOCKET", str(tmp_path / "rpc" / "runtime-kernel.sock"))

    client = GrpcRuntimeKernelClient(runtime_root=tmp_path, store=_DummyStore(), mode="rust")
    client._channel = object()
    client._last_health = {
        "mode": "rust",
        "transport": "grpc-uds",
        "ready": True,
        "status": "running",
        "details": {},
    }

    health = client.health()

    assert health["remote"] is True
    assert health["ready"] is True
    assert health["authoritative"] is True
    assert health["production_ready"] is True
    assert health["cutover_allowed"] is True
    assert health["authority_scope"] == "full_runtime"


def test_build_runtime_kernel_client_rejects_unknown_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(config, "INTERNAL_RPC_MODE", "unknown")
    monkeypatch.setattr(config, "AGENT_ID", "AGENT_A")
    monkeypatch.setattr(config, "RUNTIME_KERNEL_SOCKET", str(tmp_path / "rpc" / "runtime-kernel.sock"))

    client = build_runtime_kernel_client(runtime_root=tmp_path, store=_DummyStore())

    assert isinstance(client, GrpcRuntimeKernelClient)
    assert client.health()["selection_reason"] == "rust-default"


def test_build_memory_engine_client_uses_grpc_in_rust_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "INTERNAL_RPC_MODE", "rust")
    monkeypatch.setattr(config, "MEMORY_GRPC_TARGET", "/tmp/koda/memory.sock")

    client = build_memory_engine_client(agent_id="AGENT_A")

    assert isinstance(client, GrpcMemoryEngineClient)
    health = client.health()
    assert health["selection_reason"] == "rust-default"
    assert health["transport"] == "grpc-uds"
    assert health["configured_target"] == "unix:///tmp/koda/memory.sock"


def test_build_artifact_engine_client_uses_grpc_in_rust_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "INTERNAL_RPC_MODE", "rust")
    monkeypatch.setattr(config, "ARTIFACT_GRPC_TARGET", "127.0.0.1:50064")

    client = build_artifact_engine_client(agent_id="AGENT_A")

    assert isinstance(client, GrpcArtifactEngineClient)
    health = client.health()
    assert health["selection_reason"] == "rust-default"
    assert health["configured_target"] == "127.0.0.1:50064"


def test_build_retrieval_engine_client_uses_grpc_in_rust_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "INTERNAL_RPC_MODE", "rust")
    monkeypatch.setattr(config, "RETRIEVAL_GRPC_TARGET", "/tmp/koda/retrieval.sock")

    client = build_retrieval_engine_client(agent_id="AGENT_A")

    assert isinstance(client, GrpcRetrievalEngineClient)
    health = client.health()
    assert health["selection_reason"] == "rust-default"
    assert health["transport"] == "grpc-uds"
    assert health["configured_target"] == "unix:///tmp/koda/retrieval.sock"


@pytest.mark.asyncio
async def test_grpc_retrieval_engine_client_probes_health_and_returns_remote_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import grpc

    class _FakeChannel:
        def close(self) -> None:
            return None

    class _HealthRequest:
        pass

    class _RequestMetadata:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class _RetrievalHit:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _AuthoritativeEvidence:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _AnswerPlan:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _JudgeResult:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _RetrieveEnvelope:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _RetrieveRequest:
        def __init__(
            self,
            *,
            metadata: object,
            agent_id: str,
            query: str,
            limit: int,
            envelope: object,
        ) -> None:
            self.metadata = metadata
            self.agent_id = agent_id
            self.query = query
            self.limit = limit
            self.envelope = envelope

    class _FakeStub:
        def __init__(self, channel: _FakeChannel) -> None:
            self.channel = channel

        def Health(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _HealthRequest)
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                service="koda-retrieval-engine",
                ready=True,
                status="ok",
                details={"transport": "test", "capabilities": "bundle-assembly,ranking"},
            )

        def Retrieve(self, request: _RetrieveRequest, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert request.query
            assert request.agent_id == "AGENT_A"
            assert request.limit == 2
            assert timeout > 0
            assert metadata
            assert isinstance(request.metadata, _RequestMetadata)
            assert request.envelope.normalized_query == "deploy"
            return SimpleNamespace(
                trace_id="trace-123",
                normalized_query="deploy",
                query_intent="operational_execution",
                route="operational",
                strategy="langgraph_current",
                selected_hits=[
                    _RetrievalHit(
                        id="policy-1",
                        title="Policy",
                        content="Deploy policy",
                        layer="canonical_policy",
                        scope="operational_policy",
                        source_label="policy:deploy",
                        source_path="/tmp/policy.md",
                        updated_at="2026-03-25T00:00:00",
                        freshness="fresh",
                        similarity=0.8,
                        source_type="document",
                        operable=True,
                        tags=[],
                        graph_relation_types=[],
                        evidence_modalities=[],
                        reasons=[],
                    ),
                    _RetrievalHit(
                        id="runbook-1",
                        title="Runbook",
                        content="Deploy runbook",
                        layer="approved_runbook",
                        scope="runbook",
                        source_label="runbook:deploy",
                        source_path="/tmp/runbook.md",
                        updated_at="2026-03-25T00:00:00",
                        freshness="fresh",
                        similarity=0.7,
                        source_type="document",
                        operable=True,
                        tags=[],
                        graph_relation_types=[],
                        evidence_modalities=[],
                        reasons=[],
                    ),
                ],
                candidate_hits=[],
                trace_hits=[],
                authoritative_evidence=[
                    _AuthoritativeEvidence(
                        source_label="policy:deploy",
                        layer="canonical_policy",
                        title="Policy",
                        excerpt="Deploy policy",
                        updated_at="2026-03-25T00:00:00",
                        freshness="fresh",
                        score=0.8,
                        operable=True,
                        rationale="",
                        evidence_modalities=[],
                    ),
                    _AuthoritativeEvidence(
                        source_label="runbook:deploy",
                        layer="approved_runbook",
                        title="Runbook",
                        excerpt="Deploy runbook",
                        updated_at="2026-03-25T00:00:00",
                        freshness="fresh",
                        score=0.7,
                        operable=True,
                        rationale="",
                        evidence_modalities=[],
                    ),
                ],
                supporting_evidence=[],
                linked_entities=[],
                graph_relations=[],
                subqueries=["deploy"],
                open_conflicts=[],
                uncertainty_notes=[],
                uncertainty_level="low",
                recommended_action_mode="execute",
                required_verifications=["policy:deploy", "runbook:deploy"],
                graph_hops=0,
                grounding_score=0.9,
                answer_plan=_AnswerPlan(
                    user_intent="operational_execution",
                    recommended_action_mode="execute",
                    authoritative_sources=["policy:deploy", "runbook:deploy"],
                    supporting_sources=[],
                    required_verifications=["policy:deploy", "runbook:deploy"],
                    open_conflicts=[],
                    uncertainty_level="low",
                ),
                judge_result=_JudgeResult(
                    status="passed",
                    reasons=[],
                    warnings=[],
                    citation_coverage=1.0,
                    citation_span_precision=0.9,
                    contradiction_escape_rate=0.0,
                    policy_compliance=1.0,
                    uncertainty_marked=False,
                    requires_review=False,
                    safe_response="",
                    metrics={},
                ),
                effective_engine="rust_grpc",
                fallback_used=False,
                explanation="remote bundle",
            )

    generated_common = ModuleType("common")
    generated_common_v1 = ModuleType("common.v1")
    generated_metadata_pb2 = ModuleType("common.v1.metadata_pb2")
    generated_metadata_pb2.HealthRequest = _HealthRequest
    generated_metadata_pb2.RequestMetadata = _RequestMetadata
    generated_retrieval = ModuleType("retrieval")
    generated_retrieval_v1 = ModuleType("retrieval.v1")
    generated_retrieval_pb2 = ModuleType("retrieval.v1.retrieval_pb2")
    generated_retrieval_pb2.RetrievalHit = _RetrievalHit
    generated_retrieval_pb2.AuthoritativeEvidence = _AuthoritativeEvidence
    generated_retrieval_pb2.AnswerPlan = _AnswerPlan
    generated_retrieval_pb2.JudgeResult = _JudgeResult
    generated_retrieval_pb2.RetrieveEnvelope = _RetrieveEnvelope
    generated_retrieval_pb2.RetrieveRequest = _RetrieveRequest
    generated_retrieval_pb2_grpc = ModuleType("retrieval.v1.retrieval_pb2_grpc")
    generated_retrieval_pb2_grpc.RetrievalEngineServiceStub = _FakeStub

    monkeypatch.setitem(sys.modules, "common", generated_common)
    monkeypatch.setitem(sys.modules, "common.v1", generated_common_v1)
    monkeypatch.setitem(sys.modules, "common.v1.metadata_pb2", generated_metadata_pb2)
    monkeypatch.setitem(sys.modules, "retrieval", generated_retrieval)
    monkeypatch.setitem(sys.modules, "retrieval.v1", generated_retrieval_v1)
    monkeypatch.setitem(sys.modules, "retrieval.v1.retrieval_pb2", generated_retrieval_pb2)
    monkeypatch.setitem(sys.modules, "retrieval.v1.retrieval_pb2_grpc", generated_retrieval_pb2_grpc)
    monkeypatch.setattr(grpc, "insecure_channel", lambda _target: _FakeChannel())

    client = GrpcRetrievalEngineClient(
        selection=EngineSelection(
            backend="grpc",
            reason="rust-default",
            mode="rust",
            agent_id="agent_a",
        )
    )

    await client.start()
    health = client.health()
    assert health["verified"] is True
    assert health["ready"] is True
    assert health["authoritative"] is True
    assert health["cutover_allowed"] is True
    assert health["service"] == "koda-retrieval-engine"

    envelope = QueryEnvelope(
        query="deploy",
        normalized_query="deploy",
        agent_id="AGENT_A",
        task_id=1,
        task_kind="deploy",
        strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        requires_write=True,
    )
    bundle = client.query(
        envelope=envelope,
        max_results=2,
    )

    assert [item.source_label for item in bundle.authoritative_evidence] == ["policy:deploy", "runbook:deploy"]
    assert "trace_id=trace-123" in bundle.explanation
    assert bundle.answer_plan is not None
    assert bundle.answer_plan.recommended_action_mode == "execute"
    assert bundle.judge_result is not None
    assert bundle.judge_result.status == "passed"
    assert bundle.effective_engine == "rust_grpc"
    assert bundle.fallback_used is False

    await client.stop()


@pytest.mark.asyncio
async def test_grpc_retrieval_engine_client_lists_graph_when_capability_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import grpc

    class _FakeChannel:
        def close(self) -> None:
            return None

    class _HealthRequest:
        pass

    class _RequestMetadata:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class _ListGraphRequest:
        def __init__(self, *, metadata: object, agent_id: str, entity_type: str, limit: int) -> None:
            self.metadata = metadata
            self.agent_id = agent_id
            self.entity_type = entity_type
            self.limit = limit

    class _FakeStub:
        def __init__(self, channel: _FakeChannel) -> None:
            self.channel = channel

        def Health(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _HealthRequest)
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                service="koda-retrieval-engine",
                ready=True,
                status="ready",
                details={"transport": "test", "capabilities": "bundle-assembly,graph_read"},
            )

        def ListGraph(self, request: _ListGraphRequest, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request.metadata, _RequestMetadata)
            assert request.agent_id == "agent_a"
            assert request.entity_type == "project"
            assert request.limit == 25
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                entities=[
                    SimpleNamespace(
                        entity_key="project:billing",
                        entity_type="project",
                        label="billing",
                        source_kind="knowledge",
                        metadata={"source_label": "policy:deploy"},
                        updated_at="2026-03-25T00:00:00+00:00",
                        graph_score=0.0,
                        graph_hops=0,
                        relation_types=[],
                    )
                ],
                relations=[
                    SimpleNamespace(
                        relation_key="observed_in:policy:billing",
                        relation_type="observed_in",
                        source_entity_key="entry:canonical_policy:deploy",
                        target_entity_key="project:billing",
                        weight=1.0,
                        metadata={},
                        updated_at="2026-03-25T00:00:00+00:00",
                    )
                ],
            )

    generated_common = ModuleType("common")
    generated_common_v1 = ModuleType("common.v1")
    generated_metadata_pb2 = ModuleType("common.v1.metadata_pb2")
    generated_metadata_pb2.HealthRequest = _HealthRequest
    generated_metadata_pb2.RequestMetadata = _RequestMetadata
    generated_retrieval = ModuleType("retrieval")
    generated_retrieval_v1 = ModuleType("retrieval.v1")
    generated_retrieval_pb2 = ModuleType("retrieval.v1.retrieval_pb2")
    generated_retrieval_pb2.ListGraphRequest = _ListGraphRequest
    generated_retrieval_pb2_grpc = ModuleType("retrieval.v1.retrieval_pb2_grpc")
    generated_retrieval_pb2_grpc.RetrievalEngineServiceStub = _FakeStub

    monkeypatch.setitem(sys.modules, "common", generated_common)
    monkeypatch.setitem(sys.modules, "common.v1", generated_common_v1)
    monkeypatch.setitem(sys.modules, "common.v1.metadata_pb2", generated_metadata_pb2)
    monkeypatch.setitem(sys.modules, "retrieval", generated_retrieval)
    monkeypatch.setitem(sys.modules, "retrieval.v1", generated_retrieval_v1)
    monkeypatch.setitem(sys.modules, "retrieval.v1.retrieval_pb2", generated_retrieval_pb2)
    monkeypatch.setitem(sys.modules, "retrieval.v1.retrieval_pb2_grpc", generated_retrieval_pb2_grpc)
    monkeypatch.setattr(grpc, "insecure_channel", lambda _target: _FakeChannel())

    client = GrpcRetrievalEngineClient(
        selection=EngineSelection(
            backend="grpc",
            reason="rust-default",
            mode="rust",
            agent_id="agent_a",
        )
    )

    await client.start()
    graph = client.list_graph(entity_type="project", limit=25)

    assert graph["entities"][0]["entity_key"] == "project:billing"
    assert graph["entities"][0]["metadata"]["source_label"] == "policy:deploy"
    assert graph["relations"][0]["relation_type"] == "observed_in"

    await client.stop()


@pytest.mark.asyncio
async def test_grpc_retrieval_engine_client_requires_bundle_assembly_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import grpc

    class _FakeChannel:
        def close(self) -> None:
            return None

    class _HealthRequest:
        pass

    class _FakeStub:
        def __init__(self, channel: _FakeChannel) -> None:
            self.channel = channel

        def Health(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _HealthRequest)
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                service="koda-retrieval-engine",
                ready=True,
                status="ready",
                details={"transport": "test", "capabilities": "ranking"},
            )

    generated_common = ModuleType("common")
    generated_common_v1 = ModuleType("common.v1")
    generated_metadata_pb2 = ModuleType("common.v1.metadata_pb2")
    generated_metadata_pb2.HealthRequest = _HealthRequest
    generated_retrieval = ModuleType("retrieval")
    generated_retrieval_v1 = ModuleType("retrieval.v1")
    generated_retrieval_pb2 = ModuleType("retrieval.v1.retrieval_pb2")
    generated_retrieval_pb2_grpc = ModuleType("retrieval.v1.retrieval_pb2_grpc")
    generated_retrieval_pb2_grpc.RetrievalEngineServiceStub = _FakeStub

    monkeypatch.setitem(sys.modules, "common", generated_common)
    monkeypatch.setitem(sys.modules, "common.v1", generated_common_v1)
    monkeypatch.setitem(sys.modules, "common.v1.metadata_pb2", generated_metadata_pb2)
    monkeypatch.setitem(sys.modules, "retrieval", generated_retrieval)
    monkeypatch.setitem(sys.modules, "retrieval.v1", generated_retrieval_v1)
    monkeypatch.setitem(sys.modules, "retrieval.v1.retrieval_pb2", generated_retrieval_pb2)
    monkeypatch.setitem(sys.modules, "retrieval.v1.retrieval_pb2_grpc", generated_retrieval_pb2_grpc)
    monkeypatch.setattr(grpc, "insecure_channel", lambda _target: _FakeChannel())

    client = GrpcRetrievalEngineClient(
        selection=EngineSelection(
            backend="grpc",
            reason="rust-default",
            mode="rust",
            agent_id="agent_a",
        )
    )

    await client.start()

    health = client.health()
    assert health["ready"] is True
    assert health["authoritative"] is False
    assert health["cutover_allowed"] is False
    assert health["bundle_contract_ready"] is False

    await client.stop()


@pytest.mark.asyncio
async def test_grpc_retrieval_engine_client_rejects_invalid_remote_bundle_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import grpc

    class _FakeChannel:
        def close(self) -> None:
            return None

    class _HealthRequest:
        pass

    class _RequestMetadata:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class _RetrievalHit:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _RetrieveEnvelope:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _RetrieveRequest:
        def __init__(
            self,
            *,
            metadata: object,
            agent_id: str,
            query: str,
            limit: int,
            envelope: object,
        ) -> None:
            self.metadata = metadata
            self.agent_id = agent_id
            self.query = query
            self.limit = limit
            self.envelope = envelope

    class _FakeStub:
        def __init__(self, channel: _FakeChannel) -> None:
            self.channel = channel

        def Health(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _HealthRequest)
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                service="koda-retrieval-engine",
                ready=True,
                status="ok",
                details={"transport": "test", "capabilities": "bundle-assembly,ranking"},
            )

        def Retrieve(self, request: _RetrieveRequest, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request.metadata, _RequestMetadata)
            assert request.envelope.normalized_query == "deploy"
            return SimpleNamespace(
                trace_id="trace-123",
                strategy="langgraph_current",
            )

    generated_common = ModuleType("common")
    generated_common_v1 = ModuleType("common.v1")
    generated_metadata_pb2 = ModuleType("common.v1.metadata_pb2")
    generated_metadata_pb2.HealthRequest = _HealthRequest
    generated_metadata_pb2.RequestMetadata = _RequestMetadata
    generated_retrieval = ModuleType("retrieval")
    generated_retrieval_v1 = ModuleType("retrieval.v1")
    generated_retrieval_pb2 = ModuleType("retrieval.v1.retrieval_pb2")
    generated_retrieval_pb2.RetrievalHit = _RetrievalHit
    generated_retrieval_pb2.RetrieveEnvelope = _RetrieveEnvelope
    generated_retrieval_pb2.RetrieveRequest = _RetrieveRequest
    generated_retrieval_pb2_grpc = ModuleType("retrieval.v1.retrieval_pb2_grpc")
    generated_retrieval_pb2_grpc.RetrievalEngineServiceStub = _FakeStub

    monkeypatch.setitem(sys.modules, "common", generated_common)
    monkeypatch.setitem(sys.modules, "common.v1", generated_common_v1)
    monkeypatch.setitem(sys.modules, "common.v1.metadata_pb2", generated_metadata_pb2)
    monkeypatch.setitem(sys.modules, "retrieval", generated_retrieval)
    monkeypatch.setitem(sys.modules, "retrieval.v1", generated_retrieval_v1)
    monkeypatch.setitem(sys.modules, "retrieval.v1.retrieval_pb2", generated_retrieval_pb2)
    monkeypatch.setitem(sys.modules, "retrieval.v1.retrieval_pb2_grpc", generated_retrieval_pb2_grpc)
    monkeypatch.setattr(grpc, "insecure_channel", lambda _target: _FakeChannel())

    client = GrpcRetrievalEngineClient(
        selection=EngineSelection(
            backend="grpc",
            reason="rust-default",
            mode="rust",
            agent_id="agent_a",
        )
    )

    await client.start()

    envelope = QueryEnvelope(
        query="deploy",
        normalized_query="deploy",
        agent_id="AGENT_A",
        task_id=1,
        task_kind="deploy",
        strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        requires_write=True,
    )
    with pytest.raises(RuntimeError, match="grpc_retrieval_engine_invalid_bundle_contract"):
        client.query(
            envelope=envelope,
            max_results=1,
        )

    await client.stop()


@pytest.mark.asyncio
async def test_grpc_memory_engine_client_probes_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import grpc.aio as grpc_aio

    class _FakeChannel:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class _HealthRequest:
        pass

    class _FakeStub:
        def __init__(self, channel: _FakeChannel) -> None:
            self.channel = channel
            self.last_metadata: object | None = None

        async def Health(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _HealthRequest)
            assert timeout > 0
            self.last_metadata = metadata
            return SimpleNamespace(
                service="koda-memory-engine",
                ready=False,
                status="stub",
                details={"transport": "test", "authoritative": "false", "maturity": "stub"},
            )

    generated_common = ModuleType("common")
    generated_common_v1 = ModuleType("common.v1")
    generated_metadata_pb2 = ModuleType("common.v1.metadata_pb2")
    generated_metadata_pb2.HealthRequest = _HealthRequest
    generated_memory = ModuleType("memory")
    generated_memory_v1 = ModuleType("memory.v1")
    generated_memory_pb2 = ModuleType("memory.v1.memory_pb2")
    generated_memory_pb2_grpc = ModuleType("memory.v1.memory_pb2_grpc")
    generated_memory_pb2_grpc.MemoryEngineServiceStub = _FakeStub

    monkeypatch.setitem(sys.modules, "common", generated_common)
    monkeypatch.setitem(sys.modules, "common.v1", generated_common_v1)
    monkeypatch.setitem(sys.modules, "common.v1.metadata_pb2", generated_metadata_pb2)
    monkeypatch.setitem(sys.modules, "memory", generated_memory)
    monkeypatch.setitem(sys.modules, "memory.v1", generated_memory_v1)
    monkeypatch.setitem(sys.modules, "memory.v1.memory_pb2", generated_memory_pb2)
    monkeypatch.setitem(sys.modules, "memory.v1.memory_pb2_grpc", generated_memory_pb2_grpc)

    fake_channel = _FakeChannel()
    monkeypatch.setattr(grpc_aio, "insecure_channel", lambda _target: fake_channel)
    monkeypatch.setattr(config, "MEMORY_GRPC_TARGET", "127.0.0.1:50063")

    client = GrpcMemoryEngineClient(
        selection=EngineSelection(
            backend="grpc",
            reason="rust-default",
            mode="rust",
            agent_id="agent_a",
        )
    )

    await client.start()

    health = client.health()
    assert health["service"] == "koda-memory-engine"
    assert health["verified"] is True
    assert health["ready"] is False
    assert health["authoritative"] is False
    assert health["cutover_allowed"] is False
    assert ("x-agent-id", "agent_a") in client._stub.last_metadata  # type: ignore[attr-defined]

    await client.stop()

    assert fake_channel.closed is True
    assert client.health()["connected"] is False


@pytest.mark.asyncio
async def test_grpc_memory_engine_client_recall_sources_authoritative_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import grpc.aio as grpc_aio

    class _FakeChannel:
        async def close(self) -> None:
            return None

    class _HealthRequest:
        pass

    class _MemoryRecordRow:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _RecallResultItem:
        def __init__(self, *, memory: object, score: float, retrieval_source: str, layer: str) -> None:
            self.memory = memory
            self.score = score

    class _RecallContext:
        def __init__(
            self,
            *,
            user_id: int = 0,
            memory_types: list[str] | None = None,
            project_key: str = "",
            environment: str = "",
            team: str = "",
            origin_kinds: list[str] | None = None,
            session_id: str = "",
            source_query_id: int = 0,
            source_task_id: int = 0,
            source_episode_id: int = 0,
            memory_statuses: list[str] | None = None,
        ) -> None:
            self.user_id = user_id
            self.memory_types = memory_types or []
            self.project_key = project_key
            self.environment = environment
            self.team = team
            self.origin_kinds = origin_kinds or []
            self.session_id = session_id
            self.source_query_id = source_query_id
            self.source_task_id = source_task_id
            self.source_episode_id = source_episode_id
            self.memory_statuses = memory_statuses or []

    class _RecallRequest:
        def __init__(
            self,
            *,
            agent_id: str,
            query: str,
            limit: int,
            context: object,
            allowed_layers: list[str],
            allowed_retrieval_sources: list[str],
        ) -> None:
            self.agent_id = agent_id
            self.query = query
            self.limit = limit
            self.context = context
            self.allowed_layers = allowed_layers
            self.allowed_retrieval_sources = allowed_retrieval_sources

    class _FakeStub:
        def __init__(self, channel: _FakeChannel) -> None:
            self.channel = channel

        async def Health(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _HealthRequest)
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                service="koda-memory-engine",
                ready=True,
                status="ready",
                details={
                    "authoritative": "true",
                    "production_ready": "true",
                    "maturity": "authoritative",
                    "capabilities": "recall,cluster,deduplicate,memory_map,curation,curation_detail,curation_action",
                },
            )

        async def Recall(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _RecallRequest)
            assert request.query == "deploy API"
            assert request.limit == 2
            assert isinstance(request.context, _RecallContext)
            assert request.context.user_id == 7
            assert request.context.memory_types == ["fact"]
            assert request.context.project_key == "agent_a"
            assert request.allowed_layers == []
            assert request.allowed_retrieval_sources == []
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                items=[
                    _RecallResultItem(
                        memory=_MemoryRecordRow(
                            id=2,
                            memory_type="fact",
                            content="second",
                            agent_id="agent_a",
                            user_id=7,
                            project_key="agent_a",
                            environment="prod",
                            team="ops",
                            origin_kind="conversation",
                            memory_status="active",
                        ),
                        score=0.95,
                        retrieval_source="lexical",
                        layer="conversational",
                    ),
                    _RecallResultItem(
                        memory=_MemoryRecordRow(
                            id=1,
                            memory_type="fact",
                            content="first",
                            agent_id="agent_a",
                            user_id=7,
                            project_key="agent_a",
                            environment="prod",
                            team="ops",
                            origin_kind="conversation",
                            memory_status="active",
                        ),
                        score=0.20,
                        retrieval_source="lexical",
                        layer="conversational",
                    ),
                ]
            )

    generated_common = ModuleType("common")
    generated_common_v1 = ModuleType("common.v1")
    generated_metadata_pb2 = ModuleType("common.v1.metadata_pb2")
    generated_metadata_pb2.HealthRequest = _HealthRequest
    generated_memory = ModuleType("memory")
    generated_memory_v1 = ModuleType("memory.v1")
    generated_memory_pb2 = ModuleType("memory.v1.memory_pb2")
    generated_memory_pb2.MemoryRecordRow = _MemoryRecordRow
    generated_memory_pb2.RecallResultItem = _RecallResultItem
    generated_memory_pb2.RecallContext = _RecallContext
    generated_memory_pb2.RecallRequest = _RecallRequest
    generated_memory_pb2_grpc = ModuleType("memory.v1.memory_pb2_grpc")
    generated_memory_pb2_grpc.MemoryEngineServiceStub = _FakeStub

    monkeypatch.setitem(sys.modules, "common", generated_common)
    monkeypatch.setitem(sys.modules, "common.v1", generated_common_v1)
    monkeypatch.setitem(sys.modules, "common.v1.metadata_pb2", generated_metadata_pb2)
    monkeypatch.setitem(sys.modules, "memory", generated_memory)
    monkeypatch.setitem(sys.modules, "memory.v1", generated_memory_v1)
    monkeypatch.setitem(sys.modules, "memory.v1.memory_pb2", generated_memory_pb2)
    monkeypatch.setitem(sys.modules, "memory.v1.memory_pb2_grpc", generated_memory_pb2_grpc)
    monkeypatch.setattr(grpc_aio, "insecure_channel", lambda _target: _FakeChannel())

    client = GrpcMemoryEngineClient(
        selection=EngineSelection(
            backend="grpc",
            reason="rust-default",
            mode="rust",
            agent_id="agent_a",
        )
    )

    await client.start()
    reranked = await client.recall(
        query="deploy API",
        limit=2,
        user_id=7,
        memory_types=["fact"],
        project_key="agent_a",
        environment="prod",
        team="ops",
    )

    assert [item["memory_id"] for item in reranked] == [2, 1]
    assert client.health()["cutover_allowed"] is True


@pytest.mark.asyncio
async def test_grpc_memory_engine_client_sends_typed_cluster_and_dedupe_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import grpc.aio as grpc_aio

    class _FakeChannel:
        async def close(self) -> None:
            return None

    class _HealthRequest:
        pass

    class _MemoryRecordRow:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _ClusterRequest:
        def __init__(self, *, agent_id: str, rows: list[object]) -> None:
            self.agent_id = agent_id
            self.rows = rows

    class _DeduplicateRequest:
        def __init__(self, *, agent_id: str, rows: list[object]) -> None:
            self.agent_id = agent_id
            self.rows = rows

    class _FakeStub:
        def __init__(self, channel: _FakeChannel) -> None:
            self.channel = channel

        async def Health(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _HealthRequest)
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                service="koda-memory-engine",
                ready=True,
                status="ready",
                details={
                    "authoritative": "true",
                    "production_ready": "true",
                    "maturity": "authoritative",
                    "capabilities": "cluster,deduplicate",
                },
            )

        async def Cluster(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _ClusterRequest)
            assert request.agent_id == "agent_a"
            assert len(request.rows) == 1
            assert getattr(request.rows[0], "content_hash", "") == "hash-1"
            assert timeout > 0
            assert metadata
            return SimpleNamespace(cluster_json='[{"cluster_id":"cluster-1"}]')

        async def Deduplicate(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _DeduplicateRequest)
            assert request.agent_id == "agent_a"
            assert len(request.rows) == 1
            assert getattr(request.rows[0], "session_id", "") == "sess-1"
            assert timeout > 0
            assert metadata
            return SimpleNamespace(dedupe_json='{"duplicate_groups":[]}')

    generated_common = ModuleType("common")
    generated_common_v1 = ModuleType("common.v1")
    generated_metadata_pb2 = ModuleType("common.v1.metadata_pb2")
    generated_metadata_pb2.HealthRequest = _HealthRequest
    generated_memory = ModuleType("memory")
    generated_memory_v1 = ModuleType("memory.v1")
    generated_memory_pb2 = ModuleType("memory.v1.memory_pb2")
    generated_memory_pb2.MemoryRecordRow = _MemoryRecordRow
    generated_memory_pb2.ClusterRequest = _ClusterRequest
    generated_memory_pb2.DeduplicateRequest = _DeduplicateRequest
    generated_memory_pb2_grpc = ModuleType("memory.v1.memory_pb2_grpc")
    generated_memory_pb2_grpc.MemoryEngineServiceStub = _FakeStub

    monkeypatch.setitem(sys.modules, "common", generated_common)
    monkeypatch.setitem(sys.modules, "common.v1", generated_common_v1)
    monkeypatch.setitem(sys.modules, "common.v1.metadata_pb2", generated_metadata_pb2)
    monkeypatch.setitem(sys.modules, "memory", generated_memory)
    monkeypatch.setitem(sys.modules, "memory.v1", generated_memory_v1)
    monkeypatch.setitem(sys.modules, "memory.v1.memory_pb2", generated_memory_pb2)
    monkeypatch.setitem(sys.modules, "memory.v1.memory_pb2_grpc", generated_memory_pb2_grpc)
    monkeypatch.setattr(grpc_aio, "insecure_channel", lambda _target: _FakeChannel())

    client = GrpcMemoryEngineClient(
        selection=EngineSelection(
            backend="grpc",
            reason="rust-default",
            mode="rust",
            agent_id="agent_a",
        )
    )

    await client.start()
    cluster_payload = await client.cluster(
        rows=[
            {
                "id": 101,
                "content_hash": "hash-1",
                "conflict_key": "cluster-1",
                "quality_score": 0.8,
                "importance": 0.9,
                "created_at": "2026-03-27T09:00:00+00:00",
                "agent_id": "agent_a",
                "memory_type": "procedure",
                "subject": "rollback",
                "content": "rollback billing",
                "session_id": "sess-1",
            }
        ]
    )
    dedupe_payload = await client.deduplicate(
        rows=[
            {
                "id": 101,
                "content_hash": "hash-1",
                "conflict_key": "cluster-1",
                "quality_score": 0.8,
                "importance": 0.9,
                "created_at": "2026-03-27T09:00:00+00:00",
                "agent_id": "agent_a",
                "memory_type": "procedure",
                "subject": "rollback",
                "content": "rollback billing",
                "session_id": "sess-1",
            }
        ]
    )

    assert cluster_payload == [{"cluster_id": "cluster-1"}]
    assert dedupe_payload == {"duplicate_groups": []}


@pytest.mark.asyncio
async def test_grpc_memory_engine_client_supports_projection_rpc_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import grpc.aio as grpc_aio

    class _FakeChannel:
        async def close(self) -> None:
            return None

    class _HealthRequest:
        pass

    class _Message:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _ListCurationItemsRequest:
        def __init__(
            self,
            *,
            agent_id: str,
            total: int,
            rows: list[object],
            all_rows: list[object],
            cluster_rows: list[object],
            filters: object,
        ) -> None:
            self.agent_id = agent_id
            self.total = total
            self.rows = rows
            self.all_rows = all_rows
            self.cluster_rows = cluster_rows
            self.filters = filters

    class _GetMemoryMapRequest:
        def __init__(
            self,
            *,
            agent_id: str,
            summary: object,
            type_counts: list[object],
            user_counts: list[object],
            embedding_jobs: list[object],
            quality_counters: list[object],
            cluster_rows: list[object],
            rows: list[object],
            recent_recall: list[object],
            maintenance_rows: list[object],
            filters: object,
        ) -> None:
            self.agent_id = agent_id
            self.summary = summary
            self.type_counts = type_counts
            self.user_counts = user_counts
            self.embedding_jobs = embedding_jobs
            self.quality_counters = quality_counters
            self.cluster_rows = cluster_rows
            self.rows = rows
            self.recent_recall = recent_recall
            self.maintenance_rows = maintenance_rows
            self.filters = filters

    class _GetCurationDetailRequest:
        def __init__(
            self,
            *,
            agent_id: str,
            subject_id: str,
            detail_kind: str,
            cluster_id: str,
            row: object,
            cluster_rows: list[object],
            related_rows: list[object],
            recent_audits: list[object],
        ) -> None:
            self.agent_id = agent_id
            self.subject_id = subject_id
            self.detail_kind = detail_kind
            self.cluster_id = cluster_id
            self.row = row
            self.cluster_rows = cluster_rows
            self.related_rows = related_rows
            self.recent_audits = recent_audits

    class _ApplyCurationActionRequest:
        def __init__(
            self,
            *,
            agent_id: str,
            subject_id: str,
            action: str,
            target_type: str,
            target_ids: list[str],
            cluster_ids: list[str],
            memory_ids: list[int],
            reason: str,
            duplicate_of_memory_id: int,
            memory_status: str,
            cluster_rows: list[object] | None = None,
        ) -> None:
            self.agent_id = agent_id
            self.subject_id = subject_id
            self.action = action
            self.target_type = target_type
            self.target_ids = target_ids
            self.cluster_ids = cluster_ids
            self.memory_ids = memory_ids
            self.reason = reason
            self.duplicate_of_memory_id = duplicate_of_memory_id
            self.memory_status = memory_status
            self.cluster_rows = cluster_rows or []

    class _FakeStub:
        def __init__(self, channel: _FakeChannel) -> None:
            self.channel = channel

        async def Health(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _HealthRequest)
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                service="koda-memory-engine",
                ready=True,
                status="ready",
                details={
                    "authoritative": "true",
                    "production_ready": "true",
                    "maturity": "authoritative",
                    "capabilities": "curation,memory_map,curation_detail,curation_action",
                },
            )

        async def ListCurationItems(
            self,
            request: object,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert isinstance(request, _ListCurationItemsRequest)
            assert request.agent_id == "agent_a"
            assert getattr(request.filters, "query", "") == "rollback"
            assert len(request.rows) == 1
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                agent_id="AGENT_A",
                overview=_Message(pending_memories=1, pending_clusters=0, expiring_soon=0),
                items=[_Message(id=101, memory_id=101, memory_type="procedure", title="rollback", metadata_json="{}")],
                clusters=[],
                page=_Message(limit=50, offset=0, total=1, has_more=False),
                filters=_Message(query="rollback"),
                status_filters=[_Message(value="pending", label="pending", count=1, color="")],
                type_filters=[_Message(value="procedure", label="procedure", count=1, color="")],
            )

        async def GetMemoryMap(
            self,
            request: object,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert isinstance(request, _GetMemoryMapRequest)
            assert request.agent_id == "agent_a"
            assert getattr(request.summary, "total", 0) == 3
            assert len(request.rows) == 1
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                agent_id="AGENT_A",
                summary=_Message(total=3, active=2, superseded=1, stale=0, invalidated=0),
                embedding_jobs=[_Message(key="ready", count=2)],
                quality_counters=[_Message(key="dedup.semantic", count=4)],
                top_clusters=[_Message(cluster_id="cluster-1", memory_count=2)],
                recent_recall=[],
                maintenance=[],
                nodes=[],
                edges=[],
                stats=_Message(total_memories=3, rendered_memories=0, hidden_memories=3, semantic_status="available"),
                filters=_Message(limit=25),
                filter_users=[],
                filter_sessions=[],
                filter_types=[],
                type_counts=[],
                user_counts=[],
                semantic_status="available",
            )

        async def GetCurationDetail(
            self,
            request: object,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert isinstance(request, _GetCurationDetailRequest)
            assert request.subject_id == "101"
            assert getattr(request.row, "id", 0) == 101
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                detail_kind="memory",
                memory=_Message(id=101, memory_id=101, memory_type="procedure", title="rollback", metadata_json="{}"),
                related_memories=[],
                cluster_members=[],
                recent_audits=[],
                cluster_summary=None,
                source_query_text="rollback billing",
                session_name="sess-1",
                overlaps=[],
                history=[],
            )

        async def ApplyCurationAction(
            self,
            request: object,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert isinstance(request, _ApplyCurationActionRequest)
            assert request.subject_id == "cluster-1"
            assert request.action == "merge"
            assert request.memory_ids == [101, 102]
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                applied=True,
                updated_count=1,
                memory_ids=[101, 102],
                duplicate_of_memory_id=101,
                operations=[SimpleNamespace(op="review_state", memory_id=102)],
                target_type="cluster",
                cluster_ids=["cluster-1"],
                reason="dedupe canonical",
                memory_status="superseded",
                review_status="merged",
            )

    generated_common = ModuleType("common")
    generated_common_v1 = ModuleType("common.v1")
    generated_metadata_pb2 = ModuleType("common.v1.metadata_pb2")
    generated_metadata_pb2.HealthRequest = _HealthRequest
    generated_memory = ModuleType("memory")
    generated_memory_v1 = ModuleType("memory.v1")
    generated_memory_pb2 = ModuleType("memory.v1.memory_pb2")
    generated_memory_pb2.MemoryRecordRow = _Message
    generated_memory_pb2.CurationClusterSummary = _Message
    generated_memory_pb2.MemoryDashboardFilter = _Message
    generated_memory_pb2.MemoryMapSummary = _Message
    generated_memory_pb2.CounterEntry = _Message
    generated_memory_pb2.UserMemoryCount = _Message
    generated_memory_pb2.RecallLogItem = _Message
    generated_memory_pb2.MaintenanceLogItem = _Message
    generated_memory_pb2.AuditLogItem = _Message
    generated_memory_pb2.ListCurationItemsRequest = _ListCurationItemsRequest
    generated_memory_pb2.GetMemoryMapRequest = _GetMemoryMapRequest
    generated_memory_pb2.GetCurationDetailRequest = _GetCurationDetailRequest
    generated_memory_pb2.ApplyCurationActionRequest = _ApplyCurationActionRequest
    generated_memory_pb2_grpc = ModuleType("memory.v1.memory_pb2_grpc")
    generated_memory_pb2_grpc.MemoryEngineServiceStub = _FakeStub

    monkeypatch.setitem(sys.modules, "common", generated_common)
    monkeypatch.setitem(sys.modules, "common.v1", generated_common_v1)
    monkeypatch.setitem(sys.modules, "common.v1.metadata_pb2", generated_metadata_pb2)
    monkeypatch.setitem(sys.modules, "memory", generated_memory)
    monkeypatch.setitem(sys.modules, "memory.v1", generated_memory_v1)
    monkeypatch.setitem(sys.modules, "memory.v1.memory_pb2", generated_memory_pb2)
    monkeypatch.setitem(sys.modules, "memory.v1.memory_pb2_grpc", generated_memory_pb2_grpc)
    monkeypatch.setattr(grpc_aio, "insecure_channel", lambda _target: _FakeChannel())

    client = GrpcMemoryEngineClient(
        selection=EngineSelection(
            backend="grpc",
            reason="rust-default",
            mode="rust",
            agent_id="agent_a",
        )
    )

    await client.start()

    curation = await client.list_curation_items(
        payload={"total": 1, "rows": [{"id": 101}], "all_rows": [{"id": 101}], "filters": {"query": "rollback"}}
    )
    memory_map = await client.get_memory_map(
        payload={
            "agent_id": "AGENT_A",
            "summary_row": {"total_memories": 3},
            "rows": [{"id": 101}],
            "filters": {"limit": 25},
        }
    )
    detail = await client.get_curation_detail(subject_id="101", payload={"row": {"id": 101}})
    action = await client.apply_curation_action(
        subject_id="cluster-1",
        action="merge",
        payload={"memory_ids": [101, 102]},
    )

    assert curation["items"][0]["id"] == 101
    assert curation["filters"]["query"] == "rollback"
    assert memory_map["summary"]["total"] == 3
    assert detail["memory"]["id"] == 101
    assert detail["source_query_text"] == "rollback billing"
    assert action["applied"] is True
    assert action["updated_count"] == 1
    assert action["duplicate_of_memory_id"] == 101


@pytest.mark.asyncio
async def test_grpc_artifact_engine_client_probes_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import grpc.aio as grpc_aio

    class _FakeChannel:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class _HealthRequest:
        pass

    class _FakeStub:
        def __init__(self, channel: _FakeChannel) -> None:
            self.channel = channel
            self.last_metadata: object | None = None

        async def Health(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _HealthRequest)
            assert timeout > 0
            self.last_metadata = metadata
            return SimpleNamespace(
                service="koda-artifact-engine",
                ready=True,
                status="ready",
                details={
                    "object_store": "ready",
                    "storage_backing": "object_storage_postgres",
                    "authoritative": "true",
                    "production_ready": "true",
                    "maturity": "ga",
                },
            )

    generated_common = ModuleType("common")
    generated_common_v1 = ModuleType("common.v1")
    generated_metadata_pb2 = ModuleType("common.v1.metadata_pb2")
    generated_metadata_pb2.HealthRequest = _HealthRequest
    generated_artifact = ModuleType("artifact")
    generated_artifact_v1 = ModuleType("artifact.v1")
    generated_artifact_pb2 = ModuleType("artifact.v1.artifact_pb2")
    generated_artifact_pb2_grpc = ModuleType("artifact.v1.artifact_pb2_grpc")
    generated_artifact_pb2_grpc.ArtifactEngineServiceStub = _FakeStub

    monkeypatch.setitem(sys.modules, "common", generated_common)
    monkeypatch.setitem(sys.modules, "common.v1", generated_common_v1)
    monkeypatch.setitem(sys.modules, "common.v1.metadata_pb2", generated_metadata_pb2)
    monkeypatch.setitem(sys.modules, "artifact", generated_artifact)
    monkeypatch.setitem(sys.modules, "artifact.v1", generated_artifact_v1)
    monkeypatch.setitem(sys.modules, "artifact.v1.artifact_pb2", generated_artifact_pb2)
    monkeypatch.setitem(sys.modules, "artifact.v1.artifact_pb2_grpc", generated_artifact_pb2_grpc)

    fake_channel = _FakeChannel()
    monkeypatch.setattr(grpc_aio, "insecure_channel", lambda _target: fake_channel)
    monkeypatch.setattr(config, "ARTIFACT_GRPC_TARGET", "/tmp/koda/artifact.sock")

    client = GrpcArtifactEngineClient(
        selection=EngineSelection(
            backend="grpc",
            reason="rust-default",
            mode="rust",
            agent_id="agent_a",
        )
    )

    await client.start()

    health = client.health()
    assert health["service"] == "koda-artifact-engine"
    assert health["transport"] == "grpc-uds"
    assert health["verified"] is True
    assert health["ready"] is True
    assert health["production_ready"] is True
    assert health["cutover_allowed"] is True
    assert ("x-agent-id", "agent_a") in client._stub.last_metadata  # type: ignore[attr-defined]

    await client.stop()

    assert fake_channel.closed is True


@pytest.mark.asyncio
async def test_grpc_artifact_engine_client_ingests_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import grpc.aio as grpc_aio

    class _FakeChannel:
        async def close(self) -> None:
            return None

    class _HealthRequest:
        pass

    class _PutArtifactRequest:
        def __init__(
            self,
            *,
            metadata: object | None = None,
            agent_id: str = "",
            logical_filename: str = "",
            object_key: str = "",
            mime_type: str = "",
            source_metadata_json: str = "",
            purpose: str = "",
            data: bytes = b"",
        ) -> None:
            self.metadata = metadata
            self.agent_id = agent_id
            self.logical_filename = logical_filename
            self.object_key = object_key
            self.mime_type = mime_type
            self.source_metadata_json = source_metadata_json
            self.purpose = purpose
            self.data = data

    class _GenerateEvidenceByArtifactIdRequest:
        def __init__(self, *, agent_id: str, artifact_id: str) -> None:
            self.agent_id = agent_id
            self.artifact_id = artifact_id

    class _GetArtifactMetadataByArtifactIdRequest:
        def __init__(self, *, agent_id: str, artifact_id: str) -> None:
            self.agent_id = agent_id
            self.artifact_id = artifact_id

    class _FakeStub:
        def __init__(self, channel: _FakeChannel) -> None:
            self.channel = channel

        async def Health(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _HealthRequest)
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                service="koda-artifact-engine",
                ready=True,
                status="ready",
                details={
                    "authoritative": "true",
                    "production_ready": "true",
                    "maturity": "ga",
                    "storage_backing": "object_storage_postgres",
                    "object_store": "ready",
                },
            )

        async def PutArtifact(
            self,
            request: object,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            chunks = [item async for item in request]
            assert chunks
            assert isinstance(chunks[0], _PutArtifactRequest)
            assert chunks[0].agent_id == "agent_a"
            assert chunks[0].logical_filename == "file.txt"
            assert chunks[0].data == b"file-bytes"
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                artifact=SimpleNamespace(
                    artifact_id="abc1230000000000",
                    object_key="agent_a/file.txt",
                    content_hash="abc123",
                    mime_type="text/plain",
                ),
                metadata_json='{"size_bytes":7,"logical_filename":"file.txt"}',
                upload_outcome="persisted_object_storage",
            )

        async def GenerateEvidenceByArtifactId(
            self,
            request: object,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert isinstance(request, _GenerateEvidenceByArtifactIdRequest)
            assert request.agent_id == "agent_a"
            assert request.artifact_id == "abc1230000000000"
            assert timeout > 0
            assert metadata
            return SimpleNamespace(evidence_json='{"excerpt":"hello"}')

        async def GetArtifactMetadataByArtifactId(
            self,
            request: object,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert isinstance(request, _GetArtifactMetadataByArtifactIdRequest)
            assert request.agent_id == "agent_a"
            assert request.artifact_id == "abc1230000000000"
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                artifact=SimpleNamespace(
                    artifact_id="abc1230000000000",
                    object_key="agent_a/file.txt",
                    content_hash="abc123",
                    mime_type="text/plain",
                ),
                metadata_json='{"size_bytes":7}',
            )

    generated_common = ModuleType("common")
    generated_common_v1 = ModuleType("common.v1")
    generated_metadata_pb2 = ModuleType("common.v1.metadata_pb2")
    generated_metadata_pb2.HealthRequest = _HealthRequest
    generated_artifact = ModuleType("artifact")
    generated_artifact_v1 = ModuleType("artifact.v1")
    generated_artifact_pb2 = ModuleType("artifact.v1.artifact_pb2")
    generated_artifact_pb2.PutArtifactRequest = _PutArtifactRequest
    generated_artifact_pb2.GenerateEvidenceByArtifactIdRequest = _GenerateEvidenceByArtifactIdRequest
    generated_artifact_pb2.GetArtifactMetadataByArtifactIdRequest = _GetArtifactMetadataByArtifactIdRequest
    generated_artifact_pb2_grpc = ModuleType("artifact.v1.artifact_pb2_grpc")
    generated_artifact_pb2_grpc.ArtifactEngineServiceStub = _FakeStub

    monkeypatch.setitem(sys.modules, "common", generated_common)
    monkeypatch.setitem(sys.modules, "common.v1", generated_common_v1)
    monkeypatch.setitem(sys.modules, "common.v1.metadata_pb2", generated_metadata_pb2)
    monkeypatch.setitem(sys.modules, "artifact", generated_artifact)
    monkeypatch.setitem(sys.modules, "artifact.v1", generated_artifact_v1)
    monkeypatch.setitem(sys.modules, "artifact.v1.artifact_pb2", generated_artifact_pb2)
    monkeypatch.setitem(sys.modules, "artifact.v1.artifact_pb2_grpc", generated_artifact_pb2_grpc)
    monkeypatch.setattr(grpc_aio, "insecure_channel", lambda _target: _FakeChannel())

    client = GrpcArtifactEngineClient(
        selection=EngineSelection(
            backend="grpc",
            reason="rust-default",
            mode="rust",
            agent_id="agent_a",
        )
    )

    file_path = tmp_path / "file.txt"
    file_path.write_bytes(b"file-bytes")

    await client.start()
    artifact = await client.put_artifact(path=str(file_path))
    evidence = await client.generate_evidence_by_artifact_id(artifact_id="abc1230000000000")
    metadata = await client.get_artifact_metadata_by_artifact_id(artifact_id="abc1230000000000")

    assert artifact["artifact_id"] == "abc1230000000000"
    assert artifact["object_key"] == "agent_a/file.txt"
    assert artifact["metadata_json"] == '{"size_bytes":7,"logical_filename":"file.txt"}'
    assert artifact["upload_outcome"] == "persisted_object_storage"
    assert evidence["evidence_json"] == '{"excerpt":"hello"}'
    assert metadata["artifact_id"] == "abc1230000000000"
    assert metadata["metadata_json"] == '{"size_bytes":7}'
    assert client.health()["cutover_allowed"] is True


@pytest.mark.asyncio
async def test_grpc_runtime_kernel_client_probes_health_and_forwards_pause(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import grpc.aio as grpc_aio

    class _FakeChannel:
        async def close(self) -> None:
            return None

    class _HealthRequest:
        pass

    class _RequestMetadata:
        def __init__(self, *, agent_id: str = "", task_id: str = "", labels: dict[str, str] | None = None) -> None:
            self.agent_id = agent_id
            self.task_id = task_id
            self.labels = labels or {}

    class _CreateEnvironmentRequest:
        def __init__(
            self,
            *,
            metadata: _RequestMetadata,
            agent_id: str,
            task_id: str,
            workspace_path: str,
            worktree_ref: str,
            base_work_dir: str = "",
            slug: str = "",
            create_worktree: bool = False,
        ) -> None:
            self.metadata = metadata
            self.agent_id = agent_id
            self.task_id = task_id
            self.workspace_path = workspace_path
            self.worktree_ref = worktree_ref
            self.base_work_dir = base_work_dir
            self.slug = slug
            self.create_worktree = create_worktree

    class _ExecuteCommandRequest:
        def __init__(
            self,
            *,
            metadata: _RequestMetadata,
            agent_id: str,
            runtime_env_id: str,
            command: str,
            argv: list[str],
            working_directory: str,
            environment_overrides: dict[str, str],
            stdin_payload: bytes,
            timeout_seconds: int,
            allow_network: bool,
            purpose: str,
            env_labels: dict[str, str],
            start_new_session: bool,
        ) -> None:
            self.metadata = metadata
            self.agent_id = agent_id
            self.runtime_env_id = runtime_env_id
            self.command = command
            self.argv = argv
            self.working_directory = working_directory
            self.environment_overrides = environment_overrides
            self.stdin_payload = stdin_payload
            self.timeout_seconds = timeout_seconds
            self.allow_network = allow_network
            self.purpose = purpose
            self.env_labels = env_labels
            self.start_new_session = start_new_session

    class _StartTaskRequest:
        def __init__(self, *, metadata: _RequestMetadata, task_id: str, command: str, args: list[str]) -> None:
            self.metadata = metadata
            self.task_id = task_id
            self.command = command
            self.args = args

    class _AttachTerminalRequest:
        def __init__(self, *, metadata: _RequestMetadata, task_id: str, session_id: str) -> None:
            self.metadata = metadata
            self.task_id = task_id
            self.session_id = session_id

    class _PauseTaskRequest:
        def __init__(self, *, task_id: str, reason: str) -> None:
            self.task_id = task_id
            self.reason = reason

    class _ResumeTaskRequest:
        def __init__(self, *, task_id: str, phase: str) -> None:
            self.task_id = task_id
            self.phase = phase

    class _FinalizeTaskRequest:
        def __init__(
            self,
            *,
            task_id: str,
            success: bool,
            error_message: str,
            final_phase: str = "",
        ) -> None:
            self.task_id = task_id
            self.success = success
            self.error_message = error_message
            self.final_phase = final_phase

    class _ReconcileRequest:
        pass

    class _CollectSnapshotRequest:
        def __init__(self, *, metadata: _RequestMetadata, task_id: str) -> None:
            self.metadata = metadata
            self.task_id = task_id

    class _SaveCheckpointRequest:
        def __init__(
            self,
            *,
            metadata: _RequestMetadata,
            task_id: str,
            environment_id: str,
            success: bool,
            final_phase: str,
            retention_hours: int,
        ) -> None:
            self.metadata = metadata
            self.task_id = task_id
            self.environment_id = environment_id
            self.success = success
            self.final_phase = final_phase
            self.retention_hours = retention_hours

    class _GetCheckpointRequest:
        def __init__(self, *, metadata: _RequestMetadata, task_id: str, checkpoint_id: str) -> None:
            self.metadata = metadata
            self.task_id = task_id
            self.checkpoint_id = checkpoint_id

    class _RestoreCheckpointRequest:
        def __init__(
            self,
            *,
            metadata: _RequestMetadata,
            task_id: str,
            checkpoint_id: str,
            workspace_path: str,
        ) -> None:
            self.metadata = metadata
            self.task_id = task_id
            self.checkpoint_id = checkpoint_id
            self.workspace_path = workspace_path

    class _CleanupEnvironmentRequest:
        def __init__(self, *, metadata: _RequestMetadata, task_id: str, force: bool) -> None:
            self.metadata = metadata
            self.task_id = task_id
            self.force = force

    class _FakeStub:
        def __init__(self, channel: _FakeChannel) -> None:
            self.channel = channel

        async def Health(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _HealthRequest)
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                service="koda-runtime-kernel",
                ready=True,
                status="ok",
                details={
                    "transport": "test",
                    "authoritative": "true",
                    "production_ready": "true",
                    "maturity": "ga",
                    "full_authority": "true",
                },
            )

        async def CreateEnvironment(
            self,
            request: _CreateEnvironmentRequest,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert request.metadata.agent_id == "AGENT_A"
            assert request.task_id == "42"
            assert request.base_work_dir == "/workspace"
            assert request.slug == "task-42"
            assert request.create_worktree is True
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                environment=SimpleNamespace(environment_id="env-42", agent_id=request.agent_id),
                runtime_root="/tmp/runtime/env-42",
                workspace_path="/tmp/runtime/workspaces/task-42",
                branch_name="task/42",
                created_worktree=True,
                worktree_mode="worktree",
                metadata_path="/tmp/runtime/workspaces/task-42/worktree.json",
            )

        async def ExecuteCommand(
            self,
            request: _ExecuteCommandRequest,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert request.metadata.agent_id == "AGENT_A"
            assert request.command == "echo hello"
            assert request.timeout_seconds == 5
            assert request.environment_overrides == {"LOCAL_FLAG": "enabled"}
            assert request.start_new_session is True
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                command=request.command,
                argv=[],
                working_directory=request.working_directory,
                stdout="hello",
                stderr="",
                exit_code=0,
                timed_out=False,
                killed=False,
                started_at_ms=1000,
                finished_at_ms=2000,
            )

        async def StartTask(
            self,
            request: _StartTaskRequest,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert request.metadata.task_id == "42"
            assert request.command == "python"
            assert request.args == ["-m", "http.server"]
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                environment=SimpleNamespace(environment_id="env-42"),
                process_id="proc-1",
                phase="running",
            )

        async def AttachTerminal(
            self,
            request: _AttachTerminalRequest,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert request.session_id == "session-1"
            assert timeout > 0
            assert metadata
            return SimpleNamespace(task_id=request.task_id, session_id=request.session_id, attached=True)

        async def PauseTask(self, request: _PauseTaskRequest, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert request.reason == "operator"
            assert timeout > 0
            assert metadata
            return SimpleNamespace(task_id=request.task_id, phase="paused_for_operator")

        async def ResumeTask(
            self,
            request: _ResumeTaskRequest,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert request.phase == "executing"
            assert timeout > 0
            assert metadata
            return SimpleNamespace(task_id=request.task_id, phase=request.phase)

        async def FinalizeTask(
            self,
            request: _FinalizeTaskRequest,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert request.success is True
            assert request.final_phase == "completed"
            assert timeout > 0
            assert metadata
            return SimpleNamespace(task_id=request.task_id, final_phase="completed")

        async def Reconcile(self, request: object, *, timeout: float, metadata: object) -> SimpleNamespace:
            assert isinstance(request, _ReconcileRequest)
            assert timeout > 0
            assert metadata
            return SimpleNamespace(active_environments=2, reconciled_environments=2)

        async def CollectSnapshot(
            self,
            request: _CollectSnapshotRequest,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert request.task_id == "42"
            assert timeout > 0
            assert metadata
            payload_json = (
                b'{"kernel":{"service":"koda-runtime-kernel"},'
                b'"task":{"task_id":"42"},'
                b'"environment":{"environment_id":"env-42"}}'
            )
            return SimpleNamespace(task_id=request.task_id, environment_id="env-42", payload_json=payload_json)

        async def CleanupEnvironment(
            self,
            request: _CleanupEnvironmentRequest,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert request.task_id == "42"
            assert request.force is True
            assert timeout > 0
            assert metadata
            return SimpleNamespace(
                task_id=request.task_id,
                environment_id="env-42",
                cleaned=True,
                workspace_removed=True,
                runtime_root_removed=True,
                worktree_mode="worktree",
            )

        async def SaveCheckpoint(
            self,
            request: _SaveCheckpointRequest,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert request.metadata.task_id == "42"
            assert request.retention_hours == 12
            assert timeout > 0
            assert metadata
            checkpoint = SimpleNamespace(
                checkpoint_id="ckpt-42",
                task_id=request.task_id,
                environment_id=request.environment_id,
                success=request.success,
                final_phase=request.final_phase,
                checkpoint_dir="/tmp/runtime/checkpoints/ckpt-42",
                manifest_path="/tmp/runtime/checkpoints/ckpt-42/manifest.json",
                snapshot_path="/tmp/runtime/checkpoints/ckpt-42/workspace_snapshot.json",
                patch_path="/tmp/runtime/checkpoints/ckpt-42/git.patch",
                git_status_path="/tmp/runtime/checkpoints/ckpt-42/git_status.txt",
                untracked_bundle_path="/tmp/runtime/checkpoints/ckpt-42/untracked.tar.gz",
                commit_sha="abc123",
                has_untracked_bundle=True,
                created_at_ms=123,
                expires_at_ms=456,
            )
            return SimpleNamespace(checkpoint=checkpoint, saved=True)

        async def GetCheckpoint(
            self,
            request: _GetCheckpointRequest,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert request.metadata.task_id == "42"
            assert request.checkpoint_id == "ckpt-42"
            assert timeout > 0
            assert metadata
            checkpoint = SimpleNamespace(
                checkpoint_id=request.checkpoint_id,
                task_id=request.task_id,
                environment_id="env-42",
                success=True,
                final_phase="completed",
                checkpoint_dir="/tmp/runtime/checkpoints/ckpt-42",
                manifest_path="/tmp/runtime/checkpoints/ckpt-42/manifest.json",
                snapshot_path="/tmp/runtime/checkpoints/ckpt-42/workspace_snapshot.json",
                patch_path="/tmp/runtime/checkpoints/ckpt-42/git.patch",
                git_status_path="/tmp/runtime/checkpoints/ckpt-42/git_status.txt",
                untracked_bundle_path="/tmp/runtime/checkpoints/ckpt-42/untracked.tar.gz",
                commit_sha="abc123",
                has_untracked_bundle=True,
                created_at_ms=123,
                expires_at_ms=456,
            )
            return SimpleNamespace(checkpoint=checkpoint, found=True)

        async def RestoreCheckpoint(
            self,
            request: _RestoreCheckpointRequest,
            *,
            timeout: float,
            metadata: object,
        ) -> SimpleNamespace:
            assert request.metadata.task_id == "42"
            assert request.workspace_path == "/workspace"
            assert timeout > 0
            assert metadata
            checkpoint = SimpleNamespace(
                checkpoint_id=request.checkpoint_id,
                environment_id="env-42",
                checkpoint_dir="/tmp/runtime/checkpoints/ckpt-42",
                manifest_path="/tmp/runtime/checkpoints/ckpt-42/manifest.json",
                snapshot_path="/tmp/runtime/checkpoints/ckpt-42/workspace_snapshot.json",
                patch_path="/tmp/runtime/checkpoints/ckpt-42/git.patch",
                git_status_path="/tmp/runtime/checkpoints/ckpt-42/git_status.txt",
                untracked_bundle_path="/tmp/runtime/checkpoints/ckpt-42/untracked.tar.gz",
                commit_sha="abc123",
                has_untracked_bundle=True,
            )
            return SimpleNamespace(
                checkpoint=checkpoint,
                found=True,
                restored=True,
                workspace_path=request.workspace_path,
                restored_commit_sha="abc123",
                restored_paths=["git_reset", "git_patch"],
                error_message="",
            )

    generated_common = ModuleType("common")
    generated_common_v1 = ModuleType("common.v1")
    generated_metadata_pb2 = ModuleType("common.v1.metadata_pb2")
    generated_metadata_pb2.HealthRequest = _HealthRequest
    generated_metadata_pb2.RequestMetadata = _RequestMetadata
    generated_runtime = ModuleType("runtime")
    generated_runtime_v1 = ModuleType("runtime.v1")
    generated_runtime_pb2 = ModuleType("runtime.v1.runtime_pb2")
    generated_runtime_pb2.CreateEnvironmentRequest = _CreateEnvironmentRequest
    generated_runtime_pb2.ExecuteCommandRequest = _ExecuteCommandRequest
    generated_runtime_pb2.StartTaskRequest = _StartTaskRequest
    generated_runtime_pb2.AttachTerminalRequest = _AttachTerminalRequest
    generated_runtime_pb2.PauseTaskRequest = _PauseTaskRequest
    generated_runtime_pb2.ResumeTaskRequest = _ResumeTaskRequest
    generated_runtime_pb2.FinalizeTaskRequest = _FinalizeTaskRequest
    generated_runtime_pb2.ReconcileRequest = _ReconcileRequest
    generated_runtime_pb2.CollectSnapshotRequest = _CollectSnapshotRequest
    generated_runtime_pb2.SaveCheckpointRequest = _SaveCheckpointRequest
    generated_runtime_pb2.GetCheckpointRequest = _GetCheckpointRequest
    generated_runtime_pb2.RestoreCheckpointRequest = _RestoreCheckpointRequest
    generated_runtime_pb2.CleanupEnvironmentRequest = _CleanupEnvironmentRequest
    generated_runtime_pb2_grpc = ModuleType("runtime.v1.runtime_pb2_grpc")
    generated_runtime_pb2_grpc.RuntimeKernelServiceStub = _FakeStub

    monkeypatch.setattr(config, "AGENT_ID", "AGENT_A")
    monkeypatch.setitem(sys.modules, "common", generated_common)
    monkeypatch.setitem(sys.modules, "common.v1", generated_common_v1)
    monkeypatch.setitem(sys.modules, "common.v1.metadata_pb2", generated_metadata_pb2)
    monkeypatch.setitem(sys.modules, "runtime", generated_runtime)
    monkeypatch.setitem(sys.modules, "runtime.v1", generated_runtime_v1)
    monkeypatch.setitem(sys.modules, "runtime.v1.runtime_pb2", generated_runtime_pb2)
    monkeypatch.setitem(sys.modules, "runtime.v1.runtime_pb2_grpc", generated_runtime_pb2_grpc)
    monkeypatch.setattr(grpc_aio, "insecure_channel", lambda _target: _FakeChannel())

    client = GrpcRuntimeKernelClient(runtime_root=tmp_path, store=_DummyStore(), mode="rust")

    await client.start()

    health = client.health()
    assert health["verified"] is True
    assert health["ready"] is True
    assert health["authoritative"] is True
    assert health["cutover_allowed"] is True
    assert health["service"] == "koda-runtime-kernel"

    create_result = await client.create_environment(
        task_id=42,
        agent_id="AGENT_A",
        workspace_path="",
        worktree_ref="",
        base_work_dir="/workspace",
        slug="task-42",
        create_worktree=True,
    )
    execute_result = await client.execute_command(
        agent_id="AGENT_A",
        command="echo hello",
        working_directory="/workspace",
        environment_overrides={"LOCAL_FLAG": "enabled"},
        timeout_seconds=5,
        purpose="shell",
        start_new_session=True,
    )
    start_result = await client.start_task(task_id=42, command="python", args=["-m", "http.server"])
    attach_result = await client.attach_terminal(task_id=42, session_id="session-1")
    pause_result = await client.pause_task(task_id=42, reason="operator", actor="local_ui")
    resume_result = await client.resume_task(task_id=42, actor="local_ui")
    finalize_result = await client.finalize_task(
        task_id=42,
        success=True,
        final_phase="completed",
        error_message=None,
    )
    reconcile_result = await client.reconcile()
    snapshot_result = await client.collect_snapshot(task_id=42)
    cleanup_result = await client.cleanup_environment(task_id=42, force=True)
    save_result = await client.save_checkpoint(
        task_id=42,
        environment_id="env-42",
        success=True,
        final_phase="completed",
        retention_hours=12,
    )
    fetched_checkpoint = await client.get_checkpoint(task_id=42, checkpoint_id="ckpt-42")
    restore_result = await client.restore_checkpoint(
        task_id=42,
        checkpoint_id="ckpt-42",
        workspace_path="/workspace",
    )

    assert create_result["forwarded"] is True
    assert create_result["environment_id"] == "env-42"
    assert create_result["workspace_path"] == "/tmp/runtime/workspaces/task-42"
    assert execute_result["forwarded"] is True
    assert execute_result["stdout"] == "hello"
    assert execute_result["exit_code"] == 0
    assert start_result["forwarded"] is True
    assert start_result["process_id"] == "proc-1"
    assert attach_result["attached"] is True
    assert pause_result["forwarded"] is True
    assert pause_result["phase"] == "paused_for_operator"
    assert resume_result["phase"] == "executing"
    assert finalize_result["final_phase"] == "completed"
    assert reconcile_result["reconciled_environments"] == 2
    assert snapshot_result is not None
    assert snapshot_result["environment"]["environment_id"] == "env-42"
    assert cleanup_result["cleaned"] is True
    assert save_result["saved"] is True
    assert save_result["patch_path"].endswith("git.patch")
    assert fetched_checkpoint is not None
    assert fetched_checkpoint["commit_sha"] == "abc123"
    assert restore_result["restored"] is True
    assert restore_result["restored_paths"] == ["git_reset", "git_patch"]

    await client.stop()
