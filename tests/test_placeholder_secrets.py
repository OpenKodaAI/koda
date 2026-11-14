"""Unedited .env.example credential placeholders must never authenticate."""

from __future__ import annotations

import pytest

from koda import config as config_mod
from koda.config import is_placeholder_secret
from koda.control_plane.settings import parse_api_tokens


@pytest.mark.parametrize(
    "value",
    [
        "replace-with-a-random-token",
        "  replace-with-a-random-runtime-token  ",
        "REPLACE-WITH-a-random-web-session-secret",
    ],
)
def test_placeholder_values_are_detected(value: str) -> None:
    assert is_placeholder_secret(value)


@pytest.mark.parametrize("value", ["", None, "a-real-random-token", "please-replace-with-later-x"])
def test_real_or_empty_values_are_not_placeholders(value: str | None) -> None:
    assert not is_placeholder_secret(value)


def test_parse_api_tokens_drops_placeholders_and_keeps_rotation_pairs() -> None:
    assert parse_api_tokens("replace-with-a-random-token") == ([], 1)
    assert parse_api_tokens(" new-token , old-token ,") == (["new-token", "old-token"], 0)
    assert parse_api_tokens("new-token,replace-with-a-random-token") == (["new-token"], 1)
    assert parse_api_tokens("") == ([], 0)


def test_env_secret_treats_placeholder_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_mod, "AGENT_ID", None)
    monkeypatch.setenv("RUNTIME_LOCAL_UI_TOKEN", "replace-with-a-random-runtime-token")
    assert config_mod._env_secret("RUNTIME_LOCAL_UI_TOKEN") == ""

    monkeypatch.setenv("RUNTIME_LOCAL_UI_TOKEN", "  real-runtime-token  ")
    assert config_mod._env_secret("RUNTIME_LOCAL_UI_TOKEN") == "real-runtime-token"


def test_runtime_access_broker_never_signs_with_a_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.control_plane import runtime_access

    monkeypatch.setattr(runtime_access, "fetch_one", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("RUNTIME_LOCAL_UI_TOKEN", "replace-with-a-random-runtime-token")
    monkeypatch.setenv("KODA_RUNTIME_LOCAL_UI_TOKEN", "replace-with-a-random-runtime-token")
    broker = runtime_access.ControlPlaneRuntimeAccessBroker(manager=None)

    assert broker.resolve_runtime_secret("koda") == ""

    monkeypatch.setenv("KODA_RUNTIME_LOCAL_UI_TOKEN", "scoped-real-token")
    assert broker.resolve_runtime_secret("koda") == "scoped-real-token"
