//! koda-bot-gateway — Telegram fan-in service (Phase 1B).
//!
//! Public surface:
//! - [`config::Config`] — env-driven configuration.
//! - [`store::Store`] — abstract registry/queue (Postgres-backed in prod,
//!   in-memory for tests).
//! - [`telegram::TelegramApi`] — abstract Telegram getUpdates client
//!   (real reqwest in prod, mock in tests).
//! - [`poller::Poller`] — long-running polling task per registered bot.
//! - [`server::BotGatewayServer`] — tonic service implementation.
//!
//! See `proto/bot_gateway/v1/bot_gateway.proto` for the wire contract
//! and `docs/architecture/production-deployment-roadmap.md` (P2-6) for
//! the design rationale.

pub mod config;
pub mod poller;
pub mod server;
pub mod store;
pub mod telegram;

pub use config::Config;
pub use server::BotGatewayServer;
pub use store::{InMemoryStore, PendingUpdate, Store};
pub use telegram::{HttpTelegramApi, MockTelegramApi, TelegramApi, TelegramUpdate};
