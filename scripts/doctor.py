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

    ok = all(bool(item.get("ok")) for item in checks)
    return {
        "ok": ok,
        "checks": checks,
        "base_url": base_url,
        "dashboard_url": dashboard_url,
        "setup_url": f"{base_url.rstrip('/')}/setup",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--dashboard-url", default=None)
    parser.add_argument("--provider", default=None)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = run_doctor(
        env=load_env_file(args.env_file),
        base_url=args.base_url,
        dashboard_url=args.dashboard_url,
        provider_id=args.provider,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
