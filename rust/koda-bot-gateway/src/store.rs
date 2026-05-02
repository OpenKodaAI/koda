//! Persistence layer for the bot-gateway.
//!
//! Two implementations behind one trait so the service is testable
//! without a live Postgres:
//! - `PostgresStore` — production (writes go through ``cp_bot_gateway_tokens``
//!   and ``cp_telegram_pending_updates`` from migration 021).
//! - `InMemoryStore` — used by the integration tests; same semantics.
//!
//! Durability contract: the poller persists every update through
//! ``enqueue_updates`` BEFORE advancing its offset (``set_offset``) so
//! a gateway crash never loses a message. Subscribers consume via
//! ``replay_pending`` then via the live broadcast channel. Workers
//! call ``acknowledge_update`` after processing; that DELETE is the
//! ack that prevents replay on the next reconnect.

use std::collections::BTreeMap;
use std::sync::Arc;

use async_trait::async_trait;
use serde_json::Value;
use thiserror::Error;
use tokio::sync::Mutex;

#[derive(Debug, Error)]
pub enum StoreError {
    #[error("postgres error: {0}")]
    Postgres(String),
    #[error("not found")]
    NotFound,
}

#[derive(Debug, Clone)]
pub struct BotEntry {
    pub agent_id: String,
    pub bot_token: String,
    pub last_offset: i64,
}

#[derive(Debug, Clone)]
pub struct PendingUpdate {
    pub agent_id: String,
    pub update_id: i64,
    pub payload: Value,
}

#[async_trait]
pub trait Store: Send + Sync + 'static {
    async fn upsert_bot(&self, agent_id: &str, bot_token: &str) -> Result<(), StoreError>;
    async fn delete_bot(&self, agent_id: &str) -> Result<bool, StoreError>;
    async fn list_bots(&self) -> Result<Vec<BotEntry>, StoreError>;

    /// Persist updates and atomically advance the offset.
    /// Caller passes ``next_offset`` from the Telegram response so the
    /// store does not need to reason about Telegram semantics.
    async fn enqueue_updates(
        &self,
        agent_id: &str,
        updates: &[PendingUpdate],
        next_offset: i64,
    ) -> Result<(), StoreError>;

    /// All unacknowledged updates for ``agent_id`` ordered by queued_at,id.
    async fn replay_pending(&self, agent_id: &str) -> Result<Vec<PendingUpdate>, StoreError>;

    /// Delete the pending row for the given ``(agent_id, update_id)``
    /// pair. Returns true when a row was deleted, false when the row
    /// was already gone (idempotent worker re-acks).
    async fn acknowledge_update(&self, agent_id: &str, update_id: i64) -> Result<bool, StoreError>;

    /// Status snapshot used by GetGatewayStatus.
    async fn snapshot(&self) -> Result<Vec<BotEntry>, StoreError>;
}

// ---------------------------------------------------------------------------
// In-memory implementation (used by integration tests + when DSN empty)
// ---------------------------------------------------------------------------

#[derive(Default)]
pub struct InMemoryStore {
    inner: Arc<Mutex<MemState>>,
}

#[derive(Default)]
struct MemState {
    bots: BTreeMap<String, (String, i64)>,
    pending: BTreeMap<(String, i64), Value>,
}

impl InMemoryStore {
    pub fn new() -> Self {
        Self::default()
    }
}

#[async_trait]
impl Store for InMemoryStore {
    async fn upsert_bot(&self, agent_id: &str, bot_token: &str) -> Result<(), StoreError> {
        let mut state = self.inner.lock().await;
        let entry = state
            .bots
            .entry(agent_id.to_string())
            .or_insert_with(|| (bot_token.to_string(), 0));
        entry.0 = bot_token.to_string();
        Ok(())
    }

    async fn delete_bot(&self, agent_id: &str) -> Result<bool, StoreError> {
        let mut state = self.inner.lock().await;
        let removed_bot = state.bots.remove(agent_id).is_some();
        let mut to_drop: Vec<(String, i64)> = Vec::new();
        for key in state.pending.keys() {
            if key.0 == agent_id {
                to_drop.push(key.clone());
            }
        }
        for key in to_drop {
            state.pending.remove(&key);
        }
        Ok(removed_bot)
    }

    async fn list_bots(&self) -> Result<Vec<BotEntry>, StoreError> {
        let state = self.inner.lock().await;
        Ok(state
            .bots
            .iter()
            .map(|(agent_id, (bot_token, offset))| BotEntry {
                agent_id: agent_id.clone(),
                bot_token: bot_token.clone(),
                last_offset: *offset,
            })
            .collect())
    }

