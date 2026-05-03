"""Extended tests for koda.services.runtime.redaction.

The basic round-trip is already covered by test_redaction.py. This file pins:

  * Plain non-secret content survives unchanged.
  * Recursive masking through dict/list/tuple/nested combinations.
  * Edge cases: empty containers, primitives, None.
  * Idempotence: redacting a redacted payload is a no-op.
  * JSON serialization preserves PT-BR unicode without \\u escapes.
  * Common secret-shaped patterns (api_key, password, bearer, token,
    cookie, URLs with embedded credentials) are all redacted.
"""

from __future__ import annotations

import json

import pytest

from koda.services.runtime.redaction import redact_json_dumps, redact_value

# ---------------------------------------------------------------------------
# Plain content passes through unchanged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "hello world",
        "Olá mundo",
        "user typed this query",
        "a single-word",
        "",
    ],
)
def test_plain_strings_unchanged(value: str) -> None:
    assert redact_value(value) == value


@pytest.mark.parametrize(
    "value",
    [42, 3.14, True, False, None, 0, -1, 2**31],
)
def test_primitives_pass_through(value: object) -> None:
    assert redact_value(value) == value


def test_empty_dict_round_trips() -> None:
    assert redact_value({}) == {}


def test_empty_list_round_trips() -> None:
    assert redact_value([]) == []


# ---------------------------------------------------------------------------
# Structural preservation
# ---------------------------------------------------------------------------


def test_dict_keys_preserved_for_non_secret_values() -> None:
    src = {"event": "command.started", "phase": "executing", "task_id": 42}
    out = redact_value(src)
    assert isinstance(out, dict)
    assert set(out.keys()) == {"event", "phase", "task_id"}
    assert out["task_id"] == 42
    assert out["phase"] == "executing"


def test_nested_structure_round_trips() -> None:
    src = {
        "command": "ls -la",
        "metadata": {
            "task_id": 1,
            "tags": ["a", "b", "c"],
            "nested": {"depth": 2, "items": [{"x": 1}, {"x": 2}]},
        },
    }
    out = redact_value(src)
    assert isinstance(out, dict)
    assert isinstance(out["metadata"], dict)
    assert isinstance(out["metadata"]["tags"], list)
    assert out["metadata"]["nested"]["items"] == [{"x": 1}, {"x": 2}]


def test_list_of_strings_yields_list() -> None:
    out = redact_value(["apple", "banana", "cherry"])
    assert out == ["apple", "banana", "cherry"]


