//! Process hygiene for the runtime-kernel binary (ADR-002 §2.4 L1, AG-04).
//!
//! The agent workers, commands and terminals the kernel starts run as the
//! kernel's uid. On Linux a same-uid process may read `/proc/<pid>/environ`
//! and `/proc/<pid>/mem` of any *dumpable* process without a capability, and
//! a crash can write the whole address space to a core file.
//!
//! [`harden_current_process`] closes both, and `main` calls it before the
//! async runtime starts:
//!
//! * `prctl(PR_SET_DUMPABLE, 0)` (Linux): `/proc/<pid>/*` becomes owned by
//!   root and ptrace-mode access (environ, mem, fd, ptrace attach) is refused
//!   to any caller without `CAP_SYS_PTRACE`. The kernel writes no core.
//! * `RLIMIT_CORE` soft and hard limit 0: inherited by every child, which
//!   cannot raise it again without `CAP_SYS_RESOURCE`. `execve` makes a child
//!   dumpable again, so this limit is what keeps children's cores off; the
//!   Python worker also makes itself non-dumpable (`koda/process_hygiene.py`).
//!
//! Neither setting affects supervision: signals, `waitpid`, `setsid`,
//! `PR_SET_PDEATHSIG` and cgroup placement do not depend on dumpability.

use std::io;

/// Makes the current process non-dumpable (Linux) and sets `RLIMIT_CORE` to
/// zero. Returns an error instead of running unhardened.
pub fn harden_current_process() -> io::Result<()> {
    #[cfg(target_os = "linux")]
    disable_dumpable()?;
    disable_core_dumps()
}

#[cfg(target_os = "linux")]
fn disable_dumpable() -> io::Result<()> {
    let zero: libc::c_ulong = 0;
    // SAFETY: PR_SET_DUMPABLE and PR_GET_DUMPABLE take integer arguments only.
    if unsafe { libc::prctl(libc::PR_SET_DUMPABLE, zero, zero, zero, zero) } != 0 {
        let err = io::Error::last_os_error();
        return Err(io::Error::new(
            err.kind(),
            format!("prctl(PR_SET_DUMPABLE, 0) failed: {err}"),
        ));
    }
    // SAFETY: as above.
    let state = unsafe { libc::prctl(libc::PR_GET_DUMPABLE, zero, zero, zero, zero) };
    if state != 0 {
        return Err(io::Error::other(format!(
            "process is still dumpable after PR_SET_DUMPABLE (state {state})"
        )));
    }
    Ok(())
}

fn disable_core_dumps() -> io::Result<()> {
    let limit = libc::rlimit {
        rlim_cur: 0,
        rlim_max: 0,
    };
    // SAFETY: `limit` is a valid rlimit that outlives the call.
    if unsafe { libc::setrlimit(libc::RLIMIT_CORE, &limit) } != 0 {
        let err = io::Error::last_os_error();
        return Err(io::Error::new(
            err.kind(),
            format!("setrlimit(RLIMIT_CORE, 0) failed: {err}"),
        ));
    }
    Ok(())
}
