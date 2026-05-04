//! Tonic implementation of `PolicyEngineService`.

use std::sync::Arc;

use tonic::{Request, Response, Status};

use koda_proto::policy_engine::v1::policy_engine_service_server::PolicyEngineService as PolicyEngineServiceTrait;
use koda_proto::policy_engine::v1::{
    AcquireSlotRequest, AcquireSlotResponse, CheckIngestRequest, CheckIngestResponse,
    GetPolicyRequest, GetPolicyResponse, Policy as PolicyMsg, RecordSpendRequest,
    RecordSpendResponse, ReleaseSlotRequest, ReleaseSlotResponse, UpdatePolicyRequest,
    UpdatePolicyResponse,
};

use crate::limiter::RateLimiter;
use crate::slots::SlotTable;
use crate::spend::evaluate_spend;
use crate::store::{Policy, PolicyStore};

pub struct PolicyEngineServer<S: PolicyStore> {
    store: Arc<S>,
    limiter: RateLimiter,
    slots: SlotTable,
}

impl<S: PolicyStore> PolicyEngineServer<S> {
    pub fn new(store: Arc<S>) -> Self {
        Self {
            store,
            limiter: RateLimiter::new(),
            slots: SlotTable::new(),
        }
    }

    async fn policy_or_default(&self, workspace_id: &str) -> Policy {
        match self.store.get_policy(workspace_id).await {
            Ok(Some(p)) => p,
            _ => Policy::unlimited(workspace_id),
        }
    }
}

fn policy_to_msg(p: &Policy) -> PolicyMsg {
    PolicyMsg {
        workspace_id: p.workspace_id.clone(),
        max_concurrent_agents: p.max_concurrent_agents,
        max_messages_per_minute: p.max_messages_per_minute,
        monthly_llm_spend_usd_cap: p.monthly_llm_spend_usd_cap,
        spend_warning_fraction: p.spend_warning_fraction,
        enabled: p.enabled,
    }
}

fn msg_to_policy(m: &PolicyMsg) -> Policy {
    Policy {
        workspace_id: m.workspace_id.clone(),
        max_concurrent_agents: m.max_concurrent_agents,
        max_messages_per_minute: m.max_messages_per_minute,
        monthly_llm_spend_usd_cap: m.monthly_llm_spend_usd_cap,
        spend_warning_fraction: m.spend_warning_fraction,
        enabled: m.enabled,
    }
}

#[tonic::async_trait]
impl<S: PolicyStore> PolicyEngineServiceTrait for PolicyEngineServer<S> {
    async fn check_ingest(
        &self,
        request: Request<CheckIngestRequest>,
    ) -> Result<Response<CheckIngestResponse>, Status> {
        let req = request.into_inner();
        if req.workspace_id.is_empty() {
            return Err(Status::invalid_argument("workspace_id is required"));
        }
        let policy = self.policy_or_default(&req.workspace_id).await;
        if !policy.enabled {
            return Ok(Response::new(CheckIngestResponse {
                allowed: true,
                deny_reason: String::new(),
                retry_after_ms: 0,
            }));
        }
        // Rate limit first — cheapest decision.
        let limit = self
            .limiter
            .check(&req.workspace_id, policy.max_messages_per_minute as u32)
            .await;
        if !limit.allowed {
            return Ok(Response::new(CheckIngestResponse {
                allowed: false,
                deny_reason: "rate_limit_exceeded".into(),
                retry_after_ms: limit.retry_after_ms as i32,
            }));
        }
        // Then concurrency cap (cheap in-memory check).
        let active = self.slots.active_count(&req.workspace_id).await;
        if policy.max_concurrent_agents > 0 && active >= policy.max_concurrent_agents {
            return Ok(Response::new(CheckIngestResponse {
                allowed: false,
                deny_reason: "concurrent_agent_limit".into(),
                retry_after_ms: 0,
            }));
        }
        // Last: spend cap (DB read for current_window_spend).
        let spent = self
            .store
            .current_window_spend(&req.workspace_id)
            .await
            .unwrap_or(0.0);
        let decision = evaluate_spend(
            policy.monthly_llm_spend_usd_cap,
            spent,
            policy.spend_warning_fraction,
        );
        if decision.hard_stop_threshold_crossed {
            return Ok(Response::new(CheckIngestResponse {
                allowed: false,
                deny_reason: "monthly_spend_cap_reached".into(),
                retry_after_ms: 0,
            }));
        }
        Ok(Response::new(CheckIngestResponse {
            allowed: true,
            deny_reason: String::new(),
            retry_after_ms: 0,
        }))
    }

