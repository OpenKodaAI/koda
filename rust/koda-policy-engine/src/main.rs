//! koda-policy-engine binary entrypoint (Phase 1C).

use std::env;
use std::sync::Arc;

use anyhow::Context;
use koda_observability::init_tracing;
use koda_policy_engine::store::{InMemoryStore, PolicyStore, PostgresPolicyStore};
use koda_policy_engine::PolicyEngineServer;
use koda_proto::policy_engine::v1::policy_engine_service_server::PolicyEngineServiceServer;
use tokio::signal;
use tonic::transport::Server;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    init_tracing("koda-policy-engine");
    let bind: std::net::SocketAddr = env::var("POLICY_ENGINE_BIND")
        .unwrap_or_else(|_| "0.0.0.0:50067".to_string())
        .parse()
        .context("invalid POLICY_ENGINE_BIND")?;
    let dsn = env::var("KNOWLEDGE_V2_POSTGRES_DSN").unwrap_or_default();
    let schema =
        env::var("KNOWLEDGE_V2_POSTGRES_SCHEMA").unwrap_or_else(|_| "knowledge_v2".to_string());

    if dsn.is_empty() {
        tracing::warn!("KNOWLEDGE_V2_POSTGRES_DSN empty — running with in-memory store");
        run_with_store(Arc::new(InMemoryStore::new()), bind).await
    } else {
        let store = Arc::new(
            PostgresPolicyStore::connect(&dsn, &schema)
                .await
                .context("connect policy-engine Postgres store")?,
        );
        run_with_store(store, bind).await
    }
}

async fn run_with_store<S: PolicyStore>(
    store: Arc<S>,
    bind: std::net::SocketAddr,
) -> anyhow::Result<()> {
    let server = PolicyEngineServer::new(store);
    tracing::info!(bind = %bind, "koda_policy_engine_listening");
    Server::builder()
        .add_service(PolicyEngineServiceServer::new(server))
        .serve_with_shutdown(bind, shutdown_signal())
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
    tracing::info!("koda_policy_engine_shutdown_signal_received");
}
