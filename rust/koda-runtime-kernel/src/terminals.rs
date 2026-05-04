use std::collections::{HashMap, VecDeque};
use std::sync::{Arc, RwLock};

use tokio::sync::broadcast;

use crate::state::TerminalRecord;

#[derive(Clone)]
pub(crate) struct TerminalRegistry {
    inner: Arc<RwLock<HashMap<String, TerminalBuffer>>>,
    history_limit: usize,
}

struct TerminalBuffer {
    history: VecDeque<TerminalRecord>,
    sender: broadcast::Sender<TerminalRecord>,
}

impl TerminalRegistry {
    pub(crate) fn new(history_limit: usize) -> Self {
        Self {
            inner: Arc::new(RwLock::new(HashMap::new())),
            history_limit: history_limit.max(1),
        }
    }

    pub(crate) fn append(&self, key: &str, record: TerminalRecord) {
        let mut inner = self.inner.write().expect("terminal registry poisoned");
        let buffer = inner.entry(key.to_string()).or_insert_with(|| {
            let (sender, _) = broadcast::channel(self.history_limit.next_power_of_two());
            TerminalBuffer {
                history: VecDeque::new(),
                sender,
            }
        });
        buffer.history.push_back(record.clone());
        while buffer.history.len() > self.history_limit {
            buffer.history.pop_front();
        }
        let _ = buffer.sender.send(record);
    }

    pub(crate) fn replay(&self, key: &str, stream: Option<&str>) -> Vec<TerminalRecord> {
        self.replay_after(key, stream, 0)
    }

    #[cfg(test)]
    pub(crate) fn clear(&self, key: &str) {
        let mut inner = self.inner.write().expect("terminal registry poisoned");
        inner.remove(key);
    }

    pub(crate) fn replay_after(
        &self,
        key: &str,
        stream: Option<&str>,
        sequence: u64,
    ) -> Vec<TerminalRecord> {
        let inner = self.inner.read().expect("terminal registry poisoned");
        inner
            .get(key)
            .into_iter()
            .flat_map(|buffer| buffer.history.iter())
            .filter(|record| record.sequence > sequence)
            .filter(|record| stream.is_none_or(|stream| record.stream == stream))
            .cloned()
            .collect()
    }

    pub(crate) fn subscribe(&self, key: &str) -> broadcast::Receiver<TerminalRecord> {
        let mut inner = self.inner.write().expect("terminal registry poisoned");
        inner
            .entry(key.to_string())
            .or_insert_with(|| {
                let (sender, _) = broadcast::channel(self.history_limit.next_power_of_two());
                TerminalBuffer {
                    history: VecDeque::new(),
                    sender,
                }
            })
            .sender
            .subscribe()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn record(sequence: u64, stream: &str, data: &str, eof: bool) -> TerminalRecord {
        TerminalRecord {
            sequence,
            stream: stream.to_string(),
            data: data.as_bytes().to_vec(),
            eof,
            timestamp_ms: sequence,
        }
    }

    #[test]
    fn replay_is_bounded_and_filterable() {
        let registry = TerminalRegistry::new(2);
        registry.append("task-1", record(1, "stdout", "one", false));
        registry.append("task-1", record(2, "stderr", "two", false));
        registry.append("task-1", record(3, "stdout", "three", true));

        let replay = registry.replay("task-1", None);
        assert_eq!(
            replay.iter().map(|item| item.sequence).collect::<Vec<_>>(),
            vec![2, 3]
        );

        let stdout = registry.replay("task-1", Some("stdout"));
        assert_eq!(
            stdout.iter().map(|item| item.sequence).collect::<Vec<_>>(),
            vec![3]
        );
    }

    #[tokio::test]
    async fn subscribe_receives_live_records() {
        let registry = TerminalRegistry::new(8);
        let mut receiver = registry.subscribe("task-1");

        registry.append("task-1", record(1, "stdout", "hello", false));

        let received = receiver.recv().await.unwrap();
        assert_eq!(received.sequence, 1);
        assert_eq!(received.data, b"hello");
    }
}
