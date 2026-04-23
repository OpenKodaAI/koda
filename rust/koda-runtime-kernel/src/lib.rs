use std::collections::{BTreeSet, HashMap};
use std::ffi::CString;
use std::fs as stdfs;
use std::fs::File as StdFile;
use std::fs::OpenOptions as StdOpenOptions;
use std::io::{Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs as unix_fs;
use std::path::{Component, Path, PathBuf};
use std::pin::Pin;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, RwLock};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::{anyhow, Result};
use async_stream::try_stream;
use koda_observability::health_details;
use koda_proto::common::v1::{HealthRequest, HealthResponse, RequestMetadata};
use koda_proto::runtime::v1::runtime_kernel_service_server::RuntimeKernelService;
use koda_proto::runtime::v1::{
    AttachTerminalRequest, AttachTerminalResponse, BrowserSessionRef, CheckpointRef,
    CleanupEnvironmentRequest, CleanupEnvironmentResponse, CloseTerminalRequest,
    CloseTerminalResponse, CollectSnapshotRequest, CollectSnapshotResponse,
    CreateEnvironmentRequest, CreateEnvironmentResponse, EnvironmentRef, ExecuteCommandRequest,
    ExecuteCommandResponse, FinalizeTaskRequest, FinalizeTaskResponse, GetBrowserSessionRequest,
    GetBrowserSessionResponse, GetCheckpointRequest, GetCheckpointResponse, OpenTerminalRequest,
    OpenTerminalResponse, PauseTaskRequest, PauseTaskResponse, ProcessRef, ReconcileRequest,
    ReconcileResponse, ResizeTerminalRequest, ResizeTerminalResponse, RestoreCheckpointRequest,
    RestoreCheckpointResponse, ResumeTaskRequest, ResumeTaskResponse, SaveCheckpointRequest,
    SaveCheckpointResponse, StartBrowserSessionRequest, StartBrowserSessionResponse,
    StartTaskRequest, StartTaskResponse, StopBrowserSessionRequest, StopBrowserSessionResponse,
    StreamTerminalRequest, StreamTerminalSessionRequest, TerminalChunk, TerminalSessionRef,
    TerminateTaskRequest, TerminateTaskResponse, WriteTerminalRequest, WriteTerminalResponse,
};
use koda_security_core::{sanitize_env, validate_runtime_path, validate_shell_command};
use serde::Serialize;
use serde_json::{Map, Value};
use tokio::fs;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::process::{Child, Command as TokioCommand};
use tokio::sync::Mutex;
use tokio::task;
use tokio_stream::Stream;
use tonic::{Request, Response, Status};
use tracing::info;

pub type TerminalStream =
    Pin<Box<dyn Stream<Item = Result<TerminalChunk, Status>> + Send + 'static>>;

const SERVICE_NAME: &str = "koda-runtime-kernel";
const AUTHORITY_SCOPE: &str =
    "workspace_lifecycle_plus_process_streaming_plus_interactive_terminal_sessions_plus_browser_sidecars_plus_checkpoint_registry";
const CUTOVER_BLOCKERS: &str = "";
const AUTHORITATIVE_OPERATIONS: &str =
    "create_environment,start_task,execute_command,stream_terminal,open_terminal,write_terminal,resize_terminal,close_terminal,stream_terminal_session,terminate_task,cleanup_environment,start_browser_session,stop_browser_session,get_browser_session,save_checkpoint,get_checkpoint,restore_checkpoint";

#[derive(Clone, Debug)]
pub struct KernelConfig {
    runtime_root: PathBuf,
}

impl KernelConfig {
    pub fn from_env() -> Self {
        let runtime_root = std::env::var("RUNTIME_KERNEL_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("/tmp/koda-runtime/default/kernel"));
        Self { runtime_root }
    }

    pub fn runtime_root(&self) -> &Path {
        &self.runtime_root
    }
}

#[derive(Clone, Debug)]
struct ProvisionedWorkspace {
    workspace_path: String,
    branch_name: String,
    created_worktree: bool,
    worktree_mode: String,
    metadata_path: String,
}

fn truncate_slug(raw: &str) -> String {
    let mut value = raw.trim().to_string();
    if value.is_empty() {
        value = "task".to_string();
    }
    value.chars().take(32).collect()
}

fn is_git_repo(base_work_dir: &Path) -> bool {
    Command::new("git")
        .arg("-C")
        .arg(base_work_dir)
        .arg("rev-parse")
        .arg("--is-inside-work-tree")
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .is_some_and(|stdout| stdout.trim() == "true")
}

fn branch_exists(base_work_dir: &Path, branch_name: &str) -> bool {
    Command::new("git")
        .arg("-C")
        .arg(base_work_dir)
        .arg("show-ref")
        .arg("--verify")
        .arg("--quiet")
        .arg(format!("refs/heads/{branch_name}"))
        .status()
        .is_ok_and(|status| status.success())
}

fn unique_branch_name(base_work_dir: &Path, branch_name: &str) -> String {
    if !branch_exists(base_work_dir, branch_name) {
        return branch_name.to_string();
    }
    let suffix_seed = now_ms();
    for offset in 0..100u64 {
        let candidate = format!("{branch_name}-{}", suffix_seed + offset);
        if !branch_exists(base_work_dir, &candidate) {
            return candidate;
        }
    }
    format!("{branch_name}-{suffix_seed}")
}

fn copy_workspace_recursive(source: &Path, target: &Path) -> Result<()> {
    if target.exists() {
        stdfs::remove_dir_all(target)?;
    }
    stdfs::create_dir_all(target)?;
    for entry in stdfs::read_dir(source)? {
        let entry = entry?;
        let file_name = entry.file_name();
        if file_name.to_string_lossy() == ".git" {
            continue;
        }
        let source_path = entry.path();
        let target_path = target.join(&file_name);
        let file_type = entry.file_type()?;
        if file_type.is_dir() {
            copy_workspace_recursive(&source_path, &target_path)?;
            continue;
        }
        if file_type.is_symlink() {
            let link_target = stdfs::read_link(&source_path)?;
            let _ = stdfs::remove_file(&target_path);
            unix_fs::symlink(link_target, &target_path)?;
            continue;
        }
        if let Some(parent) = target_path.parent() {
            stdfs::create_dir_all(parent)?;
        }
        stdfs::copy(&source_path, &target_path)?;
    }
    Ok(())
}

fn provision_workspace(
    runtime_root: &Path,
    task_id: &str,
    slug: &str,
    base_work_dir: &str,
    create_worktree: bool,
) -> Result<ProvisionedWorkspace> {
    let base_path = PathBuf::from(base_work_dir).canonicalize()?;
    let safe_slug = truncate_slug(slug);
    let workspace_path = runtime_root
        .join("worktrees")
        .join(format!("task-{task_id}-{safe_slug}"));
    let metadata_path = runtime_root
        .join("tasks")
        .join(task_id)
        .join("worktree.json");
    if let Some(parent) = metadata_path.parent() {
        stdfs::create_dir_all(parent)?;
    }
    let mut branch_name = format!("task/{task_id}-{safe_slug}");
    let mut mode = "shared".to_string();
    let mut created = false;
    let mut resolved_workspace_path = base_path.clone();

    if create_worktree {
        if is_git_repo(&base_path) {
            branch_name = unique_branch_name(&base_path, &branch_name);
            if workspace_path.exists() {
                stdfs::remove_dir_all(&workspace_path)?;
            }
            let result = Command::new("git")
                .arg("-C")
                .arg(&base_path)
                .arg("worktree")
                .arg("add")
                .arg("-b")
                .arg(&branch_name)
                .arg(&workspace_path)
                .output()?;
            if result.status.success() {
                mode = "worktree".to_string();
                created = true;
                resolved_workspace_path = workspace_path.clone();
            } else {
                copy_workspace_recursive(&base_path, &workspace_path)?;
                mode = "copy_fallback".to_string();
                created = true;
                resolved_workspace_path = workspace_path.clone();
            }
        } else {
            copy_workspace_recursive(&base_path, &workspace_path)?;
            mode = "copy".to_string();
            created = true;
            resolved_workspace_path = workspace_path.clone();
        }
    }

    let metadata = serde_json::json!({
        "workspace_path": resolved_workspace_path.display().to_string(),
        "branch_name": branch_name,
        "created": created,
        "mode": mode,
        "base_work_dir": base_path.display().to_string(),
    });
    stdfs::write(&metadata_path, serde_json::to_vec_pretty(&metadata)?)?;

    Ok(ProvisionedWorkspace {
        workspace_path: resolved_workspace_path.display().to_string(),
        branch_name,
        created_worktree: created,
        worktree_mode: mode,
        metadata_path: metadata_path.display().to_string(),
    })
}

fn cleanup_workspace(workspace_path: &str, created_worktree: bool) -> Result<bool> {
    let path = PathBuf::from(workspace_path);
    if !created_worktree || !path.exists() {
        return Ok(false);
    }
    let git_dir = path.join(".git");
    if git_dir.exists() {
        let result = Command::new("git")
            .arg("-C")
            .arg(&path)
            .arg("worktree")
            .arg("remove")
            .arg("--force")
            .arg(&path)
            .output()?;
        if result.status.success() {
            return Ok(true);
        }
    }
    stdfs::remove_dir_all(&path)?;
    Ok(true)
}

#[derive(Clone)]
pub struct RuntimeKernelServer {
    config: KernelConfig,
    state: Arc<RwLock<KernelState>>,
    process_handles: Arc<Mutex<HashMap<String, ManagedProcessHandle>>>,
    terminal_handles: Arc<Mutex<HashMap<String, ManagedTerminalHandle>>>,
    browser_handles: Arc<Mutex<HashMap<String, ManagedBrowserSessionHandle>>>,
    next_process_id: Arc<AtomicU64>,
    next_terminal_session_id: Arc<AtomicU64>,
    next_browser_session_id: Arc<AtomicU64>,
    next_checkpoint_id: Arc<AtomicU64>,
}

impl RuntimeKernelServer {
    pub fn new(config: KernelConfig) -> Self {
        Self {
            config,
            state: Arc::new(RwLock::new(KernelState::new())),
            process_handles: Arc::new(Mutex::new(HashMap::new())),
            terminal_handles: Arc::new(Mutex::new(HashMap::new())),
            browser_handles: Arc::new(Mutex::new(HashMap::new())),
            next_process_id: Arc::new(AtomicU64::new(1)),
            next_terminal_session_id: Arc::new(AtomicU64::new(1)),
            next_browser_session_id: Arc::new(AtomicU64::new(1)),
            next_checkpoint_id: Arc::new(AtomicU64::new(1)),
        }
    }

    pub fn config(&self) -> &KernelConfig {
        &self.config
    }

    fn build_environment_ref(record: &EnvironmentRecord) -> EnvironmentRef {
        EnvironmentRef {
            environment_id: record.environment_id.clone(),
            task_id: record.task_id.clone(),
            agent_id: record.agent_id.clone(),
        }
    }

    #[allow(clippy::result_large_err)]
    fn require_task<'a>(
        state: &'a mut KernelState,
        task_id: &str,
    ) -> Result<&'a mut TaskRecord, Status> {
        state
            .tasks
            .get_mut(task_id)
            .ok_or_else(|| Status::not_found(format!("task not found: {task_id}")))
    }

    fn append_terminal_line(
        state: &mut KernelState,
        task_id: &str,
        stream: &str,
        line: String,
        eof: bool,
    ) {
        Self::append_terminal_bytes(state, task_id, stream, line.into_bytes(), eof);
    }

    fn append_terminal_bytes(
        state: &mut KernelState,
        task_id: &str,
        stream: &str,
        data: Vec<u8>,
        eof: bool,
    ) {
        state
            .terminal_history
            .entry(task_id.to_string())
            .or_default()
            .push(TerminalRecord {
                stream: stream.to_string(),
                data,
                eof,
                timestamp_ms: now_ms(),
            });
        if let Some(task) = state.tasks.get_mut(task_id) {
            if stream == "stdout" {
                task.stdout_eof = eof;
            } else if stream == "stderr" {
                task.stderr_eof = eof;
            }
            if eof && task.stdout_eof && task.stderr_eof {
                task.terminal_closed_at_ms = Some(now_ms());
            }
        }
    }

    fn environment_root(&self, agent_id: &str, task_id: &str, environment_id: &str) -> PathBuf {
        self.config
            .runtime_root()
            .join(agent_id)
            .join(task_id)
            .join(environment_id)
    }

    fn next_process_id(&self) -> String {
        let id = self.next_process_id.fetch_add(1, Ordering::Relaxed);
        format!("proc-{id}")
    }

    fn next_browser_session_id(&self) -> String {
        let id = self.next_browser_session_id.fetch_add(1, Ordering::Relaxed);
        format!("browser-{id}")
    }

    fn next_terminal_session_id(&self) -> String {
        let id = self
            .next_terminal_session_id
            .fetch_add(1, Ordering::Relaxed);
        format!("terminal-{id}")
    }

    fn next_checkpoint_id(&self) -> String {
        let id = self.next_checkpoint_id.fetch_add(1, Ordering::Relaxed);
        format!("ckpt-{id}")
    }

    fn build_browser_session_ref(record: &BrowserSessionRecord) -> BrowserSessionRef {
        BrowserSessionRef {
            session_id: record.session_id.clone(),
            task_id: record.task_id.clone(),
            environment_id: record.environment_id.clone(),
            scope_id: record.scope_id.clone(),
            transport: record.transport.clone(),
            status: record.status.clone(),
            runtime_dir: record.runtime_dir.clone(),
            display_id: record.display_id.unwrap_or_default(),
            vnc_port: record.vnc_port.unwrap_or_default(),
            novnc_port: record.novnc_port.unwrap_or_default(),
            missing_binaries: record.missing_binaries.clone(),
            created_at_ms: record.created_at_ms,
            ended_at_ms: record.ended_at_ms.unwrap_or_default(),
            metadata: record.metadata.clone(),
        }
    }

    fn build_checkpoint_ref(record: &CheckpointRecord) -> CheckpointRef {
        CheckpointRef {
            checkpoint_id: record.checkpoint_id.clone(),
            task_id: record.task_id.clone(),
            environment_id: record.environment_id.clone(),
            success: record.success,
            final_phase: record.final_phase.clone(),
            checkpoint_dir: record.checkpoint_dir.display().to_string(),
            manifest_path: record.manifest_path.display().to_string(),
            snapshot_path: record.snapshot_path.display().to_string(),
            patch_path: record.patch_path.display().to_string(),
            git_status_path: record.git_status_path.display().to_string(),
            untracked_bundle_path: record.untracked_bundle_path.display().to_string(),
            commit_sha: record.commit_sha.clone(),
            has_untracked_bundle: record.has_untracked_bundle,
            created_at_ms: record.created_at_ms,
            expires_at_ms: record.expires_at_ms.unwrap_or_default(),
        }
    }

    fn build_process_ref(record: &TaskRecord) -> Option<ProcessRef> {
        let process_id = record.process_id.clone()?;
        Some(ProcessRef {
            process_id,
            task_id: record.task_id.clone(),
            environment_id: record.environment_id.clone(),
            pid: record.pid.unwrap_or_default(),
            pgid: record.pgid.unwrap_or_default(),
            command: record.command.clone(),
            args: record.args.clone(),
            status: record.process_status.clone(),
            started_at_ms: record.started_at_ms.unwrap_or_default(),
            exit_code: record.exit_code.unwrap_or_default(),
        })
    }

    fn build_terminal_ref(record: &TaskRecord, stream: &str) -> Option<TerminalSessionRef> {
        let (session_id, eof, opened_at_ms, closed_at_ms) = if stream == "stdout" {
            (
                record.stdout_terminal_id.clone()?,
                record.stdout_eof,
                record.started_at_ms.unwrap_or_default(),
                record.terminal_closed_at_ms.unwrap_or_default(),
            )
        } else {
            (
                record.stderr_terminal_id.clone()?,
                record.stderr_eof,
                record.started_at_ms.unwrap_or_default(),
                record.terminal_closed_at_ms.unwrap_or_default(),
            )
        };
        Some(TerminalSessionRef {
            session_id,
            task_id: record.task_id.clone(),
            stream: stream.to_string(),
            status: if eof {
                "closed".to_string()
            } else {
                "open".to_string()
            },
            eof,
            opened_at_ms,
            closed_at_ms,
        })
    }

    fn build_interactive_terminal_ref(record: &InteractiveTerminalRecord) -> TerminalSessionRef {
        TerminalSessionRef {
            session_id: record.session_id.clone(),
            task_id: record.task_id.clone(),
            stream: "interactive".to_string(),
            status: record.status.clone(),
            eof: record.eof,
            opened_at_ms: record.opened_at_ms,
            closed_at_ms: record.closed_at_ms.unwrap_or_default(),
        }
    }

    fn build_interactive_terminal_process_ref(record: &InteractiveTerminalRecord) -> ProcessRef {
        ProcessRef {
            process_id: format!("tty-{}", record.session_id),
            task_id: record.task_id.clone(),
            environment_id: record.environment_id.clone(),
            pid: record.pid.unwrap_or_default(),
            pgid: record.pgid.unwrap_or_default(),
            command: record.command.clone(),
            args: record.args.clone(),
            status: record.status.clone(),
            started_at_ms: record.opened_at_ms,
            exit_code: record.exit_code.unwrap_or_default(),
        }
    }

    fn runtime_health_response(&self) -> HealthResponse {
        let state = self.state.read().expect("kernel state poisoned");
        let mut details = health_details(SERVICE_NAME);
        details.insert("startup_phase".to_string(), "ready".to_string());
        details.insert(
            "runtime_root".to_string(),
            self.config.runtime_root().display().to_string(),
        );
        details.insert(
            "active_environments".to_string(),
            state.active_environment_count().to_string(),
        );
        details.insert(
            "known_environments".to_string(),
            state.environments.len().to_string(),
        );
        details.insert("known_tasks".to_string(), state.tasks.len().to_string());
        details.insert(
            "known_interactive_terminals".to_string(),
            state.interactive_terminals.len().to_string(),
        );
        details.insert(
            "known_browser_sessions".to_string(),
            state.browser_sessions.len().to_string(),
        );
        details.insert(
            "known_checkpoints".to_string(),
            state.checkpoints.len().to_string(),
        );
        details.insert(
            "last_reconcile_at_ms".to_string(),
            state
                .last_reconcile_at_ms
                .map(|value| value.to_string())
                .unwrap_or_else(|| "0".to_string()),
        );
        details.insert(
            "uptime_ms".to_string(),
            now_ms().saturating_sub(state.started_at_ms).to_string(),
        );
        details.insert(
            "terminal_records".to_string(),
            state
                .terminal_history
                .values()
                .map(std::vec::Vec::len)
                .sum::<usize>()
                .to_string(),
        );
        details.insert("authoritative".to_string(), "true".to_string());
        details.insert("production_ready".to_string(), "true".to_string());
        details.insert("maturity".to_string(), "ga".to_string());
        details.insert("authority_scope".to_string(), AUTHORITY_SCOPE.to_string());
        details.insert(
            "authoritative_operations".to_string(),
            AUTHORITATIVE_OPERATIONS.to_string(),
        );
        details.insert("full_authority".to_string(), "true".to_string());
        details.insert("partial_authority".to_string(), "false".to_string());
        details.insert("cutover_blockers".to_string(), CUTOVER_BLOCKERS.to_string());
        details.insert(
            "capabilities".to_string(),
            "workspace-provisioning,workspace-cleanup,environment-tracking,process-spawn,command-execution,terminal-streaming,interactive-terminal-sessions,terminal-input-write,terminal-resize,signal-termination,browser-session-registry,checkpoint-persistence,checkpoint-retrieval,checkpoint-restore,snapshot-collection,reconcile"
                .to_string(),
        );
        HealthResponse {
            service: SERVICE_NAME.to_string(),
            ready: true,
            status: if state.active_environment_count() > 0 {
                "running".to_string()
            } else {
                "idle".to_string()
            },
            details,
        }
    }

    async fn ensure_environment_root(&self, root: &Path) -> Result<(), Status> {
        fs::create_dir_all(root)
            .await
            .map_err(|error| Status::internal(format!("failed to create runtime root: {error}")))?;
        fs::create_dir_all(root.join("terminal"))
            .await
            .map_err(|error| {
                Status::internal(format!("failed to create terminal root: {error}"))
            })?;
        fs::create_dir_all(root.join("snapshots"))
            .await
            .map_err(|error| {
                Status::internal(format!("failed to create snapshot root: {error}"))
            })?;
        Ok(())
    }
}

