//! Agent worker lifecycle owned by the runtime-kernel.
//!
//! ## Why this lives here
//!
//! Until this module shipped, the Python control-plane supervisor spawned
//! agent workers itself via `asyncio.create_subprocess_exec`. That made the
//! supervisor the OS-level parent of every worker, so a SIGKILL'd
//! supervisor left the workers re-parented to PID 1 — orphans that held
//! their health ports until a human operator killed them. The next
//! supervisor instance then crashed on `EADDRINUSE`, the surrounding sync
//! DB writes saturated the asyncio event loop, and `/health` appeared to
//! hang.
//!
//! The runtime-kernel already owns process spawn lifecycle elsewhere
//! (`StartTask`/`TerminateTask`/`ExecuteCommand`). Moving agent worker
//! lifecycle here closes the architectural gap: the kernel becomes the
//! sole process parent of agent workers, the supervisor degrades to a
//! stateless declarative client (`EnsureAgentWorkers(desired)`), and
//! orphans cease to exist by construction.
//!
//! ## Lifecycle invariants
//!
//! 1. `agent_id` is the canonical registry key. The kernel guarantees
//!    at-most-one running worker per agent_id. Concurrent
//!    `EnsureAgentWorkers` calls serialise on a single registry mutex —
//!    we never spawn twice for the same agent.
//! 2. Spawn is preceded by a non-disruptive bind probe on the worker's
//!    health port. If the port is held by a process we don't recognise,
//!    the spawn is refused with `Spawn_Blocked` instead of fighting the
//!    holder. This matters when an old worker survived a kernel crash;
//!    the kernel sweeps those orphans on startup but a foreign listener
//!    on the same port is the operator's problem to clear.
//! 3. Every spawned worker is its own process group leader (`setsid`).
//!    On Linux we additionally request `PR_SET_PDEATHSIG=SIGTERM` so
//!    the kernel dying takes its workers down with it (no orphans).
//! 4. A reaper task per worker awaits `Child.wait()` and transitions
//!    state to `Exited` with the captured exit code. The next reconcile
//!    cycle decides whether to respawn (if still desired) or leave it
//!    out (if removed from the desired set).
//! 5. A health monitor task per worker probes
//!    `http://127.0.0.1:<health_port><health_path>` every
//!    `HEALTH_PROBE_INTERVAL`. After
//!    `HEALTH_FAILURE_THRESHOLD` consecutive failures the state flips
//!    to `Unhealthy`; a single success flips it back. The monitor
//!    never restarts the worker — that is the supervisor's policy.

use std::collections::{HashMap, HashSet};
use std::process::Stdio;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::Result;
use koda_proto::runtime::v1::{
    agent_worker_status::State as AgentWorkerStateProto, AgentWorkerSpec, AgentWorkerStatus,
};
use serde::{Deserialize, Serialize};

use crate::isolation;
use tokio::net::TcpListener;
use tokio::process::{Child, Command as TokioCommand};
use tokio::sync::{Mutex, RwLock};
use tokio::task::JoinHandle;
use tokio::time::{sleep, timeout, Duration};
use tracing::{debug, warn};

/// How long the kernel waits between consecutive health probes for a
/// running worker. 5s is a reasonable balance: tight enough that an
/// unhealthy worker is flagged within 25s, loose enough that the probe
/// overhead is invisible in stats.
const HEALTH_PROBE_INTERVAL: Duration = Duration::from_secs(5);

/// Per-probe deadline. Workers respond to /health in milliseconds when
/// healthy; 1.5s is far above noise and well below the probe interval.
const HEALTH_PROBE_TIMEOUT: Duration = Duration::from_millis(1500);

/// Number of consecutive probe failures before the kernel moves a
/// worker from `Running` to `Unhealthy`. A single transient blip
/// shouldn't downgrade an otherwise healthy worker.
const HEALTH_FAILURE_THRESHOLD: u32 = 5;

/// Grace period between SIGTERM and SIGKILL during termination. Workers
/// get a chance to flush state (cancel Telegram polling, drain
/// in-flight queries) before the kernel forces them down.
const TERMINATE_GRACE: Duration = Duration::from_secs(15);

/// Internal state machine. Mirrors the proto enum but lives in code so
/// transitions can be matched exhaustively.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum AgentWorkerState {
    Starting,
    Running,
    Unhealthy,
    Exited,
    SpawnBlocked,
    Terminated,
}

