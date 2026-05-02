//! koda-rpc-gateway — sidecar connection multiplexer (Phase 1D).
//!
//! Workers connect to one local UDS hosted here and the gateway pools
//! connections to upstream sidecars (security, memory, retrieval,
//! artifact, runtime-kernel) with health-aware load balancing,
//! circuit breakers, and per-workspace fairness. The proto contract
//! lives at `proto/rpc_gateway/v1/rpc_gateway.proto` and the design
//! rationale is in
//! `docs/architecture/production-deployment-roadmap.md` (P0-3, P2-2,
//! P2-3).
//!
//! Scaffold binary; real implementation lands in subsequent sessions.

use std::process::ExitCode;

fn main() -> ExitCode {
    eprintln!(
        "koda-rpc-gateway is a Phase 1D scaffold. \
         The full service implementation has not landed yet — see \
         docs/architecture/production-deployment-roadmap.md (P0-3, P2-2, \
         P2-3) and proto/rpc_gateway/v1/rpc_gateway.proto for the \
         planned contract."
    );
    ExitCode::from(0)
}
