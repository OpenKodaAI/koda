"""Sidecar service-discovery contract.

Workers used to talk to one sidecar replica via a hard-coded
``host:port`` (or UDS path). Operators may point each
``*_GRPC_TARGET`` at a comma-separated pool — the resolver translates
that to gRPC's native ``ipv4:`` scheme and the channel is built with
the round-robin LB policy enabled. A single hung sidecar replica then
stops bringing every worker to a halt.

These tests pin the resolver normalization and the channel options
applied for pool targets. They do NOT exercise live gRPC round-robin
behavior — that's covered by gRPC's own conformance tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from koda.internal_rpc import common


def test_single_tcp_target_unchanged() -> None:
    target, transport = common.resolve_grpc_target("memory:50063")
    assert target == "memory:50063"
    assert transport == "grpc-tcp"


def test_single_uds_path_normalized() -> None:
    target, transport = common.resolve_grpc_target("/var/run/koda/runtime.sock")
    assert target == "unix:///var/run/koda/runtime.sock"
    assert transport == "grpc-uds"


def test_uds_with_unix_prefix_passes_through() -> None:
    target, transport = common.resolve_grpc_target("unix:///var/run/koda.sock")
    assert target == "unix:///var/run/koda.sock"
    assert transport == "grpc-uds"


def test_multi_target_uses_ipv4_resolver_scheme() -> None:
    target, transport = common.resolve_grpc_target("a.svc:50063,b.svc:50063,c.svc:50063")
    assert target == "ipv4:a.svc:50063,b.svc:50063,c.svc:50063"
    assert transport == "grpc-tcp-pool"


def test_multi_target_with_whitespace_normalized() -> None:
    target, transport = common.resolve_grpc_target("a.svc:50063,  b.svc:50063 , c.svc:50063 ")
    assert target == "ipv4:a.svc:50063,b.svc:50063,c.svc:50063"
    assert transport == "grpc-tcp-pool"


def test_multi_target_collapses_to_single_when_only_one_endpoint() -> None:
    target, transport = common.resolve_grpc_target("a.svc:50063, , ")
    assert target == "a.svc:50063"
    assert transport == "grpc-tcp"


def test_uds_with_comma_in_path_does_not_split() -> None:
    """A pathological UDS path containing a comma must not be split as
    a pool — UDS targets are pinned to one process by definition."""
    target, transport = common.resolve_grpc_target("unix:///tmp/a,b.sock")
    assert target == "unix:///tmp/a,b.sock"
    assert transport == "grpc-uds"


def test_create_channel_applies_round_robin_options_for_pool_target() -> None:
    """When the resolver returns an ``ipv4:`` pool target the channel
    must be opened with the round-robin LB policy."""
    fake_channel = MagicMock()
    with (
        patch("koda.config.GRPC_TLS_ENABLED", False),
        patch("grpc.aio.insecure_channel", return_value=fake_channel) as spy,
    ):
        common.create_grpc_channel("ipv4:127.0.0.1:50063,127.0.0.2:50063", async_channel=True)

    args, kwargs = spy.call_args
    assert args[0] == "ipv4:127.0.0.1:50063,127.0.0.2:50063"
    options = kwargs.get("options") or []
    assert ("grpc.lb_policy_name", "round_robin") in options
    assert ("grpc.service_config", '{"loadBalancingPolicy":"round_robin"}') in options


def test_create_channel_omits_pool_options_for_single_target() -> None:
    """Single-target channels stay zero-overhead — no service config
    blob, so a misconfigured static target cannot regress through
    extra channel-options parsing."""
    fake_channel = MagicMock()
    with (
        patch("koda.config.GRPC_TLS_ENABLED", False),
        patch("grpc.aio.insecure_channel", return_value=fake_channel) as spy,
    ):
        common.create_grpc_channel("memory:50063", async_channel=True)

    _, kwargs = spy.call_args
    assert kwargs.get("options") in (None, [])
