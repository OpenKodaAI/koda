use std::collections::HashMap;
use std::path::{Path, PathBuf};

use koda_security_core::{sanitize_env, validate_runtime_path};
use serde_json::{Map, Value};
use tokio::process::Command as TokioCommand;
use tonic::Status;

pub(crate) fn default_shell_command() -> String {
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

pub(crate) fn default_shell_args(command: &str) -> Vec<String> {
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
pub(crate) fn normalize_working_directory(value: &str) -> Result<Option<PathBuf>, Status> {
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
pub(crate) fn sanitize_command_environment(
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

#[allow(clippy::result_large_err)]
pub(crate) fn prepare_process_command(
    command: &str,
    args: &[String],
    working_directory: &str,
    environment_overrides: &HashMap<String, String>,
    start_new_session: bool,
) -> Result<TokioCommand, Status> {
    let mut command_builder = TokioCommand::new(command);
    command_builder.args(args);
    if let Some(cwd) = normalize_working_directory(working_directory)? {
        command_builder.current_dir(cwd);
    }
    command_builder.env_clear();
    let sanitized_env = sanitize_command_environment(environment_overrides)?;
    command_builder.envs(sanitized_env);
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
    Ok(command_builder)
}

pub(crate) fn send_process_signal(pgid: Option<i32>, pid: Option<i32>, signal: i32) -> bool {
    if let Some(group_id) = pgid.filter(|value| *value > 0) {
        let result = unsafe { libc::killpg(group_id, signal) };
        if result == 0 {
            return true;
        }
    }
    if let Some(process_id) = pid.filter(|value| *value > 0) {
        let result = unsafe { libc::kill(process_id, signal) };
        if result == 0 {
            return true;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn send_process_signal_ignores_zero_identifiers() {
        assert!(!send_process_signal(Some(0), None, libc::SIGTERM));
        assert!(!send_process_signal(None, Some(0), libc::SIGTERM));
    }
}
