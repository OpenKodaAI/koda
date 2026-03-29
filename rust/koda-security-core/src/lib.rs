use regex::Regex;
use serde_json::{Map, Value};
use std::io;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

const SAFE_EXACT_KEYS: &[&str] = &[
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TERM",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TMP",
    "TEMP",
    "PWD",
    "SSH_AUTH_SOCK",
    "DISPLAY",
    "XAUTHORITY",
    "COLORTERM",
    "TERM_PROGRAM",
    "TERM_PROGRAM_VERSION",
    "CI",
    "NO_COLOR",
    "FORCE_COLOR",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
];

const SAFE_PREFIXES: &[&str] = &["XDG_", "GIT_", "SSH_"];
const STRIP_PREFIXES: &[&str] = &[
    "BOT_",
    "JIRA_",
    "CONFLUENCE_",
    "GWS_",
    "POSTGRES_",
    "RUNTIME_",
    "MEMORY_",
    "KNOWLEDGE_",
    "SCHEDULER_",
    "RUNBOOK_",
    "ELEVENLABS_",
    "AWS_",
    "CLAUDE_",
    "CODEX_",
    "GEMINI_",
    "OLLAMA_",
    "OPENAI_",
    "ANTHROPIC_",
    "GOOGLE_",
];

fn sensitive_key_pattern() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r"(TOKEN|PASSWORD|SECRET|API_KEY|PRIVATE_KEY|CLIENT_KEY|POSTGRES_URL)").unwrap()
    })
}

fn secret_key_pattern() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r"(?i)(token|secret|password|passwd|authorization|cookie|api[_-]?key|session)")
            .unwrap()
    })
}

fn bearer_pattern() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| Regex::new(r"(?i)bearer\s+[a-z0-9._\-]+").unwrap())
}

fn cookie_pattern() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| Regex::new(r"(?i)(cookie\s*[:=]\s*)([^;\n]+)").unwrap())
}

fn url_credential_pattern() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| Regex::new(r"(https?://)([^/\s:@]+):([^/\s@]+)@").unwrap())
}

fn long_secret_pattern() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| Regex::new(r"(?i)\b[a-z0-9_\-]{24,}\b").unwrap())
}

pub fn canonicalize_under(root: &Path, candidate: &Path) -> io::Result<PathBuf> {
    let canonical_root = root.canonicalize()?;
    let canonical_candidate = candidate.canonicalize()?;
    if canonical_candidate.starts_with(&canonical_root) {
        Ok(canonical_candidate)
    } else {
        Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "candidate escapes canonical root",
        ))
    }
}

pub fn canonicalize_existing_file(candidate: &Path) -> io::Result<PathBuf> {
    let canonical_candidate = candidate.canonicalize()?;
    let metadata = canonical_candidate.metadata()?;
    if metadata.is_file() {
        Ok(canonical_candidate)
    } else {
        Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "candidate is not a regular file",
        ))
    }
}

pub fn validate_logical_object_key(candidate: &str) -> io::Result<String> {
    let normalized = candidate.trim();
    if normalized.is_empty() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "object key is required",
        ));
    }
    if normalized.starts_with('/') || normalized.starts_with('\\') || normalized.contains('\\') {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "object key must be logical and relative",
        ));
    }
    if normalized.contains('\0') {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "object key contains invalid characters",
        ));
    }
    let parts = normalized.split('/').map(str::trim).collect::<Vec<_>>();
    if parts.is_empty()
        || parts
            .iter()
            .any(|part| part.is_empty() || *part == "." || *part == "..")
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "object key contains invalid path segments",
        ));
    }
    Ok(parts.join("/"))
}

pub fn validate_scoped_object_key(agent_scope: &str, candidate: &str) -> io::Result<String> {
    let normalized_agent = agent_scope.trim().to_ascii_lowercase();
    if normalized_agent.is_empty() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "agent scope is required",
        ));
    }
    let normalized_key = validate_logical_object_key(candidate)?;
    let expected_prefix = format!("{normalized_agent}/");
    if normalized_key == normalized_agent || normalized_key.starts_with(&expected_prefix) {
        Ok(normalized_key)
    } else {
        Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "object key escapes agent scope",
        ))
    }
}

