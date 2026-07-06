"""Tests for canonical core connection defaults and S3 client consolidation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# Helpers


def _make_integration_manager(monkeypatch):
    """Build a lightweight ControlPlaneManager stub for integration tests."""
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)

    integration_rows: dict[str, dict | None] = {}
    env_fields: dict[str, list[dict]] = {}
    secrets: dict[str, str] = {}
    system_settings: dict[str, dict] = {"integrations": {}}

    manager._merged_global_env = lambda: {}  # type: ignore[attr-defined]
    manager._merged_global_env_base = lambda: {}  # type: ignore[attr-defined]

    def _integration_connection_row(integration_id: str):
        return integration_rows.get(integration_id)

    def _integration_fields_payload(integration_id: str):
        return env_fields.get(integration_id, [])

    def _global_secret_value(key: str):
        return secrets.get(key, "")

    def _stored_global_secret_value(key: str):
        return secrets.get(key, "")

    def _system_default_connection_config(integration_id: str):
        return {
            str(item.get("key") or ""): str(item.get("value") or "")
            for item in env_fields.get(integration_id, [])
            if str(item.get("value") or "").strip()
        }

    def _integration_configured(integration_id: str):
        template = manager_mod._GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.get(integration_id)
        if template is None:
            return integration_id != "browser"
        for field in template["fields"]:
            if not bool(field.get("required")):
                continue
            fkey = str(field["key"])
            if str(field.get("storage") or "env") == "secret":
                if not secrets.get(fkey, "").strip():
                    return False
                continue
            payload = next((item for item in env_fields.get(integration_id, []) if str(item.get("key")) == fkey), {})
            if not bool(payload.get("value") or payload.get("value_present")):
                return False
        return True

    manager._integration_connection_row = _integration_connection_row  # type: ignore[attr-defined]
    manager._integration_fields_payload = _integration_fields_payload  # type: ignore[attr-defined]
    manager._global_secret_value = _global_secret_value  # type: ignore[attr-defined]
    manager._stored_global_secret_value = _stored_global_secret_value  # type: ignore[attr-defined]
    manager._system_default_connection_config = _system_default_connection_config  # type: ignore[attr-defined]
    manager._integration_configured = _integration_configured  # type: ignore[attr-defined]
    manager.get_system_settings = lambda: dict(system_settings)  # type: ignore[attr-defined]

    monkeypatch.setattr(manager_mod, "fetch_one", lambda *args, **kwargs: None)
    monkeypatch.setattr(manager_mod, "execute", lambda *args, **kwargs: None)

    return manager, integration_rows, env_fields, secrets


# Verified status truthfulness


class TestVerifiedStatusTruthfulness:
    """Ensure connection defaults report configured and verified truthfully."""

    def test_removed_external_core_defaults_are_not_resolved(self, monkeypatch):
        manager, _rows, _fields, _secrets = _make_integration_manager(monkeypatch)

        for connection_key in ("core:aws", "core:gh", "core:glab", "core:gws", "core:jira", "core:confluence"):
            try:
                manager.get_connection_default(connection_key)
            except KeyError:
                continue
            raise AssertionError(f"{connection_key} should not be exposed as a core connection")


# S3 client consolidation


class TestS3ClientConsolidation:
    """Verify _build_s3_client passes credentials correctly."""

    def test_passes_all_configured_credentials(self, monkeypatch):
        from koda.knowledge.v2 import common as common_mod

        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_ENDPOINT_URL", "http://minio:9000")
        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_REGION", "us-west-2")
        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_ACCESS_KEY_ID", "AKID123")
        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY", "SECRET456")

        mock_boto3 = MagicMock()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            store = common_mod.V2StoreSupport.__new__(common_mod.V2StoreSupport)
            result = store._build_s3_client()

        mock_boto3.client.assert_called_once_with(
            "s3",
            endpoint_url="http://minio:9000",
            region_name="us-west-2",
            aws_access_key_id="AKID123",
            aws_secret_access_key="SECRET456",
        )
        assert result is mock_client

    def test_override_credentials_take_precedence(self, monkeypatch):
        from koda.knowledge.v2 import common as common_mod

        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_ENDPOINT_URL", "")
        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_REGION", "")
        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_ACCESS_KEY_ID", "old-key")
        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY", "old-secret")

        mock_boto3 = MagicMock()
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            store = common_mod.V2StoreSupport.__new__(common_mod.V2StoreSupport)
            store._build_s3_client(
                credentials={
                    "aws_access_key_id": "new-key",
                    "aws_secret_access_key": "new-secret",
                }
            )

        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "new-key"
        assert call_kwargs["aws_secret_access_key"] == "new-secret"

    def test_falls_back_to_config_when_no_overrides(self, monkeypatch):
        from koda.knowledge.v2 import common as common_mod

        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_ENDPOINT_URL", "")
        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_REGION", "eu-west-1")
        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_ACCESS_KEY_ID", "config-key")
        monkeypatch.setattr(common_mod, "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY", "config-secret")

        mock_boto3 = MagicMock()
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            store = common_mod.V2StoreSupport.__new__(common_mod.V2StoreSupport)
            store._build_s3_client()

        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "config-key"
        assert call_kwargs["region_name"] == "eu-west-1"


class TestLegacyPostgresCredentials:
    """Verify native Postgres credentials are no longer exposed in system settings."""

    def test_postgres_template_is_absent(self):
        import koda.control_plane.manager as manager_mod

        assert "postgres" not in manager_mod._GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES
