"""Verify sensitive keys are redacted from structured log events (shared redactor key rules)."""

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
    assert redacted["password"] == "[REDACTED]"
    assert redacted["session_token"] == "[REDACTED]"
    assert redacted["recovery_code"] == "[REDACTED]"
    assert redacted["bootstrap_code"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"


def test_masks_empty_values_like_every_other_path() -> None:
    event = {"event": "foo", "password": "", "api_key": None}
    redacted = _redact_sensitive(object(), "info", event)
    assert redacted == {"event": "foo", "password": "[REDACTED]", "api_key": "[REDACTED]"}


def test_is_case_insensitive_on_keys() -> None:
    event = {"Password": "hunter2", "SESSION_TOKEN": "abc"}
    redacted = _redact_sensitive(object(), "info", event)
    assert redacted["Password"] == "[REDACTED]"
    assert redacted["SESSION_TOKEN"] == "[REDACTED]"
