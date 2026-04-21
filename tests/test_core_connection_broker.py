"""Tests for agent-scoped CORE connection brokering."""

from __future__ import annotations

from pathlib import Path

import pytest


def _stub_manager(monkeypatch, payloads: dict[str, dict[str, object] | None]) -> None:
    import koda.control_plane.manager as manager_mod

    class _Manager:
        def resolve_agent_core_runtime_connection(self, agent_id: str, integration_id: str):
            del agent_id
            return payloads.get(integration_id)

    monkeypatch.setattr(manager_mod, "get_control_plane_manager", lambda: _Manager())


def test_gws_service_account_key_is_materialized_temporarily(monkeypatch):
    import koda.services.core_connection_broker as broker_mod

    _stub_manager(
        monkeypatch,
        {
            "gws": {
                "connection_key": "core:gws",
                "kind": "core",
                "integration_key": "gws",
                "auth_method": "service_account_key",
                "source_origin": "agent_binding",
                "status": "configured",
                "connected": True,
                "config_values": {},
                "secret_refs": {"GWS_SERVICE_ACCOUNT_KEY": "agent:ATLAS:GWS_SERVICE_ACCOUNT_KEY"},
                "secret_values": {"GWS_SERVICE_ACCOUNT_KEY": '{"client_email":"atlas@example.com"}'},
                "metadata": {},
                "tool_policies": {},
            }
        },
    )

    broker = broker_mod.CoreConnectionBroker()
    materialized_path: str | None = None
    with broker.materialize_cli_environment("gws", agent_id="ATLAS") as (_resolved, env):
        materialized_path = env["GWS_CREDENTIALS_FILE"]
        assert Path(materialized_path).exists()
        assert env["GOOGLE_APPLICATION_CREDENTIALS"] == materialized_path
    assert materialized_path is not None
    assert not Path(materialized_path).exists()


def test_github_local_session_requires_explicit_opt_in(monkeypatch):
    import koda.services.core_connection_broker as broker_mod

    _stub_manager(
        monkeypatch,
        {
            "gh": {
                "connection_key": "core:gh",
                "kind": "core",
                "integration_key": "gh",
                "auth_method": "local_session",
                "source_origin": "local_session",
                "status": "configured",
                "connected": True,
                "config_values": {},
                "secret_refs": {},
                "secret_values": {},
                "metadata": {"allow_local_session": False},
                "tool_policies": {},
            }
        },
    )

    broker = broker_mod.CoreConnectionBroker()
    with (
        pytest.raises(RuntimeError, match="not allowed"),
        broker.materialize_cli_environment(
            "gh",
            agent_id="ATLAS",
        ),
    ):
        pass


def test_github_token_materializes_temp_config_dir(monkeypatch):
    import koda.services.core_connection_broker as broker_mod

    _stub_manager(
        monkeypatch,
        {
            "gh": {
                "connection_key": "core:gh",
                "kind": "core",
                "integration_key": "gh",
                "auth_method": "token",
                "source_origin": "agent_binding",
                "status": "configured",
                "connected": True,
                "config_values": {},
                "secret_refs": {"GH_TOKEN": "agent:ATLAS:GH_TOKEN"},
                "secret_values": {"GH_TOKEN": "ghp_agent_token"},
                "metadata": {},
                "tool_policies": {},
            }
        },
    )

    broker = broker_mod.CoreConnectionBroker()
    config_dir: str | None = None
    with broker.materialize_cli_environment("gh", agent_id="ATLAS") as (_resolved, env):
        config_dir = env["GH_CONFIG_DIR"]
        assert env["GH_TOKEN"] == "ghp_agent_token"
        assert Path(config_dir).exists()
    assert config_dir is not None
    assert not Path(config_dir).exists()


def test_gitlab_local_session_uses_host_config_dir_when_allowed(monkeypatch):
    import koda.services.core_connection_broker as broker_mod

    monkeypatch.setenv("HOME", "/tmp/koda-home")
    _stub_manager(
        monkeypatch,
        {
            "glab": {
                "connection_key": "core:glab",
                "kind": "core",
                "integration_key": "glab",
                "auth_method": "local_session",
                "source_origin": "local_session",
                "status": "configured",
                "connected": True,
                "config_values": {},
                "secret_refs": {},
                "secret_values": {},
                "metadata": {"allow_local_session": True},
                "tool_policies": {},
            }
        },
    )

    broker = broker_mod.CoreConnectionBroker()
    with broker.materialize_cli_environment("glab", agent_id="ATLAS") as (_resolved, env):
        assert env["HOME"] == "/tmp/koda-home"
        assert env["GLAB_CONFIG_DIR"] == "/tmp/koda-home/.config/glab-cli"


def test_aws_assume_role_materializes_temporary_credentials(monkeypatch):
    import koda.services.core_connection_broker as broker_mod

    _stub_manager(
        monkeypatch,
        {
            "aws": {
                "connection_key": "core:aws",
                "kind": "core",
                "integration_key": "aws",
                "auth_method": "assume_role",
                "source_origin": "agent_binding",
                "status": "configured",
                "connected": True,
                "config_values": {
                    "AWS_DEFAULT_REGION": "us-east-1",
                    "AWS_ROLE_ARN": "arn:aws:iam::123456789012:role/TestRole",
                },
                "secret_refs": {
                    "AWS_ACCESS_KEY_ID": "agent:ATLAS:AWS_ACCESS_KEY_ID",
                    "AWS_SECRET_ACCESS_KEY": "agent:ATLAS:AWS_SECRET_ACCESS_KEY",
                },
                "secret_values": {
                    "AWS_ACCESS_KEY_ID": "base-access",
                    "AWS_SECRET_ACCESS_KEY": "base-secret",
                },
                "metadata": {},
                "tool_policies": {},
            }
        },
    )

    monkeypatch.setattr(
        broker_mod.CoreConnectionBroker,
        "_assume_role_credentials",
        lambda self, resolved: {
            "AccessKeyId": "temp-access",
            "SecretAccessKey": "temp-secret",
            "SessionToken": "temp-token",
        },
    )

    broker = broker_mod.CoreConnectionBroker()
    with broker.materialize_cli_environment("aws", agent_id="ATLAS") as (_resolved, env):
        assert env["AWS_ACCESS_KEY_ID"] == "temp-access"
        assert env["AWS_SECRET_ACCESS_KEY"] == "temp-secret"
        assert env["AWS_SESSION_TOKEN"] == "temp-token"
        assert Path(env["AWS_SHARED_CREDENTIALS_FILE"]).exists()
        assert Path(env["AWS_CONFIG_FILE"]).exists()
