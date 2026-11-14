#!/usr/bin/env python3
"""Quickstart diagnostics for the Docker-first Koda deployment."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen

# `python3 scripts/doctor.py` puts scripts/ first on sys.path, not the checkout.
REPO_ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # Docker Compose reads `export KEY=value` as KEY, so doctor must too.
        parts = key.split(None, 1)
        key = parts[1] if len(parts) == 2 and parts[0] == "export" else key.strip()
        values[key] = value.strip().strip("'").strip('"')
    return values


def parse_postgres_target(dsn: str) -> tuple[str, int]:
    parsed = urlparse(dsn)
    return parsed.hostname or "localhost", int(parsed.port or 5432)


def parse_http_target(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    if not parsed.hostname:
        raise ValueError(f"invalid URL: {url}")
    if parsed.port:
        return parsed.hostname, int(parsed.port)
    return parsed.hostname, 443 if parsed.scheme == "https" else 80


def check_socket(host: str, port: int, *, timeout: float = 2.0) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ok": True, "host": host, "port": port}
    except OSError as exc:
        return {"ok": False, "host": host, "port": port, "error": str(exc)}


def host_resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
    except OSError:
        return False
    return True


# Docker Compose keeps Postgres and SeaweedFS on its internal network and does not
# publish their ports on the host, so their service names resolve only inside the
# stack. Doctor probes them from the app container, the client that uses them.
COMPOSE_PROBE_SERVICE = "app"
COMPOSE_TCP_PROBE = (
    "import socket, sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=float(sys.argv[3])).close()"
)


# Compose quotes the line of a .env it cannot parse, value included. Its errors then name the
# file (`failed to read <env file>: ...`) or carry one of these phrases.
COMPOSE_ENV_PARSE_ERRORS = (
    "invalid template",
    "invalid interpolation",
    "unterminated quoted value",
    "unexpected character",
)
# Names whose values doctor treats as secrets when it repeats compose's output.
SECRET_NAME_MARKERS = ("PASSWORD", "PASSWD", "SECRET", "TOKEN", "KEY", "CREDENTIAL", "DSN")
REDACTED = "[redacted]"
# Shorter values are not usable secrets, and replacing them would garble the message.
MIN_REDACTED_LENGTH = 4


def secret_values(env: dict[str, str]) -> list[str]:
    """The values in ``env`` that doctor must never print: secret-named settings and URL passwords."""
    values: set[str] = set()
    for name, raw in env.items():
        value = str(raw or "").strip()
        if not value:
            continue
        if any(marker in name.upper() for marker in SECRET_NAME_MARKERS):
            values.update({value, quote(value, safe="")})
        if "://" in value:
            password = _dsn_password(value)
            if password:
                values.update({password, quote(password, safe="")})
    return sorted((value for value in values if len(value) >= MIN_REDACTED_LENGTH), key=len, reverse=True)


def redact(text: str, secrets: Iterable[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, REDACTED)
    return text


def _compose_failure_detail(output: str, *, env_path: Path, secrets: Iterable[str]) -> str:
    """What doctor repeats of a failed `docker compose` run, never a configured secret."""
    if str(env_path) in output or any(marker in output.lower() for marker in COMPOSE_ENV_PARSE_ERRORS):
        # The error names the offending line with its value, which may be the password itself.
        return (
            f"docker compose could not parse {env_path}; run "
            f"`docker compose --env-file {env_path} config -q` in {env_path.parent} to see where"
        )
    lines = output.strip().splitlines()
    return redact(lines[-1], secrets) if lines else ""


def check_socket_in_compose(
    host: str, port: int, *, env_file: Path, secrets: Iterable[str] = (), timeout: float = 2.0
) -> dict[str, Any]:
    """Open host:port from the app container of the compose project that ``env_file`` configures.

    ``secrets`` are the configured values that must not reach doctor's output when compose fails.
    """
    secrets = list(secrets)
    via = f"docker compose exec {COMPOSE_PROBE_SERVICE}"
    result: dict[str, Any] = {"host": host, "port": port, "via": via}
    env_path = env_file.resolve()
    command = [
        "docker",
        "compose",
        "--env-file",
        str(env_path),
        "exec",
        "-T",
        COMPOSE_PROBE_SERVICE,
        "python",
        "-c",
        COMPOSE_TCP_PROBE,
        host,
        str(port),
        str(timeout),
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed command; host and port come from the operator's .env
            command,
            cwd=str(env_path.parent),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            **result,
            "ok": False,
            "error": f"{host} does not resolve on this host and `{via}` could not run: {redact(str(exc), secrets)}",
        }
    if completed.returncode == 0:
        return {**result, "ok": True}
    output = completed.stderr or completed.stdout or ""
    detail = _compose_failure_detail(output, env_path=env_path, secrets=secrets)
    detail = detail or f"exit status {completed.returncode}"
    return {**result, "ok": False, "error": f"{host} does not resolve on this host and `{via}` failed: {detail}"}


def probe_service(host: str, port: int, *, env_file: Path | None, secrets: Iterable[str] = ()) -> dict[str, Any]:
    """Probe from this host when it resolves ``host``, otherwise from the compose app container."""
    if env_file is None or host_resolves(host):
        return check_socket(host, port)
    return check_socket_in_compose(host, port, env_file=env_file, secrets=secrets)


def fetch_json(url: str, *, timeout: float = 5.0, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local/control-plane health URL only
        return json.loads(response.read().decode("utf-8"))


def fetch_status(url: str, *, timeout: float = 5.0, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local/product URL only
        return {
            "status": getattr(response, "status", 200),
            "content_type": response.headers.get("Content-Type", ""),
        }


def read_bootstrap_file_path(base_url: str) -> str | None:
    """Where the setup-code file is, or None once an owner exists.

    Before login, onboarding/status answers only has_owner and
    bootstrap_required. The public auth/status still names the file while no
    owner exists, which is the only time the file is there.
    """
    try:
        payload = fetch_json(f"{base_url.rstrip('/')}/api/control-plane/auth/status")
    except Exception:
        return None
    value = payload.get("bootstrap_file_path")
    return str(value) if value else None


PLACEHOLDER_SECRET_PREFIX = "replace-with-"
# Copy of koda.config.STORAGE_SECRET_ENV_SOURCES: doctor runs on the host without
# Koda's dependencies. tests/test_doctor_strict.py keeps the two in sync.
STORAGE_SECRET_ENV_SOURCES: dict[str, tuple[str, ...]] = {
    "POSTGRES_PASSWORD": ("POSTGRES_PASSWORD", "KNOWLEDGE_V2_POSTGRES_DSN"),
    "S3_ACCESS_KEY_ID": ("S3_ACCESS_KEY_ID", "KNOWLEDGE_V2_S3_ACCESS_KEY_ID"),
    "S3_SECRET_ACCESS_KEY": ("S3_SECRET_ACCESS_KEY", "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY"),
}
PLACEHOLDER_SECRET_ROTATION_COMMAND = "python3 scripts/generate_env_secrets.py --all"
PLACEHOLDER_SECRET_ROTATION_DOC = "docs/install/local.md#rotating-placeholder-postgres-and-object-storage-secrets"


def _is_placeholder(value: str | None) -> bool:
    return str(value or "").strip().lower().startswith(PLACEHOLDER_SECRET_PREFIX)


def _is_real_secret(value: str) -> bool:
    """True for a configured value that is not an unedited .env.example placeholder."""
    cleaned = str(value or "").strip()
    return bool(cleaned) and not _is_placeholder(cleaned)


def api_tokens(raw: str | None) -> list[str]:
    """The break-glass tokens the control plane accepts from CONTROL_PLANE_API_TOKEN.

    The same rule as koda.control_plane.settings.parse_api_tokens: during a rotation the value is
    a comma-separated list (`new-token,old-token`), each token authenticates on its own, and an
    unedited placeholder never does. tests/test_doctor_api_token_rotation.py keeps the two in sync.
    """
    candidates = [token.strip() for token in str(raw or "").split(",") if token.strip()]
    return [token for token in candidates if not _is_placeholder(token)]


def _dsn_password(dsn: str | None) -> str:
    try:
        return unquote(urlparse(str(dsn or "").strip()).password or "")
    except ValueError:
        return ""


def check_storage_secrets(env: dict[str, str]) -> dict[str, Any]:
    """Fail while POSTGRES_PASSWORD or an S3_* secret is a placeholder. Reports names, never values."""
    placeholder_keys: list[str] = []
    for name, sources in STORAGE_SECRET_ENV_SOURCES.items():
        for source in sources:
            value = env.get(source)
            if source.endswith("_DSN"):
                value = _dsn_password(value)
            if _is_placeholder(value):
                placeholder_keys.append(name)
                break
    check: dict[str, Any] = {
        "name": "storage_secrets_not_placeholders",
        "ok": not placeholder_keys,
        "placeholder_keys": placeholder_keys,
    }
    if placeholder_keys:
        several = len(placeholder_keys) > 1
        check["rotation_command"] = PLACEHOLDER_SECRET_ROTATION_COMMAND
        check["user_action"] = (
            f"{', '.join(placeholder_keys)} {'still use' if several else 'still uses'} the public .env.example "
            f"placeholder. Replace {'them' if several else 'it'} with "
            f"`{PLACEHOLDER_SECRET_ROTATION_COMMAND}`. On an install that has already started, Postgres keeps "
            f"the old password: follow {PLACEHOLDER_SECRET_ROTATION_DOC} to apply the new one before restarting. "
            "The command only rewrites values that start with the placeholder: a placeholder password inside "
            "KNOWLEDGE_V2_POSTGRES_DSN must be edited by hand."
        )
    return check


# How Docker Compose builds the app's KNOWLEDGE_V2_POSTGRES_DSN from the .env
# (docker-compose.yml and the release compose, `app.environment`).
COMPOSE_POSTGRES_SOURCES = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
COMPOSE_POSTGRES_HOST = "postgres"
COMPOSE_POSTGRES_PORT = 5432


def is_native_env(env: dict[str, str]) -> bool:
    """Whether the .env is a native install's: it sets KNOWLEDGE_V2_POSTGRES_DSN, which Compose builds itself."""
    return bool(str(env.get("KNOWLEDGE_V2_POSTGRES_DSN", "")).strip())


