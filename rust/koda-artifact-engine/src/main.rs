use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::Result;
use aws_config::BehaviorVersion;
use aws_credential_types::Credentials;
use aws_sdk_s3::config::Region;
use aws_sdk_s3::primitives::ByteStream;
use aws_sdk_s3::Client as S3Client;
use koda_observability::{health_details, init_tracing};
use koda_proto::artifact::v1::artifact_engine_service_server::{
    ArtifactEngineService, ArtifactEngineServiceServer,
};
use koda_proto::artifact::v1::{
    ArtifactDescriptor, GenerateEvidenceByArtifactIdRequest, GenerateEvidenceResponse,
    GetArtifactMetadataByArtifactIdRequest, GetArtifactMetadataResponse, PutArtifactRequest,
    PutArtifactResponse,
};
use koda_proto::common::v1::{HealthRequest, HealthResponse};
use koda_security_core::validate_scoped_object_key;
use serde_json::json;
use sha2::{Digest, Sha256};
use tokio::fs;
use tokio::io::AsyncWriteExt;
use tokio::net::UnixListener;
use tokio_postgres::NoTls;
use tokio_stream::wrappers::UnixListenerStream;
use tonic::transport::Server;
use tonic::{Request, Response, Status};

const SERVICE_NAME: &str = "koda-artifact-engine";
const OBJECT_STORAGE_UPLOAD_OUTCOME: &str = "persisted_object_storage";
const OBJECT_STORAGE_STORAGE_BACKING: &str = "object_storage_postgres";

#[derive(Clone, Default)]
struct ArtifactServer;

#[derive(Debug, Clone, PartialEq, Eq)]
struct ObjectStoreConfig {
    bucket: String,
    prefix: String,
    endpoint_url: Option<String>,
    region: Option<String>,
    access_key_id: Option<String>,
    secret_access_key: Option<String>,
}

impl ObjectStoreConfig {
    fn scoped_key(&self, object_key: &str) -> String {
        let normalized_prefix = self.prefix.trim().trim_matches('/');
        let normalized_key = object_key.trim().trim_start_matches('/');
        if normalized_prefix.is_empty() {
            normalized_key.to_string()
        } else {
            format!("{normalized_prefix}/{normalized_key}")
        }
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
struct ArtifactRecordDescriptor {
    artifact_id: String,
    object_key: String,
    content_hash: String,
    mime_type: String,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
struct ArtifactRecord {
    agent_id: String,
    descriptor: ArtifactRecordDescriptor,
    source_path: String,
    size_bytes: u64,
    storage_backing: String,
    object_store_bucket: String,
    object_store_key: String,
    metadata_json: String,
    evidence_json: String,
    upload_outcome: String,
    created_at_ms: u128,
    updated_at_ms: u128,
}

#[derive(Debug, Clone)]
struct StoredArtifact {
    record: ArtifactRecord,
    payload: Vec<u8>,
}

struct MetadataJsonContext<'a> {
    source_path: &'a str,
    descriptor: &'a ArtifactDescriptor,
    size_bytes: u64,
    upload_outcome: &'a str,
    source_metadata_json: &'a str,
    purpose: &'a str,
    storage_backing: &'a str,
    object_store_bucket: &'a str,
    object_store_key: &'a str,
}

struct PersistUploadedRecordRequest<'a> {
    agent_id: &'a str,
    logical_filename: &'a str,
    object_key: String,
    mime_type: String,
    source_metadata_json: String,
    purpose: String,
    staging_path: &'a Path,
    content_hash: String,
    size_bytes: u64,
}

/// Maximum number of bytes accepted per artifact upload. Controlled by
/// `ARTIFACT_MAX_UPLOAD_BYTES`. Returns `None` when unset, which disables
/// the limit (legacy behaviour for tests and one-off development runs).
fn max_upload_bytes() -> Option<u64> {
    match std::env::var("ARTIFACT_MAX_UPLOAD_BYTES") {
        Ok(raw) => raw.trim().parse::<u64>().ok().filter(|value| *value > 0),
        Err(_) => None,
    }
}

fn mime_type_for(path: &Path) -> String {
    match path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
        .as_str()
    {
        "txt" | "md" | "py" | "json" | "yaml" | "yml" | "xml" | "csv" | "tsv" | "log" => {
            "text/plain".to_string()
        }
        "html" | "htm" => "text/html".to_string(),
        "pdf" => "application/pdf".to_string(),
        "png" => "image/png".to_string(),
        "jpg" | "jpeg" => "image/jpeg".to_string(),
        "gif" => "image/gif".to_string(),
        "webp" => "image/webp".to_string(),
        "mp4" => "video/mp4".to_string(),
        "mov" => "video/quicktime".to_string(),
        "wav" => "audio/wav".to_string(),
        "mp3" => "audio/mpeg".to_string(),
        _ => "application/octet-stream".to_string(),
    }
}

fn artifact_id_for_name(logical_filename: &str, content_hash: &str) -> String {
    let suffix = Path::new(logical_filename)
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("artifact");
    format!("{}-{}", &content_hash[..16], suffix)
}

fn default_object_key(agent_id: &str, content_hash: &str, logical_filename: &str) -> String {
    let suffix = Path::new(logical_filename)
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| format!(".{value}"))
        .unwrap_or_default();
    format!(
        "{}/{content_hash}{suffix}",
        agent_id.trim().to_ascii_lowercase()
    )
}

fn staging_payload_path(agent_id: &str) -> PathBuf {
    artifact_store_root()
        .join(agent_id.trim().to_ascii_lowercase())
        .join("staging")
        .join(format!("upload-{}-{}.bin", now_ms(), std::process::id()))
}

fn proto_descriptor(record: &ArtifactRecordDescriptor) -> ArtifactDescriptor {
    ArtifactDescriptor {
        artifact_id: record.artifact_id.clone(),
        object_key: record.object_key.clone(),
        content_hash: record.content_hash.clone(),
        mime_type: record.mime_type.clone(),
    }
}

fn normalize_agent_scope(agent_id: &str) -> Result<String, &'static str> {
    let normalized = agent_id.trim().to_ascii_lowercase();
    if normalized.is_empty() {
        return Err("agent_id is required");
    }
    Ok(normalized)
}

fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn artifact_store_root() -> PathBuf {
    std::env::var("ARTIFACT_STORE_DIR")
        .ok()
        .map(PathBuf::from)
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| PathBuf::from("/tmp/koda/artifact-store"))
}

fn artifact_postgres_dsn() -> String {
    std::env::var("KNOWLEDGE_V2_POSTGRES_DSN")
        .unwrap_or_default()
        .trim()
        .to_string()
}

fn artifact_postgres_schema() -> String {
    let schema = std::env::var("KNOWLEDGE_V2_POSTGRES_SCHEMA")
        .unwrap_or_else(|_| "knowledge_v2".to_string());
    let trimmed = schema.trim();
    if trimmed.is_empty() {
        "knowledge_v2".to_string()
    } else {
        trimmed.to_string()
    }
}

fn optional_env(key: &str) -> Option<String> {
    std::env::var(key)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn artifact_object_store_config() -> Option<ObjectStoreConfig> {
    let bucket = optional_env("KNOWLEDGE_V2_S3_BUCKET")?;
    Some(ObjectStoreConfig {
        bucket,
        prefix: std::env::var("KNOWLEDGE_V2_S3_PREFIX")
            .unwrap_or_else(|_| "knowledge-v2".to_string())
            .trim()
            .to_string(),
        endpoint_url: optional_env("KNOWLEDGE_V2_S3_ENDPOINT_URL"),
        region: optional_env("KNOWLEDGE_V2_S3_REGION"),
        access_key_id: optional_env("KNOWLEDGE_V2_S3_ACCESS_KEY_ID"),
        secret_access_key: optional_env("KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY"),
    })
}

fn artifact_object_store_config_for_bucket(
    bucket: &str,
) -> Result<ObjectStoreConfig, &'static str> {
    let normalized_bucket = bucket.trim();
    if normalized_bucket.is_empty() {
        return Err("object storage bucket is not configured");
    }
    Ok(ObjectStoreConfig {
        bucket: normalized_bucket.to_string(),
        prefix: String::new(),
        endpoint_url: optional_env("KNOWLEDGE_V2_S3_ENDPOINT_URL"),
        region: optional_env("KNOWLEDGE_V2_S3_REGION"),
        access_key_id: optional_env("KNOWLEDGE_V2_S3_ACCESS_KEY_ID"),
        secret_access_key: optional_env("KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY"),
    })
}

fn metadata_json_for(context: &MetadataJsonContext<'_>) -> String {
    json!({
        "artifact_id": context.descriptor.artifact_id,
        "object_key": context.descriptor.object_key,
        "content_hash": context.descriptor.content_hash,
        "mime_type": context.descriptor.mime_type,
        "logical_filename": context.source_path,
        "size_bytes": context.size_bytes,
        "upload_outcome": context.upload_outcome,
        "storage_backing": context.storage_backing,
        "object_store_bucket": if context.object_store_bucket.trim().is_empty() { None::<String> } else { Some(context.object_store_bucket.to_string()) },
        "object_store_key": if context.object_store_key.trim().is_empty() { None::<String> } else { Some(context.object_store_key.to_string()) },
        "source_metadata_json": context.source_metadata_json,
        "purpose": context.purpose,
    })
    .to_string()
}

async fn artifact_object_store_client(config: &ObjectStoreConfig) -> Result<S3Client, Status> {
    let mut loader = aws_config::defaults(BehaviorVersion::latest());
    if let Some(region) = &config.region {
        loader = loader.region(Region::new(region.clone()));
    }
    if let (Some(access_key_id), Some(secret_access_key)) =
        (&config.access_key_id, &config.secret_access_key)
    {
        loader = loader.credentials_provider(Credentials::new(
            access_key_id,
            secret_access_key,
            None,
            None,
            "artifact-engine-static",
        ));
    }
    let shared = loader.load().await;
    let mut builder = aws_sdk_s3::config::Builder::from(&shared);
    if let Some(endpoint_url) = &config.endpoint_url {
        builder = builder.endpoint_url(endpoint_url).force_path_style(true);
    }
    if let Some(region) = &config.region {
        builder = builder.region(Region::new(region.clone()));
    }
    Ok(S3Client::from_conf(builder.build()))
}

async fn artifact_object_store_ready(config: &ObjectStoreConfig) -> Result<(), Status> {
    artifact_object_store_client(config)
        .await?
        .head_bucket()
        .bucket(&config.bucket)
        .send()
        .await
        .map_err(|error| {
            Status::unavailable(format!("failed to reach artifact object storage: {error}"))
        })?;
    Ok(())
}

async fn upload_object_store_payload(
    config: &ObjectStoreConfig,
    object_store_key: &str,
    mime_type: &str,
    staging_path: &Path,
) -> Result<(), anyhow::Error> {
    let client = artifact_object_store_client(config)
        .await
        .map_err(anyhow::Error::msg)?;
    let body = ByteStream::from_path(staging_path.to_path_buf()).await?;
    let mut request = client
        .put_object()
        .bucket(&config.bucket)
        .key(object_store_key)
        .body(body);
    if !mime_type.trim().is_empty() {
        request = request.content_type(mime_type.trim().to_string());
    }
    request.send().await?;
    Ok(())
}

async fn delete_object_store_payload(
    config: &ObjectStoreConfig,
    object_store_key: &str,
) -> Result<(), anyhow::Error> {
    artifact_object_store_client(config)
        .await
        .map_err(anyhow::Error::msg)?
        .delete_object()
        .bucket(&config.bucket)
        .key(object_store_key)
        .send()
        .await?;
    Ok(())
}

async fn load_object_store_payload(
    bucket: &str,
    object_store_key: &str,
) -> Result<Vec<u8>, Status> {
    let config =
        artifact_object_store_config_for_bucket(bucket).map_err(Status::failed_precondition)?;
    let response = artifact_object_store_client(&config)
        .await?
        .get_object()
        .bucket(&config.bucket)
        .key(object_store_key)
        .send()
        .await
        .map_err(|error| {
            Status::internal(format!("failed to fetch artifact object payload: {error}"))
        })?;
    let payload = response.body.collect().await.map_err(|error| {
        Status::internal(format!("failed to read artifact object payload: {error}"))
    })?;
    Ok(payload.into_bytes().to_vec())
}