impl AgentWorkerState {
    fn to_proto(self) -> AgentWorkerStateProto {
        match self {
            Self::Starting => AgentWorkerStateProto::Starting,
            Self::Running => AgentWorkerStateProto::Running,
            Self::Unhealthy => AgentWorkerStateProto::Unhealthy,
            Self::Exited => AgentWorkerStateProto::Exited,
            Self::SpawnBlocked => AgentWorkerStateProto::SpawnBlocked,
            Self::Terminated => AgentWorkerStateProto::Terminated,
        }
    }
}

/// Snapshot of worker state safe to expose over gRPC. Fields mirror
/// `AgentWorkerStatus` 1:1 so conversion is a plain field copy.
#[derive(Clone, Debug)]
pub struct WorkerSnapshot {
    agent_id: String,
    version: i32,
    state: AgentWorkerState,
    pid: i32,
    pgid: i32,
    exit_code: i32,
    started_at_ms: u64,
    last_health_at_ms: u64,
    restart_count: u32,
    spawn_blocked_reason: String,
}

impl WorkerSnapshot {
    fn to_proto(&self) -> AgentWorkerStatus {
        AgentWorkerStatus {
            agent_id: self.agent_id.clone(),
            version: self.version,
            state: self.state.to_proto() as i32,
            pid: self.pid,
            pgid: self.pgid,
            exit_code: self.exit_code,
            started_at_ms: self.started_at_ms,
            last_health_at_ms: self.last_health_at_ms,
            restart_count: self.restart_count,
            spawn_blocked_reason: self.spawn_blocked_reason.clone(),
        }
    }
}

/// Trait that lets tests replace the spawn surface and HTTP probe with
/// fakes. Default implementation in `RealRuntimeAdapter` does the real
/// thing (TcpListener bind probe, `tokio::process::Command` spawn,
/// `reqwest`-free HTTP probe via `tokio::net::TcpStream` + manual
/// HTTP/1.1 GET). Tests provide deterministic stubs.
#[async_trait::async_trait]
pub trait RuntimeAdapter: Send + Sync + 'static {
    /// Returns Ok(()) when the port is currently free, Err with the
    /// reason when it's held.
    async fn probe_port_free(&self, host: &str, port: u16) -> Result<(), String>;

    /// Spawn a worker. Returns the OS PID (or 0 if not available),
    /// tokio Child handle, and the moment of spawn.
    async fn spawn_worker(&self, spec: &AgentWorkerSpec) -> Result<SpawnHandle, String>;

    /// Probe the worker's health endpoint. Returns Ok when the response
    /// is HTTP 2xx; Err with a short error tag otherwise. Implementations
    /// must respect `HEALTH_PROBE_TIMEOUT`.
    async fn probe_health(&self, host: &str, port: u16, path: &str) -> Result<(), String>;
}

/// Spawn outcome from the adapter.
pub struct SpawnHandle {
    pub child: Child,
    pub pid: i32,
    pub pgid: i32,
}

/// In-memory record per managed worker. Holds the OS handle (Child),
/// monitor task handles, and a snapshot the registry copies on read.
struct ManagedWorker {
    snapshot: WorkerSnapshot,
    child: Option<Child>,
    /// Background tasks (reaper + health monitor). Aborted on terminate.
    monitors: Vec<JoinHandle<()>>,
}

impl ManagedWorker {
    fn snapshot(&self) -> WorkerSnapshot {
        self.snapshot.clone()
    }

    fn shutdown_monitors(&mut self) {
        for handle in self.monitors.drain(..) {
            handle.abort();
        }
    }
}

/// Registry of all managed workers. Cloneable (Arc inside) so
/// background tasks can hold their own handle without lifetime
/// gymnastics.
#[derive(Clone)]
pub struct AgentWorkerRegistry {
    inner: Arc<RegistryInner>,
}

struct RegistryInner {
    workers: RwLock<HashMap<String, Arc<Mutex<ManagedWorker>>>>,
    adapter: Arc<dyn RuntimeAdapter>,
}

impl AgentWorkerRegistry {
    pub fn new(adapter: Arc<dyn RuntimeAdapter>) -> Self {
        Self {
            inner: Arc::new(RegistryInner {
                workers: RwLock::new(HashMap::new()),
                adapter,
            }),
        }
    }

