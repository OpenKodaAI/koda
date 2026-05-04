use std::collections::{BTreeSet, HashMap};
use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use koda_proto::common::v1::RequestMetadata;
use serde::Serialize;

pub(crate) fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or(Duration::ZERO)
        .as_millis() as u64
}

#[derive(Debug)]
pub(crate) struct KernelState {
    pub(crate) started_at_ms: u64,
    pub(crate) last_reconcile_at_ms: Option<u64>,
    pub(crate) environments: HashMap<String, EnvironmentRecord>,
    pub(crate) task_to_environment: HashMap<String, String>,
    pub(crate) tasks: HashMap<String, TaskRecord>,
    pub(crate) terminal_history: HashMap<String, Vec<TerminalRecord>>,
    pub(crate) interactive_terminals: HashMap<String, InteractiveTerminalRecord>,
    pub(crate) task_to_interactive_terminals: HashMap<String, Vec<String>>,
    pub(crate) interactive_terminal_history: HashMap<String, Vec<TerminalRecord>>,
    pub(crate) next_terminal_sequence: u64,
    pub(crate) browser_sessions: HashMap<String, BrowserSessionRecord>,
    pub(crate) task_to_browser_sessions: HashMap<String, Vec<String>>,
    pub(crate) checkpoints: HashMap<String, CheckpointRecord>,
    pub(crate) task_to_checkpoints: HashMap<String, Vec<String>>,
}

impl KernelState {
    pub(crate) fn new() -> Self {
        Self {
            started_at_ms: now_ms(),
            last_reconcile_at_ms: None,
            environments: HashMap::new(),
            task_to_environment: HashMap::new(),
            tasks: HashMap::new(),
            terminal_history: HashMap::new(),
            interactive_terminals: HashMap::new(),
            task_to_interactive_terminals: HashMap::new(),
            interactive_terminal_history: HashMap::new(),
            next_terminal_sequence: 1,
            browser_sessions: HashMap::new(),
            task_to_browser_sessions: HashMap::new(),
            checkpoints: HashMap::new(),
            task_to_checkpoints: HashMap::new(),
        }
    }

    pub(crate) fn active_environment_count(&self) -> usize {
        self.environments
            .values()
            .filter(|item| item.active)
            .count()
    }

    pub(crate) fn next_terminal_sequence(&mut self) -> u64 {
        let sequence = self.next_terminal_sequence;
        self.next_terminal_sequence = self.next_terminal_sequence.saturating_add(1);
        sequence
    }
}

#[derive(Clone, Debug)]
pub(crate) struct EnvironmentRecord {
    pub(crate) environment_id: String,
    pub(crate) task_id: String,
    pub(crate) agent_id: String,
    pub(crate) workspace_path: String,
    pub(crate) worktree_ref: String,
    pub(crate) branch_name: String,
    pub(crate) created_worktree: bool,
    pub(crate) worktree_mode: String,
    pub(crate) metadata_path: String,
    pub(crate) runtime_root: PathBuf,
    pub(crate) created_at_ms: u64,
    pub(crate) last_updated_at_ms: u64,
    pub(crate) active: bool,
    pub(crate) terminal_phase: String,
}

#[derive(Clone, Debug)]
pub(crate) struct TaskRecord {
    pub(crate) task_id: String,
    pub(crate) agent_id: String,
    pub(crate) environment_id: String,
    pub(crate) phase: String,
    pub(crate) process_id: Option<String>,
    pub(crate) pid: Option<i32>,
    pub(crate) pgid: Option<i32>,
    pub(crate) process_status: String,
    pub(crate) process_running: bool,
    pub(crate) exit_code: Option<i32>,
    pub(crate) command: String,
    pub(crate) args: Vec<String>,
    pub(crate) created_at_ms: u64,
    pub(crate) last_updated_at_ms: u64,
    pub(crate) started_at_ms: Option<u64>,
    pub(crate) finalized_at_ms: Option<u64>,
    pub(crate) pause_reason: Option<String>,
    pub(crate) finalize_error: Option<String>,
    pub(crate) sessions: BTreeSet<String>,
    pub(crate) stdout_terminal_id: Option<String>,
    pub(crate) stderr_terminal_id: Option<String>,
    pub(crate) stdout_eof: bool,
    pub(crate) stderr_eof: bool,
    pub(crate) terminal_closed_at_ms: Option<u64>,
    pub(crate) metadata: Option<RequestMetadata>,
}

