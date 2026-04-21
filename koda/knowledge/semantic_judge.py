"""Heuristic semantic judge used to augment deterministic answer validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from koda.knowledge.config import KNOWLEDGE_SEMANTIC_JUDGE_SUPPORT_THRESHOLD
from koda.knowledge.types import GroundedAnswer, KnowledgeResolution

_WORD_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "com",
    "da",
    "de",
    "do",
    "e",
    "em",
    "for",
    "in",
    "no",
    "na",
    "o",
    "os",
    "para",
    "por",
    "the",
    "to",
    "um",
    "uma",
}
_OPERATIONAL_HINTS = (
    "applied",
    "assigned",
    "changed",
    "completed",
    "confirmed",
    "created",
    "deployed",
    "executed",
    "moved",
    "restarted",
    "rolled back",
    "transitioned",
    "updated",
    "validado",
    "confirmado",
    "alterado",
    "atualizado",
    "executado",
    "concluido",
)
_UNCERTAINTY_HINTS = ("incerte", "nao posso confirmar", "revis", "review", "conflit", "stale", "duvida")


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in _WORD_RE.findall(text) if token.lower() not in _STOP_WORDS}


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left))


@dataclass(slots=True)
class SemanticJudgeReport:
    support_ratio: float
    contradiction_risk: float
    uncertainty_behavior_score: float
    unsupported_claims: list[str] = field(default_factory=list)
    supported_claims: list[str] = field(default_factory=list)
    claim_count: int = 0
    requires_review: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "support_ratio": round(self.support_ratio, 4),
            "contradiction_risk": round(self.contradiction_risk, 4),
            "uncertainty_behavior_score": round(self.uncertainty_behavior_score, 4),
            "unsupported_claims": list(self.unsupported_claims),
            "supported_claims": list(self.supported_claims),
            "claim_count": self.claim_count,
            "requires_review": self.requires_review,
        }


class KnowledgeSemanticJudgeService:
    """Estimate whether answer claims are semantically supported by grounded evidence."""

    def __init__(self, *, support_threshold: float = KNOWLEDGE_SEMANTIC_JUDGE_SUPPORT_THRESHOLD) -> None:
        self._support_threshold = max(0.1, min(1.0, float(support_threshold)))

    def evaluate(
        self,
        *,
        grounded_answer: GroundedAnswer,
        resolution: KnowledgeResolution | None,
        had_write: bool,
    ) -> SemanticJudgeReport:
        if resolution is None:
            return SemanticJudgeReport(
                support_ratio=0.0,
                contradiction_risk=1.0 if had_write else 0.0,
                uncertainty_behavior_score=1.0 if grounded_answer.uncertainty_notes else 0.0,
                unsupported_claims=["knowledge resolution unavailable"] if had_write else [],
                claim_count=1 if had_write else 0,
                requires_review=had_write,
            )

        claims = self._claims_from_answer(grounded_answer.answer_text)
        if not claims:
            return SemanticJudgeReport(
                support_ratio=1.0,
                contradiction_risk=0.0,
                uncertainty_behavior_score=self._uncertainty_behavior(grounded_answer, resolution),
                claim_count=0,
            )

        evidence_corpus = self._evidence_corpus(resolution)
        supported: list[str] = []
        unsupported: list[str] = []
        for claim in claims:
            claim_tokens = _tokenize(claim)
            support = max((_overlap(claim_tokens, evidence_tokens) for evidence_tokens in evidence_corpus), default=0.0)
            if support >= self._support_threshold:
                supported.append(claim)
            else:
                unsupported.append(claim)

        claim_count = len(claims)
        support_ratio = len(supported) / claim_count if claim_count else 1.0
        uncertainty_behavior_score = self._uncertainty_behavior(grounded_answer, resolution)
        contradiction_risk = (
            1.0 if list(getattr(resolution, "conflicts", []) or []) and uncertainty_behavior_score < 1.0 else 0.0
        )
        requires_review = had_write and (support_ratio < self._support_threshold or contradiction_risk > 0.0)
        return SemanticJudgeReport(
            support_ratio=support_ratio,
            contradiction_risk=contradiction_risk,
            uncertainty_behavior_score=uncertainty_behavior_score,
            unsupported_claims=unsupported,
            supported_claims=supported,
            claim_count=claim_count,
            requires_review=requires_review,
        )

    def _claims_from_answer(self, answer_text: str) -> list[str]:
        claims: list[str] = []
        for sentence in _SENTENCE_SPLIT_RE.split(answer_text):
            clean = sentence.strip(" -\t\r\n")
            if len(clean) < 12:
                continue
            lowered = clean.lower()
            if any(hint in lowered for hint in _OPERATIONAL_HINTS):
                claims.append(clean)
        return claims[:8]

    def _evidence_corpus(self, resolution: KnowledgeResolution) -> list[set[str]]:
        corpus: list[set[str]] = []
        for hit in list(getattr(resolution, "hits", []) or [])[:8]:
            entry = getattr(hit, "entry", None)
            title = str(getattr(entry, "title", "") or getattr(hit, "title", "") or "")
            content = str(getattr(entry, "content", "") or getattr(hit, "content", "") or "")
            source_label = str(getattr(entry, "source_label", "") or getattr(hit, "source_label", "") or "")
            corpus.append(_tokenize(f"{title} {content} {source_label}"))
        for item in list(getattr(resolution, "authoritative_sources", []) or [])[:6]:
            excerpt = getattr(item, "excerpt", "")
            source_label = getattr(item, "source_label", "")
            title = getattr(item, "title", "")
            corpus.append(_tokenize(f"{title} {excerpt} {source_label}"))
        return [tokens for tokens in corpus if tokens]

    def _uncertainty_behavior(self, grounded_answer: GroundedAnswer, resolution: KnowledgeResolution) -> float:
        if not list(getattr(resolution, "conflicts", []) or []) and not bool(
            getattr(resolution, "stale_sources_present", False)
        ):
            return 1.0
        if grounded_answer.uncertainty_notes:
            return 1.0
        lowered = grounded_answer.answer_text.lower()
        return 1.0 if any(hint in lowered for hint in _UNCERTAINTY_HINTS) else 0.0
