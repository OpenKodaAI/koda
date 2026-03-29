"""Database-backed repository for knowledge traces, graph entities, and multimodal evidence."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from koda.config import AGENT_ID
from koda.knowledge.config import KNOWLEDGE_V2_STORAGE_MODE
from koda.knowledge.types import ArtifactEvidenceNode, GraphEntity, GraphRelation, RetrievalTrace
from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend
from koda.state_primary import primary_execute, primary_fetch_all, primary_fetch_val


def _scope(agent_id: str | None) -> str:
    normalized = str(agent_id or AGENT_ID or "default").strip().lower()
    return normalized or "default"


def _now_iso() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def _json_load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _retrieval_trace_from_row(row: Any, hits: Sequence[Any]) -> dict[str, Any]:
    if isinstance(row, dict):
        return {
            "id": row["id"],
            "agent_id": row.get("agent_id"),
            "task_id": row.get("task_id"),
            "query_text": row.get("query_text") or "",
            "strategy": row.get("strategy") or "",
            "route": row.get("route") or "",
            "project_key": row.get("project_key") or "",
            "environment": row.get("environment") or "",
            "team": row.get("team") or "",
            "graph_hops": int(row.get("graph_hops") or 0),
            "grounding_score": float(row.get("grounding_score") or 0.0),
            "citation_coverage": float(row.get("citation_coverage") or 0.0),
            "required_citation_count": int(row.get("required_citation_count") or 0),
            "conflict_reasons": _json_load(row.get("conflict_reasons_json"), []),
            "evidence_modalities": _json_load(row.get("evidence_modalities_json"), []),
            "winning_sources": _json_load(row.get("winning_sources_json"), []),
            "explanation": row.get("explanation") or "",
            "experiment_key": row.get("experiment_key") or "",
            "trace_role": row.get("trace_role") or "primary",
            "paired_trace_id": row.get("paired_trace_id"),
            "created_at": row.get("created_at"),
            "hits": [
                {
                    "hit_id": hit.get("hit_id") or "",
                    "title": hit.get("title") or "",
                    "layer": hit.get("layer") or "",
                    "source_label": hit.get("source_label") or "",
                    "similarity": float(hit.get("similarity") or 0.0),
                    "freshness": hit.get("freshness") or "",
                    "selected": bool(hit.get("selected")),
                    "rank_before": int(hit.get("rank_before") or 0),
                    "rank_after": int(hit.get("rank_after") or 0),
                    "graph_hops": int(hit.get("graph_hops") or 0),
                    "graph_score": float(hit.get("graph_score") or 0.0),
                    "reasons": _json_load(hit.get("reasons_json"), []),
                    "exclusion_reason": hit.get("exclusion_reason") or "",
                    "evidence_modalities": _json_load(hit.get("evidence_modalities_json"), []),
                }
                for hit in hits
            ],
        }
    return {
        "id": row[0],
        "agent_id": row[1],
        "task_id": row[2],
        "query_text": row[3],
        "strategy": row[4],
        "route": row[5],
        "project_key": row[6] or "",
        "environment": row[7] or "",
        "team": row[8] or "",
        "graph_hops": int(row[9] or 0),
        "grounding_score": float(row[10] or 0.0),
        "citation_coverage": float(row[11] or 0.0),
        "required_citation_count": int(row[12] or 0),
        "conflict_reasons": _json_load(row[13], []),
        "evidence_modalities": _json_load(row[14], []),
        "winning_sources": _json_load(row[15], []),
        "explanation": row[16] or "",
        "experiment_key": row[17] or "",
        "trace_role": row[18] or "primary",
        "paired_trace_id": row[19],
        "created_at": row[20],
        "hits": [
            {
                "hit_id": hit[0],
                "title": hit[1],
                "layer": hit[2],
                "source_label": hit[3],
                "similarity": float(hit[4] or 0.0),
                "freshness": hit[5] or "",
                "selected": bool(hit[6]),
                "rank_before": int(hit[7] or 0),
                "rank_after": int(hit[8] or 0),
                "graph_hops": int(hit[9] or 0),
                "graph_score": float(hit[10] or 0.0),
                "reasons": _json_load(hit[11], []),
                "exclusion_reason": hit[12] or "",
                "evidence_modalities": _json_load(hit[13], []),
            }
            for hit in hits
        ],
    }


def _answer_trace_from_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return {
            "id": row["id"],
            "agent_id": row.get("agent_id"),
            "task_id": row.get("task_id"),
            "operational_status": row.get("operational_status") or "",
            "answer_text": row.get("answer_text") or "",
            "citations": _json_load(row.get("citations_json"), []),
            "supporting_evidence_refs": _json_load(row.get("supporting_evidence_refs_json"), []),
            "uncertainty_notes": _json_load(row.get("uncertainty_notes_json"), []),
            "answer_plan": _json_load(row.get("answer_plan_json"), {}),
            "metadata": _json_load(row.get("metadata_json"), {}),
            "judge_result": _json_load(row.get("judge_json"), {}),
            "authoritative_sources": _json_load(row.get("authoritative_sources_json"), []),
            "supporting_sources": _json_load(row.get("supporting_sources_json"), []),
            "uncertainty": _json_load(row.get("uncertainty_json"), {}),
            "created_at": row.get("created_at"),
        }
    return {
        "id": row[0],
        "agent_id": row[1],
        "task_id": row[2],
        "operational_status": row[3] or "",
        "answer_text": row[4] or "",
        "citations": _json_load(row[5], []),
        "supporting_evidence_refs": _json_load(row[6], []),
        "uncertainty_notes": _json_load(row[7], []),
        "answer_plan": _json_load(row[8], {}),
        "metadata": _json_load(row[9], {}),
        "judge_result": _json_load(row[10], {}),
        "authoritative_sources": _json_load(row[11], []),
        "supporting_sources": _json_load(row[12], []),
        "uncertainty": _json_load(row[13], {}),
        "created_at": row[14],
    }


def _evaluation_case_from_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return {
            "id": row["id"],
            "case_key": row.get("case_key") or "",
            "agent_id": row.get("agent_id"),
            "source_task_id": row.get("source_task_id"),
            "query_text": row.get("query_text") or "",
            "task_kind": row.get("task_kind") or "general",
            "project_key": row.get("project_key") or "",
            "environment": row.get("environment") or "",
            "team": row.get("team") or "",
            "modality": row.get("modality") or "text",
            "expected_sources": _json_load(row.get("expected_sources_json"), []),
            "expected_layers": _json_load(row.get("expected_layers_json"), []),
            "reference_answer": row.get("reference_answer") or "",
            "status": row.get("status") or "draft",
            "gold_source_kind": row.get("gold_source_kind") or "manual_gold",
            "validated_by": row.get("validated_by") or "",
            "validated_at": row.get("validated_at") or "",
            "metadata": _json_load(row.get("metadata_json"), {}),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
    return {
        "id": row[0],
        "case_key": row[1],
        "agent_id": row[2],
        "source_task_id": row[3],
        "query_text": row[4],
        "task_kind": row[5],
        "project_key": row[6] or "",
        "environment": row[7] or "",
        "team": row[8] or "",
        "modality": row[9] or "text",
        "expected_sources": _json_load(row[10], []),
        "expected_layers": _json_load(row[11], []),
        "reference_answer": row[12] or "",
        "status": row[13] or "draft",
        "gold_source_kind": row[14] or "manual_gold",
        "validated_by": row[15] or "",
        "validated_at": row[16] or "",
        "metadata": _json_load(row[17], {}),
        "created_at": row[18],
        "updated_at": row[19],
    }


def _evaluation_run_from_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return {
            "id": row["id"],
            "case_key": row.get("case_key") or "",
            "agent_id": row.get("agent_id"),
            "strategy": row.get("strategy") or "",
            "retrieval_trace_id": row.get("retrieval_trace_id"),
            "recall_at_k": float(row.get("recall_at_k") or 0.0),
            "ndcg_at_k": float(row.get("ndcg_at_k") or 0.0),
            "citation_accuracy": float(row.get("citation_accuracy") or 0.0),
            "groundedness_precision": float(row.get("groundedness_precision") or 0.0),
            "conflict_detection_rate": float(row.get("conflict_detection_rate") or 0.0),
            "verification_before_finalize_rate": float(row.get("verification_before_finalize_rate") or 0.0),
            "human_correction_rate": float(row.get("human_correction_rate") or 0.0),
            "task_success_proxy": float(row.get("task_success_proxy") or 0.0),
            "metrics": _json_load(row.get("metrics_json"), {}),
            "created_at": row.get("created_at"),
        }
    return {
        "id": row[0],
        "case_key": row[1],
        "agent_id": row[2],
        "strategy": row[3],
        "retrieval_trace_id": row[4],
        "recall_at_k": float(row[5] or 0.0),
        "ndcg_at_k": float(row[6] or 0.0),
        "citation_accuracy": float(row[7] or 0.0),
        "groundedness_precision": float(row[8] or 0.0),
        "conflict_detection_rate": float(row[9] or 0.0),
        "verification_before_finalize_rate": float(row[10] or 0.0),
        "human_correction_rate": float(row[11] or 0.0),
        "task_success_proxy": float(row[12] or 0.0),
        "metrics": _json_load(row[13], {}),
        "created_at": row[14],
    }


class KnowledgeRepository:
    """Repository wrapper that centralizes knowledge persistence details."""

    def __init__(self, agent_id: str | None = None) -> None:
        self._agent_id = agent_id
        self._scope = _scope(agent_id)
        self._postgres = KnowledgeV2PostgresBackend(agent_id=agent_id)

    def _primary_mode(self) -> bool:
        return KNOWLEDGE_V2_STORAGE_MODE == "primary"

    def _require_primary_backend(self) -> None:
        if self._primary_mode() and not self._postgres.enabled:
            raise RuntimeError("knowledge_primary_backend_unavailable")

    def _run_coro_sync(self, coro: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result: dict[str, Any] = {}
        error: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except BaseException as exc:  # noqa: BLE001
                error["error"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if "error" in error:
            raise error["error"]
        return result.get("value")

    def persist_retrieval_trace(self, trace: RetrievalTrace, *, sampled: bool) -> int | None:
        if not sampled or not trace.hits:
            return None
        self._require_primary_backend()
        agent_id = _scope(trace.agent_id or self._agent_id)
        trace_id = self._run_coro_sync(
            primary_fetch_val(
                """INSERT INTO retrieval_traces
                   (agent_id, task_id, query_text, strategy, route, project_key, environment, team, graph_hops,
                    grounding_score, citation_coverage, required_citation_count, conflict_reasons_json,
                    evidence_modalities_json, winning_sources_json, explanation, experiment_key, trace_role,
                    paired_trace_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    agent_id,
                    trace.task_id,
                    trace.query,
                    trace.strategy.value,
                    trace.route,
                    trace.project_key,
                    trace.environment,
                    trace.team,
                    trace.graph_hops,
                    trace.grounding_score,
                    0.0,
                    trace.required_citation_count,
                    list(trace.conflict_reasons),
                    [modality.value for modality in trace.evidence_modalities],
                    list(trace.winning_sources),
                    trace.explanation,
                    trace.experiment_key,
                    trace.trace_role.value,
                    trace.paired_trace_id,
                    _now_iso(),
                ),
                agent_id=agent_id,
            )
        )
        if trace_id is None:
            return None
        for hit in trace.hits:
            self._run_coro_sync(
                primary_execute(
                    """INSERT INTO retrieval_trace_hits
                       (trace_id, hit_id, title, layer, source_label, similarity, freshness, selected,
                        rank_before, rank_after, graph_hops, graph_score, reasons_json, exclusion_reason,
                        evidence_modalities_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        int(trace_id),
                        hit.hit_id,
                        hit.title,
                        hit.layer,
                        hit.source_label,
                        hit.similarity,
                        hit.freshness,
                        hit.selected,
                        hit.rank_before,
                        hit.rank_after,
                        hit.graph_hops,
                        hit.graph_score,
                        list(hit.reasons),
                        hit.exclusion_reason,
                        [modality.value for modality in hit.evidence_modalities],
                    ),
                    agent_id=agent_id,
                )
            )
        return int(trace_id)

    def persist_answer_trace(
        self,
        *,
        task_id: int | None,
        grounded_answer: dict[str, Any],
        judgement: dict[str, Any],
        authoritative_sources: list[dict[str, Any]] | None = None,
        supporting_sources: list[dict[str, Any]] | None = None,
        uncertainty: dict[str, Any] | None = None,
    ) -> int:
        agent_id = self._scope
        self._require_primary_backend()
        row_id = self._run_coro_sync(
            primary_fetch_val(
                """INSERT INTO answer_traces
                   (agent_id, task_id, operational_status, answer_text, citations_json,
                    supporting_evidence_refs_json, uncertainty_notes_json, answer_plan_json, metadata_json,
                    judge_json, authoritative_sources_json, supporting_sources_json, uncertainty_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    agent_id,
                    task_id,
                    str(grounded_answer.get("operational_status") or ""),
                    str(grounded_answer.get("answer_text") or ""),
                    list(grounded_answer.get("citations") or []),
                    list(grounded_answer.get("supporting_evidence_refs") or []),
                    list(grounded_answer.get("uncertainty_notes") or []),
                    dict(grounded_answer.get("answer_plan") or {}),
                    dict(grounded_answer.get("metadata") or {}),
                    judgement,
                    authoritative_sources or [],
                    supporting_sources or [],
                    uncertainty or {},
                    _now_iso(),
                ),
                agent_id=agent_id,
            )
        )
        if row_id is None:
            raise RuntimeError("failed_to_persist_primary_answer_trace")
        return int(row_id)

    def batch_upsert_graph(self, *, entities: Sequence[GraphEntity], relations: Sequence[GraphRelation]) -> None:
        if not entities and not relations:
            return
        self._require_primary_backend()
        self._run_coro_sync(self._postgres.upsert_graph(entities=list(entities), relations=list(relations)))
        return

    def batch_upsert_artifact_evidence(self, nodes: Sequence[ArtifactEvidenceNode]) -> None:
        if not nodes:
            return
        now = _now_iso()
        self._require_primary_backend()
        for node in nodes:
            self._run_coro_sync(
                primary_execute(
                    """INSERT INTO artifact_evidence_nodes
                       (evidence_key, agent_id, task_id, artifact_id, project_key, workspace_fingerprint,
                        modality, label, extracted_text, source_path, source_url, source_hash, embedding_json,
                        confidence, trust_level, time_span, frame_ref, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(evidence_key) DO UPDATE SET
                           agent_id = EXCLUDED.agent_id,
                           task_id = EXCLUDED.task_id,
                           artifact_id = EXCLUDED.artifact_id,
                           project_key = EXCLUDED.project_key,
                           workspace_fingerprint = EXCLUDED.workspace_fingerprint,
                           modality = EXCLUDED.modality,
                           label = EXCLUDED.label,
                           extracted_text = EXCLUDED.extracted_text,
                           source_path = EXCLUDED.source_path,
                           source_url = EXCLUDED.source_url,
                           source_hash = EXCLUDED.source_hash,
                           embedding_json = EXCLUDED.embedding_json,
                           confidence = EXCLUDED.confidence,
                           trust_level = EXCLUDED.trust_level,
                           time_span = EXCLUDED.time_span,
                           frame_ref = EXCLUDED.frame_ref,
                           metadata_json = EXCLUDED.metadata_json""",
                    (
                        node.evidence_key,
                        _scope(node.agent_id or self._agent_id),
                        node.task_id,
                        node.artifact_id,
                        str(node.metadata.get("project_key") or ""),
                        str(node.metadata.get("workspace_fingerprint") or ""),
                        node.modality.value,
                        node.label,
                        node.extracted_text,
                        node.source_path,
                        node.source_url,
                        str(node.metadata.get("source_hash") or ""),
                        node.metadata.get("embedding") or [],
                        node.confidence,
                        node.trust_level,
                        node.time_span,
                        node.frame_ref,
                        node.metadata or {},
                        now,
                    ),
                    agent_id=_scope(node.agent_id or self._agent_id),
                )
            )
        return

    def list_artifact_evidence(
        self,
        *,
        task_id: int | None,
        project_key: str,
        workspace_fingerprint: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_primary_backend()
        where: list[str] = []
        params: list[Any] = []
        if self._agent_id is not None:
            where.append("agent_id = ?")
            params.append(self._scope)
        if task_id is not None:
            where.append("task_id = ?")
            params.append(task_id)
        if project_key:
            where.append("project_key = ?")
            params.append(project_key)
        if workspace_fingerprint:
            where.append("workspace_fingerprint = ?")
            params.append(workspace_fingerprint)
        params.append(max(1, limit))
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        rows = self._run_coro_sync(
            primary_fetch_all(
                "SELECT id, evidence_key, agent_id, task_id, artifact_id, "
                "project_key, workspace_fingerprint, modality, "
                "label, extracted_text, source_path, source_url, source_hash, embedding_json, confidence, "
                "trust_level, time_span, frame_ref, metadata_json, created_at "
                f"FROM artifact_evidence_nodes{clause} ORDER BY id DESC LIMIT ?",
                tuple(params),
                agent_id=self._scope,
            )
        )
        return [
            {
                "id": row["id"],
                "evidence_key": row.get("evidence_key") or "",
                "agent_id": row.get("agent_id"),
                "task_id": row.get("task_id"),
                "artifact_id": row.get("artifact_id") or "",
                "project_key": row.get("project_key") or "",
                "workspace_fingerprint": row.get("workspace_fingerprint") or "",
                "modality": row.get("modality") or "",
                "label": row.get("label") or "",
                "extracted_text": row.get("extracted_text") or "",
                "source_path": row.get("source_path") or "",
                "source_url": row.get("source_url") or "",
                "source_hash": row.get("source_hash") or "",
                "embedding": _json_load(row.get("embedding_json"), []),
                "confidence": float(row.get("confidence") or 0.0),
                "trust_level": row.get("trust_level") or "untrusted",
                "time_span": row.get("time_span") or "",
                "frame_ref": row.get("frame_ref") or "",
                "metadata": _json_load(row.get("metadata_json"), {}),
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]

    def get_retrieval_trace(self, trace_id: int) -> dict[str, Any] | None:
        self._require_primary_backend()
        return cast(dict[str, Any] | None, self._run_coro_sync(self._postgres.get_retrieval_trace(trace_id)))

    def get_answer_trace(self, answer_trace_id: int) -> dict[str, Any] | None:
        self._require_primary_backend()
        return cast(dict[str, Any] | None, self._run_coro_sync(self._postgres.get_answer_trace(answer_trace_id)))

    def get_latest_answer_trace(self, task_id: int) -> dict[str, Any] | None:
        self._require_primary_backend()
        return cast(dict[str, Any] | None, self._run_coro_sync(self._postgres.get_latest_answer_trace(task_id)))

    def list_retrieval_traces(
        self,
        *,
        task_id: int | None = None,
        strategy: str | None = None,
        experiment_key: str | None = None,
        trace_role: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._require_primary_backend()
        return cast(
            list[dict[str, Any]],
            self._run_coro_sync(
                self._postgres.list_retrieval_traces(
                    task_id=task_id,
                    strategy=strategy,
                    experiment_key=experiment_key,
                    trace_role=trace_role,
                    limit=limit,
                )
            ),
        )

    def list_answer_traces(
        self,
        *,
        task_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._require_primary_backend()
        return cast(
            list[dict[str, Any]],
            self._run_coro_sync(self._postgres.list_answer_traces(task_id=task_id, limit=limit)),
        )

    def list_evaluation_cases(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._run_coro_sync(
            primary_fetch_all(
                """SELECT id, case_key, agent_id, source_task_id, query_text, task_kind, project_key, environment,
                          team, modality, expected_sources_json, expected_layers_json, reference_answer, status,
                          gold_source_kind, validated_by, validated_at, metadata_json, created_at, updated_at
                   FROM evaluation_cases
                   WHERE agent_id = ? ORDER BY id DESC LIMIT ?""",
                (self._scope, max(1, limit)),
                agent_id=self._scope,
            )
        )
        return [_evaluation_case_from_row(row) for row in rows]

    def upsert_evaluation_case(self, **payload: Any) -> int:
        agent_id = self._scope
        now = _now_iso()
        values = (
            payload["case_key"],
            agent_id,
            payload.get("source_task_id"),
            payload["query_text"],
            payload.get("task_kind", "general"),
            payload.get("project_key", ""),
            payload.get("environment", ""),
            payload.get("team", ""),
            payload.get("modality", "text"),
            list(payload.get("expected_sources") or []),
            list(payload.get("expected_layers") or []),
            payload.get("reference_answer", ""),
            payload.get("status", "draft"),
            payload.get("gold_source_kind", "manual_gold"),
            payload.get("validated_by", ""),
            payload.get("validated_at", ""),
            dict(payload.get("metadata") or {}),
            now,
            now,
        )
        row_id = self._run_coro_sync(
            primary_fetch_val(
                """INSERT INTO evaluation_cases
                   (
                    case_key, agent_id, source_task_id, query_text, task_kind,
                    project_key, environment, team, modality,
                    expected_sources_json, expected_layers_json, reference_answer, status, gold_source_kind,
                    validated_by, validated_at, metadata_json, created_at, updated_at)
                   )
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(case_key) DO UPDATE SET
                       agent_id = EXCLUDED.agent_id,
                       source_task_id = EXCLUDED.source_task_id,
                       query_text = EXCLUDED.query_text,
                       task_kind = EXCLUDED.task_kind,
                       project_key = EXCLUDED.project_key,
                       environment = EXCLUDED.environment,
                       team = EXCLUDED.team,
                       modality = EXCLUDED.modality,
                       expected_sources_json = EXCLUDED.expected_sources_json,
                       expected_layers_json = EXCLUDED.expected_layers_json,
                       reference_answer = EXCLUDED.reference_answer,
                       status = EXCLUDED.status,
                       gold_source_kind = EXCLUDED.gold_source_kind,
                       validated_by = EXCLUDED.validated_by,
                       validated_at = EXCLUDED.validated_at,
                       metadata_json = EXCLUDED.metadata_json,
                       updated_at = EXCLUDED.updated_at
                   RETURNING id""",
                values,
                agent_id=agent_id,
            )
        )
        if row_id is None:
            raise RuntimeError("failed_to_upsert_primary_evaluation_case")
        return int(row_id)

    def update_evaluation_case(self, case_key: str, **payload: Any) -> bool:
        fields = ["updated_at = ?"]
        values: list[Any] = [_now_iso()]
        if "expected_sources" in payload and payload["expected_sources"] is not None:
            fields.append("expected_sources_json = ?")
            values.append(list(payload["expected_sources"]))
        if "expected_layers" in payload and payload["expected_layers"] is not None:
            fields.append("expected_layers_json = ?")
            values.append(list(payload["expected_layers"]))
        if "reference_answer" in payload and payload["reference_answer"] is not None:
            fields.append("reference_answer = ?")
            values.append(payload["reference_answer"])
        if "status" in payload and payload["status"] is not None:
            fields.append("status = ?")
            values.append(payload["status"])
        if "gold_source_kind" in payload and payload["gold_source_kind"] is not None:
            fields.append("gold_source_kind = ?")
            values.append(payload["gold_source_kind"])
        if "validated_by" in payload and payload["validated_by"] is not None:
            fields.append("validated_by = ?")
            values.append(payload["validated_by"])
        if "validated_at" in payload and payload["validated_at"] is not None:
            fields.append("validated_at = ?")
            values.append(payload["validated_at"])
        if "metadata" in payload and payload["metadata"] is not None:
            fields.append("metadata_json = ?")
            values.append(dict(payload["metadata"]))
        values.append(case_key)
        updated = self._run_coro_sync(
            primary_execute(
                f"UPDATE evaluation_cases SET {', '.join(fields)} WHERE case_key = ?",
                tuple(values),
                agent_id=self._scope,
            )
        )
        return bool(updated)

    def list_evaluation_runs(
        self,
        *,
        case_key: str | None = None,
        strategy: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        primary_where: list[str] = ["agent_id = ?"]
        primary_params: list[Any] = [self._scope]
        if case_key:
            primary_where.append("case_key = ?")
            primary_params.append(case_key)
        if strategy:
            primary_where.append("strategy = ?")
            primary_params.append(strategy)
        primary_params.append(max(1, limit))
        rows = self._run_coro_sync(
            primary_fetch_all(
                """SELECT id, case_key, agent_id, strategy, retrieval_trace_id, recall_at_k, ndcg_at_k,
                          citation_accuracy, groundedness_precision, conflict_detection_rate,
                          verification_before_finalize_rate, human_correction_rate, task_success_proxy,
                          metrics_json, created_at
                   FROM evaluation_runs WHERE """
                + " AND ".join(primary_where)
                + " ORDER BY id DESC LIMIT ?",
                tuple(primary_params),
                agent_id=self._scope,
            )
        )
        return [_evaluation_run_from_row(row) for row in rows]

    def create_evaluation_run(self, **payload: Any) -> int:
        row_id = self._run_coro_sync(
            primary_fetch_val(
                """INSERT INTO evaluation_runs
                   (case_key, agent_id, strategy, retrieval_trace_id, recall_at_k, ndcg_at_k, citation_accuracy,
                    groundedness_precision, conflict_detection_rate, verification_before_finalize_rate,
                    human_correction_rate, task_success_proxy, metrics_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    payload["case_key"],
                    self._scope,
                    payload["strategy"],
                    payload.get("retrieval_trace_id"),
                    payload.get("recall_at_k", 0.0),
                    payload.get("ndcg_at_k", 0.0),
                    payload.get("citation_accuracy", 0.0),
                    payload.get("groundedness_precision", 0.0),
                    payload.get("conflict_detection_rate", 0.0),
                    payload.get("verification_before_finalize_rate", 0.0),
                    payload.get("human_correction_rate", 0.0),
                    payload.get("task_success_proxy", 0.0),
                    dict(payload.get("metrics_payload") or {}),
                    _now_iso(),
                ),
                agent_id=self._scope,
            )
        )
        if row_id is None:
            raise RuntimeError("failed_to_persist_primary_evaluation_run")
        return int(row_id)

    def _schedule_external_graph_sync(
        self,
        *,
        entities: Sequence[GraphEntity],
        relations: Sequence[GraphRelation],
    ) -> None:
        if not self._postgres.enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._postgres.upsert_graph(entities=list(entities), relations=list(relations)))
