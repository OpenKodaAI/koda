"""Cascade routing policy: prefer local runtimes for low-complexity queries.

When ``LOCAL_PREFER_BELOW_COMPLEXITY > 0``, this module reorders the provider
fallback chain so that ``llamacpp`` or ``mlx`` (whichever is available) lands
first for cheap queries, with cloud providers kept as the safety net. Heavy
queries — long contexts, code-heavy refactors, multi-file diffs — bypass the
local hop entirely.

The policy is consulted from
:func:`koda.services.llm_runner.get_provider_fallback_chain`; per-agent
override comes from the agent editor's "Prefer local below" setting.
"""

from __future__ import annotations

from collections.abc import Iterable

from koda.config import AVAILABLE_PROVIDERS
from koda.logging_config import get_logger
from koda.services.model_router import complexity_score
from koda.services.runtime_capabilities import effective_local_prefer_threshold

log = get_logger(__name__)

_LOCAL_PROVIDER_PRIORITY: tuple[str, ...] = ("mlx", "llamacpp", "ollama")


def _first_available_local(eligibility: dict[str, dict[str, object]] | None) -> str | None:
    for candidate in _LOCAL_PROVIDER_PRIORITY:
        if candidate not in AVAILABLE_PROVIDERS:
            continue
        if eligibility is not None:
            entry = eligibility.get(candidate)
            if entry is not None and not bool(entry.get("eligible", False)):
                continue
        return candidate
    return None


def adjust_chain_for_local_preference(
    chain: list[str],
    *,
    query: str,
    has_images: bool = False,
    prefer_below: float | None = None,
    eligibility: dict[str, dict[str, object]] | None = None,
) -> list[str]:
    """Return a possibly-reordered provider chain.

    ``chain`` is the result of the existing ``get_provider_fallback_chain``
    logic. When the policy fires, the chosen local provider is moved to the
    front of the chain (or inserted if it wasn't already eligible). The
    original cloud ordering is preserved as a tail so any failure cascades
    transparently.
    """
    threshold = effective_local_prefer_threshold() if prefer_below is None else float(prefer_below)
    if threshold <= 0:
        return chain
    if has_images:
        # Local Metal stack does not yet ship vision-capable defaults.
        return chain
    score = complexity_score(query, has_images=False)
    if score >= threshold:
        return chain

    candidate = _first_available_local(eligibility)
    if candidate is None:
        return chain

    reordered = [candidate, *(provider for provider in chain if provider != candidate)]
    log.debug(
        "cascade_routing_applied",
        chosen_local=candidate,
        complexity=score,
        threshold=threshold,
        original_head=chain[0] if chain else None,
    )
    return reordered


def is_local_provider(provider_id: str) -> bool:
    return provider_id.strip().lower() in _LOCAL_PROVIDER_PRIORITY


def local_provider_priority() -> Iterable[str]:
    """Public accessor for the cascade priority list (tests + UI)."""
    return _LOCAL_PROVIDER_PRIORITY
