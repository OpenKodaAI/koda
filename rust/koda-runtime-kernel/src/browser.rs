use std::collections::HashMap;
use std::fs::OpenOptions as StdOpenOptions;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use tokio::process::Child;
use tokio::sync::Mutex;
use tonic::Status;

use crate::processes::send_process_signal;

#[derive(Clone)]
pub(crate) struct ManagedBrowserSessionHandle {
    pub(crate) children: Vec<Arc<Mutex<Child>>>,
}

pub(crate) fn resolve_binary_path(name: &str) -> Option<PathBuf> {
    let paths = std::env::var_os("PATH")?;
    for directory in std::env::split_paths(&paths) {
        let candidate = directory.join(name);
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}

#[allow(clippy::result_large_err)]
pub(crate) fn open_browser_log(
    runtime_dir: &Path,
    name: &str,
) -> Result<std::process::Stdio, Status> {
    let file = StdOpenOptions::new()
        .create(true)
        .append(true)
        .open(runtime_dir.join(format!("{name}.log")))
        .map_err(|error| Status::internal(format!("failed to open browser log {name}: {error}")))?;
    Ok(std::process::Stdio::from(file))
}

pub(crate) async fn stop_managed_browser_session(
    browser_handles: Arc<Mutex<HashMap<String, ManagedBrowserSessionHandle>>>,
    session_id: &str,
    force: bool,
) -> bool {
    let handle = {
        let mut handles = browser_handles.lock().await;
        handles.remove(session_id)
    };
    let Some(handle) = handle else {
        return false;
    };
    for child in handle.children {
        let pid = {
            let child = child.lock().await;
            child.id().map(|value| value as i32)
        };
        if force {
            let mut child = child.lock().await;
            let _ = child.start_kill();
            let _ = child.wait().await;
            continue;
        }
        let terminated = send_process_signal(pid, pid, libc::SIGTERM);
        let waited = {
            let mut child = child.lock().await;
            tokio::time::timeout(Duration::from_secs(3), child.wait()).await
        };
        if !terminated || waited.is_err() {
            let mut child = child.lock().await;
            let _ = child.start_kill();
            let _ = child.wait().await;
        }
    }
    true
}
