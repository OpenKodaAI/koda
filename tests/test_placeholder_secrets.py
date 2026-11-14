"""Unedited .env.example credential placeholders.

Authentication placeholders never authenticate. Postgres and object-storage
placeholders still do, so they are reported (names only, never values).
"""

from __future__ import annotations

import json

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


# --- Postgres and object-storage placeholders (warn only) -------------------

_STORAGE_ENV_KEYS = (
    "POSTGRES_PASSWORD",
    "KNOWLEDGE_V2_POSTGRES_DSN",
    "S3_ACCESS_KEY_ID",
    "KNOWLEDGE_V2_S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY",
)
_PG_PLACEHOLDER = "replace-with-a-random-postgres-password"
_S3_KEY_PLACEHOLDER = "replace-with-a-random-object-storage-access-key"
_S3_SECRET_PLACEHOLDER = "replace-with-a-random-object-storage-secret"


@pytest.fixture
def storage_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key in _STORAGE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_placeholder_storage_secrets_reports_env_example_values(storage_env: pytest.MonkeyPatch) -> None:
    """Source compose loads .env into the app container, so the .env names are visible."""
    storage_env.setenv("POSTGRES_PASSWORD", _PG_PLACEHOLDER)
    storage_env.setenv("S3_ACCESS_KEY_ID", _S3_KEY_PLACEHOLDER)
    storage_env.setenv("S3_SECRET_ACCESS_KEY", f"  {_S3_SECRET_PLACEHOLDER.upper()}  ")

    assert config_mod.placeholder_storage_secrets() == [
        "POSTGRES_PASSWORD",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
    ]


def test_placeholder_storage_secrets_reads_the_settings_compose_derives(storage_env: pytest.MonkeyPatch) -> None:
    """The release compose has no env_file: only the derived DSN and S3 settings reach the app."""
    storage_env.setenv("KNOWLEDGE_V2_POSTGRES_DSN", f"postgresql://koda:{_PG_PLACEHOLDER}@postgres:5432/koda")
    storage_env.setenv("KNOWLEDGE_V2_S3_ACCESS_KEY_ID", _S3_KEY_PLACEHOLDER)
    storage_env.setenv("KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY", _S3_SECRET_PLACEHOLDER)

    assert config_mod.placeholder_storage_secrets() == [
        "POSTGRES_PASSWORD",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
    ]


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://koda:0f3c9a7e5b@postgres:5432/koda",
        "postgresql://koda@postgres:5432/koda",
        "postgresql://postgres:5432/koda",
    ],
)
def test_placeholder_storage_secrets_accepts_a_dsn_with_a_real_or_no_password(
    storage_env: pytest.MonkeyPatch,
    dsn: str,
) -> None:
    storage_env.setenv("KNOWLEDGE_V2_POSTGRES_DSN", dsn)
    assert config_mod.placeholder_storage_secrets() == []


def test_placeholder_storage_secrets_survives_a_malformed_dsn(storage_env: pytest.MonkeyPatch) -> None:
    # urlsplit raises ValueError on an unbalanced IPv6 host; a startup warning must never crash.
    storage_env.setenv("KNOWLEDGE_V2_POSTGRES_DSN", "postgresql://koda:secret@[::1:5432/koda")
    storage_env.setenv("S3_ACCESS_KEY_ID", _S3_KEY_PLACEHOLDER)
    assert config_mod.placeholder_storage_secrets() == ["S3_ACCESS_KEY_ID"]


def test_placeholder_storage_secrets_is_empty_for_generated_or_unset_values(storage_env: pytest.MonkeyPatch) -> None:
    assert config_mod.placeholder_storage_secrets() == []

    storage_env.setenv("POSTGRES_PASSWORD", "4b1f0c2e9d8a7f6e5d4c3b2a19081726")
    storage_env.setenv("KNOWLEDGE_V2_POSTGRES_DSN", "postgresql://koda:4b1f0c2e9d8a7f6e5d4c3b2a19081726@postgres/koda")
    storage_env.setenv("S3_ACCESS_KEY_ID", "a1b2c3d4e5f6a7b8c9d0")
    storage_env.setenv("S3_SECRET_ACCESS_KEY", "")
    assert config_mod.placeholder_storage_secrets() == []


