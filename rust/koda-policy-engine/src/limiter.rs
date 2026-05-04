//! Per-workspace token-bucket rate limiter.
//!
//! Sub-millisecond decision on the message-ingest hot path. Each
//! workspace gets its own ``TokenBucket`` keyed by ``workspace_id``;
//! buckets are stored in a sharded ``DashMap``-style structure (here
//! kept simple as a ``RwLock<HashMap>``; sharding is a follow-up if
//! contention shows up under load — measured first, optimized only if
//! needed).
//!
//! The bucket refills at ``rate_per_minute`` tokens / minute and tops
//! out at the same value so a quiet workspace can burst up to its cap
//! before being throttled. ``rate_per_minute = 0`` disables the limit
//! (used by the unlimited / single-tenant configuration).

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use tokio::sync::RwLock;

#[derive(Debug, Clone, Copy)]
pub struct LimiterDecision {
    pub allowed: bool,
    pub retry_after_ms: u32,
}

#[derive(Debug, Clone)]
struct Bucket {
    tokens: f64,
    capacity: f64,
    refill_per_second: f64,
    last_refill: Instant,
}

impl Bucket {
    fn new(rate_per_minute: u32) -> Self {
        let capacity = rate_per_minute as f64;
        let refill_per_second = capacity / 60.0;
        Self {
            tokens: capacity,
            capacity,
            refill_per_second,
            last_refill: Instant::now(),
        }
    }

    fn try_consume(&mut self, now: Instant) -> LimiterDecision {
        let elapsed = now.duration_since(self.last_refill).as_secs_f64();
        if elapsed > 0.0 {
            self.tokens = (self.tokens + elapsed * self.refill_per_second).min(self.capacity);
            self.last_refill = now;
        }
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            LimiterDecision {
                allowed: true,
                retry_after_ms: 0,
            }
        } else {
            // How many ms until at least 1 token is available again?
            let deficit = 1.0 - self.tokens;
            let seconds_to_one = if self.refill_per_second > 0.0 {
                deficit / self.refill_per_second
            } else {
                f64::INFINITY
            };
            let retry_after_ms = (seconds_to_one * 1000.0).ceil().min(u32::MAX as f64) as u32;
            LimiterDecision {
                allowed: false,
                retry_after_ms,
            }
        }
    }
}

#[derive(Default, Clone)]
pub struct RateLimiter {
    buckets: Arc<RwLock<HashMap<String, Bucket>>>,
}

impl RateLimiter {
    pub fn new() -> Self {
        Self::default()
    }

    pub async fn check(&self, workspace_id: &str, rate_per_minute: u32) -> LimiterDecision {
        if rate_per_minute == 0 {
            return LimiterDecision {
                allowed: true,
                retry_after_ms: 0,
            };
        }
        let now = Instant::now();
        let mut buckets = self.buckets.write().await;
        let bucket = buckets
            .entry(workspace_id.to_string())
            .or_insert_with(|| Bucket::new(rate_per_minute));
        // Adjust capacity if policy changed (e.g. operator updated the cap).
        if (bucket.capacity - rate_per_minute as f64).abs() > f64::EPSILON {
            bucket.capacity = rate_per_minute as f64;
            bucket.refill_per_second = bucket.capacity / 60.0;
            bucket.tokens = bucket.tokens.min(bucket.capacity);
        }
        bucket.try_consume(now)
    }

    /// Test/diagnostic accessor: how many tokens a workspace has right now.
    pub async fn current_tokens(&self, workspace_id: &str) -> Option<f64> {
        self.buckets
            .read()
            .await
            .get(workspace_id)
            .map(|b| b.tokens)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn zero_rate_short_circuits_to_allowed() {
        let limiter = RateLimiter::new();
        for _ in 0..1000 {
            let d = limiter.check("ws", 0).await;
            assert!(d.allowed);
            assert_eq!(d.retry_after_ms, 0);
        }
    }

    #[tokio::test]
    async fn allows_capacity_then_denies_with_retry_hint() {
        let limiter = RateLimiter::new();
        // capacity=3 tokens. The bucket starts full.
        for _ in 0..3 {
            assert!(limiter.check("ws", 3).await.allowed);
        }
        let d = limiter.check("ws", 3).await;
        assert!(!d.allowed);
        // refill = 3/min = 0.05 tok/s -> ~20s for 1 token.
        assert!(d.retry_after_ms > 0);
    }

    #[tokio::test]
    async fn buckets_are_keyed_per_workspace() {
        let limiter = RateLimiter::new();
        for _ in 0..5 {
            assert!(limiter.check("ws_a", 5).await.allowed);
        }
        // ws_a is exhausted but ws_b still has full capacity.
        assert!(!limiter.check("ws_a", 5).await.allowed);
        assert!(limiter.check("ws_b", 5).await.allowed);
    }
}