def resolve_postgres_dsn(env: dict[str, str]) -> tuple[str, list[str], list[str]]:
    """Return the DSN the app connects with, the .env names it comes from, and the names still missing.

    A native install sets KNOWLEDGE_V2_POSTGRES_DSN itself. Under Docker Compose the
    .env holds only POSTGRES_*, and compose builds the DSN from them.
    """
    if is_native_env(env):
        return str(env["KNOWLEDGE_V2_POSTGRES_DSN"]).strip(), ["KNOWLEDGE_V2_POSTGRES_DSN"], []
    values = {name: str(env.get(name, "")).strip() for name in COMPOSE_POSTGRES_SOURCES}
    missing = [name for name, value in values.items() if not value]
    if missing:
        return "", [], missing
    dsn = (
        f"postgresql://{quote(values['POSTGRES_USER'], safe='')}:{quote(values['POSTGRES_PASSWORD'], safe='')}"
        f"@{COMPOSE_POSTGRES_HOST}:{COMPOSE_POSTGRES_PORT}/{quote(values['POSTGRES_DB'], safe='')}"
    )
    return dsn, list(COMPOSE_POSTGRES_SOURCES), []


def _first_configured(env: dict[str, str], names: tuple[str, ...]) -> tuple[str, str]:
    for name in names:
        value = str(env.get(name, "")).strip()
        if value:
            return value, name
    return "", ""