    /// Apply the desired set: spawn missing, terminate extras, restart
    /// version-mismatched. Returns the post-application snapshot plus
    /// counters so the supervisor can audit the diff.
    pub async fn ensure(&self, desired: Vec<AgentWorkerSpec>) -> EnsureOutcome {
        let mut spawned = 0u32;
        let mut terminated = 0u32;
        let mut restarted = 0u32;
        let mut unchanged = 0u32;

        // Build a desired map keyed by agent_id; reject blank ids defensively.
        let mut desired_map: HashMap<String, AgentWorkerSpec> = HashMap::new();
        for spec in desired {
            if spec.agent_id.is_empty() {
                continue;
            }
            desired_map.insert(spec.agent_id.clone(), spec);
        }
        let desired_ids: HashSet<String> = desired_map.keys().cloned().collect();

        // Snapshot the current set under a brief read lock.
        let current_ids: HashSet<String> = {
            let guard = self.inner.workers.read().await;
            guard.keys().cloned().collect()
        };

        // Phase 1: terminate workers that are no longer desired.
        for agent_id in current_ids.difference(&desired_ids) {
            if self.terminate_internal(agent_id, false).await {
                terminated += 1;
            }
        }

        // Phase 2: for each desired spec, spawn or maybe-restart.
        for (agent_id, spec) in desired_map.into_iter() {
            let (existing_version, existing_state) = {
                let guard = self.inner.workers.read().await;
                if let Some(entry) = guard.get(&agent_id) {
                    let snap = entry.lock().await.snapshot();
                    (Some(snap.version), Some(snap.state))
                } else {
                    (None, None)
                }
            };

            match (existing_version, existing_state) {
                (None, _) => {
                    // Not in registry → fresh spawn.
                    self.spawn(spec).await;
                    spawned += 1;
                }
                (Some(v), Some(state))
                    if state == AgentWorkerState::Exited
                        || state == AgentWorkerState::Terminated
                        || state == AgentWorkerState::SpawnBlocked =>
                {
                    // Worker is gone or never started — respawn even if version matches.
                    let _ = v; // matched but unused
                    self.terminate_internal(&agent_id, true).await;
                    self.spawn(spec).await;
                    spawned += 1;
                }
                (Some(v), Some(_)) if v != spec.version => {
                    // Running worker on the wrong version → graceful restart.
                    self.terminate_internal(&agent_id, false).await;
                    self.spawn(spec).await;
                    restarted += 1;
                }
                _ => {
                    unchanged += 1;
                }
            }
        }

        // Snapshot final state.
        let current = self.list_snapshots().await;
        EnsureOutcome {
            current,
            spawned,
            terminated,
            restarted,
            unchanged,
        }
    }

    pub async fn get(&self, agent_id: &str) -> Option<WorkerSnapshot> {
        let guard = self.inner.workers.read().await;
        if let Some(entry) = guard.get(agent_id) {
            Some(entry.lock().await.snapshot())
        } else {
            None
        }
    }

    pub async fn terminate(&self, agent_id: &str, force: bool) -> Option<WorkerSnapshot> {
        self.terminate_internal(agent_id, force).await;
        self.get(agent_id).await
    }

    /// Best-effort termination of every tracked worker. Used during
    /// kernel shutdown so we don't leak children when the kernel exits.
    pub async fn terminate_all(&self) {
        let agent_ids: Vec<String> = {
            let guard = self.inner.workers.read().await;
            guard.keys().cloned().collect()
        };
        for agent_id in agent_ids {
            self.terminate_internal(&agent_id, true).await;
        }
    }

    /// Snapshot every worker. Returned in stable order (sorted by
    /// agent_id) so callers can diff outputs deterministically.
    pub async fn list_snapshots(&self) -> Vec<WorkerSnapshot> {
        let guard = self.inner.workers.read().await;
        let mut entries: Vec<(String, Arc<Mutex<ManagedWorker>>)> =
            guard.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
        drop(guard);
        entries.sort_by(|a, b| a.0.cmp(&b.0));
        let mut out = Vec::with_capacity(entries.len());
        for (_, entry) in entries {
            out.push(entry.lock().await.snapshot());
        }
        out
    }

