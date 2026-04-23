"""Rust gRPC-backed subprocess environment and security adapters."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any, cast

from koda.internal_rpc.security_guard import get_security_guard_client
from koda.services.provider_auth import (
    PROVIDER_API_KEY_ENV_KEYS,
    PROVIDER_AUTH_MODE_ENV_KEYS,
    PROVIDER_AUTH_TOKEN_ENV_KEYS,
    PROVIDER_BASE_URL_ENV_KEYS,
    PROVIDER_PROJECT_ENV_KEYS,
    PROVIDER_VERIFIED_ENV_KEYS,
    ProviderId,
)

_log = logging.getLogger(__name__)


def validate_shell_command(command: str) -> str:
    try:
        return get_security_guard_client().validate_shell_command(str(command))
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def validate_runtime_path(value: str, *, allow_empty: bool = False) -> str:
    try:
        return get_security_guard_client().validate_runtime_path(str(value), allow_empty=allow_empty)
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def redact_runtime_value(value: Any, *, key_hint: str | None = None) -> Any:
    return get_security_guard_client().redact_value(value, key_hint=key_hint)


def validate_runtime_file_path(path: str, *, require_file: bool = True) -> str:
    try:
        return get_security_guard_client().validate_file_policy(path=path, require_file=require_file)
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def validate_scoped_object_key(*, agent_id: str, object_key: str) -> str:
    try:
        return get_security_guard_client().validate_object_key(agent_id=agent_id, object_key=object_key)
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _provider_allowed_keys(provider: str, source: Mapping[str, str]) -> frozenset[str]:
    normalized = provider.strip().lower()
    if normalized not in PROVIDER_API_KEY_ENV_KEYS:
        return frozenset()
    provider_id = cast(ProviderId, normalized)

    allowed = {
        PROVIDER_AUTH_MODE_ENV_KEYS[provider_id],
        PROVIDER_VERIFIED_ENV_KEYS[provider_id],
    }
    project_key = PROVIDER_PROJECT_ENV_KEYS.get(provider_id)
    if project_key:
        allowed.add(project_key)
    base_url_key = PROVIDER_BASE_URL_ENV_KEYS.get(provider_id)
    if base_url_key:
        allowed.add(base_url_key)
    auth_mode_key = PROVIDER_AUTH_MODE_ENV_KEYS[provider_id]
    auth_mode = str(source.get(auth_mode_key) or "api_key").strip().lower()
    if auth_mode == "api_key":
        allowed.add(PROVIDER_API_KEY_ENV_KEYS[provider_id])
    if normalized == "claude":
        allowed.update({"CLAUDE_HOME", "CLAUDE_CONFIG_DIR"})
    auth_token_key = PROVIDER_AUTH_TOKEN_ENV_KEYS.get(normalized)
    if auth_token_key:
        allowed.add(auth_token_key)
    if normalized == "codex":
        allowed.add("CODEX_HOME")
    return frozenset(allowed)


_SAFE_TOOL_ENV_KEYS = frozenset(
    {
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "TMP",
        "TEMP",
        "TZ",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
    }
)
_SAFE_LLM_ENV_KEYS = frozenset({*_SAFE_TOOL_ENV_KEYS, "HOME"})


def _minimal_safe_env(
    source: dict[str, str],
    allowed_provider_keys: frozenset[str],
    overrides: dict[str, str],
    *,
    safe_env_keys: frozenset[str],
) -> dict[str, str]:
    """Return a restrictive environment subset when the security RPC is unavailable."""
    safe = {}
    for key in safe_env_keys:
        if key in source:
            safe[key] = source[key]
    for key in allowed_provider_keys:
        if key in source:
            safe[key] = source[key]
    safe.update(overrides)
    return safe


def _sanitize_env(
    base_env: Mapping[str, str] | None = None,
    *,
    allowed_provider_keys: frozenset[str] = frozenset(),
    env_overrides: Mapping[str, str] | None = None,
    safe_env_keys: frozenset[str],
) -> dict[str, str]:
    source = {}
    for key in safe_env_keys:
        value = os.environ.get(key)
        if value is not None:
            source[key] = value
    if base_env is not None:
        source.update({str(key): str(value) for key, value in dict(base_env).items()})
    overrides = {str(key): str(value) for key, value in dict(env_overrides or {}).items()}
    try:
        return get_security_guard_client().sanitize_environment(
            base_env=source,
            allowed_provider_keys=sorted(allowed_provider_keys),
            env_overrides=overrides,
        )
    except Exception:
        # Fail-safe: return minimal environment on RPC failure
        # Never fall through to unsanitized os.environ
        #
        # Log at WARNING only when SECURITY_GRPC_TARGET is explicitly configured
        # (operator expected the sidecar to be reachable). In dev/compose-lite
        # setups where the Rust security service isn't deployed, the sidecar is
        # intentionally absent and the minimal-safe-env fallback is the nominal
        # behavior — log at DEBUG to avoid spamming logs on every LLM turn.
        if os.environ.get("SECURITY_GRPC_TARGET"):
            _log.warning("security_guard_rpc_unavailable: falling back to minimal safe environment")
        else:
            _log.debug("security_guard_rpc_unavailable_nominal: sidecar not configured, using minimal safe env")
        return _minimal_safe_env(source, allowed_provider_keys, overrides, safe_env_keys=safe_env_keys)


def build_llm_subprocess_env(
    base_env: Mapping[str, str] | None = None,
    *,
    provider: str,
) -> dict[str, str]:
    """Return a minimal, provider-scoped environment for one LLM subprocess."""
    source = {}
    for key in _SAFE_LLM_ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            source[key] = value
    provider_keys_from_env = _provider_allowed_keys(provider, os.environ)
    for key in provider_keys_from_env:
        value = os.environ.get(key)
        if value is not None:
            source[key] = value
    if base_env is not None:
        source.update({str(key): str(value) for key, value in dict(base_env).items()})
    env = _sanitize_env(
        source,
        allowed_provider_keys=_provider_allowed_keys(provider, source),
        safe_env_keys=_SAFE_LLM_ENV_KEYS,
    )
    home = source.get("HOME")
    if home and "HOME" not in env:
        env["HOME"] = home
    return env


def build_tool_subprocess_env(
    base_env: Mapping[str, str] | None = None,
    *,
    env_overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a tool-safe environment with only explicit overrides added back."""
    env = _sanitize_env(base_env, env_overrides=env_overrides, safe_env_keys=_SAFE_TOOL_ENV_KEYS)
    if not dict(env_overrides or {}).get("HOME"):
        env.pop("HOME", None)
    return env
