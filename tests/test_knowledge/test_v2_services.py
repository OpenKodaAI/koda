"""Tests for retrieval v2, grounded answer services, and storage v2."""

from __future__ import annotations

import asyncio
import hashlib
import sys
from collections.abc import Coroutine, Iterator
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.knowledge.answer_service import KnowledgeAnswerService
from koda.knowledge.experiments import KnowledgeExperimentPlan
from koda.knowledge.graph_materializer import KnowledgeGraphMaterializer
from koda.knowledge.ingest_worker import KnowledgeIngestWorker
from koda.knowledge.judge_service import KnowledgeJudgeService
from koda.knowledge.manager import KnowledgeManager
from koda.knowledge.repository import KnowledgeRepository
from koda.knowledge.retrieval_v2 import KnowledgeRetrievalService
from koda.knowledge.runtime_supervisor import KnowledgeRuntimeSupervisor
from koda.knowledge.semantic_judge import KnowledgeSemanticJudgeService
from koda.knowledge.storage_v2 import KnowledgeStorageV2
from koda.knowledge.types import (
    AnswerJudgement,
    AuthoritativeEvidence,
    CitationRequirement,
    GroundedAnswer,
    KnowledgeEntry,
    KnowledgeHit,
    KnowledgeLayer,
    KnowledgeQueryContext,
    KnowledgeResolution,
    KnowledgeScope,
    QueryEnvelope,
    RetrievalBundle,
    RetrievalStrategy,
    RetrievalTraceHit,
    TraceRole,
)
from koda.knowledge.v2.common import clear_shared_postgres_backends
from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend


def _hit(
    *,
    entry_id: str,
    title: str,
    layer: KnowledgeLayer,
    source_label: str,
    content: str,
    similarity: float,
    project_key: str = "billing",
    environment: str = "prod",
    team: str = "agent_a",
) -> KnowledgeHit:
    return KnowledgeHit(
        entry=KnowledgeEntry(
            id=entry_id,
            title=title,
            content=content,
            layer=layer,
            scope=KnowledgeScope.OPERATIONAL_POLICY,
            source_label=source_label,
            source_path=f"/tmp/{entry_id}.md",
            updated_at=datetime(2026, 3, 25),
            project_key=project_key,
            environment=environment,
            team=team,
            source_type="document",
            operable=True,
        ),
        similarity=similarity,
        freshness="fresh",
    )


def test_retrieval_v2_delegates_to_configured_engine_client():
    envelope = QueryEnvelope(
        query="Analyze BILL-123 deploy drift",
        normalized_query="Analyze BILL-123 deploy drift",
        agent_id="AGENT_A",
        task_id=128,
        task_kind="deploy",
        project_key="billing",
        environment="prod",
        team="agent_a",
        requires_write=True,
        strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
    )
    delegated_bundle = RetrievalBundle(
        normalized_query=envelope.normalized_query,
        query_intent="delegated",
        route="grpc",
        strategy=envelope.strategy,
        explanation="delegated to grpc engine",
    )

    class _Engine:
        engine_name = "rust_grpc"

        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def query(self, **kwargs: object) -> RetrievalBundle:
            self.calls.append(dict(kwargs))
            return delegated_bundle

    engine = _Engine()
    service = KnowledgeRetrievalService(engine_client=engine)
    bundle = service.query(
        envelope=envelope,
        max_results=3,
    )

    assert bundle is delegated_bundle
    assert service.engine_name == "rust_grpc"
    assert engine.calls[0]["envelope"] is envelope
    assert bundle.effective_engine == "rust_grpc"
    assert bundle.fallback_used is False


def test_retrieval_v2_fails_closed_when_rust_engine_is_not_ready():
    class _NotReadyEngine:
        engine_name = "rust_grpc"

        def health(self) -> dict[str, object]:
            return {
                "ready": False,
                "cutover_allowed": False,
                "selection_reason": "rust-default",
            }

        def query(self, **_kwargs: object) -> RetrievalBundle:
            raise AssertionError("query should not run when cutover is not allowed")

    service = KnowledgeRetrievalService(engine_client=_NotReadyEngine())
    envelope = QueryEnvelope(
        query="Analyze BILL-123 deploy drift",
        normalized_query="Analyze BILL-123 deploy drift",
        agent_id="AGENT_A",
        task_id=128,
        task_kind="deploy",
        project_key="billing",
        environment="prod",
        team="agent_a",
        requires_write=True,
        strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
    )

    with pytest.raises(RuntimeError, match="knowledge_retrieval_engine_not_ready_for_cutover"):
        service.query(
            envelope=envelope,
            max_results=3,
        )


def test_graph_materializer_extracts_canonical_entities_from_entries():
    repository = SimpleNamespace(batch_upsert_graph=MagicMock(), batch_upsert_artifact_evidence=MagicMock())
    materializer = KnowledgeGraphMaterializer(repository, "AGENT_A")
    entry = KnowledgeEntry(
        id="policy-graph-1",
        title="Handle SIM-410 with billing/errors.py and payments.rollback",
        content="If BillingError appears, follow runbook SIM-410 and inspect services/payments.py.",
        layer=KnowledgeLayer.CANONICAL_POLICY,
        scope=KnowledgeScope.OPERATIONAL_POLICY,
        source_label="policy:deploy",
        source_path="/tmp/services/payments.py",
        updated_at=datetime(2026, 3, 25),
        source_type="document",
    )

    materializer.materialize_entries([entry])

    kwargs = repository.batch_upsert_graph.call_args.kwargs
    entity_keys = {item.entity_key for item in kwargs["entities"]}
    relation_keys = {item.relation_key for item in kwargs["relations"]}

    assert "issue:SIM-410" in entity_keys
    assert "path:services/payments.py" in entity_keys
    assert "symbol:payments.rollback" in entity_keys
    assert "error_signature:BillingError" in entity_keys
    assert any(key.startswith("mentions:entry:canonical_policy:policy-graph-1:issue:SIM-410") for key in relation_keys)


def test_knowledge_repository_prefers_primary_trace_reads_in_primary_mode():
    repository = KnowledgeRepository("AGENT_A")
    repository._postgres = SimpleNamespace(  # type: ignore[assignment]
        enabled=True,
        get_retrieval_trace=AsyncMock(return_value={"id": 77, "trace_role": "primary"}),
    )

    with (
        patch("koda.knowledge.repository.KNOWLEDGE_V2_STORAGE_MODE", "primary"),
    ):
        trace = repository.get_retrieval_trace(77)

    assert trace == {"id": 77, "trace_role": "primary"}


def test_knowledge_repository_fails_closed_without_primary_backend_in_primary_mode():
    repository = KnowledgeRepository("AGENT_A")
    repository._postgres = SimpleNamespace(enabled=False)  # type: ignore[assignment]

    with (
        patch("koda.knowledge.repository.KNOWLEDGE_V2_STORAGE_MODE", "primary"),
        pytest.raises(RuntimeError, match="knowledge_primary_backend_unavailable"),
    ):
        repository.get_retrieval_trace(77)


