"""Script library with canonical semantic search and auto-extraction."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from functools import partial
from typing import Any, cast

from koda.config import AGENT_ID, STATE_BACKEND
from koda.logging_config import get_logger
from koda.services.cache_config import (
    SCRIPT_AUTO_EXTRACT,
    SCRIPT_LIBRARY_ENABLED,
    SCRIPT_MAX_PER_USER,
    SCRIPT_SEARCH_MAX_RESULTS,
    SCRIPT_SEARCH_THRESHOLD,
)
from koda.state.agent_scope import normalize_agent_scope
from koda.state.asset_store import disable_asset, upsert_asset
from koda.state.script_store import (
    script_deactivate,
    script_get,
    script_get_stats,
    script_insert,
    script_list_by_user,
    script_list_for_semantic_index,
    script_record_use,
    script_update_quality,
)

log = get_logger(__name__)


def _build_sentence_transformer() -> Any:
    from sentence_transformers import SentenceTransformer

    from koda.memory.config import MEMORY_EMBEDDING_MODEL

    return SentenceTransformer(MEMORY_EMBEDDING_MODEL)


_CODE_BLOCK_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
_FUNC_CLASS_RE = re.compile(r"^\s*(?:def|class|function|const|let|var|export)\s+(\w+)", re.MULTILINE)
_COMMENT_RE = re.compile(r"^\s*(?:#|//|/\*)\s*(.+?)(?:\*/)?$", re.MULTILINE)


@dataclass
class ScriptSearchResult:
    script_id: int
    title: str
    description: str | None
    language: str | None
    content: str
    similarity: float
    quality_score: float
    use_count: int


class ScriptManager:
    """Manages reusable script library with canonical semantic search."""

    def __init__(self, agent_id: str | None = None) -> None:
        self._agent_id = normalize_agent_scope(agent_id, fallback=AGENT_ID)
        self._model: Any = None
        self._model_lock = asyncio.Lock()
        self._initialized = False

    def _agent_scope(self) -> str:
        return normalize_agent_scope(self._agent_id, fallback=AGENT_ID)

    def _primary_mode(self) -> bool:
        return STATE_BACKEND == "postgres"

    def _similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        numerator = sum(float(a) * float(b) for a, b in zip(left, right, strict=False))
        left_norm = sum(float(value) * float(value) for value in left) ** 0.5
        right_norm = sum(float(value) * float(value) for value in right) ** 0.5
        if left_norm <= 0 or right_norm <= 0:
            return 0.0
        return float(max(0.0, min(1.0, numerator / (left_norm * right_norm))))

    def _search_text(self, *, title: str, description: str | None, language: str | None) -> str:
        return f"{title} {description or ''} {language or ''}".strip()

    def _asset_payload(
        self,
        *,
        script_id: int,
        title: str,
        description: str | None,
        language: str | None,
        content: str,
        quality_score: float,
        use_count: int,
        source_query: str | None = None,
        enabled: bool = True,
    ) -> None:
        upsert_asset(
            asset_key=f"script:{script_id}",
            title=title,
            kind="script",
            content_text=f"{title}\n{description or ''}\n{language or ''}\n{content[:2000]}".strip(),
            body={
                "agent_id": self._agent_scope(),
                "script_id": script_id,
                "description": description,
                "language": language,
                "quality_score": round(float(quality_score), 4),
                "use_count": int(use_count),
                "source_query": source_query or "",
                "enabled": enabled,
            },
            enabled=enabled,
            agent_id=self._agent_scope(),
        )

    async def initialize(self, memory_store: object | None = None) -> None:
        if not SCRIPT_LIBRARY_ENABLED:
            log.info("script_library_disabled")
            return
        if memory_store is not None:
            if hasattr(memory_store, "_get_model_safe"):
                self._model = await memory_store._get_model_safe()  # type: ignore[union-attr]
            elif hasattr(memory_store, "_model"):
                self._model = memory_store._model  # type: ignore[union-attr]
        if not self._primary_mode():
            log.warning("script_manager_primary_required", agent_id=self._agent_scope())
            self._initialized = False
            return
        self._initialized = True
        log.info("script_manager_initialized_primary", agent_id=self._agent_scope())

    async def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        async with self._model_lock:
            if self._model is None:
                loop = asyncio.get_running_loop()
                self._model = await loop.run_in_executor(None, _build_sentence_transformer)
        return self._model

    def _embed_sync(self, text: str) -> list[float]:
        if self._model is None:
            self._model = _build_sentence_transformer()
        result: list[float] = self._model.encode(text, normalize_embeddings=True).tolist()
        return result

    def _embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._model is None:
            self._model = _build_sentence_transformer()
        result = self._model.encode(texts, normalize_embeddings=True)
        return [list(vector) for vector in result.tolist()]

    async def save(
        self,
        user_id: int,
        title: str,
        description: str | None,
        content: str,
        language: str | None = None,
        tags: list[str] | None = None,
        source_query: str | None = None,
    ) -> int | None:
        if not SCRIPT_LIBRARY_ENABLED or not self._initialized:
            return None
        agent_scope = self._agent_scope()
        existing = script_list_by_user(user_id, limit=SCRIPT_MAX_PER_USER + 1, agent_id=agent_scope)
        if len(existing) >= SCRIPT_MAX_PER_USER:
            log.warning("script_limit_reached", user_id=user_id)
            return None
        row_id = script_insert(
            user_id,
            title,
            description,
            language,
            content,
            source_query,
            json.dumps(tags or []),
            agent_scope,
        )
        if row_id:
            try:
                self._asset_payload(
                    script_id=row_id,
                    title=title,
                    description=description,
                    language=language,
                    content=content,
                    quality_score=0.5,
                    use_count=0,
                    source_query=source_query,
                    enabled=True,
                )
            except Exception:
                log.exception("script_asset_upsert_error", script_id=row_id)
        return cast(int | None, row_id)

    async def _search_canonical(
        self,
        *,
        query: str,
        user_id: int,
        language: str | None,
        max_results: int,
    ) -> list[ScriptSearchResult]:
        agent_scope = self._agent_scope()
        fetch_limit = max(max_results * 4, max_results)
        canonical_rows = script_list_for_semantic_index(user_id, limit=fetch_limit, agent_id=agent_scope)
        if language:
            canonical_rows = [row for row in canonical_rows if str(row.get("language") or "") == language]
        if not canonical_rows:
            return []
        await self._get_model()
        loop = asyncio.get_running_loop()
        query_embedding = await loop.run_in_executor(None, partial(self._embed_sync, query))
        search_texts = [
            self._search_text(
                title=str(row.get("title") or ""),
                description=cast(str | None, row.get("description")),
                language=cast(str | None, row.get("language")),
            )
            for row in canonical_rows
        ]
        candidate_embeddings = await loop.run_in_executor(None, partial(self._embed_batch_sync, search_texts))
        matches: list[ScriptSearchResult] = []
        for row, candidate_embedding in zip(canonical_rows, candidate_embeddings, strict=True):
            similarity = self._similarity(query_embedding, candidate_embedding)
            if similarity < SCRIPT_SEARCH_THRESHOLD:
                continue
            matches.append(
                ScriptSearchResult(
                    script_id=int(row["id"]),
                    title=str(row.get("title") or ""),
                    description=cast(str | None, row.get("description")),
                    language=cast(str | None, row.get("language")),
                    content=str(row.get("content") or ""),
                    similarity=similarity,
                    quality_score=float(row.get("quality_score") or 0.5),
                    use_count=int(row.get("use_count") or 0),
                )
            )
        matches.sort(key=lambda item: (-item.similarity, -item.quality_score, -item.use_count, item.title.lower()))
        return matches[:max_results]

    async def search(
        self,
        query: str,
        user_id: int,
        language: str | None = None,
        max_results: int | None = None,
    ) -> list[ScriptSearchResult]:
        if not SCRIPT_LIBRARY_ENABLED or not self._initialized:
            return []
        return await self._search_canonical(
            query=query,
            user_id=user_id,
            language=language,
            max_results=max_results or SCRIPT_SEARCH_MAX_RESULTS,
        )

    async def auto_extract(self, query: str, response: str, user_id: int) -> list[int]:
        if not SCRIPT_LIBRARY_ENABLED or not SCRIPT_AUTO_EXTRACT or not self._initialized:
            return []
        saved_ids: list[int] = []
        for match in _CODE_BLOCK_RE.finditer(response):
            language = match.group(1) or None
            content = match.group(2).strip()
            if content.count("\n") < 5:
                continue
            if language and language.lower() in ("text", "output", "log", "console"):
                continue
            row_id = await self.save(
                user_id=user_id,
                title=_extract_title(content, language),
                description=query[:200],
                content=content,
                language=language,
                source_query=query[:500],
            )
            if row_id:
                saved_ids.append(row_id)
        return saved_ids

    async def record_use(self, script_id: int) -> None:
        script_record_use(script_id, agent_id=self._agent_scope())
        try:
            row = script_get(script_id, agent_id=self._agent_scope())
            if row is not None and len(row) > 13 and bool(row[13]):
                self._asset_payload(
                    script_id=script_id,
                    title=str(row[2]) if len(row) > 2 else "",
                    description=cast(str | None, row[3] if len(row) > 3 else None),
                    language=cast(str | None, row[4] if len(row) > 4 else None),
                    content=str(row[5]) if len(row) > 5 else "",
                    quality_score=float(row[10]) if len(row) > 10 else 0.5,
                    use_count=int(row[8]) if len(row) > 8 else 0,
                    source_query=cast(str | None, row[6] if len(row) > 6 else None),
                )
        except Exception:
            log.exception("script_record_use_sync_error", script_id=script_id)

    async def update_quality(self, script_id: int, delta: float) -> None:
        script_update_quality(script_id, delta, agent_id=self._agent_scope())
        try:
            row = script_get(script_id, agent_id=self._agent_scope())
            if row is not None and len(row) > 13 and bool(row[13]):
                self._asset_payload(
                    script_id=script_id,
                    title=str(row[2]) if len(row) > 2 else "",
                    description=cast(str | None, row[3] if len(row) > 3 else None),
                    language=cast(str | None, row[4] if len(row) > 4 else None),
                    content=str(row[5]) if len(row) > 5 else "",
                    quality_score=float(row[10]) if len(row) > 10 else 0.5,
                    use_count=int(row[8]) if len(row) > 8 else 0,
                    source_query=cast(str | None, row[6] if len(row) > 6 else None),
                )
        except Exception:
            log.exception("script_quality_sync_error", script_id=script_id)

    async def deactivate(self, script_id: int, user_id: int) -> bool:
        deactivated = bool(script_deactivate(script_id, user_id, agent_id=self._agent_scope()))
        if deactivated:
            try:
                disable_asset(f"script:{script_id}", agent_id=self._agent_scope())
            except Exception:
                log.exception("script_asset_disable_error", script_id=script_id)
        return deactivated

    async def list_scripts(self, user_id: int, language: str | None = None, limit: int = 50) -> list[tuple]:
        rows = script_list_by_user(user_id, language=language, limit=limit, agent_id=self._agent_scope())
        return cast(list[tuple[Any, ...]], rows)

    async def get_stats(self, user_id: int) -> dict:
        return cast(dict[Any, Any], script_get_stats(user_id, agent_id=self._agent_scope()))


def _extract_title(content: str, language: str | None) -> str:
    func_match = _FUNC_CLASS_RE.search(content)
    if func_match:
        return func_match.group(1)
    comment_match = _COMMENT_RE.search(content)
    if comment_match:
        return comment_match.group(1).strip()[:80]
    lang_label = language or "code"
    first_line = content.split("\n")[0].strip()[:60]
    return f"{lang_label}: {first_line}" if first_line else f"{lang_label} snippet"


_MANAGERS: dict[str, ScriptManager] = {}


def get_script_manager(agent_id: str | None = None) -> ScriptManager:
    scope = normalize_agent_scope(agent_id, fallback=AGENT_ID)
    manager = _MANAGERS.get(scope)
    if manager is None:
        manager = ScriptManager(scope)
        _MANAGERS[scope] = manager
    return manager