def object_storage_required(env: dict[str, str]) -> bool:
    """OBJECT_STORAGE_REQUIRED as Koda receives it: only `true` requires object storage.

    Unset means true. An empty value depends on who reads the .env. Compose passes it on as
    `true` (`${OBJECT_STORAGE_REQUIRED:-true}`). A native install loads the .env itself, and
    Koda's `_bool_env` reads an empty value as false.
    """
    raw = env.get("OBJECT_STORAGE_REQUIRED")
    if raw is None:
        return True
    value = str(raw).strip().lower()
    if not value:
        return not is_native_env(env)
    return value == "true"


def run_doctor(
    *,
    env: dict[str, str],
    base_url: str,
    dashboard_url: str | None = None,
    provider_id: str | None = None,
    env_file: Path | None = None,
    require_sandbox_doctor: bool = False,
) -> dict[str, Any]:
    """Run the basic checks.

    ``env_file`` is the .env the values came from: a compose service name that this
    host does not resolve is probed from that compose project's app container.
    """
    port = str(env.get("CONTROL_PLANE_PORT", "8090")).strip() or "8090"
    web_port = str(env.get("WEB_PORT", "3000")).strip() or "3000"
    configured_api_tokens = api_tokens(env.get("CONTROL_PLANE_API_TOKEN"))
    runtime_token = str(env.get("RUNTIME_LOCAL_UI_TOKEN", "")).strip()
    secrets = secret_values(env)
    postgres_dsn, postgres_sources, postgres_missing = resolve_postgres_dsn(env)
    storage_required = object_storage_required(env)
    object_storage_endpoint = str(env.get("KNOWLEDGE_V2_S3_ENDPOINT_URL", "")).strip()
    object_storage_bucket = str(env.get("KNOWLEDGE_V2_S3_BUCKET", "")).strip()
    # Compose passes S3_* to the app as KNOWLEDGE_V2_S3_*; a native install sets the latter.
    access_key, access_key_source = _first_configured(env, STORAGE_SECRET_ENV_SOURCES["S3_ACCESS_KEY_ID"])
    secret_key, secret_key_source = _first_configured(env, STORAGE_SECRET_ENV_SOURCES["S3_SECRET_ACCESS_KEY"])
    if dashboard_url is None:
        parsed = urlparse(base_url)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or "127.0.0.1"
        dashboard_url = f"{scheme}://{host}:{web_port}"

    def object_storage_check(name: str, ok: bool, **detail: Any) -> dict[str, Any]:
        # With OBJECT_STORAGE_REQUIRED=false these are reported but never fail doctor.
        return {"name": name, "ok": ok, "required": storage_required, **detail}

    checks: list[dict[str, Any]] = [
        {"name": "control_plane_port", "ok": bool(port), "value": port},
        {"name": "web_port", "ok": bool(web_port), "value": web_port},
        {"name": "control_plane_api_token", "ok": bool(configured_api_tokens)},
        {"name": "runtime_local_ui_token", "ok": _is_real_secret(runtime_token)},
        object_storage_check("object_storage_endpoint", bool(object_storage_endpoint), value=object_storage_endpoint),
        object_storage_check("object_storage_bucket", bool(object_storage_bucket), value=object_storage_bucket),
        object_storage_check(
            "object_storage_access_key",
            bool(access_key),
            source=access_key_source or " or ".join(STORAGE_SECRET_ENV_SOURCES["S3_ACCESS_KEY_ID"]),
        ),
        object_storage_check(
            "object_storage_secret_key",
            bool(secret_key),
            source=secret_key_source or " or ".join(STORAGE_SECRET_ENV_SOURCES["S3_SECRET_ACCESS_KEY"]),
        ),
        check_storage_secrets(env),
    ]

    if postgres_dsn:
        checks.append({"name": "postgres_dsn", "ok": True, "source": postgres_sources})
        host, pg_port = parse_postgres_target(postgres_dsn)
        checks.append({"name": "postgres_socket", **probe_service(host, pg_port, env_file=env_file, secrets=secrets)})
    else:
        error = (
            f"{', '.join(postgres_missing)} {'are' if len(postgres_missing) > 1 else 'is'} not set. Docker Compose "
            "builds the DSN from POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB; a native install sets "
            "KNOWLEDGE_V2_POSTGRES_DSN."
        )
        checks.append({"name": "postgres_dsn", "ok": False, "missing": postgres_missing, "error": error})
        checks.append({"name": "postgres_socket", "ok": False, "error": "no Postgres DSN to probe"})

    if object_storage_endpoint:
        host, object_storage_port = parse_http_target(object_storage_endpoint)
        checks.append(
            object_storage_check(
                "object_storage_socket",
                **probe_service(host, object_storage_port, env_file=env_file, secrets=secrets),
            )
        )
    else:
        checks.append(
            object_storage_check("object_storage_socket", False, error="KNOWLEDGE_V2_S3_ENDPOINT_URL is missing")
        )

    try:
        health_payload = fetch_json(f"{base_url.rstrip('/')}/health")
        checks.append({"name": "control_plane_health", "ok": True, "payload": health_payload})
    except Exception as exc:  # pragma: no cover - exercised via failure payload expectations
        checks.append({"name": "control_plane_health", "ok": False, "error": str(exc)})

    try:
        dashboard_payload = fetch_status(dashboard_url)
        checks.append(
            {
                "name": "web_dashboard",
                "ok": int(dashboard_payload["status"]) < 400,
                "payload": dashboard_payload,
            }
        )
    except Exception as exc:  # pragma: no cover - exercised via failure payload expectations
        checks.append({"name": "web_dashboard", "ok": False, "error": str(exc)})

    onboarding_payload: dict[str, Any] = {}
    try:
        onboarding_payload = fetch_json(f"{base_url.rstrip('/')}/api/control-plane/onboarding/status")
        checks.append(
            {
                "name": "onboarding_status",
                "ok": True,
                "has_owner": bool(onboarding_payload.get("has_owner")),
                "bootstrap_required": bool(onboarding_payload.get("bootstrap_required")),
                "bootstrap_file_path": read_bootstrap_file_path(base_url),
            }
        )
    except Exception as exc:  # pragma: no cover - exercised via failure payload expectations
        checks.append({"name": "onboarding_status", "ok": False, "error": str(exc)})

    if provider_id:
        onboarding_url = f"{base_url.rstrip('/')}/api/control-plane/onboarding/status"
        try:
            # One token of a rotation list, as the CLI sends it: the server never accepts the raw list.
            headers = {"Authorization": f"Bearer {configured_api_tokens[0]}"} if configured_api_tokens else None
            payload = fetch_json(onboarding_url, headers=headers)
            provider_rows = [row for row in payload.get("providers", []) if row.get("provider_id") == provider_id]
            provider_ok = bool(provider_rows and provider_rows[0].get("verified"))
            checks.append({"name": "provider_verification", "ok": provider_ok, "provider_id": provider_id})
        except Exception as exc:  # pragma: no cover - exercised via failure payload expectations
            checks.append({"name": "provider_verification", "ok": False, "provider_id": provider_id, "error": str(exc)})

    sandbox_doctor = build_sandbox_doctor(env)
    sandbox_status = sandbox_doctor.get("status")
    sandbox_check: dict[str, Any] = {
        "name": "sandbox_doctor",
        "ok": sandbox_status in {"passed", "degraded"} or (sandbox_status == "skipped" and not require_sandbox_doctor),
        "status": sandbox_status,
        "failed_checks": [
            item.get("id")
            for item in sandbox_doctor.get("checks", [])
            if isinstance(item, dict) and item.get("status") == "failed"
        ],
    }
    if sandbox_status == "skipped":
        sandbox_check["user_action"] = SANDBOX_DOCTOR_RUN_HINT
    checks.append(sandbox_check)

    ok = all(bool(item.get("ok")) or item.get("required") is False for item in checks)
    return {
        "ok": ok,
        "object_storage_required": storage_required,
        "checks": checks,
        "sandbox_doctor": sandbox_doctor,
        "base_url": base_url,
        "dashboard_url": dashboard_url,
        "dashboard_setup_url": f"{dashboard_url.rstrip('/')}/setup",
        "setup_url": f"{dashboard_url.rstrip('/')}/setup",
        "legacy_setup_url": f"{base_url.rstrip('/')}/setup",
    }