async fn artifact_postgres_client() -> Result<tokio_postgres::Client, Status> {
    let dsn = artifact_postgres_dsn();
    if dsn.is_empty() {
        return Err(Status::failed_precondition(
            "knowledge postgres dsn is not configured",
        ));
    }
    let (client, connection) = tokio_postgres::connect(&dsn, NoTls)
        .await
        .map_err(|error| {
            Status::unavailable(format!("failed to connect to artifact postgres: {error}"))
        })?;
    tokio::spawn(async move {
        let _ = connection.await;
    });
    Ok(client)
}

async fn ensure_artifact_tables(client: &tokio_postgres::Client) -> Result<String, Status> {
    let schema = artifact_postgres_schema();
    client
        .batch_execute(&format!(r#"CREATE SCHEMA IF NOT EXISTS "{schema}";"#))
        .await
        .map_err(|error| Status::internal(format!("failed to ensure artifact schema: {error}")))?;
    client
        .batch_execute(&format!(
            r#"
            CREATE TABLE IF NOT EXISTS "{schema}"."artifact_objects" (
                agent_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                object_key TEXT NOT NULL,
                logical_filename TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL,
                mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                storage_backing TEXT NOT NULL DEFAULT 'object_storage_postgres',
                object_store_bucket TEXT NOT NULL DEFAULT '',
                object_store_key TEXT NOT NULL DEFAULT '',
                source_metadata_json TEXT NOT NULL DEFAULT '{{}}',
                metadata_json TEXT NOT NULL DEFAULT '{{}}',
                evidence_json TEXT NOT NULL DEFAULT '',
                upload_outcome TEXT NOT NULL DEFAULT '',
                size_bytes BIGINT NOT NULL DEFAULT 0,
                payload BYTEA,
                created_at_ms BIGINT NOT NULL DEFAULT 0,
                updated_at_ms BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (agent_id, artifact_id)
            );
            ALTER TABLE "{schema}"."artifact_objects"
                ADD COLUMN IF NOT EXISTS storage_backing TEXT NOT NULL DEFAULT 'object_storage_postgres';
            ALTER TABLE "{schema}"."artifact_objects"
                ADD COLUMN IF NOT EXISTS object_store_bucket TEXT NOT NULL DEFAULT '';
            ALTER TABLE "{schema}"."artifact_objects"
                ADD COLUMN IF NOT EXISTS object_store_key TEXT NOT NULL DEFAULT '';
            ALTER TABLE "{schema}"."artifact_objects"
                ALTER COLUMN payload DROP NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS artifact_objects_agent_object_key_idx
                ON "{schema}"."artifact_objects" (agent_id, object_key);
            "#
        ))
        .await
        .map_err(|error| Status::internal(format!("failed to ensure artifact tables: {error}")))?;
    Ok(schema)
}

async fn load_record_by_artifact_id(
    agent_id: &str,
    artifact_id: &str,
) -> Result<StoredArtifact, Status> {
    let client = artifact_postgres_client().await?;
    let schema = ensure_artifact_tables(&client).await?;
    let row = client
        .query_opt(
            &format!(
                r#"
                SELECT artifact_id,
                       object_key,
                       content_hash,
                       mime_type,
                       logical_filename,
                       storage_backing,
                       object_store_bucket,
                       object_store_key,
                       size_bytes,
                       metadata_json,
                       evidence_json,
                       upload_outcome,
                       created_at_ms,
                       updated_at_ms
                  FROM "{schema}"."artifact_objects"
                 WHERE agent_id = $1
                   AND artifact_id = $2
                "#
            ),
            &[&agent_id, &artifact_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to load artifact record: {error}")))?;
    let Some(row) = row else {
        return Err(Status::not_found(format!(
            "artifact not found: {artifact_id}"
        )));
    };
    let storage_backing = row.get::<_, String>("storage_backing");
    let object_store_bucket = row.get::<_, String>("object_store_bucket");
    let object_store_key = row.get::<_, String>("object_store_key");
    if storage_backing != OBJECT_STORAGE_STORAGE_BACKING
        || object_store_bucket.trim().is_empty()
        || object_store_key.trim().is_empty()
    {
        return Err(Status::failed_precondition(
            "artifact storage backing is not canonical object storage",
        ));
    }
    let payload = load_object_store_payload(&object_store_bucket, &object_store_key).await?;
    Ok(StoredArtifact {
        record: ArtifactRecord {
            agent_id: agent_id.to_string(),
            descriptor: ArtifactRecordDescriptor {
                artifact_id: row.get::<_, String>("artifact_id"),
                object_key: row.get::<_, String>("object_key"),
                content_hash: row.get::<_, String>("content_hash"),
                mime_type: row.get::<_, String>("mime_type"),
            },
            source_path: row.get::<_, String>("logical_filename"),
            size_bytes: row.get::<_, i64>("size_bytes") as u64,
            storage_backing,
            object_store_bucket,
            object_store_key,
            metadata_json: row.get::<_, String>("metadata_json"),
            evidence_json: row.get::<_, String>("evidence_json"),
            upload_outcome: row.get::<_, String>("upload_outcome"),
            created_at_ms: row.get::<_, i64>("created_at_ms") as u128,
            updated_at_ms: row.get::<_, i64>("updated_at_ms") as u128,
        },
        payload,
    })
}

async fn persist_uploaded_record(
    request: PersistUploadedRecordRequest<'_>,
) -> Result<ArtifactRecord> {
    let client = artifact_postgres_client()
        .await
        .map_err(anyhow::Error::msg)?;
    let schema = ensure_artifact_tables(&client)
        .await
        .map_err(anyhow::Error::msg)?;
    let descriptor = ArtifactDescriptor {
        artifact_id: artifact_id_for_name(request.logical_filename, &request.content_hash),
        object_key: request.object_key,
        content_hash: request.content_hash,
        mime_type: request.mime_type,
    };
    let config = artifact_object_store_config().ok_or_else(|| {
        anyhow::anyhow!("object storage is required but KNOWLEDGE_V2_S3_BUCKET is not configured")
    })?;
    let object_store_key = config.scoped_key(&descriptor.object_key);
    upload_object_store_payload(
        &config,
        &object_store_key,
        &descriptor.mime_type,
        request.staging_path,
    )
    .await?;
    let storage_backing = OBJECT_STORAGE_STORAGE_BACKING.to_string();
    let object_store_bucket = config.bucket.clone();
    let upload_outcome = OBJECT_STORAGE_UPLOAD_OUTCOME.to_string();
    let payload: Option<Vec<u8>> = None;
    let metadata_json = metadata_json_for(&MetadataJsonContext {
        source_path: request.logical_filename,
        descriptor: &descriptor,
        size_bytes: request.size_bytes,
        upload_outcome: &upload_outcome,
        source_metadata_json: &request.source_metadata_json,
        purpose: &request.purpose,
        storage_backing: &storage_backing,
        object_store_bucket: &object_store_bucket,
        object_store_key: &object_store_key,
    });
    let record = ArtifactRecord {
        agent_id: request.agent_id.to_string(),
        descriptor: ArtifactRecordDescriptor {
            artifact_id: descriptor.artifact_id,
            object_key: descriptor.object_key,
            content_hash: descriptor.content_hash,
            mime_type: descriptor.mime_type,
        },
        source_path: request.logical_filename.to_string(),
        size_bytes: request.size_bytes,
        storage_backing: storage_backing.clone(),
        object_store_bucket: object_store_bucket.clone(),
        object_store_key: object_store_key.clone(),
        metadata_json,
        evidence_json: String::new(),
        upload_outcome: upload_outcome.clone(),
        created_at_ms: now_ms(),
        updated_at_ms: now_ms(),
    };
    let persist_result = client
        .execute(
            &format!(
                r#"
                INSERT INTO "{schema}"."artifact_objects" (
                    agent_id,
                    artifact_id,
                    object_key,
                    logical_filename,
                    content_hash,
                    mime_type,
                    storage_backing,
                    object_store_bucket,
                    object_store_key,
                    source_metadata_json,
                    metadata_json,
                    evidence_json,
                    upload_outcome,
                    size_bytes,
                    payload,
                    created_at_ms,
                    updated_at_ms
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17
                )
                ON CONFLICT (agent_id, artifact_id) DO UPDATE SET
                    object_key = EXCLUDED.object_key,
                    logical_filename = EXCLUDED.logical_filename,
                    content_hash = EXCLUDED.content_hash,
                    mime_type = EXCLUDED.mime_type,
                    storage_backing = EXCLUDED.storage_backing,
                    object_store_bucket = EXCLUDED.object_store_bucket,
                    object_store_key = EXCLUDED.object_store_key,
                    source_metadata_json = EXCLUDED.source_metadata_json,
                    metadata_json = EXCLUDED.metadata_json,
                    evidence_json = EXCLUDED.evidence_json,
                    upload_outcome = EXCLUDED.upload_outcome,
                    size_bytes = EXCLUDED.size_bytes,
                    payload = EXCLUDED.payload,
                    updated_at_ms = EXCLUDED.updated_at_ms
                "#
            ),
            &[
                &record.agent_id,
                &record.descriptor.artifact_id,
                &record.descriptor.object_key,
                &record.source_path,
                &record.descriptor.content_hash,
                &record.descriptor.mime_type,
                &record.storage_backing,
                &record.object_store_bucket,
                &record.object_store_key,
                &request.source_metadata_json,
                &record.metadata_json,
                &record.evidence_json,
                &record.upload_outcome,
                &(record.size_bytes as i64),
                &payload,
                &(record.created_at_ms as i64),
                &(record.updated_at_ms as i64),
            ],
        )
        .await;
    if let Err(error) = persist_result {
        if !record.object_store_key.is_empty() {
            let _ = delete_object_store_payload(&config, &record.object_store_key).await;
        }
        return Err(anyhow::anyhow!(
            "failed to persist artifact record: {error}"
        ));
    }
    Ok(record)
}

async fn count_indexed_artifacts() -> Result<i64, Status> {
    let client = artifact_postgres_client().await?;
    let schema = ensure_artifact_tables(&client).await?;
    let row = client
        .query_one(
            &format!(r#"SELECT COUNT(*)::BIGINT AS count FROM "{schema}"."artifact_objects""#),
            &[],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to count artifact rows: {error}")))?;
    Ok(row.get::<_, i64>("count"))
}

#[tonic::async_trait]
impl ArtifactEngineService for ArtifactServer {
    async fn put_artifact(
        &self,
        request: Request<tonic::Streaming<PutArtifactRequest>>,
    ) -> Result<Response<PutArtifactResponse>, Status> {
        let max_upload_bytes = max_upload_bytes();
        let mut stream = request.into_inner();
        let first = stream
            .message()
            .await
            .map_err(|error| {
                Status::internal(format!("failed to read artifact upload stream: {error}"))
            })?
            .ok_or_else(|| Status::invalid_argument("artifact upload stream is empty"))?;
        let agent_scope =
            normalize_agent_scope(&first.agent_id).map_err(Status::invalid_argument)?;
        let logical_filename = first.logical_filename.trim();
        if logical_filename.is_empty() {
            return Err(Status::invalid_argument("logical_filename is required"));
        }
        let mime_type = if first.mime_type.trim().is_empty() {
            mime_type_for(Path::new(logical_filename))
        } else {
            first.mime_type.trim().to_string()
        };
        let source_metadata_json = first.source_metadata_json.clone();
        let purpose = first.purpose.clone();
        let object_key_override = if first.object_key.trim().is_empty() {
            None
        } else {
            Some(
                validate_scoped_object_key(&agent_scope, first.object_key.trim()).map_err(
                    |error| Status::invalid_argument(format!("invalid object_key: {error}")),
                )?,
            )
        };
        let staging_path = staging_payload_path(&agent_scope);
        if let Some(parent) = staging_path.parent() {
            fs::create_dir_all(parent).await.map_err(|error| {
                Status::internal(format!("failed to prepare upload staging dir: {error}"))
            })?;
        }
        let mut file = fs::File::create(&staging_path).await.map_err(|error| {
            Status::internal(format!("failed to create upload staging file: {error}"))
        })?;
        let mut hasher = Sha256::new();
        let mut size_bytes = 0u64;
        if !first.data.is_empty() {
            size_bytes += first.data.len() as u64;
            if let Some(limit) = max_upload_bytes {
                if size_bytes > limit {
                    let _ = fs::remove_file(&staging_path).await;
                    return Err(Status::resource_exhausted(format!(
                        "artifact upload exceeds ARTIFACT_MAX_UPLOAD_BYTES ({limit} bytes)"
                    )));
                }
            }
            file.write_all(&first.data).await.map_err(|error| {
                Status::internal(format!("failed to write upload chunk: {error}"))
            })?;
            hasher.update(&first.data);
        }
        while let Some(chunk) = stream.message().await.map_err(|error| {
            Status::internal(format!("failed to read artifact upload stream: {error}"))
        })? {
            let chunk_agent_id = chunk.agent_id.trim();
            if !chunk_agent_id.is_empty() && chunk_agent_id != agent_scope {
                return Err(Status::invalid_argument(
                    "artifact upload chunk agent_id mismatch",
                ));
            }
            let chunk_filename = chunk.logical_filename.trim();
            if !chunk_filename.is_empty() && chunk_filename != logical_filename {
                return Err(Status::invalid_argument(
                    "artifact upload chunk logical_filename mismatch",
                ));
            }
            let chunk_object_key = chunk.object_key.trim();
            if !chunk_object_key.is_empty() {
                match object_key_override.as_deref() {
                    Some(expected) if expected != chunk_object_key => {
                        return Err(Status::invalid_argument(
                            "artifact upload chunk object_key mismatch",
                        ));
                    }
                    None => {
                        return Err(Status::invalid_argument(
                            "artifact upload chunk object_key is not allowed after initialization",
                        ));
                    }
                    _ => {}
                }
            }
            if !chunk.mime_type.trim().is_empty() && chunk.mime_type.trim() != mime_type {
                return Err(Status::invalid_argument(
                    "artifact upload chunk mime_type mismatch",
                ));
            }
            if !chunk.source_metadata_json.trim().is_empty()
                && chunk.source_metadata_json.trim() != source_metadata_json.trim()
            {
                return Err(Status::invalid_argument(
                    "artifact upload chunk source_metadata_json mismatch",
                ));
            }
            if !chunk.purpose.trim().is_empty() && chunk.purpose.trim() != purpose.trim() {
                return Err(Status::invalid_argument(
                    "artifact upload chunk purpose mismatch",
                ));
            }
            if !chunk.data.is_empty() {
                size_bytes += chunk.data.len() as u64;
                if let Some(limit) = max_upload_bytes {
                    if size_bytes > limit {
                        let _ = fs::remove_file(&staging_path).await;
                        return Err(Status::resource_exhausted(format!(
                            "artifact upload exceeds ARTIFACT_MAX_UPLOAD_BYTES ({limit} bytes)"
                        )));
                    }
                }
                file.write_all(&chunk.data).await.map_err(|error| {
                    Status::internal(format!("failed to write upload chunk: {error}"))
                })?;
                hasher.update(&chunk.data);
            }
        }
        file.flush().await.map_err(|error| {
            Status::internal(format!("failed to flush upload staging file: {error}"))
        })?;
        drop(file);
        // sha2 0.11's `finalize()` returns a `hybrid-array::Array<u8, N>` which
        // does not implement `std::fmt::LowerHex` directly — unlike the prior
        // `GenericArray`. Convert the raw bytes to lowercase hex explicitly so
        // the content-hash string stays identical across sha2 versions.
        let digest = hasher.finalize();
        let mut content_hash = String::with_capacity(digest.len() * 2);
        for byte in digest.as_slice() {
            use std::fmt::Write as _;
            write!(content_hash, "{byte:02x}").expect("write to string never fails");
        }
        let object_key = match object_key_override {
            Some(object_key) => object_key,
            None => default_object_key(&agent_scope, &content_hash, logical_filename),
        };
        let record = persist_uploaded_record(PersistUploadedRecordRequest {
            agent_id: &agent_scope,
            logical_filename,
            object_key,
            mime_type,
            source_metadata_json,
            purpose,
            staging_path: &staging_path,
            content_hash,
            size_bytes,
        })
        .await
        .map_err(|error| {
            Status::internal(format!("failed to persist uploaded artifact: {error}"))
        })?;
        let _ = fs::remove_file(&staging_path).await;
        Ok(Response::new(PutArtifactResponse {
            artifact: Some(proto_descriptor(&record.descriptor)),
            metadata_json: record.metadata_json,
            upload_outcome: record.upload_outcome,
        }))
    }

    async fn generate_evidence_by_artifact_id(
        &self,
        request: Request<GenerateEvidenceByArtifactIdRequest>,
    ) -> Result<Response<GenerateEvidenceResponse>, Status> {
        let payload = request.into_inner();
        let agent_scope =
            normalize_agent_scope(&payload.agent_id).map_err(Status::invalid_argument)?;
        let artifact_id = payload.artifact_id.trim();
        if artifact_id.is_empty() {
            return Err(Status::invalid_argument("artifact_id is required"));
        }
        let mut stored = load_record_by_artifact_id(&agent_scope, artifact_id).await?;
        let preview = if stored.record.descriptor.mime_type.starts_with("text/") {
            String::from_utf8_lossy(&stored.payload)
                .chars()
                .take(400)
                .collect::<String>()
        } else {
            String::new()
        };
        let evidence_json = json!({
            "artifact_id": stored.record.descriptor.artifact_id,
            "object_key": stored.record.descriptor.object_key,
            "mime_type": stored.record.descriptor.mime_type,
            "content_hash": stored.record.descriptor.content_hash,
            "size_bytes": stored.record.size_bytes,
            "excerpt": preview,
            "storage_backing": stored.record.storage_backing,
        })
        .to_string();
        stored.record.evidence_json = evidence_json.clone();
        stored.record.updated_at_ms = now_ms();
        let client = artifact_postgres_client().await?;
        let schema = ensure_artifact_tables(&client).await?;
        client
            .execute(
                &format!(
                    r#"
                    UPDATE "{schema}"."artifact_objects"
                       SET evidence_json = $3,
                           updated_at_ms = $4
                     WHERE agent_id = $1
                       AND artifact_id = $2
                    "#
                ),
                &[
                    &agent_scope,
                    &stored.record.descriptor.artifact_id,
                    &stored.record.evidence_json,
                    &(stored.record.updated_at_ms as i64),
                ],
            )
            .await
            .map_err(|error| {
                Status::internal(format!("failed to persist artifact evidence: {error}"))
            })?;
        Ok(Response::new(GenerateEvidenceResponse { evidence_json }))
    }

    async fn get_artifact_metadata_by_artifact_id(
        &self,
        request: Request<GetArtifactMetadataByArtifactIdRequest>,
    ) -> Result<Response<GetArtifactMetadataResponse>, Status> {
        let payload = request.into_inner();
        let agent_scope =
            normalize_agent_scope(&payload.agent_id).map_err(Status::invalid_argument)?;
        let artifact_id = payload.artifact_id.trim();
        if artifact_id.is_empty() {
            return Err(Status::invalid_argument("artifact_id is required"));
        }
        let stored = load_record_by_artifact_id(&agent_scope, artifact_id).await?;
        Ok(Response::new(GetArtifactMetadataResponse {
            artifact: Some(proto_descriptor(&stored.record.descriptor)),
            metadata_json: stored.record.metadata_json,
        }))
    }

    async fn health(
        &self,
        _request: Request<HealthRequest>,
    ) -> Result<Response<HealthResponse>, Status> {
        let postgres_ready = !artifact_postgres_dsn().is_empty();
        let object_store_config = artifact_object_store_config();
        let object_store_ready = if let Some(config) = object_store_config.as_ref() {
            artifact_object_store_ready(config).await.is_ok()
        } else {
            false
        };
        let backend_ready = postgres_ready && object_store_ready;
        let mut details = health_details(SERVICE_NAME);
        details.insert("authoritative".to_string(), backend_ready.to_string());
        details.insert("production_ready".to_string(), backend_ready.to_string());
        details.insert(
            "maturity".to_string(),
            if backend_ready {
                "ga"
            } else {
                "config_required"
            }
            .to_string(),
        );
        details.insert(
            "storage_backing".to_string(),
            if backend_ready {
                OBJECT_STORAGE_STORAGE_BACKING.to_string()
            } else {
                "unconfigured".to_string()
            },
        );
        details.insert(
            "object_store".to_string(),
            if object_store_ready {
                "ready".to_string()
            } else if object_store_config.is_some() {
                "unreachable".to_string()
            } else {
                "required_unconfigured".to_string()
            },
        );
        details.insert(
            "metadata_mode".to_string(),
            "canonical_descriptor".to_string(),
        );
        details.insert(
            "capabilities".to_string(),
            "fingerprint,put_artifact,metadata,evidence,durable,multi_instance".to_string(),
        );
        details.insert(
            "tracked_artifacts".to_string(),
            count_indexed_artifacts()
                .await
                .unwrap_or_default()
                .to_string(),
        );
        Ok(Response::new(HealthResponse {
            service: SERVICE_NAME.to_string(),
            ready: backend_ready,
            status: if backend_ready {
                "ready"
            } else {
                "missing_config"
            }
            .to_string(),
            details,
        }))
    }
}

async fn serve_target(target: &str) -> Result<()> {
    let service = ArtifactEngineServiceServer::new(ArtifactServer);
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
        std::env::var("ARTIFACT_GRPC_TARGET").unwrap_or_else(|_| "127.0.0.1:50064".to_string());
    serve_target(&target).await
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::collections::HashMap;
    use std::net::TcpListener as StdTcpListener;
    use std::process::{Command, Stdio};
    use std::sync::{Arc, Mutex as StdMutex, OnceLock};

    use axum::body::Bytes;
    use axum::extract::{Path as AxumPath, State};
    use axum::http::{HeaderMap, StatusCode};
    use axum::response::IntoResponse;
    use axum::routing::{head, put};
    use axum::Router;
    use koda_proto::artifact::v1::artifact_engine_service_client::ArtifactEngineServiceClient;
    use tempfile::TempDir;
    use tokio::net::TcpListener;
    use tokio::sync::{oneshot, Mutex};
    use tokio_stream::wrappers::TcpListenerStream;

    type ObjectMap = Arc<StdMutex<HashMap<String, Vec<u8>>>>;

    fn env_lock() -> &'static Mutex<()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
    }

    struct EnvGuard {
        saved: Vec<(String, Option<String>)>,
    }

    impl EnvGuard {
        fn set(entries: &[(&str, String)]) -> Self {
            let mut saved = Vec::with_capacity(entries.len());
            for (key, value) in entries {
                saved.push(((*key).to_string(), std::env::var(key).ok()));
                std::env::set_var(key, value);
            }
            Self { saved }
        }
    }

    impl Drop for EnvGuard {
        fn drop(&mut self) {
            for (key, value) in self.saved.drain(..).rev() {
                if let Some(value) = value {
                    std::env::set_var(&key, value);
                } else {
                    std::env::remove_var(&key);
                }
            }
        }
    }

    #[derive(Clone)]
    struct FakeS3State {
        bucket: String,
        objects: ObjectMap,
    }

    struct FakeS3Server {
        endpoint_url: String,
        objects: ObjectMap,
        shutdown: Option<oneshot::Sender<()>>,
        task: tokio::task::JoinHandle<()>,
    }

    impl FakeS3Server {
        async fn start(bucket: &str) -> Self {
            let state = FakeS3State {
                bucket: bucket.to_string(),
                objects: Arc::new(StdMutex::new(HashMap::new())),
            };
            // axum 0.8 switched route capture syntax from `:param` / `*splat`
            // to `{param}` / `{*splat}`. Mixed-mode routers raise at startup.
            let app = Router::new()
                .route("/{bucket}", head(head_bucket))
                .route("/{bucket}/", head(head_bucket))
                .route(
                    "/{bucket}/{*key}",
                    put(put_object).get(get_object).delete(delete_object),
                )
                .with_state(state.clone());
            let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
            let addr = listener.local_addr().unwrap();
            let (shutdown_tx, shutdown_rx) = oneshot::channel();
            let task = tokio::spawn(async move {
                axum::serve(listener, app)
                    .with_graceful_shutdown(async {
                        let _ = shutdown_rx.await;
                    })
                    .await
                    .unwrap();
            });
            Self {
                endpoint_url: format!("http://{addr}"),
                objects: state.objects,
                shutdown: Some(shutdown_tx),
                task,
            }
        }

        fn payload(&self, object_store_key: &str) -> Option<Vec<u8>> {
            self.objects.lock().unwrap().get(object_store_key).cloned()
        }

        async fn shutdown(mut self) {
            if let Some(shutdown) = self.shutdown.take() {
                let _ = shutdown.send(());
            }
            let _ = self.task.await;
        }
    }

    async fn head_bucket(
        AxumPath(bucket): AxumPath<String>,
        State(state): State<FakeS3State>,
    ) -> StatusCode {
        if bucket == state.bucket {
            StatusCode::OK
        } else {
            StatusCode::NOT_FOUND
        }
    }

    async fn put_object(
        AxumPath((bucket, key)): AxumPath<(String, String)>,
        State(state): State<FakeS3State>,
        headers: HeaderMap,
        body: Bytes,
    ) -> StatusCode {
        if bucket != state.bucket {
            return StatusCode::NOT_FOUND;
        }
        let payload = if headers
            .get("content-encoding")
            .and_then(|value| value.to_str().ok())
            .is_some_and(|value| value.eq_ignore_ascii_case("aws-chunked"))
        {
            decode_aws_chunked_body(body.as_ref()).unwrap_or_else(|| body.to_vec())
        } else {
            body.to_vec()
        };
        state.objects.lock().unwrap().insert(key, payload);
        StatusCode::OK
    }

    async fn get_object(
        AxumPath((bucket, key)): AxumPath<(String, String)>,
        State(state): State<FakeS3State>,
    ) -> impl IntoResponse {
        if bucket != state.bucket {
            return StatusCode::NOT_FOUND.into_response();
        }
        let Some(payload) = state.objects.lock().unwrap().get(&key).cloned() else {
            return StatusCode::NOT_FOUND.into_response();
        };
        (StatusCode::OK, payload).into_response()
    }

    async fn delete_object(
        AxumPath((bucket, key)): AxumPath<(String, String)>,
        State(state): State<FakeS3State>,
    ) -> StatusCode {
        if bucket != state.bucket {
            return StatusCode::NOT_FOUND;
        }
        state.objects.lock().unwrap().remove(&key);
        StatusCode::NO_CONTENT
    }

    fn decode_aws_chunked_body(payload: &[u8]) -> Option<Vec<u8>> {
        let mut cursor = 0usize;
        let mut decoded = Vec::new();
        while cursor < payload.len() {
            let line_end = payload[cursor..]
                .windows(2)
                .position(|window| window == b"\r\n")?
                + cursor;
            let line = std::str::from_utf8(&payload[cursor..line_end]).ok()?;
            let size_hex = line.split(';').next()?.trim();
            let size = usize::from_str_radix(size_hex, 16).ok()?;
            cursor = line_end + 2;
            if size == 0 {
                return Some(decoded);
            }
            let chunk_end = cursor.checked_add(size)?;
            decoded.extend_from_slice(payload.get(cursor..chunk_end)?);
            cursor = chunk_end.checked_add(2)?;
        }
        None
    }

    fn run_command(command: &mut Command, label: &str) {
        let output = command.output().unwrap_or_else(|error| {
            panic!("failed to spawn {label}: {error}");
        });
        assert!(
            output.status.success(),
            "{label} failed with status {:?}\nstdout:\n{}\nstderr:\n{}",
            output.status.code(),
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
    }

    fn pick_unused_port() -> u16 {
        let listener = StdTcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener);
        port
    }

    struct PostgresHarness {
        _tempdir: TempDir,
        data_dir: PathBuf,
        dsn: String,
    }

    impl PostgresHarness {
        fn start() -> Self {
            let tempdir = TempDir::new().unwrap();
            let data_dir = tempdir.path().join("data");
            let socket_dir = tempdir.path().join("socket");
            let log_path = tempdir.path().join("postgres.log");
            std::fs::create_dir_all(&socket_dir).unwrap();
            run_command(
                Command::new("initdb")
                    .arg("-D")
                    .arg(&data_dir)
                    .arg("-A")
                    .arg("trust")
                    .arg("-U")
                    .arg("postgres")
                    .arg("--no-locale")
                    .arg("--encoding=UTF8")
                    .stdout(Stdio::null()),
                "initdb",
            );
            let port = pick_unused_port();
            run_command(
                Command::new("pg_ctl")
                    .arg("-D")
                    .arg(&data_dir)
                    .arg("-l")
                    .arg(&log_path)
                    .arg("-w")
                    .arg("start")
                    .arg("-o")
                    .arg(format!("-F -k {} -p {port}", socket_dir.display())),
                "pg_ctl start",
            );
            Self {
                _tempdir: tempdir,
                data_dir,
                dsn: format!(
                    "host={} port={} user=postgres dbname=postgres",
                    socket_dir.display(),
                    port
                ),
            }
        }

        fn dsn(&self) -> &str {
            &self.dsn
        }
    }

    impl Drop for PostgresHarness {
        fn drop(&mut self) {
            let _ = Command::new("pg_ctl")
                .arg("-D")
                .arg(&self.data_dir)
                .arg("-m")
                .arg("immediate")
                .arg("-w")
                .arg("stop")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }
    }

    struct GrpcHarness {
        target: String,
        shutdown: Option<oneshot::Sender<()>>,
        task: tokio::task::JoinHandle<()>,
    }

    impl GrpcHarness {
        async fn start() -> Self {
            let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
            let addr = listener.local_addr().unwrap();
            let incoming = TcpListenerStream::new(listener);
            let (shutdown_tx, shutdown_rx) = oneshot::channel();
            let task = tokio::spawn(async move {
                Server::builder()
                    .add_service(ArtifactEngineServiceServer::new(ArtifactServer))
                    .serve_with_incoming_shutdown(incoming, async {
                        let _ = shutdown_rx.await;
                    })
                    .await
                    .unwrap();
            });
            Self {
                target: format!("http://{addr}"),
                shutdown: Some(shutdown_tx),
                task,
            }
        }

        async fn client(&self) -> ArtifactEngineServiceClient<tonic::transport::Channel> {
            ArtifactEngineServiceClient::connect(self.target.clone())
                .await
                .unwrap()
        }

        async fn shutdown(mut self) {
            if let Some(shutdown) = self.shutdown.take() {
                let _ = shutdown.send(());
            }
            let _ = self.task.await;
        }
    }

    async fn connect_postgres(dsn: &str) -> tokio_postgres::Client {
        let (client, connection) = tokio_postgres::connect(dsn, NoTls).await.unwrap();
        tokio::spawn(async move {
            let _ = connection.await;
        });
        client
    }

    // Requires PostgreSQL's `initdb` / `pg_ctl` binaries on PATH (the
    // harness spins up an ephemeral cluster per run). CI runners don't
    // install postgres client tooling, so the test is opt-in via the
    // KODA_INTEGRATION_TESTS env flag — set it locally with postgres
    // installed to exercise the roundtrip.
    #[tokio::test(flavor = "current_thread")]
    #[ignore = "requires local PostgreSQL; run with KODA_INTEGRATION_TESTS=1 cargo test -- --ignored"]
    async fn object_storage_roundtrip_is_durable_across_instances() {
        let _env_lock = env_lock().lock().await;
        let postgres = PostgresHarness::start();
        let fake_s3 = FakeS3Server::start("artifact-proof-bucket").await;
        let artifact_root = TempDir::new().unwrap();
        let schema = format!("artifact_e2e_{}_{}", std::process::id(), now_ms());
        let _env = EnvGuard::set(&[
            ("KNOWLEDGE_V2_POSTGRES_DSN", postgres.dsn().to_string()),
            ("KNOWLEDGE_V2_POSTGRES_SCHEMA", schema.clone()),
            (
                "KNOWLEDGE_V2_S3_BUCKET",
                "artifact-proof-bucket".to_string(),
            ),
            ("KNOWLEDGE_V2_S3_PREFIX", "artifact-proof".to_string()),
            ("KNOWLEDGE_V2_S3_ENDPOINT_URL", fake_s3.endpoint_url.clone()),
            ("KNOWLEDGE_V2_S3_REGION", "us-east-1".to_string()),
            (
                "KNOWLEDGE_V2_S3_ACCESS_KEY_ID",
                "artifact-test-key".to_string(),
            ),
            (
                "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY",
                "artifact-test-secret".to_string(),
            ),
            (
                "ARTIFACT_STORE_DIR",
                artifact_root.path().display().to_string(),
            ),
            ("AWS_EC2_METADATA_DISABLED", "true".to_string()),
        ]);

        let first_server = GrpcHarness::start().await;
        let mut first_client = first_server.client().await;
        let put_response = first_client
            .put_artifact(tokio_stream::iter(vec![
                PutArtifactRequest {
                    agent_id: "AGENT_A".to_string(),
                    logical_filename: "proof.txt".to_string(),
                    mime_type: "text/plain".to_string(),
                    source_metadata_json: r#"{"source":"e2e"}"#.to_string(),
                    purpose: "artifact_object_storage_proof".to_string(),
                    data: b"hello ".to_vec(),
                    ..Default::default()
                },
                PutArtifactRequest {
                    data: b"world".to_vec(),
                    ..Default::default()
                },
            ]))
            .await
            .unwrap()
            .into_inner();
        let descriptor = put_response.artifact.unwrap();
        assert_eq!(put_response.upload_outcome, OBJECT_STORAGE_UPLOAD_OUTCOME);
        assert!(put_response
            .metadata_json
            .contains(OBJECT_STORAGE_STORAGE_BACKING));
        first_server.shutdown().await;

        let _ = fs::remove_dir_all(artifact_root.path()).await;

        let second_server = GrpcHarness::start().await;
        let mut second_client = second_server.client().await;
        let health = second_client
            .health(HealthRequest::default())
            .await
            .unwrap()
            .into_inner();
        assert!(health.ready, "artifact health was not ready: {:?}", health);
        assert_eq!(
            health.details.get("storage_backing"),
            Some(&OBJECT_STORAGE_STORAGE_BACKING.to_string())
        );
        assert_eq!(
            health.details.get("object_store"),
            Some(&"ready".to_string())
        );

        let metadata = second_client
            .get_artifact_metadata_by_artifact_id(GetArtifactMetadataByArtifactIdRequest {
                agent_id: "AGENT_A".to_string(),
                artifact_id: descriptor.artifact_id.clone(),
                ..Default::default()
            })
            .await
            .unwrap()
            .into_inner();
        let evidence = second_client
            .generate_evidence_by_artifact_id(GenerateEvidenceByArtifactIdRequest {
                agent_id: "AGENT_A".to_string(),
                artifact_id: descriptor.artifact_id.clone(),
                ..Default::default()
            })
            .await
            .unwrap()
            .into_inner();

        let returned_descriptor = metadata.artifact.unwrap();
        let metadata_json: serde_json::Value =
            serde_json::from_str(&metadata.metadata_json).unwrap();
        let evidence_json: serde_json::Value =
            serde_json::from_str(&evidence.evidence_json).unwrap();
        assert_eq!(returned_descriptor.artifact_id, descriptor.artifact_id);
        assert_eq!(returned_descriptor.object_key, descriptor.object_key);
        assert_eq!(
            metadata_json
                .get("storage_backing")
                .and_then(serde_json::Value::as_str),
            Some(OBJECT_STORAGE_STORAGE_BACKING)
        );
        assert_eq!(
            evidence_json
                .get("excerpt")
                .and_then(serde_json::Value::as_str),
            Some("hello world")
        );

        let postgres_client = connect_postgres(postgres.dsn()).await;
        let row = postgres_client
            .query_one(
                &format!(
                    r#"
                    SELECT storage_backing,
                           object_store_bucket,
                           object_store_key,
                           upload_outcome,
                           evidence_json,
                           payload IS NULL AS payload_is_null
                      FROM "{schema}"."artifact_objects"
                     WHERE agent_id = $1
                       AND artifact_id = $2
                    "#
                ),
                &[&"agent_a", &descriptor.artifact_id],
            )
            .await
            .unwrap();
        let object_store_key = row.get::<_, String>("object_store_key");
        assert_eq!(
            row.get::<_, String>("storage_backing"),
            OBJECT_STORAGE_STORAGE_BACKING
        );
        assert_eq!(
            row.get::<_, String>("object_store_bucket"),
            "artifact-proof-bucket"
        );
        assert_eq!(
            row.get::<_, String>("upload_outcome"),
            OBJECT_STORAGE_UPLOAD_OUTCOME
        );
        assert!(row.get::<_, bool>("payload_is_null"));
        assert!(row
            .get::<_, String>("evidence_json")
            .contains("\"excerpt\":\"hello world\""));
        assert_eq!(
            fake_s3.payload(&object_store_key),
            Some(b"hello world".to_vec())
        );

        second_server.shutdown().await;
        fake_s3.shutdown().await;
    }
}