def test_knowledge_repository_upserts_graph_via_primary_backend_in_primary_mode():
    repository = KnowledgeRepository("AGENT_A")
    upsert_graph = AsyncMock(return_value=None)
    repository._postgres = SimpleNamespace(  # type: ignore[assignment]
        enabled=True,
        upsert_graph=upsert_graph,
    )
    entity = SimpleNamespace(
        entity_key="issue:SIM-410",
        agent_id="AGENT_A",
        entity_type="issue",
        label="SIM-410",
        source_kind="knowledge",
        metadata={},
    )
    relation = SimpleNamespace(
        relation_key="mentions:policy:issue:SIM-410",
        agent_id="AGENT_A",
        relation_type="MENTIONS",
        source_entity_key="source:policy:deploy",
        target_entity_key="issue:SIM-410",
        weight=1.0,
        metadata={},
    )

    with (
        patch("koda.knowledge.repository.KNOWLEDGE_V2_STORAGE_MODE", "primary"),
    ):
        repository.batch_upsert_graph(entities=[entity], relations=[relation])


def test_answer_and_judge_services_block_unsafe_write_without_citations():
    resolution = KnowledgeResolution(
        context="",
        hits=[
            _hit(
                entry_id="policy-1",
                title="Deploy Policy",
                layer=KnowledgeLayer.CANONICAL_POLICY,
                source_label="policy:deploy",
                content="Deploys in production require approval and verification.",
                similarity=0.9,
            )
        ],
        citation_requirements=[
            CitationRequirement(
                source_label="policy:deploy",
                updated_at="2026-03-25",
                layer="canonical_policy",
                required=True,
            )
        ],
        winning_sources=["policy:deploy"],
        retrieval_grounding_score=0.94,
        grounding_score=0.94,
        answer_plan={"uncertainty_level": "low"},
    )
    answer_service = KnowledgeAnswerService()
    judge_service = KnowledgeJudgeService()

    grounded_answer = answer_service.build_grounded_answer(
        response="Deployment completed successfully.",
        resolution=resolution,
    )
    judgement = judge_service.evaluate(
        grounded_answer=grounded_answer,
        resolution=resolution,
        had_write=True,
        verified_before_finalize=False,
        required_verifications=("runbook verification",),
    )

    assert grounded_answer.citations == []
    assert judgement.status == "needs_review"
    assert "missing required source citations" in judgement.reasons
    assert "required verification missing" in judgement.reasons
    assert judgement.safe_response


def test_answer_service_marks_primary_backend_unavailable_explicitly():
    resolution = KnowledgeResolution(
        context="",
        retrieval_strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        answer_plan={"uncertainty_level": "high"},
        backend_unavailable=True,
        backend_failure_reason="knowledge_primary_read_failed",
    )

    grounded_answer = KnowledgeAnswerService().build_grounded_answer(
        response="Nao foi possivel validar a acao.",
        resolution=resolution,
    )

    assert grounded_answer.operational_status == "knowledge_unavailable"
    assert grounded_answer.citations == []
    assert grounded_answer.metadata["backend_unavailable"] is True
    assert "knowledge_primary_read_failed" in grounded_answer.uncertainty_notes


def test_answer_service_includes_retrieval_engine_metadata():
    bundle = RetrievalBundle(
        normalized_query="deploy",
        query_intent="operational_execution",
        route="grpc",
        strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
    )
    plan = KnowledgeAnswerService().build_answer_plan(
        query_context=KnowledgeQueryContext(query="deploy", task_kind="deploy"),
        retrieval_bundle=bundle,
        retrieval_engine="rust_grpc",
    )
    resolution = KnowledgeResolution(
        context="",
        retrieval_strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        answer_plan=plan,
    )

    grounded = KnowledgeAnswerService().build_grounded_answer(
        response="read only response",
        resolution=resolution,
    )

    assert plan["retrieval_engine"] == "rust_grpc"
    assert grounded.metadata["retrieval_engine"] == "rust_grpc"


def test_knowledge_manager_propagates_retrieval_engine_hint_into_answer_plan():
    delegated_bundle = RetrievalBundle(
        normalized_query="deploy",
        query_intent="operational_execution",
        route="grpc",
        strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        effective_engine="rust_grpc",
        fallback_used=False,
        selected_hits=[
            _hit(
                entry_id="policy-1",
                title="Deploy Policy",
                layer=KnowledgeLayer.CANONICAL_POLICY,
                source_label="policy:deploy",
                content="Deploy requires approval and verification.",
                similarity=0.91,
            )
        ],
    )

    class _RetrievalService:
        engine_name = "rust_grpc"

        def query(self, **_kwargs: object) -> RetrievalBundle:
            return delegated_bundle

    manager = KnowledgeManager("AGENT_A", retrieval_service=_RetrievalService())  # type: ignore[arg-type]
    query_context = KnowledgeQueryContext(
        query="deploy",
        agent_id="AGENT_A",
        task_kind="deploy",
        retrieval_strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        requires_write=True,
    )
    experiment_plan = KnowledgeExperimentPlan(
        experiment_key="",
        primary_strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        persist_primary_trace=False,
    )

    with (
        patch.object(manager._storage_v2, "primary_read_enabled", return_value=True),
        patch.object(manager, "_load_guardrails", return_value=[]),
    ):
        resolution = manager._resolve_with_strategy(
            query_context=query_context,
            strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
            experiment_plan=experiment_plan,
            trace_role=TraceRole.PRIMARY,
            max_results=1,
        )

    assert resolution.answer_plan["retrieval_engine"] == "rust_grpc"


def test_knowledge_manager_preserves_authoritative_remote_bundle_without_python_dedupe():
    delegated_bundle = RetrievalBundle(
        normalized_query="deploy conflict",
        query_intent="operational_execution",
        route="grpc",
        strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        selected_hits=[
            _hit(
                entry_id="workspace-1",
                title="Deploy Policy",
                layer=KnowledgeLayer.WORKSPACE_DOC,
                source_label="workspace:deploy",
                content="Workspace-specific deploy note.",
                similarity=0.61,
            ),
            _hit(
                entry_id="policy-1",
                title="Deploy Policy",
                layer=KnowledgeLayer.CANONICAL_POLICY,
                source_label="policy:deploy",
                content="Canonical deploy policy.",
                similarity=0.96,
            ),
        ],
        trace_hits=[
            RetrievalTraceHit(
                hit_id="workspace-1",
                title="Deploy Policy",
                layer="workspace_doc",
                source_label="workspace:deploy",
                similarity=0.61,
                freshness="fresh",
                selected=True,
                rank_before=1,
                rank_after=1,
            ),
            RetrievalTraceHit(
                hit_id="policy-1",
                title="Deploy Policy",
                layer="canonical_policy",
                source_label="policy:deploy",
                similarity=0.96,
                freshness="fresh",
                selected=True,
                rank_before=2,
                rank_after=2,
            ),
        ],
        authoritative_evidence=[
            AuthoritativeEvidence(
                source_label="policy:deploy",
                layer="canonical_policy",
                title="Deploy Policy",
                excerpt="Canonical deploy policy.",
                updated_at="2026-03-25T00:00:00",
                freshness="fresh",
                score=0.96,
                operable=True,
                rationale="remote authoritative ranking",
            )
        ],
        effective_engine="rust_grpc",
        fallback_used=False,
    )

    class _RetrievalService:
        engine_name = "rust_grpc"

        def query(self, **_kwargs: object) -> RetrievalBundle:
            return delegated_bundle

    manager = KnowledgeManager("AGENT_A", retrieval_service=_RetrievalService())  # type: ignore[arg-type]
    query_context = KnowledgeQueryContext(
        query="deploy conflict",
        agent_id="AGENT_A",
        task_kind="deploy",
        retrieval_strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        requires_write=True,
    )
    experiment_plan = KnowledgeExperimentPlan(
        experiment_key="",
        primary_strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        persist_primary_trace=False,
    )
    with (
        patch.object(manager._storage_v2, "primary_read_enabled", return_value=True),
        patch.object(manager, "_load_guardrails", return_value=[]),
    ):
        resolution = manager._resolve_with_strategy(
            query_context=query_context,
            strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
            experiment_plan=experiment_plan,
            trace_role=TraceRole.PRIMARY,
            max_results=2,
        )

    assert [hit.entry.id for hit in resolution.hits] == ["workspace-1", "policy-1"]
    assert resolution.conflicts == []
    assert [hit.hit_id for hit in resolution.trace.hits] == ["workspace-1", "policy-1"]  # type: ignore[union-attr]
    assert resolution.supporting_evidence == []