impl TaskRecord {
    pub(crate) fn is_terminal(&self) -> bool {
        matches!(
            self.phase.as_str(),
            "completed"
                | "failed"
                | "cancelled"
                | "completed_retained"
                | "cancelled_retained"
                | "recoverable_failed_retained"
                | "terminal_failed"
                | "cleaned"
        )
    }
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct TerminalRecord {
    #[serde(skip)]
    pub(crate) sequence: u64,
    pub(crate) stream: String,
    #[serde(serialize_with = "serialize_terminal_data")]
    pub(crate) data: Vec<u8>,
    pub(crate) eof: bool,
    pub(crate) timestamp_ms: u64,
}

#[derive(Serialize)]
pub(crate) struct SnapshotPayload {
    pub(crate) kernel: KernelSnapshot,
    pub(crate) environment: EnvironmentSnapshot,
    pub(crate) task: TaskSnapshot,
    pub(crate) terminal: Vec<TerminalSnapshot>,
    pub(crate) interactive_terminals: Vec<InteractiveTerminalSnapshot>,
    pub(crate) browser_sessions: Vec<BrowserSessionSnapshot>,
    pub(crate) checkpoints: Vec<CheckpointSnapshot>,
}

#[derive(Serialize)]
pub(crate) struct KernelSnapshot {
    pub(crate) service: String,
    pub(crate) started_at_ms: u64,
    pub(crate) last_reconcile_at_ms: Option<u64>,
    pub(crate) active_environment_count: usize,
    pub(crate) known_task_count: usize,
    pub(crate) authoritative: bool,
    pub(crate) production_ready: bool,
    pub(crate) maturity: String,
    pub(crate) authority_scope: String,
    pub(crate) authoritative_operations: Vec<String>,
    pub(crate) full_authority: bool,
    pub(crate) partial_authority: bool,
    pub(crate) cutover_blockers: Vec<String>,
    pub(crate) interactive_terminal_count: usize,
    pub(crate) browser_session_count: usize,
    pub(crate) checkpoint_count: usize,
}

#[derive(Serialize)]
pub(crate) struct EnvironmentSnapshot {
    pub(crate) environment_id: String,
    pub(crate) task_id: String,
    pub(crate) agent_id: String,
    pub(crate) workspace_path: String,
    pub(crate) worktree_ref: String,
    pub(crate) branch_name: String,
    pub(crate) created_worktree: bool,
    pub(crate) worktree_mode: String,
    pub(crate) metadata_path: String,
    pub(crate) runtime_root: String,
    pub(crate) active: bool,
    pub(crate) phase: String,
    pub(crate) created_at_ms: u64,
    pub(crate) last_updated_at_ms: u64,
}

impl From<&EnvironmentRecord> for EnvironmentSnapshot {
    fn from(value: &EnvironmentRecord) -> Self {
        Self {
            environment_id: value.environment_id.clone(),
            task_id: value.task_id.clone(),
            agent_id: value.agent_id.clone(),
            workspace_path: value.workspace_path.clone(),
            worktree_ref: value.worktree_ref.clone(),
            branch_name: value.branch_name.clone(),
            created_worktree: value.created_worktree,
            worktree_mode: value.worktree_mode.clone(),
            metadata_path: value.metadata_path.clone(),
            runtime_root: value.runtime_root.display().to_string(),
            active: value.active,
            phase: value.terminal_phase.clone(),
            created_at_ms: value.created_at_ms,
            last_updated_at_ms: value.last_updated_at_ms,
        }
    }
}

#[derive(Serialize)]
pub(crate) struct TaskSnapshot {
    pub(crate) task_id: String,
    pub(crate) agent_id: String,
    pub(crate) environment_id: String,
    pub(crate) phase: String,
    pub(crate) final_phase: Option<String>,
    pub(crate) process_id: Option<String>,
    pub(crate) pid: Option<i32>,
    pub(crate) pgid: Option<i32>,
    pub(crate) process_status: String,
    pub(crate) process_running: bool,
    pub(crate) exit_code: Option<i32>,
    pub(crate) command: String,
    pub(crate) args: Vec<String>,
    pub(crate) created_at_ms: u64,
    pub(crate) last_updated_at_ms: u64,
    pub(crate) started_at_ms: Option<u64>,
    pub(crate) finalized_at_ms: Option<u64>,
    pub(crate) pause_reason: Option<String>,
    pub(crate) finalize_error: Option<String>,
    pub(crate) sessions: Vec<String>,
    pub(crate) stdout_terminal_id: Option<String>,
    pub(crate) stderr_terminal_id: Option<String>,
    pub(crate) metadata: Option<MetadataSnapshot>,
}

impl From<&TaskRecord> for TaskSnapshot {
    fn from(value: &TaskRecord) -> Self {
        Self {
            task_id: value.task_id.clone(),
            agent_id: value.agent_id.clone(),
            environment_id: value.environment_id.clone(),
            phase: value.phase.clone(),
            final_phase: value.finalized_at_ms.map(|_| value.phase.clone()),
            process_id: value.process_id.clone(),
            pid: value.pid,
            pgid: value.pgid,
            process_status: value.process_status.clone(),
            process_running: value.process_running,
            exit_code: value.exit_code,
            command: value.command.clone(),
            args: value.args.clone(),
            created_at_ms: value.created_at_ms,
            last_updated_at_ms: value.last_updated_at_ms,
            started_at_ms: value.started_at_ms,
            finalized_at_ms: value.finalized_at_ms,
            pause_reason: value.pause_reason.clone(),
            finalize_error: value.finalize_error.clone(),
            sessions: value.sessions.iter().cloned().collect(),
            stdout_terminal_id: value.stdout_terminal_id.clone(),
            stderr_terminal_id: value.stderr_terminal_id.clone(),
            metadata: value.metadata.as_ref().map(MetadataSnapshot::from),
        }
    }
}

#[derive(Serialize)]
pub(crate) struct MetadataSnapshot {
    pub(crate) request_id: String,
    pub(crate) trace_id: String,
    pub(crate) agent_id: String,
    pub(crate) task_id: String,
    pub(crate) user_id: String,
    pub(crate) labels: HashMap<String, String>,
}

impl From<&RequestMetadata> for MetadataSnapshot {
    fn from(value: &RequestMetadata) -> Self {
        Self {
            request_id: value.request_id.clone(),
            trace_id: value.trace_id.clone(),
            agent_id: value.agent_id.clone(),
            task_id: value.task_id.clone(),
            user_id: value.user_id.clone(),
            labels: value.labels.clone(),
        }
    }
}

#[derive(Serialize)]
pub(crate) struct TerminalSnapshot {
    pub(crate) stream: String,
    pub(crate) data: String,
    pub(crate) eof: bool,
    pub(crate) timestamp_ms: u64,
}

#[derive(Clone, Debug)]
pub(crate) struct InteractiveTerminalRecord {
    pub(crate) session_id: String,
    pub(crate) task_id: String,
    pub(crate) environment_id: String,
    pub(crate) status: String,
    pub(crate) eof: bool,
    pub(crate) opened_at_ms: u64,
    pub(crate) closed_at_ms: Option<u64>,
    pub(crate) pid: Option<i32>,
    pub(crate) pgid: Option<i32>,
    pub(crate) exit_code: Option<i32>,
    pub(crate) command: String,
    pub(crate) args: Vec<String>,
    pub(crate) working_directory: String,
    pub(crate) cols: u32,
    pub(crate) rows: u32,
}

#[derive(Serialize)]
pub(crate) struct InteractiveTerminalSnapshot {
    pub(crate) session_id: String,
    pub(crate) task_id: String,
    pub(crate) environment_id: String,
    pub(crate) status: String,
    pub(crate) eof: bool,
    pub(crate) opened_at_ms: u64,
    pub(crate) closed_at_ms: Option<u64>,
    pub(crate) pid: Option<i32>,
    pub(crate) pgid: Option<i32>,
    pub(crate) exit_code: Option<i32>,
    pub(crate) command: String,
    pub(crate) args: Vec<String>,
    pub(crate) working_directory: String,
    pub(crate) cols: u32,
    pub(crate) rows: u32,
}

impl From<&InteractiveTerminalRecord> for InteractiveTerminalSnapshot {
    fn from(value: &InteractiveTerminalRecord) -> Self {
        Self {
            session_id: value.session_id.clone(),
            task_id: value.task_id.clone(),
            environment_id: value.environment_id.clone(),
            status: value.status.clone(),
            eof: value.eof,
            opened_at_ms: value.opened_at_ms,
            closed_at_ms: value.closed_at_ms,
            pid: value.pid,
            pgid: value.pgid,
            exit_code: value.exit_code,
            command: value.command.clone(),
            args: value.args.clone(),
            working_directory: value.working_directory.clone(),
            cols: value.cols,
            rows: value.rows,
        }
    }
}

#[derive(Clone, Debug)]
pub(crate) struct BrowserSessionRecord {
    pub(crate) session_id: String,
    pub(crate) task_id: String,
    pub(crate) environment_id: String,
    pub(crate) scope_id: String,
    pub(crate) transport: String,
    pub(crate) status: String,
    pub(crate) runtime_dir: String,
    pub(crate) display_id: Option<i32>,
    pub(crate) vnc_port: Option<i32>,
    pub(crate) novnc_port: Option<i32>,
    pub(crate) missing_binaries: Vec<String>,
    pub(crate) created_at_ms: u64,
    pub(crate) ended_at_ms: Option<u64>,
    pub(crate) metadata: HashMap<String, String>,
}

#[derive(Serialize)]
pub(crate) struct BrowserSessionSnapshot {
    pub(crate) session_id: String,
    pub(crate) task_id: String,
    pub(crate) environment_id: String,
    pub(crate) scope_id: String,
    pub(crate) transport: String,
    pub(crate) status: String,
    pub(crate) runtime_dir: String,
    pub(crate) display_id: Option<i32>,
    pub(crate) vnc_port: Option<i32>,
    pub(crate) novnc_port: Option<i32>,
    pub(crate) missing_binaries: Vec<String>,
    pub(crate) created_at_ms: u64,
    pub(crate) ended_at_ms: Option<u64>,
    pub(crate) metadata: HashMap<String, String>,
}

impl From<&BrowserSessionRecord> for BrowserSessionSnapshot {
    fn from(value: &BrowserSessionRecord) -> Self {
        Self {
            session_id: value.session_id.clone(),
            task_id: value.task_id.clone(),
            environment_id: value.environment_id.clone(),
            scope_id: value.scope_id.clone(),
            transport: value.transport.clone(),
            status: value.status.clone(),
            runtime_dir: value.runtime_dir.clone(),
            display_id: value.display_id,
            vnc_port: value.vnc_port,
            novnc_port: value.novnc_port,
            missing_binaries: value.missing_binaries.clone(),
            created_at_ms: value.created_at_ms,
            ended_at_ms: value.ended_at_ms,
            metadata: value.metadata.clone(),
        }
    }
}

#[derive(Clone, Debug)]
pub(crate) struct CheckpointRecord {
    pub(crate) checkpoint_id: String,
    pub(crate) task_id: String,
    pub(crate) environment_id: String,
    pub(crate) workspace_path: String,
    pub(crate) success: bool,
    pub(crate) final_phase: String,
    pub(crate) checkpoint_dir: PathBuf,
    pub(crate) manifest_path: PathBuf,
    pub(crate) snapshot_path: PathBuf,
    pub(crate) patch_path: PathBuf,
    pub(crate) git_status_path: PathBuf,
    pub(crate) untracked_bundle_path: PathBuf,
    pub(crate) commit_sha: String,
    pub(crate) has_untracked_bundle: bool,
    pub(crate) created_at_ms: u64,
    pub(crate) expires_at_ms: Option<u64>,
}

#[derive(Serialize)]
pub(crate) struct CheckpointSnapshot {
    pub(crate) checkpoint_id: String,
    pub(crate) task_id: String,
    pub(crate) environment_id: String,
    pub(crate) success: bool,
    pub(crate) final_phase: String,
    pub(crate) checkpoint_dir: String,
    pub(crate) manifest_path: String,
    pub(crate) snapshot_path: String,
    pub(crate) patch_path: String,
    pub(crate) git_status_path: String,
    pub(crate) untracked_bundle_path: String,
    pub(crate) commit_sha: String,
    pub(crate) has_untracked_bundle: bool,
    pub(crate) created_at_ms: u64,
    pub(crate) expires_at_ms: Option<u64>,
}

impl From<&CheckpointRecord> for CheckpointSnapshot {
    fn from(value: &CheckpointRecord) -> Self {
        Self {
            checkpoint_id: value.checkpoint_id.clone(),
            task_id: value.task_id.clone(),
            environment_id: value.environment_id.clone(),
            success: value.success,
            final_phase: value.final_phase.clone(),
            checkpoint_dir: value.checkpoint_dir.display().to_string(),
            manifest_path: value.manifest_path.display().to_string(),
            snapshot_path: value.snapshot_path.display().to_string(),
            patch_path: value.patch_path.display().to_string(),
            git_status_path: value.git_status_path.display().to_string(),
            untracked_bundle_path: value.untracked_bundle_path.display().to_string(),
            commit_sha: value.commit_sha.clone(),
            has_untracked_bundle: value.has_untracked_bundle,
            created_at_ms: value.created_at_ms,
            expires_at_ms: value.expires_at_ms,
        }
    }
}

impl From<&TerminalRecord> for TerminalSnapshot {
    fn from(value: &TerminalRecord) -> Self {
        Self {
            stream: value.stream.clone(),
            data: String::from_utf8_lossy(&value.data).into_owned(),
            eof: value.eof,
            timestamp_ms: value.timestamp_ms,
        }
    }
}

fn serialize_terminal_data<S>(value: &[u8], serializer: S) -> Result<S::Ok, S::Error>
where
    S: serde::Serializer,
{
    serializer.serialize_str(&String::from_utf8_lossy(value))
}
