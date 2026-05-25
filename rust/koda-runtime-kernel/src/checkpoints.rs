use std::path::{Component, Path, PathBuf};
use std::process::Command;

use anyhow::{anyhow, Result};

use crate::state::CheckpointRecord;
use crate::workspace::is_git_repo;

pub(crate) fn build_checkpoint_archive_path(checkpoint_dir: &Path, name: &str) -> PathBuf {
    checkpoint_dir.join(name)
}

#[derive(Default, Clone, Debug)]
pub(crate) struct RestoreCheckpointOutcome {
    pub(crate) restored: bool,
    pub(crate) workspace_path: String,
    pub(crate) restored_commit_sha: String,
    pub(crate) restored_paths: Vec<String>,
    pub(crate) error_message: String,
}

pub(crate) fn run_git_output(workspace_path: &Path, args: &[&str]) -> Result<String> {
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

pub(crate) fn git_head_commit_sha(workspace_path: &Path) -> Result<String> {
    Ok(
        run_git_output(workspace_path, &["rev-parse", "--verify", "HEAD"])?
            .trim()
            .to_string(),
    )
}

pub(crate) fn git_diff_bytes(workspace_path: &Path) -> Result<Vec<u8>> {
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

pub(crate) fn build_untracked_bundle_bytes(workspace_path: &Path) -> Result<Vec<u8>> {
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

pub(crate) fn restore_checkpoint_bundle(
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
