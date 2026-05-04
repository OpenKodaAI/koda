use std::fs as stdfs;
use std::os::unix::fs as unix_fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::Result;

#[derive(Clone, Debug)]
pub(crate) struct ProvisionedWorkspace {
    pub(crate) workspace_path: String,
    pub(crate) branch_name: String,
    pub(crate) created_worktree: bool,
    pub(crate) worktree_mode: String,
    pub(crate) metadata_path: String,
}

fn truncate_slug(raw: &str) -> String {
    let mut value = raw.trim().to_string();
    if value.is_empty() {
        value = "task".to_string();
    }
    value.chars().take(32).collect()
}

pub(crate) fn is_git_repo(base_work_dir: &Path) -> bool {
    if base_work_dir.as_os_str().is_empty() {
        return false;
    }
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
    let suffix_seed = workspace_now_ms();
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

pub(crate) fn provision_workspace(
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

pub(crate) fn cleanup_workspace(workspace_path: &str, created_worktree: bool) -> Result<bool> {
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

fn workspace_now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or(Duration::ZERO)
        .as_millis() as u64
}
