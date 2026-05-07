//! Telegram getUpdates abstraction.
//!
//! Two implementations live behind one trait so the gateway can be
//! exercised end-to-end without touching the public Telegram API:
//! - [`HttpTelegramApi`] — production reqwest client.
//! - [`MockTelegramApi`] — in-memory queue for tests.

use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use serde_json::Value;
use thiserror::Error;
use tokio::sync::Mutex;

#[derive(Debug, Error)]
pub enum TelegramError {
    #[error("transport error: {0}")]
    Transport(String),
    #[error("Telegram API returned not ok: {0}")]
    ApiError(String),
    #[error("malformed payload: {0}")]
    MalformedPayload(String),
}

#[derive(Debug, Clone)]
pub struct TelegramUpdate {
    pub update_id: i64,
    pub payload: Value,
}

/// Polling result. ``next_offset`` is the value the gateway should pass
/// as ``offset`` on the next call (``last_update_id + 1`` per Telegram
/// semantics) so previously-fetched updates are not redelivered.
#[derive(Debug, Clone)]
pub struct PollResult {
    pub updates: Vec<TelegramUpdate>,
    pub next_offset: i64,
}

#[async_trait]
pub trait TelegramApi: Send + Sync + 'static {
    async fn get_updates(
        &self,
        bot_token: &str,
        offset: i64,
        timeout: Duration,
        limit: u32,
    ) -> Result<PollResult, TelegramError>;
}

/// Real Telegram client using reqwest.
pub struct HttpTelegramApi {
    base_url: String,
    client: reqwest::Client,
}

impl HttpTelegramApi {
    pub fn new(base_url: impl Into<String>) -> Self {
        let client = reqwest::Client::builder()
            // Timeout slightly above Telegram's poll timeout so the
            // connection doesn't get torn down before getUpdates returns.
            .timeout(Duration::from_secs(120))
            .build()
            .expect("reqwest client builds with default config");
        Self {
            base_url: base_url.into(),
            client,
        }
    }
}

#[async_trait]
impl TelegramApi for HttpTelegramApi {
    async fn get_updates(
        &self,
        bot_token: &str,
        offset: i64,
        timeout: Duration,
        limit: u32,
    ) -> Result<PollResult, TelegramError> {
        let url = format!("{}/bot{}/getUpdates", self.base_url, bot_token);
        let body = serde_json::json!({
            "offset": offset,
            "timeout": timeout.as_secs(),
            "limit": limit,
        });
        let resp = self
            .client
            .post(&url)
            .json(&body)
            .send()
            .await
            .map_err(|e| TelegramError::Transport(e.to_string()))?;
        let json: Value = resp
            .json()
            .await
            .map_err(|e| TelegramError::MalformedPayload(e.to_string()))?;
        parse_get_updates_response(&json, offset)
    }
}

/// Parser separated from transport so it can be unit-tested directly
/// against canned Telegram API responses.
pub fn parse_get_updates_response(
    json: &Value,
    current_offset: i64,
) -> Result<PollResult, TelegramError> {
    let ok = json.get("ok").and_then(|v| v.as_bool()).unwrap_or(false);
    if !ok {
        let desc = json
            .get("description")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown")
            .to_string();
        return Err(TelegramError::ApiError(desc));
    }
    let result = json
        .get("result")
        .and_then(|v| v.as_array())
        .ok_or_else(|| TelegramError::MalformedPayload("result is not an array".into()))?;
    let mut updates = Vec::with_capacity(result.len());
    let mut next_offset = current_offset;
    for entry in result {
        let update_id = entry
            .get("update_id")
            .and_then(|v| v.as_i64())
            .ok_or_else(|| TelegramError::MalformedPayload("update_id missing".into()))?;
        if update_id + 1 > next_offset {
            next_offset = update_id + 1;
        }
        updates.push(TelegramUpdate {
            update_id,
            payload: entry.clone(),
        });
    }
    Ok(PollResult {
        updates,
        next_offset,
    })
}

/// In-memory queue used by integration tests. Tests push pre-built
/// PollResult batches via `push_batch`; the poller consumes them in
/// order across `get_updates` calls.
#[derive(Default)]
pub struct MockTelegramApi {
    inner: Arc<Mutex<MockState>>,
}

#[derive(Default)]
struct MockState {
    queues: std::collections::HashMap<String, Vec<TelegramUpdate>>,
    /// `(bot_token, offset)` calls observed; tests assert against this
    /// to verify the poller advances offsets monotonically.
    pub call_log: Vec<(String, i64)>,
}

impl MockTelegramApi {
    pub fn new() -> Self {
        Self::default()
    }

    /// Push a batch the next get_updates call will return. Order is
    /// FIFO across batches; updates whose `update_id < offset` are
    /// dropped (mirroring Telegram semantics).
    pub async fn push_batch(&self, bot_token: &str, batch: Vec<TelegramUpdate>) {
        let mut state = self.inner.lock().await;
        state
            .queues
            .entry(bot_token.to_string())
            .or_default()
            .extend(batch);
    }

    pub async fn call_count(&self, bot_token: &str) -> usize {
        let state = self.inner.lock().await;
        state
            .call_log
            .iter()
            .filter(|(t, _)| t == bot_token)
            .count()
    }
}

#[async_trait]
impl TelegramApi for MockTelegramApi {
    async fn get_updates(
        &self,
        bot_token: &str,
        offset: i64,
        _timeout: Duration,
        limit: u32,
    ) -> Result<PollResult, TelegramError> {
        let mut state = self.inner.lock().await;
        state.call_log.push((bot_token.to_string(), offset));
        let queue = state.queues.entry(bot_token.to_string()).or_default();
        let mut delivered = Vec::new();
        let mut keep = Vec::new();
        for entry in queue.drain(..) {
            if entry.update_id < offset {
                continue; // already delivered
            }
            if delivered.len() >= limit as usize {
                keep.push(entry);
                continue;
            }
            delivered.push(entry);
        }
        *queue = keep;
        let next_offset = delivered
            .iter()
            .map(|u| u.update_id + 1)
            .max()
            .unwrap_or(offset);
        Ok(PollResult {
            updates: delivered,
            next_offset,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parse_handles_ok_response() {
        let body = json!({
            "ok": true,
            "result": [
                { "update_id": 7, "message": { "text": "hello" } },
                { "update_id": 9, "message": { "text": "world" } }
            ]
        });
        let r = parse_get_updates_response(&body, 0).unwrap();
        assert_eq!(r.updates.len(), 2);
        assert_eq!(r.updates[0].update_id, 7);
        assert_eq!(r.next_offset, 10);
    }

    #[test]
    fn parse_keeps_offset_when_empty() {
        let body = json!({"ok": true, "result": []});
        let r = parse_get_updates_response(&body, 42).unwrap();
        assert!(r.updates.is_empty());
        assert_eq!(r.next_offset, 42);
    }

    #[test]
    fn parse_propagates_telegram_errors() {
        let body = json!({"ok": false, "description": "rate limit"});
        let err = parse_get_updates_response(&body, 0).unwrap_err();
        assert!(matches!(err, TelegramError::ApiError(d) if d == "rate limit"));
    }
}