    async fn record_spend(
        &self,
        request: Request<RecordSpendRequest>,
    ) -> Result<Response<RecordSpendResponse>, Status> {
        let req = request.into_inner();
        if req.workspace_id.is_empty() || req.agent_id.is_empty() {
            return Err(Status::invalid_argument(
                "workspace_id and agent_id are required",
            ));
        }
        if req.cost_usd < 0.0 {
            return Err(Status::invalid_argument("cost_usd must be >= 0"));
        }
        let total = self
            .store
            .record_spend(
                &req.workspace_id,
                &req.agent_id,
                req.cost_usd,
                &req.provider,
                &req.model,
            )
            .await
            .map_err(|e| Status::internal(format!("record_spend: {e}")))?;
        let policy = self.policy_or_default(&req.workspace_id).await;
        let decision = evaluate_spend(
            policy.monthly_llm_spend_usd_cap,
            total,
            policy.spend_warning_fraction,
        );
        Ok(Response::new(RecordSpendResponse {
            remaining_budget_usd: decision.remaining_budget_usd,
            warning_threshold_crossed: decision.warning_threshold_crossed,
            hard_stop_threshold_crossed: decision.hard_stop_threshold_crossed,
        }))
    }

    async fn acquire_slot(
        &self,
        request: Request<AcquireSlotRequest>,
    ) -> Result<Response<AcquireSlotResponse>, Status> {
        let req = request.into_inner();
        if req.workspace_id.is_empty() {
            return Err(Status::invalid_argument("workspace_id is required"));
        }
        let policy = self.policy_or_default(&req.workspace_id).await;
        let max_holders = if policy.enabled {
            policy.max_concurrent_agents
        } else {
            0
        };
        let lease_ttl = req.lease_ttl_seconds.max(1) as u32;
        let r = self
            .slots
            .acquire(&req.workspace_id, max_holders, lease_ttl)
            .await;
        Ok(Response::new(AcquireSlotResponse {
            acquired: r.acquired,
            slot_token: r.slot_token,
            active_holders: r.active_holders,
            max_holders: r.max_holders,
        }))
    }

    async fn release_slot(
        &self,
        request: Request<ReleaseSlotRequest>,
    ) -> Result<Response<ReleaseSlotResponse>, Status> {
        let req = request.into_inner();
        if req.workspace_id.is_empty() || req.slot_token.is_empty() {
            return Err(Status::invalid_argument(
                "workspace_id and slot_token are required",
            ));
        }
        let released = self.slots.release(&req.workspace_id, &req.slot_token).await;
        Ok(Response::new(ReleaseSlotResponse { released }))
    }

    async fn update_policy(
        &self,
        request: Request<UpdatePolicyRequest>,
    ) -> Result<Response<UpdatePolicyResponse>, Status> {
        let req = request.into_inner();
        let msg = req
            .policy
            .ok_or_else(|| Status::invalid_argument("policy is required"))?;
        if msg.workspace_id.is_empty() {
            return Err(Status::invalid_argument("workspace_id is required"));
        }
        let policy = msg_to_policy(&msg);
        self.store
            .upsert_policy(&policy)
            .await
            .map_err(|e| Status::internal(format!("upsert_policy: {e}")))?;
        Ok(Response::new(UpdatePolicyResponse {
            policy: Some(policy_to_msg(&policy)),
        }))
    }

