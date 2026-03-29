"""Unified asset reuse registry across scripts and persisted artifact evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from koda.config import AGENT_ID
from koda.knowledge.repository import KnowledgeRepository
from koda.knowledge.storage_v2 import KnowledgeStorageV2
from koda.services.script_manager import ScriptManager, ScriptSearchResult, get_script_manager
from koda.state.agent_scope import normalize_agent_scope
from koda.state.asset_store import search_assets, upsert_asset

_TRUST_WEIGHTS = {
    "high": 1.0,
    "verified": 1.0,
    "medium": 0.8,
    "low": 0.55,
    "untrusted": 0.35,
}
_LOW_SIGNAL_WORDS = {"the", "and", "for", "with", "that", "this", "from", "into", "uma", "para", "com", "que"}
_ASSET_ANCHORS = ("services", "service", "src", "app", "lib", "packages", "tests", "docs")
_ASSET_SUFFIX_STRIP = ".,;:)]}>\"'"
_REGISTRIES: dict[str, AgentAssetRegistry] = {}


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in str(text or "").replace("/", " ").replace("_", " ").replace("-", " ").split()
        if len(token) >= 3 and token.lower() not in _LOW_SIGNAL_WORDS
    }


def _normalize_path(path: str) -> str:
    normalized = str(path or "").strip().strip(_ASSET_SUFFIX_STRIP)
    if not normalized:
        return ""
    parts = [part for part in normalized.split("/") if part and part != "."]
    if not parts:
        return ""
    for anchor in _ASSET_ANCHORS:
        if anchor in parts:
            return "/".join(parts[parts.index(anchor) :])
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[0]


@dataclass(slots=True)
class AgentAssetRef:
    asset_key: str
    asset_kind: str
    title: str
    score: float
    reuse_reason: str
    source_path: str | None = None
    source_url: str | None = None
    modality: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_key": self.asset_key,
            "asset_kind": self.asset_kind,
            "title": self.title,
            "score": round(self.score, 4),
            "reuse_reason": self.reuse_reason,
            "source_path": self.source_path,
            "source_url": self.source_url,
            "modality": self.modality,
            "metadata": dict(self.metadata),
        }


class AgentAssetRegistry:
    """Rank reusable assets for the current agent/workspace/query context."""

    def __init__(
        self,
        *,
        agent_id: str | None = None,
        storage: KnowledgeStorageV2 | None = None,
        script_manager: ScriptManager | None = None,
    ) -> None:
        self._agent_id = normalize_agent_scope(agent_id, fallback=AGENT_ID)
        self._storage = storage or KnowledgeStorageV2(KnowledgeRepository(self._agent_id), self._agent_id)
        self._script_manager = script_manager or get_script_manager(self._agent_id)

    async def search(
        self,
        *,
        query: str,
        user_id: int,
        work_dir: str = "",
        project_key: str = "",
        workspace_fingerprint: str = "",
        source_scope: tuple[str, ...] = (),
        task_id: int | None = None,
        limit: int = 6,
        script_matches: list[ScriptSearchResult] | None = None,
    ) -> list[dict[str, Any]]:
        query_tokens = _tokenize(query)
        normalized_work_dir = str(work_dir or "").strip()
        if not workspace_fingerprint and normalized_work_dir:
            workspace_fingerprint = _normalize_path(normalized_work_dir) or normalized_work_dir
        refs: list[AgentAssetRef] = []
        stored_assets = search_assets(query=query, limit=max(limit * 2, 8), agent_id=self._agent_id)
        for row in stored_assets:
            stored_ref = self._stored_asset_ref(row=row, query_tokens=query_tokens, workspace_root=normalized_work_dir)
            if stored_ref is not None:
                refs.append(stored_ref)

        if script_matches is None:
            script_matches = await self._script_manager.search(query, user_id, max_results=max(limit, 4))
        for match in script_matches or []:
            ref = self._script_ref(match=match, query_tokens=query_tokens, workspace_root=normalized_work_dir)
            refs.append(ref)
            self._persist_ref(ref)

        artifact_rows = await self._storage.list_artifact_evidence_rows_async(
            task_id=task_id,
            project_key=project_key,
            workspace_fingerprint=workspace_fingerprint,
            limit=max(limit * 2, 8),
        )
        for row in artifact_rows:
            if not self._artifact_allowed(row=row, source_scope=source_scope):
                continue
            artifact_ref = self._artifact_ref(row=row, query_tokens=query_tokens, workspace_root=normalized_work_dir)
            if artifact_ref is not None:
                refs.append(artifact_ref)
                self._persist_ref(artifact_ref)

        deduped: dict[str, AgentAssetRef] = {}
        for ref in refs:
            current = deduped.get(ref.asset_key)
            if current is None or ref.score > current.score:
                deduped[ref.asset_key] = ref

        ranked = sorted(
            deduped.values(),
            key=lambda item: (-item.score, item.asset_kind, item.title.lower()),
        )
        return [item.to_dict() for item in ranked[: max(1, limit)]]

    def _stored_asset_ref(
        self,
        *,
        row: dict[str, Any],
        query_tokens: set[str],
        workspace_root: str,
    ) -> AgentAssetRef | None:
        body = dict(row.get("body") or {})
        title = str(row.get("title") or row.get("asset_key") or "asset")
        content_text = str(row.get("content_text") or "")
        asset_kind = str(row.get("kind") or "asset")
        tokens = _tokenize(f"{title} {content_text}")
        overlap = len(query_tokens & tokens) / max(1, len(query_tokens) or 1)
        stored_score = float(body.get("score") or 0.0)
        score = min(1.0, max(stored_score * 0.7, overlap * 0.45 + stored_score * 0.4))
        if score < 0.2:
            return None
        source_path = _normalize_path(str(body.get("source_path") or workspace_root or ""))
        return AgentAssetRef(
            asset_key=str(row.get("asset_key") or ""),
            asset_kind=asset_kind,
            title=title,
            score=score,
            reuse_reason=str(body.get("reuse_reason") or "registry_match"),
            source_path=source_path or None,
            source_url=str(body.get("source_url") or "") or None,
            modality=str(body.get("modality") or "") or None,
            metadata=body,
        )

    def _persist_ref(self, ref: AgentAssetRef) -> None:
        try:
            upsert_asset(
                asset_key=ref.asset_key,
                title=ref.title,
                kind=ref.asset_kind,
                content_text="\n".join(
                    part for part in [ref.title, ref.source_path or "", ref.source_url or "", ref.reuse_reason] if part
                ),
                body={
                    "score": round(ref.score, 4),
                    "reuse_reason": ref.reuse_reason,
                    "source_path": ref.source_path,
                    "source_url": ref.source_url,
                    "modality": ref.modality,
                    **dict(ref.metadata),
                },
                enabled=True,
                agent_id=self._agent_id,
            )
        except Exception:
            return

    def _script_ref(
        self,
        *,
        match: ScriptSearchResult,
        query_tokens: set[str],
        workspace_root: str,
    ) -> AgentAssetRef:
        content_tokens = _tokenize(f"{match.title} {match.description or ''} {match.content[:400]}")
        overlap = len(query_tokens & content_tokens) / max(1, len(query_tokens) or 1)
        usage_bonus = min(0.15, match.use_count / 40.0)
        quality_bonus = min(0.2, max(0.0, match.quality_score) * 0.2)
        score = min(1.0, max(0.0, match.similarity * 0.65 + overlap * 0.2 + usage_bonus + quality_bonus))
        return AgentAssetRef(
            asset_key=f"script:{match.script_id}",
            asset_kind="script",
            title=match.title,
            score=score,
            reuse_reason="semantic_match",
            source_path=_normalize_path(workspace_root) or None,
            metadata={
                "language": match.language,
                "similarity": round(match.similarity, 4),
                "quality_score": round(match.quality_score, 4),
                "use_count": match.use_count,
            },
        )

    def _artifact_allowed(self, *, row: dict[str, Any], source_scope: tuple[str, ...]) -> bool:
        if not source_scope:
            return True
        metadata = dict(row.get("metadata") or {})
        source_label = str(metadata.get("source_label") or metadata.get("source_scope") or "").strip()
        if not source_label:
            return True
        return source_label in source_scope

    def _artifact_ref(
        self,
        *,
        row: dict[str, Any],
        query_tokens: set[str],
        workspace_root: str,
    ) -> AgentAssetRef | None:
        label = str(row.get("label") or row.get("evidence_key") or "artifact")
        extracted_text = str(row.get("extracted_text") or "")
        asset_tokens = _tokenize(f"{label} {extracted_text}")
        overlap = len(query_tokens & asset_tokens) / max(1, len(query_tokens) or 1)
        confidence = float(row.get("confidence") or 0.0)
        trust_weight = _TRUST_WEIGHTS.get(str(row.get("trust_level") or "").strip().lower(), 0.65)
        workspace_bonus = 0.1 if workspace_root and workspace_root in str(row.get("source_path") or "") else 0.0
        score = confidence * 0.45 + overlap * 0.35 + trust_weight * 0.2 + workspace_bonus
        if score < 0.25:
            return None
        source_path = _normalize_path(str(row.get("source_path") or ""))
        reuse_reason = "multimodal_evidence" if str(row.get("modality") or "").strip() else "artifact_context"
        return AgentAssetRef(
            asset_key=f"artifact:{row.get('evidence_key')}",
            asset_kind="artifact",
            title=label,
            score=min(1.0, score),
            reuse_reason=reuse_reason,
            source_path=source_path or None,
            source_url=str(row.get("source_url") or "") or None,
            modality=str(row.get("modality") or "") or None,
            metadata={
                "confidence": confidence,
                "trust_level": row.get("trust_level"),
                "artifact_id": row.get("artifact_id"),
                "time_span": row.get("time_span"),
            },
        )


def get_agent_asset_registry(agent_id: str | None = None) -> AgentAssetRegistry:
    normalized = normalize_agent_scope(agent_id, fallback=AGENT_ID)
    registry = _REGISTRIES.get(normalized)
    if registry is None:
        registry = AgentAssetRegistry(agent_id=normalized)
        _REGISTRIES[normalized] = registry
    return registry