    async fn enqueue_updates(
        &self,
        agent_id: &str,
        updates: &[PendingUpdate],
        next_offset: i64,
    ) -> Result<(), StoreError> {
        let mut state = self.inner.lock().await;
        for update in updates {
            // Idempotent insert: if the row is already present, leave it
            // alone (matches the Postgres ON CONFLICT DO NOTHING path).
            state
                .pending
                .entry((agent_id.to_string(), update.update_id))
                .or_insert_with(|| update.payload.clone());
        }
        if let Some(slot) = state.bots.get_mut(agent_id) {
            slot.1 = next_offset;
        }
        Ok(())
    }

    async fn replay_pending(&self, agent_id: &str) -> Result<Vec<PendingUpdate>, StoreError> {
        let state = self.inner.lock().await;
        let mut rows = state
            .pending
            .iter()
            .filter(|((a, _), _)| a == agent_id)
            .map(|((a, id), payload)| PendingUpdate {
                agent_id: a.clone(),
                update_id: *id,
                payload: payload.clone(),
            })
            .collect::<Vec<_>>();
        rows.sort_by_key(|u| u.update_id);
        Ok(rows)
    }

    async fn acknowledge_update(&self, agent_id: &str, update_id: i64) -> Result<bool, StoreError> {
        let mut state = self.inner.lock().await;
        Ok(state
            .pending
            .remove(&(agent_id.to_string(), update_id))
            .is_some())
    }

    async fn snapshot(&self) -> Result<Vec<BotEntry>, StoreError> {
        self.list_bots().await
    }
}

// ---------------------------------------------------------------------------
// Postgres implementation
// ---------------------------------------------------------------------------

pub struct PostgresStore {
    client: Arc<Mutex<tokio_postgres::Client>>,
    schema: String,
}

