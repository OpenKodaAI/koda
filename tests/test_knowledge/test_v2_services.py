"""Tests for retrieval v2, grounded answer services, and storage v2."""

from __future__ import annotations

import asyncio
import hashlib
import sys
from collections.abc import Coroutine
from datetime import datetime
from pathlib import Path
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
    ArtifactDerivative,
    AuthoritativeEvidence,
    CitationRequirement,
    EvidenceModality,
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
from koda.knowledge.v2.artifact_store import ArtifactStore
from koda.knowledge.v2.common import clear_shared_postgres_backends
from koda.knowledge.v2.document_store import KnowledgeDocumentStore
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


def test_knowledge_manager_ignores_prompt_assets_during_workspace_scan(tmp_path: Path):
    manager = KnowledgeManager("AGENT_A")
    docs_dir = tmp_path / "docs"
    prompts_dir = tmp_path / "prompts"
    docs_dir.mkdir()
    prompts_dir.mkdir()
    allowed_doc = docs_dir / "ops.md"
    prompt_asset = prompts_dir / "agent_a.md"
    allowed_doc.write_text("# Ops\nCanonical deployment notes.", encoding="utf-8")
    prompt_asset.write_text("# Prompt\nAgent behavior asset.", encoding="utf-8")

    files = manager._iter_source_files(tmp_path, ["docs/**/*.md", "prompts/*.md"], 8)

    assert allowed_doc in files
    assert prompt_asset not in files


def test_knowledge_manager_skips_inline_pack_seed_when_external_storage_is_enabled(monkeypatch: pytest.MonkeyPatch):
    manager = KnowledgeManager("AGENT_A")
    inline_pack = """
pack_id = "legacy-pack"

[[entries]]
id = "seed-1"
title = "Legacy"
content = "Should not be loaded when primary or external storage is active."
"""
    monkeypatch.setenv("KNOWLEDGE_PACK_TOML", inline_pack)

    with patch.object(manager._storage_v2, "external_read_enabled", return_value=True):
        assert manager._load_pack_entries() == []


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


def test_storage_v2_persists_remote_payloads_in_primary_mode(tmp_path: Path):
    store_root = tmp_path / "knowledge_v2"
    repository = KnowledgeRepository("AGENT_A")
    storage = KnowledgeStorageV2(repository, "AGENT_A", storage_mode="primary", object_store_root=str(store_root))
    storage._postgres = SimpleNamespace(  # type: ignore[assignment]
        enabled=True,
        bootstrapped=True,
        persist_retrieval_bundle=AsyncMock(return_value=None),
    )
    storage._documents._postgres = storage._postgres  # type: ignore[assignment]
    storage._embeddings._postgres = storage._postgres  # type: ignore[assignment]
    storage._traces._postgres = storage._postgres  # type: ignore[assignment]
    storage._graph._postgres = storage._postgres  # type: ignore[assignment]
    storage._artifacts._postgres = storage._postgres  # type: ignore[assignment]
    storage._traces.schedule = lambda coro: coro.close()  # type: ignore[method-assign]
    storage.persist_retrieval_bundle(
        task_id=77,
        payload={"strategy": "langgraph_current", "winning_sources": ["policy:deploy"]},
    )

    persisted = store_root / "AGENT_A" / "retrieval_bundles" / "77.json"
    storage._postgres.persist_retrieval_bundle.assert_called_once()
    assert not persisted.exists()


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
            hits=delegated_bundle.selected_hits,
            max_results=1,
            persist_trace=False,
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
            hits=delegated_bundle.selected_hits,
            max_results=2,
            persist_trace=False,
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
        patch.object(manager, "_get_model", AsyncMock(return_value=object())),
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


