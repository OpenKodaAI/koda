use std::collections::HashMap;
use std::path::Path;

use anyhow::Result;
use koda_observability::{health_details, init_tracing};
use koda_proto::common::v1::{HealthRequest, HealthResponse};
use koda_proto::security::v1::security_guard_service_server::{
    SecurityGuardService, SecurityGuardServiceServer,
};
use koda_proto::security::v1::{
    RedactValueRequest, RedactValueResponse, SanitizeEnvironmentRequest,
    SanitizeEnvironmentResponse, ValidateFilePolicyRequest, ValidateFilePolicyResponse,
    ValidateObjectKeyRequest, ValidateObjectKeyResponse, ValidateRuntimePathRequest,
    ValidateRuntimePathResponse, ValidateShellCommandRequest, ValidateShellCommandResponse,
};
use koda_security_core::{
    canonicalize_existing_file, redact_value, sanitize_env, validate_runtime_path,
    validate_scoped_object_key, validate_shell_command,
};
use serde_json::Value;
use tokio::fs;
use tokio::net::UnixListener;
use tokio_stream::wrappers::UnixListenerStream;
use tonic::transport::Server;
use tonic::{Request, Response, Status};

const SERVICE_NAME: &str = "koda-security-service";

#[derive(Default)]
struct SecurityServer;

#[tonic::async_trait]
impl SecurityGuardService for SecurityServer {
    async fn validate_shell_command(
        &self,
        request: Request<ValidateShellCommandRequest>,
    ) -> Result<Response<ValidateShellCommandResponse>, Status> {
        let payload = request.into_inner();
        let command = validate_shell_command(&payload.command)
            .map_err(|error| Status::invalid_argument(error.to_string()))?;
        Ok(Response::new(ValidateShellCommandResponse { command }))
    }

    async fn sanitize_environment(
        &self,
        request: Request<SanitizeEnvironmentRequest>,
    ) -> Result<Response<SanitizeEnvironmentResponse>, Status> {
        let payload = request.into_inner();
        let base_env = payload
            .base_env
            .into_iter()
            .map(|(key, value)| (key, Value::String(value)))
            .collect();
        let env_overrides = payload
            .env_overrides
            .into_iter()
            .map(|(key, value)| (key, Value::String(value)))
            .collect();
        let env = sanitize_env(&base_env, &payload.allowed_provider_keys, &env_overrides)
            .into_iter()
            .filter_map(|(key, value)| value.as_str().map(|inner| (key, inner.to_string())))
            .collect::<HashMap<String, String>>();
        Ok(Response::new(SanitizeEnvironmentResponse { env }))
    }

    async fn validate_runtime_path(
        &self,
        request: Request<ValidateRuntimePathRequest>,
    ) -> Result<Response<ValidateRuntimePathResponse>, Status> {
        let payload = request.into_inner();
        let value = validate_runtime_path(&payload.value, payload.allow_empty)
            .map_err(|error| Status::invalid_argument(error.to_string()))?;
        Ok(Response::new(ValidateRuntimePathResponse { value }))
    }

    async fn validate_object_key(
        &self,
        request: Request<ValidateObjectKeyRequest>,
    ) -> Result<Response<ValidateObjectKeyResponse>, Status> {
        let payload = request.into_inner();
        let object_key = validate_scoped_object_key(&payload.agent_id, &payload.object_key)
            .map_err(|error| Status::invalid_argument(error.to_string()))?;
        Ok(Response::new(ValidateObjectKeyResponse { object_key }))
    }

    async fn redact_value(
        &self,
        request: Request<RedactValueRequest>,
    ) -> Result<Response<RedactValueResponse>, Status> {
        let payload = request.into_inner();
        let value = serde_json::from_str::<Value>(&payload.value_json)
            .map_err(|error| Status::invalid_argument(format!("invalid value_json: {error}")))?;
        let redacted = redact_value(
            &value,
            if payload.key_hint.trim().is_empty() {
                None
            } else {
                Some(payload.key_hint.as_str())
            },
        );
        Ok(Response::new(RedactValueResponse {
            value_json: redacted.to_string(),
        }))
    }

    async fn validate_file_policy(
        &self,
        request: Request<ValidateFilePolicyRequest>,
    ) -> Result<Response<ValidateFilePolicyResponse>, Status> {
        let payload = request.into_inner();
        if payload.path.trim().is_empty() {
            return Err(Status::invalid_argument("path is required"));
        }
        let canonical_path = if payload.require_file {
            canonicalize_existing_file(Path::new(&payload.path))
                .map_err(|error| Status::invalid_argument(error.to_string()))?
        } else {
            Path::new(&payload.path)
                .canonicalize()
                .map_err(|error| Status::invalid_argument(error.to_string()))?
        };
        Ok(Response::new(ValidateFilePolicyResponse {
            canonical_path: canonical_path.display().to_string(),
        }))
    }

    async fn health(
        &self,
        _request: Request<HealthRequest>,
    ) -> Result<Response<HealthResponse>, Status> {
        let mut details = health_details(SERVICE_NAME);
        details.insert("authoritative".to_string(), "true".to_string());
        details.insert("production_ready".to_string(), "true".to_string());
        details.insert("maturity".to_string(), "ga".to_string());
        details.insert(
            "capabilities".to_string(),
            "shell_command,env_sanitization,runtime_path,object_key,redaction,file_policy"
                .to_string(),
        );
        details.insert("cutover_allowed".to_string(), "true".to_string());
        Ok(Response::new(HealthResponse {
            service: SERVICE_NAME.to_string(),
            ready: true,
            status: "ready".to_string(),
            details,
        }))
    }
}

async fn serve_target(target: &str) -> Result<()> {
    let service = SecurityGuardServiceServer::new(SecurityServer);
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
            .serve_with_incoming(incoming)
            .await?;
    } else {
        let addr = target.parse()?;
        Server::builder().add_service(service).serve(addr).await?;
    }
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    init_tracing(SERVICE_NAME);
    let target =
        std::env::var("SECURITY_GRPC_TARGET").unwrap_or_else(|_| "127.0.0.1:50065".to_string());
    serve_target(&target).await
}
