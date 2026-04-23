"""Verify sensitive keys are redacted from structured log events."""

from __future__ import annotations

from koda.logging_config import _redact_sensitive


def test_redacts_passwords_and_tokens() -> None:
    event = {
        "event": "operator_login_attempt",
        "username": "owner",
        "password": "hunter2",
        "session_token": "kodas_abcdef",
        "recovery_code": "xxxx-yyyy-zzzz",
        "bootstrap_code": "ABCD-EFGH-IJKL",
        "authorization": "Bearer abc",
    }
    redacted = _redact_sensitive(object(), "info", event)
    assert redacted["username"] == "owner"
    assert redacted["password"] == "***"
    assert redacted["session_token"] == "***"
    assert redacted["recovery_code"] == "***"
    assert redacted["bootstrap_code"] == "***"
    assert redacted["authorization"] == "***"


def test_leaves_empty_and_missing_fields_alone() -> None:
    event = {"event": "foo", "password": "", "api_key": None}
    redacted = _redact_sensitive(object(), "info", event)
    assert redacted["password"] == ""
    assert redacted["api_key"] is None


def test_is_case_insensitive_on_keys() -> None:
    event = {"Password": "hunter2", "SESSION_TOKEN": "abc"}
    redacted = _redact_sensitive(object(), "info", event)
    assert redacted["Password"] == "***"
    assert redacted["SESSION_TOKEN"] == "***"