#[derive(Clone)]
struct ManagedProcessHandle {
    task_id: String,
    child: Arc<Mutex<Child>>,
}

#[derive(Clone)]
struct ManagedTerminalHandle {
    master: Arc<Mutex<Option<StdFile>>>,
    pid: i32,
    pgid: i32,
}

#[derive(Clone)]
struct ManagedBrowserSessionHandle {
    children: Vec<Arc<Mutex<Child>>>,
}

fn metadata_label(metadata: Option<&RequestMetadata>, key: &str) -> Option<String> {
    metadata
        .and_then(|item| item.labels.get(key))
        .map(std::string::ToString::to_string)
}

fn metadata_bool(metadata: Option<&RequestMetadata>, key: &str, default: bool) -> bool {
    metadata_label(metadata, key)
        .map(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(default)
}

fn default_shell_command() -> String {
    for candidate in [
        std::env::var("SHELL").ok(),
        Some("/bin/zsh".to_string()),
        Some("/bin/bash".to_string()),
        Some("/bin/sh".to_string()),
    ] {
        let Some(command) = candidate else {
            continue;
        };
        if !command.is_empty() && Path::new(&command).exists() {
            return command;
        }
    }
    "/bin/sh".to_string()
}

fn default_shell_args(command: &str) -> Vec<String> {
    let shell_name = Path::new(command)
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or_default();
    if matches!(shell_name, "sh" | "bash" | "zsh") {
        vec!["-i".to_string()]
    } else {
        Vec::new()
    }
}

#[allow(clippy::result_large_err)]
fn normalize_working_directory(value: &str) -> Result<Option<PathBuf>, Status> {
    let normalized = validate_runtime_path(value, true)
        .map_err(|error| Status::invalid_argument(error.to_string()))?;
    if normalized.is_empty() {
        return Ok(None);
    }
    let path = Path::new(&normalized)
        .canonicalize()
        .map_err(|error| Status::invalid_argument(format!("invalid working directory: {error}")))?;
    if !path.is_dir() {
        return Err(Status::invalid_argument(
            "working directory must be a directory",
        ));
    }
    Ok(Some(path))
}

#[allow(clippy::result_large_err)]
fn sanitize_command_environment(
    environment_overrides: &HashMap<String, String>,
) -> Result<HashMap<String, String>, Status> {
    let base_env: Map<String, Value> = std::env::vars()
        .map(|(key, value)| (key, Value::String(value)))
        .collect();
    let overrides: Map<String, Value> = environment_overrides
        .iter()
        .map(|(key, value)| (key.clone(), Value::String(value.clone())))
        .collect();
    Ok(sanitize_env(&base_env, &[], &overrides)
        .into_iter()
        .filter_map(|(key, value)| value.as_str().map(|inner| (key, inner.to_string())))
        .collect())
}

async fn read_to_end_bytes<R>(mut reader: R) -> Result<Vec<u8>, std::io::Error>
where
    R: tokio::io::AsyncRead + Unpin + Send + 'static,
{
    let mut buffer = Vec::new();
    reader.read_to_end(&mut buffer).await?;
    Ok(buffer)
}

#[derive(Debug, Clone)]
struct ExecutedCommandOutcome {
    stdout: Vec<u8>,
    stderr: Vec<u8>,
    exit_code: i32,
    timed_out: bool,
    killed: bool,
    started_at_ms: u64,
    finished_at_ms: u64,
}

async fn execute_shell_command(
    command: &str,
    argv: &[String],
    working_directory: &str,
    environment_overrides: &HashMap<String, String>,
    stdin_payload: &[u8],
    timeout_seconds: u32,
    start_new_session: bool,
) -> Result<ExecutedCommandOutcome, Status> {
    let validated_command = validate_shell_command(command)
        .map_err(|error| Status::invalid_argument(error.to_string()))?;
    if validated_command.trim().is_empty() {
        return Err(Status::invalid_argument("command is required"));
    }
    let mut command_builder = if argv.is_empty() {
        let shell = default_shell_command();
        let mut builder = TokioCommand::new(shell);
        builder.arg("-lc").arg(validated_command);
        builder
    } else {
        let mut builder = TokioCommand::new(validated_command);
        builder.args(argv);
        builder
    };
    if let Some(cwd) = normalize_working_directory(working_directory)? {
        command_builder.current_dir(cwd);
    }
    command_builder.env_clear();
    let sanitized_env = sanitize_command_environment(environment_overrides)?;
    command_builder.envs(sanitized_env);
    command_builder.stdin(std::process::Stdio::piped());
    command_builder.stdout(std::process::Stdio::piped());
    command_builder.stderr(std::process::Stdio::piped());
    if start_new_session {
        unsafe {
            command_builder.pre_exec(|| {
                if libc::setpgid(0, 0) != 0 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }
    }

    let started_at_ms = now_ms();
    let mut child = command_builder.spawn().map_err(|error| {
        Status::internal(format!(
            "failed to spawn runtime command execution: {error}"
        ))
    })?;
    let pid = child
        .id()
        .map(|value| i32::try_from(value).unwrap_or_default())
        .unwrap_or_default();
    let pgid = if start_new_session { pid } else { 0 };
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| Status::internal("spawned command missing stdout pipe"))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| Status::internal("spawned command missing stderr pipe"))?;
    if let Some(mut stdin) = child.stdin.take() {
        let payload = stdin_payload.to_vec();
        tokio::spawn(async move {
            let _ = stdin.write_all(&payload).await;
            let _ = stdin.shutdown().await;
        });
    }
    let stdout_task = tokio::spawn(read_to_end_bytes(stdout));
    let stderr_task = tokio::spawn(read_to_end_bytes(stderr));
    let timeout = Duration::from_secs(u64::from(timeout_seconds.max(1)));
    let mut timed_out = false;
    let mut killed = false;
    let exit_code = match tokio::time::timeout(timeout, child.wait()).await {
        Ok(result) => match result {
            Ok(status) => status.code().unwrap_or_default(),
            Err(error) => {
                return Err(Status::internal(format!(
                    "runtime command wait failed: {error}"
                )));
            }
        },
        Err(_) => {
            timed_out = true;
            killed = true;
            let _ = send_process_signal(Some(pgid), Some(pid), libc::SIGTERM);
            if tokio::time::timeout(Duration::from_secs(2), child.wait())
                .await
                .is_err()
            {
                let _ = child.start_kill();
                let _ = child.wait().await;
            }
            124
        }
    };
    let stdout = stdout_task
        .await
        .map_err(|error| Status::internal(format!("failed to join stdout reader: {error}")))?
        .map_err(|error| Status::internal(format!("failed to read stdout: {error}")))?;
    let stderr = stderr_task
        .await
        .map_err(|error| Status::internal(format!("failed to join stderr reader: {error}")))?
        .map_err(|error| Status::internal(format!("failed to read stderr: {error}")))?;
    Ok(ExecutedCommandOutcome {
        stdout,
        stderr,
        exit_code,
        timed_out,
        killed,
        started_at_ms,
        finished_at_ms: now_ms(),
    })
}

fn append_interactive_terminal_bytes(
    state: &mut KernelState,
    session_id: &str,
    stream: &str,
    data: Vec<u8>,
    eof: bool,
) {
    state
        .interactive_terminal_history
        .entry(session_id.to_string())
        .or_default()
        .push(TerminalRecord {
            stream: stream.to_string(),
            data,
            eof,
            timestamp_ms: now_ms(),
        });
    if let Some(session) = state.interactive_terminals.get_mut(session_id) {
        if eof {
            session.eof = true;
            session.closed_at_ms.get_or_insert(now_ms());
        }
    }
}

fn append_interactive_terminal_line(
    state: &mut KernelState,
    session_id: &str,
    stream: &str,
    line: String,
    eof: bool,
) {
    append_interactive_terminal_bytes(state, session_id, stream, line.into_bytes(), eof);
}

fn build_checkpoint_archive_path(checkpoint_dir: &Path, name: &str) -> PathBuf {
    checkpoint_dir.join(name)
}

fn set_fd_nonblocking(fd: libc::c_int) -> Result<(), String> {
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    if flags < 0 {
        return Err(format!(
            "failed to read file descriptor flags: {}",
            std::io::Error::last_os_error()
        ));
    }
    let result = unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) };
    if result < 0 {
        return Err(format!(
            "failed to set non-blocking terminal fd: {}",
            std::io::Error::last_os_error()
        ));
    }
    Ok(())
}

async fn pump_terminal_stream<R>(
    state: Arc<RwLock<KernelState>>,
    task_id: String,
    stream: String,
    mut reader: R,
) where
    R: tokio::io::AsyncRead + Unpin + Send + 'static,
{
    let mut buffer = [0u8; 4096];
    loop {
        match reader.read(&mut buffer).await {
            Ok(0) => break,
            Ok(read) => {
                let mut state = state.write().expect("kernel state poisoned");
                RuntimeKernelServer::append_terminal_bytes(
                    &mut state,
                    &task_id,
                    &stream,
                    buffer[..read].to_vec(),
                    false,
                );
            }
            Err(error) => {
                let mut state = state.write().expect("kernel state poisoned");
                RuntimeKernelServer::append_terminal_line(
                    &mut state,
                    &task_id,
                    "system",
                    format!("terminal read error stream={stream} error={error}"),
                    false,
                );
                break;
            }
        }
    }
    let mut state = state.write().expect("kernel state poisoned");
    RuntimeKernelServer::append_terminal_bytes(&mut state, &task_id, &stream, Vec::new(), true);
}

fn spawn_interactive_terminal_process(
    command: &str,
    args: &[String],
    working_directory: &str,
    environment_overrides: &HashMap<String, String>,
    cols: u32,
    rows: u32,
) -> Result<(StdFile, i32, i32), String> {
    let command_c = CString::new(command.as_bytes())
        .map_err(|error| format!("invalid terminal command: {error}"))?;
    let arg_values = if args.is_empty() {
        default_shell_args(command)
    } else {
        args.to_vec()
    };
    let mut argv_cstrings = Vec::with_capacity(arg_values.len() + 1);
    argv_cstrings.push(command_c.clone());
    for arg in &arg_values {
        argv_cstrings.push(
            CString::new(arg.as_bytes())
                .map_err(|error| format!("invalid terminal arg: {error}"))?,
        );
    }
    let mut argv: Vec<*const libc::c_char> =
        argv_cstrings.iter().map(|item| item.as_ptr()).collect();
    argv.push(std::ptr::null());
    let working_dir_c = if working_directory.is_empty() {
        None
    } else {
        Some(
            CString::new(working_directory.as_bytes())
                .map_err(|error| format!("invalid terminal working directory: {error}"))?,
        )
    };
    let env_pairs: Result<Vec<(CString, CString)>, String> = environment_overrides
        .iter()
        .map(|(key, value)| {
            Ok((
                CString::new(key.as_bytes())
                    .map_err(|error| format!("invalid env key: {error}"))?,
                CString::new(value.as_bytes())
                    .map_err(|error| format!("invalid env value: {error}"))?,
            ))
        })
        .collect();
    let env_pairs = env_pairs?;

    let mut master_fd: libc::c_int = -1;
    let mut slave_fd: libc::c_int = -1;
    let mut winsize = libc::winsize {
        ws_row: u16::try_from(rows.max(1)).unwrap_or(u16::MAX),
        ws_col: u16::try_from(cols.max(1)).unwrap_or(u16::MAX),
        ws_xpixel: 0,
        ws_ypixel: 0,
    };
    let winsize_ptr = std::ptr::from_mut(&mut winsize);
    let openpty_result = unsafe {
        libc::openpty(
            &mut master_fd,
            &mut slave_fd,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            winsize_ptr,
        )
    };
    if openpty_result != 0 {
        return Err(format!(
            "openpty failed: {}",
            std::io::Error::last_os_error()
        ));
    }

    let pid = unsafe { libc::fork() };
    if pid < 0 {
        unsafe {
            libc::close(master_fd);
            libc::close(slave_fd);
        }
        return Err(format!("fork failed: {}", std::io::Error::last_os_error()));
    }

    if pid == 0 {
        unsafe {
            let _ = libc::setsid();
            let tiocsctty_request = libc::TIOCSCTTY as libc::c_ulong;
            let _ = libc::ioctl(slave_fd, tiocsctty_request, 0);
            libc::dup2(slave_fd, libc::STDIN_FILENO);
            libc::dup2(slave_fd, libc::STDOUT_FILENO);
            libc::dup2(slave_fd, libc::STDERR_FILENO);
            libc::close(master_fd);
            if slave_fd > libc::STDERR_FILENO {
                libc::close(slave_fd);
            }
            if let Some(ref cwd) = working_dir_c {
                let _ = libc::chdir(cwd.as_ptr());
            }
            for (key, value) in &env_pairs {
                let _ = libc::setenv(key.as_ptr(), value.as_ptr(), 1);
            }
            libc::execvp(command_c.as_ptr(), argv.as_ptr());
            libc::_exit(127);
        }
    }

    unsafe {
        libc::close(slave_fd);
    }
    let pgid = pid;
    let master_file = unsafe { StdFile::from_raw_fd(master_fd) };
    Ok((master_file, pid, pgid))
}

async fn pump_interactive_terminal_session(
    state: Arc<RwLock<KernelState>>,
    session_id: String,
    task_id: String,
    mut reader: StdFile,
) {
    let _ = set_fd_nonblocking(reader.as_raw_fd());
    let _ = task::spawn_blocking(move || {
        let mut buffer = [0u8; 4096];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) => break,
                Ok(read) => {
                    let mut state = state.write().expect("kernel state poisoned");
                    append_interactive_terminal_bytes(
                        &mut state,
                        &session_id,
                        "interactive",
                        buffer[..read].to_vec(),
                        false,
                    );
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    let should_stop = {
                        let state = state.read().expect("kernel state poisoned");
                        state
                            .interactive_terminals
                            .get(&session_id)
                            .is_none_or(|session| {
                                session.eof
                                    || matches!(session.status.as_str(), "closed" | "failed")
                            })
                    };
                    if should_stop {
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(20));
                }
                Err(error) => {
                    let mut state = state.write().expect("kernel state poisoned");
                    append_interactive_terminal_line(
                        &mut state,
                        &session_id,
                        "system",
                        format!("interactive terminal read error task={task_id} error={error}"),
                        false,
                    );
                    break;
                }
            }
        }
        let mut state = state.write().expect("kernel state poisoned");
        append_interactive_terminal_bytes(&mut state, &session_id, "interactive", Vec::new(), true);
    })
    .await;
}

async fn wait_for_interactive_terminal_process(
    state: Arc<RwLock<KernelState>>,
    terminal_handles: Arc<Mutex<HashMap<String, ManagedTerminalHandle>>>,
    session_id: String,
    pid: i32,
) {
    let session_id_for_wait = session_id.clone();
    let _ = task::spawn_blocking(move || {
        let mut wait_status: libc::c_int = 0;
        let wait_result = unsafe { libc::waitpid(pid, &mut wait_status, 0) };
        let (exit_code, success) = if wait_result < 0 {
            (-1, false)
        } else if libc::WIFEXITED(wait_status) {
            (libc::WEXITSTATUS(wait_status), true)
        } else if libc::WIFSIGNALED(wait_status) {
            (128 + libc::WTERMSIG(wait_status), false)
        } else {
            (-1, false)
        };
        let mut state = state.write().expect("kernel state poisoned");
        if let Some(session) = state.interactive_terminals.get_mut(&session_id_for_wait) {
            session.status = if success {
                "closed".to_string()
            } else {
                "failed".to_string()
            };
            session.eof = true;
            session.exit_code = Some(exit_code);
            session.closed_at_ms = Some(now_ms());
        }
        append_interactive_terminal_line(
            &mut state,
            &session_id_for_wait,
            "system",
            format!("interactive terminal exited exit_code={exit_code}"),
            true,
        );
    })
    .await;
    let mut handles = terminal_handles.lock().await;
    handles.remove(&session_id);
}