pub fn redact_secret_like(input: &str) -> String {
    if input.len() <= 8 {
        return "***".to_string();
    }
    format!("{}***{}", &input[..3], &input[input.len() - 3..])
}

pub fn validate_shell_command(command: &str) -> io::Result<String> {
    if command.contains('\n') || command.contains('\r') {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "newline characters are not allowed in commands",
        ));
    }
    if command.contains('\0') {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "command contains invalid characters",
        ));
    }
    Ok(command.to_string())
}

pub fn validate_runtime_path(value: &str, allow_empty: bool) -> io::Result<String> {
    let normalized = value.trim();
    if normalized.is_empty() {
        if allow_empty {
            return Ok(String::new());
        }
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "runtime path is required",
        ));
    }
    if normalized.contains('\0') || normalized.contains('\n') || normalized.contains('\r') {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "runtime path contains invalid characters",
        ));
    }
    Ok(normalized.to_string())
}

pub fn sanitize_env(
    base_env: &Map<String, Value>,
    allowed_provider_keys: &[String],
    env_overrides: &Map<String, Value>,
) -> Map<String, Value> {
    let mut sanitized = Map::new();
    for (key, value) in base_env {
        let Some(text_value) = value.as_str() else {
            continue;
        };
        if SAFE_EXACT_KEYS.contains(&key.as_str())
            || allowed_provider_keys
                .iter()
                .any(|candidate| candidate == key)
            || SAFE_PREFIXES.iter().any(|prefix| key.starts_with(prefix))
        {
            sanitized.insert(key.clone(), Value::String(text_value.to_string()));
            continue;
        }
        if STRIP_PREFIXES.iter().any(|prefix| key.starts_with(prefix)) {
            continue;
        }
        if sensitive_key_pattern().is_match(key) {
            continue;
        }
    }
    for (key, value) in env_overrides {
        let text = match value {
            Value::String(inner) => inner.clone(),
            other => other.to_string(),
        };
        sanitized.insert(key.clone(), Value::String(text));
    }
    sanitized
}

pub fn redact_text(input: &str) -> String {
    let redacted = bearer_pattern().replace_all(input, "Bearer [REDACTED]");
    let redacted = cookie_pattern().replace_all(&redacted, "$1[REDACTED]");
    let redacted = url_credential_pattern().replace_all(&redacted, "$1[REDACTED]:[REDACTED]@");
    long_secret_pattern()
        .replace_all(&redacted, "[REDACTED]")
        .into_owned()
}

