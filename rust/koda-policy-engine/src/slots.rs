//! Per-workspace concurrent agent slot accounting.
//!
//! Workers acquire a slot before starting expensive work and release
//! it after completion. Slots have a TTL lease so a worker crash does
//! not leak the slot forever — the engine reaps expired leases on
//! every acquire.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

use tokio::sync::RwLock;
use uuid::Uuid;

#[derive(Debug, Clone)]
pub struct AcquireResult {
    pub acquired: bool,
    pub slot_token: String,
    pub active_holders: i32,
    pub max_holders: i32,
}

#[derive(Debug, Clone)]
struct Lease {
    slot_token: String,
    expires_at: Instant,
}

#[derive(Default, Clone)]
pub struct SlotTable {
    inner: Arc<RwLock<HashMap<String, Vec<Lease>>>>,
}

impl SlotTable {
    pub fn new() -> Self {
        Self::default()
    }

    pub async fn acquire(
        &self,
        workspace_id: &str,
        max_holders: i32,
        lease_ttl_seconds: u32,
    ) -> AcquireResult {
        let now = Instant::now();
        let ttl = Duration::from_secs(lease_ttl_seconds.max(1) as u64);
        let mut table = self.inner.write().await;
        let leases = table.entry(workspace_id.to_string()).or_default();
        leases.retain(|l| l.expires_at > now);
        if max_holders > 0 && leases.len() as i32 >= max_holders {
            return AcquireResult {
                acquired: false,
                slot_token: String::new(),
                active_holders: leases.len() as i32,
                max_holders,
            };
        }
        let slot_token = Uuid::new_v4().to_string();
        leases.push(Lease {
            slot_token: slot_token.clone(),
            expires_at: now + ttl,
        });
        AcquireResult {
            acquired: true,
            slot_token,
            active_holders: leases.len() as i32,
            max_holders,
        }
    }

    pub async fn release(&self, workspace_id: &str, slot_token: &str) -> bool {
        let mut table = self.inner.write().await;
        let Some(leases) = table.get_mut(workspace_id) else {
            return false;
        };
        let before = leases.len();
        leases.retain(|l| l.slot_token != slot_token);
        let removed = leases.len() < before;
        if leases.is_empty() {
            table.remove(workspace_id);
        }
        removed
    }

    pub async fn active_count(&self, workspace_id: &str) -> i32 {
        let now = Instant::now();
        let table = self.inner.read().await;
        table
            .get(workspace_id)
            .map(|v| v.iter().filter(|l| l.expires_at > now).count() as i32)
            .unwrap_or(0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn acquire_under_cap_is_allowed_and_release_works() {
        let table = SlotTable::new();
        let r = table.acquire("ws", 2, 60).await;
        assert!(r.acquired);
        assert_eq!(r.active_holders, 1);
        let token = r.slot_token.clone();

        let r2 = table.acquire("ws", 2, 60).await;
        assert!(r2.acquired);
        assert_eq!(r2.active_holders, 2);

        // Cap reached.
        let r3 = table.acquire("ws", 2, 60).await;
        assert!(!r3.acquired);

        // Release one slot.
        assert!(table.release("ws", &token).await);
        assert_eq!(table.active_count("ws").await, 1);

        // Now a third acquire fits.
        let r4 = table.acquire("ws", 2, 60).await;
        assert!(r4.acquired);
    }

    #[tokio::test]
    async fn zero_max_holders_means_unlimited() {
        let table = SlotTable::new();
        for _ in 0..100 {
            assert!(table.acquire("ws", 0, 60).await.acquired);
        }
    }

    #[tokio::test]
    async fn release_unknown_token_returns_false_and_is_safe() {
        let table = SlotTable::new();
        assert!(!table.release("ws", "missing-token").await);
    }
}