impl PostgresStore {
    pub async fn connect(dsn: &str, schema: &str) -> anyhow::Result<Self> {
        let (client, connection) = tokio_postgres::connect(dsn, tokio_postgres::NoTls).await?;
        tokio::spawn(async move {
            if let Err(e) = connection.await {
                tracing::error!(error = %e, "bot_gateway_postgres_connection_lost");
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
impl Store for PostgresStore {
    async fn upsert_bot(&self, agent_id: &str, bot_token: &str) -> Result<(), StoreError> {
        let client = self.client.lock().await;
        client
            .execute(
                &self.q(r#"INSERT INTO "{schema}"."cp_bot_gateway_tokens"
                       (agent_id, bot_token, registered_at, updated_at)
                       VALUES ($1, $2, NOW(), NOW())
                       ON CONFLICT (agent_id) DO UPDATE
                       SET bot_token = EXCLUDED.bot_token, updated_at = NOW()"#),
                &[&agent_id, &bot_token],
            )
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        Ok(())
    }

    async fn delete_bot(&self, agent_id: &str) -> Result<bool, StoreError> {
        let client = self.client.lock().await;
        let n = client
            .execute(
                &self.q(r#"DELETE FROM "{schema}"."cp_bot_gateway_tokens" WHERE agent_id = $1"#),
                &[&agent_id],
            )
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        client
            .execute(
                &self.q(
                    r#"DELETE FROM "{schema}"."cp_telegram_pending_updates" WHERE agent_id = $1"#,
                ),
                &[&agent_id],
            )
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        Ok(n > 0)
    }

    async fn list_bots(&self) -> Result<Vec<BotEntry>, StoreError> {
        let client = self.client.lock().await;
        let rows = client
            .query(
                &self.q(
                    r#"SELECT t.agent_id, t.bot_token, COALESCE(o.last_update_id, 0) AS last_offset
                       FROM "{schema}"."cp_bot_gateway_tokens" t
                       LEFT JOIN "{schema}"."cp_telegram_offsets" o ON o.agent_id = t.agent_id"#,
                ),
                &[],
            )
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        Ok(rows
            .into_iter()
            .map(|row| BotEntry {
                agent_id: row.get(0),
                bot_token: row.get(1),
                last_offset: row.get::<_, i64>(2),
            })
            .collect())
    }

    async fn enqueue_updates(
        &self,
        agent_id: &str,
        updates: &[PendingUpdate],
        next_offset: i64,
    ) -> Result<(), StoreError> {
        let mut client = self.client.lock().await;
        let tx = client
            .transaction()
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        for update in updates {
            tx.execute(
                &self.q(r#"INSERT INTO "{schema}"."cp_telegram_pending_updates"
                       (agent_id, update_id, payload_json, queued_at)
                       VALUES ($1, $2, $3::jsonb, NOW())
                       ON CONFLICT (agent_id, update_id) DO NOTHING"#),
                &[&agent_id, &update.update_id, &update.payload.to_string()],
            )
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        }
        tx.execute(
            &self.q(
                r#"INSERT INTO "{schema}"."cp_telegram_offsets" (agent_id, last_update_id, updated_at)
                   VALUES ($1, $2, NOW())
                   ON CONFLICT (agent_id) DO UPDATE
                   SET last_update_id = GREATEST("{schema}"."cp_telegram_offsets".last_update_id, EXCLUDED.last_update_id),
                       updated_at = EXCLUDED.updated_at"#,
            ),
            &[&agent_id, &next_offset],
        )
        .await
        .map_err(|e| StoreError::Postgres(e.to_string()))?;
        tx.commit()
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        Ok(())
    }

    async fn replay_pending(&self, agent_id: &str) -> Result<Vec<PendingUpdate>, StoreError> {
        let client = self.client.lock().await;
        let rows = client
            .query(
                &self.q(r#"SELECT update_id, payload_json::text
                       FROM "{schema}"."cp_telegram_pending_updates"
                       WHERE agent_id = $1
                       ORDER BY queued_at ASC, id ASC"#),
                &[&agent_id],
            )
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        let mut out = Vec::with_capacity(rows.len());
        for row in rows {
            let update_id: i64 = row.get(0);
            let payload_text: String = row.get(1);
            let payload: Value = serde_json::from_str(&payload_text)
                .map_err(|e| StoreError::Postgres(format!("payload decode: {e}")))?;
            out.push(PendingUpdate {
                agent_id: agent_id.to_string(),
                update_id,
                payload,
            });
        }
        Ok(out)
    }

    async fn acknowledge_update(&self, agent_id: &str, update_id: i64) -> Result<bool, StoreError> {
        let client = self.client.lock().await;
        let n = client
            .execute(
                &self.q(r#"DELETE FROM "{schema}"."cp_telegram_pending_updates"
                       WHERE agent_id = $1 AND update_id = $2"#),
                &[&agent_id, &update_id],
            )
            .await
            .map_err(|e| StoreError::Postgres(e.to_string()))?;
        Ok(n > 0)
    }

    async fn snapshot(&self) -> Result<Vec<BotEntry>, StoreError> {
        self.list_bots().await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn upd(agent: &str, id: i64) -> PendingUpdate {
        PendingUpdate {
            agent_id: agent.to_string(),
            update_id: id,
            payload: json!({"update_id": id}),
        }
    }

    #[tokio::test]
    async fn in_memory_store_full_lifecycle() {
        let store = InMemoryStore::new();
        store.upsert_bot("AGENT_A", "tok-a").await.unwrap();
        store.upsert_bot("AGENT_B", "tok-b").await.unwrap();

        store
            .enqueue_updates("AGENT_A", &[upd("AGENT_A", 5), upd("AGENT_A", 6)], 7)
            .await
            .unwrap();

        let pending = store.replay_pending("AGENT_A").await.unwrap();
        assert_eq!(pending.len(), 2);
        assert_eq!(pending[0].update_id, 5);
        assert_eq!(pending[1].update_id, 6);

        // Idempotent re-enqueue (same pair) does not duplicate.
        store
            .enqueue_updates("AGENT_A", &[upd("AGENT_A", 5)], 7)
            .await
            .unwrap();
        let pending2 = store.replay_pending("AGENT_A").await.unwrap();
        assert_eq!(pending2.len(), 2);

        let acked = store.acknowledge_update("AGENT_A", 5).await.unwrap();
        assert!(acked);
        let acked_again = store.acknowledge_update("AGENT_A", 5).await.unwrap();
        assert!(!acked_again, "second ack must be idempotent");

        let pending3 = store.replay_pending("AGENT_A").await.unwrap();
        assert_eq!(pending3.len(), 1);
        assert_eq!(pending3[0].update_id, 6);

        // Delete bot wipes its queue.
        let removed = store.delete_bot("AGENT_A").await.unwrap();
        assert!(removed);
        assert!(store.replay_pending("AGENT_A").await.unwrap().is_empty());

        let bots = store.list_bots().await.unwrap();
        assert_eq!(bots.len(), 1);
        assert_eq!(bots[0].agent_id, "AGENT_B");
    }
}
