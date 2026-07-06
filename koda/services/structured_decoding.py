"""Constrained-decoding helpers for local LLM runtimes.

Local models (especially small ones) emit malformed ``<agent_cmd>`` blocks at
non-trivial rates. ``llama-server`` accepts a GBNF grammar via the OpenAI-
compatible chat payload that bounds the sampler's logits to syntactically
valid output, eliminating that failure mode.

This module:

- Loads the canonical GBNF grammar from
  ``koda/services/grammars/agent_cmd.gbnf``.
- Exposes a thin API the local runners use to attach the grammar to chat
  payloads (``payload_extras_for_provider``).
- Reads ``STRUCTURED_DECODING_ENABLED`` and ``LLAMACPP_GRAMMAR_FILE`` from
  ``koda.config`` so operators can swap grammars or disable the feature
  without touching code.

The grammar's contract with ``tool_dispatcher.parse_agent_commands`` is
covered by ``tests/test_services/test_structured_decoding.py`` — drift
breaks CI.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from koda.logging_config import get_logger

log = get_logger(__name__)

_DEFAULT_GRAMMAR_PATH = Path(__file__).parent / "grammars" / "agent_cmd.gbnf"


@cache
def _load_default_grammar() -> str:
    try:
        return _DEFAULT_GRAMMAR_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("structured_decoding_grammar_unreadable", path=str(_DEFAULT_GRAMMAR_PATH), error=str(exc))
        return ""


def agent_cmd_grammar_gbnf() -> str:
    """Canonical GBNF grammar for ``<agent_cmd>`` blocks.

    Falls back to an empty string if the bundled file is unreadable so the
    runtime degrades gracefully (no grammar = unconstrained sampling).
    """
    return _load_default_grammar()


def agent_cmd_grammar_xgrammar() -> str:
    """XGrammar-compatible regex describing the ``<agent_cmd>`` block.

    XGrammar drives logits processors used by MLX and some Python wrappers
    around vLLM. The ``mlx-openai-server`` project does not yet expose a
    grammar field over its OpenAI-compatible HTTP API as of early 2026, so
    this string is currently informational — kept here to make a future
    integration a one-line wire-up rather than a redesign.
    """
    return (
        r"(?:[^<]|<[^a]|<a[^g]|<ag[^e]|<age[^n]|<agen[^t]|<agent[^_]|"
        r"<agent_[^c]|<agent_c[^m]|<agent_cm[^d])*"
        r'(?:<agent_cmd tool="[a-zA-Z_][a-zA-Z0-9_]*">'
        r"\s*(?:\{.*?\}|\[.*?\]|\".*?\"|true|false|null|-?[0-9]+(?:\.[0-9]+)?)\s*"
        r"</agent_cmd>)*"
    )


def resolve_grammar_path(override_path: str | None = None) -> Path | None:
    """Pick the grammar file path: explicit override > default bundle."""
    if override_path:
        candidate = Path(override_path).expanduser()
        if candidate.is_file():
            return candidate
        log.warning("structured_decoding_override_missing", path=str(candidate))
        return None
    if _DEFAULT_GRAMMAR_PATH.is_file():
        return _DEFAULT_GRAMMAR_PATH
    return None


def payload_extras_for_provider(
    provider_id: str,
    *,
    enabled: bool,
    grammar_override_path: str | None = None,
) -> tuple[tuple[str, object], ...]:
    """Build the ``extra_payload`` tuple injected into the chat payload.

    Returns an empty tuple when constrained decoding is disabled, the
    provider does not support it, or the grammar cannot be loaded. Callers
    are expected to merge the result into ``ProviderHttpProfile.extra_payload``.

    ``llama-server`` accepts the grammar in the ``grammar`` field of the
    chat-completion payload; ``mlx-openai-server`` does not yet expose a
    grammar surface over HTTP so MLX returns an empty tuple.
    """
    if not enabled:
        return ()
    if provider_id == "llamacpp":
        path = resolve_grammar_path(grammar_override_path)
        if path is None:
            return ()
        try:
            grammar_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("structured_decoding_load_failed", path=str(path), error=str(exc))
            return ()
        if not grammar_text.strip():
            return ()
        return (("grammar", grammar_text),)
    if provider_id == "mlx":
        # MLX OpenAI-compat servers don't surface a grammar field today.
        # When upstream support lands we'll attach via "guided_regex" or
        # equivalent; until then constrained decoding is a no-op for MLX.
        return ()
    return ()


def reset_cache_for_tests() -> None:
    """Test hook: invalidate the cached grammar so a fresh read runs."""
    _load_default_grammar.cache_clear()
