"""Tests for semantic squad routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from koda.squads.capabilities import CapabilitySummary
from koda.squads.semantic_router import SquadSemanticRouter, reset_semantic_router_cache_for_tests


def _summary(agent_id: str, *, role: str = "", delegate_when: str = "", do_not_delegate: str = "") -> CapabilitySummary:
    return CapabilitySummary(
        agent_id=agent_id,
        display_name=agent_id,
        role=role,
        delegate_when=delegate_when,
        do_not_delegate=do_not_delegate,
    )


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    reset_semantic_router_cache_for_tests()


@pytest.mark.asyncio
async def test_semantic_router_requires_real_embedding_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.squads.semantic_router.resolve_active_embedding_repo", lambda: "local/model")
    monkeypatch.setattr("koda.squads.semantic_router.load_sentence_transformer", lambda _: None)

    def fail_embed(*_: Any) -> list[list[float]]:
        raise AssertionError("hash/embedding fallback should not be called when the real model is missing")

    monkeypatch.setattr("koda.squads.semantic_router.embed_batch_with_model", fail_embed)

    result = await SquadSemanticRouter().rank_agents(
        "lançar página",
        [_summary("FE", role="Interface")],
        squad_id="build",
    )

    assert result.available is False
    assert result.reason == "embedding model unavailable"


@pytest.mark.asyncio
async def test_semantic_router_ranks_multilingual_summaries_without_token_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("koda.squads.semantic_router.resolve_active_embedding_repo", lambda: "local/model")
    monkeypatch.setattr("koda.squads.semantic_router.load_sentence_transformer", lambda _: object())

    def fake_embed(texts: list[str], _: object) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if "campaña" in text:
                vectors.append([1.0, 0.0, 0.0])
            elif "storytelling" in text:
                vectors.append([0.95, 0.0, 0.0])
            elif "interfaz" in text:
                vectors.append([0.1, 0.9, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors

    monkeypatch.setattr("koda.squads.semantic_router.embed_batch_with_model", fake_embed)

    result = await SquadSemanticRouter(min_score=0.2).rank_agents(
        "Necesito una campaña de lanzamiento para clientes nuevos",
        [
            _summary("COPY", role="Content", delegate_when="brand storytelling and launch positioning"),
            _summary("FE", role="Interface", delegate_when="experiencia visual e interfaz"),
        ],
        squad_id="build",
    )

    assert result.available is True
    assert result.top_agents() == ["COPY"]


@pytest.mark.asyncio
async def test_do_not_delegate_penalizes_semantic_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.squads.semantic_router.resolve_active_embedding_repo", lambda: "local/model")
    monkeypatch.setattr("koda.squads.semantic_router.load_sentence_transformer", lambda _: object())

    def fake_embed(texts: list[str], _: object) -> list[list[float]]:
        return [[1.0, 0.0] if "manual bookkeeping" in text or "avoid" in text else [0.9, 0.1] for text in texts]

    monkeypatch.setattr("koda.squads.semantic_router.embed_batch_with_model", fake_embed)

    result = await SquadSemanticRouter(min_score=0.0, negative_penalty=0.8).rank_agents(
        "manual bookkeeping reconciliation",
        [
            _summary("OPS", delegate_when="finance operations", do_not_delegate="avoid manual bookkeeping"),
            _summary("PM", role="Coordinator"),
        ],
        squad_id="build",
        coordinator_agent_id="PM",
    )

    ops_score = next(item for item in result.scores if item.agent_id == "OPS")
    assert ops_score.negative_score > 0.9
    assert ops_score.score < ops_score.positive_score


@pytest.mark.asyncio
async def test_capability_vectors_are_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.squads.semantic_router.resolve_active_embedding_repo", lambda: "local/model")
    monkeypatch.setattr("koda.squads.semantic_router.load_sentence_transformer", lambda _: object())
    batch_sizes: list[int] = []

    def fake_embed(texts: list[str], _: object) -> list[list[float]]:
        batch_sizes.append(len(texts))
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr("koda.squads.semantic_router.embed_batch_with_model", fake_embed)
    router = SquadSemanticRouter(min_score=0.0)
    summaries = [_summary("FE", role="Interface", delegate_when="visual experience")]

    await router.rank_agents("build visual page", summaries, squad_id="build")
    await router.rank_agents("build visual page", summaries, squad_id="build")

    assert batch_sizes[0] == 2
    assert batch_sizes[1] == 1


def test_routing_source_keeps_only_mention_regex() -> None:
    routing_source = Path("koda/squads/routing.py").read_text(encoding="utf-8")
    engine_source = Path("koda/squads/coordinator_engine.py").read_text(encoding="utf-8")

    assert "_COLLABORATION_RE" not in routing_source
    assert "_STOPWORDS" not in routing_source
    assert "_DELIVERABLE_RE" not in engine_source
    assert "_COMPLEX_OBJECT_RE" not in engine_source
    assert "_ROLE_TERMS" not in engine_source