class _RecordingLog:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object]]] = []

    def warning(self, event: str, **fields: object) -> None:
        self.events.append(("warning", event, fields))

    def error(self, event: str, **fields: object) -> None:
        self.events.append(("error", event, fields))


def test_supervisor_startup_warns_about_storage_placeholders_without_values(
    storage_env: pytest.MonkeyPatch,
) -> None:
    from koda.control_plane import supervisor as supervisor_mod

    recorder = _RecordingLog()
    storage_env.setattr(supervisor_mod, "log", recorder)
    storage_env.setenv("POSTGRES_PASSWORD", _PG_PLACEHOLDER)
    storage_env.setenv("KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY", _S3_SECRET_PLACEHOLDER)

    # Interim mitigation: a warning, never an exception that would stop the start.
    supervisor_mod._warn_about_placeholder_secrets()

    storage_events = [entry for entry in recorder.events if entry[1] == "storage_secret_placeholder_in_use"]
    assert len(storage_events) == 1
    level, _event, fields = storage_events[0]
    assert level == "warning"
    assert fields["keys"] == ["POSTGRES_PASSWORD", "S3_SECRET_ACCESS_KEY"]
    assert fields["rotation_url"] == config_mod.PLACEHOLDER_SECRET_ROTATION_URL
    assert "#rotating-placeholder-postgres-and-object-storage-secrets" in str(fields["rotation_url"])
    assert "replace-with-" not in repr(recorder.events)


def test_supervisor_startup_is_silent_when_storage_secrets_are_real(storage_env: pytest.MonkeyPatch) -> None:
    from koda.control_plane import supervisor as supervisor_mod

    recorder = _RecordingLog()
    storage_env.setattr(supervisor_mod, "log", recorder)
    storage_env.setenv("POSTGRES_PASSWORD", "4b1f0c2e9d8a7f6e5d4c3b2a19081726")

    supervisor_mod._warn_about_placeholder_secrets()

    assert all(entry[1] != "storage_secret_placeholder_in_use" for entry in recorder.events)


def test_rotation_anchor_exists_in_the_install_guide() -> None:
    from pathlib import Path

    anchor = config_mod.PLACEHOLDER_SECRET_ROTATION_URL.rsplit("#", 1)[1]
    guide = (Path(__file__).resolve().parent.parent / "docs" / "install" / "local.md").read_text(encoding="utf-8")
    headings = {
        "-".join(line.lstrip("#").strip().lower().replace("`", "").split())
        for line in guide.splitlines()
        if line.startswith("#")
    }
    assert anchor in headings


async def test_placeholder_secrets_route_requires_an_operator_and_returns_names_only(
    storage_env: pytest.MonkeyPatch,
) -> None:
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from koda.control_plane import api as control_plane_api
    from koda.control_plane.operator_auth import OperatorAuthContext

    operator = OperatorAuthContext(
        auth_kind="session",
        subject_type="operator",
        user_id="op-1",
        username="owner",
        email=None,
        display_name=None,
    )

    class _FakeAuthService:
        def resolve_bearer_token(self, token: str) -> OperatorAuthContext | None:
            return operator if token == "valid-session" else None

    storage_env.setattr(control_plane_api, "_auth_service", lambda: _FakeAuthService())
    storage_env.setenv("POSTGRES_PASSWORD", _PG_PLACEHOLDER)
    storage_env.setenv("S3_ACCESS_KEY_ID", _S3_KEY_PLACEHOLDER)

    app = web.Application(
        middlewares=[
            control_plane_api.control_plane_error_middleware,
            control_plane_api.control_plane_auth_middleware,
        ]
    )
    control_plane_api.setup_control_plane_routes(app)
    path = "/api/control-plane/system-settings/placeholder-secrets"

    async with TestClient(TestServer(app)) as client:
        anonymous = await client.get(path)
        assert anonymous.status == 401

        wrong = await client.get(path, headers={"Authorization": "Bearer nope"})
        assert wrong.status == 401

        response = await client.get(path, headers={"Authorization": "Bearer valid-session"})
        assert response.status == 200
        body = await response.text()

    payload = json.loads(body)
    assert payload == {
        "placeholder_keys": ["POSTGRES_PASSWORD", "S3_ACCESS_KEY_ID"],
        "rotation_url": config_mod.PLACEHOLDER_SECRET_ROTATION_URL,
    }
    assert "replace-with-" not in body