@pytest.mark.asyncio
async def test_knowledge_manager_resolve_uses_remote_bundle_inputs():
    capture: dict[str, object] = {}

    class _RetrievalService:
        engine_name = "rust_grpc"

        def query(self, **kwargs: object) -> RetrievalBundle:
            capture.update(kwargs)
            return RetrievalBundle(
                normalized_query="deploy drift",
                query_intent="operational_execution",
                route="grpc",
                strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
                selected_hits=[
                    _hit(
                        entry_id="policy-1",
                        title="Deploy Policy",
                        layer=KnowledgeLayer.CANONICAL_POLICY,
                        source_label="policy:deploy",
                        content="Canonical deploy policy.",
                        similarity=0.96,
                    )
                ],
                candidate_hits=[
                    _hit(
                        entry_id="policy-1",
                        title="Deploy Policy",
                        layer=KnowledgeLayer.CANONICAL_POLICY,
                        source_label="policy:deploy",
                        content="Canonical deploy policy.",
                        similarity=0.96,
                    )
                ],
                trace_hits=[],
                effective_engine="rust_grpc",
                fallback_used=False,
            )

    manager = KnowledgeManager("AGENT_A", retrieval_service=_RetrievalService())  # type: ignore[arg-type]
    manager._initialized = True
    manager._storage_v2._postgres = SimpleNamespace(  # type: ignore[attr-defined]
        enabled=True,
        query_candidate_inputs=AsyncMock(side_effect=AssertionError("should not query candidate inputs in hot path")),
        list_graph_async=AsyncMock(side_effect=AssertionError("should not query graph in hot path")),
    )
    query_context = KnowledgeQueryContext(
        query="deploy drift",
        agent_id="AGENT_A",
        task_kind="deploy",
        project_key="billing",
        environment="prod",
        team="agent_a",
        retrieval_strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
    )
    experiment_plan = KnowledgeExperimentPlan(
        experiment_key="",
        primary_strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        persist_primary_trace=False,
    )

    with (
        patch.object(manager._experiment_service, "plan", return_value=experiment_plan),
        patch.object(manager._storage_v2, "primary_read_enabled", return_value=True),
        patch.object(manager._storage_v2, "external_read_enabled", return_value=True),
        patch.object(manager, "_load_guardrails", return_value=[]),
        patch.object(manager, "_finalize_trace_persistence", return_value=None),
    ):
        resolution = await manager.resolve(query_context, max_results=3)

    assert "candidate_hits" not in capture
    assert "candidate_source_payload" not in capture
    assert "graph_snapshot" not in capture
    manager._storage_v2._postgres.query_candidate_inputs.assert_not_awaited()
    manager._storage_v2._postgres.list_graph_async.assert_not_awaited()
    assert resolution.hits[0].entry.id == "policy-1"


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_knowledge_manager_initialize_starts_retrieval_service():
    class _RetrievalService:
        def __init__(self) -> None:
            self.started = False
            self.engine_name = "test-engine"

        async def start(self) -> None:
            self.started = True

        def health(self) -> dict[str, object]:
            return {"primary": {"service": "retrieval", "ready": True}}

    service = _RetrievalService()
    manager = KnowledgeManager("AGENT_A", retrieval_service=service)  # type: ignore[arg-type]

    with (
        patch.object(manager._storage_v2, "primary_read_enabled", return_value=True),
        patch.object(manager._storage_v2, "start_primary_backend", AsyncMock(return_value=None)),
        patch.object(manager._storage_v2, "external_read_enabled", return_value=True),
    ):
        await manager.initialize()

    assert service.started is True
    assert manager.retrieval_engine_health()["primary"]["ready"] is True


def test_knowledge_manager_disables_python_fallback_for_rust_forced_engine():
    class _RustEngine:
        engine_name = "rust_grpc"

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def query(self, **_kwargs: object) -> RetrievalBundle:
            raise RuntimeError("grpc unavailable")

        def health(self) -> dict[str, object]:
            return {
                "service": "retrieval",
                "ready": True,
                "cutover_allowed": True,
                "selection_reason": "rust-default",
            }

    manager = KnowledgeManager("AGENT_A", retrieval_engine_client=_RustEngine())  # type: ignore[arg-type]

    assert manager.retrieval_engine_health()["primary"]["selection_reason"] == "rust-default"


def test_retrieval_v2_respects_allowed_source_labels():
    class _Engine:
        engine_name = "rust_grpc"

        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def query(self, **kwargs: object) -> RetrievalBundle:
            self.calls.append(dict(kwargs))
            return RetrievalBundle(
                normalized_query="Find deploy policy and notes",
                query_intent="delegated",
                route="grpc",
                strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
                explanation="delegated to grpc engine",
            )

        def health(self) -> dict[str, object]:
            return {
                "service": "retrieval",
                "ready": True,
                "cutover_allowed": True,
                "selection_reason": "rust-default",
            }

    engine = _Engine()
    service = KnowledgeRetrievalService(engine_client=engine)
    envelope = QueryEnvelope(
        query="Find deploy policy and notes",
        normalized_query="Find deploy policy and notes",
        agent_id="AGENT_A",
        task_id=129,
        task_kind="deploy",
        project_key="billing",
        environment="prod",
        team="agent_a",
        requires_write=False,
        strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        allowed_source_labels=("policy:*",),
    )
    bundle = service.query(
        envelope=envelope,
        max_results=5,
    )

    assert bundle.query_intent == "delegated"
    assert engine.calls[0]["envelope"].allowed_source_labels == ("policy:*",)
    assert bundle.effective_engine == "rust_grpc"


@pytest.mark.asyncio
async def test_storage_v2_deferred_answer_trace_stays_remote_only_in_primary_mode():
    repository = KnowledgeRepository("AGENT_A")
    storage = KnowledgeStorageV2(repository, "AGENT_A", storage_mode="primary")
    persist_answer_trace = AsyncMock(return_value=321)
    fake_backend = SimpleNamespace(enabled=True, persist_answer_trace=persist_answer_trace)
    storage._postgres = fake_backend  # type: ignore[assignment]

    scheduled: list[asyncio.Task[object]] = []

    def _schedule(coro: object) -> None:
        scheduled.append(asyncio.create_task(cast(Coroutine[Any, Any, object], coro)))

    with patch.object(storage, "_schedule", side_effect=_schedule):
        result = storage.persist_answer_trace_deferred(
            task_id=88,
            grounded_answer=GroundedAnswer(
                answer_text="policy:deploy",
                operational_status="grounded",
                answer_plan={"uncertainty_level": "low"},
            ),
            judgement=AnswerJudgement(status="grounded"),
        )
        await asyncio.gather(*scheduled)

    assert result is None
    persist_answer_trace.assert_awaited_once()
    assert persist_answer_trace.await_args.kwargs["task_id"] == 88
    assert persist_answer_trace.await_args.kwargs["object_key"].endswith("/AGENT_A/answer_traces/88.json")


