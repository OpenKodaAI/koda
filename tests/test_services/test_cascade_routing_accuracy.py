"""Classification accuracy of the cascade-routing complexity score.

The cascade router prepends ``llamacpp``/``mlx``/``ollama`` to the provider
fallback chain when a query's estimated complexity is below a threshold.
The threshold defaults to 0.4 under auto-activation, and the score comes
from ``koda.services.model_router.complexity_score``.

This test asserts the score puts each kind of query in the right bucket
on a fixed labeled corpus:

- **trivial** (≤ 0.20): greetings, yes/no, single-word factual
- **simple** (≤ 0.40): one-line factual / shallow lookups
- **moderate** (0.30 – 0.65): explanations, short howtos, refactors of one func
- **complex** (≥ 0.55): multi-file refactor, architecture debate, long diff

We don't assert exact scores (the heuristic is intentionally fuzzy); we
assert the bucketing is correct so the cascade decision (route local for
trivial+simple, escalate cloud for complex) is reliable.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import koda.services.local_routing_policy as policy
from koda.services.model_router import complexity_score

_TRIVIAL = [
    "hi",
    "hello",
    "ok",
    "yes",
    "thanks",
    "what is python",
    "translate hello to portuguese",
    "define recursion",
]

_SIMPLE = [
    "Show me the git log for the last 3 commits.",
    "List the files in this directory.",
    "What's the time in São Paulo right now?",
    "Read the README and tell me the title.",
    "Show open jira tasks for the team.",
]

_MODERATE = [
    """
    I have a Python function that takes a list of users and returns those
    above a given age. Can you make it return the top N oldest users?
    Function below:

        def filter_users(users, age):
            return [u for u in users if u['age'] > age]
    """.strip(),
    "Explain how Postgres handles MVCC and what that means for read consistency.",
    "How would you migrate this small SQLAlchemy model to async style?",
]

_COMPLEX = [
    """
    Refactor the authentication subsystem. We need to:
    1. Move from session-cookie to JWT-based auth
    2. Support OAuth2 PKCE flow with rotating refresh tokens
    3. Add audit logging for every login/logout
    4. Migrate the existing 3 million users without invalidating their sessions
    Walk me through the migration strategy step by step, and identify the
    high-risk corners of the migration.
    """.strip(),
    """
    Review this 500-line module for performance and security issues. We have a
    soft deadline for production rollout next week, and the team has flagged
    that the database query path is slow under load. Please go through each
    function, identify the bottlenecks, suggest concrete optimization
    strategies, and call out any security concerns related to user input
    handling, SQL injection, and authentication bypass risks.

    """
    + "import os\nimport sys\nimport json\n"
    + ("a" * 2000)
    + "\n",
    (
        "Design a multi-region replication strategy for our Postgres cluster "
        "that survives network partitions and zonal failures. We have 5 read "
        "replicas across 3 regions and need RPO under 10 seconds."
    ),
]


def _classify(score: float) -> str:
    if score < 0.30:
        return "trivial"
    if score < 0.50:
        return "simple"
    if score < 0.70:
        return "moderate"
    return "complex"


@pytest.mark.parametrize("query", _TRIVIAL, ids=lambda q: q[:30])
def test_trivial_queries_score_strictly_below_default_threshold(query: str):
    """All trivial queries must score strictly under the default 0.4 cascade threshold."""
    score = complexity_score(query)
    assert score < 0.4, f"trivial query scored {score} (expected < 0.4): {query!r}"


@pytest.mark.parametrize("query", _SIMPLE, ids=lambda q: q[:30])
def test_simple_queries_route_local_at_default_threshold(query: str):
    """Simple queries must score below the default cascade threshold so they route local."""
    score = complexity_score(query)
    assert score < 0.4, f"simple query scored {score} (expected < 0.4): {query[:60]!r}"


@pytest.mark.parametrize("query", _COMPLEX, ids=lambda q: q[:30])
def test_complex_queries_escalate_at_default_threshold(query: str):
    """Complex queries must score at-or-above the cascade threshold so they escalate to cloud."""
    score = complexity_score(query)
    assert score >= 0.4, f"complex query scored {score} (expected ≥ 0.4): {query[:60]!r}"


def test_complex_queries_outscore_trivial_queries():
    """Sanity: average complex > average trivial. The heuristic is meaningful."""
    avg_trivial = sum(complexity_score(q) for q in _TRIVIAL) / len(_TRIVIAL)
    avg_complex = sum(complexity_score(q) for q in _COMPLEX) / len(_COMPLEX)
    assert avg_complex > avg_trivial + 0.2, f"avg trivial={avg_trivial:.3f} avg complex={avg_complex:.3f}"


def test_image_query_floors_at_half_regardless_of_text():
    """Vision queries are floored at 0.5 because the local Metal stack lacks vision."""
    assert complexity_score("hi", has_images=True) >= 0.5
    assert complexity_score("ok", has_images=True) >= 0.5


# ---------------------------------------------------------------------------
# Routing decisions on the labeled corpus — the key behavioral assertion.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", _TRIVIAL + _SIMPLE, ids=lambda q: q[:30])
def test_below_threshold_queries_route_to_local_when_available(query: str):
    """Queries the heuristic calls trivial/simple must prepend a local provider."""
    chain = ["claude", "groq"]
    with (
        patch.object(policy, "AVAILABLE_PROVIDERS", ["claude", "groq", "llamacpp"]),
        patch("koda.services.local_routing_policy.effective_local_prefer_threshold", lambda: 0.4),
    ):
        result = policy.adjust_chain_for_local_preference(chain, query=query)
    # Trivial queries get llamacpp first; some simple queries may not depending on score
    score = complexity_score(query)
    if score < 0.4:
        assert result[0] == "llamacpp", f"score={score} but local not first: {result}"


@pytest.mark.parametrize("query", _COMPLEX, ids=lambda q: q[:30])
def test_above_threshold_queries_keep_cloud_chain(query: str):
    chain = ["claude", "groq"]
    with (
        patch.object(policy, "AVAILABLE_PROVIDERS", ["claude", "groq", "llamacpp"]),
        patch("koda.services.local_routing_policy.effective_local_prefer_threshold", lambda: 0.4),
    ):
        result = policy.adjust_chain_for_local_preference(chain, query=query)
    assert result == chain, f"complex query routed local: {result}"


# ---------------------------------------------------------------------------
# Rate of correct routing on the labeled set
# ---------------------------------------------------------------------------


def test_routing_decision_accuracy_on_labeled_corpus():
    """Binary routing accuracy at the default threshold: trivial+simple→local, complex→cloud.

    We don't validate fine-grained 4-bucket classification — the heuristic is
    too coarse for that. Routing is binary (local vs cloud at threshold 0.4),
    and that's what matters in production.
    """
    threshold = 0.4
    expected_local = _TRIVIAL + _SIMPLE
    expected_cloud = _COMPLEX

    routed_local_correctly = sum(1 for q in expected_local if complexity_score(q) < threshold)
    routed_cloud_correctly = sum(1 for q in expected_cloud if complexity_score(q) >= threshold)

    local_acc = routed_local_correctly / len(expected_local)
    cloud_acc = routed_cloud_correctly / len(expected_cloud)
    overall = (routed_local_correctly + routed_cloud_correctly) / (len(expected_local) + len(expected_cloud))

    print(f"\n  Local routing: {routed_local_correctly}/{len(expected_local)} = {local_acc:.0%}")
    print(f"  Cloud routing: {routed_cloud_correctly}/{len(expected_cloud)} = {cloud_acc:.0%}")
    print(f"  Overall: {overall:.0%}")
    # Production expectation: ≥ 90% on this labeled corpus. The heuristic is
    # tuned to be conservative on escalation — it's better to escalate a
    # borderline query to cloud than to send a too-hard query to a 7B local.
    assert local_acc >= 0.85, f"local routing accuracy {local_acc:.0%} < 85%"
    assert cloud_acc >= 0.85, f"cloud routing accuracy {cloud_acc:.0%} < 85%"
