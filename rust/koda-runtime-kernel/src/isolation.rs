//! OS-level isolation hooks for agent workers.
//!
//! Per-workspace cgroup v2 limits + premium-tier CPU pinning. Today
//! every Python worker is a plain process; this module is what the
//! supervisor calls before spawning so a noisy workspace cannot
//! starve the others. The runtime-kernel already owns process spawn
//! lifecycle, so the isolation primitives sit naturally here.
//!
//! Cross-platform behavior:
//!
//! - **Linux**: writes cgroup v2 files under
//!   `/sys/fs/cgroup/koda/ws_<workspace_id>/` (path overridable via
//!   `KODA_CGROUP_ROOT`). Falls back to a configured "soft" mode that
//!   only logs when the cgroup root is missing or non-writable —
//!   production deploys mount the cgroup root at supervisor start;
//!   developer machines without root just see `tracing::warn!` lines.
//! - **macOS / other**: no-op with `tracing::debug!`. Production is
//!   Linux; macOS is a development target.
//!
//! See `docs/architecture/production-deployment-roadmap.md` for the
//! broader "isolamento além de lógico" rationale.

#[cfg(target_os = "linux")]
use anyhow::anyhow;
use anyhow::Result;

#[cfg(target_os = "linux")]
use std::path::PathBuf;

/// Per-workspace OS-level limits. `None` leaves the corresponding
/// cgroup knob untouched (system default).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct WorkspaceLimits {
    pub workspace_id: String,
    /// `memory.max` in bytes. Exceeding triggers an in-cgroup OOM kill
    /// without touching the host. Default unset.
    pub memory_max_bytes: Option<u64>,
    /// `cpu.max` quota / period pair, e.g. `(50000, 100000)` = 0.5
    /// CPU. Default unset.
    pub cpu_max_quota_period: Option<(u64, u64)>,
    /// `pids.max`: cap on processes the workspace can spawn.
    pub pids_max: Option<u64>,
    /// Optional CPU set for premium-tier pinning (`cpuset.cpus`).
    /// Empty vec is treated as `None`.
    pub cpu_affinity: Option<Vec<u32>>,
}

/// Ensure the cgroup root the runtime-kernel will use exists and is
/// writable. Called once at supervisor startup. On non-Linux this is
/// a no-op. On Linux when the root is missing this is downgraded to a
/// warn so dev environments without root privileges still boot.
pub fn ensure_cgroup_v2_root() -> Result<()> {
    #[cfg(target_os = "linux")]
    {
        let root = cgroup_root();
        match std::fs::metadata(&root) {
            Ok(meta) if meta.is_dir() => {
                tracing::info!(root = %root.display(), "ensure_cgroup_v2_root_ok");
                Ok(())
            }
            Ok(_) => Err(anyhow!(
                "cgroup root {} exists but is not a directory",
                root.display()
            )),
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
                // Try to create — succeeds when running as root or with the
                // necessary capabilities. Soft-fail otherwise so dev hosts
                // that don't have CAP_SYS_ADMIN still boot the supervisor;
                // limits will simply be no-ops until the operator mounts
                // the cgroup root.
                if std::fs::create_dir_all(&root).is_ok() {
                    tracing::info!(
                        root = %root.display(),
                        "ensure_cgroup_v2_root_created"
                    );
                    Ok(())
                } else {
                    tracing::warn!(
                        root = %root.display(),
                        "ensure_cgroup_v2_root_unavailable_running_unisolated"
                    );
                    Ok(())
                }
            }
            Err(err) => {
                tracing::warn!(
                    root = %root.display(),
                    error = %err,
                    "ensure_cgroup_v2_root_inspect_failed_running_unisolated"
                );
                Ok(())
            }
        }
    }
    #[cfg(not(target_os = "linux"))]
    {
        tracing::debug!("ensure_cgroup_v2_root: skipped on non-linux platform");
        Ok(())
    }
}

