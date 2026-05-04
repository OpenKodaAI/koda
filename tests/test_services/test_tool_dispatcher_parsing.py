"""Parsing-layer tests for koda.services.tool_dispatcher.

Pins parse_agent_commands behavior:
  * Recognizes well-formed <agent_cmd tool="..."> {...} </agent_cmd> blocks
  * Skips blocks with malformed JSON without raising
  * Strips parsed blocks AND <action_plan>...</action_plan> from clean text
  * Collapses 3+ consecutive newlines to 2
  * Tool name is matched verbatim (no normalization), params are dict
  * Hypothesis fuzz: never crashes, never returns invalid types

Also covers _infer_tool_category — the prefix-based router that decides
which integration policy and approval flow apply.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from koda.services.tool_dispatcher import (
    AgentToolCall,
    _infer_tool_category,
    parse_agent_commands,
)

# parse_agent_commands — happy path


def test_parse_single_well_formed_call() -> None:
    text = '<agent_cmd tool="job_list">{"limit": 10}</agent_cmd>'
    calls, clean = parse_agent_commands(text)
    assert len(calls) == 1
    assert calls[0].tool == "job_list"
    assert calls[0].params == {"limit": 10}
    assert clean == ""  # the entire input was a tool block


def test_parse_with_surrounding_text() -> None:
    text = 'I will list jobs.\n<agent_cmd tool="job_list">{}</agent_cmd>\nDone.'
    calls, clean = parse_agent_commands(text)
    assert len(calls) == 1
    assert "I will list jobs." in clean
    assert "Done." in clean
    assert "agent_cmd" not in clean


def test_parse_multiple_calls() -> None:
    text = (
        '<agent_cmd tool="file_read">{"path": "/a"}</agent_cmd>\n<agent_cmd tool="file_read">{"path": "/b"}</agent_cmd>'
    )
    calls, _ = parse_agent_commands(text)
    assert len(calls) == 2
    assert [c.params["path"] for c in calls] == ["/a", "/b"]


def test_parse_empty_body_yields_empty_dict() -> None:
    text = '<agent_cmd tool="job_list"></agent_cmd>'
    calls, _ = parse_agent_commands(text)
    assert len(calls) == 1
    assert calls[0].params == {}


def test_parse_whitespace_around_body() -> None:
    text = '<agent_cmd tool="job_list">   { "x": 1 }   </agent_cmd>'
    calls, _ = parse_agent_commands(text)
    assert calls[0].params == {"x": 1}


def test_parse_multiline_body_via_dotall() -> None:
    text = '<agent_cmd tool="file_write">{\n  "path": "/x",\n  "content": "hello"\n}</agent_cmd>'
    calls, _ = parse_agent_commands(text)
    assert calls[0].params == {"path": "/x", "content": "hello"}


# parse_agent_commands — malformed JSON skipped without raising


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "{",
        "}",
        "{,}",
        '{"key": }',
        '{"key": "value",}',
        "[1, 2,",
        "true false",
    ],
)
def test_parse_malformed_json_skipped(body: str) -> None:
    text = f'<agent_cmd tool="job_list">{body}</agent_cmd>'
    calls, _ = parse_agent_commands(text)
    assert calls == []


def test_parse_mix_of_valid_and_malformed() -> None:
    text = (
        '<agent_cmd tool="ok">{"a": 1}</agent_cmd>'
        '<agent_cmd tool="bad">not json</agent_cmd>'
        '<agent_cmd tool="ok2">{"b": 2}</agent_cmd>'
    )
    calls, _ = parse_agent_commands(text)
    assert [c.tool for c in calls] == ["ok", "ok2"]


# parse_agent_commands — clean-text behavior


def test_clean_strips_action_plan_blocks() -> None:
    text = '<action_plan>I will read files.</action_plan>\n<agent_cmd tool="file_read">{"path": "/x"}</agent_cmd>'
    _, clean = parse_agent_commands(text)
    assert "action_plan" not in clean
    assert "I will read files" not in clean


def test_clean_collapses_excessive_newlines() -> None:
    text = 'before\n\n\n\n<agent_cmd tool="x">{}</agent_cmd>\n\n\n\nafter'
    _, clean = parse_agent_commands(text)
    # No more than 2 consecutive newlines remain.
    assert "\n\n\n" not in clean
    assert "before" in clean and "after" in clean


def test_clean_strips_outer_whitespace() -> None:
    text = '   \n<agent_cmd tool="x">{}</agent_cmd>\n   '
    _, clean = parse_agent_commands(text)
    assert clean == ""


# parse_agent_commands — degenerate inputs


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no tags here at all",
        "<agent_cmd>missing tool attr</agent_cmd>",
        '<agent_cmd tool="">{}</agent_cmd>',  # empty tool name — regex requires ≥1 char
        "<agent_cmd tool='single-quote'>{}</agent_cmd>",  # single quotes → not matched
        '<AGENT_CMD tool="x">{}</AGENT_CMD>',  # case-sensitive tag → not matched
    ],
)
def test_parse_no_match_returns_no_calls(text: str) -> None:
    """The regex requires `tool="..."` with at least one character; everything
    else falls through to no-calls."""
    calls, _ = parse_agent_commands(text)
    assert calls == []


# Hypothesis fuzz — never crash on arbitrary input


@given(text=st.text(max_size=500))
@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_parse_never_crashes_on_arbitrary_text(text: str) -> None:
    calls, clean = parse_agent_commands(text)
    assert isinstance(calls, list)
    assert all(isinstance(c, AgentToolCall) for c in calls)
    assert isinstance(clean, str)


@given(
    tool=st.text(
        alphabet=st.characters(blacklist_characters='"<>&', blacklist_categories=("Cc", "Zs")),
        min_size=1,
        max_size=50,
    ),
    payload=st.dictionaries(
        keys=st.text(
            alphabet=st.characters(blacklist_categories=("Cc",)),
            min_size=1,
            max_size=20,
        ),
        values=st.one_of(
            st.text(max_size=50),
            st.integers(),
            st.booleans(),
            st.none(),
        ),
        max_size=8,
    ),
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_parse_round_trips_well_formed(tool: str, payload: dict) -> None:
    """Any well-formed JSON payload survives the parse round-trip exactly.

    The implementation strips surrounding whitespace from the tool name
    (`match.group(1).strip()`), so we forbid whitespace categories (`Zs`,
    `Cc`) from the strategy to keep round-trip exactness.
    """
    body = json.dumps(payload)
    text = f'<agent_cmd tool="{tool}">{body}</agent_cmd>'
    calls, _ = parse_agent_commands(text)
    assert len(calls) == 1
    assert calls[0].tool == tool
    assert calls[0].params == payload


def test_parse_strips_whitespace_around_tool_name() -> None:
    """Documented contract: tool name is .strip()'d after extraction."""
    text = '<agent_cmd tool="  job_list  ">{}</agent_cmd>'
    calls, _ = parse_agent_commands(text)
    assert len(calls) == 1
    assert calls[0].tool == "job_list"