@pytest.mark.asyncio
async def test_backend_start_uses_pool_and_reports_health(monkeypatch: pytest.MonkeyPatch):
    class _AcquireContext:
        def __init__(self, conn: object) -> None:
            self._conn = conn

        async def __aenter__(self) -> object:
            return self._conn

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class _Pool:
        def __init__(self) -> None:
            self.closed = False
            self.conn = SimpleNamespace(fetchval=AsyncMock(return_value=1), fetch=AsyncMock(return_value=[]))

        def acquire(self) -> _AcquireContext:
            return _AcquireContext(self.conn)

        async def close(self) -> None:
            self.closed = True

    fake_pool = _Pool()
    backend = KnowledgeV2PostgresBackend(agent_id="AGENT_A", dsn="postgres://test", schema="knowledge_v2_test")

    async def _bootstrap() -> bool:
        backend._ready = True
        return True

    async def _load_asyncpg() -> object:
        return SimpleNamespace(create_pool=AsyncMock(return_value=fake_pool))

    backend.bootstrap = _bootstrap  # type: ignore[method-assign]
    backend._load_asyncpg = _load_asyncpg  # type: ignore[method-assign]

    assert await backend.start() is True
    health = await backend.health()

    assert health["pool_active"] is True
    assert health["check_ok"] is True
    assert health["pool_max_size"] >= health["pool_min_size"]
    assert health["acquire_timeout_ms"] > 0
    assert health["query_timeout_ms"] > 0
    assert health["pool_wait_timeout_total"] == 0
    assert health["direct_connections_in_flight"] == 0

    await backend.close()
    assert fake_pool.closed is True


@pytest.mark.asyncio
async def test_backend_health_does_not_bootstrap_unstarted_backend():
    backend = KnowledgeV2PostgresBackend(agent_id="AGENT_A", dsn="postgres://test", schema="knowledge_v2_test")
    backend.ensure_ready = AsyncMock(side_effect=AssertionError("health must not call ensure_ready"))  # type: ignore[method-assign]

    class _ConnContext:
        async def __aenter__(self) -> tuple[object, str]:
            return SimpleNamespace(fetchval=AsyncMock(return_value=1)), "direct"

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    backend._probe_connection = lambda: _ConnContext()  # type: ignore[method-assign]

    health = await backend.health()

    assert health["enabled"] is True
    assert health["check_ok"] is True
    assert health["ready"] is False
    assert health["bootstrap_state"] == "not_bootstrapped"
    assert health["probe_mode"] == "direct"
    assert health["error"] == "not_bootstrapped"
    assert health["ingest_queue"]["ready"] is False
    assert health["ingest_queue"]["reason"] == "backend_not_bootstrapped"


@pytest.mark.asyncio
async def test_postgres_backend_limits_direct_connection_fallback() -> None:
    backend = KnowledgeV2PostgresBackend(
        agent_id="AGENT_A",
        dsn="postgres://test",
        schema="knowledge_v2_test",
        pool_max_size=1,
        acquire_timeout_ms=1,
    )
    backend._ready = True
    backend._ensure_pool = AsyncMock(return_value=None)  # type: ignore[method-assign]

    await backend._direct_connection_gate.acquire()
    backend._direct_connections_in_flight = 1
    try:
        with pytest.raises(RuntimeError, match="direct postgres connection lane saturated"):
            async with backend._connection():
                raise AssertionError("connection should not be yielded")
    finally:
        backend._direct_connections_in_flight = 0
        backend._direct_connection_gate.release()

    assert backend._direct_wait_timeout_total == 1
    assert backend._last_postgres_error == "direct postgres connection lane saturated"


@pytest.mark.asyncio
async def test_ingest_queue_health_reports_degraded_when_poisoned_jobs_exist():
    backend = KnowledgeV2PostgresBackend(agent_id="AGENT_A", dsn="postgres://test", schema="knowledge_v2_test")
    backend._ready = True

    class _Conn:
        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            return [
                {"status": "ready", "count": 2, "updated_at": "2026-03-27T00:00:00+00:00"},
                {"status": "failed", "count": 1, "updated_at": "2026-03-27T00:05:00+00:00"},
            ]

        async def fetchval(self, query: str, *args: object) -> int:
            return 1

    class _ConnContext:
        async def __aenter__(self) -> tuple[object, str]:
            return _Conn(), "direct"

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    backend._probe_connection = lambda: _ConnContext()  # type: ignore[method-assign]

    health = await backend.ingest_queue_health()

    assert health["enabled"] is True
    assert health["ready"] is False
    assert health["poisoned_jobs"] == 1
    assert "poisoned_jobs" in health["degraded_reasons"]


def test_v2_storages_reuse_shared_postgres_backend():
    clear_shared_postgres_backends()
    with patch("koda.knowledge.storage_v2.KNOWLEDGE_V2_POSTGRES_DSN", "postgres://shared"):
        first = KnowledgeStorageV2(KnowledgeRepository("AGENT_A"), "AGENT_A", storage_mode="primary")
        second = KnowledgeStorageV2(KnowledgeRepository("AGENT_A"), "AGENT_A", storage_mode="primary")
    assert first._postgres is second._postgres
    clear_shared_postgres_backends()


@pytest.mark.asyncio
async def test_storage_primary_health_summary_includes_queue_and_object_store():
    clear_shared_postgres_backends()
    storage = KnowledgeStorageV2(KnowledgeRepository("AGENT_A"), "AGENT_A", storage_mode="primary")
    storage._postgres = SimpleNamespace(  # type: ignore[assignment]
        enabled=True,
        health=AsyncMock(return_value={"enabled": True, "ready": True, "pool_active": True}),
        ingest_queue_health=AsyncMock(return_value={"enabled": True, "ready": True, "queue_depth": 2}),
    )

    with patch(
        "koda.knowledge.storage_v2.object_store_health",
        return_value={"enabled": True, "ready": True, "mode": "s3"},
    ):
        summary = await storage.primary_health_summary()

    assert summary["primary_backend"]["ready"] is True
    assert summary["object_store"]["ready"] is True
    assert summary["ingest_worker"]["queue"]["queue_depth"] == 2
    clear_shared_postgres_backends()


def test_object_store_health_requires_s3_probe_when_bucket_is_enabled():
    from koda.knowledge.v2 import common

    clear_shared_postgres_backends()
    fake_client = SimpleNamespace(head_bucket=MagicMock(return_value=None))
    fake_boto3 = SimpleNamespace(client=MagicMock(return_value=fake_client))
    with (
        patch("koda.knowledge.v2.common.KNOWLEDGE_V2_S3_BUCKET", "knowledge-v2"),
        patch("koda.knowledge.v2.common.KNOWLEDGE_V2_S3_ENDPOINT_URL", "https://s3.example.test"),
        patch.dict(sys.modules, {"boto3": fake_boto3}),
    ):
        health = common.object_store_health("primary")

    assert health["enabled"] is True
    assert health["mode"] == "s3"
    assert health["local_root"] is None
    assert health["local_ready"] is None
    assert health["s3_ready"] is True
    assert health["ready"] is True
    clear_shared_postgres_backends()


