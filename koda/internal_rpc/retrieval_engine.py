"""Retrieval-engine client selection for the Rust migration seam."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

from koda import config
from koda.internal_rpc.common import (
    EngineSelection,
    ensure_generated_proto_path,
    normalize_internal_service_probe,
    resolve_grpc_target,
    select_engine_backend,
)
from koda.internal_rpc.metadata import build_rpc_metadata

if TYPE_CHECKING:
    from koda.knowledge.types import QueryEnvelope, RetrievalBundle


def _protobuf_value_to_python(value: Any) -> object:
    if value is None:
        return None
    which_oneof = getattr(value, "WhichOneof", None)
    if callable(which_oneof):
        kind = which_oneof("kind")
        if kind == "null_value":
            return None
        if kind == "bool_value":
            return bool(getattr(value, "bool_value", False))
        if kind == "number_value":
            return float(getattr(value, "number_value", 0.0))
        if kind == "string_value":
            return str(getattr(value, "string_value", ""))
        if kind == "struct_value":
            return _protobuf_struct_to_dict(getattr(value, "struct_value", None))
        if kind == "list_value":
            return [
                _protobuf_value_to_python(item)
                for item in getattr(getattr(value, "list_value", None), "values", []) or []
            ]
    if isinstance(value, Mapping):
        return {str(key): _protobuf_value_to_python(raw_value) for key, raw_value in value.items()}
    return value


def _protobuf_struct_to_dict(value: Any) -> dict[str, object]:
    if value is None:
        return {}
    fields = getattr(value, "fields", None)
    if isinstance(fields, Mapping):
        return {str(key): _protobuf_value_to_python(raw_value) for key, raw_value in fields.items()}
    if isinstance(value, Mapping):
        return {str(key): _protobuf_value_to_python(raw_value) for key, raw_value in value.items()}
    return {}


def _build_struct_message(payload: Mapping[str, object]) -> Any | None:
    clean_payload = {str(key): value for key, value in payload.items()}
    if not clean_payload:
        return None
    try:
        from google.protobuf import json_format, struct_pb2
    except Exception:
        return None
    message = struct_pb2.Struct()
    json_format.ParseDict(dict(clean_payload), message)
    return message


class RetrievalEngineClient(Protocol):
    """Behavior expected from the retrieval-engine adapter."""

    engine_name: str

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def query(
        self,
        *,
        envelope: QueryEnvelope,
        max_results: int,
    ) -> RetrievalBundle: ...

    def list_graph(
        self,
        *,
        entity_type: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]: ...

    def health(self) -> dict[str, object]: ...


class GrpcRetrievalEngineClient:
    """Rust retrieval client over internal gRPC."""

    engine_name = "rust_grpc"

    def __init__(self, *, selection: EngineSelection) -> None:
        self.selection = selection
        self._target, self._transport = resolve_grpc_target(config.RETRIEVAL_GRPC_TARGET)
        self._channel: Any | None = None
        self._stub: Any | None = None
        self._metadata_pb2: Any | None = None
        self._retrieval_pb2: Any | None = None
        self._startup_error: str | None = None
        self._last_health: dict[str, object] = {
            "service": "retrieval",
            "mode": self.selection.mode,
            "implementation": "grpc-retrieval-engine-client",
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

    async def start(self) -> None:
        try:
            import grpc

            ensure_generated_proto_path()
            from common.v1 import metadata_pb2
            from retrieval.v1 import retrieval_pb2, retrieval_pb2_grpc
        except Exception as exc:  # pragma: no cover - import failure depends on environment
            self._startup_error = f"{type(exc).__name__}: {exc}"
            self._last_health = {
                **self._last_health,
                "startup_error": self._startup_error,
                "ready": False,
            }
            raise RuntimeError("grpc_retrieval_engine_client_requires_retrieval_stubs") from exc

        self._channel = grpc.insecure_channel(self._target)
        self._metadata_pb2 = metadata_pb2
        self._retrieval_pb2 = retrieval_pb2
        self._stub = retrieval_pb2_grpc.RetrievalEngineServiceStub(self._channel)
        self._probe_health()

    async def stop(self) -> None:
        if self._channel is None:
            return
        channel = self._channel
        self._channel = None
        self._stub = None
        channel.close()

    def _rpc_metadata(
        self,
        *,
        envelope: QueryEnvelope | None = None,
        extra: dict[str, str] | None = None,
    ) -> tuple[tuple[str, str], ...]:
        return build_rpc_metadata(
            agent_id=(envelope.agent_id if envelope is not None else self.selection.agent_id),
            task_id=(envelope.task_id if envelope is not None else None),
            user_id=(envelope.user_id if envelope is not None else None),
            extra={
                "x-internal-rpc-mode": self.selection.mode,
                **(extra or {}),
            },
        )

    def _probe_health(self) -> None:
        if self._stub is None or self._metadata_pb2 is None:
            return
        response = self._stub.Health(
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
        raw_details = self._last_health.get("details")
        details = dict(raw_details) if isinstance(raw_details, Mapping) else {}
        capabilities = {
            item.strip().lower() for item in str(details.get("capabilities") or "").split(",") if item.strip()
        }
        bundle_contract_ready = "bundle-assembly" in capabilities
        self._last_health = {
            **self._last_health,
            "bundle_contract_ready": bundle_contract_ready,
            "authoritative": bool(self._last_health.get("authoritative")) and bundle_contract_ready,
            "production_ready": bool(self._last_health.get("production_ready")) and bundle_contract_ready,
            "cutover_allowed": bool(self._last_health.get("cutover_allowed")) and bundle_contract_ready,
        }

    def query(
        self,
        *,
        envelope: QueryEnvelope,
        max_results: int,
    ) -> RetrievalBundle:
        if self._stub is None or self._retrieval_pb2 is None:
            raise RuntimeError("grpc_retrieval_engine_unavailable")
        if not bool(self.health().get("cutover_allowed")):
            raise RuntimeError("grpc_retrieval_engine_not_authoritative")

        envelope_kwargs: dict[str, object] = {
            "normalized_query": envelope.normalized_query,
            "task_kind": envelope.task_kind,
            "project_key": envelope.project_key,
            "environment": envelope.environment,
            "team": envelope.team,
            "workspace_dir": envelope.workspace_dir,
            "workspace_fingerprint": envelope.workspace_fingerprint,
            "requires_write": envelope.requires_write,
            "strategy": envelope.strategy.value,
            "allowed_source_labels": list(envelope.allowed_source_labels),
            "allowed_workspace_roots": list(envelope.allowed_workspace_roots),
        }
        metadata_struct = _build_struct_message(envelope.metadata)
        if metadata_struct is not None:
            envelope_kwargs["metadata"] = metadata_struct

        retrieve_response = self._stub.Retrieve(
            self._retrieval_pb2.RetrieveRequest(
                metadata=self._request_metadata(envelope=envelope),
                agent_id=envelope.agent_id or self.selection.agent_id or "",
                query=envelope.query,
                limit=max_results,
                envelope=self._retrieval_pb2.RetrieveEnvelope(**envelope_kwargs),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(envelope=envelope),
        )
        from koda.knowledge.types import RetrievalBundle

        bundle_payload: dict[str, Any] = {
            "normalized_query": str(getattr(retrieve_response, "normalized_query", "") or ""),
            "query_intent": str(getattr(retrieve_response, "query_intent", "") or ""),
            "route": str(getattr(retrieve_response, "route", "") or ""),
            "strategy": str(getattr(retrieve_response, "strategy", "") or ""),
            "selected_hits": [
                self._retrieval_hit_payload(item)
                for item in list(getattr(retrieve_response, "selected_hits", []) or [])
            ],
            "candidate_hits": [
                self._retrieval_hit_payload(item)
                for item in list(getattr(retrieve_response, "candidate_hits", []) or [])
            ],
            "trace_hits": [
                self._trace_hit_payload(item) for item in list(getattr(retrieve_response, "trace_hits", []) or [])
            ],
            "authoritative_evidence": [
                self._authoritative_evidence_payload(item)
                for item in list(getattr(retrieve_response, "authoritative_evidence", []) or [])
            ],
            "supporting_evidence": [
                self._supporting_evidence_payload(item)
                for item in list(getattr(retrieve_response, "supporting_evidence", []) or [])
            ],
            "linked_entities": [
                self._linked_entity_payload(item)
                for item in list(getattr(retrieve_response, "linked_entities", []) or [])
            ],
            "graph_relations": [
                self._graph_relation_payload(item)
                for item in list(getattr(retrieve_response, "graph_relations", []) or [])
            ],
            "subqueries": [str(item) for item in list(getattr(retrieve_response, "subqueries", []) or [])],
            "open_conflicts": [str(item) for item in list(getattr(retrieve_response, "open_conflicts", []) or [])],
            "uncertainty_notes": [
                str(item) for item in list(getattr(retrieve_response, "uncertainty_notes", []) or [])
            ],
            "uncertainty_level": str(getattr(retrieve_response, "uncertainty_level", "") or ""),
            "recommended_action_mode": str(getattr(retrieve_response, "recommended_action_mode", "") or ""),
            "required_verifications": [
                str(item) for item in list(getattr(retrieve_response, "required_verifications", []) or [])
            ],
            "graph_hops": int(getattr(retrieve_response, "graph_hops", 0) or 0),
            "grounding_score": float(getattr(retrieve_response, "grounding_score", 0.0) or 0.0),
            "answer_plan": self._answer_plan_payload(getattr(retrieve_response, "answer_plan", None)),
            "judge_result": self._judge_result_payload(getattr(retrieve_response, "judge_result", None)),
            "effective_engine": str(getattr(retrieve_response, "effective_engine", "") or ""),
            "fallback_used": bool(getattr(retrieve_response, "fallback_used", False)),
            "explanation": str(getattr(retrieve_response, "explanation", "") or ""),
        }
        self._validate_remote_bundle_payload(bundle_payload)
        bundle = RetrievalBundle.from_dict(bundle_payload)
        bundle.effective_engine = str(bundle.effective_engine or self.engine_name)
        bundle.fallback_used = bool(bundle.fallback_used)
        trace_id = str(getattr(retrieve_response, "trace_id", "") or "").strip()
        if trace_id:
            if bundle.explanation:
                bundle.explanation = f"{bundle.explanation}; trace_id={trace_id}"
            else:
                bundle.explanation = f"trace_id={trace_id}"
        return bundle

    def list_graph(
        self,
        *,
        entity_type: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]:
        if self._stub is None or self._retrieval_pb2 is None:
            raise RuntimeError("grpc_retrieval_engine_unavailable")
        health = self.health()
        if not bool(health.get("ready")):
            raise RuntimeError("grpc_retrieval_engine_not_ready")
        details = health.get("details")
        capabilities = (
            {item.strip().lower() for item in str((details or {}).get("capabilities") or "").split(",") if item.strip()}
            if isinstance(details, Mapping)
            else set()
        )
        if "graph_read" not in capabilities:
            raise RuntimeError("grpc_retrieval_engine_graph_read_not_supported")
        response = self._stub.ListGraph(
            self._retrieval_pb2.ListGraphRequest(
                metadata=self._request_metadata(
                    envelope=None,
                ),
                agent_id=self.selection.agent_id or "",
                entity_type=(entity_type or "").strip(),
                limit=max(0, int(limit)),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(
                extra={"x-retrieval-graph-read": "true"},
            ),
        )
        return {
            "entities": [
                {
                    "entity_key": str(item.entity_key or ""),
                    "entity_type": str(item.entity_type or ""),
                    "label": str(item.label or ""),
                    "source_kind": str(item.source_kind or ""),
                    "metadata": _protobuf_struct_to_dict(getattr(item, "metadata", None)),
                    "updated_at": str(item.updated_at or "") or None,
                    "graph_score": float(item.graph_score or 0.0),
                    "graph_hops": int(item.graph_hops or 0),
                    "relation_types": [str(value) for value in item.relation_types],
                }
                for item in response.entities
            ],
            "relations": [
                {
                    "relation_key": str(item.relation_key or ""),
                    "relation_type": str(item.relation_type or ""),
                    "source_entity_key": str(item.source_entity_key or ""),
                    "target_entity_key": str(item.target_entity_key or ""),
                    "weight": float(item.weight or 0.0),
                    "metadata": _protobuf_struct_to_dict(getattr(item, "metadata", None)),
                    "updated_at": str(item.updated_at or "") or None,
                }
                for item in response.relations
            ],
        }

    def _retrieval_hit_payload(self, item: Any) -> dict[str, object]:
        return {
            "id": str(getattr(item, "id", "") or ""),
            "title": str(getattr(item, "title", "") or ""),
            "content": str(getattr(item, "content", "") or ""),
            "layer": str(getattr(item, "layer", "") or ""),
            "scope": str(getattr(item, "scope", "") or ""),
            "source_label": str(getattr(item, "source_label", "") or ""),
            "source_path": str(getattr(item, "source_path", "") or ""),
            "updated_at": str(getattr(item, "updated_at", "") or ""),
            "owner": str(getattr(item, "owner", "") or ""),
            "tags": [str(value) for value in list(getattr(item, "tags", []) or [])],
            "criticality": str(getattr(item, "criticality", "") or ""),
            "freshness": str(getattr(item, "freshness", "") or ""),
            "similarity": float(getattr(item, "similarity", 0.0) or 0.0),
            "lexical_rank": int(getattr(item, "lexical_rank", -1) or -1),
            "dense_rank": int(getattr(item, "dense_rank", -1) or -1),
            "graph_rank": int(getattr(item, "graph_rank", -1) or -1),
            "lexical_score": float(getattr(item, "lexical_score", 0.0) or 0.0),
            "dense_score": float(getattr(item, "dense_score", 0.0) or 0.0),
            "project_key": str(getattr(item, "project_key", "") or ""),
            "environment": str(getattr(item, "environment", "") or ""),
            "team": str(getattr(item, "team", "") or ""),
            "source_type": str(getattr(item, "source_type", "") or ""),
            "operable": bool(getattr(item, "operable", True)),
            "graph_hops": int(getattr(item, "graph_hops", 0) or 0),
            "graph_score": float(getattr(item, "graph_score", 0.0) or 0.0),
            "graph_relation_types": [str(value) for value in list(getattr(item, "graph_relation_types", []) or [])],
            "evidence_modalities": [str(value) for value in list(getattr(item, "evidence_modalities", []) or [])],
            "reasons": [str(value) for value in list(getattr(item, "reasons", []) or [])],
        }

    def _trace_hit_payload(self, item: Any) -> dict[str, object]:
        return {
            "hit_id": str(getattr(item, "hit_id", "") or ""),
            "title": str(getattr(item, "title", "") or ""),
            "layer": str(getattr(item, "layer", "") or ""),
            "source_label": str(getattr(item, "source_label", "") or ""),
            "similarity": float(getattr(item, "similarity", 0.0) or 0.0),
            "freshness": str(getattr(item, "freshness", "") or ""),
            "selected": bool(getattr(item, "selected", False)),
            "rank_before": int(getattr(item, "rank_before", 0) or 0),
            "rank_after": int(getattr(item, "rank_after", 0) or 0),
            "lexical_rank": int(getattr(item, "lexical_rank", -1) or -1),
            "dense_rank": int(getattr(item, "dense_rank", -1) or -1),
            "graph_rank": int(getattr(item, "graph_rank", -1) or -1),
            "lexical_score": float(getattr(item, "lexical_score", 0.0) or 0.0),
            "dense_score": float(getattr(item, "dense_score", 0.0) or 0.0),
            "graph_hops": int(getattr(item, "graph_hops", 0) or 0),
            "graph_score": float(getattr(item, "graph_score", 0.0) or 0.0),
            "graph_relation_types": [str(value) for value in list(getattr(item, "graph_relation_types", []) or [])],
            "reasons": [str(value) for value in list(getattr(item, "reasons", []) or [])],
            "exclusion_reason": str(getattr(item, "exclusion_reason", "") or ""),
            "evidence_modalities": [str(value) for value in list(getattr(item, "evidence_modalities", []) or [])],
            "supporting_evidence_keys": [
                str(value) for value in list(getattr(item, "supporting_evidence_keys", []) or [])
            ],
        }

    def _authoritative_evidence_payload(self, item: Any) -> dict[str, object]:
        return {
            "source_label": str(getattr(item, "source_label", "") or ""),
            "layer": str(getattr(item, "layer", "") or ""),
            "title": str(getattr(item, "title", "") or ""),
            "excerpt": str(getattr(item, "excerpt", "") or ""),
            "updated_at": str(getattr(item, "updated_at", "") or ""),
            "freshness": str(getattr(item, "freshness", "") or ""),
            "score": float(getattr(item, "score", 0.0) or 0.0),
            "operable": bool(getattr(item, "operable", True)),
            "rationale": str(getattr(item, "rationale", "") or ""),
            "evidence_modalities": [str(value) for value in list(getattr(item, "evidence_modalities", []) or [])],
        }

    def _supporting_evidence_payload(self, item: Any) -> dict[str, object]:
        return {
            "ref_key": str(getattr(item, "ref_key", "") or ""),
            "label": str(getattr(item, "label", "") or ""),
            "modality": str(getattr(item, "modality", "") or ""),
            "excerpt": str(getattr(item, "excerpt", "") or ""),
            "score": float(getattr(item, "score", 0.0) or 0.0),
            "confidence": float(getattr(item, "confidence", 0.0) or 0.0),
            "trust_level": str(getattr(item, "trust_level", "") or ""),
            "source_kind": str(getattr(item, "source_kind", "") or ""),
            "provenance": _protobuf_struct_to_dict(getattr(item, "provenance", None)),
        }

    def _linked_entity_payload(self, item: Any) -> dict[str, object]:
        return {
            "entity_key": str(getattr(item, "entity_key", "") or ""),
            "entity_type": str(getattr(item, "entity_type", "") or ""),
            "label": str(getattr(item, "label", "") or ""),
            "aliases": [str(value) for value in list(getattr(item, "aliases", []) or [])],
            "confidence": float(getattr(item, "confidence", 0.0) or 0.0),
            "metadata": _protobuf_struct_to_dict(getattr(item, "metadata", None)),
        }

    def _graph_relation_payload(self, item: Any) -> dict[str, object]:
        return {
            "relation_key": str(getattr(item, "relation_key", "") or ""),
            "relation_type": str(getattr(item, "relation_type", "") or ""),
            "source_entity_key": str(getattr(item, "source_entity_key", "") or ""),
            "target_entity_key": str(getattr(item, "target_entity_key", "") or ""),
            "weight": float(getattr(item, "weight", 0.0) or 0.0),
            "metadata": _protobuf_struct_to_dict(getattr(item, "metadata", None)),
        }

    def _answer_plan_payload(self, item: Any) -> dict[str, object]:
        if item is None:
            return {}
        return {
            "user_intent": str(getattr(item, "user_intent", "") or ""),
            "recommended_action_mode": str(getattr(item, "recommended_action_mode", "") or ""),
            "authoritative_sources": [str(value) for value in list(getattr(item, "authoritative_sources", []) or [])],
            "supporting_sources": [str(value) for value in list(getattr(item, "supporting_sources", []) or [])],
            "required_verifications": [str(value) for value in list(getattr(item, "required_verifications", []) or [])],
            "open_conflicts": [str(value) for value in list(getattr(item, "open_conflicts", []) or [])],
            "uncertainty_level": str(getattr(item, "uncertainty_level", "") or ""),
        }

    def _judge_result_payload(self, item: Any) -> dict[str, object]:
        if item is None:
            return {}
        metrics = getattr(item, "metrics", None)
        return {
            "status": str(getattr(item, "status", "") or ""),
            "reasons": [str(value) for value in list(getattr(item, "reasons", []) or [])],
            "warnings": [str(value) for value in list(getattr(item, "warnings", []) or [])],
            "citation_coverage": float(getattr(item, "citation_coverage", 0.0) or 0.0),
            "citation_span_precision": float(getattr(item, "citation_span_precision", 0.0) or 0.0),
            "contradiction_escape_rate": float(getattr(item, "contradiction_escape_rate", 0.0) or 0.0),
            "policy_compliance": float(getattr(item, "policy_compliance", 0.0) or 0.0),
            "uncertainty_marked": bool(getattr(item, "uncertainty_marked", False)),
            "requires_review": bool(getattr(item, "requires_review", False)),
            "safe_response": str(getattr(item, "safe_response", "") or ""),
            "metrics": (
                {str(key): float(value or 0.0) for key, value in metrics.items()}
                if isinstance(metrics, Mapping)
                else {}
            ),
        }

    def _validate_remote_bundle_payload(self, payload: dict[str, Any]) -> None:
        required_string_fields = (
            "normalized_query",
            "query_intent",
            "route",
            "strategy",
            "effective_engine",
            "uncertainty_level",
            "recommended_action_mode",
        )
        required_list_fields = (
            "selected_hits",
            "candidate_hits",
            "trace_hits",
            "authoritative_evidence",
            "supporting_evidence",
            "linked_entities",
            "graph_relations",
            "subqueries",
            "open_conflicts",
            "uncertainty_notes",
            "required_verifications",
        )
        for field_name in required_string_fields:
            if not str(payload.get(field_name) or "").strip():
                raise RuntimeError(f"grpc_retrieval_engine_invalid_bundle_contract:{field_name}")
        for field_name in required_list_fields:
            if not isinstance(payload.get(field_name), list):
                raise RuntimeError(f"grpc_retrieval_engine_invalid_bundle_contract:{field_name}")
        if "graph_hops" not in payload or "grounding_score" not in payload:
            raise RuntimeError("grpc_retrieval_engine_invalid_bundle_contract:scalars")
        if not isinstance(payload.get("fallback_used"), bool):
            raise RuntimeError("grpc_retrieval_engine_invalid_bundle_contract:fallback_used")
        if payload.get("answer_plan") is not None and not isinstance(payload.get("answer_plan"), dict):
            raise RuntimeError("grpc_retrieval_engine_invalid_bundle_contract:answer_plan")
        if payload.get("judge_result") is not None and not isinstance(payload.get("judge_result"), dict):
            raise RuntimeError("grpc_retrieval_engine_invalid_bundle_contract:judge_result")

    def _request_metadata(self, *, envelope: QueryEnvelope | None) -> Any:
        if self._metadata_pb2 is None:
            raise RuntimeError("retrieval-engine metadata stubs are unavailable")
        return self._metadata_pb2.RequestMetadata(
            agent_id=((envelope.agent_id if envelope is not None else self.selection.agent_id) or "").strip(),
            task_id=str(envelope.task_id) if envelope is not None and envelope.task_id is not None else "",
            user_id=str(envelope.user_id) if envelope is not None and envelope.user_id is not None else "",
            labels={
                "internal_rpc_mode": self.selection.mode,
            },
        )

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


def build_retrieval_engine_client(*, agent_id: str | None = None) -> RetrievalEngineClient:
    """Build the Rust retrieval-engine client."""

    selection = select_engine_backend(mode=config.INTERNAL_RPC_MODE, agent_id=agent_id)
    return GrpcRetrievalEngineClient(selection=selection)