def test_artifact_store_prefers_ingest_job_when_worker_enabled(tmp_path: Path):
    store = ArtifactStore(agent_id="AGENT_A", storage_mode="primary", object_store_root=str(tmp_path))
    store._postgres = SimpleNamespace(
        enabled=True,
        bootstrapped=True,
        enqueue_ingest_job=AsyncMock(return_value=None),
        upsert_artifact_derivatives=AsyncMock(return_value=None),
    )
    store.schedule = MagicMock(side_effect=lambda coro: getattr(coro, "close", lambda: None)())
    derivatives = [
        ArtifactDerivative(
            derivative_key="deriv-1",
            artifact_id="artifact-1",
            modality=EvidenceModality.OCR,
            label="OCR chunk",
            extracted_text="deploy approval present",
            confidence=0.92,
            source_path="/tmp/source.png",
        )
    ]

    with (
        patch("koda.knowledge.v2.artifact_store.KNOWLEDGE_V2_INGEST_WORKER_ENABLED", True),
        patch("koda.knowledge.v2.artifact_store.schedule_ingest_worker_drain") as schedule_drain,
    ):
        store.persist_derivatives(task_id=44, derivatives=derivatives)

    store._postgres.enqueue_ingest_job.assert_called_once()
    store._postgres.upsert_artifact_derivatives.assert_not_called()
    schedule_drain.assert_called_once()
    assert not (tmp_path / "AGENT_A" / "artifact_derivatives" / "44.json").exists()


def test_artifact_store_skips_primary_write_until_backend_bootstrapped(tmp_path: Path):
    store = ArtifactStore(agent_id="AGENT_A", storage_mode="primary", object_store_root=str(tmp_path))
    store._postgres = SimpleNamespace(
        enabled=True,
        bootstrapped=False,
        enqueue_ingest_job=AsyncMock(return_value=None),
        upsert_artifact_derivatives=AsyncMock(return_value=None),
    )
    store.schedule = MagicMock(side_effect=lambda coro: getattr(coro, "close", lambda: None)())
    derivatives = [
        ArtifactDerivative(
            derivative_key="deriv-1",
            artifact_id="artifact-1",
            modality=EvidenceModality.OCR,
            label="OCR chunk",
            extracted_text="deploy approval present",
            confidence=0.92,
            source_path="/tmp/source.png",
        )
    ]

    with (
        patch("koda.knowledge.v2.artifact_store.KNOWLEDGE_V2_INGEST_WORKER_ENABLED", True),
        patch("koda.knowledge.v2.artifact_store.schedule_ingest_worker_drain") as schedule_drain,
    ):
        store.persist_derivatives(task_id=44, derivatives=derivatives)

    store._postgres.enqueue_ingest_job.assert_not_called()
    store._postgres.upsert_artifact_derivatives.assert_not_called()
    schedule_drain.assert_not_called()


