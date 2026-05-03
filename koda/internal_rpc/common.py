"""Shared selection helpers for Rust-backed internal RPC seams."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from koda import config

GENERATED_PROTO_ROOT = Path(__file__).resolve().parent / "generated"


def resolve_grpc_target(raw_target: str) -> tuple[str, str]:
    """Normalize a target string into a (target, transport_tag) tuple.

    Accepts a comma-separated list of host:port endpoints, e.g.
    ``"sidecar-a:50063,sidecar-b:50063"``. Multi-target strings are
    translated to gRPC's ``ipv4:`` resolver scheme so the channel
    natively load-balances across the configured pool — workers stop
    being pinned to one sidecar replica and a single hung instance can
    no longer freeze every caller. UDS targets stay untouched: a UDS
    path inherently points at one process so the pool concept does not
    apply there.
    """
    target = raw_target.strip()
    if not target.startswith(("unix://", "/")) and "," in target:
        endpoints = [chunk.strip() for chunk in target.split(",") if chunk.strip()]
        if len(endpoints) > 1:
            return f"ipv4:{','.join(endpoints)}", "grpc-tcp-pool"
        if endpoints:
            target = endpoints[0]
    if target.startswith("unix://"):
        return target, "grpc-uds"
    if target.startswith("/"):
        return f"unix://{target}", "grpc-uds"
    return target, "grpc-tcp"


def _grpc_pool_options() -> list[tuple[str, str]]:
    """Channel options that enable client-side round-robin balancing
    across the addresses returned by the ``ipv4:`` resolver. The
    service-config JSON is the formal way to set the LB policy in
    grpc-python and is honored by both ``grpc`` and ``grpc.aio``."""
    return [
        ("grpc.lb_policy_name", "round_robin"),
        ("grpc.service_config", '{"loadBalancingPolicy":"round_robin"}'),
    ]


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

        # only pass ``options`` when the target is a multi-
        # endpoint pool. Keeping the single-target call signature
        # untouched preserves backward compatibility with test stubs
        # that mocked ``insecure_channel`` as ``lambda target, ...``
        # before the LB plumbing existed.
        if target.startswith("ipv4:"):
            options = _grpc_pool_options()
            if async_channel:
                return grpc_aio.secure_channel(target, credentials, options=options)
            return grpc.secure_channel(target, credentials, options=options)
        if async_channel:
            return grpc_aio.secure_channel(target, credentials)
        return grpc.secure_channel(target, credentials)

    # TLS disabled — backward-compatible insecure channel.
    if target.startswith("ipv4:"):
        options = _grpc_pool_options()
        if async_channel:
            import grpc.aio as grpc_aio

            return grpc_aio.insecure_channel(target, options=options)
        import grpc

        return grpc.insecure_channel(target, options=options)
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


def make_internal_breaker(name: str) -> Any:
    """Process-local circuit breaker for an internal RPC.

    Each gRPC client constructs one breaker keyed by the upstream
    service name (``"runtime_kernel"``, ``"memory_engine"`` etc.).
    The breaker registry is process-local: repeat calls with the same
    name return the same instance so all sites of one client share
    state, and the open/closed transitions are coherent across the
    worker.

    The numeric thresholds are sourced from
    ``koda.config.INTERNAL_RPC_BREAKER_*`` so an operator can widen
    or tighten them without code changes. The default values were
    picked to match the cascading-deadlock incident the breaker is
    designed to break out of.
    """
    from koda.internal_rpc.circuit_breaker import get_breaker

    return get_breaker(
        name,
        failure_threshold=int(config.INTERNAL_RPC_BREAKER_THRESHOLD),
        window_seconds=float(config.INTERNAL_RPC_BREAKER_WINDOW_SECONDS),
        open_seconds=float(config.INTERNAL_RPC_BREAKER_OPEN_SECONDS),
    )


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
