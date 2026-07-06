//! Persistence layer for the policy engine.
//!
//! Mirrors the bot-gateway pattern: in-memory implementation for tests
//! and a Postgres-backed implementation that writes through to the
//! tables created by migration 022. Operations are intentionally
//! idempotent so a transient DB blip does not corrupt the workspace
//! policy or duplicate spend rows.

use std::collections::BTreeMap;
use std::sync::Arc;

use async_trait::async_trait;
use thiserror::Error;
use tokio::sync::Mutex;

#[derive(Debug, Error)]
pub enum StoreError {
    #[error("postgres error: {0}")]
    Postgres(String),
}

#[derive(Debug, Clone, PartialEq)]
pub struct Policy {
    pub workspace_id: String,
    pub max_concurrent_agents: i32,
    pub max_messages_per_minute: i32,
    pub monthly_llm_spend_usd_cap: f64,
    pub spend_warning_fraction: f64,
    pub enabled: bool,
}

impl Policy {
    pub fn unlimited(workspace_id: impl Into<String>) -> Self {
        Self {
            workspace_id: workspace_id.into(),
            max_concurrent_agents: 0,
            max_messages_per_minute: 0,
            monthly_llm_spend_usd_cap: 0.0,
            spend_warning_fraction: 0.8,
            enabled: false,
        }
    }
}

#[async_trait]
pub trait PolicyStore: Send + Sync + 'static {
    async fn get_policy(&self, workspace_id: &str) -> Result<Option<Policy>, StoreError>;
    async fn upsert_policy(&self, policy: &Policy) -> Result<(), StoreError>;
    async fn record_spend(
        &self,
        workspace_id: &str,
        agent_id: &str,
        cost_usd: f64,
        provider: &str,
        model: &str,
    ) -> Result<f64, StoreError>;
    async fn current_window_spend(&self, workspace_id: &str) -> Result<f64, StoreError>;
}

// ---------------------------------------------------------------------------
// In-memory implementation
// ---------------------------------------------------------------------------

#[derive(Default)]
pub struct InMemoryStore {
    inner: Arc<Mutex<MemState>>,
}

#[derive(Default)]
struct MemState {
    policies: BTreeMap<String, Policy>,
    spend: BTreeMap<String, f64>,
}

impl InMemoryStore {
    pub fn new() -> Self {
        Self::default()
    }
}

#[async_trait]
impl PolicyStore for InMemoryStore {
    async fn get_policy(&self, workspace_id: &str) -> Result<Option<Policy>, StoreError> {
        Ok(self.inner.lock().await.policies.get(workspace_id).cloned())
    }

    async fn upsert_policy(&self, policy: &Policy) -> Result<(), StoreError> {
        self.inner
            .lock()
            .await
            .policies
            .insert(policy.workspace_id.clone(), policy.clone());
        Ok(())
    }

    async fn record_spend(
        &self,
        workspace_id: &str,
        _agent_id: &str,
        cost_usd: f64,
        _provider: &str,
        _model: &str,
    ) -> Result<f64, StoreError> {
        let mut state = self.inner.lock().await;
        let current = state.spend.entry(workspace_id.to_string()).or_insert(0.0);
        *current += cost_usd;
        Ok(*current)
    }

    async fn current_window_spend(&self, workspace_id: &str) -> Result<f64, StoreError> {
        Ok(self
            .inner
            .lock()
            .await
            .spend
            .get(workspace_id)
            .copied()
            .unwrap_or(0.0))
    }
}

// ---------------------------------------------------------------------------
// Postgres implementation
// ---------------------------------------------------------------------------

pub struct PostgresPolicyStore {
    client: Arc<Mutex<tokio_postgres::Client>>,
    schema: String,
}

impl PostgresPolicyStore {
    pub async fn connect(dsn: &str, schema: &str) -> anyhow::Result<Self> {
        let (client, connection) = tokio_postgres::connect(dsn, tokio_postgres::NoTls).await?;
        tokio::spawn(async move {
            if let Err(e) = connection.await {
                tracing::error!(error = %e, "policy_engine_postgres_connection_lost");
            }
        });
        Ok(Self {
            client: Arc::new(Mutex::new(client)),
            schema: schema.to_string(),
        })
    }

    fn q(&self, sql: &str) -> String {
        sql.replace("{schema}", &self.schema)
    }
}

#[async_trait]
impl PolicyStore for PostgresPolicyStore {
    async fn get_policy(&self, workspace_id: &str) -> Result<Option<Policy>, StoreError> {
        let client = self.client.lock().await;
        let row = client
            .query_opt(
                &self.q(
                    r#"SELECT workspace_id, max_concurrent_agents, max_messages_per_minute,
                              monthly_llm_spend_usd_cap, spend_warning_fraction, enabled
                       FROM "{schema}"."cp_policy" WHERE workspace_id = $1"#,
                ),
                &[&workspace_id],
            )
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        Ok(row.map(|r| Policy {
            workspace_id: r.get(0),
            max_concurrent_agents: r.get(1),
            max_messages_per_minute: r.get(2),
            monthly_llm_spend_usd_cap: r.get(3),
            spend_warning_fraction: r.get(4),
            enabled: r.get(5),
        }))
    }

