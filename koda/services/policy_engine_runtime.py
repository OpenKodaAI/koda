"""Process-local lazy singleton of :class:`PolicyEngineClient`.

Wires the policy-engine into the queue_manager hot path (ingest gate +
post-LLM spend ledger). Each worker holds at most one gRPC channel to
the engine; the channel is created on first use, reused across all
subsequent calls in the same process, and closed when the process
exits.

When ``config.POLICY_ENGINE_ENABLED`` is ``False`` the helper returns
``None`` and the queue_manager wrappers
(:func:`koda.internal_rpc.policy_engine.check_ingest_or_allow` and
:func:`koda.internal_rpc.policy_engine.record_spend_safe`) short-
circuit to a permissive default — single-tenant deployments without a
configured workspace policy pay zero overhead.

Failures to start the channel (engine unreachable at boot) are
swallowed with a single log line; subsequent calls keep retrying. The
permissive fallback in the public wrappers ensures a transient outage
doesn't trap user traffic.
"""

from __future__ import annotations

import asyncio

from koda import config
from koda.internal_rpc.policy_engine import PolicyEngineClient
from koda.logging_config import get_logger

log = get_logger(__name__)


_CLIENT: PolicyEngineClient | None = None
_LOCK = asyncio.Lock()
_START_FAILED = False


async def get_policy_engine_client() -> PolicyEngineClient | None:
    """Return the process-local client, or ``None`` when the policy
    engine is disabled / unreachable.

    Repeated calls return the same instance. The first call lazily
    opens the gRPC channel; subsequent calls are O(1).
    """
    global _CLIENT, _START_FAILED
    if not config.POLICY_ENGINE_ENABLED:
        return None
    if _CLIENT is not None:
        return _CLIENT
    if _START_FAILED:
        # Channel start failed at least once; honor the breaker-style
        # behavior baked into the public wrappers (permissive
        # fallback) and don't keep trying every request.
        return None
    async with _LOCK:
        if _CLIENT is not None:
            return _CLIENT
        if _START_FAILED:
            return None
        client = PolicyEngineClient()
        try:
            await client.start()
        except Exception:
            log.exception("policy_engine_client_start_failed")
            _START_FAILED = True
            return None
        _CLIENT = client
        return _CLIENT


async def shutdown_policy_engine_client() -> None:
    """Close the singleton channel. Called from worker shutdown."""
    global _CLIENT
    async with _LOCK:
        if _CLIENT is None:
            return
        client = _CLIENT
        _CLIENT = None
    try:
        await client.stop()
    except Exception:
        log.exception("policy_engine_client_stop_failed")


def _reset_for_tests() -> None:
    """Test helper — reset the singleton state."""
    global _CLIENT, _START_FAILED
    _CLIENT = None
    _START_FAILED = False