def test_storage_v2_persists_retrieval_trace_synchronously_in_primary_mode(tmp_path: Path):
    repository = KnowledgeRepository("AGENT_A")
    storage = KnowledgeStorageV2(
        repository,
        "AGENT_A",
        storage_mode="primary",
        object_store_root=str(tmp_path / "knowledge_v2"),
    )

    trace = SimpleNamespace(
        agent_id="AGENT_A",
        task_id=501,
        query="deploy policy",
        strategy=SimpleNamespace(value="langgraph_current"),
        route="primary",
        project_key="billing",
        environment="prod",
        team="agent_a",
        graph_hops=1,
        grounding_score=0.9,
        required_citation_count=1,
        conflict_reasons=(),
        evidence_modalities=(),
        winning_sources=("policy:deploy",),
        explanation="primary trace",
        experiment_key="exp-1",
        trace_role=SimpleNamespace(value="primary"),
        paired_trace_id=None,
        hits=[
            SimpleNamespace(
                hit_id="hit-1",
                title="Deploy Policy",
                layer="canonical_policy",
                source_label="policy:deploy",
                similarity=0.92,
                freshness="fresh",
                selected=True,
                rank_before=1,
                rank_after=1,
                graph_hops=1,
                graph_score=0.4,
                reasons=("authoritative",),
                exclusion_reason="",
                evidence_modalities=(),
                supporting_evidence_keys=(),
            )
        ],
        to_dict=lambda: {"query": "deploy policy"},
    )

    fake_backend = SimpleNamespace(
        enabled=True,
        bootstrapped=True,
        persist_retrieval_trace=AsyncMock(return_value=88),
    )
    storage._postgres = fake_backend  # type: ignore[assignment]
    storage._documents._postgres = fake_backend  # type: ignore[assignment]
    storage._embeddings._postgres = fake_backend  # type: ignore[assignment]
    storage._traces._postgres = fake_backend  # type: ignore[assignment]
    storage._graph._postgres = fake_backend  # type: ignore[assignment]
    storage._artifacts._postgres = fake_backend  # type: ignore[assignment]

    trace_id = storage.persist_retrieval_trace(trace=trace, sampled=True)

    assert trace_id == 88


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
async def test_storage_v2_deferred_answer_trace_stays_remote_only_in_primary_mode(tmp_path: Path):
    repository = KnowledgeRepository("AGENT_A")
    storage = KnowledgeStorageV2(
        repository,
        "AGENT_A",
        storage_mode="primary",
        object_store_root=str(tmp_path / "knowledge_v2"),
    )
    persist_answer_trace = AsyncMock(return_value=321)
    fake_backend = SimpleNamespace(enabled=True, persist_answer_trace=persist_answer_trace)
    storage._postgres = fake_backend  # type: ignore[assignment]
    storage._documents._postgres = fake_backend  # type: ignore[assignment]
    storage._embeddings._postgres = fake_backend  # type: ignore[assignment]
    storage._traces._postgres = fake_backend  # type: ignore[assignment]
    storage._graph._postgres = fake_backend  # type: ignore[assignment]
    storage._artifacts._postgres = fake_backend  # type: ignore[assignment]

    scheduled: list[asyncio.Task[object]] = []

    def _schedule(coro: object) -> None:
        scheduled.append(asyncio.create_task(cast(Coroutine[Any, Any, object], coro)))

    with (
        patch.object(storage._traces, "schedule", side_effect=_schedule),
        patch.object(
            storage._traces,
            "write_local_payload",
            side_effect=AssertionError("local payload should not be written in primary mode"),
        ),
    ):
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


def test_v2_stores_reuse_shared_postgres_backend(tmp_path: Path):
    clear_shared_postgres_backends()
    with patch("koda.knowledge.v2.common.KNOWLEDGE_V2_POSTGRES_DSN", "postgres://shared"):
        documents = KnowledgeDocumentStore(agent_id="AGENT_A", storage_mode="primary", object_store_root=str(tmp_path))
        artifacts = ArtifactStore(agent_id="AGENT_A", storage_mode="primary", object_store_root=str(tmp_path))
    assert documents._postgres is artifacts._postgres
    clear_shared_postgres_backends()


@pytest.mark.asyncio
async def test_storage_primary_health_summary_includes_queue_and_object_store(tmp_path: Path):
    clear_shared_postgres_backends()
    storage = KnowledgeStorageV2(
        KnowledgeRepository("AGENT_A"),
        "AGENT_A",
        storage_mode="primary",
        object_store_root=str(tmp_path),
    )
    storage.external_read_enabled = lambda: True  # type: ignore[method-assign]
    storage.primary_read_enabled = lambda: True  # type: ignore[method-assign]
    storage._documents.backend_lifecycle.health = AsyncMock(  # type: ignore[method-assign]
        return_value={"enabled": True, "ready": True, "pool_active": True}
    )
    storage._documents.object_store_health = MagicMock(  # type: ignore[method-assign]
        return_value={"enabled": True, "ready": True, "mode": "local"}
    )
    storage.ingest_queue_health = AsyncMock(  # type: ignore[method-assign]
        return_value={"enabled": True, "ready": True, "queue_depth": 2}
    )

    summary = await storage.primary_health_summary()

    assert summary["primary_backend"]["ready"] is True
    assert summary["object_store"]["ready"] is True
    assert summary["ingest_worker"]["queue"]["queue_depth"] == 2
    clear_shared_postgres_backends()