    /// Internal: spawn one worker. Performs the port pre-flight check;
    /// records SpawnBlocked instead of fighting a foreign holder.
    async fn spawn(&self, spec: AgentWorkerSpec) {
        let agent_id = spec.agent_id.clone();
        let now_ms = now_millis();

        // Pre-flight port check. health_port == 0 means "no probe", so we
        // skip the bind probe and the health monitor.
        let port = u16::try_from(spec.health_port).ok().filter(|p| *p > 0);
        if let Some(port) = port {
            if let Err(reason) = self.inner.adapter.probe_port_free("127.0.0.1", port).await {
                let snapshot = WorkerSnapshot {
                    agent_id: agent_id.clone(),
                    version: spec.version,
                    state: AgentWorkerState::SpawnBlocked,
                    pid: 0,
                    pgid: 0,
                    exit_code: 0,
                    started_at_ms: now_ms,
                    last_health_at_ms: 0,
                    restart_count: 0,
                    spawn_blocked_reason: reason,
                };
                let entry = ManagedWorker {
                    snapshot,
                    child: None,
                    monitors: Vec::new(),
                };
                let mut guard = self.inner.workers.write().await;
                guard.insert(agent_id, Arc::new(Mutex::new(entry)));
                return;
            }
        }

        // Hand off to the adapter for the actual spawn.
        let spawn_result = self.inner.adapter.spawn_worker(&spec).await;
        let SpawnHandle { child, pid, pgid } = match spawn_result {
            Ok(h) => h,
            Err(reason) => {
                warn!(agent_id = %agent_id, reason = %reason, "agent_worker_spawn_failed");
                let snapshot = WorkerSnapshot {
                    agent_id: agent_id.clone(),
                    version: spec.version,
                    state: AgentWorkerState::SpawnBlocked,
                    pid: 0,
                    pgid: 0,
                    exit_code: 0,
                    started_at_ms: now_ms,
                    last_health_at_ms: 0,
                    restart_count: 0,
                    spawn_blocked_reason: reason,
                };
                let entry = ManagedWorker {
                    snapshot,
                    child: None,
                    monitors: Vec::new(),
                };
                let mut guard = self.inner.workers.write().await;
                guard.insert(agent_id, Arc::new(Mutex::new(entry)));
                return;
            }
        };

        let snapshot = WorkerSnapshot {
            agent_id: agent_id.clone(),
            version: spec.version,
            state: AgentWorkerState::Starting,
            pid,
            pgid,
            exit_code: 0,
            started_at_ms: now_ms,
            last_health_at_ms: 0,
            restart_count: 0,
            spawn_blocked_reason: String::new(),
        };

        let entry = Arc::new(Mutex::new(ManagedWorker {
            snapshot,
            child: Some(child),
            monitors: Vec::new(),
        }));

        // Register first, then start monitors so they can find the entry.
        {
            let mut guard = self.inner.workers.write().await;
            guard.insert(agent_id.clone(), entry.clone());
        }

        // Reaper: awaits Child.wait() and flips state to Exited. Holds a
        // weak handle (well, an Arc clone) to avoid keeping the kernel
        // alive past shutdown.
        let reaper = tokio::spawn(reaper_loop(entry.clone()));
        // Health monitor: probes the worker periodically.
        let health = if let Some(port) = port {
            let path = if spec.health_path.is_empty() {
                "/health".to_string()
            } else {
                spec.health_path.clone()
            };
            Some(tokio::spawn(health_monitor_loop(
                entry.clone(),
                self.inner.adapter.clone(),
                port,
                path,
            )))
        } else {
            None
        };

        let mut guard = entry.lock().await;
        guard.monitors.push(reaper);
        if let Some(h) = health {
            guard.monitors.push(h);
        }
    }

    async fn terminate_internal(&self, agent_id: &str, force: bool) -> bool {
        let entry = {
            let guard = self.inner.workers.read().await;
            guard.get(agent_id).cloned()
        };
        let Some(entry) = entry else {
            return false;
        };

        // Take child + monitors under the lock; release the lock before
        // we await child.wait() so the registry stays responsive.
        let (child_opt, pid, pgid) = {
            let mut worker = entry.lock().await;
            worker.shutdown_monitors();
            let child = worker.child.take();
            (child, worker.snapshot.pid, worker.snapshot.pgid)
        };

        if let Some(mut child) = child_opt {
            let _ = pgid; // pgid available if we want to log it
            if force {
                // Force: skip the grace period, SIGKILL the whole pgid
                // immediately. Used for shutdown-blocked workers and tests.
                send_signal(&mut child, libc::SIGKILL);
            } else {
                // Graceful: SIGTERM, give the worker `TERMINATE_GRACE`
                // to flush state, then SIGKILL if it's still alive.
                send_signal(&mut child, libc::SIGTERM);
                if timeout(TERMINATE_GRACE, child.wait()).await.is_err() {
                    send_signal(&mut child, libc::SIGKILL);
                }
            }
            // Either way, reap the child so we don't leak a zombie.
            let _ = child.wait().await;
            debug!(agent_id, pid, "agent_worker_terminated");
        }

        // Mark Terminated. The entry stays in the registry until the
        // next ensure() removes it (so callers can read final state).
        {
            let mut worker = entry.lock().await;
            worker.snapshot.state = AgentWorkerState::Terminated;
        }
        // Now drop from the registry so the next ensure() doesn't see
        // it as "still there but Terminated" and skip respawn.
        {
            let mut guard = self.inner.workers.write().await;
            guard.remove(agent_id);
        }
        true
    }
}