def _stat_mode(path: Path) -> int | None:
    try:
        return path.stat().st_mode & 0o777
    except OSError:
        return None


def run_strict_hardening(env: dict[str, str], *, env_file: Path) -> list[dict[str, Any]]:
    """Phase F — pre-deploy hardening checks matching
    ``docs/operations/hardening.md``.

    Each check returns ``{name, ok, ...detail}``. Strict mode AND-s
    all of them so a deployment that fails any single check is
    refused by ``--strict``.
    """
    checks: list[dict[str, Any]] = []

    # --- Filesystem & secrets -------------------------------------------------
    state_root = Path(env.get("STATE_ROOT_DIR", "/var/lib/koda/state").strip() or "/var/lib/koda/state")
    state_mode = _stat_mode(state_root)
    checks.append(
        {
            "name": "state_root_owner_only_perms",
            "ok": state_mode is not None and state_mode == 0o700,
            "path": str(state_root),
            "mode": f"{state_mode:o}" if state_mode is not None else None,
            "expected": "700",
        }
    )

    master_key_path = Path(
        env.get("CONTROL_PLANE_MASTER_KEY_FILE", "").strip() or str(state_root / "control_plane" / ".master.key")
    )
    master_mode = _stat_mode(master_key_path)
    checks.append(
        {
            "name": "master_key_perms_0600",
            "ok": master_mode is not None and master_mode == 0o600,
            "path": str(master_key_path),
            "mode": f"{master_mode:o}" if master_mode is not None else None,
            "expected": "600",
        }
    )

    env_mode = _stat_mode(env_file)
    checks.append(
        {
            "name": "env_file_perms_0600",
            "ok": env_mode is None or env_mode == 0o600,
            "path": str(env_file),
            "mode": f"{env_mode:o}" if env_mode is not None else None,
            "note": "skipped when .env file does not exist",
        }
    )

    # --- Auth posture ---------------------------------------------------------
    # Each token of a rotation list authenticates on its own, so each one must be strong.
    configured_api_tokens = api_tokens(env.get("CONTROL_PLANE_API_TOKEN"))
    shortest_api_token = min((len(token) for token in configured_api_tokens), default=0)
    checks.append(
        {
            "name": "control_plane_api_token_strong",
            "ok": bool(configured_api_tokens) and shortest_api_token >= 32,
            "length": shortest_api_token,
            "tokens": len(configured_api_tokens),
        }
    )

    session_secret = env.get("WEB_OPERATOR_SESSION_SECRET", "").strip()
    checks.append(
        {
            "name": "web_operator_session_secret_strong",
            "ok": len(session_secret) >= 32 and _is_real_secret(session_secret),
            "length": len(session_secret),
        }
    )

    runtime_token = env.get("RUNTIME_LOCAL_UI_TOKEN", "").strip()
    checks.append(
        {
            "name": "runtime_local_ui_token_strong",
            "ok": len(runtime_token) >= 32 and _is_real_secret(runtime_token),
            "length": len(runtime_token),
        }
    )

    allowed_user_ids = env.get("ALLOWED_USER_IDS", "").strip()
    checks.append(
        {
            "name": "allowed_user_ids_set",
            "ok": bool(allowed_user_ids),
            "note": "empty means no Telegram user is authorized",
        }
    )

    allow_loopback = env.get("ALLOW_LOOPBACK_BOOTSTRAP", "false").strip().lower()
    checks.append(
        {
            "name": "loopback_bootstrap_disabled_in_production",
            "ok": allow_loopback in {"false", "0", "no", "off", ""},
            "value": allow_loopback,
        }
    )

    # --- Browser sandbox ------------------------------------------------------
    browser_private = env.get("BROWSER_ALLOW_PRIVATE_NETWORK", "false").strip().lower()
    checks.append(
        {
            "name": "browser_private_network_disabled",
            "ok": browser_private in {"false", "0", "no", "off", ""},
            "value": browser_private,
        }
    )

    # --- Audit retention ------------------------------------------------------
    try:
        retention = int(env.get("AUDIT_RETENTION_DAYS", "90"))
    except ValueError:
        retention = 0
    checks.append(
        {
            "name": "audit_retention_at_least_90_days",
            "ok": retention >= 90,
            "value": retention,
        }
    )

    # --- Cgroup root (Linux only) --------------------------------------------
    import sys as _sys

    if _sys.platform == "linux":
        cgroup_root = Path(env.get("KODA_CGROUP_ROOT", "/sys/fs/cgroup/koda"))
        checks.append(
            {
                "name": "cgroup_root_writable_for_isolation",
                "ok": cgroup_root.exists() and os_access(cgroup_root, write=True),
                "path": str(cgroup_root),
                "note": "required when KODA_AGENT_DEFAULT_* limits are set",
            }
        )

    return checks


