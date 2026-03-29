"""Response cache with exact hash and canonical semantic matching."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any

from koda.config import AGENT_ID, STATE_BACKEND
from koda.logging_config import get_logger
from koda.services.cache_config import (
    CACHE_ENABLED,
    CACHE_FUZZY_SUGGEST_THRESHOLD,
    CACHE_FUZZY_THRESHOLD,
    CACHE_TTL_DAYS,
)
from koda.state.agent_scope import normalize_agent_scope
from koda.state.cache_store import (
    cache_get_by_id,
    cache_get_stats,
    cache_invalidate_entry,
    cache_invalidate_user,
    cache_list_active_entries,
    cache_lookup_by_hash,
    cache_record_hit,
    cache_upsert,
)

log = get_logger(__name__)
_MANAGERS: dict[str, CacheManager] = {}


def _build_sentence_transformer() -> Any:
    from sentence_transformers import SentenceTransformer

    from koda.memory.config import MEMORY_EMBEDDING_MODEL

    return SentenceTransformer(MEMORY_EMBEDDING_MODEL)


_CONVERSATIONAL_PREFIXES = re.compile(
    r"^(por favor|pode|preciso que|quero que|gostaria que|please|can you|could you|i need you to|i want you to)\s+",
    re.I,
)
_TEMPORAL_INDICATORS = re.compile(
    r"\b(agora|hoje|atual|latest|current|now|today|right now|neste momento|acabou de)\b",
    re.I,
)
_VOLATILE_INDICATORS = re.compile(
    r"\b(git status|git log|git diff|ps aux|top|htop|uptime|free -|df -|who\b|w\b)\b",
    re.I,
)
_PROVIDER_ERROR_INDICATORS = re.compile(
    (
        r"failed to authenticate|authentication(?:_error)?|invalid authentication credentials|"
        r"api error:\s*401|not logged in|login required|"
        r"claude authentication failed|codex authentication failed|"
        r"<b>autenticação</b>|o provedor está sem credenciais válidas|"
        r"unexpected argument|unrecognized option|unknown option|"
        r"usage:\s+(?:claude|codex)\b"
    ),
    re.IGNORECASE,
)


@dataclass
class CacheLookupResult:
    cache_id: int
    response: str
    match_type: str
    similarity: float
    original_cost_usd: float


def normalize_query(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = _CONVERSATIONAL_PREFIXES.sub("", text).strip()
    return text


def query_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_cache_scope_fingerprint(
    *,
    agent_id: str | None,
    work_dir: str,
    source_scope: tuple[str, ...] = (),
    strategy_version: str = "",
    model_family: str = "",
) -> str:
    try:
        workspace_root = str(Path(work_dir).expanduser().resolve())
    except Exception:
        workspace_root = str(work_dir or "").strip()
    payload = {
        "agent_id": normalize_agent_scope(agent_id, fallback="default"),
        "workspace_root": workspace_root,
        "source_scope": list(source_scope),
        "strategy_version": str(strategy_version or "").strip().lower(),
        "model_family": str(model_family or "").strip().lower(),
    }
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def scoped_query_hash(normalized: str, *, scope_fingerprint: str = "") -> str:
    if not scope_fingerprint:
        return query_hash(normalized)
    return hashlib.sha256(f"{scope_fingerprint}:{normalized}".encode()).hexdigest()


def should_cache(query: str, response: str, is_continuation: bool = False) -> bool:
    if is_continuation or len(response) < 50:
        return False
    if response.startswith("Error") or response.startswith("❌") or looks_like_provider_error_response(response):
        return False
    if _TEMPORAL_INDICATORS.search(query) or "<agent_cmd" in response:
        return False
    return not _VOLATILE_INDICATORS.search(query)


def looks_like_provider_error_response(response: str) -> bool:
    return bool(_PROVIDER_ERROR_INDICATORS.search(response or ""))


class CacheManager:
    """Manages response cache with exact and canonical semantic matching."""

    def __init__(self, agent_id: str | None = None) -> None:
        self._agent_id = normalize_agent_scope(agent_id, fallback=AGENT_ID)
        self._model: Any = None
        self._model_lock = asyncio.Lock()
        self._initialized = False

    def _agent_scope(self) -> str:
        return normalize_agent_scope(self._agent_id, fallback=AGENT_ID)

    def _primary_mode(self) -> bool:
        return STATE_BACKEND == "postgres"

    def _workspace_root(self, work_dir: str) -> str:
        try:
            return str(Path(work_dir).expanduser().resolve())
        except Exception:
            return str(work_dir or "").strip()

    def _similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        numerator = sum(float(a) * float(b) for a, b in zip(left, right, strict=False))
        left_norm = sum(float(value) * float(value) for value in left) ** 0.5
        right_norm = sum(float(value) * float(value) for value in right) ** 0.5
        if left_norm <= 0 or right_norm <= 0:
            return 0.0
        return float(max(0.0, min(1.0, numerator / (left_norm * right_norm))))

    async def initialize(self, memory_store: object | None = None) -> None:
        if not CACHE_ENABLED:
            log.info("cache_disabled")
            return
        if memory_store is not None:
            if hasattr(memory_store, "_get_model_safe"):
                self._model = await memory_store._get_model_safe()  # type: ignore[union-attr]
            elif hasattr(memory_store, "_model"):
                self._model = memory_store._model  # type: ignore[union-attr]
        if not self._primary_mode():
            log.warning("cache_manager_primary_required", agent_id=self._agent_scope())
            self._initialized = False
            return
        self._initialized = True
        log.info("cache_manager_initialized_primary", agent_id=self._agent_scope())

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

    def _embed_sync_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._model is None:
            self._model = _build_sentence_transformer()
        result = self._model.encode(texts, normalize_embeddings=True)
        return [list(vector) for vector in result.tolist()]

    async def lookup(
        self,
        query: str,
        user_id: int,
        *,
        work_dir: str = "",
        source_scope: tuple[str, ...] = (),
        strategy_version: str = "",
        model_family: str = "",
    ) -> CacheLookupResult | None:
        if not CACHE_ENABLED or not self._initialized:
            return None

        normalized = normalize_query(query)
        scope_fingerprint = build_cache_scope_fingerprint(
            agent_id=self._agent_scope(),
            work_dir=work_dir,
            source_scope=source_scope,
            strategy_version=strategy_version,
            model_family=model_family,
        )
        qhash = scoped_query_hash(normalized, scope_fingerprint=scope_fingerprint)
        row = cache_lookup_by_hash(user_id, qhash, agent_id=self._agent_scope())
        if row:
            cache_id, response, cost_usd = row
            if looks_like_provider_error_response(response):
                cache_invalidate_entry(cache_id, agent_id=self._agent_scope())
                log.warning("cache_poisoned_exact_entry_invalidated", user_id=user_id, cache_id=cache_id)
                return None
            cache_record_hit(cache_id, agent_id=self._agent_scope())
            return CacheLookupResult(
                cache_id=cache_id,
                response=response,
                match_type="exact",
                similarity=1.0,
                original_cost_usd=cost_usd,
            )
        return await self._lookup_primary_semantic(
            normalized=normalized,
            user_id=user_id,
            work_dir=work_dir,
            source_scope=source_scope,
            strategy_version=strategy_version,
            model_family=model_family,
        )

    async def _lookup_primary_semantic(
        self,
        *,
        normalized: str,
        user_id: int,
        work_dir: str,
        source_scope: tuple[str, ...],
        strategy_version: str,
        model_family: str,
    ) -> CacheLookupResult | None:
        if source_scope or strategy_version or model_family:
            return None
        try:
            rows = cache_list_active_entries(user_id, limit=64, agent_id=self._agent_scope())
        except RuntimeError:
            log.warning("cache_primary_backend_unavailable", agent_id=self._agent_scope(), user_id=user_id)
            return None
        if not rows:
            return None
        workspace_root = self._workspace_root(work_dir)
        if workspace_root:
            rows = [
                row
                for row in rows
                if not str(row.get("work_dir") or "").strip()
                or self._workspace_root(str(row.get("work_dir") or "")) == workspace_root
            ]
        if not rows:
            return None
        await self._get_model()
        loop = asyncio.get_running_loop()
        query_embedding = await loop.run_in_executor(None, partial(self._embed_sync, normalized))
        candidate_queries = [normalize_query(str(row.get("query_text") or "")) for row in rows]
        candidate_embeddings = await loop.run_in_executor(None, partial(self._embed_sync_batch, candidate_queries))
        best_match: tuple[dict[str, Any], float] | None = None
        for row, candidate_embedding in zip(rows, candidate_embeddings, strict=True):
            similarity = self._similarity(query_embedding, candidate_embedding)
            if best_match is None or similarity > best_match[1]:
                best_match = (row, similarity)
        if best_match is None:
            return None
        row, similarity = best_match
        if similarity < CACHE_FUZZY_SUGGEST_THRESHOLD:
            return None
        canonical_row = cache_get_by_id(int(row["id"]), agent_id=self._agent_scope())
        if canonical_row is None:
            cache_invalidate_entry(int(row["id"]), agent_id=self._agent_scope())
            return None
        response, cost_usd = canonical_row
        response = str(response or "")
        if not response or looks_like_provider_error_response(response):
            cache_invalidate_entry(int(row["id"]), agent_id=self._agent_scope())
            return None
        match_type = "fuzzy_auto" if similarity >= CACHE_FUZZY_THRESHOLD else "fuzzy_suggest"
        if match_type == "fuzzy_auto":
            cache_record_hit(int(row["id"]), agent_id=self._agent_scope())
        return CacheLookupResult(
            cache_id=int(row["id"]),
            response=response,
            match_type=match_type,
            similarity=similarity,
            original_cost_usd=float(cost_usd or 0.0),
        )

    async def store(
        self,
        user_id: int,
        query: str,
        response: str,
        model: str | None,
        cost_usd: float,
        work_dir: str,
        *,
        source_scope: tuple[str, ...] = (),
        strategy_version: str = "",
        model_family: str = "",
    ) -> int | None:
        if not CACHE_ENABLED or not self._initialized:
            return None
        normalized = normalize_query(query)
        scope_fingerprint = build_cache_scope_fingerprint(
            agent_id=self._agent_scope(),
            work_dir=work_dir,
            source_scope=source_scope,
            strategy_version=strategy_version,
            model_family=model_family,
        )
        qhash = scoped_query_hash(normalized, scope_fingerprint=scope_fingerprint)
        expires_at = (datetime.now() + timedelta(days=CACHE_TTL_DAYS)).isoformat()
        return cache_upsert(
            user_id,
            qhash,
            query,
            response,
            model,
            cost_usd,
            work_dir,
            expires_at,
            agent_id=self._agent_scope(),
        )

    async def invalidate_user(self, user_id: int) -> int:
        return cache_invalidate_user(user_id, agent_id=self._agent_scope())

    async def get_stats(self, user_id: int) -> dict:
        return cache_get_stats(user_id, agent_id=self._agent_scope())


def get_cache_manager(agent_id: str | None = None) -> CacheManager:
    scope = normalize_agent_scope(agent_id, fallback=AGENT_ID)
    manager = _MANAGERS.get(scope)
    if manager is None:
        manager = CacheManager(scope)
        _MANAGERS[scope] = manager
    return manager
