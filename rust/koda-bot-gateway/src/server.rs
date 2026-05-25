//! Tonic implementation of `BotGatewayService`.
//!
//! Owns the per-agent broadcast channel registry plus the per-agent
//! cancellation watch channels used by the pollers. Wiring goal: a
//! Worker calling `SubscribeUpdates` first receives every persisted
//! pending update for its agent (replay), then transitions to the
//! live broadcast for new updates from the poller. Worker call to
//! `AcknowledgeUpdate` deletes the corresponding row.

use std::collections::HashMap;
use std::pin::Pin;
use std::sync::Arc;
use std::time::Duration;

use async_stream::try_stream;
use futures::Stream;
use tokio::sync::{broadcast, watch, RwLock};
use tonic::{Request, Response, Status};

use koda_proto::bot_gateway::v1::bot_gateway_service_server::BotGatewayService as BotGatewayServiceTrait;
use koda_proto::bot_gateway::v1::{
    AcknowledgeUpdateRequest, AcknowledgeUpdateResponse, BotStatus, GetGatewayStatusRequest,
    GetGatewayStatusResponse, RegisterBotRequest, RegisterBotResponse, SubscribeUpdatesRequest,
    UnregisterBotRequest, UnregisterBotResponse, Update,
};

use crate::poller::{LiveUpdate, Poller};
use crate::store::Store;
use crate::telegram::TelegramApi;

/// Capacity of each per-agent broadcast channel. Keep small — replay
/// is the durable path; broadcast is best-effort live fan-out.
const BROADCAST_CAPACITY: usize = 256;

struct AgentState {
    broadcaster: broadcast::Sender<LiveUpdate>,
    cancel_tx: watch::Sender<bool>,
}

pub struct BotGatewayServer<S: Store, A: TelegramApi> {
    store: Arc<S>,
    api: Arc<A>,
    poll_timeout: Duration,
    poll_initial_backoff: Duration,
    poll_batch_limit: u32,
    state: Arc<RwLock<HashMap<String, AgentState>>>,
}

