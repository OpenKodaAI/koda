//! AG-04 (ADR-002 §2.4 L1): the runtime-kernel binary is non-dumpable, writes
//! no core files, and still supervises agent workers.
//!
//! The kernel's environment can hold secrets, and the workers and commands it
//! starts run as the same uid. Unless the kernel is non-dumpable, any of them
//! can read `/proc/<kernel>/environ`.
//!
//! The kernel and the reading sibling run as one unprivileged uid: root (or
//! any holder of `CAP_SYS_PTRACE`) reads every `environ` whatever the kernel
//! does, so a root reader would prove nothing. When the tests run as root they
//! switch both processes to an unused uid.
//!
//! Rust has no skipped state and `cargo test` hides a passing test's output,
//! so a test that returns early is reported as `ok`. Only an identity
//! precondition may end a test early: no unused uid, a non-root runner that
//! holds `CAP_SYS_PTRACE`, or root that may not act as the throwaway uid. Even
//! then the test fails unless `KODA_TEST_ALLOW_PROCESS_HYGIENE_SKIP=1` says a
//! run that proves nothing is acceptable. A kernel that cannot be started for
//! any other reason, or that exits during startup (as it does when it cannot
//! harden itself), always fails the test with its exit status and output.

#![cfg(target_os = "linux")]

use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{self, Read, Seek, SeekFrom};
use std::net::{TcpListener, TcpStream};
use std::os::unix::fs::MetadataExt;
use std::os::unix::process::CommandExt;
use std::process::{Child, Command, Output, Stdio};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use koda_proto::runtime::v1::agent_worker_status::State;
use koda_proto::runtime::v1::runtime_kernel_service_client::RuntimeKernelServiceClient;
use koda_proto::runtime::v1::{
    AgentWorkerSpec, AgentWorkerStatus, EnsureAgentWorkersRequest, GetAgentWorkerRequest,
    TerminateAgentWorkerRequest,
};
use tonic::transport::Channel;

const KERNEL_BIN: &str = env!("CARGO_BIN_EXE_koda-runtime-kernel");
const CANARY_KEY: &str = "KODA_AG04_CANARY";
const CAP_SYS_PTRACE: u32 = 19;
const SEARCH_PATH: &str = "/usr/local/bin:/usr/bin:/bin";
/// Set to `1` to let a test whose identity precondition fails pass without
/// proving anything, instead of failing.
const ALLOW_SKIP_ENV: &str = "KODA_TEST_ALLOW_PROCESS_HYGIENE_SKIP";

/// Ends a test whose proof cannot be made here: fails it, unless
/// [`ALLOW_SKIP_ENV`] allows the skip. Only identity preconditions call this.
fn skip(test: &str, reason: &str) {
    if std::env::var_os(ALLOW_SKIP_ENV).is_some_and(|value| value == "1") {
        eprintln!("SKIPPED {test}: {reason}");
        return;
    }
    panic!(
        "{test} cannot make its proof here: {reason}. \
         Set {ALLOW_SKIP_ENV}=1 to let it pass without proving anything."
    );
}

/// The unprivileged uid that the kernel and the sibling share.
#[derive(Clone, Copy)]
struct Identity {
    uid: u32,
    gid: u32,
    /// The test runs as root and must switch the processes it starts.
    switch: bool,
}

impl Identity {
    /// The user running the tests, with no switch.
    fn current() -> Self {
        // SAFETY: plain getters without arguments.
        let (uid, gid) = unsafe { (libc::getuid(), libc::getgid()) };
        Identity {
            uid,
            gid,
            switch: false,
        }
    }

    fn apply(&self, command: &mut Command) {
        if self.switch {
            // std clears the supplementary groups when it changes the uid.
            command.uid(self.uid).gid(self.gid);
        }
    }
}

/// Root that may not act as the throwaway uid (no `CAP_SETUID` or
/// `CAP_CHOWN`, or a path that uid cannot reach) is an identity
/// precondition, returned as the reason. Every other error fails the test.
fn uid_switch_refused(id: Identity, what: String, err: io::Error) -> String {
    if id.switch && err.kind() == io::ErrorKind::PermissionDenied {
        return format!("root may not {what}: {err}");
    }
    panic!("cannot {what}: {err}");
}

fn cap_eff_has(cap: u32) -> bool {
    let status = fs::read_to_string("/proc/self/status").expect("read /proc/self/status");
    status
        .lines()
        .find_map(|line| line.strip_prefix("CapEff:"))
        .and_then(|value| u64::from_str_radix(value.trim(), 16).ok())
        .map(|mask| mask & (1 << cap) != 0)
        .unwrap_or(false)
}

