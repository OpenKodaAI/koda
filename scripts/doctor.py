#!/usr/bin/env python3
"""Quickstart diagnostics for the Docker-first Koda deployment."""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
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


def run_doctor(
    *,
    env: dict[str, str],
    base_url: str,
    dashboard_url: str | None = None,
    provider_id: str | None = None,
) -> dict[str, Any]:
    port = str(env.get("CONTROL_PLANE_PORT", "8090")).strip() or "8090"
    web_port = str(env.get("WEB_PORT", "3000")).strip() or "3000"
    api_token = str(env.get("CONTROL_PLANE_API_TOKEN", "")).strip()
    runtime_token = str(env.get("RUNTIME_LOCAL_UI_TOKEN", "")).strip()
    postgres_dsn = str(env.get("KNOWLEDGE_V2_POSTGRES_DSN", "")).strip()
    object_storage_endpoint = str(env.get("KNOWLEDGE_V2_S3_ENDPOINT_URL", "")).strip()
    object_storage_bucket = str(env.get("KNOWLEDGE_V2_S3_BUCKET", "")).strip()
    object_storage_access_key = str(env.get("KNOWLEDGE_V2_S3_ACCESS_KEY_ID", "")).strip()
    object_storage_secret_key = str(env.get("KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY", "")).strip()
    if dashboard_url is None:
        parsed = urlparse(base_url)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or "127.0.0.1"
        dashboard_url = f"{scheme}://{host}:{web_port}"

    checks: list[dict[str, Any]] = [
        {"name": "control_plane_port", "ok": bool(port), "value": port},
        {"name": "web_port", "ok": bool(web_port), "value": web_port},
        {"name": "control_plane_api_token", "ok": bool(api_token)},
        {"name": "runtime_local_ui_token", "ok": bool(runtime_token)},
        {"name": "object_storage_endpoint", "ok": bool(object_storage_endpoint), "value": object_storage_endpoint},
        {"name": "object_storage_bucket", "ok": bool(object_storage_bucket), "value": object_storage_bucket},
        {"name": "object_storage_access_key", "ok": bool(object_storage_access_key)},
        {"name": "object_storage_secret_key", "ok": bool(object_storage_secret_key)},
    ]

    if postgres_dsn:
        host, pg_port = parse_postgres_target(postgres_dsn)
        checks.append({"name": "postgres_socket", **check_socket(host, pg_port)})
    else:
        checks.append({"name": "postgres_socket", "ok": False, "error": "KNOWLEDGE_V2_POSTGRES_DSN is missing"})

    if object_storage_endpoint:
        host, object_storage_port = parse_http_target(object_storage_endpoint)
        checks.append({"name": "object_storage_socket", **check_socket(host, object_storage_port)})
    else:
        checks.append(
            {"name": "object_storage_socket", "ok": False, "error": "KNOWLEDGE_V2_S3_ENDPOINT_URL is missing"}
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
                "bootstrap_file_path": onboarding_payload.get("bootstrap_file_path"),
            }
        )
    except Exception as exc:  # pragma: no cover - exercised via failure payload expectations
        checks.append({"name": "onboarding_status", "ok": False, "error": str(exc)})

    if provider_id:
        onboarding_url = f"{base_url.rstrip('/')}/api/control-plane/onboarding/status"
        try:
            headers = {"Authorization": f"Bearer {api_token}"} if api_token else None
            payload = fetch_json(onboarding_url, headers=headers)
            provider_rows = [row for row in payload.get("providers", []) if row.get("provider_id") == provider_id]
            provider_ok = bool(provider_rows and provider_rows[0].get("verified"))
            checks.append({"name": "provider_verification", "ok": provider_ok, "provider_id": provider_id})
        except Exception as exc:  # pragma: no cover - exercised via failure payload expectations
            checks.append({"name": "provider_verification", "ok": False, "provider_id": provider_id, "error": str(exc)})

    sandbox_doctor = build_sandbox_doctor(env)
    checks.append(
        {
            "name": "sandbox_doctor",
            "ok": sandbox_doctor.get("status") in {"passed", "degraded"},
            "status": sandbox_doctor.get("status"),
            "failed_checks": [
                item.get("id")
                for item in sandbox_doctor.get("checks", [])
                if isinstance(item, dict) and item.get("status") == "failed"
            ],
        }
    )

    ok = all(bool(item.get("ok")) for item in checks)
    return {
        "ok": ok,
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
    api_token = env.get("CONTROL_PLANE_API_TOKEN", "").strip()
    checks.append(
        {
            "name": "control_plane_api_token_strong",
            "ok": len(api_token) >= 32 and not api_token.startswith("replace-with"),
            "length": len(api_token),
        }
    )

    session_secret = env.get("WEB_OPERATOR_SESSION_SECRET", "").strip()
    checks.append(
        {
            "name": "web_operator_session_secret_strong",
            "ok": len(session_secret) >= 32 and not session_secret.startswith("replace-with"),
            "length": len(session_secret),
        }
    )

    runtime_token = env.get("RUNTIME_LOCAL_UI_TOKEN", "").strip()
    checks.append(
        {
            "name": "runtime_local_ui_token_strong",
            "ok": len(runtime_token) >= 32 and not runtime_token.startswith("replace-with"),
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


def build_sandbox_doctor(env: dict[str, str]) -> dict[str, Any]:
    try:
        from koda.services.sandbox_doctor import build_cli_sandbox_doctor_payload

        return build_cli_sandbox_doctor_payload(env)
    except Exception as exc:  # pragma: no cover - defensive for packaged installs
        return {
            "doctor_version": "sandbox_doctor.v1",
            "schema_version": "sandbox_doctor.v1",
            "status": "unavailable",
            "checks": [
                {
                    "id": "sandbox_doctor_unavailable",
                    "scope": "shell",
                    "title": "Sandbox doctor",
                    "severity": "warning",
                    "status": "unavailable",
                    "message": str(exc),
                    "user_action": "Run doctor from a complete Koda install with Python package imports available.",
                }
            ],
            "degraded_components": ["sandbox"],
        }


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


def main() -> int:
    args = _build_parser().parse_args()
    env_values = load_env_file(args.env_file)
    payload = run_doctor(
        env=env_values,
        base_url=args.base_url,
        dashboard_url=args.dashboard_url,
        provider_id=args.provider,
    )
    if args.strict:
        strict_checks = run_strict_hardening(env_values, env_file=args.env_file)
        payload["strict_checks"] = strict_checks
        payload["ok"] = bool(payload["ok"]) and all(bool(item.get("ok")) for item in strict_checks)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