impl<S: Store, A: TelegramApi> BotGatewayServer<S, A> {
    pub fn new(
        store: Arc<S>,
        api: Arc<A>,
        poll_timeout: Duration,
        poll_initial_backoff: Duration,
        poll_batch_limit: u32,
    ) -> Self {
        Self {
            store,
            api,
            poll_timeout,
            poll_initial_backoff,
            poll_batch_limit,
            state: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Bootstrap a poller for every bot already registered in the store.
    /// Called once at gateway startup so registrations made during a
    /// previous run resume polling without an explicit RegisterBot call.
    pub async fn bootstrap_existing_bots(&self) -> anyhow::Result<()> {
        let bots = self
            .store
            .list_bots()
            .await
            .map_err(|e| anyhow::anyhow!(e.to_string()))?;
        for bot in bots {
            self.start_poller(&bot.agent_id, &bot.bot_token, bot.last_offset)
                .await;
        }
        Ok(())
    }

    async fn start_poller(&self, agent_id: &str, bot_token: &str, starting_offset: i64) {
        let mut state_map = self.state.write().await;
        // Replace any prior poller (token rotation): cancel the old one,
        // drop the broadcast sender, and create fresh channels.
        if let Some(prev) = state_map.remove(agent_id) {
            let _ = prev.cancel_tx.send(true);
        }
        let (broadcaster, _) = broadcast::channel::<LiveUpdate>(BROADCAST_CAPACITY);
        let (cancel_tx, cancel_rx) = watch::channel(false);
        let poller = Poller::new(
            self.store.clone(),
            self.api.clone(),
            broadcaster.clone(),
            self.poll_timeout,
            self.poll_initial_backoff,
            self.poll_batch_limit,
        );
        let agent_id_owned = agent_id.to_string();
        let bot_token_owned = bot_token.to_string();
        tokio::spawn(async move {
            poller
                .run(agent_id_owned, bot_token_owned, starting_offset, cancel_rx)
                .await;
        });
        state_map.insert(
            agent_id.to_string(),
            AgentState {
                broadcaster,
                cancel_tx,
            },
        );
    }

    async fn ensure_subscriber(
        &self,
        agent_id: &str,
    ) -> Result<broadcast::Receiver<LiveUpdate>, Status> {
        let state_map = self.state.read().await;
        let state = state_map.get(agent_id).ok_or_else(|| {
            Status::failed_precondition(format!(
                "no bot registered for agent_id={agent_id}; call RegisterBot first"
            ))
        })?;
        Ok(state.broadcaster.subscribe())
    }
}

type SubscribeStream = Pin<Box<dyn Stream<Item = Result<Update, Status>> + Send + 'static>>;

#[tonic::async_trait]
impl<S: Store, A: TelegramApi> BotGatewayServiceTrait for BotGatewayServer<S, A> {
    type SubscribeUpdatesStream = SubscribeStream;

    async fn subscribe_updates(
        &self,
        request: Request<SubscribeUpdatesRequest>,
    ) -> Result<Response<Self::SubscribeUpdatesStream>, Status> {
        let req = request.into_inner();
        let agent_id = req.agent_id.clone();
        if agent_id.is_empty() {
            return Err(Status::invalid_argument("agent_id is required"));
        }
        let store = self.store.clone();
        let mut receiver = self.ensure_subscriber(&agent_id).await?;

        // Replay any unacked rows persisted before the worker connected.
        let replay = store
            .replay_pending(&agent_id)
            .await
            .map_err(|e| Status::internal(format!("replay failed: {e}")))?;

        let stream = try_stream! {
            for pending in replay {
                yield Update {
                    update_json: pending.payload.to_string(),
                    update_id: pending.update_id,
                };
            }
            loop {
                match receiver.recv().await {
                    Ok(live) if live.agent_id == agent_id => {
                        yield Update {
                            update_json: live.payload_json,
                            update_id: live.update_id,
                        };
                    }
                    Ok(_) => continue,
                    // Lagged subscriber: rejoin from broadcast tail. The
                    // durable replay path already covered missed messages.
                    Err(broadcast::error::RecvError::Lagged(_)) => continue,
                    Err(broadcast::error::RecvError::Closed) => break,
                }
            }
        };
        Ok(Response::new(
            Box::pin(stream) as Self::SubscribeUpdatesStream
        ))
    }

    async fn acknowledge_update(
        &self,
        request: Request<AcknowledgeUpdateRequest>,
    ) -> Result<Response<AcknowledgeUpdateResponse>, Status> {
        let req = request.into_inner();
        if req.agent_id.is_empty() {
            return Err(Status::invalid_argument("agent_id is required"));
        }
        let acknowledged = self
            .store
            .acknowledge_update(&req.agent_id, req.update_id)
            .await
            .map_err(|e| Status::internal(format!("acknowledge failed: {e}")))?;
        Ok(Response::new(AcknowledgeUpdateResponse { acknowledged }))
    }

    async fn register_bot(
        &self,
        request: Request<RegisterBotRequest>,
    ) -> Result<Response<RegisterBotResponse>, Status> {
        let req = request.into_inner();
        if req.agent_id.is_empty() {
            return Err(Status::invalid_argument("agent_id is required"));
        }
        if req.bot_token.is_empty() {
            return Err(Status::invalid_argument("bot_token is required"));
        }
        self.store
            .upsert_bot(&req.agent_id, &req.bot_token)
            .await
            .map_err(|e| Status::internal(format!("upsert failed: {e}")))?;
        let starting_offset = self
            .store
            .list_bots()
            .await
            .map_err(|e| Status::internal(format!("list bots failed: {e}")))?
            .into_iter()
            .find(|b| b.agent_id == req.agent_id)
            .map(|b| b.last_offset)
            .unwrap_or(0);
        self.start_poller(&req.agent_id, &req.bot_token, starting_offset)
            .await;
        Ok(Response::new(RegisterBotResponse { registered: true }))
    }

    async fn unregister_bot(
        &self,
        request: Request<UnregisterBotRequest>,
    ) -> Result<Response<UnregisterBotResponse>, Status> {
        let req = request.into_inner();
        if req.agent_id.is_empty() {
            return Err(Status::invalid_argument("agent_id is required"));
        }
        let mut state_map = self.state.write().await;
        if let Some(prev) = state_map.remove(&req.agent_id) {
            let _ = prev.cancel_tx.send(true);
        }
        let removed = self
            .store
            .delete_bot(&req.agent_id)
            .await
            .map_err(|e| Status::internal(format!("delete failed: {e}")))?;
        Ok(Response::new(UnregisterBotResponse { removed }))
    }

    async fn get_gateway_status(
        &self,
        _request: Request<GetGatewayStatusRequest>,
    ) -> Result<Response<GetGatewayStatusResponse>, Status> {
        let bots = self
            .store
            .snapshot()
            .await
            .map_err(|e| Status::internal(format!("snapshot failed: {e}")))?;
        let state_map = self.state.read().await;
        let active_subscribers: i32 = state_map
            .values()
            .map(|s| s.broadcaster.receiver_count() as i32)
            .sum();
        let payload = GetGatewayStatusResponse {
            active_subscribers,
            bots: bots
                .into_iter()
                .map(|b| BotStatus {
                    agent_id: b.agent_id,
                    last_update_id: b.last_offset,
                    last_poll_at: String::new(),
                    errors_recent: 0,
                })
                .collect(),
        };
        Ok(Response::new(payload))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::store::InMemoryStore;
    use crate::telegram::{MockTelegramApi, TelegramUpdate};
    use futures::StreamExt;
    use serde_json::json;

    fn live_update(id: i64) -> TelegramUpdate {
        TelegramUpdate {
            update_id: id,
            payload: json!({"update_id": id, "message": {"text": format!("msg-{id}")}}),
        }
    }

    fn make_server() -> BotGatewayServer<InMemoryStore, MockTelegramApi> {
        BotGatewayServer::new(
            Arc::new(InMemoryStore::new()),
            Arc::new(MockTelegramApi::new()),
            Duration::from_millis(20),
            Duration::from_millis(5),
            100,
        )
    }

    #[tokio::test]
    async fn register_then_subscribe_streams_updates_through_broadcast() {
        let server = make_server();
        // Pre-seed the mock Telegram queue.
        server.api.push_batch("tok-a", vec![live_update(1)]).await;

        // Register bot — spawns a poller.
        let resp = server
            .register_bot(Request::new(RegisterBotRequest {
                metadata: None,
                agent_id: "AGENT_A".into(),
                bot_token: "tok-a".into(),
            }))
            .await
            .unwrap();
        assert!(resp.into_inner().registered);

        // Subscribe and expect the broadcast Update to flow through.
        let stream_resp = server
            .subscribe_updates(Request::new(SubscribeUpdatesRequest {
                metadata: None,
                agent_id: "AGENT_A".into(),
            }))
            .await
            .unwrap();
        let mut stream = stream_resp.into_inner();

        let received = tokio::time::timeout(Duration::from_secs(2), stream.next())
            .await
            .expect("stream timed out")
            .expect("stream closed without item")
            .expect("status error");
        assert_eq!(received.update_id, 1);
    }

    #[tokio::test]
    async fn subscribe_replays_pending_rows_before_streaming_live() {
        let server = make_server();
        // Bot registered but poller has not produced anything yet —
        // pre-stuff the durable queue to simulate updates persisted by
        // a prior run that crashed before a worker picked them up.
        server
            .register_bot(Request::new(RegisterBotRequest {
                metadata: None,
                agent_id: "AGENT_A".into(),
                bot_token: "tok-a".into(),
            }))
            .await
            .unwrap();
        server
            .store
            .enqueue_updates(
                "AGENT_A",
                &[
                    crate::store::PendingUpdate {
                        agent_id: "AGENT_A".into(),
                        update_id: 100,
                        payload: json!({"update_id": 100}),
                    },
                    crate::store::PendingUpdate {
                        agent_id: "AGENT_A".into(),
                        update_id: 101,
                        payload: json!({"update_id": 101}),
                    },
                ],
                102,
            )
            .await
            .unwrap();

        let stream_resp = server
            .subscribe_updates(Request::new(SubscribeUpdatesRequest {
                metadata: None,
                agent_id: "AGENT_A".into(),
            }))
            .await
            .unwrap();
        let mut stream = stream_resp.into_inner();

        let first = tokio::time::timeout(Duration::from_secs(2), stream.next())
            .await
            .expect("timeout")
            .expect("closed")
            .expect("status");
        let second = tokio::time::timeout(Duration::from_secs(2), stream.next())
            .await
            .expect("timeout")
            .expect("closed")
            .expect("status");
        assert_eq!(first.update_id, 100);
        assert_eq!(second.update_id, 101);
    }

    #[tokio::test]
    async fn acknowledge_deletes_from_pending_and_is_idempotent() {
        let server = make_server();
        server
            .register_bot(Request::new(RegisterBotRequest {
                metadata: None,
                agent_id: "AGENT_A".into(),
                bot_token: "tok-a".into(),
            }))
            .await
            .unwrap();
        server
            .store
            .enqueue_updates(
                "AGENT_A",
                &[crate::store::PendingUpdate {
                    agent_id: "AGENT_A".into(),
                    update_id: 7,
                    payload: json!({}),
                }],
                8,
            )
            .await
            .unwrap();

        let r1 = server
            .acknowledge_update(Request::new(AcknowledgeUpdateRequest {
                metadata: None,
                agent_id: "AGENT_A".into(),
                update_id: 7,
            }))
            .await
            .unwrap();
        assert!(r1.into_inner().acknowledged);
        let r2 = server
            .acknowledge_update(Request::new(AcknowledgeUpdateRequest {
                metadata: None,
                agent_id: "AGENT_A".into(),
                update_id: 7,
            }))
            .await
            .unwrap();
        assert!(!r2.into_inner().acknowledged, "second ack must be a no-op");
    }

    #[tokio::test]
    async fn subscribe_without_register_returns_failed_precondition() {
        let server = make_server();
        let err = server
            .subscribe_updates(Request::new(SubscribeUpdatesRequest {
                metadata: None,
                agent_id: "AGENT_X".into(),
            }))
            .await
            .err()
            .expect("expected failure");
        assert_eq!(err.code(), tonic::Code::FailedPrecondition);
    }

    #[tokio::test]
    async fn unregister_stops_poller_and_clears_state() {
        let server = make_server();
        server
            .register_bot(Request::new(RegisterBotRequest {
                metadata: None,
                agent_id: "AGENT_A".into(),
                bot_token: "tok-a".into(),
            }))
            .await
            .unwrap();
        let resp = server
            .unregister_bot(Request::new(UnregisterBotRequest {
                metadata: None,
                agent_id: "AGENT_A".into(),
            }))
            .await
            .unwrap();
        assert!(resp.into_inner().removed);
        let state = server.state.read().await;
        assert!(!state.contains_key("AGENT_A"));
    }

    #[tokio::test]
    async fn get_gateway_status_reports_registered_bots() {
        let server = make_server();
        server
            .register_bot(Request::new(RegisterBotRequest {
                metadata: None,
                agent_id: "AGENT_A".into(),
                bot_token: "tok-a".into(),
            }))
            .await
            .unwrap();
        let resp = server
            .get_gateway_status(Request::new(GetGatewayStatusRequest { metadata: None }))
            .await
            .unwrap()
            .into_inner();
        assert_eq!(resp.bots.len(), 1);
        assert_eq!(resp.bots[0].agent_id, "AGENT_A");
    }
}
