//! Per-bot Telegram polling task.
//!
//! Spawn one of these per registered bot. Each task:
//! 1. Calls Telegram getUpdates with the agent's last known offset.
//! 2. Persists every returned Update to the store.
//! 3. Advances the offset (via the same store transaction) so a crash
//!    after a successful poll never replays already-persisted updates
//!    nor loses unpersisted ones.
//! 4. Broadcasts the new updates to subscribers via [`tokio::sync::broadcast`].
//!
//! Stop semantics: the task returns when its `cancel` watch channel
//! transitions to true (typically because the bot was unregistered or
//! the gateway is shutting down).

use std::sync::Arc;
use std::time::Duration;

use tokio::sync::{broadcast, watch};

use crate::store::{PendingUpdate, Store};
use crate::telegram::{TelegramApi, TelegramError};

/// Updates the poller pushes onto the broadcast channel. Subscribers
/// re-emit these on the gRPC stream after replaying the durable queue.
#[derive(Debug, Clone)]
pub struct LiveUpdate {
    pub agent_id: String,
    pub update_id: i64,
    pub payload_json: String,
}

#[derive(Clone)]
pub struct Poller<S: Store, A: TelegramApi> {
    pub store: Arc<S>,
    pub api: Arc<A>,
    pub broadcaster: broadcast::Sender<LiveUpdate>,
    pub poll_timeout: Duration,
    pub poll_initial_backoff: Duration,
    pub poll_batch_limit: u32,
}

impl<S: Store, A: TelegramApi> Poller<S, A> {
    pub fn new(
        store: Arc<S>,
        api: Arc<A>,
        broadcaster: broadcast::Sender<LiveUpdate>,
        poll_timeout: Duration,
        poll_initial_backoff: Duration,
        poll_batch_limit: u32,
    ) -> Self {
        Self {
            store,
            api,
            broadcaster,
            poll_timeout,
            poll_initial_backoff,
            poll_batch_limit,
        }
    }

    /// Run the poll loop until ``cancel`` flips to true. The
    /// ``starting_offset`` is the agent's last known offset from the
    /// store (replays unacked updates on first iteration).
    pub async fn run(
        self,
        agent_id: String,
        bot_token: String,
        starting_offset: i64,
        mut cancel: watch::Receiver<bool>,
    ) {
        let mut offset = starting_offset;
        let mut backoff = self.poll_initial_backoff;
        let max_backoff = self.poll_timeout * 4;
        loop {
            if *cancel.borrow() {
                tracing::info!(agent_id = %agent_id, "bot_gateway_poller_stopped");
                return;
            }
            tokio::select! {
                _ = cancel.changed() => {
                    if *cancel.borrow() {
                        tracing::info!(agent_id = %agent_id, "bot_gateway_poller_stopped");
                        return;
                    }
                }
                result = self.api.get_updates(
                    &bot_token,
                    offset,
                    self.poll_timeout,
                    self.poll_batch_limit,
                ) => {
                    match result {
                        Ok(poll) => {
                            backoff = self.poll_initial_backoff;
                            if poll.updates.is_empty() {
                                continue;
                            }
                            let pending: Vec<PendingUpdate> = poll
                                .updates
                                .iter()
                                .map(|u| PendingUpdate {
                                    agent_id: agent_id.clone(),
                                    update_id: u.update_id,
                                    payload: u.payload.clone(),
                                })
                                .collect();
                            if let Err(err) = self
                                .store
                                .enqueue_updates(&agent_id, &pending, poll.next_offset)
                                .await
                            {
                                tracing::error!(
                                    agent_id = %agent_id,
                                    error = %err,
                                    "bot_gateway_persist_failed"
                                );
                                tokio::time::sleep(backoff).await;
                                continue;
                            }
                            offset = poll.next_offset;
                            for update in pending {
                                let _ = self.broadcaster.send(LiveUpdate {
                                    agent_id: update.agent_id.clone(),
                                    update_id: update.update_id,
                                    payload_json: update.payload.to_string(),
                                });
                            }
                        }
                        Err(TelegramError::ApiError(desc)) => {
                            tracing::warn!(
                                agent_id = %agent_id,
                                error = %desc,
                                "bot_gateway_telegram_api_error"
                            );
                            tokio::time::sleep(backoff).await;
                            backoff = (backoff * 2).min(max_backoff);
                        }
                        Err(err) => {
                            tracing::warn!(
                                agent_id = %agent_id,
                                error = %err,
                                "bot_gateway_poll_failed"
                            );
                            tokio::time::sleep(backoff).await;
                            backoff = (backoff * 2).min(max_backoff);
                        }
                    }
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::store::InMemoryStore;
    use crate::telegram::{MockTelegramApi, TelegramUpdate};
    use serde_json::json;

    fn live_update(id: i64) -> TelegramUpdate {
        TelegramUpdate {
            update_id: id,
            payload: json!({"update_id": id, "message": {"text": format!("msg-{id}")}}),
        }
    }

    #[tokio::test]
    async fn poller_persists_then_broadcasts() {
        let store = Arc::new(InMemoryStore::new());
        store.upsert_bot("AGENT_A", "tok-a").await.unwrap();
        let api = Arc::new(MockTelegramApi::new());
        api.push_batch("tok-a", vec![live_update(1), live_update(2)])
            .await;

        let (tx, mut rx) = broadcast::channel(16);
        let (cancel_tx, cancel_rx) = watch::channel(false);
        let poller = Poller::new(
            store.clone(),
            api.clone(),
            tx,
            Duration::from_millis(10),
            Duration::from_millis(5),
            100,
        );
        let handle =
            tokio::spawn(poller.run("AGENT_A".to_string(), "tok-a".to_string(), 0, cancel_rx));

        let first = rx.recv().await.unwrap();
        assert_eq!(first.update_id, 1);
        let second = rx.recv().await.unwrap();
        assert_eq!(second.update_id, 2);

        // Persistence happened before broadcast — both rows are in the store.
        let pending = store.replay_pending("AGENT_A").await.unwrap();
        assert_eq!(pending.len(), 2);

        cancel_tx.send(true).unwrap();
        handle.await.unwrap();
    }
}