fn unused_uid() -> Option<u32> {
    // SAFETY: getpwuid only reads the passwd database; the pointer is not kept.
    (61_000u32..62_000).find(|uid| unsafe { libc::getpwuid(*uid).is_null() })
}

fn identity() -> Result<Identity, String> {
    // SAFETY: plain getters without arguments.
    let (euid, uid, gid) = unsafe { (libc::geteuid(), libc::getuid(), libc::getgid()) };
    if euid == 0 {
        let throwaway = unused_uid().ok_or("no unused uid in 61000-61999")?;
        return Ok(Identity {
            uid: throwaway,
            gid: throwaway,
            switch: true,
        });
    }
    if cap_eff_has(CAP_SYS_PTRACE) {
        return Err("this non-root test process holds CAP_SYS_PTRACE".into());
    }
    Ok(Identity {
        uid,
        gid,
        switch: false,
    })
}

/// Kills the process on drop so a failed assertion never leaks it.
struct Reaped(Child);

impl Drop for Reaped {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn free_port() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind an ephemeral port");
    listener.local_addr().expect("local addr").port()
}

struct Kernel {
    process: Reaped,
    port: u16,
    _root: tempfile::TempDir,
}

impl Kernel {
    fn pid(&self) -> i32 {
        self.process.0.id() as i32
    }
}

/// Starts the real binary the way the compose service does, as `id`.
fn start_kernel(id: Identity, canary: &str) -> Result<Kernel, String> {
    let port = free_port();
    launch_kernel(id, canary, &format!("127.0.0.1:{port}"), port)
}

/// Starts the kernel listening on `socket` and waits until `port` accepts.
///
/// `Err` is only the identity precondition of [`uid_switch_refused`]. Any
/// other failure panics, and a kernel that exits before it listens panics
/// with its exit status and output: a kernel that refuses to start must fail
/// the test, never skip it.
fn launch_kernel(id: Identity, canary: &str, socket: &str, port: u16) -> Result<Kernel, String> {
    let root = tempfile::tempdir().expect("kernel root");
    if id.switch {
        std::os::unix::fs::chown(root.path(), Some(id.uid), Some(id.gid)).map_err(|err| {
            uid_switch_refused(id, format!("chown the kernel root to uid {}", id.uid), err)
        })?;
    }
    // stdout carries the kernel's tracing, stderr the error main() returns.
    let mut output = tempfile::tempfile().expect("kernel output file");
    let mut command = Command::new(KERNEL_BIN);
    command
        .env_clear()
        .env("RUNTIME_KERNEL_SOCKET", socket)
        .env("RUNTIME_KERNEL_ROOT", root.path())
        .env(CANARY_KEY, canary)
        .stdin(Stdio::null())
        .stdout(output.try_clone().expect("share the kernel output file"))
        .stderr(output.try_clone().expect("share the kernel output file"));
    id.apply(&mut command);
    let child = command.spawn().map_err(|err| {
        uid_switch_refused(id, format!("start {KERNEL_BIN} as uid {}", id.uid), err)
    })?;
    let mut process = Reaped(child);

    let deadline = Instant::now() + Duration::from_secs(20);
    loop {
        if let Some(status) = process.0.try_wait().expect("poll kernel") {
            panic!(
                "kernel exited during startup: {status}\n--- kernel output ---\n{}",
                read_all(&mut output)
            );
        }
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            break;
        }
        assert!(
            Instant::now() < deadline,
            "kernel did not listen on {port}\n--- kernel output ---\n{}",
            read_all(&mut output)
        );
        std::thread::sleep(Duration::from_millis(50));
    }
    Ok(Kernel {
        process,
        port,
        _root: root,
    })
}

fn read_all(file: &mut File) -> String {
    let mut bytes = Vec::new();
    match file
        .seek(SeekFrom::Start(0))
        .and_then(|_| file.read_to_end(&mut bytes))
    {
        Ok(_) => String::from_utf8_lossy(&bytes).into_owned(),
        Err(err) => format!("<cannot read the kernel output: {err}>"),
    }
}

/// A same-uid process reading `/proc/<pid>/environ`, exactly as a provider
/// CLI or a governed shell command would.
fn sibling_reads_environ(id: Identity, pid: i32) -> Output {
    let mut command = Command::new("cat");
    command
        .arg(format!("/proc/{pid}/environ"))
        .env_clear()
        .env("PATH", SEARCH_PATH)
        .env("LC_ALL", "C");
    id.apply(&mut command);
    command.output().expect("run cat")
}

fn status_field(pid: i32, key: &str) -> String {
    let status = fs::read_to_string(format!("/proc/{pid}/status")).expect("read status");
    status
        .lines()
        .find_map(|line| line.strip_prefix(key))
        .map(|value| value.trim().to_string())
        .unwrap_or_else(|| panic!("no {key} in /proc/{pid}/status"))
}

