"""Skills v2 — structured skill definitions and registry."""

from __future__ import annotations

from koda.skills._registry import (
    SkillDefinition,
    SkillRegistry,
    get_shared_registry,
)

__all__ = [
    "SkillDefinition",
    "SkillRegistry",
    "get_shared_registry",
]
