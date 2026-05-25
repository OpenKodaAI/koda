//! koda-bot-gateway binary entrypoint.
//!
//! Boots the tonic server, attaches a Postgres-backed store and a real
//! HTTP Telegram client, and resumes polling for every bot already
//! registered in ``cp_bot_gateway_tokens``. Stops gracefully on SIGINT
//! or SIGTERM.

use std::sync::Arc;

use anyhow::Context;
use koda_bot_gateway::store::{InMemoryStore, PostgresStore, Store};
use koda_bot_gateway::{BotGatewayServer, Config, HttpTelegramApi};
use koda_observability::init_tracing;
use koda_proto::bot_gateway::v1::bot_gateway_service_server::BotGatewayServiceServer;
use tokio::signal;
use tonic::transport::Server;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    init_tracing("koda-bot-gateway");
    let config = Config::from_env();
    let api = Arc::new(HttpTelegramApi::new(config.telegram_base_url.clone()));

    if config.postgres_dsn.is_empty() {
        tracing::warn!("KNOWLEDGE_V2_POSTGRES_DSN empty — running with in-memory store");
        run_with_store::<InMemoryStore>(Arc::new(InMemoryStore::new()), api, config).await
    } else {
        let store = Arc::new(
            PostgresStore::connect(&config.postgres_dsn, &config.postgres_schema)
                .await
                .context("connect bot-gateway Postgres store")?,
        );
        run_with_store::<PostgresStore>(store, api, config).await
    }
}

async fn run_with_store<S: Store>(
    store: Arc<S>,
    api: Arc<HttpTelegramApi>,
    config: Config,
) -> anyhow::Result<()> {
    let server = BotGatewayServer::new(
        store,
        api,
        config.poll_timeout,
        config.poll_initial_backoff,
        config.poll_batch_limit,
    );
    server
        .bootstrap_existing_bots()
        .await
        .context("bootstrap pollers from store")?;

    let addr = config.bind.parse().context("invalid BOT_GATEWAY_BIND")?;
    tracing::info!(bind = %config.bind, "koda_bot_gateway_listening");
    Server::builder()
        .add_service(BotGatewayServiceServer::new(server))
        .serve_with_shutdown(addr, shutdown_signal())
        .await
        .context("tonic server")?;
    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        let _ = signal::ctrl_c().await;
    };
    #[cfg(unix)]
    let term = async {
        let mut sig = signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("install SIGTERM handler");
        sig.recv().await;
    };
    #[cfg(not(unix))]
    let term = std::future::pending::<()>();
    tokio::select! {
        _ = ctrl_c => {},
        _ = term => {},
    }
    tracing::info!("koda_bot_gateway_shutdown_signal_received");
}