pub fn redact_value(value: &Value, key_hint: Option<&str>) -> Value {
    if key_hint.is_some_and(|hint| secret_key_pattern().is_match(hint)) {
        return Value::String("[REDACTED]".to_string());
    }
    match value {
        Value::Null | Value::Bool(_) | Value::Number(_) => value.clone(),
        Value::String(inner) => Value::String(redact_text(inner)),
        Value::Array(items) => {
            Value::Array(items.iter().map(|item| redact_value(item, None)).collect())
        }
        Value::Object(obj) => {
            let mut redacted = Map::new();
            for (key, inner) in obj {
                redacted.insert(key.clone(), redact_value(inner, Some(key)));
            }
            Value::Object(redacted)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{
        redact_secret_like, redact_text, redact_value, sanitize_env, validate_logical_object_key,
        validate_runtime_path, validate_scoped_object_key, validate_shell_command,
    };
    use serde_json::{Map, Value};

    #[test]
    fn redacts_middle_of_long_secret() {
        assert_eq!(redact_secret_like("supersecretvalue"), "sup***lue");
    }

    #[test]
    fn accepts_normalized_logical_object_keys() {
        assert_eq!(
            validate_logical_object_key("agent_a/screenshots/frame.png").expect("valid object key"),
            "agent_a/screenshots/frame.png"
        );
    }

    #[test]
    fn rejects_escape_segments_in_logical_object_keys() {
        assert!(validate_logical_object_key("../secret.txt").is_err());
        assert!(validate_logical_object_key("agent_a/../secret.txt").is_err());
        assert!(validate_logical_object_key("/absolute/path").is_err());
    }

    #[test]
    fn accepts_agent_scoped_object_keys() {
        assert_eq!(
            validate_scoped_object_key("AGENT_A", "agent_a/screenshots/frame.png")
                .expect("valid scoped object key"),
            "agent_a/screenshots/frame.png"
        );
    }

    #[test]
    fn rejects_cross_agent_object_keys() {
        assert!(validate_scoped_object_key("agent_a", "other/frame.png").is_err());
        assert!(validate_scoped_object_key("", "agent_a/frame.png").is_err());
    }

    #[test]
    fn shell_command_rejects_newlines() {
        assert!(validate_shell_command("echo safe\nrm -rf /").is_err());
        assert!(validate_shell_command("echo safe\rrm -rf /").is_err());
        assert_eq!(
            validate_shell_command("echo safe").expect("command should pass"),
            "echo safe"
        );
    }

    #[test]
    fn runtime_path_rejects_control_characters() {
        assert!(validate_runtime_path("/tmp/ok", false).is_ok());
        assert!(validate_runtime_path("/tmp/bad\npath", false).is_err());
        assert!(validate_runtime_path("", false).is_err());
        assert_eq!(validate_runtime_path("", true).expect("allow empty"), "");
    }

    #[test]
    fn redaction_replaces_bearer_and_secret_keys() {
        let payload = json!({
            "authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456",
            "nested": {
                "cookie": "session=supersecretcookie",
                "url": "https://user:pass@example.com/path",
            },
            "plain": "token abcdefghijklmnopqrstuvwxyz123456"
        });
        let redacted = redact_value(&payload, None);
        assert_eq!(redacted["authorization"], "[REDACTED]");
        assert_eq!(redacted["nested"]["cookie"], "[REDACTED]");
        assert_eq!(
            redacted["nested"]["url"],
            Value::String("https://[REDACTED]:[REDACTED]@example.com/path".to_string())
        );
        assert_eq!(
            redacted["plain"],
            Value::String("token [REDACTED]".to_string())
        );
    }

    #[test]
    fn redact_text_masks_bearer_tokens() {
        assert_eq!(
            redact_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456"),
            "Authorization: Bearer [REDACTED]"
        );
    }

    #[test]
    fn sanitize_env_filters_sensitive_keys() {
        let mut base_env = Map::new();
        base_env.insert("PATH".to_string(), Value::String("/usr/bin".to_string()));
        base_env.insert(
            "BOT_TOKEN".to_string(),
            Value::String("telegram-secret".to_string()),
        );
        base_env.insert(
            "OPENAI_API_KEY".to_string(),
            Value::String("openai-secret".to_string()),
        );
        base_env.insert(
            "ANTHROPIC_API_KEY".to_string(),
            Value::String("anthropic-secret".to_string()),
        );
        let env_overrides = Map::from_iter([(
            "LOCAL_FLAG".to_string(),
            Value::String("enabled".to_string()),
        )]);
        let sanitized = sanitize_env(
            &base_env,
            &["ANTHROPIC_API_KEY".to_string()],
            &env_overrides,
        );
        assert_eq!(
            sanitized.get("PATH"),
            Some(&Value::String("/usr/bin".to_string()))
        );
        assert_eq!(
            sanitized.get("ANTHROPIC_API_KEY"),
            Some(&Value::String("anthropic-secret".to_string()))
        );
        assert_eq!(
            sanitized.get("LOCAL_FLAG"),
            Some(&Value::String("enabled".to_string()))
        );
        assert!(!sanitized.contains_key("BOT_TOKEN"));
        assert!(!sanitized.contains_key("OPENAI_API_KEY"));
    }
}