fn real_uid(pid: i32) -> u32 {
    status_field(pid, "Uid:")
        .split_whitespace()
        .next()
        .and_then(|value| value.parse().ok())
        .expect("uid")
}

fn parent_pid(pid: i32) -> i32 {
    status_field(pid, "PPid:").parse().expect("ppid")
}

/// Soft and hard `RLIMIT_CORE` from `/proc/<pid>/limits`.
fn core_limit(pid: i32) -> (String, String) {
    let limits = fs::read_to_string(format!("/proc/{pid}/limits")).expect("read limits");
    let line = limits
        .lines()
        .find(|line| line.starts_with("Max core file size"))
        .expect("core limit line");
    let fields: Vec<&str> = line.split_whitespace().collect();
    (fields[4].to_string(), fields[5].to_string())
}

fn pid_alive(pid: i32) -> bool {
    // A reaped worker leaves no /proc entry; a zombie still has one.
    fs::read_to_string(format!("/proc/{pid}/status"))
        .map(|status| {
            status
                .lines()
                .find_map(|line| line.strip_prefix("State:"))
                .is_some_and(|state| !state.trim_start().starts_with('Z'))
        })
        .unwrap_or(false)
}

fn wait_until(what: &str, mut done: impl FnMut() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(20);
    while !done() {
        assert!(Instant::now() < deadline, "timed out waiting for {what}");
        std::thread::sleep(Duration::from_millis(50));
    }
}

#[test]
fn same_uid_sibling_cannot_read_kernel_environ_and_core_dumps_are_off() {
    const TEST: &str = "same_uid_sibling_cannot_read_kernel_environ_and_core_dumps_are_off";
    let id = match identity() {
        Ok(id) => id,
        Err(reason) => return skip(TEST, &reason),
    };
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or_default();
    let canary = format!("ag04-{}-{nanos}", std::process::id());

    // Control: a dumpable process of the same uid leaks its environment to
    // the sibling, so a refusal below is the kernel's doing.
    let mut control = Command::new("sleep");
    control
        .arg("60")
        .env_clear()
        .env("PATH", SEARCH_PATH)
        .env(CANARY_KEY, &canary)
        .stdin(Stdio::null());
    id.apply(&mut control);
    let control = match control.spawn() {
        Ok(child) => Reaped(child),
        Err(err) => {
            let what = format!("start a process as uid {}", id.uid);
            return skip(TEST, &uid_switch_refused(id, what, err));
        }
    };
    let control_pid = control.0.id() as i32;
    wait_until("control process", || {
        fs::read(format!("/proc/{control_pid}/cmdline"))
            .map(|cmdline| cmdline.starts_with(b"sleep"))
            .unwrap_or(false)
    });
    assert_eq!(real_uid(control_pid), id.uid);
    let leaked = sibling_reads_environ(id, control_pid);
    assert!(
        leaked.status.success(),
        "control read failed: {}",
        String::from_utf8_lossy(&leaked.stderr)
    );
    assert!(String::from_utf8_lossy(&leaked.stdout).contains(&canary));
    drop(control);

    let kernel = match start_kernel(id, &canary) {
        Ok(kernel) => kernel,
        Err(reason) => return skip(TEST, &reason),
    };
    let pid = kernel.pid();
    assert_eq!(real_uid(pid), id.uid);

    let refused = sibling_reads_environ(id, pid);
    assert!(
        !String::from_utf8_lossy(&refused.stdout).contains(&canary),
        "a same-uid sibling read the kernel's environment"
    );
    assert!(!refused.status.success());
    let stderr = String::from_utf8_lossy(&refused.stderr);
    assert!(stderr.contains("Permission denied"), "{stderr}");

    // A non-dumpable process's /proc entries belong to root (task_dump_owner).
    let environ_owner = fs::metadata(format!("/proc/{pid}/environ"))
        .expect("stat environ")
        .uid();
    assert_eq!(environ_owner, 0);
    assert_ne!(id.uid, 0);

    assert_eq!(core_limit(pid), ("0".to_string(), "0".to_string()));
}