/// Returned by `ensure`. Mirrors `EnsureAgentWorkersResponse` shape so
/// callers can convert with one trivial helper.
#[derive(Debug)]
pub struct EnsureOutcome {
    pub current: Vec<WorkerSnapshot>,
    pub spawned: u32,
    pub terminated: u32,
    pub restarted: u32,
    pub unchanged: u32,
}

impl EnsureOutcome {
    pub fn current_protos(&self) -> Vec<AgentWorkerStatus> {
        self.current.iter().map(|s| s.to_proto()).collect()
    }
}

/// Background task: await Child.wait() and flip state to Exited. The
/// reaper task does NOT respawn — that's the supervisor's call on the
/// next reconcile.
async fn reaper_loop(entry: Arc<Mutex<ManagedWorker>>) {
    // Take the Child OUT of the worker so we can await wait() without
    // holding the lock. If the child was already taken by terminate(),
    // there's nothing to reap and the task exits.
    let child_opt = {
        let mut worker = entry.lock().await;
        worker.child.take()
    };
    let Some(mut child) = child_opt else {
        return;
    };
    let exit_status = child.wait().await;
    let exit_code = exit_status.ok().and_then(|s| s.code()).unwrap_or(-1);
    let mut worker = entry.lock().await;
    worker.snapshot.state = AgentWorkerState::Exited;
    worker.snapshot.exit_code = exit_code;
    worker.shutdown_monitors();
}

/// Background task: probe /health periodically and update state.
async fn health_monitor_loop(
    entry: Arc<Mutex<ManagedWorker>>,
    adapter: Arc<dyn RuntimeAdapter>,
    port: u16,
    path: String,
) {
    let mut consecutive_failures: u32 = 0;
    loop {
        sleep(HEALTH_PROBE_INTERVAL).await;
        // Cheap exit when terminated/exited.
        {
            let worker = entry.lock().await;
            match worker.snapshot.state {
                AgentWorkerState::Terminated | AgentWorkerState::Exited => return,
                _ => {}
            }
        }
        let probe = adapter.probe_health("127.0.0.1", port, &path).await;
        let mut worker = entry.lock().await;
        match probe {
            Ok(()) => {
                consecutive_failures = 0;
                worker.snapshot.state = AgentWorkerState::Running;
                worker.snapshot.last_health_at_ms = now_millis();
            }
            Err(_) => {
                consecutive_failures += 1;
                if consecutive_failures >= HEALTH_FAILURE_THRESHOLD {
                    worker.snapshot.state = AgentWorkerState::Unhealthy;
                }
            }
        }
    }
}

fn send_signal(child: &mut Child, sig: i32) {
    if let Some(pid) = child.id() {
        // Send to the process group so the whole tree dies (worker
        // spawned grandchildren survive the parent otherwise).
        let pgid = pid as i32;
        unsafe {
            libc::killpg(pgid, sig);
        }
    }
}

fn now_millis() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

// --------------------------------------------------------------------- //
//  Real adapter (production)                                             //
// --------------------------------------------------------------------- //

/// Production adapter. Uses tokio::net for the bind probe, tokio::process
/// for spawn (with setsid + Linux PR_SET_PDEATHSIG), and a hand-rolled
/// HTTP/1.1 GET for the health probe so the runtime-kernel doesn't take a
/// transitive dependency on a full HTTP client.
pub struct RealRuntimeAdapter;

#[async_trait::async_trait]
impl RuntimeAdapter for RealRuntimeAdapter {
    async fn probe_port_free(&self, host: &str, port: u16) -> Result<(), String> {
        let addr = format!("{host}:{port}");
        match TcpListener::bind(&addr).await {
            Ok(listener) => {
                drop(listener);
                Ok(())
            }
            Err(e) => Err(format!("port_in_use: {e}")),
        }
    }