def os_access(path: Path, *, write: bool) -> bool:
    import os as _os

    mode = _os.W_OK if write else _os.R_OK
    try:
        return _os.access(str(path), mode)
    except OSError:
        return False


SANDBOX_DOCTOR_RUN_HINT = (
    "The sandbox check needs Koda's Python dependencies. Run doctor from the source checkout with them: "
    "`uv run python scripts/doctor.py --env-file .env`."
)


def _sandbox_doctor_result(status: str, *, severity: str, message: str, user_action: str) -> dict[str, Any]:
    return {
        "doctor_version": "sandbox_doctor.v1",
        "schema_version": "sandbox_doctor.v1",
        "status": status,
        "checks": [
            {
                "id": f"sandbox_doctor_{status}",
                "scope": "shell",
                "title": "Sandbox doctor",
                "severity": severity,
                "status": status,
                "message": message,
                "user_action": user_action,
            }
        ],
        "degraded_components": ["sandbox"],
    }


def _import_sandbox_doctor() -> Any:
    root = str(REPO_ROOT)
    if (REPO_ROOT / "koda" / "__init__.py").is_file() and root not in sys.path:
        # Appended, so an interpreter's own installed packages keep precedence.
        sys.path.append(root)
    from koda.services.sandbox_doctor import build_cli_sandbox_doctor_payload

    return build_cli_sandbox_doctor_payload