/// Guards the two kernel tests: a kernel that exits during startup (as it does
/// when it cannot harden itself) fails them with its exit status and output,
/// instead of ending them early as a pass.
#[test]
fn kernel_exiting_during_startup_fails_the_test() {
    let port = free_port();
    // The real kernel hardens itself, then main() returns the parse error of
    // this listen address and the process exits 1 before it ever listens. The
    // test's own user runs it: no identity precondition applies.
    let outcome = std::panic::catch_unwind(|| {
        launch_kernel(
            Identity::current(),
            "startup-failure",
            "not-a-socket-address",
            port,
        )
    });
    let Err(payload) = outcome else {
        panic!("a kernel that exited during startup was not reported as a failure");
    };
    let message = payload
        .downcast_ref::<String>()
        .cloned()
        .or_else(|| payload.downcast_ref::<&str>().map(|text| text.to_string()))
        .unwrap_or_default();
    assert!(
        message.contains("kernel exited during startup: exit status: 1"),
        "{message}"
    );
    // The kernel's own stderr is part of the failure, so it can be diagnosed.
    assert!(
        message.contains("invalid socket address syntax"),
        "{message}"
    );
}

fn worker(agent_id: &str, script: &str) -> AgentWorkerSpec {
    AgentWorkerSpec {
        agent_id: agent_id.to_string(),
        version: 1,
        command: "/bin/sh".to_string(),
        args: vec!["-c".to_string(), script.to_string()],
        environment: HashMap::from([("PATH".to_string(), SEARCH_PATH.to_string())]),
        // No health port (no probe) and no workspace (no cgroup writes).
        health_port: 0,
        ..Default::default()
    }
}

async fn get_worker(
    client: &mut RuntimeKernelServiceClient<Channel>,
    agent_id: &str,
) -> AgentWorkerStatus {
    let response = client
        .get_agent_worker(GetAgentWorkerRequest {
            agent_id: agent_id.to_string(),
            ..Default::default()
        })
        .await
        .expect("GetAgentWorker")
        .into_inner();
    assert!(response.found, "{agent_id} not tracked");
    response.status.expect("status")
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn hardened_kernel_still_supervises_agent_workers() {
    const TEST: &str = "hardened_kernel_still_supervises_agent_workers";
    let id = match identity() {
        Ok(id) => id,
        Err(reason) => return skip(TEST, &reason),
    };
    let kernel = match start_kernel(id, "supervision") {
        Ok(kernel) => kernel,
        Err(reason) => return skip(TEST, &reason),
    };
    let kernel_pid = kernel.pid();
    let mut client =
        RuntimeKernelServiceClient::connect(format!("http://127.0.0.1:{}", kernel.port))
            .await
            .expect("connect to the kernel");

    let outcome = client
        .ensure_agent_workers(EnsureAgentWorkersRequest {
            desired: vec![
                worker("AG04_TERMINATED", "exec sleep 60"),
                worker("AG04_ORPHANED", "exec sleep 60"),
                worker("AG04_EXITS", "exit 7"),
            ],
            ..Default::default()
        })
        .await
        .expect("EnsureAgentWorkers")
        .into_inner();
    assert_eq!(outcome.spawned, 3);

    // Spawned as the kernel's child, as its own process-group leader, and
    // with the kernel's zero core limit inherited.
    let terminated = get_worker(&mut client, "AG04_TERMINATED").await;
    let orphaned = get_worker(&mut client, "AG04_ORPHANED").await;
    for status in [&terminated, &orphaned] {
        assert!(status.pid > 0);
        assert_eq!(status.pgid, status.pid);
        assert_eq!(parent_pid(status.pid), kernel_pid);
        assert_eq!(real_uid(status.pid), id.uid);
        assert_eq!(core_limit(status.pid), ("0".to_string(), "0".to_string()));
    }

    // The reaper records a worker's own exit with its code.
    let deadline = Instant::now() + Duration::from_secs(20);
    let exited = loop {
        let status = get_worker(&mut client, "AG04_EXITS").await;
        if status.state == State::Exited as i32 {
            break status;
        }
        assert!(
            Instant::now() < deadline,
            "AG04_EXITS never reported as exited"
        );
        tokio::time::sleep(Duration::from_millis(50)).await;
    };
    assert_eq!(exited.exit_code, 7);

    // Terminate signals the worker's process group and reaps it.
    let response = client
        .terminate_agent_worker(TerminateAgentWorkerRequest {
            agent_id: "AG04_TERMINATED".to_string(),
            force: true,
            ..Default::default()
        })
        .await
        .expect("TerminateAgentWorker")
        .into_inner();
    assert!(response.terminated);
    assert_eq!(
        response.status.expect("status").state,
        State::Terminated as i32
    );
    wait_until("the terminated worker to be reaped", || {
        !pid_alive(terminated.pid)
    });

    // PR_SET_PDEATHSIG still takes the workers down with the kernel.
    assert!(pid_alive(orphaned.pid));
    drop(client);
    drop(kernel);
    wait_until("the orphaned worker to die with the kernel", || {
        !pid_alive(orphaned.pid)
    });
}
