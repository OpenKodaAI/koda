"""Agent-scoped resolution and materialization for CORE connections."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from koda.config import AGENT_ID, CONFLUENCE_CLOUD, JIRA_CLOUD
from koda.logging_config import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class ResolvedConnection:
    agent_id: str
    connection_key: str
    kind: str
    integration_key: str
    auth_method: str
    source_origin: str
    status: str
    connected: bool
    account_label: str | None = None
    provider_account_id: str | None = None
    expires_at: str | None = None
    last_verified_at: str | None = None
    last_error: str | None = None
    config_values: dict[str, str] = field(default_factory=dict)
    secret_refs: dict[str, str] = field(default_factory=dict)
    secret_values: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_policies: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AgentConnectionContext:
    agent_id: str
    runtime_access_token: str | None
    connections: dict[str, ResolvedConnection]
    tool_policies: dict[str, dict[str, str]] = field(default_factory=dict)
    account_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)


class CoreConnectionBroker:
    """Resolve core connections and materialize minimal per-call auth state."""

    def _current_agent_id(self) -> str:
        raw = str(AGENT_ID or os.environ.get("AGENT_ID") or "").strip().upper()
        if not raw:
            raise RuntimeError("AGENT_ID is required to resolve core connections")
        return raw

    def resolve(
        self,
        integration_id: str,
        *,
        agent_id: str | None = None,
    ) -> ResolvedConnection | None:
        from koda.control_plane.manager import get_control_plane_manager

        resolved_agent = str(agent_id or self._current_agent_id()).strip().upper()
        payload = get_control_plane_manager().resolve_agent_core_runtime_connection(
            resolved_agent,
            integration_id,
        )
        if payload is None:
            return None
        return ResolvedConnection(
            agent_id=resolved_agent,
            connection_key=str(payload.get("connection_key") or ""),
            kind=str(payload.get("kind") or "core"),
            integration_key=str(payload.get("integration_key") or integration_id).strip().lower(),
            auth_method=str(payload.get("auth_method") or "none"),
            source_origin=str(payload.get("source_origin") or "agent_binding"),
            status=str(payload.get("status") or "not_configured"),
            connected=bool(payload.get("connected")),
            account_label=str(payload.get("account_label") or "") or None,
            provider_account_id=str(payload.get("provider_account_id") or "") or None,
            expires_at=str(payload.get("expires_at") or "") or None,
            last_verified_at=str(payload.get("last_verified_at") or "") or None,
            last_error=str(payload.get("last_error") or "") or None,
            config_values={str(k): str(v) for k, v in dict(payload.get("config_values") or {}).items()},
            secret_refs={str(k): str(v) for k, v in dict(payload.get("secret_refs") or {}).items()},
            secret_values={str(k): str(v) for k, v in dict(payload.get("secret_values") or {}).items()},
            metadata=dict(payload.get("metadata") or {}),
            tool_policies={str(k): str(v) for k, v in dict(payload.get("tool_policies") or {}).items()},
        )

    def get_context(
        self,
        *,
        agent_id: str | None = None,
        runtime_access_token: str | None = None,
    ) -> AgentConnectionContext:
        from koda.agent_contract import CORE_INTEGRATION_IDS

        resolved_agent = str(agent_id or self._current_agent_id()).strip().upper()
        connections: dict[str, ResolvedConnection] = {}
        account_metadata: dict[str, dict[str, Any]] = {}
        for integration_id in CORE_INTEGRATION_IDS:
            connection = self.resolve(integration_id, agent_id=resolved_agent)
            if connection is None:
                continue
            connections[connection.connection_key] = connection
            account_metadata[connection.connection_key] = {
                "account_label": connection.account_label,
                "provider_account_id": connection.provider_account_id,
                "expires_at": connection.expires_at,
                "source_origin": connection.source_origin,
            }
        return AgentConnectionContext(
            agent_id=resolved_agent,
            runtime_access_token=runtime_access_token,
            connections=connections,
            account_metadata=account_metadata,
        )

    def atlassian_client_kwargs(
        self,
        integration_id: str,
        *,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        resolved = self.resolve(integration_id, agent_id=agent_id)
        if resolved is None or not resolved.connected:
            raise RuntimeError(f"{integration_id} connection is not configured for this agent")
        if resolved.auth_method != "api_token":
            raise RuntimeError(f"{integration_id} auth method '{resolved.auth_method}' is not supported")
        if integration_id == "jira":
            return {
                "url": str(resolved.config_values.get("JIRA_URL") or "").strip(),
                "username": str(resolved.config_values.get("JIRA_USERNAME") or "").strip(),
                "password": str(resolved.secret_values.get("JIRA_API_TOKEN") or "").strip(),
                "cloud": bool(resolved.metadata.get("cloud", JIRA_CLOUD)),
            }
        if integration_id == "confluence":
            return {
                "url": str(resolved.config_values.get("CONFLUENCE_URL") or "").strip(),
                "username": str(resolved.config_values.get("CONFLUENCE_USERNAME") or "").strip(),
                "password": str(resolved.secret_values.get("CONFLUENCE_API_TOKEN") or "").strip(),
                "cloud": bool(resolved.metadata.get("cloud", CONFLUENCE_CLOUD)),
            }
        raise RuntimeError(f"Unsupported Atlassian integration: {integration_id}")

    def atlassian_base_urls(self, *, agent_id: str | None = None) -> dict[str, str]:
        urls: dict[str, str] = {}
        jira = self.resolve("jira", agent_id=agent_id)
        if jira and jira.connected:
            value = str(jira.config_values.get("JIRA_URL") or "").strip()
            if value:
                urls["jira"] = value
        confluence = self.resolve("confluence", agent_id=agent_id)
        if confluence and confluence.connected:
            value = str(confluence.config_values.get("CONFLUENCE_URL") or "").strip()
            if value:
                urls["confluence"] = value
        return urls

    @contextmanager
    def materialize_cli_environment(
        self,
        integration_id: str,
        *,
        agent_id: str | None = None,
    ) -> Iterator[tuple[ResolvedConnection, dict[str, str]]]:
        resolved = self.resolve(integration_id, agent_id=agent_id)
        if resolved is None or not resolved.connected:
            raise RuntimeError(f"{integration_id} connection is not configured for this agent")
        with ExitStack() as stack:
            env = self._build_cli_env(resolved, stack=stack)
            yield resolved, env

    def build_boto3_session_kwargs(
        self,
        *,
        agent_id: str | None = None,
    ) -> tuple[ResolvedConnection, dict[str, Any]]:
        resolved = self.resolve("aws", agent_id=agent_id)
        if resolved is None or not resolved.connected:
            raise RuntimeError("aws connection is not configured for this agent")

        region = str(resolved.config_values.get("AWS_DEFAULT_REGION") or "").strip()
        if not region:
            raise RuntimeError("AWS_DEFAULT_REGION is required")

        kwargs: dict[str, Any] = {"region_name": region}
        auth_method = resolved.auth_method
        if auth_method == "access_key":
            access_key = str(resolved.secret_values.get("AWS_ACCESS_KEY_ID") or "").strip()
            secret_key = str(resolved.secret_values.get("AWS_SECRET_ACCESS_KEY") or "").strip()
            if not access_key or not secret_key:
                raise RuntimeError("AWS access key credentials are incomplete")
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
            session_token = str(resolved.secret_values.get("AWS_SESSION_TOKEN") or "").strip()
            if session_token:
                kwargs["aws_session_token"] = session_token
            return resolved, kwargs

        if auth_method == "assume_role":
            temp_creds = self._assume_role_credentials(resolved)
            kwargs["aws_access_key_id"] = temp_creds["AccessKeyId"]
            kwargs["aws_secret_access_key"] = temp_creds["SecretAccessKey"]
            kwargs["aws_session_token"] = temp_creds["SessionToken"]
            return resolved, kwargs

        if auth_method == "local_session":
            if not bool(resolved.metadata.get("allow_local_session")):
                raise RuntimeError("AWS local session is not allowed for this agent")
            profile = str(
                resolved.config_values.get("AWS_PROFILE_PROD")
                or resolved.config_values.get("AWS_PROFILE_DEV")
                or resolved.metadata.get("profile_name")
                or ""
            ).strip()
            if profile:
                kwargs["profile_name"] = profile
            return resolved, kwargs

        raise RuntimeError(f"Unsupported AWS auth method: {auth_method}")

    def _build_cli_env(self, resolved: ResolvedConnection, *, stack: ExitStack) -> dict[str, str]:
        integration_id = resolved.integration_key
        if integration_id == "gws":
            return self._build_gws_env(resolved, stack=stack)
        if integration_id == "gh":
            return self._build_github_env(resolved, stack=stack)
        if integration_id == "glab":
            return self._build_gitlab_env(resolved, stack=stack)
        if integration_id == "aws":
            return self._build_aws_env(resolved, stack=stack)
        return {}

    def _build_gws_env(self, resolved: ResolvedConnection, *, stack: ExitStack) -> dict[str, str]:
        credentials_file = str(resolved.config_values.get("GWS_CREDENTIALS_FILE") or "").strip()
        if resolved.auth_method == "service_account_key":
            key_payload = str(resolved.secret_values.get("GWS_SERVICE_ACCOUNT_KEY") or "").strip()
            if not key_payload:
                raise RuntimeError("GWS service account key is missing")
            with tempfile.NamedTemporaryFile("w", suffix=".json", prefix="koda_gws_", delete=False) as handle:
                handle.write(key_payload)
                handle.flush()
                path = handle.name
            stack.callback(_unlink_file, path)
            credentials_file = path
        if not credentials_file:
            raise RuntimeError("GWS credentials file is missing")
        return {
            "GWS_CREDENTIALS_FILE": credentials_file,
            "GOOGLE_APPLICATION_CREDENTIALS": credentials_file,
        }

    def _build_github_env(self, resolved: ResolvedConnection, *, stack: ExitStack) -> dict[str, str]:
        if resolved.auth_method == "token":
            token = str(resolved.secret_values.get("GH_TOKEN") or "").strip()
            if not token:
                raise RuntimeError("GH_TOKEN is missing")
            config_dir = tempfile.mkdtemp(prefix="koda_gh_")
            stack.callback(_cleanup_temp_dir, config_dir)
            return {
                "GH_TOKEN": token,
                "GH_CONFIG_DIR": config_dir,
            }
        if resolved.auth_method == "local_session":
            if not bool(resolved.metadata.get("allow_local_session")):
                raise RuntimeError("GitHub local session is not allowed for this agent")
            home = str(os.environ.get("HOME") or "").strip()
            env: dict[str, str] = {}
            if home:
                env["HOME"] = home
                env["GH_CONFIG_DIR"] = str(Path(home) / ".config" / "gh")
            return env
        raise RuntimeError(f"Unsupported GitHub auth method: {resolved.auth_method}")

    def _build_gitlab_env(self, resolved: ResolvedConnection, *, stack: ExitStack) -> dict[str, str]:
        if resolved.auth_method == "token":
            token = str(resolved.secret_values.get("GITLAB_TOKEN") or "").strip()
            if not token:
                raise RuntimeError("GITLAB_TOKEN is missing")
            config_dir = tempfile.mkdtemp(prefix="koda_glab_")
            stack.callback(_cleanup_temp_dir, config_dir)
            return {
                "GITLAB_TOKEN": token,
                "GLAB_CONFIG_DIR": config_dir,
            }
        if resolved.auth_method == "local_session":
            if not bool(resolved.metadata.get("allow_local_session")):
                raise RuntimeError("GitLab local session is not allowed for this agent")
            home = str(os.environ.get("HOME") or "").strip()
            env: dict[str, str] = {}
            if home:
                env["HOME"] = home
                env["GLAB_CONFIG_DIR"] = str(Path(home) / ".config" / "glab-cli")
            return env
        raise RuntimeError(f"Unsupported GitLab auth method: {resolved.auth_method}")

    def _build_aws_env(self, resolved: ResolvedConnection, *, stack: ExitStack) -> dict[str, str]:
        region = str(resolved.config_values.get("AWS_DEFAULT_REGION") or "").strip()
        if not region:
            raise RuntimeError("AWS_DEFAULT_REGION is required")
        env: dict[str, str] = {
            "AWS_DEFAULT_REGION": region,
            "AWS_REGION": region,
            "AWS_EC2_METADATA_DISABLED": "true",
        }
        if resolved.auth_method == "local_session":
            if not bool(resolved.metadata.get("allow_local_session")):
                raise RuntimeError("AWS local session is not allowed for this agent")
            home = str(os.environ.get("HOME") or "").strip()
            if home:
                env["HOME"] = home
                env["AWS_SHARED_CREDENTIALS_FILE"] = str(Path(home) / ".aws" / "credentials")
                env["AWS_CONFIG_FILE"] = str(Path(home) / ".aws" / "config")
            profile = str(
                resolved.config_values.get("AWS_PROFILE_PROD")
                or resolved.config_values.get("AWS_PROFILE_DEV")
                or resolved.metadata.get("profile_name")
                or ""
            ).strip()
            if profile:
                env["AWS_PROFILE"] = profile
            return env

        aws_dir = tempfile.mkdtemp(prefix="koda_aws_")
        stack.callback(_cleanup_temp_dir, aws_dir)
        credentials_file = Path(aws_dir) / "credentials"
        config_file = Path(aws_dir) / "config"
        credentials_file.write_text("", encoding="utf-8")
        config_file.write_text("", encoding="utf-8")
        env["AWS_SHARED_CREDENTIALS_FILE"] = str(credentials_file)
        env["AWS_CONFIG_FILE"] = str(config_file)

        if resolved.auth_method == "access_key":
            access_key = str(resolved.secret_values.get("AWS_ACCESS_KEY_ID") or "").strip()
            secret_key = str(resolved.secret_values.get("AWS_SECRET_ACCESS_KEY") or "").strip()
            if not access_key or not secret_key:
                raise RuntimeError("AWS access key credentials are incomplete")
            env["AWS_ACCESS_KEY_ID"] = access_key
            env["AWS_SECRET_ACCESS_KEY"] = secret_key
            session_token = str(resolved.secret_values.get("AWS_SESSION_TOKEN") or "").strip()
            if session_token:
                env["AWS_SESSION_TOKEN"] = session_token
            return env

        if resolved.auth_method == "assume_role":
            temp_creds = self._assume_role_credentials(resolved)
            env["AWS_ACCESS_KEY_ID"] = str(temp_creds["AccessKeyId"])
            env["AWS_SECRET_ACCESS_KEY"] = str(temp_creds["SecretAccessKey"])
            env["AWS_SESSION_TOKEN"] = str(temp_creds["SessionToken"])
            return env

        raise RuntimeError(f"Unsupported AWS auth method: {resolved.auth_method}")

    def _assume_role_credentials(self, resolved: ResolvedConnection) -> dict[str, Any]:
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError("boto3 not installed") from exc

        role_arn = str(resolved.config_values.get("AWS_ROLE_ARN") or "").strip()
        if not role_arn:
            raise RuntimeError("AWS_ROLE_ARN is required for assume_role")

        region = str(resolved.config_values.get("AWS_DEFAULT_REGION") or "").strip()
        access_key = str(resolved.secret_values.get("AWS_ACCESS_KEY_ID") or "").strip()
        secret_key = str(resolved.secret_values.get("AWS_SECRET_ACCESS_KEY") or "").strip()
        if not access_key or not secret_key:
            raise RuntimeError("Base AWS access key credentials are required for assume_role")

        session_kwargs: dict[str, Any] = {
            "region_name": region,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
        }
        session_token = str(resolved.secret_values.get("AWS_SESSION_TOKEN") or "").strip()
        if session_token:
            session_kwargs["aws_session_token"] = session_token
        session = boto3.Session(**session_kwargs)
        client = session.client("sts")
        assume_kwargs: dict[str, Any] = {
            "RoleArn": role_arn,
            "RoleSessionName": str(
                resolved.config_values.get("AWS_ROLE_SESSION_NAME") or f"koda-{resolved.agent_id.lower()}"
            ).strip(),
        }
        external_id = str(resolved.config_values.get("AWS_EXTERNAL_ID") or "").strip()
        if external_id:
            assume_kwargs["ExternalId"] = external_id
        response = client.assume_role(**assume_kwargs)
        credentials = dict(response.get("Credentials") or {})
        if not credentials:
            raise RuntimeError("assume_role returned no credentials")
        return credentials


def _unlink_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def _cleanup_temp_dir(path: str) -> None:
    directory = Path(path)
    if not directory.exists():
        return
    for child in directory.iterdir():
        child.unlink(missing_ok=True)
    directory.rmdir()


_core_connection_broker: CoreConnectionBroker | None = None


def get_core_connection_broker() -> CoreConnectionBroker:
    global _core_connection_broker
    if _core_connection_broker is None:
        _core_connection_broker = CoreConnectionBroker()
    return _core_connection_broker