async fn close_managed_terminal_session(
    terminal_handles: Arc<Mutex<HashMap<String, ManagedTerminalHandle>>>,
    session_id: &str,
    force: bool,
) -> bool {
    let handle = {
        let handles = terminal_handles.lock().await;
        handles.get(session_id).cloned()
    };
    let Some(handle) = handle else {
        return false;
    };
    {
        let mut master = handle.master.lock().await;
        if let Some(master_file) = master.as_mut() {
            let _ = master_file.flush();
        }
    }
    if force {
        send_process_signal(Some(handle.pgid), Some(handle.pid), libc::SIGKILL)
    } else {
        let terminated = send_process_signal(Some(handle.pgid), Some(handle.pid), libc::SIGTERM);
        let hup = send_process_signal(Some(handle.pgid), Some(handle.pid), libc::SIGHUP);
        terminated || hup
    }
}

async fn wait_for_managed_process(
    state: Arc<RwLock<KernelState>>,
    process_handles: Arc<Mutex<HashMap<String, ManagedProcessHandle>>>,
    task_id: String,
    child: Arc<Mutex<Child>>,
) {
    let exit_status = {
        let mut child = child.lock().await;
        child.wait().await.ok()
    };
    let exit_code = exit_status
        .and_then(|status| status.code())
        .unwrap_or_default();
    {
        let mut state = state.write().expect("kernel state poisoned");
        let environment_id = if let Some(task) = state.tasks.get_mut(&task_id) {
            task.process_status = if exit_code == 0 {
                "exited".to_string()
            } else {
                "failed".to_string()
            };
            task.process_running = false;
            task.exit_code = Some(exit_code);
            task.last_updated_at_ms = now_ms();
            task.environment_id.clone()
        } else {
            String::new()
        };
        if let Some(environment) = state.environments.get_mut(&environment_id) {
            environment.last_updated_at_ms = now_ms();
        }
        RuntimeKernelServer::append_terminal_line(
            &mut state,
            &task_id,
            "system",
            format!("process exited exit_code={exit_code}"),
            false,
        );
    }
    let mut handles = process_handles.lock().await;
    handles.remove(&task_id);
}

fn send_process_signal(pgid: Option<i32>, pid: Option<i32>, signal: i32) -> bool {
    if let Some(group_id) = pgid {
        let result = unsafe { libc::killpg(group_id, signal) };
        if result == 0 {
            return true;
        }
    }
    if let Some(process_id) = pid {
        let result = unsafe { libc::kill(process_id, signal) };
        if result == 0 {
            return true;
        }
    }
    false
}

