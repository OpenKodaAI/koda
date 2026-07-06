//! Env-driven configuration for the bot-gateway binary.

use std::env;
use std::time::Duration;

#[derive(Debug, Clone)]
pub struct Config {
    /// Postgres DSN. Same connection string the Python control plane
    /// uses (KNOWLEDGE_V2_POSTGRES_DSN). Empty disables persistence —
    /// only useful for the mock-backed integration tests.
    pub postgres_dsn: String,
    /// Schema where ``cp_bot_gateway_tokens`` and
    /// ``cp_telegram_pending_updates`` were created by migration 021.
    pub postgres_schema: String,
    /// Address the tonic server listens on. Override with
    /// BOT_GATEWAY_BIND in compose deploys.
    pub bind: String,
    /// Telegram API base URL. Overridable so integration tests can
    /// point at a stubbed HTTP server.
    pub telegram_base_url: String,
    /// long_poll_timeout_seconds passed to getUpdates. Telegram caps at
    /// 50; we default to 25 to play nice with intermediate proxies.
    pub poll_timeout: Duration,
    /// Backoff between failed getUpdates calls. Starts here and doubles
    /// up to poll_timeout * 4. Resets on success.
    pub poll_initial_backoff: Duration,
    /// Maximum updates fetched per poll. Telegram caps at 100.
    pub poll_batch_limit: u32,
}

impl Config {
    pub fn from_env() -> Self {
        Self {
            postgres_dsn: env_or_default("KNOWLEDGE_V2_POSTGRES_DSN", ""),
            postgres_schema: env_or_default("KNOWLEDGE_V2_POSTGRES_SCHEMA", "knowledge_v2"),
            bind: env_or_default("BOT_GATEWAY_BIND", "0.0.0.0:50066"),
            telegram_base_url: env_or_default(
                "BOT_GATEWAY_TELEGRAM_BASE_URL",
                "https://api.telegram.org",
            ),
            poll_timeout: env_duration_seconds("BOT_GATEWAY_POLL_TIMEOUT_SECONDS", 25),
            poll_initial_backoff: env_duration_seconds(
                "BOT_GATEWAY_POLL_INITIAL_BACKOFF_SECONDS",
                1,
            ),
            poll_batch_limit: env_u32("BOT_GATEWAY_POLL_BATCH_LIMIT", 100),
        }
    }
}

fn env_or_default(key: &str, default: &str) -> String {
    env::var(key)
        .ok()
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| default.to_string())
}

fn env_duration_seconds(key: &str, default: u64) -> Duration {
    let secs = env::var(key)
        .ok()
        .and_then(|v| v.parse::<u64>().ok())
        .filter(|v| *v > 0)
        .unwrap_or(default);
    Duration::from_secs(secs)
}

fn env_u32(key: &str, default: u32) -> u32 {
    env::var(key)
        .ok()
        .and_then(|v| v.parse::<u32>().ok())
        .filter(|v| *v > 0)
        .unwrap_or(default)
}
