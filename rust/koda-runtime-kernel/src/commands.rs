use std::collections::HashMap;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use koda_security_core::validate_shell_command;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tonic::Status;

use crate::processes::{default_shell_command, prepare_process_command, send_process_signal};

const COMMAND_OUTPUT_BYTE_LIMIT: usize = 1024 * 1024;
const COMMAND_TRUNCATION_SUFFIX: &[u8] =
    b"\n[runtime-kernel truncated command output after 1048576 bytes]\n";

async fn read_to_capped_bytes<R>(mut reader: R, limit: usize) -> Result<Vec<u8>, std::io::Error>
where
    R: tokio::io::AsyncRead + Unpin + Send + 'static,
{
    let mut buffer = Vec::new();
    let mut scratch = [0u8; 8192];
    loop {
        let read = reader.read(&mut scratch).await?;
        if read == 0 {
            break;
        }
        let remaining = limit.saturating_sub(buffer.len());
        if remaining > 0 {
            buffer.extend_from_slice(&scratch[..read.min(remaining)]);
            if read > remaining {
                buffer.extend_from_slice(COMMAND_TRUNCATION_SUFFIX);
            }
        }
        if buffer.len() >= limit {
            // Drain the child pipe so the process is not blocked by a full pipe.
            while reader.read(&mut scratch).await? != 0 {}
            if !buffer.ends_with(COMMAND_TRUNCATION_SUFFIX) {
                buffer.extend_from_slice(COMMAND_TRUNCATION_SUFFIX);
            }
            break;
        }
    }
    Ok(buffer)
}

struct CommandPolicy {
    allow_network: bool,
}

impl CommandPolicy {
    fn from_allow_network(allow_network: bool) -> Self {
        Self { allow_network }
    }

    #[allow(clippy::result_large_err)]
    fn validate(&self, command: &str, argv: &[String]) -> Result<(), Status> {
        if self.allow_network {
            return Ok(());
        }
        let mut parts = Vec::with_capacity(argv.len() + 1);
        parts.push(command.to_string());
        parts.extend(argv.iter().cloned());
        let joined = parts.join(" ").to_ascii_lowercase();
        let network_tokens = [
            "curl",
            "wget",
            "ssh",
            "scp",
            "sftp",
            "rsync",
            "ftp",
            "telnet",
            "ping",
            "traceroute",
            "dig",
            "nslookup",
            "host",
            "nc",
            "ncat",
            "netcat",
            "socat",
        ];
        let explicit_network = joined
            .split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_' || ch == '-' || ch == '.'))
            .filter(|token| !token.is_empty())
            .any(|token| network_tokens.contains(&token));
        if explicit_network
            || joined.contains("/dev/tcp/")
            || joined.contains("http://")
            || joined.contains("https://")
        {
            return Err(Status::permission_denied(
                "network command execution requires allow_network=true",
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub(crate) struct ExecutedCommandOutcome {
    pub(crate) stdout: Vec<u8>,
    pub(crate) stderr: Vec<u8>,
    pub(crate) exit_code: i32,
    pub(crate) timed_out: bool,
    pub(crate) killed: bool,
    pub(crate) started_at_ms: u64,
    pub(crate) finished_at_ms: u64,
}

#[allow(clippy::too_many_arguments)]
pub(crate) async fn execute_shell_command(
    command: &str,
    argv: &[String],
    working_directory: &str,
    environment_overrides: &HashMap<String, String>,
    stdin_payload: &[u8],
    timeout_seconds: u32,
    start_new_session: bool,
    allow_network: bool,
) -> Result<ExecutedCommandOutcome, Status> {
    let validated_command = validate_shell_command(command)
        .map_err(|error| Status::invalid_argument(error.to_string()))?;
    if validated_command.trim().is_empty() {
        return Err(Status::invalid_argument("command is required"));
    }
    CommandPolicy::from_allow_network(allow_network).validate(&validated_command, argv)?;
    let (spawn_command, spawn_args) = if argv.is_empty() {
        (
            default_shell_command(),
            vec!["-lc".to_string(), validated_command.clone()],
        )
    } else {
        (validated_command.clone(), argv.to_vec())
    };
    let mut command_builder = prepare_process_command(
        &spawn_command,
        &spawn_args,
        working_directory,
        environment_overrides,
        start_new_session,
    )?;
    command_builder.stdin(std::process::Stdio::piped());
    command_builder.stdout(std::process::Stdio::piped());
    command_builder.stderr(std::process::Stdio::piped());

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
    let stdout_task = tokio::spawn(read_to_capped_bytes(stdout, COMMAND_OUTPUT_BYTE_LIMIT));
    let stderr_task = tokio::spawn(read_to_capped_bytes(stderr, COMMAND_OUTPUT_BYTE_LIMIT));
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

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis() as u64)
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn read_to_capped_bytes_truncates_and_marks_output() {
        let (reader, mut writer) = tokio::io::duplex(64);
        let reader_task = tokio::spawn(read_to_capped_bytes(reader, 8));

        writer.write_all(b"abcdefghijklmnop").await.unwrap();
        drop(writer);

        let output = reader_task.await.unwrap().unwrap();
        assert_eq!(&output[..8], b"abcdefgh");
        assert!(output.ends_with(COMMAND_TRUNCATION_SUFFIX));
    }

    #[test]
    fn command_policy_blocks_explicit_network_without_grant() {
        let error = CommandPolicy::from_allow_network(false)
            .validate("curl", &["https://example.com".to_string()])
            .unwrap_err();

        assert_eq!(error.code(), tonic::Code::PermissionDenied);
    }

    #[test]
    fn command_policy_allows_network_when_granted() {
        CommandPolicy::from_allow_network(true)
            .validate("curl", &["https://example.com".to_string()])
            .unwrap();
    }

    #[tokio::test]
    async fn execute_shell_command_times_out_and_kills_child() {
        let outcome = execute_shell_command(
            "sleep",
            &["5".to_string()],
            "",
            &HashMap::new(),
            b"",
            1,
            false,
            false,
        )
        .await
        .unwrap();

        assert_eq!(outcome.exit_code, 124);
        assert!(outcome.timed_out);
        assert!(outcome.killed);
    }
}