fn resolve_binary_path(name: &str) -> Option<PathBuf> {
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
fn open_browser_log(runtime_dir: &Path, name: &str) -> Result<std::process::Stdio, Status> {
    let file = StdOpenOptions::new()
        .create(true)
        .append(true)
        .open(runtime_dir.join(format!("{name}.log")))
        .map_err(|error| Status::internal(format!("failed to open browser log {name}: {error}")))?;
    Ok(std::process::Stdio::from(file))
}

async fn stop_managed_browser_session(
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

#[tonic::async_trait]
impl RuntimeKernelService for RuntimeKernelServer {
    type StreamTerminalStream = TerminalStream;
    type StreamTerminalSessionStream = TerminalStream;

    async fn create_environment(
        &self,
        request: Request<CreateEnvironmentRequest>,
    ) -> Result<Response<CreateEnvironmentResponse>, Status> {
        let payload = request.into_inner();
        let agent_id = non_empty_or(
            payload.agent_id,
            payload.metadata.as_ref().map(|item| item.agent_id.clone()),
        );
        if agent_id.is_empty() {
            return Err(Status::invalid_argument("agent_id is required"));
        }
        if payload.task_id.is_empty() {
            return Err(Status::invalid_argument("task_id is required"));
        }

        let environment_id = format!("env-{}", payload.task_id);
        let runtime_root = self.environment_root(&agent_id, &payload.task_id, &environment_id);
        self.ensure_environment_root(&runtime_root).await?;
        let provisioned = if !payload.base_work_dir.is_empty() {
            task::spawn_blocking({
                let kernel_runtime_root = self.config.runtime_root().to_path_buf();
                let task_id = payload.task_id.clone();
                let slug = payload.slug.clone();
                let base_work_dir = payload.base_work_dir.clone();
                let create_worktree = payload.create_worktree;
                move || {
                    provision_workspace(
                        &kernel_runtime_root,
                        &task_id,
                        &slug,
                        &base_work_dir,
                        create_worktree,
                    )
                }
            })
            .await
            .map_err(|error| {
                Status::internal(format!("workspace provision join failure: {error}"))
            })?
            .map_err(|error| Status::internal(format!("workspace provision failed: {error}")))?
        } else {
            ProvisionedWorkspace {
                workspace_path: payload.workspace_path.clone(),
                branch_name: payload.worktree_ref.clone(),
                created_worktree: false,
                worktree_mode: "shared".to_string(),
                metadata_path: String::new(),
            }
        };

        let mut state = self.state.write().expect("kernel state poisoned");
        let record = EnvironmentRecord {
            environment_id: environment_id.clone(),
            task_id: payload.task_id.clone(),
            agent_id: agent_id.clone(),
            workspace_path: provisioned.workspace_path.clone(),
            worktree_ref: if provisioned.branch_name.is_empty() {
                provisioned.worktree_mode.clone()
            } else {
                provisioned.branch_name.clone()
            },
            branch_name: provisioned.branch_name.clone(),
            created_worktree: provisioned.created_worktree,
            worktree_mode: provisioned.worktree_mode.clone(),
            metadata_path: provisioned.metadata_path.clone(),
            runtime_root: runtime_root.clone(),
            created_at_ms: now_ms(),
            last_updated_at_ms: now_ms(),
            active: true,
            terminal_phase: "created".to_string(),
        };
        let task_id = record.task_id.clone();
        state
            .environments
            .insert(environment_id.clone(), record.clone());
        state
            .task_to_environment
            .insert(task_id.clone(), environment_id.clone());
        state
            .tasks
            .entry(task_id.clone())
            .or_insert_with(|| TaskRecord {
                task_id: task_id.clone(),
                agent_id: agent_id.clone(),
                environment_id: environment_id.clone(),
                phase: "created".to_string(),
                process_id: None,
                pid: None,
                pgid: None,
                process_status: "idle".to_string(),
                process_running: false,
                exit_code: None,
                command: String::new(),
                args: Vec::new(),
                created_at_ms: now_ms(),
                last_updated_at_ms: now_ms(),
                started_at_ms: None,
                finalized_at_ms: None,
                pause_reason: None,
                finalize_error: None,
                sessions: BTreeSet::new(),
                stdout_terminal_id: None,
                stderr_terminal_id: None,
                stdout_eof: false,
                stderr_eof: false,
                terminal_closed_at_ms: None,
                metadata: payload.metadata.clone(),
            });
        Self::append_terminal_line(
            &mut state,
            &task_id,
            "system",
            format!(
                "environment created agent_id={agent_id} workspace={} worktree={}",
                empty_to_dash(&provisioned.workspace_path),
                empty_to_dash(&record.worktree_ref)
            ),
            false,
        );

        Ok(Response::new(CreateEnvironmentResponse {
            environment: Some(Self::build_environment_ref(&record)),
            runtime_root: runtime_root.display().to_string(),
            workspace_path: provisioned.workspace_path,
            branch_name: provisioned.branch_name,
            created_worktree: provisioned.created_worktree,
            worktree_mode: provisioned.worktree_mode,
            metadata_path: provisioned.metadata_path,
        }))
    }

    async fn start_task(
        &self,
        request: Request<StartTaskRequest>,
    ) -> Result<Response<StartTaskResponse>, Status> {
        let payload = request.into_inner();
        if payload.task_id.is_empty() {
            return Err(Status::invalid_argument("task_id is required"));
        }

        let process_id = self.next_process_id();
        let command = payload.command.clone();
        let args = payload.args.clone();
        let working_directory = if payload.working_directory.is_empty() {
            metadata_label(payload.metadata.as_ref(), "working_directory").unwrap_or_default()
        } else {
            payload.working_directory.clone()
        };
        let stdin_payload = if payload.stdin_payload.is_empty() {
            metadata_label(payload.metadata.as_ref(), "stdin_text")
                .unwrap_or_default()
                .into_bytes()
        } else {
            payload.stdin_payload.clone()
        };
        let mut environment_overrides = payload.environment_overrides.clone();
        if environment_overrides.is_empty() {
            if let Some(encoded) = metadata_label(payload.metadata.as_ref(), "environment_json") {
                if let Ok(decoded) = serde_json::from_str::<HashMap<String, String>>(&encoded) {
                    environment_overrides = decoded;
                }
            }
        }
        let start_new_session = payload.start_new_session
            || metadata_bool(payload.metadata.as_ref(), "start_new_session", true);
        let phase = if command.is_empty() {
            "planning".to_string()
        } else {
            "executing".to_string()
        };
        let stdout_terminal_id = format!("{process_id}-stdout");
        let stderr_terminal_id = format!("{process_id}-stderr");
        let (environment_id, agent_id) = {
            let state = self.state.read().expect("kernel state poisoned");
            get_environment_for_task(&state, &payload.task_id)?
        };
        let mut command_builder = TokioCommand::new(&command);
        command_builder.args(&args);
        if !working_directory.is_empty() {
            command_builder.current_dir(&working_directory);
        }
        if !environment_overrides.is_empty() {
            command_builder.envs(environment_overrides.clone());
        }
        command_builder.stdin(std::process::Stdio::piped());
        command_builder.stdout(std::process::Stdio::piped());
        command_builder.stderr(std::process::Stdio::piped());
        if start_new_session {
            unsafe {
                command_builder.pre_exec(|| {
                    if libc::setpgid(0, 0) != 0 {
                        return Err(std::io::Error::last_os_error());
                    }
                    Ok(())
                });
            }
        }
        let mut child = command_builder.spawn().map_err(|error| {
            Status::internal(format!(
                "failed to spawn runtime process for task {}: {error}",
                payload.task_id
            ))
        })?;
        let pid = child
            .id()
            .map(|value| i32::try_from(value).unwrap_or_default())
            .unwrap_or_default();
        let pgid = if start_new_session { pid } else { 0 };
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| Status::internal("spawned process missing stdout pipe"))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| Status::internal("spawned process missing stderr pipe"))?;
        let stdin = child.stdin.take();
        let child_handle = Arc::new(Mutex::new(child));
        let stdin_handle = Arc::new(Mutex::new(stdin));
        let process_handle = ManagedProcessHandle {
            task_id: payload.task_id.clone(),
            child: child_handle.clone(),
        };
        {
            let mut handles = self.process_handles.lock().await;
            handles.insert(payload.task_id.clone(), process_handle);
        }
        tokio::spawn(pump_terminal_stream(
            self.state.clone(),
            payload.task_id.clone(),
            "stdout".to_string(),
            stdout,
        ));
        tokio::spawn(pump_terminal_stream(
            self.state.clone(),
            payload.task_id.clone(),
            "stderr".to_string(),
            stderr,
        ));
        tokio::spawn(wait_for_managed_process(
            self.state.clone(),
            self.process_handles.clone(),
            payload.task_id.clone(),
            child_handle.clone(),
        ));
        if !stdin_payload.is_empty() {
            let stdin_writer = stdin_handle.clone();
            tokio::spawn(async move {
                let mut stdin = stdin_writer.lock().await;
                if let Some(mut handle) = stdin.take() {
                    let _ = handle.write_all(&stdin_payload).await;
                    let _ = handle.shutdown().await;
                }
            });
        } else {
            let stdin_writer = stdin_handle.clone();
            tokio::spawn(async move {
                let mut stdin = stdin_writer.lock().await;
                if let Some(mut handle) = stdin.take() {
                    let _ = handle.shutdown().await;
                }
            });
        }
        let mut state = self.state.write().expect("kernel state poisoned");
        {
            let task = Self::require_task(&mut state, &payload.task_id)?;
            task.agent_id = agent_id.clone();
            task.environment_id = environment_id.clone();
            task.command = command.clone();
            task.args = args.clone();
            task.process_id = Some(process_id.clone());
            task.phase = phase.clone();
            task.pid = Some(pid);
            task.pgid = (pgid != 0).then_some(pgid);
            task.process_status = "running".to_string();
            task.process_running = true;
            task.exit_code = None;
            task.stdout_terminal_id = Some(stdout_terminal_id.clone());
            task.stderr_terminal_id = Some(stderr_terminal_id.clone());
            task.stdout_eof = false;
            task.stderr_eof = false;
            task.terminal_closed_at_ms = None;
            task.started_at_ms.get_or_insert(now_ms());
            task.last_updated_at_ms = now_ms();
            task.metadata = payload.metadata.clone();
        }
        if let Some(environment) = state.environments.get_mut(&environment_id) {
            environment.active = true;
            environment.terminal_phase = phase.clone();
            environment.last_updated_at_ms = now_ms();
        }
        Self::append_terminal_line(
            &mut state,
            &payload.task_id,
            "system",
            format!(
                "task started phase={phase} command={} args={}",
                empty_to_dash(&command),
                args.join(" ")
            ),
            false,
        );
        let environment = state
            .environments
            .get(&environment_id)
            .map(Self::build_environment_ref);
        let process = state
            .tasks
            .get(&payload.task_id)
            .and_then(Self::build_process_ref);
        let stdout_terminal = state
            .tasks
            .get(&payload.task_id)
            .and_then(|task| Self::build_terminal_ref(task, "stdout"));
        let stderr_terminal = state
            .tasks
            .get(&payload.task_id)
            .and_then(|task| Self::build_terminal_ref(task, "stderr"));

        Ok(Response::new(StartTaskResponse {
            environment,
            process_id,
            phase,
            process,
            stdout_terminal,
            stderr_terminal,
        }))
    }

    async fn execute_command(
        &self,
        request: Request<ExecuteCommandRequest>,
    ) -> Result<Response<ExecuteCommandResponse>, Status> {
        let payload = request.into_inner();
        let timeout_seconds = payload.timeout_seconds.max(1);
        let command = payload.command.clone();
        let argv = payload.argv.clone();
        let runtime_env_id = payload.runtime_env_id.trim().to_string();
        let purpose = payload.purpose.trim().to_string();
        let outcome = execute_shell_command(
            &command,
            &argv,
            &payload.working_directory,
            &payload.environment_overrides,
            &payload.stdin_payload,
            timeout_seconds,
            payload.start_new_session,
        )
        .await?;
        info!(
            command = %command,
            argv = ?argv,
            working_directory = %payload.working_directory,
            timeout_seconds = timeout_seconds,
            allow_network = payload.allow_network,
            runtime_env_id = %runtime_env_id,
            purpose = %purpose,
            exit_code = outcome.exit_code,
            timed_out = outcome.timed_out,
            killed = outcome.killed,
            "runtime command executed"
        );
        Ok(Response::new(ExecuteCommandResponse {
            command,
            argv,
            working_directory: payload.working_directory,
            stdout: String::from_utf8_lossy(&outcome.stdout).to_string(),
            stderr: String::from_utf8_lossy(&outcome.stderr).to_string(),
            exit_code: outcome.exit_code,
            timed_out: outcome.timed_out,
            killed: outcome.killed,
            started_at_ms: outcome.started_at_ms,
            finished_at_ms: outcome.finished_at_ms,
        }))
    }

    async fn terminate_task(
        &self,
        request: Request<TerminateTaskRequest>,
    ) -> Result<Response<TerminateTaskResponse>, Status> {
        let payload = request.into_inner();
        if payload.task_id.is_empty() {
            return Err(Status::invalid_argument("task_id is required"));
        }
        let handle = {
            let handles = self.process_handles.lock().await;
            handles.get(&payload.task_id).cloned()
        };
        let Some(handle) = handle else {
            let state = self.state.read().expect("kernel state poisoned");
            let process = state
                .tasks
                .get(&payload.task_id)
                .and_then(Self::build_process_ref);
            return Ok(Response::new(TerminateTaskResponse {
                task_id: payload.task_id,
                phase: "missing".to_string(),
                terminated: false,
                process,
            }));
        };

        let (pid, pgid) = {
            let state = self.state.read().expect("kernel state poisoned");
            let task = state
                .tasks
                .get(&payload.task_id)
                .ok_or_else(|| Status::not_found(format!("task not found: {}", payload.task_id)))?;
            (task.pid, task.pgid)
        };
        let terminated = if payload.force {
            let mut child = handle.child.lock().await;
            child.start_kill().is_ok()
        } else {
            send_process_signal(pgid, pid, libc::SIGTERM)
        };
        let phase = if payload.force {
            "terminal_failed".to_string()
        } else {
            "cleanup_pending".to_string()
        };
        {
            let mut state = self.state.write().expect("kernel state poisoned");
            {
                let task = Self::require_task(&mut state, &payload.task_id)?;
                task.phase = phase.clone();
                task.process_status = if terminated {
                    "terminating".to_string()
                } else {
                    "missing".to_string()
                };
                task.last_updated_at_ms = now_ms();
            }
            RuntimeKernelServer::append_terminal_line(
                &mut state,
                &payload.task_id,
                "system",
                format!(
                    "terminate requested force={} task={}",
                    payload.force, handle.task_id
                ),
                false,
            );
        }
        let state = self.state.read().expect("kernel state poisoned");
        let process = state
            .tasks
            .get(&payload.task_id)
            .and_then(Self::build_process_ref);
        Ok(Response::new(TerminateTaskResponse {
            task_id: payload.task_id,
            phase,
            terminated,
            process,
        }))
    }

    async fn attach_terminal(
        &self,
        request: Request<AttachTerminalRequest>,
    ) -> Result<Response<AttachTerminalResponse>, Status> {
        let payload = request.into_inner();
        let mut state = self.state.write().expect("kernel state poisoned");
        let task = Self::require_task(&mut state, &payload.task_id)?;
        task.sessions.insert(payload.session_id.clone());
        task.last_updated_at_ms = now_ms();
        Self::append_terminal_line(
            &mut state,
            &payload.task_id,
            "system",
            format!("terminal attached session_id={}", payload.session_id),
            false,
        );
        Ok(Response::new(AttachTerminalResponse {
            task_id: payload.task_id,
            session_id: payload.session_id,
            attached: true,
        }))
    }

    async fn open_terminal(
        &self,
        request: Request<OpenTerminalRequest>,
    ) -> Result<Response<OpenTerminalResponse>, Status> {
        let payload = request.into_inner();
        if payload.task_id.is_empty() {
            return Err(Status::invalid_argument("task_id is required"));
        }
        let (environment_id, environment_runtime_root, default_workspace_path) = {
            let state = self.state.read().expect("kernel state poisoned");
            let (environment_id, _) = get_environment_for_task(&state, &payload.task_id)?;
            let environment = state.environments.get(&environment_id).ok_or_else(|| {
                Status::not_found(format!("environment not found: {environment_id}"))
            })?;
            (
                environment_id,
                environment.runtime_root.clone(),
                environment.workspace_path.clone(),
            )
        };
        let session_id = if payload.session_id.is_empty() {
            self.next_terminal_session_id()
        } else {
            payload.session_id.clone()
        };
        {
            let state = self.state.read().expect("kernel state poisoned");
            if state.interactive_terminals.contains_key(&session_id) {
                return Err(Status::already_exists(format!(
                    "interactive terminal already exists: {session_id}"
                )));
            }
        }

        let command = if payload.command.is_empty() {
            default_shell_command()
        } else {
            payload.command.clone()
        };
        let args = if payload.args.is_empty() {
            default_shell_args(&command)
        } else {
            payload.args.clone()
        };
        let working_directory = if payload.working_directory.is_empty() {
            default_workspace_path
        } else {
            payload.working_directory.clone()
        };
        let environment_overrides = payload.environment_overrides.clone();
        let cols = payload.cols.max(1);
        let rows = payload.rows.max(1);
        let (mut master_file, pid, pgid) = spawn_interactive_terminal_process(
            &command,
            &args,
            &working_directory,
            &environment_overrides,
            cols,
            rows,
        )
        .map_err(Status::internal)?;
        if !payload.stdin_payload.is_empty() {
            master_file
                .write_all(&payload.stdin_payload)
                .map_err(|error| {
                    Status::internal(format!("failed to write initial terminal stdin: {error}"))
                })?;
            master_file.flush().map_err(|error| {
                Status::internal(format!("failed to flush initial terminal stdin: {error}"))
            })?;
        }
        let master_reader = master_file.try_clone().map_err(|error| {
            Status::internal(format!("failed to clone terminal pty master: {error}"))
        })?;
        let master_writer = Arc::new(Mutex::new(Some(master_file)));

        let record = InteractiveTerminalRecord {
            session_id: session_id.clone(),
            task_id: payload.task_id.clone(),
            environment_id: environment_id.clone(),
            status: "open".to_string(),
            eof: false,
            opened_at_ms: now_ms(),
            closed_at_ms: None,
            pid: Some(pid),
            pgid: Some(pgid),
            exit_code: None,
            command: command.clone(),
            args: args.clone(),
            working_directory: working_directory.clone(),
            cols,
            rows,
        };
        {
            let mut state = self.state.write().expect("kernel state poisoned");
            state
                .task_to_interactive_terminals
                .entry(payload.task_id.clone())
                .or_default()
                .push(session_id.clone());
            state
                .interactive_terminals
                .insert(session_id.clone(), record.clone());
            if let Some(task) = state.tasks.get_mut(&payload.task_id) {
                task.sessions.insert(session_id.clone());
                task.last_updated_at_ms = now_ms();
            }
            append_interactive_terminal_line(
                &mut state,
                &session_id,
                "system",
                format!(
                    "interactive terminal opened command={} cwd={}",
                    empty_to_dash(&command),
                    empty_to_dash(&working_directory)
                ),
                false,
            );
        }
        {
            let mut handles = self.terminal_handles.lock().await;
            handles.insert(
                session_id.clone(),
                ManagedTerminalHandle {
                    master: master_writer,
                    pid,
                    pgid,
                },
            );
        }
        tokio::spawn(pump_interactive_terminal_session(
            self.state.clone(),
            session_id.clone(),
            payload.task_id.clone(),
            master_reader,
        ));
        tokio::spawn(wait_for_interactive_terminal_process(
            self.state.clone(),
            self.terminal_handles.clone(),
            session_id.clone(),
            pid,
        ));

        let terminal = Self::build_interactive_terminal_ref(&record);
        let process = Self::build_interactive_terminal_process_ref(&record);
        let _ = environment_runtime_root;
        Ok(Response::new(OpenTerminalResponse {
            terminal: Some(terminal),
            process: Some(process),
            opened: true,
        }))
    }

    async fn write_terminal(
        &self,
        request: Request<WriteTerminalRequest>,
    ) -> Result<Response<WriteTerminalResponse>, Status> {
        let payload = request.into_inner();
        let handle = {
            let handles = self.terminal_handles.lock().await;
            handles.get(&payload.session_id).cloned()
        };
        let Some(handle) = handle else {
            return Ok(Response::new(WriteTerminalResponse {
                task_id: payload.task_id,
                session_id: payload.session_id,
                accepted: false,
                bytes_written: 0,
                eof: false,
                status: "missing".to_string(),
            }));
        };

        let bytes_written = {
            let mut master_guard = handle.master.lock().await;
            let Some(master_file) = master_guard.as_mut() else {
                return Ok(Response::new(WriteTerminalResponse {
                    task_id: payload.task_id,
                    session_id: payload.session_id,
                    accepted: false,
                    bytes_written: 0,
                    eof: false,
                    status: "closed".to_string(),
                }));
            };
            master_file.write_all(&payload.data).map_err(|error| {
                Status::internal(format!("failed to write terminal session: {error}"))
            })?;
            master_file.flush().map_err(|error| {
                Status::internal(format!("failed to flush terminal session: {error}"))
            })?;
            u32::try_from(payload.data.len()).unwrap_or(u32::MAX)
        };
        if payload.eof {
            let _ = close_managed_terminal_session(
                self.terminal_handles.clone(),
                &payload.session_id,
                false,
            )
            .await;
        }
        let mut state = self.state.write().expect("kernel state poisoned");
        if let Some(session) = state.interactive_terminals.get_mut(&payload.session_id) {
            session.status = if payload.eof {
                "closing".to_string()
            } else {
                "open".to_string()
            };
        }
        Ok(Response::new(WriteTerminalResponse {
            task_id: payload.task_id,
            session_id: payload.session_id,
            accepted: true,
            bytes_written,
            eof: payload.eof,
            status: if payload.eof {
                "closing".to_string()
            } else {
                "open".to_string()
            },
        }))
    }

    async fn resize_terminal(
        &self,
        request: Request<ResizeTerminalRequest>,
    ) -> Result<Response<ResizeTerminalResponse>, Status> {
        let payload = request.into_inner();
        let handle = {
            let handles = self.terminal_handles.lock().await;
            handles.get(&payload.session_id).cloned()
        };
        let Some(handle) = handle else {
            return Ok(Response::new(ResizeTerminalResponse {
                task_id: payload.task_id,
                session_id: payload.session_id,
                resized: false,
                cols: payload.cols,
                rows: payload.rows,
                status: "missing".to_string(),
            }));
        };
        let cols = payload.cols.max(1);
        let rows = payload.rows.max(1);
        let resized = {
            let master_guard = handle.master.lock().await;
            if let Some(master_file) = master_guard.as_ref() {
                let winsize = libc::winsize {
                    ws_row: u16::try_from(rows).unwrap_or(u16::MAX),
                    ws_col: u16::try_from(cols).unwrap_or(u16::MAX),
                    ws_xpixel: 0,
                    ws_ypixel: 0,
                };
                unsafe { libc::ioctl(master_file.as_raw_fd(), libc::TIOCSWINSZ, &winsize) == 0 }
            } else {
                false
            }
        };
        let mut state = self.state.write().expect("kernel state poisoned");
        if let Some(session) = state.interactive_terminals.get_mut(&payload.session_id) {
            session.cols = cols;
            session.rows = rows;
        }
        Ok(Response::new(ResizeTerminalResponse {
            task_id: payload.task_id,
            session_id: payload.session_id,
            resized,
            cols,
            rows,
            status: if resized {
                "resized".to_string()
            } else {
                "resize_unsupported".to_string()
            },
        }))
    }

    async fn close_terminal(
        &self,
        request: Request<CloseTerminalRequest>,
    ) -> Result<Response<CloseTerminalResponse>, Status> {
        let payload = request.into_inner();
        let closed = close_managed_terminal_session(
            self.terminal_handles.clone(),
            &payload.session_id,
            payload.force,
        )
        .await;
        let mut state = self.state.write().expect("kernel state poisoned");
        let status = if let Some(session) = state.interactive_terminals.get_mut(&payload.session_id)
        {
            session.status = if closed {
                "closing".to_string()
            } else {
                "missing".to_string()
            };
            if !closed {
                session.closed_at_ms.get_or_insert(now_ms());
            }
            session.status.clone()
        } else if closed {
            "closing".to_string()
        } else {
            "missing".to_string()
        };
        append_interactive_terminal_line(
            &mut state,
            &payload.session_id,
            "system",
            format!(
                "interactive terminal close requested force={}",
                payload.force
            ),
            false,
        );
        Ok(Response::new(CloseTerminalResponse {
            task_id: payload.task_id,
            session_id: payload.session_id,
            closed,
            status,
            closed_at_ms: if closed { now_ms() } else { 0 },
        }))
    }

    async fn stream_terminal(
        &self,
        request: Request<StreamTerminalRequest>,
    ) -> Result<Response<Self::StreamTerminalStream>, Status> {
        let payload = request.into_inner();
        {
            let state = self.state.read().expect("kernel state poisoned");
            if !state.tasks.contains_key(&payload.task_id) {
                return Err(Status::not_found(format!(
                    "task not found: {}",
                    payload.task_id
                )));
            }
        }
        let requested_stream = if payload.stream.is_empty() {
            None
        } else {
            Some(payload.stream.clone())
        };
        let task_id = payload.task_id.clone();
        let state = self.state.clone();
        let output = try_stream! {
            let mut delivered = 0usize;
            let mut eof_emitted = false;
            loop {
                let (records, reached_eof, task_terminal, task_finished) = {
                    let state = state.read().expect("kernel state poisoned");
                    let filtered: Vec<TerminalRecord> = state
                        .terminal_history
                        .get(&task_id)
                        .into_iter()
                        .flat_map(|items| items.iter())
                        .filter(|record| {
                            requested_stream
                                .as_ref()
                                .is_none_or(|stream| record.stream == *stream)
                        })
                        .cloned()
                        .collect();
                    let next_records = if delivered >= filtered.len() {
                        Vec::new()
                    } else {
                        filtered[delivered..].to_vec()
                    };
                    let reached_eof = filtered.last().is_some_and(|record| record.eof);
                    let task_terminal = state
                        .tasks
                        .get(&task_id)
                        .is_some_and(TaskRecord::is_terminal);
                    let task_finished = state.tasks.get(&task_id).is_some_and(|task| {
                        (task.stdout_eof && task.stderr_eof)
                            || (!task.process_running && task.started_at_ms.is_some())
                    });
                    (next_records, reached_eof, task_terminal, task_finished)
                };
                if !records.is_empty() {
                    delivered += records.len();
                    for record in records {
                        if record.eof {
                            eof_emitted = true;
                        }
                        yield TerminalChunk {
                            task_id: task_id.clone(),
                            stream: record.stream,
                            data: record.data,
                            eof: record.eof,
                            session_id: String::new(),
                        };
                    }
                }
                if reached_eof || task_terminal || task_finished {
                    if !eof_emitted {
                        yield TerminalChunk {
                            task_id: task_id.clone(),
                            stream: requested_stream.clone().unwrap_or_default(),
                            data: Vec::new(),
                            eof: true,
                            session_id: String::new(),
                        };
                    }
                    break;
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        };
        Ok(Response::new(Box::pin(output)))
    }

    async fn stream_terminal_session(
        &self,
        request: Request<StreamTerminalSessionRequest>,
    ) -> Result<Response<Self::StreamTerminalSessionStream>, Status> {
        let payload = request.into_inner();
        {
            let state = self.state.read().expect("kernel state poisoned");
            let Some(session) = state.interactive_terminals.get(&payload.session_id) else {
                return Err(Status::not_found(format!(
                    "interactive terminal not found: {}",
                    payload.session_id
                )));
            };
            if session.task_id != payload.task_id {
                return Err(Status::failed_precondition(format!(
                    "interactive terminal {} does not belong to task {}",
                    payload.session_id, payload.task_id
                )));
            }
        }
        let task_id = payload.task_id.clone();
        let session_id = payload.session_id.clone();
        let state = self.state.clone();
        let output = try_stream! {
            let mut delivered = 0usize;
            let mut eof_emitted = false;
            loop {
                let (records, reached_eof, session_terminal) = {
                    let state = state.read().expect("kernel state poisoned");
                    let filtered: Vec<TerminalRecord> = state
                        .interactive_terminal_history
                        .get(&session_id)
                        .into_iter()
                        .flat_map(|items| items.iter())
                        .cloned()
                        .collect();
                    let next_records = if delivered >= filtered.len() {
                        Vec::new()
                    } else {
                        filtered[delivered..].to_vec()
                    };
                    let reached_eof = filtered.last().is_some_and(|record| record.eof);
                    let session_terminal = state
                        .interactive_terminals
                        .get(&session_id)
                        .is_some_and(|session| session.eof || matches!(session.status.as_str(), "closed" | "failed"));
                    (next_records, reached_eof, session_terminal)
                };
                if !records.is_empty() {
                    delivered += records.len();
                    for record in records {
                        if record.eof {
                            eof_emitted = true;
                        }
                        yield TerminalChunk {
                            task_id: task_id.clone(),
                            stream: record.stream,
                            data: record.data,
                            eof: record.eof,
                            session_id: session_id.clone(),
                        };
                    }
                }
                if reached_eof || session_terminal {
                    if !eof_emitted {
                        yield TerminalChunk {
                            task_id: task_id.clone(),
                            stream: "interactive".to_string(),
                            data: Vec::new(),
                            eof: true,
                            session_id: session_id.clone(),
                        };
                    }
                    break;
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        };
        Ok(Response::new(Box::pin(output)))
    }

    async fn pause_task(
        &self,
        request: Request<PauseTaskRequest>,
    ) -> Result<Response<PauseTaskResponse>, Status> {
        let payload = request.into_inner();
        let (pgid, pid) = {
            let state = self.state.read().expect("kernel state poisoned");
            let task = state
                .tasks
                .get(&payload.task_id)
                .ok_or_else(|| Status::not_found(format!("task not found: {}", payload.task_id)))?;
            (task.pgid, task.pid)
        };
        if !send_process_signal(pgid, pid, libc::SIGSTOP) {
            return Err(Status::failed_precondition(format!(
                "task {} is not running under kernel process control",
                payload.task_id
            )));
        }
        let mut state = self.state.write().expect("kernel state poisoned");
        let environment_id = {
            let task = Self::require_task(&mut state, &payload.task_id)?;
            task.phase = "paused_for_operator".to_string();
            task.process_status = "paused".to_string();
            task.pause_reason = Some(payload.reason.clone());
            task.last_updated_at_ms = now_ms();
            task.environment_id.clone()
        };
        if let Some(environment) = state.environments.get_mut(&environment_id) {
            environment.terminal_phase = "paused_for_operator".to_string();
            environment.last_updated_at_ms = now_ms();
        }
        Self::append_terminal_line(
            &mut state,
            &payload.task_id,
            "system",
            format!("task paused reason={}", empty_to_dash(&payload.reason)),
            false,
        );
        Ok(Response::new(PauseTaskResponse {
            task_id: payload.task_id,
            phase: "paused_for_operator".to_string(),
        }))
    }

    async fn resume_task(
        &self,
        request: Request<ResumeTaskRequest>,
    ) -> Result<Response<ResumeTaskResponse>, Status> {
        let payload = request.into_inner();
        let resumed_phase = if payload.phase.is_empty() {
            "executing".to_string()
        } else {
            payload.phase.clone()
        };
        let (pgid, pid) = {
            let state = self.state.read().expect("kernel state poisoned");
            let task = state
                .tasks
                .get(&payload.task_id)
                .ok_or_else(|| Status::not_found(format!("task not found: {}", payload.task_id)))?;
            (task.pgid, task.pid)
        };
        if !send_process_signal(pgid, pid, libc::SIGCONT) {
            return Err(Status::failed_precondition(format!(
                "task {} is not running under kernel process control",
                payload.task_id
            )));
        }
        let mut state = self.state.write().expect("kernel state poisoned");
        let environment_id = {
            let task = Self::require_task(&mut state, &payload.task_id)?;
            task.phase = resumed_phase.clone();
            task.process_status = "running".to_string();
            task.pause_reason = None;
            task.last_updated_at_ms = now_ms();
            task.environment_id.clone()
        };
        if let Some(environment) = state.environments.get_mut(&environment_id) {
            environment.active = true;
            environment.terminal_phase = resumed_phase.clone();
            environment.last_updated_at_ms = now_ms();
        }
        Self::append_terminal_line(
            &mut state,
            &payload.task_id,
            "system",
            format!("task resumed phase={resumed_phase}"),
            false,
        );
        Ok(Response::new(ResumeTaskResponse {
            task_id: payload.task_id,
            phase: resumed_phase,
        }))
    }

    async fn finalize_task(
        &self,
        request: Request<FinalizeTaskRequest>,
    ) -> Result<Response<FinalizeTaskResponse>, Status> {
        let payload = request.into_inner();
        let final_phase = if payload.final_phase.is_empty() {
            if payload.success {
                "completed_retained".to_string()
            } else {
                "recoverable_failed_retained".to_string()
            }
        } else {
            payload.final_phase.clone()
        };
        let mut state = self.state.write().expect("kernel state poisoned");
        let environment_id = {
            let task = Self::require_task(&mut state, &payload.task_id)?;
            task.phase = final_phase.clone();
            task.finalize_error =
                (!payload.error_message.is_empty()).then(|| payload.error_message.clone());
            task.finalized_at_ms = Some(now_ms());
            task.last_updated_at_ms = now_ms();
            task.environment_id.clone()
        };
        if let Some(environment) = state.environments.get_mut(&environment_id) {
            environment.active = false;
            environment.terminal_phase = final_phase.clone();
            environment.last_updated_at_ms = now_ms();
        }
        Self::append_terminal_line(
            &mut state,
            &payload.task_id,
            "system",
            format!(
                "task finalized phase={final_phase} error={}",
                empty_to_dash(&payload.error_message)
            ),
            true,
        );
        Ok(Response::new(FinalizeTaskResponse {
            task_id: payload.task_id,
            final_phase,
            environment_id,
        }))
    }

    async fn collect_snapshot(
        &self,
        request: Request<CollectSnapshotRequest>,
    ) -> Result<Response<CollectSnapshotResponse>, Status> {
        let payload = request.into_inner();
        let state = self.state.read().expect("kernel state poisoned");
        let task = state
            .tasks
            .get(&payload.task_id)
            .ok_or_else(|| Status::not_found(format!("task not found: {}", payload.task_id)))?;
        let environment = state
            .environments
            .get(&task.environment_id)
            .ok_or_else(|| {
                Status::not_found(format!("environment not found: {}", task.environment_id))
            })?;
        let terminal_records = state
            .terminal_history
            .get(&payload.task_id)
            .cloned()
            .unwrap_or_default();
        let browser_sessions = state
            .task_to_browser_sessions
            .get(&payload.task_id)
            .into_iter()
            .flat_map(|items| items.iter())
            .filter_map(|session_id| state.browser_sessions.get(session_id))
            .map(BrowserSessionSnapshot::from)
            .collect::<Vec<_>>();
        let interactive_terminals = state
            .task_to_interactive_terminals
            .get(&payload.task_id)
            .into_iter()
            .flat_map(|items| items.iter())
            .filter_map(|session_id| state.interactive_terminals.get(session_id))
            .map(InteractiveTerminalSnapshot::from)
            .collect::<Vec<_>>();
        let checkpoints = state
            .task_to_checkpoints
            .get(&payload.task_id)
            .into_iter()
            .flat_map(|items| items.iter())
            .filter_map(|checkpoint_id| state.checkpoints.get(checkpoint_id))
            .map(CheckpointSnapshot::from)
            .collect::<Vec<_>>();
        let snapshot = SnapshotPayload {
            kernel: KernelSnapshot {
                service: SERVICE_NAME.to_string(),
                started_at_ms: state.started_at_ms,
                last_reconcile_at_ms: state.last_reconcile_at_ms,
                active_environment_count: state.active_environment_count(),
                known_task_count: state.tasks.len(),
                authoritative: true,
                production_ready: true,
                maturity: "ga".to_string(),
                authority_scope: AUTHORITY_SCOPE.to_string(),
                authoritative_operations: AUTHORITATIVE_OPERATIONS
                    .split(',')
                    .map(str::trim)
                    .filter(|item| !item.is_empty())
                    .map(str::to_string)
                    .collect(),
                full_authority: true,
                partial_authority: false,
                cutover_blockers: CUTOVER_BLOCKERS
                    .split(',')
                    .map(str::trim)
                    .filter(|item| !item.is_empty())
                    .map(str::to_string)
                    .collect(),
                interactive_terminal_count: interactive_terminals.len(),
                browser_session_count: browser_sessions.len(),
                checkpoint_count: checkpoints.len(),
            },
            environment: EnvironmentSnapshot::from(environment),
            task: TaskSnapshot::from(task),
            terminal: terminal_records
                .iter()
                .map(TerminalSnapshot::from)
                .collect::<Vec<_>>(),
            interactive_terminals,
            browser_sessions,
            checkpoints,
        };
        let payload_json = serde_json::to_vec(&snapshot)
            .map_err(|error| Status::internal(format!("failed to encode snapshot: {error}")))?;
        Ok(Response::new(CollectSnapshotResponse {
            task_id: payload.task_id,
            environment_id: environment.environment_id.clone(),
            payload_json,
            task_phase: task.phase.clone(),
            final_phase: if task.finalized_at_ms.is_some() {
                task.phase.clone()
            } else {
                String::new()
            },
            runtime_root: environment.runtime_root.display().to_string(),
            interactive_terminal_count: snapshot.kernel.interactive_terminal_count as u32,
            browser_session_count: snapshot.kernel.browser_session_count as u32,
            checkpoint_count: snapshot.kernel.checkpoint_count as u32,
        }))
    }

    async fn reconcile(
        &self,
        _request: Request<ReconcileRequest>,
    ) -> Result<Response<ReconcileResponse>, Status> {
        let mut state = self.state.write().expect("kernel state poisoned");
        let mut reconciled = 0u32;
        let updates: Vec<(String, bool, String)> = state
            .tasks
            .values()
            .map(|task| {
                (
                    task.environment_id.clone(),
                    !task.is_terminal(),
                    task.phase.clone(),
                )
            })
            .collect();
        for (environment_id, should_be_active, should_phase) in updates {
            if let Some(environment) = state.environments.get_mut(&environment_id) {
                if environment.active != should_be_active
                    || environment.terminal_phase != should_phase
                {
                    environment.active = should_be_active;
                    environment.terminal_phase = should_phase;
                    environment.last_updated_at_ms = now_ms();
                    reconciled = reconciled.saturating_add(1);
                }
            }
        }
        state.last_reconcile_at_ms = Some(now_ms());
        Ok(Response::new(ReconcileResponse {
            active_environments: state.active_environment_count() as u32,
            reconciled_environments: reconciled,
        }))
    }

    async fn cleanup_environment(
        &self,
        request: Request<CleanupEnvironmentRequest>,
    ) -> Result<Response<CleanupEnvironmentResponse>, Status> {
        let payload = request.into_inner();
        if payload.task_id.is_empty() {
            return Err(Status::invalid_argument("task_id is required"));
        }

        let (environment_id, workspace_path, created_worktree, worktree_mode, runtime_root) = {
            let state = self.state.read().expect("kernel state poisoned");
            let environment_id = state
                .task_to_environment
                .get(&payload.task_id)
                .cloned()
                .ok_or_else(|| Status::not_found(format!("task not found: {}", payload.task_id)))?;
            let environment = state.environments.get(&environment_id).ok_or_else(|| {
                Status::not_found(format!("environment not found: {environment_id}"))
            })?;
            (
                environment_id,
                environment.workspace_path.clone(),
                environment.created_worktree,
                environment.worktree_mode.clone(),
                environment.runtime_root.clone(),
            )
        };

        let force = payload.force;
        let (task_pgid, task_pid) = {
            let state = self.state.read().expect("kernel state poisoned");
            state
                .tasks
                .get(&payload.task_id)
                .map(|task| (task.pgid, task.pid))
                .unwrap_or((None, None))
        };
        let _terminated = if force {
            send_process_signal(task_pgid, task_pid, libc::SIGKILL)
        } else {
            let terminated = send_process_signal(task_pgid, task_pid, libc::SIGTERM);
            let hup = send_process_signal(task_pgid, task_pid, libc::SIGHUP);
            terminated || hup
        };
        let interactive_terminal_ids = {
            let state = self.state.read().expect("kernel state poisoned");
            state
                .task_to_interactive_terminals
                .get(&payload.task_id)
                .cloned()
                .unwrap_or_default()
        };
        for session_id in &interactive_terminal_ids {
            let _ =
                close_managed_terminal_session(self.terminal_handles.clone(), session_id, force)
                    .await;
        }
        let session_ids = {
            let state = self.state.read().expect("kernel state poisoned");
            state
                .task_to_browser_sessions
                .get(&payload.task_id)
                .cloned()
                .unwrap_or_default()
        };
        for session_id in &session_ids {
            let _ =
                stop_managed_browser_session(self.browser_handles.clone(), session_id, force).await;
        }
        let (workspace_removed, runtime_root_removed) =
            task::spawn_blocking(move || -> Result<(bool, bool)> {
                let workspace_removed = cleanup_workspace(&workspace_path, created_worktree)?;
                let runtime_root_removed = if runtime_root.exists() {
                    stdfs::remove_dir_all(&runtime_root)?;
                    !runtime_root.exists()
                } else {
                    false
                };
                Ok((workspace_removed, runtime_root_removed || force))
            })
            .await
            .map_err(|error| Status::internal(format!("cleanup join failure: {error}")))?
            .map_err(|error| Status::internal(format!("cleanup failed: {error}")))?;

        let mut state = self.state.write().expect("kernel state poisoned");
        if let Some(environment) = state.environments.get_mut(&environment_id) {
            environment.active = false;
            environment.terminal_phase = "cleaned".to_string();
            environment.last_updated_at_ms = now_ms();
        }
        if let Some(task) = state.tasks.get_mut(&payload.task_id) {
            task.phase = "cleaned".to_string();
            task.finalized_at_ms.get_or_insert(now_ms());
            task.last_updated_at_ms = now_ms();
        }
        if let Some(session_ids) = state
            .task_to_interactive_terminals
            .get(&payload.task_id)
            .cloned()
        {
            for session_id in session_ids {
                if let Some(session) = state.interactive_terminals.get_mut(&session_id) {
                    session.status = "closed".to_string();
                    session.eof = true;
                    session.closed_at_ms = Some(now_ms());
                }
            }
        }
        if let Some(session_ids) = state
            .task_to_browser_sessions
            .get(&payload.task_id)
            .cloned()
        {
            for session_id in session_ids {
                if let Some(session) = state.browser_sessions.get_mut(&session_id) {
                    session.status = "closed".to_string();
                    session.ended_at_ms = Some(now_ms());
                }
            }
        }
        Self::append_terminal_line(
            &mut state,
            &payload.task_id,
            "system",
            format!(
                "cleanup finished workspace_removed={} runtime_root_removed={}",
                workspace_removed, runtime_root_removed
            ),
            false,
        );

        Ok(Response::new(CleanupEnvironmentResponse {
            task_id: payload.task_id,
            environment_id,
            cleaned: workspace_removed || runtime_root_removed || force,
            workspace_removed,
            runtime_root_removed,
            worktree_mode,
        }))
    }

    async fn start_browser_session(
        &self,
        request: Request<StartBrowserSessionRequest>,
    ) -> Result<Response<StartBrowserSessionResponse>, Status> {
        let payload = request.into_inner();
        if payload.task_id.is_empty() {
            return Err(Status::invalid_argument("task_id is required"));
        }
        let created_at_ms = now_ms();
        let (environment_id, _agent_id) = {
            let state = self.state.read().expect("kernel state poisoned");
            get_environment_for_task(&state, &payload.task_id)?
        };
        let session_id = self.next_browser_session_id();
        let transport = if payload.transport.is_empty() {
            "local_headful".to_string()
        } else {
            payload.transport.clone()
        };
        let runtime_dir = if payload.runtime_dir.is_empty() {
            self.config
                .runtime_root()
                .join("tasks")
                .join(&payload.task_id)
                .join("browser")
        } else {
            PathBuf::from(payload.runtime_dir.clone())
        };
        fs::create_dir_all(&runtime_dir).await.map_err(|error| {
            Status::internal(format!("failed to create browser runtime dir: {error}"))
        })?;
        let mut missing_binaries = payload.missing_binaries.clone();
        let mut metadata = payload.metadata_labels.clone();
        let mut browser_children: Vec<Arc<Mutex<Child>>> = Vec::new();
        let display_id = (payload.display_id != 0).then_some(payload.display_id);
        let vnc_port = (payload.vnc_port != 0).then_some(payload.vnc_port);
        let novnc_port = (payload.novnc_port != 0).then_some(payload.novnc_port);
        let mut status = "running".to_string();

        if transport == "novnc" {
            if missing_binaries.is_empty() {
                for binary in ["Xvfb", "openbox", "x11vnc", "websockify"] {
                    if resolve_binary_path(binary).is_none() {
                        missing_binaries.push(binary.to_string());
                    }
                }
            }
            if missing_binaries.is_empty()
                && (display_id.is_none() || vnc_port.is_none() || novnc_port.is_none())
            {
                status = "unavailable".to_string();
                metadata.insert(
                    "unavailable_reason".to_string(),
                    "missing_display_or_ports".to_string(),
                );
            } else if missing_binaries.is_empty() {
                let browser_env = [("DISPLAY", format!(":{}", display_id.unwrap_or_default()))];
                let xvfb_log = open_browser_log(&runtime_dir, "xvfb")?;
                let openbox_log = open_browser_log(&runtime_dir, "openbox")?;
                let x11vnc_log = open_browser_log(&runtime_dir, "x11vnc")?;
                let websockify_log = open_browser_log(&runtime_dir, "websockify")?;

                let mut xvfb = TokioCommand::new("Xvfb");
                xvfb.arg(format!(":{}", display_id.unwrap_or_default()))
                    .arg("-screen")
                    .arg("0")
                    .arg("1280x720x24")
                    .arg("-nolisten")
                    .arg("tcp")
                    .stdout(xvfb_log)
                    .stderr(std::process::Stdio::null());
                unsafe {
                    xvfb.pre_exec(|| {
                        if libc::setpgid(0, 0) != 0 {
                            return Err(std::io::Error::last_os_error());
                        }
                        Ok(())
                    });
                }
                let xvfb_child = Arc::new(Mutex::new(xvfb.spawn().map_err(|error| {
                    Status::internal(format!("failed to start Xvfb: {error}"))
                })?));

                let mut openbox = TokioCommand::new("openbox");
                openbox
                    .envs(browser_env.iter().cloned())
                    .stdout(openbox_log)
                    .stderr(std::process::Stdio::null());
                unsafe {
                    openbox.pre_exec(|| {
                        if libc::setpgid(0, 0) != 0 {
                            return Err(std::io::Error::last_os_error());
                        }
                        Ok(())
                    });
                }
                let openbox_child = Arc::new(Mutex::new(openbox.spawn().map_err(|error| {
                    Status::internal(format!("failed to start openbox: {error}"))
                })?));

                let mut x11vnc = TokioCommand::new("x11vnc");
                x11vnc
                    .arg("-display")
                    .arg(format!(":{}", display_id.unwrap_or_default()))
                    .arg("-rfbport")
                    .arg(vnc_port.unwrap_or_default().to_string())
                    .arg("-localhost")
                    .arg("-forever")
                    .arg("-shared")
                    .arg("-nopw")
                    .stdout(x11vnc_log)
                    .stderr(std::process::Stdio::null());
                unsafe {
                    x11vnc.pre_exec(|| {
                        if libc::setpgid(0, 0) != 0 {
                            return Err(std::io::Error::last_os_error());
                        }
                        Ok(())
                    });
                }
                let x11vnc_child = Arc::new(Mutex::new(x11vnc.spawn().map_err(|error| {
                    Status::internal(format!("failed to start x11vnc: {error}"))
                })?));

                let mut websockify = TokioCommand::new("websockify");
                websockify
                    .arg(novnc_port.unwrap_or_default().to_string())
                    .arg(format!("127.0.0.1:{}", vnc_port.unwrap_or_default()))
                    .stdout(websockify_log)
                    .stderr(std::process::Stdio::null());
                unsafe {
                    websockify.pre_exec(|| {
                        if libc::setpgid(0, 0) != 0 {
                            return Err(std::io::Error::last_os_error());
                        }
                        Ok(())
                    });
                }
                let websockify_child =
                    Arc::new(Mutex::new(websockify.spawn().map_err(|error| {
                        Status::internal(format!("failed to start websockify: {error}"))
                    })?));

                metadata.insert(
                    "xvfb_pid".to_string(),
                    xvfb_child
                        .lock()
                        .await
                        .id()
                        .map(|value| value.to_string())
                        .unwrap_or_default(),
                );
                metadata.insert(
                    "openbox_pid".to_string(),
                    openbox_child
                        .lock()
                        .await
                        .id()
                        .map(|value| value.to_string())
                        .unwrap_or_default(),
                );
                metadata.insert(
                    "x11vnc_pid".to_string(),
                    x11vnc_child
                        .lock()
                        .await
                        .id()
                        .map(|value| value.to_string())
                        .unwrap_or_default(),
                );
                metadata.insert(
                    "websockify_pid".to_string(),
                    websockify_child
                        .lock()
                        .await
                        .id()
                        .map(|value| value.to_string())
                        .unwrap_or_default(),
                );
                metadata.insert(
                    "xvfb_log".to_string(),
                    runtime_dir.join("xvfb.log").display().to_string(),
                );
                metadata.insert(
                    "openbox_log".to_string(),
                    runtime_dir.join("openbox.log").display().to_string(),
                );
                metadata.insert(
                    "x11vnc_log".to_string(),
                    runtime_dir.join("x11vnc.log").display().to_string(),
                );
                metadata.insert(
                    "websockify_log".to_string(),
                    runtime_dir.join("websockify.log").display().to_string(),
                );
                browser_children = vec![xvfb_child, openbox_child, x11vnc_child, websockify_child];
            } else {
                status = "unavailable".to_string();
            }
        }

        let session = BrowserSessionRecord {
            session_id: session_id.clone(),
            task_id: payload.task_id.clone(),
            environment_id,
            scope_id: payload.scope_id.clone(),
            transport: transport.clone(),
            status: status.clone(),
            runtime_dir: runtime_dir.display().to_string(),
            display_id,
            vnc_port,
            novnc_port,
            missing_binaries: missing_binaries.clone(),
            created_at_ms,
            ended_at_ms: None,
            metadata,
        };
        if !browser_children.is_empty() {
            let mut handles = self.browser_handles.lock().await;
            handles.insert(
                session_id.clone(),
                ManagedBrowserSessionHandle {
                    children: browser_children,
                },
            );
        }
        let mut state = self.state.write().expect("kernel state poisoned");
        state
            .task_to_browser_sessions
            .entry(payload.task_id.clone())
            .or_default()
            .push(session_id.clone());
        state
            .browser_sessions
            .insert(session_id.clone(), session.clone());
        Self::append_terminal_line(
            &mut state,
            &payload.task_id,
            "system",
            format!(
                "browser session registered scope_id={} transport={}",
                empty_to_dash(&payload.scope_id),
                empty_to_dash(&transport)
            ),
            false,
        );
        Ok(Response::new(StartBrowserSessionResponse {
            session: Some(Self::build_browser_session_ref(&session)),
            started: true,
        }))
    }

    async fn stop_browser_session(
        &self,
        request: Request<StopBrowserSessionRequest>,
    ) -> Result<Response<StopBrowserSessionResponse>, Status> {
        let payload = request.into_inner();
        let session_id = {
            let state = self.state.read().expect("kernel state poisoned");
            state
                .task_to_browser_sessions
                .get(&payload.task_id)
                .and_then(|items| {
                    items.iter().rev().find(|session_id| {
                        state
                            .browser_sessions
                            .get(*session_id)
                            .is_some_and(|session| {
                                session.scope_id == payload.scope_id
                                    && session.ended_at_ms.is_none()
                            })
                    })
                })
                .cloned()
        };
        let Some(session_id) = session_id else {
            return Ok(Response::new(StopBrowserSessionResponse {
                task_id: payload.task_id,
                scope_id: payload.scope_id,
                stopped: false,
                status: "missing".to_string(),
            }));
        };
        let _ =
            stop_managed_browser_session(self.browser_handles.clone(), &session_id, payload.force)
                .await;
        let mut state = self.state.write().expect("kernel state poisoned");
        let status = {
            let session = state.browser_sessions.get_mut(&session_id).ok_or_else(|| {
                Status::not_found(format!("browser session not found: {session_id}"))
            })?;
            session.status = "closed".to_string();
            session.ended_at_ms = Some(now_ms());
            session.status.clone()
        };
        Self::append_terminal_line(
            &mut state,
            &payload.task_id,
            "system",
            format!(
                "browser session stopped scope_id={}",
                empty_to_dash(&payload.scope_id)
            ),
            false,
        );
        Ok(Response::new(StopBrowserSessionResponse {
            task_id: payload.task_id,
            scope_id: payload.scope_id,
            stopped: true,
            status,
        }))
    }

    async fn get_browser_session(
        &self,
        request: Request<GetBrowserSessionRequest>,
    ) -> Result<Response<GetBrowserSessionResponse>, Status> {
        let payload = request.into_inner();
        let state = self.state.read().expect("kernel state poisoned");
        let session = state
            .task_to_browser_sessions
            .get(&payload.task_id)
            .and_then(|items| {
                items.iter().rev().find_map(|session_id| {
                    state.browser_sessions.get(session_id).filter(|session| {
                        payload.scope_id.is_empty() || session.scope_id == payload.scope_id
                    })
                })
            })
            .cloned();
        Ok(Response::new(GetBrowserSessionResponse {
            found: session.is_some(),
            session: session.as_ref().map(Self::build_browser_session_ref),
        }))
    }

    async fn save_checkpoint(
        &self,
        request: Request<SaveCheckpointRequest>,
    ) -> Result<Response<SaveCheckpointResponse>, Status> {
        let payload = request.into_inner();
        if payload.task_id.is_empty() {
            return Err(Status::invalid_argument("task_id is required"));
        }
        let environment_id = if payload.environment_id.is_empty() {
            let state = self.state.read().expect("kernel state poisoned");
            state
                .task_to_environment
                .get(&payload.task_id)
                .cloned()
                .ok_or_else(|| Status::not_found(format!("task not found: {}", payload.task_id)))?
        } else {
            payload.environment_id.clone()
        };
        let environment_runtime_root = {
            let state = self.state.read().expect("kernel state poisoned");
            state
                .environments
                .get(&environment_id)
                .map(|environment| environment.runtime_root.clone())
                .ok_or_else(|| {
                    Status::not_found(format!("environment not found: {environment_id}"))
                })?
        };
        let checkpoint_id = self.next_checkpoint_id();
        let checkpoint_dir = environment_runtime_root
            .join("checkpoints")
            .join(&checkpoint_id);
        let manifest_path = checkpoint_dir.join("manifest.json");
        let snapshot_path = checkpoint_dir.join("workspace_snapshot.json");
        let patch_path = build_checkpoint_archive_path(&checkpoint_dir, "git.patch");
        let git_status_path = build_checkpoint_archive_path(&checkpoint_dir, "git_status.txt");
        let untracked_bundle_path =
            build_checkpoint_archive_path(&checkpoint_dir, "untracked.tar.gz");
        fs::create_dir_all(&checkpoint_dir).await.map_err(|error| {
            Status::internal(format!("failed to create checkpoint dir: {error}"))
        })?;
        let (
            manifest_json,
            snapshot_json,
            patch_bytes,
            git_status_text,
            untracked_bundle_bytes,
            commit_sha,
            has_untracked_bundle,
            workspace_path,
        ) = {
            let state = self.state.read().expect("kernel state poisoned");
            let task = state
                .tasks
                .get(&payload.task_id)
                .ok_or_else(|| Status::not_found(format!("task not found: {}", payload.task_id)))?;
            let environment = state.environments.get(&environment_id).ok_or_else(|| {
                Status::not_found(format!("environment not found: {environment_id}"))
            })?;
            let terminal_records = state
                .terminal_history
                .get(&payload.task_id)
                .cloned()
                .unwrap_or_default();
            let browser_sessions = state
                .task_to_browser_sessions
                .get(&payload.task_id)
                .into_iter()
                .flat_map(|items| items.iter())
                .filter_map(|session_id| state.browser_sessions.get(session_id))
                .map(BrowserSessionSnapshot::from)
                .collect::<Vec<_>>();
            let interactive_terminals = state
                .task_to_interactive_terminals
                .get(&payload.task_id)
                .into_iter()
                .flat_map(|items| items.iter())
                .filter_map(|session_id| state.interactive_terminals.get(session_id))
                .map(InteractiveTerminalSnapshot::from)
                .collect::<Vec<_>>();
            let checkpoints = state
                .task_to_checkpoints
                .get(&payload.task_id)
                .into_iter()
                .flat_map(|items| items.iter())
                .filter_map(|checkpoint_id| state.checkpoints.get(checkpoint_id))
                .map(CheckpointSnapshot::from)
                .collect::<Vec<_>>();
            let workspace_path = environment.workspace_path.clone();
            let workspace_root = PathBuf::from(&workspace_path);
            let git_status_text = run_git_output(
                &workspace_root,
                &["status", "--short", "--untracked-files=all"],
            )
            .map_err(|error| Status::internal(format!("failed to capture git status: {error}")))?;
            let patch_bytes = git_diff_bytes(&workspace_root).map_err(|error| {
                Status::internal(format!("failed to capture git diff: {error}"))
            })?;
            let untracked_bundle_bytes =
                build_untracked_bundle_bytes(&workspace_root).map_err(|error| {
                    Status::internal(format!("failed to capture untracked bundle: {error}"))
                })?;
            let has_untracked_bundle = !untracked_bundle_bytes.is_empty();
            let commit_sha = git_head_commit_sha(&workspace_root).map_err(|error| {
                Status::internal(format!("failed to capture git commit sha: {error}"))
            })?;
            let snapshot_json = serde_json::to_vec(&SnapshotPayload {
                kernel: KernelSnapshot {
                    service: SERVICE_NAME.to_string(),
                    started_at_ms: state.started_at_ms,
                    last_reconcile_at_ms: state.last_reconcile_at_ms,
                    active_environment_count: state.active_environment_count(),
                    known_task_count: state.tasks.len(),
                    authoritative: true,
                    production_ready: true,
                    maturity: "ga".to_string(),
                    authority_scope: AUTHORITY_SCOPE.to_string(),
                    authoritative_operations: AUTHORITATIVE_OPERATIONS
                        .split(',')
                        .map(str::trim)
                        .filter(|item| !item.is_empty())
                        .map(str::to_string)
                        .collect(),
                    full_authority: true,
                    partial_authority: false,
                    cutover_blockers: Vec::new(),
                    interactive_terminal_count: interactive_terminals.len(),
                    browser_session_count: browser_sessions.len(),
                    checkpoint_count: checkpoints.len(),
                },
                environment: EnvironmentSnapshot::from(environment),
                task: TaskSnapshot::from(task),
                terminal: terminal_records
                    .iter()
                    .map(TerminalSnapshot::from)
                    .collect::<Vec<_>>(),
                interactive_terminals,
                browser_sessions,
                checkpoints,
            })
            .map_err(|error| {
                Status::internal(format!("failed to encode checkpoint snapshot: {error}"))
            })?;
            let manifest_json = serde_json::to_vec(&serde_json::json!({
                "task": TaskSnapshot::from(task),
                "environment": EnvironmentSnapshot::from(environment),
                "checkpoint": {
                    "task_id": payload.task_id,
                    "environment_id": environment_id,
                    "success": payload.success,
                    "final_phase": payload.final_phase,
                    "manifest_path": manifest_path.display().to_string(),
                    "snapshot_path": snapshot_path.display().to_string(),
                    "patch_path": patch_path.display().to_string(),
                    "git_status_path": git_status_path.display().to_string(),
                    "untracked_bundle_path": untracked_bundle_path.display().to_string(),
                    "commit_sha": commit_sha,
                    "has_untracked_bundle": has_untracked_bundle,
                    "retention_hours": payload.retention_hours,
                    "saved_at_ms": now_ms(),
                }
            }))
            .map_err(|error| {
                Status::internal(format!("failed to encode checkpoint manifest: {error}"))
            })?;
            (
                manifest_json,
                snapshot_json,
                patch_bytes,
                git_status_text,
                untracked_bundle_bytes,
                commit_sha,
                has_untracked_bundle,
                workspace_path,
            )
        };
        fs::write(&manifest_path, &manifest_json)
            .await
            .map_err(|error| {
                Status::internal(format!("failed to write checkpoint manifest: {error}"))
            })?;
        fs::write(&snapshot_path, &snapshot_json)
            .await
            .map_err(|error| {
                Status::internal(format!("failed to write checkpoint snapshot: {error}"))
            })?;
        fs::write(&patch_path, &patch_bytes)
            .await
            .map_err(|error| {
                Status::internal(format!("failed to write checkpoint patch: {error}"))
            })?;
        fs::write(&git_status_path, git_status_text.as_bytes())
            .await
            .map_err(|error| Status::internal(format!("failed to write git status: {error}")))?;
        if has_untracked_bundle {
            fs::write(&untracked_bundle_path, &untracked_bundle_bytes)
                .await
                .map_err(|error| {
                    Status::internal(format!("failed to write untracked bundle: {error}"))
                })?;
        } else if untracked_bundle_path.exists() {
            let _ = fs::remove_file(&untracked_bundle_path).await;
        }
        let created_at_ms = now_ms();
        let expires_at_ms = (payload.retention_hours > 0)
            .then_some(created_at_ms + u64::from(payload.retention_hours) * 60 * 60 * 1000);
        let patch_bytes_len = patch_bytes.len();
        let checkpoint = CheckpointRecord {
            checkpoint_id: checkpoint_id.clone(),
            task_id: payload.task_id.clone(),
            environment_id: environment_id.clone(),
            workspace_path,
            success: payload.success,
            final_phase: payload.final_phase.clone(),
            checkpoint_dir: checkpoint_dir.clone(),
            manifest_path: manifest_path.clone(),
            snapshot_path: snapshot_path.clone(),
            patch_path: patch_path.clone(),
            git_status_path: git_status_path.clone(),
            untracked_bundle_path: untracked_bundle_path.clone(),
            commit_sha: commit_sha.clone(),
            has_untracked_bundle,
            created_at_ms,
            expires_at_ms,
        };
        let checkpoint_ref = Self::build_checkpoint_ref(&checkpoint);
        let mut state = self.state.write().expect("kernel state poisoned");
        state
            .task_to_checkpoints
            .entry(payload.task_id.clone())
            .or_default()
            .push(checkpoint_id.clone());
        state.checkpoints.insert(checkpoint_id, checkpoint);
        Self::append_terminal_line(
            &mut state,
            &payload.task_id,
            "system",
            format!(
                "checkpoint saved final_phase={} success={} patch_bytes={} has_untracked_bundle={}",
                empty_to_dash(&payload.final_phase),
                payload.success,
                patch_bytes_len,
                has_untracked_bundle
            ),
            false,
        );
        Ok(Response::new(SaveCheckpointResponse {
            checkpoint: Some(checkpoint_ref),
            saved: true,
        }))
    }

    async fn get_checkpoint(
        &self,
        request: Request<GetCheckpointRequest>,
    ) -> Result<Response<GetCheckpointResponse>, Status> {
        let payload = request.into_inner();
        let state = self.state.read().expect("kernel state poisoned");
        let checkpoint = if !payload.checkpoint_id.is_empty() {
            state.checkpoints.get(&payload.checkpoint_id)
        } else {
            state
                .task_to_checkpoints
                .get(&payload.task_id)
                .and_then(|items| items.last())
                .and_then(|checkpoint_id| state.checkpoints.get(checkpoint_id))
        };
        let Some(checkpoint) = checkpoint else {
            return Ok(Response::new(GetCheckpointResponse {
                checkpoint: None,
                found: false,
            }));
        };
        Ok(Response::new(GetCheckpointResponse {
            checkpoint: Some(Self::build_checkpoint_ref(checkpoint)),
            found: true,
        }))
    }

    async fn restore_checkpoint(
        &self,
        request: Request<RestoreCheckpointRequest>,
    ) -> Result<Response<RestoreCheckpointResponse>, Status> {
        let payload = request.into_inner();
        if payload.task_id.is_empty() {
            return Err(Status::invalid_argument("task_id is required"));
        }
        let (checkpoint, workspace_path) = {
            let state = self.state.read().expect("kernel state poisoned");
            let checkpoint = if !payload.checkpoint_id.is_empty() {
                state.checkpoints.get(&payload.checkpoint_id)
            } else {
                state
                    .task_to_checkpoints
                    .get(&payload.task_id)
                    .and_then(|items| items.last())
                    .and_then(|checkpoint_id| state.checkpoints.get(checkpoint_id))
            }
            .cloned();
            let workspace_path = if !payload.workspace_path.is_empty() {
                payload.workspace_path.clone()
            } else {
                checkpoint
                    .as_ref()
                    .map(|item| item.workspace_path.clone())
                    .filter(|path| !path.is_empty())
                    .or_else(|| {
                        state
                            .task_to_environment
                            .get(&payload.task_id)
                            .and_then(|environment_id| state.environments.get(environment_id))
                            .map(|environment| environment.workspace_path.clone())
                    })
                    .unwrap_or_default()
            };
            (checkpoint, workspace_path)
        };
        let Some(checkpoint) = checkpoint else {
            return Ok(Response::new(RestoreCheckpointResponse {
                checkpoint: None,
                found: false,
                restored: false,
                workspace_path,
                restored_commit_sha: String::new(),
                restored_paths: Vec::new(),
                error_message: "checkpoint not found".to_string(),
            }));
        };
        if workspace_path.is_empty() {
            return Ok(Response::new(RestoreCheckpointResponse {
                checkpoint: Some(Self::build_checkpoint_ref(&checkpoint)),
                found: true,
                restored: false,
                workspace_path,
                restored_commit_sha: String::new(),
                restored_paths: Vec::new(),
                error_message: "workspace_path_required".to_string(),
            }));
        }
        let restore_result = task::spawn_blocking({
            let checkpoint = checkpoint.clone();
            let workspace_path = workspace_path.clone();
            move || -> Result<RestoreCheckpointOutcome, String> {
                restore_checkpoint_bundle(&checkpoint, &workspace_path)
                    .map_err(|error| error.to_string())
            }
        })
        .await
        .map_err(|error| Status::internal(format!("checkpoint restore join failure: {error}")))?;

        match restore_result {
            Ok(outcome) => {
                let mut state = self.state.write().expect("kernel state poisoned");
                Self::append_terminal_line(
                    &mut state,
                    &payload.task_id,
                    "system",
                    format!(
                        "checkpoint restored final_phase={} commit_sha={}",
                        empty_to_dash(&checkpoint.final_phase),
                        empty_to_dash(&checkpoint.commit_sha)
                    ),
                    false,
                );
                Ok(Response::new(RestoreCheckpointResponse {
                    checkpoint: Some(Self::build_checkpoint_ref(&checkpoint)),
                    found: true,
                    restored: outcome.restored,
                    workspace_path: outcome.workspace_path,
                    restored_commit_sha: outcome.restored_commit_sha,
                    restored_paths: outcome.restored_paths,
                    error_message: outcome.error_message,
                }))
            }
            Err(error_message) => Ok(Response::new(RestoreCheckpointResponse {
                checkpoint: Some(Self::build_checkpoint_ref(&checkpoint)),
                found: true,
                restored: false,
                workspace_path,
                restored_commit_sha: checkpoint.commit_sha.clone(),
                restored_paths: Vec::new(),
                error_message,
            })),
        }
    }

    async fn health(
        &self,
        _request: Request<HealthRequest>,
    ) -> Result<Response<HealthResponse>, Status> {
        Ok(Response::new(self.runtime_health_response()))
    }
}

#[derive(Debug)]
struct KernelState {
    started_at_ms: u64,
    last_reconcile_at_ms: Option<u64>,
    environments: HashMap<String, EnvironmentRecord>,
    task_to_environment: HashMap<String, String>,
    tasks: HashMap<String, TaskRecord>,
    terminal_history: HashMap<String, Vec<TerminalRecord>>,
    interactive_terminals: HashMap<String, InteractiveTerminalRecord>,
    task_to_interactive_terminals: HashMap<String, Vec<String>>,
    interactive_terminal_history: HashMap<String, Vec<TerminalRecord>>,
    browser_sessions: HashMap<String, BrowserSessionRecord>,
    task_to_browser_sessions: HashMap<String, Vec<String>>,
    checkpoints: HashMap<String, CheckpointRecord>,
    task_to_checkpoints: HashMap<String, Vec<String>>,
}

impl KernelState {
    fn new() -> Self {
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
            browser_sessions: HashMap::new(),
            task_to_browser_sessions: HashMap::new(),
            checkpoints: HashMap::new(),
            task_to_checkpoints: HashMap::new(),
        }
    }

    fn active_environment_count(&self) -> usize {
        self.environments
            .values()
            .filter(|item| item.active)
            .count()
    }
}

#[derive(Clone, Debug)]
struct EnvironmentRecord {
    environment_id: String,
    task_id: String,
    agent_id: String,
    workspace_path: String,
    worktree_ref: String,
    branch_name: String,
    created_worktree: bool,
    worktree_mode: String,
    metadata_path: String,
    runtime_root: PathBuf,
    created_at_ms: u64,
    last_updated_at_ms: u64,
    active: bool,
    terminal_phase: String,
}

#[derive(Clone, Debug)]
struct TaskRecord {
    task_id: String,
    agent_id: String,
    environment_id: String,
    phase: String,
    process_id: Option<String>,
    pid: Option<i32>,
    pgid: Option<i32>,
    process_status: String,
    process_running: bool,
    exit_code: Option<i32>,
    command: String,
    args: Vec<String>,
    created_at_ms: u64,
    last_updated_at_ms: u64,
    started_at_ms: Option<u64>,
    finalized_at_ms: Option<u64>,
    pause_reason: Option<String>,
    finalize_error: Option<String>,
    sessions: BTreeSet<String>,
    stdout_terminal_id: Option<String>,
    stderr_terminal_id: Option<String>,
    stdout_eof: bool,
    stderr_eof: bool,
    terminal_closed_at_ms: Option<u64>,
    metadata: Option<RequestMetadata>,
}

impl TaskRecord {
    fn is_terminal(&self) -> bool {
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
struct TerminalRecord {
    stream: String,
    #[serde(serialize_with = "serialize_terminal_data")]
    data: Vec<u8>,
    eof: bool,
    timestamp_ms: u64,
}

#[derive(Serialize)]
struct SnapshotPayload {
    kernel: KernelSnapshot,
    environment: EnvironmentSnapshot,
    task: TaskSnapshot,
    terminal: Vec<TerminalSnapshot>,
    interactive_terminals: Vec<InteractiveTerminalSnapshot>,
    browser_sessions: Vec<BrowserSessionSnapshot>,
    checkpoints: Vec<CheckpointSnapshot>,
}

#[derive(Serialize)]
struct KernelSnapshot {
    service: String,
    started_at_ms: u64,
    last_reconcile_at_ms: Option<u64>,
    active_environment_count: usize,
    known_task_count: usize,
    authoritative: bool,
    production_ready: bool,
    maturity: String,
    authority_scope: String,
    authoritative_operations: Vec<String>,
    full_authority: bool,
    partial_authority: bool,
    cutover_blockers: Vec<String>,
    interactive_terminal_count: usize,
    browser_session_count: usize,
    checkpoint_count: usize,
}

#[derive(Serialize)]
struct EnvironmentSnapshot {
    environment_id: String,
    task_id: String,
    agent_id: String,
    workspace_path: String,
    worktree_ref: String,
    branch_name: String,
    created_worktree: bool,
    worktree_mode: String,
    metadata_path: String,
    runtime_root: String,
    active: bool,
    phase: String,
    created_at_ms: u64,
    last_updated_at_ms: u64,
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
struct TaskSnapshot {
    task_id: String,
    agent_id: String,
    environment_id: String,
    phase: String,
    final_phase: Option<String>,
    process_id: Option<String>,
    pid: Option<i32>,
    pgid: Option<i32>,
    process_status: String,
    process_running: bool,
    exit_code: Option<i32>,
    command: String,
    args: Vec<String>,
    created_at_ms: u64,
    last_updated_at_ms: u64,
    started_at_ms: Option<u64>,
    finalized_at_ms: Option<u64>,
    pause_reason: Option<String>,
    finalize_error: Option<String>,
    sessions: Vec<String>,
    stdout_terminal_id: Option<String>,
    stderr_terminal_id: Option<String>,
    metadata: Option<MetadataSnapshot>,
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
struct MetadataSnapshot {
    request_id: String,
    trace_id: String,
    agent_id: String,
    task_id: String,
    user_id: String,
    labels: HashMap<String, String>,
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
struct TerminalSnapshot {
    stream: String,
    data: String,
    eof: bool,
    timestamp_ms: u64,
}

#[derive(Clone, Debug)]
struct InteractiveTerminalRecord {
    session_id: String,
    task_id: String,
    environment_id: String,
    status: String,
    eof: bool,
    opened_at_ms: u64,
    closed_at_ms: Option<u64>,
    pid: Option<i32>,
    pgid: Option<i32>,
    exit_code: Option<i32>,
    command: String,
    args: Vec<String>,
    working_directory: String,
    cols: u32,
    rows: u32,
}

#[derive(Serialize)]
struct InteractiveTerminalSnapshot {
    session_id: String,
    task_id: String,
    environment_id: String,
    status: String,
    eof: bool,
    opened_at_ms: u64,
    closed_at_ms: Option<u64>,
    pid: Option<i32>,
    pgid: Option<i32>,
    exit_code: Option<i32>,
    command: String,
    args: Vec<String>,
    working_directory: String,
    cols: u32,
    rows: u32,
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
struct BrowserSessionRecord {
    session_id: String,
    task_id: String,
    environment_id: String,
    scope_id: String,
    transport: String,
    status: String,
    runtime_dir: String,
    display_id: Option<i32>,
    vnc_port: Option<i32>,
    novnc_port: Option<i32>,
    missing_binaries: Vec<String>,
    created_at_ms: u64,
    ended_at_ms: Option<u64>,
    metadata: HashMap<String, String>,
}

#[derive(Serialize)]
struct BrowserSessionSnapshot {
    session_id: String,
    task_id: String,
    environment_id: String,
    scope_id: String,
    transport: String,
    status: String,
    runtime_dir: String,
    display_id: Option<i32>,
    vnc_port: Option<i32>,
    novnc_port: Option<i32>,
    missing_binaries: Vec<String>,
    created_at_ms: u64,
    ended_at_ms: Option<u64>,
    metadata: HashMap<String, String>,
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
struct CheckpointRecord {
    checkpoint_id: String,
    task_id: String,
    environment_id: String,
    workspace_path: String,
    success: bool,
    final_phase: String,
    checkpoint_dir: PathBuf,
    manifest_path: PathBuf,
    snapshot_path: PathBuf,
    patch_path: PathBuf,
    git_status_path: PathBuf,
    untracked_bundle_path: PathBuf,
    commit_sha: String,
    has_untracked_bundle: bool,
    created_at_ms: u64,
    expires_at_ms: Option<u64>,
}

#[derive(Serialize)]
struct CheckpointSnapshot {
    checkpoint_id: String,
    task_id: String,
    environment_id: String,
    success: bool,
    final_phase: String,
    checkpoint_dir: String,
    manifest_path: String,
    snapshot_path: String,
    patch_path: String,
    git_status_path: String,
    untracked_bundle_path: String,
    commit_sha: String,
    has_untracked_bundle: bool,
    created_at_ms: u64,
    expires_at_ms: Option<u64>,
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

pub async fn serve(target: &str, server: RuntimeKernelServer) -> Result<()> {
    use tokio::net::UnixListener;
    use tokio_stream::wrappers::UnixListenerStream;
    use tonic::transport::Server;

    let service =
        koda_proto::runtime::v1::runtime_kernel_service_server::RuntimeKernelServiceServer::new(
            server.clone(),
        );

    info!(target, "starting runtime kernel");
    let uds_target = target.strip_prefix("unix://").unwrap_or(target);
    if target.starts_with("unix://") || target.starts_with('/') {
        if let Some(parent) = Path::new(uds_target).parent() {
            fs::create_dir_all(parent).await?;
        }
        if Path::new(uds_target).exists() {
            let _ = fs::remove_file(uds_target).await;
        }
        let listener = UnixListener::bind(uds_target)?;
        let incoming = UnixListenerStream::new(listener);
        Server::builder()
            .add_service(service)
            .serve_with_incoming_shutdown(incoming, shutdown_signal())
            .await?;
    } else {
        let addr = target.parse()?;
        Server::builder()
            .add_service(service)
            .serve_with_shutdown(addr, shutdown_signal())
            .await?;
    }
    Ok(())
}

async fn shutdown_signal() {
    let _ = tokio::signal::ctrl_c().await;
}

#[allow(clippy::result_large_err)]
fn get_environment_for_task(
    state: &KernelState,
    task_id: &str,
) -> Result<(String, String), Status> {
    let environment_id = state
        .task_to_environment
        .get(task_id)
        .cloned()
        .ok_or_else(|| {
            Status::failed_precondition(format!("environment not created for task: {task_id}"))
        })?;
    let agent_id = state
        .environments
        .get(&environment_id)
        .map(|item| item.agent_id.clone())
        .ok_or_else(|| Status::not_found(format!("environment not found: {environment_id}")))?;
    Ok((environment_id, agent_id))
}

fn non_empty_or(primary: String, fallback: Option<String>) -> String {
    if primary.is_empty() {
        fallback.unwrap_or_default()
    } else {
        primary
    }
}

fn empty_to_dash(value: &str) -> String {
    if value.is_empty() {
        "-".to_string()
    } else {
        value.to_string()
    }
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or(Duration::ZERO)
        .as_millis() as u64
}

#[derive(Default, Clone, Debug)]
struct RestoreCheckpointOutcome {
    restored: bool,
    workspace_path: String,
    restored_commit_sha: String,
    restored_paths: Vec<String>,
    error_message: String,
}

fn run_git_output(workspace_path: &Path, args: &[&str]) -> Result<String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(workspace_path)
        .args(args)
        .output()
        .map_err(|error| anyhow!("failed to run git {:?}: {error}", args))?;
    if !output.status.success() {
        return Ok(String::new());
    }
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

fn git_head_commit_sha(workspace_path: &Path) -> Result<String> {
    Ok(
        run_git_output(workspace_path, &["rev-parse", "--verify", "HEAD"])?
            .trim()
            .to_string(),
    )
}

fn git_diff_bytes(workspace_path: &Path) -> Result<Vec<u8>> {
    if !is_git_repo(workspace_path) {
        return Ok(Vec::new());
    }
    let has_head = !git_head_commit_sha(workspace_path)?.is_empty();
    let diff_args: &[&str] = if has_head {
        &["diff", "--binary", "--no-ext-diff", "HEAD"]
    } else {
        &["diff", "--binary", "--no-ext-diff", "--root"]
    };
    let output = Command::new("git")
        .arg("-C")
        .arg(workspace_path)
        .args(diff_args)
        .output()
        .map_err(|error| anyhow!("failed to capture git diff: {error}"))?;
    if !output.status.success() {
        return Ok(Vec::new());
    }
    Ok(output.stdout)
}

fn collect_untracked_paths(workspace_path: &Path) -> Result<Vec<String>> {
    if !is_git_repo(workspace_path) {
        return Ok(Vec::new());
    }
    let output = Command::new("git")
        .arg("-C")
        .arg(workspace_path)
        .args(["ls-files", "--others", "--exclude-standard", "-z"])
        .output()
        .map_err(|error| anyhow!("failed to enumerate untracked paths: {error}"))?;
    if !output.status.success() {
        return Ok(Vec::new());
    }
    Ok(output
        .stdout
        .split(|byte| *byte == 0)
        .filter_map(|item| {
            let value = String::from_utf8_lossy(item).trim().to_string();
            if value.is_empty() {
                None
            } else {
                Some(value)
            }
        })
        .collect())
}

fn build_untracked_bundle_bytes(workspace_path: &Path) -> Result<Vec<u8>> {
    let untracked_paths = collect_untracked_paths(workspace_path)?;
    if untracked_paths.is_empty() {
        return Ok(Vec::new());
    }
    let mut command = Command::new("tar");
    command.arg("-czf").arg("-").arg("-C").arg(workspace_path);
    for path in &untracked_paths {
        command.arg(path);
    }
    let output = command
        .output()
        .map_err(|error| anyhow!("failed to create untracked bundle: {error}"))?;
    if !output.status.success() {
        return Err(anyhow!(
            "failed to create untracked bundle: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    Ok(output.stdout)
}

fn validate_tar_listing(bundle_path: &Path) -> Result<()> {
    let output = Command::new("tar")
        .arg("-tzf")
        .arg(bundle_path)
        .output()
        .map_err(|error| anyhow!("failed to inspect checkpoint tar bundle: {error}"))?;
    if !output.status.success() {
        return Err(anyhow!(
            "checkpoint tar bundle listing failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    for raw_entry in stdout.lines() {
        let entry = raw_entry.trim();
        if entry.is_empty() {
            continue;
        }
        let path = Path::new(entry);
        if path.is_absolute()
            || path
                .components()
                .any(|component| matches!(component, Component::ParentDir | Component::RootDir))
        {
            return Err(anyhow!("checkpoint bundle contains path outside workspace"));
        }
    }
    Ok(())
}

fn run_git_restore(workspace_path: &Path, args: &[&str]) -> Result<bool> {
    let status = Command::new("git")
        .arg("-C")
        .arg(workspace_path)
        .args(args)
        .status()
        .map_err(|error| anyhow!("failed to run git {:?}: {error}", args))?;
    Ok(status.success())
}

fn restore_checkpoint_bundle(
    checkpoint: &CheckpointRecord,
    workspace_path: &str,
) -> Result<RestoreCheckpointOutcome> {
    let workspace = PathBuf::from(workspace_path);
    if !workspace.exists() {
        return Err(anyhow!("workspace path does not exist"));
    }
    let mut restored_paths = Vec::new();
    let mut restore_errors = Vec::new();
    if is_git_repo(&workspace) {
        if !checkpoint.commit_sha.is_empty() {
            if run_git_restore(
                &workspace,
                &["reset", "--hard", checkpoint.commit_sha.as_str()],
            )? {
                restored_paths.push("git_reset".to_string());
            } else {
                restore_errors.push("git_reset_failed".to_string());
            }
        } else if run_git_restore(&workspace, &["reset", "--hard"])? {
            restored_paths.push("git_reset_head".to_string());
        } else {
            restore_errors.push("git_reset_head_failed".to_string());
        }
        if checkpoint.patch_path.exists()
            && checkpoint
                .patch_path
                .metadata()
                .map(|metadata| metadata.len() > 0)
                .unwrap_or(false)
        {
            if run_git_restore(
                &workspace,
                &[
                    "apply",
                    "--check",
                    checkpoint.patch_path.to_string_lossy().as_ref(),
                ],
            )? {
                if run_git_restore(
                    &workspace,
                    &[
                        "apply",
                        "--whitespace=nowarn",
                        checkpoint.patch_path.to_string_lossy().as_ref(),
                    ],
                )? {
                    restored_paths.push("git_patch".to_string());
                } else {
                    restore_errors.push("git_patch_apply_failed".to_string());
                }
            } else if run_git_restore(
                &workspace,
                &[
                    "apply",
                    "--reverse",
                    "--check",
                    checkpoint.patch_path.to_string_lossy().as_ref(),
                ],
            )? {
                restored_paths.push("git_patch_already_applied".to_string());
            } else {
                restore_errors.push("git_patch_check_failed".to_string());
            }
        }
    } else if checkpoint.patch_path.exists()
        && checkpoint
            .patch_path
            .metadata()
            .map(|metadata| metadata.len() > 0)
            .unwrap_or(false)
    {
        restore_errors.push("git_repo_required_for_patch_restore".to_string());
    }
    if checkpoint.has_untracked_bundle
        && checkpoint.untracked_bundle_path.exists()
        && checkpoint
            .untracked_bundle_path
            .metadata()
            .map(|metadata| metadata.len() > 0)
            .unwrap_or(false)
    {
        validate_tar_listing(&checkpoint.untracked_bundle_path)?;
        let status = Command::new("tar")
            .arg("-xzf")
            .arg(&checkpoint.untracked_bundle_path)
            .arg("-C")
            .arg(&workspace)
            .status()
            .map_err(|error| anyhow!("failed to extract checkpoint tar bundle: {error}"))?;
        if status.success() {
            restored_paths.push("untracked_bundle".to_string());
        } else {
            restore_errors.push("untracked_bundle_extract_failed".to_string());
        }
    }
    Ok(RestoreCheckpointOutcome {
        restored: restore_errors.is_empty(),
        workspace_path: workspace.display().to_string(),
        restored_commit_sha: checkpoint.commit_sha.clone(),
        restored_paths,
        error_message: restore_errors.join(", "),
    })
}

fn serialize_terminal_data<S>(value: &[u8], serializer: S) -> Result<S::Ok, S::Error>
where
    S: serde::Serializer,
{
    serializer.serialize_str(&String::from_utf8_lossy(value))
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::Context;
    use tempfile::TempDir;
    use tokio_stream::StreamExt;

    fn metadata(agent_id: &str, task_id: &str) -> RequestMetadata {
        RequestMetadata {
            request_id: "req-1".to_string(),
            trace_id: "trace-1".to_string(),
            agent_id: agent_id.to_string(),
            task_id: task_id.to_string(),
            user_id: "user-1".to_string(),
            labels: HashMap::from([("env".to_string(), "test".to_string())]),
        }
    }

    fn test_server(tempdir: &TempDir) -> RuntimeKernelServer {
        RuntimeKernelServer::new(KernelConfig {
            runtime_root: tempdir.path().to_path_buf(),
        })
    }

    #[tokio::test]
    async fn lifecycle_transitions_update_health_and_snapshot() -> Result<()> {
        let tempdir = TempDir::new()?;
        let server = test_server(&tempdir);

        let create = server
            .create_environment(Request::new(CreateEnvironmentRequest {
                metadata: Some(metadata("agent-a", "task-1")),
                agent_id: "agent-a".to_string(),
                task_id: "task-1".to_string(),
                workspace_path: "/workspace/project".to_string(),
                worktree_ref: "wt-1".to_string(),
                base_work_dir: String::new(),
                slug: String::new(),
                create_worktree: false,
            }))
            .await?
            .into_inner();
        assert_eq!(
            create
                .environment
                .as_ref()
                .map(|item| item.environment_id.as_str()),
            Some("env-task-1")
        );
        assert!(Path::new(&create.runtime_root).exists());
        assert_eq!(create.workspace_path, "/workspace/project");

        let start = server
            .start_task(Request::new(StartTaskRequest {
                metadata: Some(metadata("agent-a", "task-1")),
                task_id: "task-1".to_string(),
                command: "/bin/sh".to_string(),
                args: vec!["-lc".to_string(), "sleep 30".to_string()],
                working_directory: String::new(),
                environment_overrides: HashMap::new(),
                stdin_payload: Vec::new(),
                start_new_session: true,
            }))
            .await?
            .into_inner();
        assert_eq!(start.phase, "executing");
        assert!(start.process_id.starts_with("proc-"));

        let attach = server
            .attach_terminal(Request::new(AttachTerminalRequest {
                metadata: Some(metadata("agent-a", "task-1")),
                task_id: "task-1".to_string(),
                session_id: "sess-1".to_string(),
            }))
            .await?
            .into_inner();
        assert!(attach.attached);

        let pause = server
            .pause_task(Request::new(PauseTaskRequest {
                metadata: Some(metadata("agent-a", "task-1")),
                task_id: "task-1".to_string(),
                reason: "manual".to_string(),
            }))
            .await?
            .into_inner();
        assert_eq!(pause.phase, "paused_for_operator");

        let resume = server
            .resume_task(Request::new(ResumeTaskRequest {
                metadata: Some(metadata("agent-a", "task-1")),
                task_id: "task-1".to_string(),
                phase: String::new(),
            }))
            .await?
            .into_inner();
        assert_eq!(resume.phase, "executing");

        let browser = server
            .start_browser_session(Request::new(StartBrowserSessionRequest {
                metadata: Some(metadata("agent-a", "task-1")),
                task_id: "task-1".to_string(),
                scope_id: "1".to_string(),
                runtime_dir: "/tmp/runtime/browser".to_string(),
                transport: "local_headful".to_string(),
                display_id: 0,
                vnc_port: 0,
                novnc_port: 0,
                missing_binaries: Vec::new(),
                metadata_labels: HashMap::from([("source".to_string(), "test".to_string())]),
            }))
            .await?
            .into_inner();
        assert!(browser.started);
        assert_eq!(
            browser.session.as_ref().map(|item| item.transport.as_str()),
            Some("local_headful")
        );

        let checkpoint = server
            .save_checkpoint(Request::new(SaveCheckpointRequest {
                metadata: Some(metadata("agent-a", "task-1")),
                task_id: "task-1".to_string(),
                environment_id: "env-task-1".to_string(),
                success: true,
                final_phase: "completed_retained".to_string(),
                retention_hours: 12,
            }))
            .await?
            .into_inner();
        assert!(checkpoint.saved);
        assert_eq!(
            checkpoint
                .checkpoint
                .as_ref()
                .map(|item| item.final_phase.as_str()),
            Some("completed_retained")
        );

        let snapshot = server
            .collect_snapshot(Request::new(CollectSnapshotRequest {
                metadata: Some(metadata("agent-a", "task-1")),
                task_id: "task-1".to_string(),
            }))
            .await?
            .into_inner();
        let payload: serde_json::Value =
            serde_json::from_slice(&snapshot.payload_json).context("snapshot should decode")?;
        assert_eq!(snapshot.task_phase, "executing");
        assert_eq!(snapshot.browser_session_count, 1);
        assert_eq!(snapshot.checkpoint_count, 1);
        assert_eq!(payload["task"]["phase"], "executing");
        assert_eq!(payload["environment"]["agent_id"], "agent-a");
        assert_eq!(payload["kernel"]["authoritative"], true);
        assert_eq!(payload["kernel"]["production_ready"], true);
        assert_eq!(payload["kernel"]["maturity"], "ga");
        assert_eq!(payload["kernel"]["browser_session_count"], 1);
        assert_eq!(payload["kernel"]["checkpoint_count"], 1);
        assert_eq!(payload["browser_sessions"][0]["transport"], "local_headful");
        assert_eq!(
            payload["checkpoints"][0]["final_phase"],
            "completed_retained"
        );
        assert!(payload["terminal"]
            .as_array()
            .is_some_and(|items| items.len() >= 3));

        let finalize = server
            .finalize_task(Request::new(FinalizeTaskRequest {
                metadata: Some(metadata("agent-a", "task-1")),
                task_id: "task-1".to_string(),
                success: true,
                error_message: String::new(),
                final_phase: String::new(),
            }))
            .await?
            .into_inner();
        assert_eq!(finalize.final_phase, "completed_retained");
        assert_eq!(finalize.environment_id, "env-task-1");

        let cleanup = server
            .cleanup_environment(Request::new(CleanupEnvironmentRequest {
                metadata: Some(metadata("agent-a", "task-1")),
                task_id: "task-1".to_string(),
                force: false,
            }))
            .await?
            .into_inner();
        assert!(cleanup.runtime_root_removed);

        let health = server
            .health(Request::new(HealthRequest {}))
            .await?
            .into_inner();
        assert!(health.ready);
        assert_eq!(health.status, "idle");
        assert_eq!(
            health
                .details
                .get("active_environments")
                .map(String::as_str),
            Some("0")
        );
        assert_eq!(
            health.details.get("authoritative").map(String::as_str),
            Some("true")
        );
        assert_eq!(
            health.details.get("production_ready").map(String::as_str),
            Some("true")
        );
        assert_eq!(
            health.details.get("authority_scope").map(String::as_str),
            Some(AUTHORITY_SCOPE)
        );

        Ok(())
    }

    #[tokio::test]
    async fn reconcile_returns_consistent_counts_after_finalize() -> Result<()> {
        let tempdir = TempDir::new()?;
        let server = test_server(&tempdir);

        server
            .create_environment(Request::new(CreateEnvironmentRequest {
                metadata: Some(metadata("agent-b", "task-2")),
                agent_id: "agent-b".to_string(),
                task_id: "task-2".to_string(),
                workspace_path: String::new(),
                worktree_ref: String::new(),
                base_work_dir: String::new(),
                slug: String::new(),
                create_worktree: false,
            }))
            .await?;
        server
            .start_task(Request::new(StartTaskRequest {
                metadata: Some(metadata("agent-b", "task-2")),
                task_id: "task-2".to_string(),
                command: "/bin/sh".to_string(),
                args: vec!["-lc".to_string(), "true".to_string()],
                working_directory: String::new(),
                environment_overrides: HashMap::new(),
                stdin_payload: Vec::new(),
                start_new_session: true,
            }))
            .await?;
        server
            .finalize_task(Request::new(FinalizeTaskRequest {
                metadata: Some(metadata("agent-b", "task-2")),
                task_id: "task-2".to_string(),
                success: false,
                error_message: "boom".to_string(),
                final_phase: String::new(),
            }))
            .await?;

        let reconcile = server
            .reconcile(Request::new(ReconcileRequest {
                metadata: Some(metadata("agent-b", "task-2")),
            }))
            .await?
            .into_inner();
        assert_eq!(reconcile.active_environments, 0);
        assert_eq!(reconcile.reconciled_environments, 0);

        let health = server
            .health(Request::new(HealthRequest {}))
            .await?
            .into_inner();
        assert_ne!(
            health
                .details
                .get("last_reconcile_at_ms")
                .map(String::as_str),
            Some("0")
        );

        Ok(())
    }

    #[tokio::test]
    async fn stream_terminal_returns_recorded_history_and_eof() -> Result<()> {
        let tempdir = TempDir::new()?;
        let server = test_server(&tempdir);
        server
            .create_environment(Request::new(CreateEnvironmentRequest {
                metadata: Some(metadata("agent-c", "task-3")),
                agent_id: "agent-c".to_string(),
                task_id: "task-3".to_string(),
                workspace_path: String::new(),
                worktree_ref: String::new(),
                base_work_dir: String::new(),
                slug: String::new(),
                create_worktree: false,
            }))
            .await?;
        server
            .start_task(Request::new(StartTaskRequest {
                metadata: Some(metadata("agent-c", "task-3")),
                task_id: "task-3".to_string(),
                command: "bash".to_string(),
                args: vec!["-lc".to_string(), "echo hi".to_string()],
                working_directory: String::new(),
                environment_overrides: HashMap::new(),
                stdin_payload: Vec::new(),
                start_new_session: true,
            }))
            .await?;

        let response = server
            .stream_terminal(Request::new(StreamTerminalRequest {
                metadata: Some(metadata("agent-c", "task-3")),
                task_id: "task-3".to_string(),
                stream: "system".to_string(),
            }))
            .await?
            .into_inner();
        let chunks: Vec<TerminalChunk> = response
            .collect::<Vec<_>>()
            .await
            .into_iter()
            .collect::<Result<Vec<_>, _>>()?;

        assert!(!chunks.is_empty());
        assert!(chunks.last().is_some_and(|item| item.eof));
        assert!(String::from_utf8_lossy(&chunks[0].data).contains("environment created"));

        Ok(())
    }

    #[tokio::test]
    async fn interactive_terminal_rpcs_roundtrip_with_real_pty() -> Result<()> {
        let tempdir = TempDir::new()?;
        let workspace = tempdir.path().join("workspace");
        stdfs::create_dir_all(&workspace)?;
        let server = test_server(&tempdir);
        server
            .create_environment(Request::new(CreateEnvironmentRequest {
                metadata: Some(metadata("agent-pty", "task-pty")),
                agent_id: "agent-pty".to_string(),
                task_id: "task-pty".to_string(),
                workspace_path: workspace.display().to_string(),
                worktree_ref: String::new(),
                base_work_dir: String::new(),
                slug: String::new(),
                create_worktree: false,
            }))
            .await?;

        let opened = server
            .open_terminal(Request::new(OpenTerminalRequest {
                metadata: Some(metadata("agent-pty", "task-pty")),
                task_id: "task-pty".to_string(),
                session_id: "session-pty".to_string(),
                command: "/bin/sh".to_string(),
                args: vec!["-i".to_string()],
                working_directory: workspace.display().to_string(),
                environment_overrides: HashMap::new(),
                cols: 120,
                rows: 32,
                stdin_payload: Vec::new(),
            }))
            .await?
            .into_inner();
        assert!(opened.opened);
        assert_eq!(
            opened
                .terminal
                .as_ref()
                .map(|terminal| terminal.session_id.as_str()),
            Some("session-pty")
        );

        let resized = server
            .resize_terminal(Request::new(ResizeTerminalRequest {
                metadata: Some(metadata("agent-pty", "task-pty")),
                task_id: "task-pty".to_string(),
                session_id: "session-pty".to_string(),
                cols: 140,
                rows: 40,
            }))
            .await?
            .into_inner();
        assert!(resized.resized);

        let _ = server
            .write_terminal(Request::new(WriteTerminalRequest {
                metadata: Some(metadata("agent-pty", "task-pty")),
                task_id: "task-pty".to_string(),
                session_id: "session-pty".to_string(),
                data: b"printf 'hello-from-pty\\n'; exit\n".to_vec(),
                eof: false,
            }))
            .await?
            .into_inner();

        let response = server
            .stream_terminal_session(Request::new(StreamTerminalSessionRequest {
                metadata: Some(metadata("agent-pty", "task-pty")),
                task_id: "task-pty".to_string(),
                session_id: "session-pty".to_string(),
            }))
            .await?
            .into_inner();
        let chunks: Vec<TerminalChunk> = response
            .collect::<Vec<_>>()
            .await
            .into_iter()
            .collect::<Result<Vec<_>, _>>()?;
        let combined = chunks
            .iter()
            .map(|chunk| String::from_utf8_lossy(&chunk.data).into_owned())
            .collect::<Vec<_>>()
            .join("");

        assert!(combined.contains("hello-from-pty"));
        assert!(chunks.last().is_some_and(|item| item.eof));
        assert!(chunks.iter().all(|chunk| chunk.session_id == "session-pty"));

        Ok(())
    }

    #[tokio::test]
    async fn checkpoint_restore_replays_patch_payload_in_kernel() -> Result<()> {
        let tempdir = TempDir::new()?;
        let workspace = tempdir.path().join("workspace");
        stdfs::create_dir_all(&workspace)?;
        let git = |args: &[&str]| -> Result<()> {
            let status = Command::new("git").args(args).status()?;
            if !status.success() {
                return Err(anyhow!("git command failed: {:?}", args));
            }
            Ok(())
        };
        git(&["-C", workspace.to_str().unwrap_or_default(), "init"])?;
        git(&[
            "-C",
            workspace.to_str().unwrap_or_default(),
            "config",
            "user.email",
            "test@example.com",
        ])?;
        git(&[
            "-C",
            workspace.to_str().unwrap_or_default(),
            "config",
            "user.name",
            "Test User",
        ])?;
        stdfs::write(workspace.join("file.txt"), "before\n")?;
        git(&[
            "-C",
            workspace.to_str().unwrap_or_default(),
            "add",
            "file.txt",
        ])?;
        git(&[
            "-C",
            workspace.to_str().unwrap_or_default(),
            "commit",
            "-m",
            "initial",
        ])?;

        stdfs::write(workspace.join("file.txt"), "after\n")?;
        let patch_output = Command::new("git")
            .arg("-C")
            .arg(&workspace)
            .arg("diff")
            .output()?;
        let commit_sha = String::from_utf8(
            Command::new("git")
                .arg("-C")
                .arg(&workspace)
                .arg("rev-parse")
                .arg("HEAD")
                .output()?
                .stdout,
        )?
        .trim()
        .to_string();
        let server = test_server(&tempdir);
        server
            .create_environment(Request::new(CreateEnvironmentRequest {
                metadata: Some(metadata("agent-ckpt", "task-ckpt")),
                agent_id: "agent-ckpt".to_string(),
                task_id: "task-ckpt".to_string(),
                workspace_path: workspace.display().to_string(),
                worktree_ref: String::new(),
                base_work_dir: String::new(),
                slug: String::new(),
                create_worktree: false,
            }))
            .await?;

        let saved = server
            .save_checkpoint(Request::new(SaveCheckpointRequest {
                metadata: Some(metadata("agent-ckpt", "task-ckpt")),
                task_id: "task-ckpt".to_string(),
                environment_id: "env-task-ckpt".to_string(),
                success: true,
                final_phase: "completed_retained".to_string(),
                retention_hours: 24,
            }))
            .await?
            .into_inner();
        let checkpoint_id = saved
            .checkpoint
            .as_ref()
            .map(|checkpoint| checkpoint.checkpoint_id.clone())
            .context("checkpoint id should be present")?;
        git(&[
            "-C",
            workspace.to_str().unwrap_or_default(),
            "checkout",
            "--",
            "file.txt",
        ])?;

        let restored = server
            .restore_checkpoint(Request::new(RestoreCheckpointRequest {
                metadata: Some(metadata("agent-ckpt", "task-ckpt")),
                task_id: "task-ckpt".to_string(),
                checkpoint_id: checkpoint_id.clone(),
                workspace_path: workspace.display().to_string(),
            }))
            .await?
            .into_inner();
        assert!(restored.found);
        assert!(restored.restored);
        assert_eq!(restored.restored_commit_sha, commit_sha);
        assert_eq!(
            stdfs::read_to_string(workspace.join("file.txt"))?,
            "after\n"
        );

        let fetched = server
            .get_checkpoint(Request::new(GetCheckpointRequest {
                metadata: Some(metadata("agent-ckpt", "task-ckpt")),
                task_id: "task-ckpt".to_string(),
                checkpoint_id,
            }))
            .await?
            .into_inner();
        assert!(fetched.found);
        let checkpoint_ref = fetched
            .checkpoint
            .as_ref()
            .context("checkpoint should be present")?;
        assert!(Path::new(&checkpoint_ref.patch_path).exists());
        assert_eq!(
            stdfs::read(checkpoint_ref.patch_path.clone())?,
            patch_output.stdout
        );
        assert!(
            stdfs::read_to_string(checkpoint_ref.git_status_path.clone())?.contains("file.txt")
        );

        Ok(())
    }

    #[tokio::test]
    async fn browser_and_checkpoint_rpcs_roundtrip() -> Result<()> {
        let tempdir = TempDir::new()?;
        let server = test_server(&tempdir);
        server
            .create_environment(Request::new(CreateEnvironmentRequest {
                metadata: Some(metadata("agent-d", "task-4")),
                agent_id: "agent-d".to_string(),
                task_id: "task-4".to_string(),
                workspace_path: String::new(),
                worktree_ref: String::new(),
                base_work_dir: String::new(),
                slug: String::new(),
                create_worktree: false,
            }))
            .await?;

        let browser = server
            .start_browser_session(Request::new(StartBrowserSessionRequest {
                metadata: Some(metadata("agent-d", "task-4")),
                task_id: "task-4".to_string(),
                scope_id: "99".to_string(),
                runtime_dir: "/tmp/browser".to_string(),
                transport: "novnc".to_string(),
                display_id: 12,
                vnc_port: 5901,
                novnc_port: 6081,
                missing_binaries: vec!["Xvfb".to_string()],
                metadata_labels: HashMap::from([("mode".to_string(), "shadow".to_string())]),
            }))
            .await?
            .into_inner();
        assert!(browser.started);
        let fetched_browser = server
            .get_browser_session(Request::new(GetBrowserSessionRequest {
                metadata: Some(metadata("agent-d", "task-4")),
                task_id: "task-4".to_string(),
                scope_id: "99".to_string(),
            }))
            .await?
            .into_inner();
        assert!(fetched_browser.found);
        assert_eq!(
            fetched_browser.session.as_ref().map(|item| item.vnc_port),
            Some(5901)
        );
        let stopped_browser = server
            .stop_browser_session(Request::new(StopBrowserSessionRequest {
                metadata: Some(metadata("agent-d", "task-4")),
                task_id: "task-4".to_string(),
                scope_id: "99".to_string(),
                force: true,
            }))
            .await?
            .into_inner();
        assert!(stopped_browser.stopped);
        assert_eq!(stopped_browser.status, "closed");

        let checkpoint = server
            .save_checkpoint(Request::new(SaveCheckpointRequest {
                metadata: Some(metadata("agent-d", "task-4")),
                task_id: "task-4".to_string(),
                environment_id: "env-task-4".to_string(),
                success: false,
                final_phase: "recoverable_failed_retained".to_string(),
                retention_hours: 1,
            }))
            .await?
            .into_inner();
        assert!(checkpoint.saved);
        let fetched_checkpoint = server
            .get_checkpoint(Request::new(GetCheckpointRequest {
                metadata: Some(metadata("agent-d", "task-4")),
                task_id: "task-4".to_string(),
                checkpoint_id: checkpoint
                    .checkpoint
                    .as_ref()
                    .map(|item| item.checkpoint_id.clone())
                    .unwrap_or_default(),
            }))
            .await?
            .into_inner();
        assert!(fetched_checkpoint.found);
        let checkpoint_ref = fetched_checkpoint
            .checkpoint
            .as_ref()
            .context("checkpoint should be present")?;
        assert!(Path::new(&checkpoint_ref.manifest_path).exists());
        assert!(Path::new(&checkpoint_ref.snapshot_path).exists());

        Ok(())
    }
}