def test_object_store_health_is_not_ready_without_any_sink_in_primary():
    from koda.knowledge.v2 import common

    clear_shared_postgres_backends()
    with (
        patch("koda.knowledge.v2.common.KNOWLEDGE_V2_S3_BUCKET", ""),
        patch("koda.knowledge.v2.common.KNOWLEDGE_V2_S3_ENDPOINT_URL", ""),
    ):
        health = common.object_store_health("primary")

    assert health["enabled"] is False
    assert health["mode"] == "disabled"
    assert health["ready"] is False
    assert health["error"] == "remote object storage required in primary mode"
    clear_shared_postgres_backends()


@pytest.mark.asyncio
async def test_ingest_worker_processes_artifact_derivative_batch():
    backend = SimpleNamespace(
        lease_ingest_jobs=AsyncMock(
            return_value=[
                {
                    "id": 14,
                    "task_id": 321,
                    "artifact_id": "artifact-1",
                    "job_key": "artifact-batch:321",
                    "job_type": "artifact_derivative_batch",
                    "payload_json": {
                        "object_key": "AGENT_A/artifact_derivatives/321.json",
                        "items": [
                            {
                                "derivative_key": "drv-1",
                                "artifact_id": "artifact-1",
                                "modality": "ocr",
                                "label": "Screenshot OCR",
                                "extracted_text": "deploy drift visible",
                                "confidence": 0.88,
                                "trust_level": "derived",
                                "source_path": "/tmp/shot.png",
                                "source_url": "",
                                "time_span": "",
                                "frame_ref": "",
                                "provenance": {"project_key": "billing"},
                            }
                        ],
                    },
                }
            ]
        ),
        upsert_artifact_derivatives=AsyncMock(return_value=None),
        complete_ingest_job=AsyncMock(return_value=None),
        fail_ingest_job=AsyncMock(return_value=None),
        agent_id="AGENT_A",
        schema="knowledge_v2",
    )
    worker = KnowledgeIngestWorker(backend=backend, worker_id="test-worker")

    result = await worker.run_once(limit=5)

    assert result == {"leased": 1, "completed": 1, "failed": 0}
    backend.upsert_artifact_derivatives.assert_awaited_once()
    backend.complete_ingest_job.assert_awaited_once()
    backend.fail_ingest_job.assert_not_awaited()


def test_semantic_judge_and_orchestration_block_unsupported_write_claims():
    resolution = KnowledgeResolution(
        context="",
        hits=[
            _hit(
                entry_id="policy-1",
                title="Deploy Policy",
                layer=KnowledgeLayer.CANONICAL_POLICY,
                source_label="policy:deploy",
                content="Deploy requires approval and verification before completion is confirmed.",
                similarity=0.9,
            )
        ],
        citation_requirements=[
            CitationRequirement(
                source_label="policy:deploy",
                updated_at="2026-03-25",
                layer="canonical_policy",
                required=True,
            )
        ],
        authoritative_sources=[
            AuthoritativeEvidence(
                source_label="policy:deploy",
                layer="canonical_policy",
                title="Deploy Policy",
                excerpt="Deploy requires approval and verification before completion is confirmed.",
                updated_at="2026-03-25",
                freshness="fresh",
                score=0.95,
                operable=True,
            )
        ],
        winning_sources=["policy:deploy"],
        retrieval_grounding_score=0.95,
        grounding_score=0.95,
        answer_plan={"uncertainty_level": "low"},
    )
    semantic_service = KnowledgeSemanticJudgeService()
    grounded_answer = GroundedAnswer(
        answer_text="policy:deploy confirms deployment completed successfully and the database was migrated.",
        operational_status="grounded",
        citations=[{"source_label": "policy:deploy"}],
        uncertainty_notes=[],
        answer_plan={"uncertainty_level": "low"},
    )

    report = semantic_service.evaluate(
        grounded_answer=grounded_answer,
        resolution=resolution,
        had_write=True,
    )

    assert report.requires_review is True
    assert report.unsupported_claims

    class _Storage:
        def persist_answer_trace_deferred(self, **_kwargs) -> int | None:
            return None

        def primary_read_enabled(self) -> bool:
            return True

    from koda.services.knowledge_orchestration_service import KnowledgeOrchestrationService

    service = KnowledgeOrchestrationService(_Storage())  # type: ignore[arg-type]
    grounded, judgement, evaluation, gate = service.evaluate_response(
        response=grounded_answer.answer_text,
        resolution=resolution,
        had_write=True,
        verified_before_finalize=True,
        required_verifications=(),
        task_id=101,
    )

    assert grounded.metadata["semantic_judge"]["requires_review"] is True
    assert grounded.metadata["answer_trace_pending"] is True
    assert judgement.status == "needs_review"
    assert "semantic judge found unsupported operational claims" in judgement.reasons


def test_orchestration_service_surfaces_deferred_answer_trace_failure():
    resolution = KnowledgeResolution(context="", answer_plan={"uncertainty_level": "high"})

    class _Storage:
        def persist_answer_trace_deferred(self, **_kwargs) -> int | None:
            raise RuntimeError("knowledge_primary_async_context_required")

        def primary_read_enabled(self) -> bool:
            return True

    from koda.services.knowledge_orchestration_service import KnowledgeOrchestrationService

    service = KnowledgeOrchestrationService(_Storage())  # type: ignore[arg-type]
    grounded, _judgement, _evaluation, _gate = service.evaluate_response(
        response="read only response",
        resolution=resolution,
        had_write=False,
        task_id=102,
    )

    assert grounded.metadata["answer_trace_pending"] is True
    assert grounded.metadata["answer_trace_error"] == "knowledge_primary_async_context_required"


@pytest.mark.asyncio
async def test_storage_v2_primary_reads_answer_trace_from_backend():
    repository = KnowledgeRepository("AGENT_A")
    storage = KnowledgeStorageV2(repository, "AGENT_A", storage_mode="primary")

    class _FakeBackend:
        enabled = True
        bootstrapped = True

        async def get_latest_answer_trace(self, task_id: int) -> dict[str, object] | None:
            return {
                "id": 7,
                "task_id": task_id,
                "answer_text": "Primary answer trace",
                "judge_result": {"status": "passed"},
                "authoritative_sources": [{"source_label": "policy:deploy"}],
            }

    fake = _FakeBackend()
    storage._postgres = fake  # type: ignore[assignment]

    answer_trace = await storage.get_latest_answer_trace_async(321)

    assert answer_trace is not None
    assert answer_trace["answer_text"] == "Primary answer trace"
    assert answer_trace["judge_result"]["status"] == "passed"


@pytest.mark.asyncio
async def test_storage_v2_primary_reads_fail_closed_when_backend_not_bootstrapped():
    repository = KnowledgeRepository("AGENT_A")
    storage = KnowledgeStorageV2(repository, "AGENT_A", storage_mode="primary")
    fake = SimpleNamespace(enabled=True, bootstrapped=False)
    storage._postgres = fake  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="knowledge_primary_backend_unavailable"):
        await storage.get_latest_answer_trace_async(321)