    async fn spawn_worker(&self, spec: &AgentWorkerSpec) -> Result<SpawnHandle, String> {
        let mut command = TokioCommand::new(&spec.command);
        command.args(&spec.args);
        if !spec.working_directory.is_empty() {
            command.current_dir(&spec.working_directory);
        }
        // Replace the env entirely — we never want the kernel's env to
        // leak into the worker. The supervisor passes whatever it wants
        // the worker to see.
        command.env_clear();
        for (k, v) in &spec.environment {
            command.env(k, v);
        }
        command.stdin(Stdio::null());
        command.stdout(Stdio::inherit());
        command.stderr(Stdio::inherit());
        unsafe {
            command.pre_exec(|| {
                // setsid: new session + new process group with the worker
                // as leader. SIGTERM to the pgid hits the whole subtree.
                if libc::setsid() == -1 {
                    return Err(std::io::Error::last_os_error());
                }
                // Linux: ask the kernel to deliver SIGTERM to the worker
                // when its parent (us) dies. macOS has no equivalent;
                // workers there rely on the pgid-based shutdown path
                // and on the supervisor sending TerminateAgentWorker
                // before exiting cleanly.
                #[cfg(target_os = "linux")]
                {
                    if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) == -1 {
                        return Err(std::io::Error::last_os_error());
                    }
                }
                Ok(())
            });
        }
        match command.spawn() {
            Ok(child) => {
                let pid = child.id().map(|p| p as i32).unwrap_or(0);
                // Best-effort placement into the workspace cgroup. The
                // call is idempotent (cgroup files accept duplicate
                // writes) and a soft-failing no-op on macOS / hosts
                // without root, so we never fail the spawn over it.
                if pid > 0 && !spec.workspace_id.is_empty() {
                    let limits = isolation::WorkspaceLimits {
                        workspace_id: spec.workspace_id.clone(),
                        ..Default::default()
                    };
                    let _ = isolation::ensure_cgroup_v2_root();
                    let _ = isolation::apply_workspace_limits(&limits);
                    let _ = isolation::place_pid(&spec.workspace_id, pid as u32);
                }
                // setsid() makes the child its own pgid leader, so pgid == pid.
                Ok(SpawnHandle {
                    child,
                    pid,
                    pgid: pid,
                })
            }
            Err(e) => Err(format!("spawn_failed: {e}")),
        }
    }

    async fn probe_health(&self, host: &str, port: u16, path: &str) -> Result<(), String> {
        // Manual HTTP/1.1 GET to keep the runtime-kernel free of a full
        // HTTP client dependency. Workers expose /health on
        // 127.0.0.1:<port>, so the request never leaves the box and we
        // don't need TLS, redirects, keepalive, etc.
        let request = format!(
            "GET {} HTTP/1.1\r\nHost: {}:{}\r\nConnection: close\r\n\r\n",
            path, host, port
        );
        let probe = async {
            use tokio::io::{AsyncReadExt, AsyncWriteExt};
            let mut stream = tokio::net::TcpStream::connect((host, port))
                .await
                .map_err(|e| format!("connect: {e}"))?;
            stream
                .write_all(request.as_bytes())
                .await
                .map_err(|e| format!("write: {e}"))?;
            let mut buf = [0u8; 64];
            let n = stream
                .read(&mut buf)
                .await
                .map_err(|e| format!("read: {e}"))?;
            let head = std::str::from_utf8(&buf[..n]).unwrap_or("");
            // Expect "HTTP/1.1 2xx ..."
            if head.starts_with("HTTP/1.1 2") || head.starts_with("HTTP/1.0 2") {
                Ok(())
            } else {
                Err(format!("status: {}", head.lines().next().unwrap_or("")))
            }
        };
        match timeout(HEALTH_PROBE_TIMEOUT, probe).await {
            Ok(result) => result,
            Err(_) => Err("timeout".to_string()),
        }
    }
}

// --------------------------------------------------------------------- //
//  Public conversion helpers                                             //
// --------------------------------------------------------------------- //