# _infer_tool_category — prefix-based routing


@pytest.mark.parametrize(
    "tool,expected_category",
    [
        ("mcp_postgres__query", "mcp"),
        ("mcp_anything", "mcp"),
        ("file_read", "fileops"),
        ("file_write", "fileops"),
        ("file_edit", "fileops"),
        ("db_query", "db"),
        ("db_execute", "db"),
        ("gws", "tool"),
        ("jira", "tool"),
        ("confluence", "tool"),
        ("browser_navigate", "browser"),
        ("browser_click", "browser"),
        ("job_list", "ops"),
        ("job_create", "ops"),
        ("shell_execute", "shell"),
        ("shell_status", "shell"),
        ("git_status", "git"),
        ("git_commit", "git"),
        ("plugin_list", "plugin"),
        ("workflow_create", "workflow"),
        ("snapshot_save", "snapshots"),
        ("agent_send", "agent_comm"),
        ("agent_receive", "agent_comm"),
        ("agent_delegate", "agent_comm"),
        ("agent_list_agents", "agent_comm"),
        ("agent_broadcast", "agent_comm"),
    ],
)
def test_infer_tool_category(tool: str, expected_category: str) -> None:
    assert _infer_tool_category(tool) == expected_category


@pytest.mark.parametrize(
    "tool",
    [
        "weird_tool",
        "no_known_prefix",
        "",
        "memory_recall",  # not in the matrix, defaults to "tool"
        "audit_log",
    ],
)
def test_infer_tool_category_default(tool: str) -> None:
    assert _infer_tool_category(tool) == "tool"


def test_infer_tool_category_does_not_match_substrings() -> None:
    """`agent_send` matches exactly; `agent_send_extra` does not.

    The rule is *exact* membership for the agent_comm bucket; it falls back
    to the default 'tool' otherwise.
    """
    assert _infer_tool_category("agent_send_extra") == "tool"
    assert _infer_tool_category("xagent_send") == "tool"