/// Apply the given limits to the cgroup that hosts the workspace's
/// workers. Idempotent: re-applying the same limits is a no-op (cgroup
/// files accept the same value without error). On non-Linux this is a
/// no-op.
pub fn apply_workspace_limits(_limits: &WorkspaceLimits) -> Result<()> {
    #[cfg(target_os = "linux")]
    {
        apply_workspace_limits_with_root(_limits, &cgroup_root())?;
    }
    #[cfg(not(target_os = "linux"))]
    {
        tracing::debug!(
            workspace = %_limits.workspace_id,
            "apply_workspace_limits: skipped on non-linux platform"
        );
    }
    Ok(())
}

/// Move the given pid into the workspace's cgroup right after spawn.
/// On non-Linux this is a no-op.
pub fn place_pid(_workspace_id: &str, _pid: u32) -> Result<()> {
    #[cfg(target_os = "linux")]
    {
        place_pid_with_root(_workspace_id, _pid, &cgroup_root())?;
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Linux helpers
// ---------------------------------------------------------------------------

#[cfg(target_os = "linux")]
fn cgroup_root() -> PathBuf {
    std::env::var_os("KODA_CGROUP_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/sys/fs/cgroup/koda"))
}

#[cfg(target_os = "linux")]
fn workspace_cgroup_dir(root: &std::path::Path, workspace_id: &str) -> PathBuf {
    let safe = sanitize_workspace_segment(workspace_id);
    root.join(format!("ws_{safe}"))
}

#[cfg(target_os = "linux")]
fn apply_workspace_limits_with_root(
    limits: &WorkspaceLimits,
    root: &std::path::Path,
) -> Result<()> {
    let cgroup_path = workspace_cgroup_dir(root, &limits.workspace_id);
    ensure_dir(&cgroup_path)?;
    if let Some(memory_max) = limits.memory_max_bytes {
        write_cgroup_file(&cgroup_path, "memory.max", &memory_max.to_string())?;
    }
    if let Some((quota, period)) = limits.cpu_max_quota_period {
        write_cgroup_file(&cgroup_path, "cpu.max", &format!("{quota} {period}"))?;
    }
    if let Some(pids_max) = limits.pids_max {
        write_cgroup_file(&cgroup_path, "pids.max", &pids_max.to_string())?;
    }
    if let Some(cpus) = limits.cpu_affinity.as_ref().filter(|v| !v.is_empty()) {
        let formatted = cpus
            .iter()
            .map(|c| c.to_string())
            .collect::<Vec<_>>()
            .join(",");
        write_cgroup_file(&cgroup_path, "cpuset.cpus", &formatted)?;
    }
    Ok(())
}

#[cfg(target_os = "linux")]
fn place_pid_with_root(workspace_id: &str, pid: u32, root: &std::path::Path) -> Result<()> {
    let cgroup_path = workspace_cgroup_dir(root, workspace_id);
    ensure_dir(&cgroup_path)?;
    write_cgroup_file(&cgroup_path, "cgroup.procs", &pid.to_string())?;
    Ok(())
}

#[cfg(target_os = "linux")]
fn ensure_dir(path: &std::path::Path) -> Result<()> {
    match std::fs::metadata(path) {
        Ok(m) if m.is_dir() => Ok(()),
        Ok(_) => Err(anyhow!("cgroup path {} is not a directory", path.display())),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
            std::fs::create_dir_all(path)
                .map_err(|e| anyhow!("create cgroup dir {}: {e}", path.display()))?;
            Ok(())
        }
        Err(err) => Err(anyhow!(
            "inspect cgroup path {} failed: {err}",
            path.display()
        )),
    }
}

#[cfg(target_os = "linux")]
fn write_cgroup_file(dir: &std::path::Path, name: &str, value: &str) -> Result<()> {
    let target = dir.join(name);
    std::fs::write(&target, value)
        .map_err(|e| anyhow!("write {} = {value:?}: {e}", target.display()))?;
    Ok(())
}