pub fn snapshot_to_proto(snap: &WorkerSnapshot) -> AgentWorkerStatus {
    snap.to_proto()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
    use tokio::sync::Mutex as TokioMutex;

    /// Test adapter: fully deterministic. Tests inject port-bound state,
    /// spawn outcomes, and health responses without ever touching the OS.
    struct FakeAdapter {
        port_free: Arc<AtomicBool>,
        spawn_should_fail: Arc<AtomicBool>,
        next_pid: Arc<AtomicU32>,
        health_results: Arc<TokioMutex<Vec<bool>>>, // pop-front per call
    }

    impl FakeAdapter {
        fn new() -> Arc<Self> {
            Arc::new(Self {
                port_free: Arc::new(AtomicBool::new(true)),
                spawn_should_fail: Arc::new(AtomicBool::new(false)),
                next_pid: Arc::new(AtomicU32::new(10_000)),
                health_results: Arc::new(TokioMutex::new(Vec::new())),
            })
        }
    }

    #[async_trait::async_trait]
    impl RuntimeAdapter for FakeAdapter {
        async fn probe_port_free(&self, _host: &str, _port: u16) -> Result<(), String> {
            if self.port_free.load(Ordering::SeqCst) {
                Ok(())
            } else {
                Err("test_port_held".to_string())
            }
        }

        async fn spawn_worker(&self, _spec: &AgentWorkerSpec) -> Result<SpawnHandle, String> {
            if self.spawn_should_fail.load(Ordering::SeqCst) {
                return Err("test_spawn_failed".to_string());
            }
            // Spawn `sleep 3600` so the Child stays alive until the test
            // explicitly terminates it. We MUST setsid the child so it
            // becomes its own process group leader — otherwise the
            // production termination path (`killpg(pgid, SIGTERM)` in
            // `send_signal`) finds no matching process group and the
            // test hangs on `child.wait()`. `kill_on_drop(true)` is the
            // belt-and-suspenders so a panicked test doesn't leak a
            // long-running sleep into the host.
            let mut command = TokioCommand::new("sleep");
            command
                .arg("3600")
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .kill_on_drop(true);
            unsafe {
                command.pre_exec(|| {
                    if libc::setsid() == -1 {
                        return Err(std::io::Error::last_os_error());
                    }
                    Ok(())
                });
            }
            let child = command
                .spawn()
                .map_err(|e| format!("test_spawn_sleep: {e}"))?;
            let pid = child.id().map(|p| p as i32).unwrap_or(0);
            self.next_pid.fetch_add(1, Ordering::SeqCst);
            Ok(SpawnHandle {
                child,
                pid,
                pgid: pid,
            })
        }

        async fn probe_health(&self, _host: &str, _port: u16, _path: &str) -> Result<(), String> {
            let mut buf = self.health_results.lock().await;
            if let Some(ok) = (*buf).pop() {
                if ok {
                    Ok(())
                } else {
                    Err("test_unhealthy".to_string())
                }
            } else {
                Ok(())
            }
        }
    }

    fn spec(agent_id: &str, version: i32, port: i32) -> AgentWorkerSpec {
        AgentWorkerSpec {
            agent_id: agent_id.to_string(),
            version,
            command: "sleep".to_string(),
            args: vec!["3600".to_string()],
            working_directory: String::new(),
            environment: HashMap::new(),
            health_port: port,
            health_path: "/health".to_string(),
            workspace_id: "default".to_string(),
        }
    }

    #[tokio::test]
    async fn ensure_spawns_missing_workers() {
        let adapter = FakeAdapter::new();
        let registry = AgentWorkerRegistry::new(adapter.clone());
        let outcome = registry
            .ensure(vec![spec("ALPHA", 1, 0), spec("BETA", 1, 0)])
            .await;
        assert_eq!(outcome.spawned, 2);
        assert_eq!(outcome.terminated, 0);
        assert_eq!(outcome.restarted, 0);
        assert_eq!(outcome.current.len(), 2);
        registry.terminate_all().await;
    }

    #[tokio::test]
    async fn ensure_terminates_extras() {
        let adapter = FakeAdapter::new();
        let registry = AgentWorkerRegistry::new(adapter.clone());
        registry
            .ensure(vec![spec("ALPHA", 1, 0), spec("BETA", 1, 0)])
            .await;
        let outcome = registry.ensure(vec![spec("ALPHA", 1, 0)]).await;
        assert_eq!(outcome.terminated, 1);
        assert_eq!(outcome.unchanged, 1);
        assert_eq!(outcome.spawned, 0);
        assert_eq!(outcome.current.len(), 1);
        assert_eq!(outcome.current[0].agent_id, "ALPHA");
        registry.terminate_all().await;
    }

    #[tokio::test]
    async fn ensure_restarts_on_version_bump() {
        let adapter = FakeAdapter::new();
        let registry = AgentWorkerRegistry::new(adapter.clone());
        registry.ensure(vec![spec("ALPHA", 1, 0)]).await;
        let outcome = registry.ensure(vec![spec("ALPHA", 2, 0)]).await;
        assert_eq!(outcome.restarted, 1);
        assert_eq!(outcome.spawned, 0);
        assert_eq!(outcome.terminated, 0);
        let snapshot = registry.get("ALPHA").await.unwrap();
        assert_eq!(snapshot.version, 2);
        registry.terminate_all().await;
    }

    #[tokio::test]
    async fn ensure_records_spawn_blocked_when_port_in_use() {
        let adapter = FakeAdapter::new();
        adapter.port_free.store(false, Ordering::SeqCst);
        let registry = AgentWorkerRegistry::new(adapter.clone());
        let outcome = registry.ensure(vec![spec("ALPHA", 1, 8080)]).await;
        assert_eq!(outcome.spawned, 1);
        let snap = &outcome.current[0];
        assert_eq!(snap.state, AgentWorkerState::SpawnBlocked);
        assert!(snap.spawn_blocked_reason.contains("test_port_held"));
        // No process was actually spawned; nothing to terminate.
    }

    #[tokio::test]
    async fn ensure_records_spawn_blocked_when_adapter_spawn_fails() {
        let adapter = FakeAdapter::new();
        adapter.spawn_should_fail.store(true, Ordering::SeqCst);
        let registry = AgentWorkerRegistry::new(adapter.clone());
        let outcome = registry.ensure(vec![spec("ALPHA", 1, 0)]).await;
        let snap = &outcome.current[0];
        assert_eq!(snap.state, AgentWorkerState::SpawnBlocked);
        assert!(snap.spawn_blocked_reason.contains("test_spawn_failed"));
    }

    #[tokio::test]
    async fn terminate_removes_from_registry_so_next_ensure_respawns() {
        let adapter = FakeAdapter::new();
        let registry = AgentWorkerRegistry::new(adapter.clone());
        registry.ensure(vec![spec("ALPHA", 1, 0)]).await;
        registry.terminate("ALPHA", true).await;
        assert!(registry.get("ALPHA").await.is_none());
        let outcome = registry.ensure(vec![spec("ALPHA", 1, 0)]).await;
        assert_eq!(outcome.spawned, 1);
        registry.terminate_all().await;
    }

    #[tokio::test]
    async fn terminate_all_clears_registry() {
        let adapter = FakeAdapter::new();
        let registry = AgentWorkerRegistry::new(adapter.clone());
        registry
            .ensure(vec![
                spec("ALPHA", 1, 0),
                spec("BETA", 1, 0),
                spec("GAMMA", 1, 0),
            ])
            .await;
        registry.terminate_all().await;
        let snapshots = registry.list_snapshots().await;
        assert!(snapshots.is_empty());
    }

    #[tokio::test]
    async fn list_snapshots_is_deterministic_order() {
        let adapter = FakeAdapter::new();
        let registry = AgentWorkerRegistry::new(adapter.clone());
        registry
            .ensure(vec![
                spec("GAMMA", 1, 0),
                spec("ALPHA", 1, 0),
                spec("BETA", 1, 0),
            ])
            .await;
        let snapshots = registry.list_snapshots().await;
        let ids: Vec<&str> = snapshots.iter().map(|s| s.agent_id.as_str()).collect();
        assert_eq!(ids, vec!["ALPHA", "BETA", "GAMMA"]);
        registry.terminate_all().await;
    }

    #[tokio::test]
    async fn empty_desired_set_terminates_everything() {
        let adapter = FakeAdapter::new();
        let registry = AgentWorkerRegistry::new(adapter.clone());
        registry
            .ensure(vec![spec("ALPHA", 1, 0), spec("BETA", 1, 0)])
            .await;
        let outcome = registry.ensure(Vec::new()).await;
        assert_eq!(outcome.terminated, 2);
        assert!(outcome.current.is_empty());
    }

    #[tokio::test]
    async fn empty_agent_id_in_desired_set_is_skipped() {
        let adapter = FakeAdapter::new();
        let registry = AgentWorkerRegistry::new(adapter.clone());
        let mut blank = spec("", 1, 0);
        blank.agent_id = String::new();
        let outcome = registry.ensure(vec![blank, spec("ALPHA", 1, 0)]).await;
        assert_eq!(outcome.spawned, 1);
        assert_eq!(outcome.current.len(), 1);
        assert_eq!(outcome.current[0].agent_id, "ALPHA");
        registry.terminate_all().await;
    }
}
