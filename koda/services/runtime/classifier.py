"""Deterministic runtime task classification."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from koda.services.runtime.constants import RUNTIME_CLASSIFICATIONS

_HEAVY_PATTERNS = (
    re.compile(r"\b(playwright|browser|selenium|chrom(e|ium)|headful|screenshot|video|trace)\b", re.I),
    re.compile(r"\b(npm install|pnpm install|yarn install|pip install|poetry install|uv sync)\b", re.I),
    re.compile(r"\b(docker|docker-compose|compose up|server|dev server|start app|open port)\b", re.I),
    re.compile(r"\b(pytest|npm test|playwright test|integration test|e2e|validate)\b", re.I),
)
_STANDARD_PATTERNS = (
    re.compile(r"\b(edit|write|refactor|patch|fix|implement|build|compile|lint|typecheck|unit test)\b", re.I),
    re.compile(r"\b(git|worktree|branch|commit|diff)\b", re.I),
)


@dataclass(slots=True)
class RuntimeClassification:
    classification: str
    isolation: str
    duration: str
    environment_kind: str
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_task(query_text: str, *, override: str | None = None) -> RuntimeClassification:
    """Classify a task into runtime intensity and environment kind."""
    normalized_override = (override or "").strip().lower()
    if normalized_override in RUNTIME_CLASSIFICATIONS:
        classification = normalized_override
        reasons = [f"user_override:{normalized_override}"]
    elif any(pattern.search(query_text) for pattern in _HEAVY_PATTERNS):
        classification = "heavy"
        reasons = ["matched_heavy_keywords"]
    elif any(pattern.search(query_text) for pattern in _STANDARD_PATTERNS):
        classification = "standard"
        reasons = ["matched_standard_keywords"]
    else:
        classification = "light"
        reasons = ["default_light"]

    if classification == "heavy":
        return RuntimeClassification(
            classification="heavy",
            isolation="worktree",
            duration="long",
            environment_kind="dev_worktree_browser",
            reasons=reasons,
        )
    if classification == "standard":
        return RuntimeClassification(
            classification="standard",
            isolation="worktree",
            duration="medium",
            environment_kind="dev_worktree",
            reasons=reasons,
        )
    return RuntimeClassification(
        classification="light",
        isolation="shared",
        duration="short",
        environment_kind="dev_worktree",
        reasons=reasons,
    )
