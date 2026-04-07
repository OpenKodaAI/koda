"""Tests for canonical core connection defaults and S3 client consolidation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        if integration_id in {"gh", "glab"}:
            secret_key = "GH_TOKEN" if integration_id == "gh" else "GITLAB_TOKEN"
            return bool(secrets.get(secret_key, ""))
        if integration_id == "gws":
            fields_map = {
                str(manager_mod._safe_json_object(item).get("key") or ""): manager_mod._safe_json_object(item)
                for item in env_fields.get(integration_id, [])
            }
            credentials_file = str(fields_map.get("GWS_CREDENTIALS_FILE", {}).get("value") or "").strip()
            return bool(credentials_file or secrets.get("GWS_SERVICE_ACCOUNT_KEY", ""))
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


# ---------------------------------------------------------------------------
# Phase 1A — Verified status truthfulness
# ---------------------------------------------------------------------------


class TestVerifiedStatusTruthfulness:
    """Ensure connection defaults report configured and verified truthfully."""

    def test_no_row_shows_configured_not_verified(self, monkeypatch):
        manager, rows, fields, _secrets = _make_integration_manager(monkeypatch)
        # AWS with region set → configured=True, but no DB row
        fields["aws"] = [{"key": "AWS_DEFAULT_REGION", "value": "us-east-1"}]
        result = manager.get_connection_default("core:aws")
        assert result["connection_key"] == "core:aws"
        assert result["connected"] is True
        assert result["metadata"]["verified"] is False
        assert result["status"] == "configured"

    def test_verified_row_shows_verified(self, monkeypatch):
        manager, rows, fields, _secrets = _make_integration_manager(monkeypatch)
        fields["aws"] = [{"key": "AWS_DEFAULT_REGION", "value": "us-east-1"}]
        rows["aws"] = {
            "verified": 1,
            "configured": 1,
            "account_label": "arn:aws:iam::123456",
            "auth_method": "profile",
            "last_verified_at": "2026-01-01T00:00:00",
            "last_error": "",
            "checked_via": "sts_get_caller_identity",
            "auth_expired": 0,
            "metadata_json": "{}",
        }
        result = manager.get_connection_default("core:aws")
        assert result["metadata"]["verified"] is True
        assert result["status"] == "verified"

    def test_no_row_unconfigured_shows_not_configured(self, monkeypatch):
        manager, rows, fields, _secrets = _make_integration_manager(monkeypatch)
        # AWS with no region → configured=False
        fields["aws"] = []
        result = manager.get_connection_default("core:aws")
        assert result["connected"] is False
        assert result["metadata"]["verified"] is False
        assert result["status"] == "not_configured"


# ---------------------------------------------------------------------------
# Phase 1B — S3 client consolidation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Phase 2 — AWS verification with STS
# ---------------------------------------------------------------------------


class TestAWSVerification:
    """Verify AWS integration uses STS GetCallerIdentity for real verification."""

    def test_verify_with_access_keys(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        fields["aws"] = [
            {"key": "AWS_DEFAULT_REGION", "value": "us-east-1"},
            {"key": "AWS_PROFILE_DEV", "value": ""},
            {"key": "AWS_PROFILE_PROD", "value": ""},
        ]
        secrets["AWS_ACCESS_KEY_ID"] = "AKIAIOSFODNN7EXAMPLE"
        secrets["AWS_SECRET_ACCESS_KEY"] = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        mock_session = MagicMock()
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/test",
            "UserId": "AIDACKCEVSQ6C2EXAMPLE",
        }
        mock_session.client.return_value = mock_sts

        mock_boto3 = MagicMock()
        mock_boto3.Session.return_value = mock_session

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            result = manager._verify_integration_configuration("aws")

        assert result["verified"] is True
        assert result["checked_via"] == "sts_get_caller_identity"
        assert result["details"]["auth_mode"] == "access_key"
        assert result["details"]["account"] == "123456789012"

    def test_verify_with_profile(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        fields["aws"] = [
            {"key": "AWS_DEFAULT_REGION", "value": "eu-west-1"},
            {"key": "AWS_PROFILE_DEV", "value": ""},
            {"key": "AWS_PROFILE_PROD", "value": "production"},
        ]

        mock_session = MagicMock()
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Account": "987654321098",
            "Arn": "arn:aws:iam::987654321098:role/prod",
            "UserId": "AROA3XFRBF23",
        }
        mock_session.client.return_value = mock_sts
        mock_boto3 = MagicMock()
        mock_boto3.Session.return_value = mock_session

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            result = manager._verify_integration_configuration("aws")

        assert result["verified"] is True
        assert result["details"]["auth_mode"] == "assume_role"
        mock_boto3.Session.assert_called_once()
        call_kwargs = mock_boto3.Session.call_args[1]
        assert call_kwargs["profile_name"] == "production"

    def test_verify_missing_region(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        # Use whitespace so _integration_configured passes (value is truthy)
        # but _nonempty_text strips it to empty for the region check.
        fields["aws"] = [{"key": "AWS_DEFAULT_REGION", "value": " "}]
        result = manager._verify_integration_configuration("aws")
        assert result["verified"] is False
        assert "missing default region" in result["last_error"]

    def test_verify_no_boto3(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        fields["aws"] = [
            {"key": "AWS_DEFAULT_REGION", "value": "us-east-1"},
            {"key": "AWS_PROFILE_DEV", "value": ""},
            {"key": "AWS_PROFILE_PROD", "value": ""},
        ]

        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def mock_import(name, *args, **kwargs):
            if name == "boto3":
                raise ImportError("No module named 'boto3'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)
        result = manager._verify_integration_configuration("aws")
        assert result["verified"] is False
        assert "boto3 not installed" in result["last_error"]

    def test_verify_credential_failure(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        fields["aws"] = [
            {"key": "AWS_DEFAULT_REGION", "value": "us-east-1"},
            {"key": "AWS_PROFILE_DEV", "value": ""},
            {"key": "AWS_PROFILE_PROD", "value": ""},
        ]
        secrets["AWS_ACCESS_KEY_ID"] = "AKIAIOSFODNN7EXAMPLE"
        secrets["AWS_SECRET_ACCESS_KEY"] = "bad-key"

        mock_session = MagicMock()
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.side_effect = Exception("InvalidClientTokenId: The security token is not valid")
        mock_session.client.return_value = mock_sts
        mock_boto3 = MagicMock()
        mock_boto3.Session.return_value = mock_session

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            result = manager._verify_integration_configuration("aws")

        assert result["verified"] is False
        assert "InvalidClientTokenId" in result["last_error"]


# ---------------------------------------------------------------------------
# Phase 4 — GitHub / GitLab verification and Postgres SSH secrets
# ---------------------------------------------------------------------------


class TestGitHubVerification:
    """Verify GitHub integration supports token and CLI auth."""

    def test_verify_with_token(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        secrets["GH_TOKEN"] = "ghp_test123456"

        import subprocess

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"login": "testuser", "name": "Test User"}'
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

        result = manager._verify_integration_configuration("gh")
        assert result["verified"] is True
        assert result["account_label"] == "testuser"
        assert result["details"]["auth_mode"] == "token"

    def test_verify_with_cli_auth(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        rows["gh"] = {"auth_method": "local_session"}

        import subprocess

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"login": "cliuser"}'
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

        result = manager._verify_integration_configuration("gh")
        assert result["verified"] is True
        assert result["details"]["auth_mode"] == "local_session"

    def test_verify_cli_not_found(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        rows["gh"] = {"auth_method": "local_session"}

        import subprocess

        monkeypatch.setattr(subprocess, "run", MagicMock(side_effect=FileNotFoundError))

        result = manager._verify_integration_configuration("gh")
        assert result["verified"] is False
        assert "gh CLI not found" in result["last_error"]


class TestGitLabVerification:
    """Verify GitLab integration supports token and CLI auth."""

    def test_verify_with_token(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        secrets["GITLAB_TOKEN"] = "glpat-test123456"

        import subprocess

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"username": "gluser", "name": "GL User"}'
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

        result = manager._verify_integration_configuration("glab")
        assert result["verified"] is True
        assert result["account_label"] == "gluser"
        assert result["details"]["auth_mode"] == "token"

    def test_verify_cli_not_found(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        rows["glab"] = {"auth_method": "local_session"}

        import subprocess

        monkeypatch.setattr(subprocess, "run", MagicMock(side_effect=FileNotFoundError))

        result = manager._verify_integration_configuration("glab")
        assert result["verified"] is False
        assert "glab CLI not found" in result["last_error"]


class TestLegacyPostgresCredentials:
    """Verify native Postgres credentials are no longer exposed in system settings."""

    def test_postgres_template_is_absent(self):
        import koda.control_plane.manager as manager_mod

        assert "postgres" not in manager_mod._GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES


# ---------------------------------------------------------------------------
# Phase 3 — GWS service account key as secret
# ---------------------------------------------------------------------------


class TestGWSVerification:
    """Verify GWS supports both file path and secret key auth."""

    def test_configured_with_file_only(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        fields["gws"] = [
            {"key": "GWS_CREDENTIALS_FILE", "value": "/path/to/creds.json"},
            {"key": "GWS_SERVICE_ACCOUNT_KEY", "value": ""},
        ]
        assert manager._integration_configured("gws") is True

    def test_configured_with_secret_only(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        fields["gws"] = [
            {"key": "GWS_CREDENTIALS_FILE", "value": ""},
        ]
        secrets["GWS_SERVICE_ACCOUNT_KEY"] = (
            '{"type":"service_account","client_email":"test@proj.iam.gserviceaccount.com"}'
        )
        assert manager._integration_configured("gws") is True

    def test_configured_neither(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        fields["gws"] = [
            {"key": "GWS_CREDENTIALS_FILE", "value": ""},
        ]
        assert manager._integration_configured("gws") is False

    def test_verify_with_secret_key(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        sa_json = '{"type":"service_account","client_email":"bot@proj.iam.gserviceaccount.com","project_id":"my-proj","token_uri":"https://oauth2.googleapis.com/token"}'
        fields["gws"] = [
            {"key": "GWS_CREDENTIALS_FILE", "value": ""},
        ]
        secrets["GWS_SERVICE_ACCOUNT_KEY"] = sa_json

        import koda.control_plane.manager as manager_mod

        monkeypatch.setattr(
            manager_mod,
            "_mint_google_service_account_token",
            lambda path: {
                "client_email": "bot@proj.iam.gserviceaccount.com",
                "project_id": "my-proj",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        )

        result = manager._verify_integration_configuration("gws")
        assert result["verified"] is True
        assert result["details"]["credentials_source"] == "secret"
        assert result["account_label"] == "bot@proj.iam.gserviceaccount.com"

    def test_verify_with_file_path(self, monkeypatch, tmp_path):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        sa_json = (
            '{"type":"service_account","client_email":"file@proj.iam.gserviceaccount.com","project_id":"file-proj"}'
        )
        cred_file = tmp_path / "creds.json"
        cred_file.write_text(sa_json)
        fields["gws"] = [
            {"key": "GWS_CREDENTIALS_FILE", "value": str(cred_file)},
        ]

        import koda.control_plane.manager as manager_mod

        monkeypatch.setattr(
            manager_mod,
            "_mint_google_service_account_token",
            lambda path: {
                "client_email": "file@proj.iam.gserviceaccount.com",
                "project_id": "file-proj",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        )

        result = manager._verify_integration_configuration("gws")
        assert result["verified"] is True
        assert result["details"]["credentials_source"] == "file"

    def test_verify_missing_credentials(self, monkeypatch):
        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        fields["gws"] = [
            {"key": "GWS_CREDENTIALS_FILE", "value": ""},
        ]
        result = manager._verify_integration_configuration("gws")
        assert result["verified"] is False
        assert "missing" in result["last_error"]


# ---------------------------------------------------------------------------
# Phase 5 — Jira / Confluence timeout protection
# ---------------------------------------------------------------------------


class TestJiraConfluenceTimeout:
    """Ensure Jira and Confluence verification respects a timeout."""

    def test_jira_verification_timeout(self, monkeypatch):
        import sys
        import types

        import koda.control_plane.manager as manager_mod

        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        fields["jira"] = [
            {"key": "JIRA_URL", "value": "https://test.atlassian.net"},
            {"key": "JIRA_USERNAME", "value": "user@example.com"},
            {"key": "JIRA_API_TOKEN", "value_present": True},
        ]
        secrets["JIRA_API_TOKEN"] = "tok-123"

        # Fake atlassian module so `from atlassian import Jira` succeeds
        fake_atlassian = types.ModuleType("atlassian")
        fake_atlassian.Jira = MagicMock  # type: ignore[attr-defined]

        def _timeout_run(func, timeout_seconds=10):
            raise manager_mod._VerificationTimeout(f"Verification timed out after {timeout_seconds}s")

        monkeypatch.setattr(manager_mod, "_run_with_timeout", _timeout_run)

        with patch.dict(sys.modules, {"atlassian": fake_atlassian}):
            result = manager._verify_integration_configuration("jira")

        assert result["verified"] is False
        assert "timed out" in result["last_error"]
        assert result["checked_via"] == "jira_myself"

    def test_confluence_verification_timeout(self, monkeypatch):
        import sys
        import types

        import koda.control_plane.manager as manager_mod

        manager, rows, fields, secrets = _make_integration_manager(monkeypatch)
        fields["confluence"] = [
            {"key": "CONFLUENCE_URL", "value": "https://test.atlassian.net/wiki"},
            {"key": "CONFLUENCE_USERNAME", "value": "user@example.com"},
            {"key": "CONFLUENCE_API_TOKEN", "value_present": True},
        ]
        secrets["CONFLUENCE_API_TOKEN"] = "tok-456"

        # Fake atlassian module so `from atlassian import Confluence` succeeds
        fake_atlassian = types.ModuleType("atlassian")
        fake_atlassian.Confluence = MagicMock  # type: ignore[attr-defined]

        def _timeout_run(func, timeout_seconds=10):
            raise manager_mod._VerificationTimeout(f"Verification timed out after {timeout_seconds}s")

        monkeypatch.setattr(manager_mod, "_run_with_timeout", _timeout_run)

        with patch.dict(sys.modules, {"atlassian": fake_atlassian}):
            result = manager._verify_integration_configuration("confluence")

        assert result["verified"] is False
        assert "timed out" in result["last_error"]
        assert result["checked_via"] == "confluence_read_probe"