def test_list_of_dicts_recursively_redacted() -> None:
    """Each dict in the list is independently scanned for secrets."""
    src = [
        {"name": "alice", "api_key": "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        {"name": "bob", "phase": "executing"},
    ]
    out = redact_value(src)
    assert isinstance(out, list)
    assert len(out) == 2
    # Plain fields preserved.
    assert out[0]["name"] == "alice"
    assert out[1]["name"] == "bob"
    assert out[1]["phase"] == "executing"
    # Secret fields masked (the existing test pins "[REDACTED]" as the mask).
    assert out[0]["api_key"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# Common secret patterns (using the existing mask contract: [REDACTED])
# ---------------------------------------------------------------------------


def test_authorization_bearer_token_masked() -> None:
    src = {"authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghij.zzz"}
    out = redact_value(src)
    assert out["authorization"] == "[REDACTED]"


def test_password_field_masked() -> None:
    out = redact_value({"password": "SuperSecret123!"})
    assert out["password"] == "[REDACTED]"


def test_api_key_field_masked() -> None:
    out = redact_value({"api_key": "sk-proj-abcdefghijklmnopqrstuvwxyz0123"})
    assert out["api_key"] == "[REDACTED]"


def test_cookie_field_masked() -> None:
    out = redact_value({"cookie": "session=abc123"})
    assert out["cookie"] == "[REDACTED]"


def test_url_with_embedded_credentials_masked_in_string() -> None:
    """URL with user:pass@ has the user/pass parts replaced inline."""
    out = redact_value("https://user:pass@example.com/path")
    assert "user:pass" not in out
    assert "example.com" in out  # host preserved
    assert "[REDACTED]" in out


def test_secret_inside_nested_dict_is_masked() -> None:
    src = {"a": {"b": {"c": {"api_key": "sk-zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"}}}}
    out = redact_value(src)
    assert out["a"]["b"]["c"]["api_key"] == "[REDACTED]"


def test_token_in_message_text_is_masked() -> None:
    """Long token-shaped substring inside a plain message is masked."""
    out = redact_value({"message": "your token is abcdefghijklmnopqrstuvwxyz123456"})
    assert "abcdefghijklmnopqrstuvwxyz123456" not in out["message"]
    assert "[REDACTED]" in out["message"]


# ---------------------------------------------------------------------------
# Case-insensitive key matching (the existing test pins "Authorization"
# capitalization is recognized; let's pin a few more variants).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["authorization", "Authorization", "AUTHORIZATION", "Authorization"],
)
def test_authorization_key_case_insensitive(key: str) -> None:
    out = redact_value({key: "Bearer abcdefghijklmnopqrstuvwxyz123456"})
    assert out[key] == "[REDACTED]"


@pytest.mark.parametrize("key", ["api_key", "API_KEY", "Api_Key"])
def test_api_key_case_insensitive(key: str) -> None:
    out = redact_value({key: "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})
    assert out[key] == "[REDACTED]"


# ---------------------------------------------------------------------------
# Idempotence: a redacted payload re-redacts to the same shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "plain text",
        {"k": "v"},
        ["a", "b"],
        {"nested": {"inner": [1, 2, 3]}},
        42,
        None,
        {"authorization": "Bearer xyz"},
    ],
)
def test_redact_idempotent(value: object) -> None:
    once = redact_value(value)
    twice = redact_value(once)
    assert once == twice


# ---------------------------------------------------------------------------
# redact_json_dumps: serialization layer
# ---------------------------------------------------------------------------


def test_json_dumps_returns_valid_json_string() -> None:
    out = redact_json_dumps({"a": 1, "b": "two"})
    assert isinstance(out, str)
    parsed = json.loads(out)
    assert parsed == {"a": 1, "b": "two"}


def test_json_dumps_preserves_pt_br_unicode() -> None:
    """ensure_ascii=False — accented chars survive without \\u escapes."""
    out = redact_json_dumps({"text": "olá mundo, ção"})
    parsed = json.loads(out)
    assert parsed["text"] == "olá mundo, ção"
    assert "olá" in out  # raw unicode in serialized form


def test_json_dumps_redacts_secrets_in_payload() -> None:
    out = redact_json_dumps({"api_key": "sk-zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz", "phase": "executing"})
    parsed = json.loads(out)
    assert parsed["api_key"] == "[REDACTED]"
    assert parsed["phase"] == "executing"


def test_json_dumps_handles_non_serializable_via_default_str() -> None:
    """Sets are not JSON-serializable — default=str coerces."""
    out = redact_json_dumps({1, 2, 3})
    # Should produce SOME parseable JSON; structure is the str() of the set.
    json.loads(out)


def test_json_dumps_handles_datetime() -> None:
    """datetime is not JSON-serializable; default=str converts."""
    from datetime import UTC, datetime

    dt = datetime(2026, 5, 3, 12, 0, 0, tzinfo=UTC)
    out = redact_json_dumps({"ts": dt})
    parsed = json.loads(out)
    assert "2026-05-03" in parsed["ts"]


def test_json_dumps_empty_payloads() -> None:
    assert json.loads(redact_json_dumps({})) == {}
    assert json.loads(redact_json_dumps([])) == []


# ---------------------------------------------------------------------------
# Defensive: arbitrary key_hint values do not crash
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key_hint",
    [None, "", "any-key", "API_KEY", "x-custom-header", "deeply/nested/path"],
)
def test_redact_value_accepts_any_key_hint(key_hint: str | None) -> None:
    out = redact_value("some content", key_hint=key_hint)
    assert isinstance(out, str)


# ---------------------------------------------------------------------------
# The existing test pinned five mask outcomes; we add a per-pattern
# parametrized version to make regressions easy to triage.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key,value",
    [
        ("authorization", "Bearer abcdefghijklmnopqrstuvwxyz123456"),
        ("cookie", "session=supersecretcookie"),
        ("api_key", "abcdefghijklmnopqrstuvwxyz123456"),
        ("password", "password123!@"),
    ],
)
def test_known_secret_keys_yield_redacted_marker(key: str, value: str) -> None:
    out = redact_value({key: value})
    assert out[key] == "[REDACTED]"
    # The original value is gone.
    assert value not in str(out)