def test_object_store_health_requires_s3_probe_when_bucket_is_enabled(tmp_path: Path):
    clear_shared_postgres_backends()
    fake_client = SimpleNamespace(head_bucket=MagicMock(return_value=None))
    fake_boto3 = SimpleNamespace(client=MagicMock(return_value=fake_client))
    with (
        patch("koda.knowledge.v2.common.KNOWLEDGE_V2_S3_BUCKET", "knowledge-v2"),
        patch("koda.knowledge.v2.common.KNOWLEDGE_V2_S3_ENDPOINT_URL", "https://s3.example.test"),
        patch.dict(sys.modules, {"boto3": fake_boto3}),
    ):
        store = KnowledgeDocumentStore(agent_id="AGENT_A", storage_mode="primary", object_store_root=str(tmp_path))
        health = store.object_store_health()

    assert health["enabled"] is True
    assert health["mode"] == "s3"
    assert health["local_root"] is None
    assert health["local_ready"] is None
    assert health["s3_ready"] is True
    assert health["ready"] is True
    clear_shared_postgres_backends()


def test_object_store_health_is_not_ready_without_any_sink_in_primary(tmp_path: Path):
    clear_shared_postgres_backends()
    store = KnowledgeDocumentStore(agent_id="AGENT_A", storage_mode="primary", object_store_root=str(tmp_path))

    health = store.object_store_health()

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
async def test_storage_v2_primary_reads_answer_trace_from_backend(tmp_path: Path):
    store_root = tmp_path / "knowledge_v2"
    repository = KnowledgeRepository("AGENT_A")
    storage = KnowledgeStorageV2(
        repository,
        "AGENT_A",
        storage_mode="primary",
        object_store_root=str(store_root),
    )

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
    storage._documents._postgres = fake  # type: ignore[assignment]
    storage._embeddings._postgres = fake  # type: ignore[assignment]
    storage._traces._postgres = fake  # type: ignore[assignment]
    storage._graph._postgres = fake  # type: ignore[assignment]
    storage._artifacts._postgres = fake  # type: ignore[assignment]

    answer_trace = await storage.get_latest_answer_trace_async(321)

    assert answer_trace is not None
    assert answer_trace["answer_text"] == "Primary answer trace"
    assert answer_trace["judge_result"]["status"] == "passed"


@pytest.mark.asyncio
async def test_storage_v2_primary_reads_fail_closed_when_backend_not_bootstrapped(tmp_path: Path):
    store_root = tmp_path / "knowledge_v2"
    repository = KnowledgeRepository("AGENT_A")
    storage = KnowledgeStorageV2(
        repository,
        "AGENT_A",
        storage_mode="primary",
        object_store_root=str(store_root),
    )
    fake = SimpleNamespace(enabled=True, bootstrapped=False)
    storage._postgres = fake  # type: ignore[assignment]
    storage._documents._postgres = fake  # type: ignore[assignment]
    storage._embeddings._postgres = fake  # type: ignore[assignment]
    storage._traces._postgres = fake  # type: ignore[assignment]
    storage._graph._postgres = fake  # type: ignore[assignment]
    storage._artifacts._postgres = fake  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="knowledge_primary_backend_unavailable"):
        await storage.get_latest_answer_trace_async(321)


