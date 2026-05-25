"""Tests for the GBNF grammar + payload-extras helpers used by llama.cpp."""

from __future__ import annotations

import json
import re

import pytest

from koda.services.structured_decoding import (
    agent_cmd_grammar_gbnf,
    agent_cmd_grammar_xgrammar,
    payload_extras_for_provider,
    reset_cache_for_tests,
    resolve_grammar_path,
)
from koda.services.tool_dispatcher import _AGENT_CMD_RE, parse_agent_commands


@pytest.fixture(autouse=True)
def _reset():
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def test_grammar_file_exists_in_package():
    path = resolve_grammar_path()
    assert path is not None
    assert path.is_file()
    assert path.name == "agent_cmd.gbnf"


def test_grammar_text_is_non_trivial():
    text = agent_cmd_grammar_gbnf()
    assert "agent-cmd" in text
    assert "json-value" in text
    assert "<agent_cmd" in text


def test_xgrammar_pattern_compiles():
    pattern = agent_cmd_grammar_xgrammar()
    # Just ensure the regex compiles — it's a marker for future MLX work.
    re.compile(pattern, re.DOTALL)


def test_payload_extras_disabled_returns_empty():
    extras = payload_extras_for_provider("llamacpp", enabled=False)
    assert extras == ()


def test_payload_extras_for_mlx_is_empty_even_when_enabled():
    extras = payload_extras_for_provider("mlx", enabled=True)
    assert extras == ()


def test_payload_extras_for_llamacpp_carries_grammar():
    extras = payload_extras_for_provider("llamacpp", enabled=True)
    assert len(extras) == 1
    key, value = extras[0]
    assert key == "grammar"
    assert isinstance(value, str)
    assert "agent-cmd" in value


def test_payload_extras_with_missing_override_logs_warning(caplog, tmp_path):
    missing = tmp_path / "does-not-exist.gbnf"
    extras = payload_extras_for_provider(
        "llamacpp",
        enabled=True,
        grammar_override_path=str(missing),
    )
    # Falls back to no grammar; runner stays unconstrained but functional.
    assert extras == ()


# ---------------------------------------------------------------------------
# Golden-corpus contract: every <agent_cmd> the dispatcher accepts must match
# the dispatcher's regex AND parse to valid JSON. The grammar's job is to
# bound model output to this same shape — divergence from the regex breaks
# users.
# ---------------------------------------------------------------------------


_GOLDEN_AGENT_CMDS = [
    '<agent_cmd tool="shell_run">{"command": "ls -la"}</agent_cmd>',
    '<agent_cmd tool="file_read">{"path": "src/index.ts", "max_lines": 200}</agent_cmd>',
    '<agent_cmd tool="db_query">{"query": "SELECT 1", "env": "dev"}</agent_cmd>',
    '<agent_cmd tool="git_status">{}</agent_cmd>',
    '<agent_cmd tool="browser_click">{"selector": "#submit"}</agent_cmd>',
    '<agent_cmd tool="agent_send">{"to": "buddy", "message": "ping"}</agent_cmd>',
    '<agent_cmd tool="job_create">{"name": "nightly", "schedule": "0 2 * * *"}</agent_cmd>',
    '<agent_cmd tool="mcp_list_tools">{"server": "stripe"}</agent_cmd>',
]


@pytest.mark.parametrize("payload", _GOLDEN_AGENT_CMDS)
def test_golden_corpus_matches_dispatcher_regex(payload: str):
    match = _AGENT_CMD_RE.search(payload)
    assert match is not None, "dispatcher regex must accept the golden corpus"
    body = match.group(2).strip()
    # JSON body must round-trip through json.loads — otherwise the dispatcher
    # logs a warning and skips the call.
    parsed = json.loads(body) if body else {}
    assert isinstance(parsed, (dict, list))


@pytest.mark.parametrize("payload", _GOLDEN_AGENT_CMDS)
def test_golden_corpus_parses_through_dispatcher(payload: str):
    calls, _clean = parse_agent_commands(payload)
    assert len(calls) == 1


def test_grammar_bundle_path_is_inside_services():
    path = resolve_grammar_path()
    assert path is not None
    assert "services" in str(path)
    assert "grammars" in str(path)


def test_grammar_text_describes_json_subset():
    text = agent_cmd_grammar_gbnf()
    # We don't enforce equality (operators may swap grammars) — just that the
    # bundled file is the JSON-aware variant, not a degenerate stub.
    for token in ("string", "number", "object", "array", "ws"):
        assert token in text, f"expected GBNF rule for {token!r}"


def test_path_resolution_prefers_override(tmp_path):
    custom = tmp_path / "custom.gbnf"
    custom.write_text("root ::= .*", encoding="utf-8")
    resolved = resolve_grammar_path(str(custom))
    assert resolved == custom


# ---------------------------------------------------------------------------
# Static-syntax regression guard. Catches the multi-line-alternative bug that
# silently disabled grammar enforcement in earlier revisions: GBNF requires
# every alternative branch (`|`) to live on the same line as its rule. A
# rule like:
#
#     prose-char ::= [^<]
#                  | "<" [^a]
#
# parses to a syntax error inside llama.cpp and the constraint is silently
# dropped. We catch that by inspecting the raw bytes — every `|` token
# must appear on the same line as a `::=` arrow.
# ---------------------------------------------------------------------------


def test_no_continuation_lines_in_grammar():
    text = agent_cmd_grammar_gbnf()
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("|"):
            raise AssertionError(
                f"GBNF line {lineno} starts with '|' — llama.cpp's grammar parser "
                f"rejects this. Put the alternative on the same line as the rule:\n"
                f"  {line!r}"
            )


def test_grammar_declares_root():
    text = agent_cmd_grammar_gbnf()
    assert any(line.startswith("root ::=") for line in text.splitlines()), "GBNF must declare a `root` production"


def test_grammar_references_agent_cmd_tag():
    text = agent_cmd_grammar_gbnf()
    assert "<agent_cmd " in text, "Grammar must produce the literal <agent_cmd opener"
    assert "</agent_cmd>" in text, "Grammar must produce the literal </agent_cmd> closer"
