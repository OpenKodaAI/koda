//! koda-policy-engine — quotas, rate limits, and spend caps per workspace.
//!
//! Phase 1C of the production roadmap. Sits on the message-ingest hot
//! path: every queued user message hits [`PolicyEngineServer::check_ingest`]
//! before being enqueued; every billed LLM call hits `record_spend`;
//! every concurrent agent slot is acquired/released here. Decisions are
//! sub-millisecond — the implementation keeps state in sharded
//! in-memory data structures and flushes mutations to Postgres so a
//! restart preserves accumulated spend without losing fairness.
//!
//! See `proto/policy_engine/v1/policy_engine.proto` for the wire
//! contract and `docs/architecture/production-deployment-roadmap.md`
//! (P2-7, P2-8) for the design rationale.

pub mod limiter;
pub mod server;
pub mod slots;
pub mod spend;
pub mod store;

pub use server::PolicyEngineServer;
pub use store::{InMemoryStore, Policy, PolicyStore};