    async fn upsert_policy(&self, policy: &Policy) -> Result<(), StoreError> {
        let client = self.client.lock().await;
        client
            .execute(
                &self.q(r#"INSERT INTO "{schema}"."cp_policy"
                       (workspace_id, max_concurrent_agents, max_messages_per_minute,
                        monthly_llm_spend_usd_cap, spend_warning_fraction, enabled, updated_at)
                       VALUES ($1, $2, $3, $4, $5, $6, NOW())
                       ON CONFLICT (workspace_id) DO UPDATE SET
                           max_concurrent_agents = EXCLUDED.max_concurrent_agents,
                           max_messages_per_minute = EXCLUDED.max_messages_per_minute,
                           monthly_llm_spend_usd_cap = EXCLUDED.monthly_llm_spend_usd_cap,
                           spend_warning_fraction = EXCLUDED.spend_warning_fraction,
                           enabled = EXCLUDED.enabled,
                           updated_at = NOW()"#),
                &[
                    &policy.workspace_id,
                    &policy.max_concurrent_agents,
                    &policy.max_messages_per_minute,
                    &policy.monthly_llm_spend_usd_cap,
                    &policy.spend_warning_fraction,
                    &policy.enabled,
                ],
            )
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        Ok(())
    }

    async fn record_spend(
        &self,
        workspace_id: &str,
        agent_id: &str,
        cost_usd: f64,
        provider: &str,
        model: &str,
    ) -> Result<f64, StoreError> {
        let mut client = self.client.lock().await;
        let tx = client
            .transaction()
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        tx.execute(
            &self.q(r#"INSERT INTO "{schema}"."cp_policy_spend_ledger"
                   (workspace_id, agent_id, cost_usd, provider, model, recorded_at)
                   VALUES ($1, $2, $3, $4, $5, NOW())"#),
            &[&workspace_id, &agent_id, &cost_usd, &provider, &model],
        )
        .await
        .map_err(|e| StoreError::Postgres(e.to_string()))?;
        let row = tx
            .query_one(
                &self.q(
                    r#"INSERT INTO "{schema}"."cp_policy_spend_window"
                       (workspace_id, window_start, spent_usd, updated_at)
                       VALUES ($1, date_trunc('month', NOW()), $2, NOW())
                       ON CONFLICT (workspace_id) DO UPDATE SET
                           spent_usd = CASE
                               WHEN "{schema}"."cp_policy_spend_window".window_start < date_trunc('month', NOW())
                               THEN EXCLUDED.spent_usd
                               ELSE "{schema}"."cp_policy_spend_window".spent_usd + EXCLUDED.spent_usd
                           END,
                           window_start = CASE
                               WHEN "{schema}"."cp_policy_spend_window".window_start < date_trunc('month', NOW())
                               THEN date_trunc('month', NOW())
                               ELSE "{schema}"."cp_policy_spend_window".window_start
                           END,
                           updated_at = NOW()
                       RETURNING spent_usd"#,
                ),
                &[&workspace_id, &cost_usd],
            )
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        let total: f64 = row.get(0);
        tx.commit()
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        Ok(total)
    }

    async fn current_window_spend(&self, workspace_id: &str) -> Result<f64, StoreError> {
        let client = self.client.lock().await;
        let row = client
            .query_opt(
                &self.q(r#"SELECT spent_usd FROM "{schema}"."cp_policy_spend_window"
                       WHERE workspace_id = $1
                         AND window_start = date_trunc('month', NOW())"#),
                &[&workspace_id],
            )
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        Ok(row.map(|r| r.get::<_, f64>(0)).unwrap_or(0.0))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn in_memory_policy_lifecycle() {
        let store = InMemoryStore::new();
        let p = Policy {
            workspace_id: "ws".into(),
            max_concurrent_agents: 5,
            max_messages_per_minute: 30,
            monthly_llm_spend_usd_cap: 100.0,
            spend_warning_fraction: 0.8,
            enabled: true,
        };
        store.upsert_policy(&p).await.unwrap();
        let fetched = store.get_policy("ws").await.unwrap().unwrap();
        assert_eq!(fetched, p);
        assert!(store.get_policy("nope").await.unwrap().is_none());
    }

    #[tokio::test]
    async fn in_memory_spend_accumulates_per_workspace() {
        let store = InMemoryStore::new();
        let total = store
            .record_spend("ws", "AGENT_A", 1.5, "openai", "gpt")
            .await
            .unwrap();
        assert!((total - 1.5).abs() < 1e-9);
        let total2 = store
            .record_spend("ws", "AGENT_A", 2.5, "openai", "gpt")
            .await
            .unwrap();
        assert!((total2 - 4.0).abs() < 1e-9);
        let other = store
            .record_spend("ws_other", "AGENT_B", 7.0, "openai", "gpt")
            .await
            .unwrap();
        assert!((other - 7.0).abs() < 1e-9);
        assert!((store.current_window_spend("ws").await.unwrap() - 4.0).abs() < 1e-9);
    }
}