@pytest.mark.asyncio
async def test_postgres_backend_upsert_documents_uses_stable_content_hash(monkeypatch: pytest.MonkeyPatch):
    captured_rows: list[tuple[object, ...]] = []

    class _Conn:
        async def executemany(self, query: str, rows: list[tuple[object, ...]]) -> None:
            if '"knowledge_documents"' in query:
                captured_rows.extend(rows)

        async def close(self) -> None:
            return None

    async def _connect(_dsn: str) -> _Conn:
        return _Conn()

    monkeypatch.setitem(sys.modules, "asyncpg", SimpleNamespace(connect=_connect))
    backend = KnowledgeV2PostgresBackend(agent_id="AGENT_A", dsn="postgres://test", schema="knowledge_v2_test")
    backend._ready = True

    entry = KnowledgeEntry(
        id="policy-1",
        title="Deploy Policy",
        content="Canonical deploy policy content.",
        layer=KnowledgeLayer.CANONICAL_POLICY,
        scope=KnowledgeScope.OPERATIONAL_POLICY,
        source_label="policy:deploy",
        source_path="/tmp/policy.md",
        updated_at=datetime(2026, 3, 25),
    )

    await backend.upsert_documents([entry], object_key="AGENT_A/knowledge_documents/latest.json")

    assert captured_rows
    assert captured_rows[0][18] == hashlib.sha256(entry.content.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_postgres_backend_lists_trace_hits_with_single_connection(monkeypatch: pytest.MonkeyPatch):
    connect_calls = 0

    class _Conn:
        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            if '"retrieval_traces"' in query:
                return [
                    {
                        "id": 11,
                        "agent_id": "AGENT_A",
                        "task_id": 501,
                        "query_text": "deploy policy",
                        "strategy": "langgraph_current",
                        "route": "local",
                        "project_key": "billing",
                        "environment": "prod",
                        "team": "agent_a",
                        "graph_hops": 1,
                        "grounding_score": 0.9,
                        "required_citation_count": 1,
                        "conflict_reasons_json": [],
                        "evidence_modalities_json": ["text"],
                        "winning_sources_json": ["policy:deploy"],
                        "explanation": "",
                        "experiment_key": "exp-1",
                        "trace_role": "primary",
                        "paired_trace_id": None,
                        "created_at": datetime(2026, 3, 25),
                    },
                    {
                        "id": 12,
                        "agent_id": "AGENT_A",
                        "task_id": 502,
                        "query_text": "runbook verification",
                        "strategy": "langgraph_current",
                        "route": "local",
                        "project_key": "billing",
                        "environment": "prod",
                        "team": "agent_a",
                        "graph_hops": 0,
                        "grounding_score": 0.8,
                        "required_citation_count": 1,
                        "conflict_reasons_json": [],
                        "evidence_modalities_json": ["text"],
                        "winning_sources_json": ["runbook:billing"],
                        "explanation": "",
                        "experiment_key": "exp-1",
                        "trace_role": "primary",
                        "paired_trace_id": 11,
                        "created_at": datetime(2026, 3, 25),
                    },
                ]
            if '"retrieval_trace_hits"' in query:
                return [
                    {
                        "trace_id": 11,
                        "hit_id": "policy-1",
                        "title": "Deploy Policy",
                        "layer": "canonical_policy",
                        "source_label": "policy:deploy",
                        "similarity": 0.91,
                        "freshness": "fresh",
                        "selected": True,
                        "rank_before": 0,
                        "rank_after": 0,
                        "graph_hops": 1,
                        "graph_score": 0.12,
                        "reasons_json": ["lexical_retrieval"],
                        "exclusion_reason": "",
                        "evidence_modalities_json": ["text"],
                        "supporting_evidence_keys_json": [],
                    },
                    {
                        "trace_id": 12,
                        "hit_id": "runbook-1",
                        "title": "Billing Runbook",
                        "layer": "approved_runbook",
                        "source_label": "runbook:billing",
                        "similarity": 0.82,
                        "freshness": "fresh",
                        "selected": True,
                        "rank_before": 0,
                        "rank_after": 0,
                        "graph_hops": 0,
                        "graph_score": 0.0,
                        "reasons_json": ["dense_retrieval"],
                        "exclusion_reason": "",
                        "evidence_modalities_json": ["text"],
                        "supporting_evidence_keys_json": [],
                    },
                ]
            raise AssertionError(query)

        async def close(self) -> None:
            return None

    async def _connect(_dsn: str) -> _Conn:
        nonlocal connect_calls
        connect_calls += 1
        return _Conn()

    monkeypatch.setitem(sys.modules, "asyncpg", SimpleNamespace(connect=_connect))
    backend = KnowledgeV2PostgresBackend(agent_id="AGENT_A", dsn="postgres://test", schema="knowledge_v2_test")
    backend._ready = True

    traces = await backend.list_retrieval_traces(limit=10)

    assert connect_calls == 1
    assert len(traces) == 2
    assert traces[0]["hits"]
    assert traces[1]["hits"]


@pytest.mark.asyncio
async def test_postgres_backend_gets_retrieval_trace_by_id_directly(monkeypatch: pytest.MonkeyPatch):
    class _Conn:
        def __init__(self) -> None:
            self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []

        async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
            self.fetchrow_calls.append((query, args))
            return {
                "id": 999,
                "agent_id": "AGENT_A",
                "task_id": 600,
                "query_text": "deploy policy",
                "strategy": "langgraph_current",
                "route": "local",
                "project_key": "billing",
                "environment": "prod",
                "team": "agent_a",
                "graph_hops": 1,
                "grounding_score": 0.92,
                "required_citation_count": 1,
                "conflict_reasons_json": [],
                "evidence_modalities_json": ["text"],
                "winning_sources_json": ["policy:deploy"],
                "explanation": "",
                "experiment_key": "exp-2",
                "trace_role": "primary",
                "paired_trace_id": None,
                "created_at": datetime(2026, 3, 25),
            }

        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            if '"retrieval_trace_hits"' in query:
                return [
                    {
                        "trace_id": 999,
                        "hit_id": "policy-1",
                        "title": "Deploy Policy",
                        "layer": "canonical_policy",
                        "source_label": "policy:deploy",
                        "similarity": 0.91,
                        "freshness": "fresh",
                        "selected": True,
                        "rank_before": 0,
                        "rank_after": 0,
                        "graph_hops": 1,
                        "graph_score": 0.1,
                        "reasons_json": ["lexical_retrieval"],
                        "exclusion_reason": "",
                        "evidence_modalities_json": ["text"],
                        "supporting_evidence_keys_json": [],
                    }
                ]
            raise AssertionError(query)

        async def close(self) -> None:
            return None

    conn = _Conn()

    async def _connect(_dsn: str) -> _Conn:
        return conn

    monkeypatch.setitem(sys.modules, "asyncpg", SimpleNamespace(connect=_connect))
    backend = KnowledgeV2PostgresBackend(agent_id="AGENT_A", dsn="postgres://test", schema="knowledge_v2_test")
    backend._ready = True

    trace = await backend.get_retrieval_trace(999)

    assert trace is not None
    assert trace["id"] == 999
    assert conn.fetchrow_calls
    assert conn.fetchrow_calls[0][1] == ("AGENT_A", 999)


@pytest.mark.asyncio
async def test_knowledge_runtime_supervisor_reports_worker_health():
    storage = SimpleNamespace(
        external_read_enabled=lambda: True,
        start_primary_backend=AsyncMock(return_value=True),
        close_primary_backend=AsyncMock(return_value=None),
        primary_health_summary=AsyncMock(
            return_value={
                "storage_mode": "primary",
                "primary_backend": {"enabled": True, "ready": True, "pool_active": True},
                "object_store": {"enabled": True, "ready": True},
            }
        ),
        _postgres=SimpleNamespace(),
    )
    supervisor = KnowledgeRuntimeSupervisor(agent_id="AGENT_A", storage=storage)

    with patch("koda.knowledge.runtime_supervisor.KNOWLEDGE_V2_INGEST_WORKER_ENABLED", False):
        assert await supervisor.start() is True
        health = await supervisor.health()
        await supervisor.close()

    assert health["started"] is True
    assert health["ready"] is True
    storage.start_primary_backend.assert_awaited_once()
    storage.close_primary_backend.assert_awaited_once()


@pytest.mark.asyncio
async def test_knowledge_runtime_supervisor_fails_closed_when_primary_backend_does_not_start():
    storage = SimpleNamespace(
        external_read_enabled=lambda: True,
        start_primary_backend=AsyncMock(return_value=False),
        close_primary_backend=AsyncMock(return_value=None),
        primary_health_summary=AsyncMock(return_value={"primary_backend": {"enabled": True, "ready": False}}),
        _postgres=SimpleNamespace(),
    )
    supervisor = KnowledgeRuntimeSupervisor(agent_id="AGENT_A", storage=storage)

    with patch("koda.knowledge.runtime_supervisor.KNOWLEDGE_V2_INGEST_WORKER_ENABLED", False):
        started = await supervisor.start()
        health = await supervisor.health()

    assert started is False
    assert health["started"] is False
    assert health["ready"] is False
    storage.start_primary_backend.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_completes_when_the_deferred_trace_write_fails():
    """Characterises today's fire-and-forget knowledge write (TD-086, M4-E1-T6).

    In PRIMARY mode the retrieval trace is written by a detached task. When
    that write fails, the turn still gets its resolution, the trace id stays
    ``None``, and the failure exists only on the detached task: nothing
    awaits it, so nothing reports it. M7-E1-T7 changes this to a visible
    error; until then this test pins the current behaviour.
    """

    class _RetrievalService:
        engine_name = "rust_grpc"

        def query(self, **_kwargs: object) -> RetrievalBundle:
            return RetrievalBundle(
                normalized_query="deploy",
                query_intent="operational_execution",
                route="grpc",
                strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
                selected_hits=[
                    _hit(
                        entry_id="policy-1",
                        title="Deploy Policy",
                        layer=KnowledgeLayer.CANONICAL_POLICY,
                        source_label="policy:deploy",
                        content="Deploy requires approval.",
                        similarity=0.93,
                    )
                ],
                effective_engine="rust_grpc",
                fallback_used=False,
            )

    write_error = RuntimeError("knowledge primary write failed")
    failing_write = AsyncMock(side_effect=write_error)
    manager = KnowledgeManager("AGENT_A", retrieval_service=_RetrievalService())  # type: ignore[arg-type]
    manager._initialized = True
    manager._storage_v2._postgres = SimpleNamespace(  # type: ignore[assignment]
        enabled=True,
        bootstrapped=True,
        persist_retrieval_trace=failing_write,
    )
    experiment_plan = KnowledgeExperimentPlan(
        experiment_key="",
        primary_strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
        persist_primary_trace=True,
    )
    query_context = KnowledgeQueryContext(
        query="deploy",
        task_id=4242,
        agent_id="AGENT_A",
        task_kind="deploy",
        retrieval_strategy=RetrievalStrategy.LANGGRAPH_CURRENT,
    )
    tasks_before = asyncio.all_tasks()

    with (
        patch.object(manager._experiment_service, "plan", return_value=experiment_plan),
        patch.object(manager._storage_v2, "primary_read_enabled", return_value=True),
        patch.object(manager._storage_v2, "external_read_enabled", return_value=True),
        patch.object(manager, "_load_guardrails", return_value=[]),
    ):
        resolution = await manager.resolve(query_context)

    detached = list(asyncio.all_tasks() - tasks_before)
    outcomes = await asyncio.gather(*detached, return_exceptions=True)

    assert [hit.entry.id for hit in resolution.hits] == ["policy-1"]
    assert resolution.trace is not None
    assert resolution.trace_id is None
    assert resolution.trace.trace_id is None
    failing_write.assert_awaited_once()
    assert failing_write.await_args.kwargs["trace"] is resolution.trace
    assert outcomes == [write_error]


@pytest.mark.asyncio
async def test_evaluate_response_completes_when_the_deferred_answer_trace_write_fails():
    """Characterises the turn's other fire-and-forget write (TD-086, M4-E1-T6).

    ``persist_answer_trace_deferred`` hands the answer-trace write to
    ``KnowledgeStorageV2._schedule``. When that detached write fails, the
    response evaluation still returns, the trace is reported as pending with
    no error and no id, and the failure exists only on the detached task.
    M7-E1-T7 changes this to a visible error.
    """
    from koda.services.knowledge_orchestration_service import KnowledgeOrchestrationService

    write_error = RuntimeError("knowledge primary write failed")
    failing_write = AsyncMock(side_effect=write_error)
    storage = KnowledgeStorageV2(KnowledgeRepository("AGENT_A"), "AGENT_A", storage_mode="primary")
    storage._postgres = SimpleNamespace(  # type: ignore[assignment]
        enabled=True,
        bootstrapped=True,
        persist_answer_trace=failing_write,
    )
    service = KnowledgeOrchestrationService(storage)
    resolution = KnowledgeResolution(context="", answer_plan={"uncertainty_level": "high"})
    tasks_before = asyncio.all_tasks()

    grounded, _judgement, _evaluation, _gate = service.evaluate_response(
        response="read only response",
        resolution=resolution,
        had_write=False,
        task_id=103,
    )

    detached = list(asyncio.all_tasks() - tasks_before)
    outcomes = await asyncio.gather(*detached, return_exceptions=True)

    assert grounded.metadata["answer_trace_pending"] is True
    assert "answer_trace_error" not in grounded.metadata
    assert "answer_trace_id" not in grounded.metadata
    failing_write.assert_awaited_once()
    assert failing_write.await_args.kwargs["task_id"] == 103
    assert outcomes == [write_error]


class _GovernanceWrites:
    """Records the SQL the knowledge governance store would run."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def run(self, call: tuple[str, str]) -> list[Any] | None:
        kind, sql = call
        self.statements.append(sql)
        return [] if kind == "fetch" else None

    def source_registrations(self) -> list[str]:
        return [sql for sql in self.statements if "INSERT INTO knowledge_source_registry" in sql]


@pytest.fixture
def off_storage_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[_GovernanceWrites]:
    """Select KNOWLEDGE_V2_STORAGE_MODE=off, as knowledge_policy.storage_mode can.

    Governance-store SQL is recorded instead of run, and the repository's
    graph and artifact-evidence writers are replaced with mocks.
    """
    import koda.state.knowledge_governance_store as governance_store

    clear_shared_postgres_backends()
    monkeypatch.setattr("koda.knowledge.storage_v2.KNOWLEDGE_V2_STORAGE_MODE", "off")
    monkeypatch.setattr("koda.knowledge.repository.KNOWLEDGE_V2_STORAGE_MODE", "off")
    monkeypatch.setattr("koda.knowledge.manager.KNOWLEDGE_ENABLED", True)
    monkeypatch.setattr("koda.knowledge.manager.KNOWLEDGE_MULTIMODAL_GRAPH_ENABLED", True)
    writes = _GovernanceWrites()
    monkeypatch.setattr(governance_store, "_primary_enabled", lambda _agent_id=None: True)
    monkeypatch.setattr(governance_store, "primary_execute", lambda sql, *_a, **_k: ("execute", sql))
    monkeypatch.setattr(governance_store, "primary_fetch_all", lambda sql, *_a, **_k: ("fetch", sql))
    monkeypatch.setattr(governance_store, "run_coro_sync", writes.run)
    monkeypatch.setattr(KnowledgeRepository, "batch_upsert_graph", MagicMock(name="batch_upsert_graph"))
    monkeypatch.setattr(
        KnowledgeRepository,
        "batch_upsert_artifact_evidence",
        MagicMock(name="batch_upsert_artifact_evidence"),
    )
    yield writes
    clear_shared_postgres_backends()


class _NoStartRetrieval:
    engine_name = "rust_grpc"

    def query(self, **_kwargs: object) -> RetrievalBundle:
        raise AssertionError("OFF mode never reaches the retrieval engine")


@pytest.mark.asyncio
async def test_off_mode_initialize_registers_no_knowledge_pack_source(
    off_storage_mode: _GovernanceWrites, monkeypatch: pytest.MonkeyPatch
):
    """M4-E1-T6 removed the OFF-mode pack loader: KNOWLEDGE_PACK_TOML no longer
    registers a ``pack:<id>`` source or writes graph rows (needs operator sign-off)."""
    monkeypatch.setenv(
        "KNOWLEDGE_PACK_TOML",
        'pack_id = "ops"\nowner = "sre"\n'
        '[[entries]]\nid = "deploy"\ntitle = "Deploy"\ncontent = "Deploy needs approval."\n',
    )
    manager = KnowledgeManager("AGENT_A", retrieval_service=_NoStartRetrieval())  # type: ignore[arg-type]

    await manager.initialize()

    assert manager.initialized is True
    assert not manager._storage_v2.primary_read_enabled()
    assert off_storage_mode.source_registrations() == []
    cast(MagicMock, KnowledgeRepository.batch_upsert_graph).assert_not_called()


@pytest.mark.asyncio
async def test_off_mode_resolve_raises_without_registering_workspace_sources(
    off_storage_mode: _GovernanceWrites, tmp_path: Any
):
    """In OFF mode resolve raises as before, but no longer registers
    ``workspace:<path>`` sources first (needs operator sign-off)."""
    (tmp_path / "README.md").write_text("# Deploy\nDeploys need approval.\n", encoding="utf-8")
    manager = KnowledgeManager("AGENT_A", retrieval_service=_NoStartRetrieval())  # type: ignore[arg-type]
    await manager.initialize()

    with pytest.raises(RuntimeError, match="knowledge_retrieval_engine_not_authoritative"):
        await manager.resolve(
            KnowledgeQueryContext(
                query="deploy approval",
                agent_id="AGENT_A",
                task_id=7,
                task_kind="deploy",
                workspace_dir=str(tmp_path),
            )
        )

    assert off_storage_mode.source_registrations() == []


@pytest.mark.asyncio
async def test_off_mode_artifact_ingest_writes_no_evidence_rows(off_storage_mode: _GovernanceWrites):
    """In OFF mode an artifact dossier no longer produces artifact_evidence_nodes
    or graph rows (needs operator sign-off)."""
    artifact = SimpleNamespace(
        ref=SimpleNamespace(kind="pdf", label="invoice.pdf", path="/tmp/invoice.pdf", url="", artifact_id="art-1"),
        summary="Invoice total 42",
        evidence_chunks=[SimpleNamespace(citation="invoice.pdf p1", excerpt="Invoice total 42", score_hint=0.8)],
        metadata={},
        status=SimpleNamespace(value="ready"),
        critical_for_action=False,
    )
    dossier = SimpleNamespace(subject_id="msg-1", subject_label="PDF upload", summary="one pdf", artifacts=[artifact])
    manager = KnowledgeManager("AGENT_A", retrieval_service=_NoStartRetrieval())  # type: ignore[arg-type]
    await manager.initialize()

    nodes = await manager.ingest_artifact_dossiers(
        KnowledgeQueryContext(query="read the invoice", agent_id="AGENT_A", task_id=8),
        [dossier],
    )

    assert nodes == []
    cast(MagicMock, KnowledgeRepository.batch_upsert_artifact_evidence).assert_not_called()
    cast(MagicMock, KnowledgeRepository.batch_upsert_graph).assert_not_called()


@pytest.mark.asyncio
async def test_off_mode_artifact_evidence_read_returns_no_rows(off_storage_mode: _GovernanceWrites):
    """Nothing writes artifact_evidence_nodes any more, so the OFF-mode read
    returns no rows instead of querying that table (needs operator sign-off)."""
    repository = KnowledgeRepository("AGENT_A")
    storage = KnowledgeStorageV2(repository, "AGENT_A")
    stale_row = {"evidence_key": "old", "label": "invoice.pdf p1"}

    with patch.object(repository, "list_artifact_evidence", return_value=[stale_row]) as legacy_read:
        rows = await storage.list_artifact_evidence_rows_async(
            task_id=None,
            project_key="",
            workspace_fingerprint="",
        )

    assert rows == []
    legacy_read.assert_not_called()


@pytest.mark.asyncio
async def test_initialize_logs_only_the_backend_state():
    """``knowledge_initialized`` carries no constant fields."""
    manager = KnowledgeManager("AGENT_A", retrieval_service=_NoStartRetrieval())  # type: ignore[arg-type]

    with (
        patch("koda.knowledge.manager.KNOWLEDGE_ENABLED", True),
        patch.object(manager._storage_v2, "primary_read_enabled", return_value=True),
        patch.object(manager._storage_v2, "external_read_enabled", return_value=True),
        patch.object(manager._storage_v2, "start_primary_backend", AsyncMock(return_value=True)),
        patch("koda.knowledge.manager.log") as log,
    ):
        await manager.initialize()

    log.info.assert_called_once_with("knowledge_initialized", primary_backend=True)


def test_dead_knowledge_paths_are_removed():
    """M4-E1-T6: the local/OFF retrieval path, the store wrappers and the
    uncalled evaluation helpers are gone."""
    import importlib.util
    import inspect

    from koda.knowledge import evaluation, manager, storage_v2
    from koda.knowledge.v2 import common

    for module in ("artifact", "document", "embedding", "evaluation", "graph", "trace"):
        assert importlib.util.find_spec(f"koda.knowledge.v2.{module}_store") is None, module
    assert not hasattr(common, "V2StoreSupport")
    assert not hasattr(common, "KnowledgeBackendLifecycle")
    for name in (
        "_load_pack_entries",
        "_load_workspace_entries",
        "_load_approved_runbook_entries",
        "_load_observed_pattern_entries",
        "_get_model",
        "_embed_batch",
        "_build_artifact_graph_relations",
    ):
        assert not hasattr(manager.KnowledgeManager, name), name
    # Arguments and imports that only fed the removed paths.
    assert "persist_trace" not in inspect.signature(manager.KnowledgeManager._resolve_with_strategy).parameters
    assert "supporting_evidence" not in inspect.signature(manager.KnowledgeManager._render_context).parameters
    assert not hasattr(manager, "ArtifactEvidenceMatch")
    for name in ("persist_entries", "persist_artifact_derivatives", "persist_retrieval_bundle"):
        assert not hasattr(storage_v2.KnowledgeStorageV2, name), name
    for name in (
        "citation_coverage_from_response",
        "evaluate_runtime_answer",
        "score_resolution_against_case",
        "compare_replay_results",
        "build_benchmark_summary",
        "replay_case",
    ):
        assert not hasattr(evaluation, name), name
