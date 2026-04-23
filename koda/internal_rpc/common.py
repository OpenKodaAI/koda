"""Shared selection helpers for Rust-backed internal RPC seams."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from koda import config

GENERATED_PROTO_ROOT = Path(__file__).resolve().parent / "generated"


def resolve_grpc_target(raw_target: str) -> tuple[str, str]:
    target = raw_target.strip()
    if target.startswith("unix://"):
        return target, "grpc-uds"
    if target.startswith("/"):
        return f"unix://{target}", "grpc-uds"
    return target, "grpc-tcp"


def create_grpc_channel(target: str, *, async_channel: bool = False) -> Any:
    """Create a gRPC channel, optionally secured with TLS/mTLS.

    When ``config.GRPC_TLS_ENABLED`` is ``True`` the channel uses
    ``ssl_channel_credentials`` built from the configured CA cert and optional
    client cert/key pair (mTLS).  When the flag is ``False`` the channel falls
    back to an insecure connection for backward compatibility.
    """

    if config.GRPC_TLS_ENABLED:
        import logging

        import grpc
        import grpc.aio as grpc_aio

        _log = logging.getLogger(__name__)

        root_certificates: bytes | None = None
        private_key: bytes | None = None
        certificate_chain: bytes | None = None

        try:
            if config.GRPC_TLS_CA_CERT:
                with open(config.GRPC_TLS_CA_CERT, "rb") as fh:
                    root_certificates = fh.read()

            if config.GRPC_TLS_CLIENT_CERT and config.GRPC_TLS_CLIENT_KEY:
                with open(config.GRPC_TLS_CLIENT_KEY, "rb") as fh:
                    private_key = fh.read()
                with open(config.GRPC_TLS_CLIENT_CERT, "rb") as fh:
                    certificate_chain = fh.read()
        except (FileNotFoundError, OSError) as exc:
            raise RuntimeError(
                f"gRPC TLS is enabled but certificate files could not be read: {exc}. "
                "Check GRPC_TLS_CA_CERT, GRPC_TLS_CLIENT_CERT, and GRPC_TLS_CLIENT_KEY paths."
            ) from exc

        credentials = grpc.ssl_channel_credentials(
            root_certificates=root_certificates,
            private_key=private_key,
            certificate_chain=certificate_chain,
        )

        _log.info("grpc_tls_channel_created", extra={"target": target, "mtls": private_key is not None})

        if async_channel:
            return grpc_aio.secure_channel(target, credentials)
        return grpc.secure_channel(target, credentials)

    # TLS disabled — backward-compatible insecure channel.
    if async_channel:
        import grpc.aio as grpc_aio

        return grpc_aio.insecure_channel(target)

    import grpc

    return grpc.insecure_channel(target)


def ensure_generated_proto_path() -> Path:
    root = GENERATED_PROTO_ROOT
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def parse_boolish(value: object, *, default: bool = False) -> bool:
    """Interpret config-style truthy values from health payloads and detail maps."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def normalize_internal_service_probe(
    *,
    base_health: dict[str, object],
    service: str,
    ready: bool,
    status: str,
    details: dict[str, object] | None,
) -> dict[str, object]:
    """Normalize internal gRPC probe responses into an honest cutover payload."""
    normalized_status = str(status or ("ready" if ready else "not_ready")).strip() or "unknown"
    normalized_details = {str(key): str(value) for key, value in dict(details or {}).items()}
    maturity = str(normalized_details.get("maturity") or normalized_status).strip() or "unknown"
    default_authoritative = bool(ready) and normalized_status.lower() not in {
        "stub",
        "mirror",
        "transitional",
    }
    default_authoritative = default_authoritative and maturity.lower() not in {
        "stub",
        "mirror",
        "transitional",
    }
    authoritative = parse_boolish(
        normalized_details.get("authoritative"),
        default=default_authoritative,
    )
    production_ready = parse_boolish(
        normalized_details.get("production_ready"),
        default=bool(ready) and authoritative,
    )
    return {
        **base_health,
        "service": service,
        "status": normalized_status,
        "details": normalized_details,
        "connected": True,
        "verified": True,
        "ready": bool(ready),
        "authoritative": authoritative,
        "production_ready": production_ready,
        "cutover_allowed": bool(ready) and authoritative and production_ready,
        "maturity": maturity,
        "startup_error": None,
    }


def normalize_agent_scope(agent_id: str | None) -> str | None:
    normalized = str(agent_id or "").strip().lower()
    return normalized or None


@dataclass(frozen=True)
class EngineSelection:
    backend: Literal["grpc"]
    reason: str
    mode: str
    agent_id: str | None


def select_engine_backend(
    *,
    mode: str,
    agent_id: str | None,
) -> EngineSelection:
    _ = mode
    normalized_agent_id = normalize_agent_scope(agent_id)
    return EngineSelection(
        backend="grpc",
        reason="rust-default",
        mode="rust",
        agent_id=normalized_agent_id,
    )