/// Strip dangerous characters from a workspace_id so it cannot escape
/// the cgroup root. We accept ASCII alphanumerics + `_` `-` and replace
/// everything else with `_`.
pub fn sanitize_workspace_segment(workspace_id: &str) -> String {
    let mut out = String::with_capacity(workspace_id.len());
    for ch in workspace_id.chars() {
        if ch.is_ascii_alphanumeric() || ch == '_' || ch == '-' {
            out.push(ch);
        } else {
            out.push('_');
        }
    }
    if out.is_empty() {
        out.push_str("default");
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(target_os = "linux")]
    fn tmp_cgroup_root(test_name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "koda-cgroup-test-{test_name}-{}",
            std::process::id()
        ))
    }

    #[test]
    fn ensure_root_is_ok_on_any_platform() {
        ensure_cgroup_v2_root().expect("scaffold must not fail");
    }

    #[test]
    fn apply_limits_is_idempotent_on_repeat() {
        let limits = WorkspaceLimits {
            workspace_id: "ws_test".into(),
            memory_max_bytes: Some(1024 * 1024 * 1024),
            cpu_max_quota_period: Some((50_000, 100_000)),
            pids_max: Some(512),
            cpu_affinity: None,
        };
        #[cfg(target_os = "linux")]
        {
            let tmp = tmp_cgroup_root("idempotent");
            apply_workspace_limits_with_root(&limits, &tmp).unwrap();
            apply_workspace_limits_with_root(&limits, &tmp).unwrap();
            std::fs::remove_dir_all(&tmp).ok();
        }
        #[cfg(not(target_os = "linux"))]
        {
            apply_workspace_limits(&limits).unwrap();
            apply_workspace_limits(&limits).unwrap();
        }
    }

    #[test]
    fn place_pid_accepts_arbitrary_pid() {
        #[cfg(target_os = "linux")]
        {
            let tmp = tmp_cgroup_root("place-pid");
            place_pid_with_root("ws_test", 12345, &tmp).unwrap();
            assert_eq!(
                std::fs::read_to_string(tmp.join("ws_ws_test").join("cgroup.procs")).unwrap(),
                "12345"
            );
            std::fs::remove_dir_all(&tmp).ok();
        }
        #[cfg(not(target_os = "linux"))]
        {
            place_pid("ws_test", 12345).unwrap();
        }
    }

    #[test]
    fn sanitize_strips_path_separators() {
        assert_eq!(sanitize_workspace_segment("ws/abc"), "ws_abc");
        assert_eq!(sanitize_workspace_segment("../escape"), "___escape");
        assert_eq!(sanitize_workspace_segment("ws.dot"), "ws_dot");
        assert_eq!(sanitize_workspace_segment(""), "default");
        assert_eq!(sanitize_workspace_segment("ws_alpha-1"), "ws_alpha-1");
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn linux_writes_to_temporary_cgroup_root() {
        // Use a tmpdir as the "cgroup root" so we exercise the real
        // file-write path without needing actual cgroup mounts. The
        // cgroup files behave like regular files at this layer.
        let tmp = tmp_cgroup_root("writes");

        let limits = WorkspaceLimits {
            workspace_id: "ws_alpha".into(),
            memory_max_bytes: Some(2 * 1024 * 1024 * 1024),
            cpu_max_quota_period: Some((25_000, 100_000)),
            pids_max: Some(256),
            cpu_affinity: Some(vec![0, 1]),
        };
        apply_workspace_limits_with_root(&limits, &tmp).unwrap();

        let dir = tmp.join("ws_ws_alpha");
        assert_eq!(
            std::fs::read_to_string(dir.join("memory.max")).unwrap(),
            "2147483648"
        );
        assert_eq!(
            std::fs::read_to_string(dir.join("cpu.max")).unwrap(),
            "25000 100000"
        );
        assert_eq!(
            std::fs::read_to_string(dir.join("pids.max")).unwrap(),
            "256"
        );
        assert_eq!(
            std::fs::read_to_string(dir.join("cpuset.cpus")).unwrap(),
            "0,1"
        );

        place_pid_with_root("ws_alpha", 999_999, &tmp).unwrap();
        assert_eq!(
            std::fs::read_to_string(dir.join("cgroup.procs")).unwrap(),
            "999999"
        );

        std::fs::remove_dir_all(&tmp).ok();
    }
}
