"""Multi-model routing based on query complexity estimation."""

import re

from koda.config import DEFAULT_PROVIDER, PROVIDER_TIER_MODELS
from koda.logging_config import get_logger

log = get_logger(__name__)

# Claude tiers
MODEL_HAIKU = PROVIDER_TIER_MODELS["claude"]["small"]
MODEL_SONNET = PROVIDER_TIER_MODELS["claude"]["medium"]
MODEL_OPUS = PROVIDER_TIER_MODELS["claude"]["large"]

# Codex tiers
MODEL_CODEX_SMALL = PROVIDER_TIER_MODELS["codex"]["small"]
MODEL_CODEX_MEDIUM = PROVIDER_TIER_MODELS["codex"]["medium"]
MODEL_CODEX_LARGE = PROVIDER_TIER_MODELS["codex"]["large"]

# Complexity indicators
_CODE_PATTERNS = re.compile(
    r"```|def\s+|class\s+|function\s+|import\s+|#include|"
    r"SELECT\s+|CREATE\s+|ALTER\s+",
    re.IGNORECASE,
)
_COMPLEX_KEYWORDS = re.compile(
    r"refactor|architect|design|optimize|debug|analyze|review|explain.*complex|"
    r"implement|migration|security|performance|benchmark",
    re.IGNORECASE,
)
_SIMPLE_KEYWORDS = re.compile(
    r"^(hi|hello|hey|thanks|ok|yes|no|what is|define|translate)\b",
    re.IGNORECASE,
)
_TOOL_QUERY_PATTERNS = re.compile(
    r"(?:tarefas?|tasks?|issues?|bugs?|tickets?|jira|sprint|board|backlog|kanban)"
    r"|(?:busca|search|lista|list|mostra|show|quais|which|status)"
    r"|(?:em progresso|in progress|to do|conclu[ií]|done|pendente)",
    re.IGNORECASE,
)


def estimate_complexity(
    query: str,
    *,
    provider: str = DEFAULT_PROVIDER,
    has_images: bool = False,
) -> str:
    """Estimate query complexity and return a model for the selected provider."""
    query_len = len(query)
    line_count = query.count("\n") + 1
    code_matches = len(_CODE_PATTERNS.findall(query))
    has_complex_keywords = bool(_COMPLEX_KEYWORDS.search(query))
    is_simple = bool(_SIMPLE_KEYWORDS.match(query.strip()))

    # Score-based routing
    score = 0

    # Length factors
    if query_len < 100:
        score -= 1
    elif query_len > 1000:
        score += 1
    if query_len > 3000:
        score += 1

    # Line count
    if line_count > 20:
        score += 1
    if line_count > 50:
        score += 1

    # Code presence
    if code_matches > 0:
        score += 1
    if code_matches > 3:
        score += 1

    # Keywords
    if has_complex_keywords:
        score += 2
    if is_simple:
        score -= 2

    # Images always need at least sonnet
    if has_images:
        score = max(score, 1)

    # Tool-oriented queries (Jira lookups, searches) are simple dispatches
    if _TOOL_QUERY_PATTERNS.search(query) and not has_complex_keywords and query_len < 500:
        score -= 1
        log.debug("tool_query_bias_applied")

    provider_key = provider.lower()
    tier_models = PROVIDER_TIER_MODELS.get(provider_key, PROVIDER_TIER_MODELS["claude"])

    # Route based on score
    if score <= -1:
        model = tier_models["small"]
    elif score <= 2:
        model = tier_models["medium"]
    else:
        model = tier_models["large"]

    log.debug(
        "model_routing",
        score=score,
        model=model,
        provider=provider_key,
        query_len=query_len,
        code_matches=code_matches,
    )
    return model


def estimate_model(query: str, provider: str = DEFAULT_PROVIDER, has_images: bool = False) -> str:
    """Provider-aware model estimator kept as an explicit public name."""
    return estimate_complexity(query, provider=provider, has_images=has_images)