    async fn get_policy(
        &self,
        request: Request<GetPolicyRequest>,
    ) -> Result<Response<GetPolicyResponse>, Status> {
        let req = request.into_inner();
        let policy = self.policy_or_default(&req.workspace_id).await;
        Ok(Response::new(GetPolicyResponse {
            policy: Some(policy_to_msg(&policy)),
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::store::InMemoryStore;

    fn req<T>(value: T) -> Request<T> {
        Request::new(value)
    }

    fn make_server() -> PolicyEngineServer<InMemoryStore> {
        PolicyEngineServer::new(Arc::new(InMemoryStore::new()))
    }

    fn policy_msg(rate: i32, concurrent: i32, cap: f64) -> PolicyMsg {
        PolicyMsg {
            workspace_id: "ws".into(),
            max_concurrent_agents: concurrent,
            max_messages_per_minute: rate,
            monthly_llm_spend_usd_cap: cap,
            spend_warning_fraction: 0.8,
            enabled: true,
        }
    }

    #[tokio::test]
    async fn unknown_workspace_defaults_to_unlimited_allow() {
        let server = make_server();
        let resp = server
            .check_ingest(req(CheckIngestRequest {
                metadata: None,
                workspace_id: "ws".into(),
                agent_id: "AGENT_A".into(),
                message_size_bytes: 100,
            }))
            .await
            .unwrap()
            .into_inner();
        assert!(resp.allowed);
        assert!(resp.deny_reason.is_empty());
    }

    #[tokio::test]
    async fn rate_limit_denies_after_capacity_exhausted() {
        let server = make_server();
        server
            .update_policy(req(UpdatePolicyRequest {
                metadata: None,
                policy: Some(policy_msg(2, 0, 0.0)),
            }))
            .await
            .unwrap();
        for _ in 0..2 {
            let resp = server
                .check_ingest(req(CheckIngestRequest {
                    metadata: None,
                    workspace_id: "ws".into(),
                    agent_id: "A".into(),
                    message_size_bytes: 1,
                }))
                .await
                .unwrap()
                .into_inner();
            assert!(resp.allowed);
        }
        let blocked = server
            .check_ingest(req(CheckIngestRequest {
                metadata: None,
                workspace_id: "ws".into(),
                agent_id: "A".into(),
                message_size_bytes: 1,
            }))
            .await
            .unwrap()
            .into_inner();
        assert!(!blocked.allowed);
        assert_eq!(blocked.deny_reason, "rate_limit_exceeded");
        assert!(blocked.retry_after_ms > 0);
    }

    #[tokio::test]
    async fn concurrent_cap_blocks_extra_acquires() {
        let server = make_server();
        server
            .update_policy(req(UpdatePolicyRequest {
                metadata: None,
                policy: Some(policy_msg(0, 1, 0.0)),
            }))
            .await
            .unwrap();
        let r1 = server
            .acquire_slot(req(AcquireSlotRequest {
                metadata: None,
                workspace_id: "ws".into(),
                agent_id: "A".into(),
                lease_ttl_seconds: 60,
            }))
            .await
            .unwrap()
            .into_inner();
        assert!(r1.acquired);
        let r2 = server
            .acquire_slot(req(AcquireSlotRequest {
                metadata: None,
                workspace_id: "ws".into(),
                agent_id: "A".into(),
                lease_ttl_seconds: 60,
            }))
            .await
            .unwrap()
            .into_inner();
        assert!(!r2.acquired);
        assert_eq!(r1.active_holders, 1);
    }

    #[tokio::test]
    async fn record_spend_emits_warning_then_hard_stop() {
        let server = make_server();
        server
            .update_policy(req(UpdatePolicyRequest {
                metadata: None,
                policy: Some(policy_msg(0, 0, 10.0)),
            }))
            .await
            .unwrap();
        let r1 = server
            .record_spend(req(RecordSpendRequest {
                metadata: None,
                workspace_id: "ws".into(),
                agent_id: "A".into(),
                cost_usd: 8.5,
                provider: "openai".into(),
                model: "gpt".into(),
            }))
            .await
            .unwrap()
            .into_inner();
        assert!(r1.warning_threshold_crossed);
        assert!(!r1.hard_stop_threshold_crossed);
        let r2 = server
            .record_spend(req(RecordSpendRequest {
                metadata: None,
                workspace_id: "ws".into(),
                agent_id: "A".into(),
                cost_usd: 5.0,
                provider: "openai".into(),
                model: "gpt".into(),
            }))
            .await
            .unwrap()
            .into_inner();
        assert!(r2.hard_stop_threshold_crossed);
        // After hard-stop, CheckIngest must deny.
        let blocked = server
            .check_ingest(req(CheckIngestRequest {
                metadata: None,
                workspace_id: "ws".into(),
                agent_id: "A".into(),
                message_size_bytes: 1,
            }))
            .await
            .unwrap()
            .into_inner();
        assert!(!blocked.allowed);
        assert_eq!(blocked.deny_reason, "monthly_spend_cap_reached");
    }

    #[tokio::test]
    async fn release_slot_makes_room_for_new_holder() {
        let server = make_server();
        server
            .update_policy(req(UpdatePolicyRequest {
                metadata: None,
                policy: Some(policy_msg(0, 1, 0.0)),
            }))
            .await
            .unwrap();
        let r1 = server
            .acquire_slot(req(AcquireSlotRequest {
                metadata: None,
                workspace_id: "ws".into(),
                agent_id: "A".into(),
                lease_ttl_seconds: 60,
            }))
            .await
            .unwrap()
            .into_inner();
        let token = r1.slot_token;
        let released = server
            .release_slot(req(ReleaseSlotRequest {
                metadata: None,
                workspace_id: "ws".into(),
                slot_token: token,
            }))
            .await
            .unwrap()
            .into_inner();
        assert!(released.released);
        let r2 = server
            .acquire_slot(req(AcquireSlotRequest {
                metadata: None,
                workspace_id: "ws".into(),
                agent_id: "A".into(),
                lease_ttl_seconds: 60,
            }))
            .await
            .unwrap()
            .into_inner();
        assert!(r2.acquired);
    }

    #[tokio::test]
    async fn disabled_policy_short_circuits_to_allow() {
        let server = make_server();
        let mut p = policy_msg(1, 1, 1.0);
        p.enabled = false;
        server
            .update_policy(req(UpdatePolicyRequest {
                metadata: None,
                policy: Some(p),
            }))
            .await
            .unwrap();
        for _ in 0..50 {
            assert!(
                server
                    .check_ingest(req(CheckIngestRequest {
                        metadata: None,
                        workspace_id: "ws".into(),
                        agent_id: "A".into(),
                        message_size_bytes: 1,
                    }))
                    .await
                    .unwrap()
                    .into_inner()
                    .allowed
            );
        }
    }
}