def _koda_installed() -> bool:
    """Whether this interpreter imports `koda` by itself, without the checkout doctor appends to sys.path."""
    try:
        return importlib.util.find_spec("koda") is not None
    except (ImportError, ValueError):
        return False


def _resolved(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser().absolute()


def _is_koda_environment() -> bool:
    """Whether this interpreter is meant to run Koda, so a missing dependency means a broken install.

    It is when Koda is installed in it, or when it runs from the checkout's `.venv` or from the
    environment that VIRTUAL_ENV or UV_PROJECT_ENVIRONMENT names (uv reads a relative one against
    the project root). Any other interpreter, such as the system python3 the install docs use, is
    not Koda's.
    """
    environments = [REPO_ROOT / ".venv"]
    for name in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        value = os.environ.get(name, "").strip()
        if value:
            path = Path(value).expanduser()
            environments.append(path if path.is_absolute() else REPO_ROOT / path)
    prefix = _resolved(Path(sys.prefix))
    return any(_resolved(path) == prefix for path in environments) or _koda_installed()


SANDBOX_DOCTOR_REINSTALL_HINT = (
    "Koda's own Python environment is missing one of its dependencies. Reinstall them (`uv sync` in the source "
    "checkout), then run doctor again."
)


def build_sandbox_doctor(env: dict[str, str]) -> dict[str, Any]:
    # Decided before the import appends the checkout to sys.path, which makes `koda` importable anywhere.
    koda_environment = _is_koda_environment()
    try:
        build_payload = _import_sandbox_doctor()
    except ModuleNotFoundError as exc:
        missing = str(exc.name or "")
        if not missing or missing.split(".")[0] == "koda":
            # Koda itself is missing: doctor is not running from a source checkout or an install.
            return _sandbox_doctor_unavailable(exc)
        if koda_environment:
            # Koda's own environment lacks a package it needs: a broken install must fail doctor.
            return _sandbox_doctor_unavailable(exc, user_action=SANDBOX_DOCTOR_REINSTALL_HINT)
        # Doctor itself needs only the standard library; this interpreter (often the system
        # python3) is not Koda's and lacks the third-party packages Koda imports.
        return _sandbox_doctor_result(
            "skipped",
            severity="info",
            message=f"{sys.executable} is not Koda's Python environment and cannot import its dependencies: {exc}",
            user_action=SANDBOX_DOCTOR_RUN_HINT,
        )
    except Exception as exc:
        return _sandbox_doctor_unavailable(exc)
    try:
        return dict(build_payload(env))
    except Exception as exc:
        return _sandbox_doctor_unavailable(exc)


def _sandbox_doctor_unavailable(
    exc: BaseException,
    *,
    user_action: str = "Run doctor from a complete Koda install with Python package imports available.",
) -> dict[str, Any]:
    return _sandbox_doctor_result("unavailable", severity="warning", message=str(exc), user_action=user_action)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--dashboard-url", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Phase F — pre-deploy hardening gate. Adds the checklist "
            "from docs/operations/hardening.md to the default checks; "
            "exits non-zero if any hardening item fails."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    env_values = load_env_file(args.env_file)
    payload = run_doctor(
        env=env_values,
        base_url=args.base_url,
        dashboard_url=args.dashboard_url,
        provider_id=args.provider,
        env_file=args.env_file,
        require_sandbox_doctor=args.strict,
    )
    if args.strict:
        strict_checks = run_strict_hardening(env_values, env_file=args.env_file)
        payload["strict_checks"] = strict_checks
        payload["ok"] = bool(payload["ok"]) and all(bool(item.get("ok")) for item in strict_checks)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