@pytest.mark.asyncio
async def test_storage_v2_primary_trace_persist_fails_closed_when_backend_not_bootstrapped(tmp_path: Path):
    store_root = tmp_path / "knowledge_v2"
    repository = KnowledgeRepository("AGENT_A")
    storage = KnowledgeStorageV2(
        repository,
        "AGENT_A",
        storage_mode="primary",
        object_store_root=str(store_root),
    )
    fake_backend = SimpleNamespace(
        enabled=True,
        bootstrapped=False,
        persist_retrieval_trace=AsyncMock(return_value=88),
    )
    storage._postgres = fake_backend  # type: ignore[assignment]
    storage._documents._postgres = fake_backend  # type: ignore[assignment]
    storage._embeddings._postgres = fake_backend  # type: ignore[assignment]
    storage._traces._postgres = fake_backend  # type: ignore[assignment]
    storage._graph._postgres = fake_backend  # type: ignore[assignment]
    storage._artifacts._postgres = fake_backend  # type: ignore[assignment]
    trace = SimpleNamespace(
        agent_id="AGENT_A",
        task_id=321,
        query="deploy policy",
        strategy=SimpleNamespace(value="langgraph_current"),
        route="knowledge",
        project_key="billing",
        environment="prod",
        team="agent_a",
        graph_hops=1,
        grounding_score=0.9,
        required_citation_count=1,
        conflict_reasons=(),
        evidence_modalities=(),
        winning_sources=("policy:deploy",),
        explanation="primary trace",
        experiment_key="exp-1",
        trace_role=SimpleNamespace(value="primary"),
        paired_trace_id=None,
        hits=[
            SimpleNamespace(
                hit_id="hit-1",
                title="Deploy Policy",
                layer="canonical_policy",
                source_label="policy:deploy",
                similarity=0.92,
                freshness="fresh",
                selected=True,
                rank_before=1,
                rank_after=1,
                graph_hops=1,
                graph_score=0.4,
                reasons=("authoritative",),
                exclusion_reason="",
                evidence_modalities=(),
                supporting_evidence_keys=(),
            )
        ],
        to_dict=lambda: {"query": "deploy policy"},
    )

    with pytest.raises(RuntimeError, match="knowledge_primary_backend_unavailable"):
        storage.persist_retrieval_trace(trace=trace, sampled=True)


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
async def test_document_store_passes_logical_object_key_to_primary_backend(tmp_path: Path):
    captured: dict[str, object] = {}
    store = KnowledgeDocumentStore(agent_id="AGENT_A", storage_mode="primary", object_store_root=str(tmp_path))

    async def _upsert_documents(entries: list[KnowledgeEntry], *, object_key: str) -> None:
        captured["entries"] = entries
        captured["object_key"] = object_key

    store._postgres = SimpleNamespace(enabled=True, upsert_documents=_upsert_documents)
    store.persist_entries(
        [
            KnowledgeEntry(
                id="policy-1",
                title="Deploy Policy",
                content="Canonical deploy policy content.",
                layer=KnowledgeLayer.CANONICAL_POLICY,
                scope=KnowledgeScope.OPERATIONAL_POLICY,
                source_label="policy:deploy",
                source_path="/tmp/policy.md",
                updated_at=datetime(2026, 3, 25),
            )
        ]
    )
    await asyncio.sleep(0)

    assert captured["object_key"] == store.build_object_key("knowledge_documents", scope="latest")


def test_v2_store_support_returns_logical_object_key_for_local_payload(tmp_path: Path):
    store = KnowledgeDocumentStore(agent_id="AGENT_A", storage_mode="primary", object_store_root=str(tmp_path))

    object_key = store.write_local_payload("knowledge_documents", scope="latest", payload={"items": []})

    assert object_key == store.build_object_key("knowledge_documents", scope="latest")


def test_v2_store_support_returns_logical_object_key_without_local_mirror(tmp_path: Path):
    store = KnowledgeDocumentStore(agent_id="AGENT_A", storage_mode="primary", object_store_root=str(tmp_path))

    object_key = store.write_local_payload("knowledge_documents", scope="latest", payload={"items": []})

    assert object_key == store.build_object_key("knowledge_documents", scope="latest")
    assert not (tmp_path / "AGENT_A" / "knowledge_documents" / "latest.json").exists()


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
