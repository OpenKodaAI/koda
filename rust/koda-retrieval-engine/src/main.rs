use std::collections::{BTreeMap, BTreeSet};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::Result;
use koda_observability::{health_details, init_tracing};
use koda_postgres::{KodaPgPool, KodaPgPoolConfig, PostgresWorkload};
use koda_proto::common::v1::{HealthRequest, HealthResponse};
use koda_proto::retrieval::v1::retrieval_engine_service_server::{
    RetrievalEngineService, RetrievalEngineServiceServer,
};
use koda_proto::retrieval::v1::{
    AnswerPlan, AuthoritativeEvidence, CanonicalEntity, CanonicalRelation, GraphEntity,
    GraphRelation, JudgeResult, ListGraphRequest, ListGraphResponse, RetrievalHit,
    RetrievalTraceHit, RetrieveEnvelope, RetrieveRequest, RetrieveResponse, SupportingEvidence,
};
use prost_types::{value::Kind, ListValue, Struct, Value as ProtoValue};
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use tokio::fs;
use tokio::net::UnixListener;
use tokio::sync::OnceCell;
use tokio_postgres::{Client, Row};
use tokio_stream::wrappers::UnixListenerStream;
use tonic::transport::Server;
use tonic::{Request, Response, Status};

const SERVICE_NAME: &str = "koda-retrieval-engine";
const REQUIRED_TABLES: [&str; 5] = [
    "knowledge_chunks",
    "knowledge_embeddings",
    "knowledge_entities",
    "knowledge_relations",
    "artifact_derivatives",
];
const REQUIRED_INDEXES: [&str; 4] = [
    "idx_knowledge_chunks_lookup",
    "idx_knowledge_chunks_search",
    "idx_artifact_derivatives_lookup",
    "idx_artifact_derivatives_search",
];
const DENSE_REQUIRED_INDEXES: [&str; 2] = [
    "idx_knowledge_embeddings_vector_hnsw",
    "idx_artifact_derivatives_vector_hnsw",
];
const DEFAULT_DENSE_WINDOW: usize = 200;
const MAX_QUERY_EMBEDDING_DIMENSION: usize = 4096;

static KNOWLEDGE_POSTGRES_POOL: OnceCell<KodaPgPool> = OnceCell::const_new();

fn knowledge_postgres_dsn() -> String {
    std::env::var("KNOWLEDGE_V2_POSTGRES_DSN")
        .unwrap_or_default()
        .trim()
        .to_string()
}

fn knowledge_postgres_schema() -> String {
    let schema = std::env::var("KNOWLEDGE_V2_POSTGRES_SCHEMA")
        .unwrap_or_else(|_| "knowledge_v2".to_string());
    let trimmed = schema.trim();
    if trimmed.is_empty() {
        "knowledge_v2".to_string()
    } else {
        trimmed.to_string()
    }
}

fn quote_ident(identifier: &str) -> String {
    format!("\"{}\"", identifier.replace('"', "\"\""))
}

fn qualified_relation(schema: &str, relation: &str) -> String {
    format!("{}.{}", quote_ident(schema), quote_ident(relation))
}

fn regclass_name(schema: &str, relation: &str) -> String {
    qualified_relation(schema, relation)
}

fn escape_like_prefix(value: &str) -> String {
    let mut escaped = String::new();
    for ch in value.chars() {
        match ch {
            '\\' | '%' | '_' => {
                escaped.push('\\');
                escaped.push(ch);
            }
            _ => escaped.push(ch),
        }
    }
    escaped
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum QualityTier {
    Unavailable = 0,
    LexicalGraph = 1,
    HybridDense = 2,
    HybridReranked = 3,
}

impl QualityTier {
    fn from_env() -> Self {
        match std::env::var("KNOWLEDGE_RETRIEVAL_MIN_QUALITY_TIER")
            .unwrap_or_else(|_| "lexical_graph".to_string())
            .trim()
            .to_ascii_lowercase()
            .as_str()
        {
            "hybrid_reranked" => Self::HybridReranked,
            "hybrid_dense" => Self::HybridDense,
            "lexical_graph" => Self::LexicalGraph,
            _ => Self::LexicalGraph,
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Unavailable => "unavailable",
            Self::LexicalGraph => "lexical_graph",
            Self::HybridDense => "hybrid_dense",
            Self::HybridReranked => "hybrid_reranked",
        }
    }
}

fn dense_window_limit() -> usize {
    std::env::var("KNOWLEDGE_RETRIEVAL_DENSE_WINDOW")
        .ok()
        .and_then(|raw| raw.trim().parse::<usize>().ok())
        .filter(|value| *value >= 10)
        .unwrap_or(DEFAULT_DENSE_WINDOW)
        .clamp(50, 500)
}

fn min_vector_coverage() -> f64 {
    std::env::var("KNOWLEDGE_RETRIEVAL_VECTOR_COVERAGE_MIN")
        .ok()
        .and_then(|raw| raw.trim().parse::<f64>().ok())
        .filter(|value| value.is_finite())
        .unwrap_or(0.80)
        .clamp(0.0, 1.0)
}

fn candidate_window(limit: usize) -> i64 {
    i64::try_from(limit.saturating_mul(6).max(50).min(dense_window_limit())).unwrap_or(200)
}

async fn connect_knowledge_postgres_pool() -> Result<KodaPgPool, Status> {
    KodaPgPool::connect(KodaPgPoolConfig::from_env(
        SERVICE_NAME,
        "KODA_RETRIEVAL_POSTGRES_POOL_MAX_SIZE",
    ))
    .await
}

async fn knowledge_postgres_pool() -> Result<&'static KodaPgPool, Status> {
    KNOWLEDGE_POSTGRES_POOL
        .get_or_try_init(connect_knowledge_postgres_pool)
        .await
}

fn knowledge_pg_error(operation: &'static str, error: tokio_postgres::Error) -> Status {
    if let Some(pool) = KNOWLEDGE_POSTGRES_POOL.get() {
        pool.status_from_pg_error(operation, error)
    } else {
        Status::internal(format!("{operation}: postgres query failed: {error}"))
    }
}

#[derive(Debug, Default, Clone)]
struct KnowledgeSchemaHealth {
    postgres_configured: bool,
    postgres_ready: bool,
    knowledge_chunks: bool,
    knowledge_embeddings: bool,
    knowledge_entities: bool,
    knowledge_relations: bool,
    artifact_derivatives: bool,
    idx_knowledge_chunks_lookup: bool,
    idx_knowledge_chunks_search: bool,
    idx_knowledge_embeddings_lookup: bool,
    idx_knowledge_entities_lookup: bool,
    idx_knowledge_relations_lookup: bool,
    idx_artifact_derivatives_lookup: bool,
    idx_artifact_derivatives_search: bool,
    idx_knowledge_embeddings_vector_hnsw: bool,
    idx_artifact_derivatives_vector_hnsw: bool,
    pgvector_extension: bool,
    knowledge_embedding_vector_column: bool,
    artifact_embedding_vector_column: bool,
    indexed_chunks_approx: i64,
    indexed_embeddings_approx: i64,
    indexed_artifacts_approx: i64,
    chunk_vector_count: i64,
    artifact_vector_count: i64,
    pool_size: usize,
    error: String,
}

impl KnowledgeSchemaHealth {
    fn bundle_ready(&self) -> bool {
        self.postgres_ready
            && self.knowledge_chunks
            && self.knowledge_embeddings
            && self.knowledge_entities
            && self.knowledge_relations
            && self.artifact_derivatives
            && self.idx_knowledge_chunks_lookup
            && self.idx_knowledge_chunks_search
            && self.idx_knowledge_embeddings_lookup
            && self.idx_knowledge_entities_lookup
            && self.idx_knowledge_relations_lookup
            && self.idx_artifact_derivatives_lookup
            && self.idx_artifact_derivatives_search
    }

    fn vector_coverage(&self) -> f64 {
        if self.indexed_chunks_approx <= 0 {
            return 1.0;
        }
        (self.chunk_vector_count as f64 / self.indexed_chunks_approx as f64).clamp(0.0, 1.0)
    }

    fn dense_ready(&self, min_coverage: f64) -> bool {
        self.bundle_ready()
            && self.pgvector_extension
            && self.knowledge_embedding_vector_column
            && self.artifact_embedding_vector_column
            && self.idx_knowledge_embeddings_vector_hnsw
            && self.idx_artifact_derivatives_vector_hnsw
            && (self.indexed_chunks_approx == 0 || self.vector_coverage() >= min_coverage)
    }

    fn quality_tier(&self, min_coverage: f64) -> QualityTier {
        if self.dense_ready(min_coverage) {
            QualityTier::HybridDense
        } else if self.bundle_ready() {
            QualityTier::LexicalGraph
        } else {
            QualityTier::Unavailable
        }
    }
}

async fn inspect_knowledge_schema() -> KnowledgeSchemaHealth {
    let mut health = KnowledgeSchemaHealth {
        postgres_configured: !knowledge_postgres_dsn().is_empty(),
        ..KnowledgeSchemaHealth::default()
    };
    if !health.postgres_configured {
        health.error = "knowledge postgres dsn is not configured".to_string();
        return health;
    }

    let pool = match knowledge_postgres_pool().await {
        Ok(pool) => pool,
        Err(error) => {
            health.error = error.message().to_string();
            return health;
        }
    };
    let snapshot = pool.snapshot();
    health.pool_size = usize::try_from(snapshot.pool_max_size).unwrap_or(0);
    let client = match pool
        .connection(PostgresWorkload::Health, "inspect_knowledge_schema")
        .await
    {
        Ok(client) => client,
        Err(error) => {
            health.error = error.message().to_string();
            return health;
        }
    };
    if let Err(error) = client.query_one("SELECT 1", &[]).await {
        health.error = pool
            .status_from_pg_error("postgres readiness probe", error)
            .message()
            .to_string();
        return health;
    }
    health.postgres_ready = true;

    let schema = knowledge_postgres_schema();
    let required = REQUIRED_TABLES
        .iter()
        .chain(REQUIRED_INDEXES.iter())
        .chain(
            [
                "idx_knowledge_embeddings_lookup",
                "idx_knowledge_entities_lookup",
                "idx_knowledge_relations_lookup",
            ]
            .iter(),
        )
        .chain(DENSE_REQUIRED_INDEXES.iter())
        .map(|relation| regclass_name(&schema, relation))
        .collect::<Vec<String>>();
    match client
        .query_one(
            "SELECT to_regclass($1) IS NOT NULL AS knowledge_chunks,
                    to_regclass($2) IS NOT NULL AS knowledge_embeddings,
                    to_regclass($3) IS NOT NULL AS knowledge_entities,
                    to_regclass($4) IS NOT NULL AS knowledge_relations,
                    to_regclass($5) IS NOT NULL AS artifact_derivatives,
                    to_regclass($6) IS NOT NULL AS idx_knowledge_chunks_lookup,
                    to_regclass($7) IS NOT NULL AS idx_knowledge_chunks_search,
                    to_regclass($8) IS NOT NULL AS idx_artifact_derivatives_lookup,
                    to_regclass($9) IS NOT NULL AS idx_artifact_derivatives_search,
                    to_regclass($10) IS NOT NULL AS idx_knowledge_embeddings_lookup,
                    to_regclass($11) IS NOT NULL AS idx_knowledge_entities_lookup,
                    to_regclass($12) IS NOT NULL AS idx_knowledge_relations_lookup,
                    to_regclass($13) IS NOT NULL AS idx_knowledge_embeddings_vector_hnsw,
                    to_regclass($14) IS NOT NULL AS idx_artifact_derivatives_vector_hnsw,
                    EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS pgvector_extension,
                    EXISTS (
                        SELECT 1
                          FROM information_schema.columns
                         WHERE table_schema = $15
                           AND table_name = 'knowledge_embeddings'
                           AND column_name = 'embedding_vector'
                    ) AS knowledge_embedding_vector_column,
                    EXISTS (
                        SELECT 1
                          FROM information_schema.columns
                         WHERE table_schema = $15
                           AND table_name = 'artifact_derivatives'
                           AND column_name = 'embedding_vector'
                    ) AS artifact_embedding_vector_column",
            &[
                &required[0],
                &required[1],
                &required[2],
                &required[3],
                &required[4],
                &required[5],
                &required[6],
                &required[7],
                &required[8],
                &required[9],
                &required[10],
                &required[11],
                &required[12],
                &required[13],
                &schema,
            ],
        )
        .await
    {
        Ok(row) => {
            health.knowledge_chunks = row.get("knowledge_chunks");
            health.knowledge_embeddings = row.get("knowledge_embeddings");
            health.knowledge_entities = row.get("knowledge_entities");
            health.knowledge_relations = row.get("knowledge_relations");
            health.artifact_derivatives = row.get("artifact_derivatives");
            health.idx_knowledge_chunks_lookup = row.get("idx_knowledge_chunks_lookup");
            health.idx_knowledge_chunks_search = row.get("idx_knowledge_chunks_search");
            health.idx_artifact_derivatives_lookup = row.get("idx_artifact_derivatives_lookup");
            health.idx_artifact_derivatives_search = row.get("idx_artifact_derivatives_search");
            health.idx_knowledge_embeddings_lookup = row.get("idx_knowledge_embeddings_lookup");
            health.idx_knowledge_entities_lookup = row.get("idx_knowledge_entities_lookup");
            health.idx_knowledge_relations_lookup = row.get("idx_knowledge_relations_lookup");
            health.idx_knowledge_embeddings_vector_hnsw =
                row.get("idx_knowledge_embeddings_vector_hnsw");
            health.idx_artifact_derivatives_vector_hnsw =
                row.get("idx_artifact_derivatives_vector_hnsw");
            health.pgvector_extension = row.get("pgvector_extension");
            health.knowledge_embedding_vector_column =
                row.get("knowledge_embedding_vector_column");
            health.artifact_embedding_vector_column = row.get("artifact_embedding_vector_column");
        }
        Err(error) => {
            health.error = format!("schema registry probe failed: {error}");
            return health;
        }
    }

    if health.knowledge_chunks {
        match client
            .query(
                "SELECT c.relname,
                        GREATEST(COALESCE(c.reltuples, 0), 0)::BIGINT AS approx_rows
                   FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = $1
                    AND c.relname = ANY($2::TEXT[])",
                &[
                    &schema,
                    &vec![
                        "knowledge_chunks".to_string(),
                        "knowledge_embeddings".to_string(),
                        "artifact_derivatives".to_string(),
                    ],
                ],
            )
            .await
        {
            Ok(rows) => {
                for row in rows {
                    let relname: String = row.get("relname");
                    let approx_rows: i64 = row.get("approx_rows");
                    match relname.as_str() {
                        "knowledge_chunks" => health.indexed_chunks_approx = approx_rows,
                        "knowledge_embeddings" => health.indexed_embeddings_approx = approx_rows,
                        "artifact_derivatives" => health.indexed_artifacts_approx = approx_rows,
                        _ => {}
                    }
                }
            }
            Err(error) => {
                health.error = format!("chunk statistics probe failed: {error}");
            }
        }
    }

    if health.knowledge_embedding_vector_column {
        let embeddings_table = qualified_relation(&schema, "knowledge_embeddings");
        match client
            .query_one(
                &format!(
                    "SELECT COUNT(*)::BIGINT AS chunk_vector_count
                       FROM {embeddings_table}
                      WHERE embedding_vector IS NOT NULL",
                    embeddings_table = embeddings_table
                ),
                &[],
            )
            .await
        {
            Ok(row) => health.chunk_vector_count = row.get("chunk_vector_count"),
            Err(error) => health.error = format!("embedding vector coverage probe failed: {error}"),
        }
    }

    if health.artifact_embedding_vector_column {
        let artifacts_table = qualified_relation(&schema, "artifact_derivatives");
        match client
            .query_one(
                &format!(
                    "SELECT COUNT(*)::BIGINT AS artifact_vector_count
                       FROM {artifacts_table}
                      WHERE embedding_vector IS NOT NULL",
                    artifacts_table = artifacts_table
                ),
                &[],
            )
            .await
        {
            Ok(row) => health.artifact_vector_count = row.get("artifact_vector_count"),
            Err(error) => health.error = format!("artifact vector coverage probe failed: {error}"),
        }
    }

    health
}

#[derive(Debug, Default, Clone)]
struct QueryEnvelopePayload {
    normalized_query: String,
    task_kind: String,
    project_key: String,
    environment: String,
    team: String,
    workspace_dir: String,
    workspace_fingerprint: String,
    requires_write: bool,
    strategy: String,
    allowed_source_labels: Vec<String>,
    allowed_workspace_roots: Vec<String>,
    query_embedding: Vec<f64>,
    query_embedding_model: String,
    query_embedding_dimension: i32,
}

#[derive(Debug, Default, Serialize, Deserialize, Clone)]
struct CandidatePayload {
    #[serde(default)]
    id: String,
    #[serde(default)]
    title: String,
    #[serde(default)]
    content: String,
    #[serde(default)]
    layer: String,
    #[serde(default)]
    scope: String,
    #[serde(default)]
    source_label: String,
    #[serde(default)]
    source_path: String,
    #[serde(default)]
    workspace_root: String,
    #[serde(default)]
    updated_at: String,
    #[serde(default)]
    owner: String,
    #[serde(default)]
    criticality: String,
    #[serde(default)]
    freshness: String,
    #[serde(default)]
    similarity: f64,
    #[serde(default = "default_rank")]
    lexical_rank: i64,
    #[serde(default = "default_rank")]
    dense_rank: i64,
    #[serde(default = "default_rank")]
    graph_rank: i64,
    #[serde(default)]
    lexical_score: f64,
    #[serde(default)]
    dense_score: f64,
    #[serde(default)]
    rerank_score: f64,
    #[serde(default = "default_rank")]
    rerank_rank: i64,
    #[serde(default)]
    tags: Vec<String>,
    #[serde(default)]
    project_key: String,
    #[serde(default)]
    environment: String,
    #[serde(default)]
    team: String,
    #[serde(default)]
    source_type: String,
    #[serde(default = "default_true")]
    operable: bool,
    #[serde(default)]
    graph_hops: i64,
    #[serde(default)]
    graph_score: f64,
    #[serde(default)]
    graph_relation_types: Vec<String>,
    #[serde(default)]
    evidence_modalities: Vec<String>,
    #[serde(default)]
    reasons: Vec<String>,
}

#[derive(Debug, Default, Clone)]
struct SupportingEvidencePayload {
    evidence_key: String,
    modality: String,
    label: String,
    similarity: f64,
    confidence: f64,
    trust_level: String,
    excerpt: String,
    source_path: String,
    source_url: String,
    project_key: String,
    workspace_fingerprint: String,
    provenance_json: String,
}

#[derive(Debug, Clone)]
struct RankedCandidate {
    candidate: CandidatePayload,
    supporting_evidence: Vec<SupportingEvidencePayload>,
    base_rank: usize,
    score: f64,
}

fn default_true() -> bool {
    true
}

fn default_rank() -> i64 {
    -1
}

fn round4(value: f64) -> f64 {
    (value * 10_000.0).round() / 10_000.0
}

fn tokenize(text: &str) -> BTreeSet<String> {
    let mut tokens = BTreeSet::new();
    let mut current = String::new();
    for ch in text.chars() {
        if ch.is_ascii_alphanumeric() || ch == '_' || ch == '-' || ch == '/' || ch == '.' {
            current.push(ch.to_ascii_lowercase());
        } else if !current.is_empty() {
            tokens.insert(current.clone());
            current.clear();
        }
    }
    if !current.is_empty() {
        tokens.insert(current);
    }
    tokens
}

fn query_terms(text: &str) -> Vec<String> {
    tokenize(text)
        .into_iter()
        .filter(|token| token.len() >= 2)
        .take(24)
        .collect()
}

fn parse_json_string_array(raw: &str) -> Vec<String> {
    serde_json::from_str::<JsonValue>(raw)
        .ok()
        .and_then(|value| match value {
            JsonValue::Array(items) => Some(
                items
                    .into_iter()
                    .filter_map(|item| item.as_str().map(str::to_string))
                    .filter(|item| !item.trim().is_empty())
                    .collect(),
            ),
            _ => None,
        })
        .unwrap_or_default()
}

fn source_label_patterns(patterns: &[String]) -> (Vec<String>, Vec<String>) {
    let mut exact = Vec::new();
    let mut prefixes = Vec::new();
    for pattern in patterns {
        let trimmed = pattern.trim();
        if trimmed.is_empty() {
            continue;
        }
        if let Some(prefix) = trimmed.strip_suffix('*') {
            if !prefix.is_empty() {
                prefixes.push(escape_like_prefix(prefix));
            }
        } else {
            exact.push(trimmed.to_string());
        }
    }
    (exact, prefixes)
}

fn workspace_root_patterns(roots: &[String]) -> Vec<String> {
    roots
        .iter()
        .map(|root| root.trim().trim_end_matches('/'))
        .filter(|root| !root.is_empty())
        .map(escape_like_prefix)
        .collect()
}

fn path_matches_root(path: &str, root: &str) -> bool {
    if path.is_empty() || root.is_empty() {
        return false;
    }
    path == root
        || path
            .strip_prefix(root)
            .is_some_and(|suffix| suffix.starts_with('/'))
}

fn layer_score(layer: &str) -> f64 {
    match layer {
        "canonical_policy" => 1.0,
        "approved_runbook" => 0.9,
        "workspace_doc" => 0.58,
        "observed_pattern" => 0.42,
        _ => 0.3,
    }
}

fn freshness_from_age(age_days: f64, freshness_days: i64) -> String {
    if freshness_days <= 0 || age_days <= freshness_days as f64 {
        "fresh".to_string()
    } else if age_days <= (freshness_days.saturating_mul(2)) as f64 {
        "stale".to_string()
    } else {
        "expired".to_string()
    }
}

fn freshness_score(freshness: &str) -> f64 {
    match freshness {
        "fresh" => 1.0,
        "stale" => 0.48,
        "expired" => 0.12,
        _ => 0.35,
    }
}

fn scope_score(candidate: &CandidatePayload, envelope: &QueryEnvelopePayload) -> f64 {
    let mut total: f64 = 0.55;
    let mut filters: f64 = 0.0;
    let mut matched: f64 = 0.0;
    for (value, filter) in [
        (&candidate.project_key, &envelope.project_key),
        (&candidate.environment, &envelope.environment),
        (&candidate.team, &envelope.team),
    ] {
        if filter.is_empty() {
            continue;
        }
        filters += 1.0;
        if value == filter {
            matched += 1.0;
        } else if value.is_empty() {
            matched += 0.55;
        }
    }
    if !envelope.allowed_workspace_roots.is_empty() {
        filters += 1.0;
        if envelope.allowed_workspace_roots.iter().any(|root| {
            let root = root.trim().trim_end_matches('/');
            path_matches_root(&candidate.workspace_root, root)
                || path_matches_root(&candidate.source_path, root)
        }) {
            matched += 1.0;
        } else if candidate.workspace_root.is_empty() {
            matched += 0.45;
        }
    }
    if filters > 0.0 {
        total = matched / filters;
    }
    total.clamp(0.0, 1.0)
}

fn criticality_for_layer(layer: &str) -> String {
    match layer {
        "canonical_policy" | "approved_runbook" => "high".to_string(),
        "workspace_doc" => "medium".to_string(),
        _ => "low".to_string(),
    }
}

fn envelope_from_request(request: &RetrieveRequest) -> QueryEnvelopePayload {
    let envelope = request
        .envelope
        .as_ref()
        .cloned()
        .unwrap_or_else(RetrieveEnvelope::default);
    QueryEnvelopePayload {
        normalized_query: envelope.normalized_query,
        task_kind: envelope.task_kind,
        project_key: envelope.project_key,
        environment: envelope.environment,
        team: envelope.team,
        workspace_dir: envelope.workspace_dir,
        workspace_fingerprint: envelope.workspace_fingerprint,
        requires_write: envelope.requires_write,
        strategy: envelope.strategy,
        allowed_source_labels: envelope.allowed_source_labels,
        allowed_workspace_roots: envelope.allowed_workspace_roots,
        query_embedding: envelope.query_embedding,
        query_embedding_model: envelope.query_embedding_model,
        query_embedding_dimension: envelope.query_embedding_dimension,
    }
}

fn classify_intent(envelope: &QueryEnvelopePayload, candidates: &[RankedCandidate]) -> String {
    let query = envelope.normalized_query.to_lowercase();
    if candidates
        .iter()
        .any(|item| !item.supporting_evidence.is_empty())
        || query.contains('-')
    {
        return "multimodal_investigation".to_string();
    }
    if envelope.requires_write
        || matches!(
            envelope.task_kind.as_str(),
            "deploy" | "rollback" | "jira_update"
        )
    {
        return "operational_execution".to_string();
    }
    if ["conflict", "compare", "difference", "drift", "stale"]
        .iter()
        .any(|term| query.contains(term))
    {
        return "drift_investigation".to_string();
    }
    if matches!(envelope.task_kind.as_str(), "bugfix" | "code_change") {
        return "workspace_investigation".to_string();
    }
    "global_summary".to_string()
}

fn route_for_intent(intent: &str) -> String {
    match intent {
        "multimodal_investigation" => "multimodal".to_string(),
        "operational_execution" => "operational".to_string(),
        "drift_investigation" => "drift".to_string(),
        "workspace_investigation" => "workspace".to_string(),
        _ => "global".to_string(),
    }
}

fn recommended_action_mode(
    intent: &str,
    has_authoritative: bool,
    has_conflict: bool,
) -> &'static str {
    if intent == "operational_execution" && has_authoritative && !has_conflict {
        "execute"
    } else if intent == "operational_execution" {
        "needs_review"
    } else {
        "read_only"
    }
}

fn uncertainty_level(has_authoritative: bool, has_conflict: bool) -> &'static str {
    if !has_authoritative {
        "high"
    } else if has_conflict {
        "medium"
    } else {
        "low"
    }
}

fn candidate_to_proto_hit(candidate: &CandidatePayload, score: f64) -> RetrievalHit {
    RetrievalHit {
        id: candidate.id.clone(),
        title: candidate.title.clone(),
        content: candidate.content.clone(),
        layer: candidate.layer.clone(),
        scope: candidate.scope.clone(),
        source_label: candidate.source_label.clone(),
        source_path: candidate.source_path.clone(),
        updated_at: candidate.updated_at.clone(),
        owner: candidate.owner.clone(),
        tags: candidate.tags.clone(),
        criticality: candidate.criticality.clone(),
        freshness: candidate.freshness.clone(),
        similarity: round4(if score <= 0.0 {
            candidate.similarity
        } else {
            score
        }),
        lexical_rank: i32::try_from(candidate.lexical_rank).unwrap_or_default(),
        dense_rank: i32::try_from(candidate.dense_rank).unwrap_or_default(),
        graph_rank: i32::try_from(candidate.graph_rank).unwrap_or_default(),
        lexical_score: round4(candidate.lexical_score),
        dense_score: round4(candidate.dense_score),
        project_key: candidate.project_key.clone(),
        environment: candidate.environment.clone(),
        team: candidate.team.clone(),
        source_type: candidate.source_type.clone(),
        operable: candidate.operable,
        graph_hops: i32::try_from(candidate.graph_hops).unwrap_or_default(),
        graph_score: round4(candidate.graph_score),
        graph_relation_types: candidate.graph_relation_types.clone(),
        evidence_modalities: candidate.evidence_modalities.clone(),
        reasons: candidate.reasons.clone(),
        rerank_score: round4(candidate.rerank_score),
        rerank_rank: i32::try_from(candidate.rerank_rank).unwrap_or_default(),
    }
}

fn build_authoritative(
    selected: &[RankedCandidate],
    requires_write: bool,
) -> Vec<AuthoritativeEvidence> {
    selected
        .iter()
        .filter(|item| {
            matches!(
                item.candidate.layer.as_str(),
                "canonical_policy" | "approved_runbook"
            ) && (!requires_write || item.candidate.operable)
        })
        .map(|item| AuthoritativeEvidence {
            source_label: item.candidate.source_label.clone(),
            layer: item.candidate.layer.clone(),
            title: item.candidate.title.clone(),
            excerpt: item.candidate.content.chars().take(240).collect::<String>(),
            updated_at: item.candidate.updated_at.clone(),
            freshness: item.candidate.freshness.clone(),
            score: round4(item.score),
            operable: item.candidate.operable,
            rationale: item.candidate.reasons.join("; "),
            evidence_modalities: item.candidate.evidence_modalities.clone(),
        })
        .collect()
}

fn merged_provenance_struct(source_label: &str, evidence: &SupportingEvidencePayload) -> Struct {
    let mut provenance = struct_from_json_str(&evidence.provenance_json);
    provenance.fields.insert(
        "source_label".to_string(),
        ProtoValue {
            kind: Some(Kind::StringValue(source_label.to_string())),
        },
    );
    if !evidence.source_path.is_empty() {
        provenance.fields.insert(
            "source_path".to_string(),
            ProtoValue {
                kind: Some(Kind::StringValue(evidence.source_path.clone())),
            },
        );
    }
    if !evidence.source_url.is_empty() {
        provenance.fields.insert(
            "source_url".to_string(),
            ProtoValue {
                kind: Some(Kind::StringValue(evidence.source_url.clone())),
            },
        );
    }
    provenance
}

fn build_supporting(selected: &[RankedCandidate]) -> Vec<SupportingEvidence> {
    let mut seen = BTreeSet::new();
    let mut items = Vec::new();
    for candidate in selected {
        for evidence in &candidate.supporting_evidence {
            if !seen.insert(evidence.evidence_key.clone()) {
                continue;
            }
            items.push(SupportingEvidence {
                ref_key: evidence.evidence_key.clone(),
                label: evidence.label.clone(),
                modality: if evidence.modality.is_empty() {
                    "text".to_string()
                } else {
                    evidence.modality.clone()
                },
                excerpt: evidence.excerpt.clone(),
                score: round4(evidence.similarity),
                confidence: round4(evidence.confidence),
                trust_level: if evidence.trust_level.is_empty() {
                    "untrusted".to_string()
                } else {
                    evidence.trust_level.clone()
                },
                source_kind: "artifact".to_string(),
                provenance: Some(merged_provenance_struct(
                    &candidate.candidate.source_label,
                    evidence,
                )),
            });
        }
    }
    items
}

fn build_trace_hits(
    candidates: &[RankedCandidate],
    selected_ids: &BTreeSet<String>,
) -> Vec<RetrievalTraceHit> {
    candidates
        .iter()
        .enumerate()
        .map(|(index, item)| RetrievalTraceHit {
            hit_id: item.candidate.id.clone(),
            title: item.candidate.title.clone(),
            layer: item.candidate.layer.clone(),
            source_label: item.candidate.source_label.clone(),
            similarity: round4(item.candidate.similarity),
            freshness: if item.candidate.freshness.is_empty() {
                "fresh".to_string()
            } else {
                item.candidate.freshness.clone()
            },
            selected: selected_ids.contains(&item.candidate.id),
            rank_before: i32::try_from(item.base_rank).unwrap_or_default(),
            rank_after: i32::try_from(index + 1).unwrap_or_default(),
            lexical_rank: i32::try_from(item.candidate.lexical_rank).unwrap_or_default(),
            dense_rank: i32::try_from(item.candidate.dense_rank).unwrap_or_default(),
            graph_rank: i32::try_from(item.candidate.graph_rank).unwrap_or_default(),
            lexical_score: round4(item.candidate.lexical_score),
            dense_score: round4(item.candidate.dense_score),
            graph_hops: i32::try_from(item.candidate.graph_hops).unwrap_or_default(),
            graph_score: round4(item.candidate.graph_score),
            graph_relation_types: item.candidate.graph_relation_types.clone(),
            reasons: item.candidate.reasons.clone(),
            exclusion_reason: if selected_ids.contains(&item.candidate.id) {
                String::new()
            } else {
                "ranked_out".to_string()
            },
            evidence_modalities: item.candidate.evidence_modalities.clone(),
            supporting_evidence_keys: item
                .supporting_evidence
                .iter()
                .map(|evidence| evidence.evidence_key.clone())
                .collect(),
            rerank_score: round4(item.candidate.rerank_score),
            rerank_rank: i32::try_from(item.candidate.rerank_rank).unwrap_or_default(),
        })
        .collect()
}

fn answer_plan(
    intent: &str,
    selected: &[RankedCandidate],
    authoritative: &[AuthoritativeEvidence],
    supporting: &[SupportingEvidence],
) -> AnswerPlan {
    AnswerPlan {
        user_intent: intent.to_string(),
        recommended_action_mode: recommended_action_mode(intent, !authoritative.is_empty(), false)
            .to_string(),
        authoritative_sources: authoritative
            .iter()
            .map(|item| item.source_label.clone())
            .collect(),
        supporting_sources: supporting.iter().map(|item| item.ref_key.clone()).collect(),
        required_verifications: selected
            .iter()
            .take(3)
            .map(|item| item.candidate.source_label.clone())
            .collect(),
        open_conflicts: Vec::new(),
        uncertainty_level: uncertainty_level(!authoritative.is_empty(), false).to_string(),
    }
}

fn judge_result(authoritative_count: usize, support_count: usize) -> JudgeResult {
    JudgeResult {
        status: if authoritative_count > 0 {
            "passed".to_string()
        } else {
            "needs_review".to_string()
        },
        reasons: if authoritative_count > 0 {
            Vec::new()
        } else {
            vec!["missing authoritative evidence".to_string()]
        },
        warnings: if support_count > 0 {
            Vec::new()
        } else {
            vec!["no supporting multimodal evidence".to_string()]
        },
        citation_coverage: if authoritative_count > 0 { 1.0 } else { 0.0 },
        citation_span_precision: if authoritative_count > 0 { 0.9 } else { 0.0 },
        contradiction_escape_rate: 0.0,
        policy_compliance: if authoritative_count > 0 { 1.0 } else { 0.75 },
        uncertainty_marked: authoritative_count == 0,
        requires_review: authoritative_count == 0,
        safe_response: String::new(),
        metrics: Default::default(),
    }
}

fn proto_value_from_json(value: &JsonValue) -> ProtoValue {
    let kind = match value {
        JsonValue::Null => Kind::NullValue(0),
        JsonValue::Bool(raw) => Kind::BoolValue(*raw),
        JsonValue::Number(raw) => Kind::NumberValue(raw.as_f64().unwrap_or_default()),
        JsonValue::String(raw) => Kind::StringValue(raw.clone()),
        JsonValue::Array(items) => Kind::ListValue(ListValue {
            values: items.iter().map(proto_value_from_json).collect(),
        }),
        JsonValue::Object(_) => Kind::StructValue(struct_from_json_value(value)),
    };
    ProtoValue { kind: Some(kind) }
}

fn struct_from_json_value(value: &JsonValue) -> Struct {
    match value {
        JsonValue::Object(object) => Struct {
            fields: object
                .iter()
                .map(|(key, value)| (key.clone(), proto_value_from_json(value)))
                .collect(),
        },
        _ => Struct::default(),
    }
}

fn struct_from_json_str(raw: &str) -> Struct {
    serde_json::from_str::<JsonValue>(raw)
        .map(|value| struct_from_json_value(&value))
        .unwrap_or_default()
}

fn candidate_from_row(row: &Row, max_lexical_score: f64) -> CandidatePayload {
    let raw_lexical_score = row.get::<_, f64>("lexical_score").max(0.0);
    let freshness_days = row.get::<_, i32>("freshness_days") as i64;
    let age_days = row.get::<_, f64>("age_days").max(0.0);
    let lexical_score = if max_lexical_score > 0.0 {
        raw_lexical_score / max_lexical_score
    } else {
        0.0
    };
    let layer = row.get::<_, String>("layer");
    CandidatePayload {
        id: row.get::<_, String>("id"),
        title: row.get::<_, String>("title"),
        content: row.get::<_, String>("content"),
        layer: layer.clone(),
        scope: row.get::<_, String>("scope"),
        source_label: row.get::<_, String>("source_label"),
        source_path: row.get::<_, String>("source_path"),
        workspace_root: row.get::<_, String>("workspace_root"),
        updated_at: row.get::<_, String>("updated_at"),
        owner: row.get::<_, String>("owner"),
        tags: parse_json_string_array(&row.get::<_, String>("tags_json")),
        criticality: criticality_for_layer(&layer),
        freshness: freshness_from_age(age_days, freshness_days),
        similarity: 0.0,
        lexical_rank: row.get::<_, i64>("lexical_rank"),
        dense_rank: -1,
        graph_rank: -1,
        lexical_score: lexical_score.clamp(0.0, 1.0),
        dense_score: 0.0,
        rerank_score: 0.0,
        rerank_rank: -1,
        project_key: row.get::<_, String>("project_key"),
        environment: row.get::<_, String>("environment"),
        team: row.get::<_, String>("team"),
        source_type: row.get::<_, String>("source_type"),
        operable: row.get::<_, bool>("operable"),
        graph_hops: 0,
        graph_score: 0.0,
        graph_relation_types: Vec::new(),
        evidence_modalities: vec!["text".to_string()],
        reasons: Vec::new(),
    }
}

fn dense_candidate_from_row(row: &Row) -> CandidatePayload {
    let dense_distance = row.get::<_, f64>("dense_distance");
    let dense_score = (1.0 - dense_distance).clamp(0.0, 1.0);
    let freshness_days = row.get::<_, i32>("freshness_days") as i64;
    let age_days = row.get::<_, f64>("age_days").max(0.0);
    let layer = row.get::<_, String>("layer");
    CandidatePayload {
        id: row.get::<_, String>("id"),
        title: row.get::<_, String>("title"),
        content: row.get::<_, String>("content"),
        layer: layer.clone(),
        scope: row.get::<_, String>("scope"),
        source_label: row.get::<_, String>("source_label"),
        source_path: row.get::<_, String>("source_path"),
        workspace_root: row.get::<_, String>("workspace_root"),
        updated_at: row.get::<_, String>("updated_at"),
        owner: row.get::<_, String>("owner"),
        tags: parse_json_string_array(&row.get::<_, String>("tags_json")),
        criticality: criticality_for_layer(&layer),
        freshness: freshness_from_age(age_days, freshness_days),
        similarity: 0.0,
        lexical_rank: -1,
        dense_rank: row.get::<_, i64>("dense_rank"),
        graph_rank: -1,
        lexical_score: 0.0,
        dense_score,
        rerank_score: 0.0,
        rerank_rank: -1,
        project_key: row.get::<_, String>("project_key"),
        environment: row.get::<_, String>("environment"),
        team: row.get::<_, String>("team"),
        source_type: row.get::<_, String>("source_type"),
        operable: row.get::<_, bool>("operable"),
        graph_hops: 0,
        graph_score: 0.0,
        graph_relation_types: Vec::new(),
        evidence_modalities: vec!["text".to_string()],
        reasons: Vec::new(),
    }
}

fn vector_literal(values: &[f64]) -> Result<String, String> {
    if values.is_empty() {
        return Err("query_embedding is empty".to_string());
    }
    if values.len() > MAX_QUERY_EMBEDDING_DIMENSION {
        return Err("query_embedding dimension exceeds maximum".to_string());
    }
    let mut encoded = String::from("[");
    for (index, value) in values.iter().enumerate() {
        if !value.is_finite() {
            return Err("query_embedding contains non-finite value".to_string());
        }
        if index > 0 {
            encoded.push(',');
        }
        encoded.push_str(&format!("{value:.8}"));
    }
    encoded.push(']');
    Ok(encoded)
}

fn validate_query_embedding(envelope: &QueryEnvelopePayload) -> Result<bool, String> {
    if envelope.query_embedding.is_empty() {
        return Ok(false);
    }
    if envelope.query_embedding_model.trim().is_empty() {
        return Err(
            "query_embedding_model is required when query_embedding is present".to_string(),
        );
    }
    let expected_dimension = usize::try_from(envelope.query_embedding_dimension).unwrap_or(0);
    if expected_dimension != envelope.query_embedding.len() {
        return Err("query_embedding_dimension does not match query_embedding length".to_string());
    }
    vector_literal(&envelope.query_embedding)?;
    Ok(true)
}

fn evidence_from_row(row: &Row, max_lexical_score: f64) -> SupportingEvidencePayload {
    let raw_score = row.get::<_, f64>("lexical_score").max(0.0);
    SupportingEvidencePayload {
        evidence_key: row.get::<_, String>("evidence_key"),
        modality: row.get::<_, String>("modality"),
        label: row.get::<_, String>("label"),
        similarity: if max_lexical_score > 0.0 {
            (raw_score / max_lexical_score).clamp(0.0, 1.0)
        } else {
            0.0
        },
        confidence: row.get::<_, f64>("confidence").clamp(0.0, 1.0),
        trust_level: row.get::<_, String>("trust_level"),
        excerpt: row
            .get::<_, String>("excerpt")
            .chars()
            .take(360)
            .collect::<String>(),
        source_path: row.get::<_, String>("source_path"),
        source_url: row.get::<_, String>("source_url"),
        project_key: row.get::<_, String>("project_key"),
        workspace_fingerprint: row.get::<_, String>("workspace_fingerprint"),
        provenance_json: row.get::<_, String>("provenance_json"),
    }
}

fn evidence_matches_candidate(
    evidence: &SupportingEvidencePayload,
    candidate: &CandidatePayload,
    envelope: &QueryEnvelopePayload,
) -> bool {
    if !evidence.source_path.is_empty()
        && !candidate.source_path.is_empty()
        && (evidence.source_path == candidate.source_path
            || path_matches_root(&candidate.source_path, &evidence.source_path)
            || path_matches_root(&evidence.source_path, &candidate.source_path))
    {
        return true;
    }
    if !evidence.project_key.is_empty()
        && !candidate.project_key.is_empty()
        && evidence.project_key == candidate.project_key
    {
        return true;
    }
    if !envelope.workspace_fingerprint.is_empty()
        && !evidence.workspace_fingerprint.is_empty()
        && evidence.workspace_fingerprint == envelope.workspace_fingerprint
    {
        return true;
    }
    let provenance =
        serde_json::from_str::<JsonValue>(&evidence.provenance_json).unwrap_or(JsonValue::Null);
    let source_label = provenance
        .get("source_label")
        .and_then(JsonValue::as_str)
        .unwrap_or_default();
    source_label == candidate.source_label && !source_label.is_empty()
}

fn metadata_source_labels(metadata: &JsonValue) -> BTreeSet<String> {
    let mut labels = BTreeSet::new();
    if let Some(label) = metadata.get("source_label").and_then(JsonValue::as_str) {
        if !label.is_empty() {
            labels.insert(label.to_string());
        }
    }
    if let Some(items) = metadata.get("source_labels").and_then(JsonValue::as_array) {
        for item in items {
            if let Some(label) = item.as_str() {
                if !label.is_empty() {
                    labels.insert(label.to_string());
                }
            }
        }
    }
    labels
}

fn entity_from_row(row: &Row) -> CanonicalEntity {
    let metadata_json = row.get::<_, String>("metadata_json");
    let metadata_value =
        serde_json::from_str::<JsonValue>(&metadata_json).unwrap_or(JsonValue::Null);
    let aliases = metadata_value
        .get("aliases")
        .and_then(JsonValue::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(JsonValue::as_str)
                .map(str::to_string)
                .collect::<Vec<String>>()
        })
        .unwrap_or_default();
    CanonicalEntity {
        entity_key: row.get::<_, String>("entity_key"),
        entity_type: row.get::<_, String>("entity_type"),
        label: row.get::<_, String>("label"),
        aliases,
        confidence: 0.86,
        metadata: Some(struct_from_json_str(&metadata_json)),
    }
}

fn relation_from_row(row: &Row) -> CanonicalRelation {
    CanonicalRelation {
        relation_key: row.get::<_, String>("relation_key"),
        relation_type: row.get::<_, String>("relation_type"),
        source_entity_key: row.get::<_, String>("source_entity_key"),
        target_entity_key: row.get::<_, String>("target_entity_key"),
        weight: row.get::<_, f64>("weight"),
        metadata: Some(struct_from_json_str(&row.get::<_, String>("metadata_json"))),
    }
}

fn graph_signal_for_candidate(
    candidate: &CandidatePayload,
    query_tokens: &BTreeSet<String>,
    linked_entities: &[CanonicalEntity],
    graph_relations: &[CanonicalRelation],
) -> (f64, Vec<String>) {
    let haystack = format!(
        "{} {} {} {}",
        candidate.title, candidate.content, candidate.source_label, candidate.source_path
    )
    .to_lowercase();
    let mut relation_types = BTreeSet::new();
    let mut graph_score: f64 = 0.0;
    for entity in linked_entities {
        let label = entity.label.to_lowercase();
        let key = entity.entity_key.to_lowercase();
        if (!label.is_empty() && haystack.contains(&label))
            || (!key.is_empty() && haystack.contains(&key))
            || query_tokens.contains(&label)
        {
            graph_score = graph_score.max(0.55);
        }
    }
    for relation in graph_relations {
        if !relation.relation_type.is_empty() {
            let mut metadata_labels = BTreeSet::new();
            if let Some(metadata) = relation.metadata.as_ref() {
                let metadata_value = JsonValue::Object(
                    metadata
                        .fields
                        .iter()
                        .map(|(key, value)| {
                            let json_value = match value.kind.as_ref() {
                                Some(Kind::StringValue(raw)) => JsonValue::String(raw.clone()),
                                Some(Kind::ListValue(items)) => JsonValue::Array(
                                    items
                                        .values
                                        .iter()
                                        .filter_map(|item| match item.kind.as_ref() {
                                            Some(Kind::StringValue(raw)) => {
                                                Some(JsonValue::String(raw.clone()))
                                            }
                                            _ => None,
                                        })
                                        .collect(),
                                ),
                                _ => JsonValue::Null,
                            };
                            (key.clone(), json_value)
                        })
                        .collect(),
                );
                metadata_labels = metadata_source_labels(&metadata_value);
            }
            if metadata_labels.contains(&candidate.source_label) {
                graph_score = graph_score.max(relation.weight.clamp(0.0, 1.0));
                relation_types.insert(relation.relation_type.clone());
            } else if graph_score > 0.0 {
                relation_types.insert(relation.relation_type.clone());
            }
        }
    }
    (
        graph_score.clamp(0.0, 1.0),
        relation_types.into_iter().collect(),
    )
}

fn merge_candidate_payloads(
    lexical_candidates: Vec<CandidatePayload>,
    dense_candidates: Vec<CandidatePayload>,
) -> Vec<CandidatePayload> {
    let mut merged: BTreeMap<String, CandidatePayload> = BTreeMap::new();
    for candidate in lexical_candidates {
        merged.insert(candidate.id.clone(), candidate);
    }
    for dense in dense_candidates {
        if let Some(existing) = merged.get_mut(&dense.id) {
            existing.dense_score = dense.dense_score;
            existing.dense_rank = dense.dense_rank;
        } else {
            merged.insert(dense.id.clone(), dense);
        }
    }
    merged.into_values().collect()
}

fn rank_candidates(
    mut candidates: Vec<CandidatePayload>,
    supporting_evidence: &[SupportingEvidencePayload],
    linked_entities: &[CanonicalEntity],
    graph_relations: &[CanonicalRelation],
    envelope: &QueryEnvelopePayload,
    query: &str,
) -> Vec<RankedCandidate> {
    let query_tokens = tokenize(query);
    let mut ranked = candidates
        .drain(..)
        .enumerate()
        .map(|(index, mut candidate)| {
            let (graph_score, graph_relation_types) = graph_signal_for_candidate(
                &candidate,
                &query_tokens,
                linked_entities,
                graph_relations,
            );
            candidate.graph_score = graph_score;
            candidate.graph_relation_types = graph_relation_types;
            candidate.graph_hops = if candidate.graph_score > 0.0 { 1 } else { 0 };
            candidate.graph_rank = if candidate.graph_score > 0.0 { 1 } else { -1 };
            let scope = scope_score(&candidate, envelope);
            let freshness = freshness_score(&candidate.freshness);
            let operability = if candidate.operable {
                1.0
            } else if envelope.requires_write {
                0.0
            } else {
                0.45
            };
            let mut reasons = Vec::new();
            if candidate.lexical_score > 0.0 {
                reasons.push("lexical_match".to_string());
            }
            if candidate.dense_score > 0.0 {
                reasons.push("dense_match".to_string());
            }
            if matches!(
                candidate.layer.as_str(),
                "canonical_policy" | "approved_runbook"
            ) {
                reasons.push("authoritative_layer".to_string());
            }
            if candidate.freshness == "fresh" {
                reasons.push("fresh".to_string());
            } else {
                reasons.push(candidate.freshness.clone());
            }
            if scope >= 0.8 {
                reasons.push("scope_match".to_string());
            }
            if candidate.graph_score > 0.0 {
                reasons.push("graph_related".to_string());
            }
            if envelope.requires_write && !candidate.operable {
                reasons.push("non_operable_reference".to_string());
            }
            let evidence = supporting_evidence
                .iter()
                .filter(|item| evidence_matches_candidate(item, &candidate, envelope))
                .take(6)
                .cloned()
                .collect::<Vec<SupportingEvidencePayload>>();
            if !evidence.is_empty() {
                candidate.evidence_modalities.extend(
                    evidence
                        .iter()
                        .map(|item| item.modality.clone())
                        .filter(|item| !item.is_empty()),
                );
                candidate.evidence_modalities.sort();
                candidate.evidence_modalities.dedup();
                reasons.push("supporting_artifact_evidence".to_string());
            }
            candidate.reasons = reasons;
            let score = if candidate.dense_score > 0.0 {
                (0.34 * candidate.dense_score)
                    + (0.28 * candidate.lexical_score)
                    + (0.12 * layer_score(&candidate.layer))
                    + (0.08 * freshness)
                    + (0.08 * scope)
                    + (0.06 * candidate.graph_score)
                    + (0.04 * operability)
            } else {
                (0.48 * candidate.lexical_score)
                    + (0.18 * layer_score(&candidate.layer))
                    + (0.14 * freshness)
                    + (0.10 * scope)
                    + (0.06 * candidate.graph_score)
                    + (0.04 * operability)
            };
            candidate.similarity = score.clamp(0.0, 1.0);
            RankedCandidate {
                candidate,
                supporting_evidence: evidence,
                base_rank: index + 1,
                score: score.clamp(0.0, 1.0),
            }
        })
        .collect::<Vec<RankedCandidate>>();

    ranked.sort_by(|left, right| {
        right
            .score
            .total_cmp(&left.score)
            .then_with(|| {
                right
                    .candidate
                    .dense_score
                    .total_cmp(&left.candidate.dense_score)
            })
            .then_with(|| {
                right
                    .candidate
                    .lexical_score
                    .total_cmp(&left.candidate.lexical_score)
            })
            .then_with(|| {
                layer_score(&right.candidate.layer).total_cmp(&layer_score(&left.candidate.layer))
            })
            .then_with(|| {
                freshness_score(&right.candidate.freshness)
                    .total_cmp(&freshness_score(&left.candidate.freshness))
            })
            .then_with(|| right.candidate.updated_at.cmp(&left.candidate.updated_at))
            .then_with(|| {
                left.candidate
                    .source_label
                    .cmp(&right.candidate.source_label)
            })
    });
    for (index, item) in ranked.iter_mut().enumerate() {
        if item.candidate.graph_score > 0.0 {
            item.candidate.graph_rank = i64::try_from(index + 1).unwrap_or(1);
        }
    }
    ranked
}

fn build_retrieve_response(
    request: &RetrieveRequest,
    trace_id: String,
    candidates: Vec<RankedCandidate>,
    linked_entities: Vec<CanonicalEntity>,
    graph_relations: Vec<CanonicalRelation>,
) -> RetrieveResponse {
    let envelope = envelope_from_request(request);
    let query = if !envelope.normalized_query.is_empty() {
        envelope.normalized_query.clone()
    } else {
        request.query.clone()
    };
    let intent = classify_intent(&envelope, &candidates);
    let limit = usize::try_from(request.limit).unwrap_or(0).max(1);
    let selected = candidates
        .iter()
        .take(limit)
        .cloned()
        .collect::<Vec<RankedCandidate>>();
    let selected_ids = selected
        .iter()
        .map(|item| item.candidate.id.clone())
        .collect::<BTreeSet<String>>();
    let authoritative = build_authoritative(&selected, envelope.requires_write);
    let supporting = build_supporting(&selected);
    let uncertainty = uncertainty_level(!authoritative.is_empty(), false).to_string();
    let recommended_action_mode =
        recommended_action_mode(&intent, !authoritative.is_empty(), false).to_string();
    let grounding_score = if selected.is_empty() {
        0.0
    } else {
        let total = selected
            .iter()
            .map(|item| item.score.clamp(0.0, 1.25))
            .sum::<f64>();
        round4((total / selected.len() as f64).min(1.0))
    };
    let route = route_for_intent(&intent);
    let scope_filters_present = !envelope.project_key.is_empty()
        || !envelope.environment.is_empty()
        || !envelope.team.is_empty()
        || !envelope.workspace_dir.is_empty()
        || !envelope.allowed_source_labels.is_empty()
        || !envelope.allowed_workspace_roots.is_empty();
    let dense_hits = candidates
        .iter()
        .filter(|item| item.candidate.dense_score > 0.0)
        .count();
    let explanation = format!(
        "engine=rust_retrieval_engine; selected={}; authoritative={}; supporting={}; dense_hits={}; graph_relations={}; workspace_fingerprint_present={}; scope_filters_present={}",
        selected.len(),
        authoritative.len(),
        supporting.len(),
        dense_hits,
        graph_relations.len(),
        !envelope.workspace_fingerprint.is_empty(),
        scope_filters_present,
    );
    let answer_plan = answer_plan(&intent, &selected, &authoritative, &supporting);
    let judge_result = judge_result(authoritative.len(), supporting.len());

    RetrieveResponse {
        trace_id,
        normalized_query: query.clone(),
        query_intent: intent,
        route,
        strategy: if envelope.strategy.is_empty() {
            "hybrid_graph_v2".to_string()
        } else {
            envelope.strategy
        },
        selected_hits: selected
            .iter()
            .map(|item| candidate_to_proto_hit(&item.candidate, item.score))
            .collect(),
        candidate_hits: candidates
            .iter()
            .map(|item| candidate_to_proto_hit(&item.candidate, item.score))
            .collect(),
        trace_hits: build_trace_hits(&candidates, &selected_ids),
        authoritative_evidence: authoritative,
        supporting_evidence: supporting,
        linked_entities,
        graph_relations,
        subqueries: vec![query],
        open_conflicts: Vec::new(),
        uncertainty_notes: if selected_ids.is_empty() {
            vec!["no candidate hits returned".to_string()]
        } else if selected.len() < limit {
            vec!["retrieval returned fewer hits than requested".to_string()]
        } else {
            Vec::new()
        },
        uncertainty_level: uncertainty,
        recommended_action_mode,
        required_verifications: selected
            .iter()
            .take(3)
            .map(|item| item.candidate.source_label.clone())
            .collect(),
        graph_hops: i32::try_from(
            selected
                .iter()
                .map(|item| item.candidate.graph_hops)
                .max()
                .unwrap_or(0),
        )
        .unwrap_or_default(),
        grounding_score,
        answer_plan: Some(answer_plan),
        judge_result: Some(judge_result),
        effective_engine: if dense_hits > 0 {
            "rust_grpc+hybrid_dense".to_string()
        } else {
            "rust_grpc".to_string()
        },
        fallback_used: false,
        explanation,
    }
}

async fn query_candidate_payloads(
    client: &Client,
    schema: &str,
    request: &RetrieveRequest,
    envelope: &QueryEnvelopePayload,
    query: &str,
) -> Result<Vec<CandidatePayload>, Status> {
    let limit = usize::try_from(request.limit).unwrap_or(0).max(1);
    let candidate_window = candidate_window(limit);
    let (allowed_source_labels, allowed_source_prefixes) =
        source_label_patterns(&envelope.allowed_source_labels);
    let allowed_workspace_roots = workspace_root_patterns(&envelope.allowed_workspace_roots);
    let sql = format!(
        r#"WITH search AS (
               SELECT websearch_to_tsquery('simple', $2) AS query
           ),
           ranked AS (
               SELECT chunk_key AS id,
                      title,
                      content,
                      layer,
                      scope,
                      source_label,
                      source_path,
                      workspace_root,
                      COALESCE(updated_at::text, '') AS updated_at,
                      owner,
                      project_key,
                      environment,
                      team,
                      source_type,
                      operable,
                      freshness_days,
                      COALESCE(tags_json::text, '[]') AS tags_json,
                      ts_rank_cd(search_vector, search.query)::DOUBLE PRECISION AS lexical_score,
                      (EXTRACT(EPOCH FROM (NOW() - updated_at))::DOUBLE PRECISION / 86400.0) AS age_days,
                      ROW_NUMBER() OVER (
                          ORDER BY ts_rank_cd(search_vector, search.query) DESC,
                                   updated_at DESC,
                                   source_label ASC,
                                   chunk_key ASC
                      )::BIGINT AS lexical_rank
                 FROM {chunks}, search
                WHERE agent_id = $1
                  AND numnode(search.query) > 0
                  AND search_vector @@ search.query
                  AND ($3 = '' OR project_key = '' OR project_key = $3)
                  AND ($4 = '' OR environment = '' OR environment = $4)
                  AND ($5 = '' OR team = '' OR team = $5)
                  AND (
                        cardinality($6::TEXT[]) = 0
                        OR source_label = ANY($6::TEXT[])
                        OR EXISTS (
                            SELECT 1
                              FROM unnest($7::TEXT[]) AS prefix(value)
                             WHERE source_label LIKE prefix.value || '%' ESCAPE '\'
                        )
                  )
                  AND (
                        cardinality($8::TEXT[]) = 0
                        OR workspace_root = ''
                        OR EXISTS (
                            SELECT 1
                              FROM unnest($8::TEXT[]) AS root(value)
                             WHERE workspace_root = root.value
                                OR workspace_root LIKE root.value || '/%' ESCAPE '\'
                                OR source_path = root.value
                                OR source_path LIKE root.value || '/%' ESCAPE '\'
                        )
                  )
           )
           SELECT *
             FROM ranked
            ORDER BY lexical_score DESC, updated_at DESC, source_label ASC, id ASC
            LIMIT $9"#,
        chunks = qualified_relation(schema, "knowledge_chunks")
    );
    let rows = client
        .query(
            &sql,
            &[
                &request.agent_id,
                &query,
                &envelope.project_key,
                &envelope.environment,
                &envelope.team,
                &allowed_source_labels,
                &allowed_source_prefixes,
                &allowed_workspace_roots,
                &candidate_window,
            ],
        )
        .await
        .map_err(|error| {
            Status::internal(format!("failed to query retrieval candidates: {error}"))
        })?;
    let max_lexical_score = rows
        .iter()
        .map(|row| row.get::<_, f64>("lexical_score"))
        .fold(0.0, f64::max);
    Ok(rows
        .iter()
        .map(|row| candidate_from_row(row, max_lexical_score))
        .collect())
}

async fn dense_schema_ready(client: &Client, schema: &str) -> Result<bool, Status> {
    client
        .query_one(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS pgvector_extension,
                    EXISTS (
                        SELECT 1
                          FROM information_schema.columns
                         WHERE table_schema = $1
                           AND table_name = 'knowledge_embeddings'
                           AND column_name = 'embedding_vector'
                    ) AS embedding_vector_column,
                    to_regclass($2) IS NOT NULL AS vector_index",
            &[
                &schema,
                &regclass_name(schema, "idx_knowledge_embeddings_vector_hnsw"),
            ],
        )
        .await
        .map(|row| {
            row.get::<_, bool>("pgvector_extension")
                && row.get::<_, bool>("embedding_vector_column")
                && row.get::<_, bool>("vector_index")
        })
        .map_err(|error| knowledge_pg_error("inspect dense retrieval schema", error))
}

async fn query_dense_candidate_payloads(
    client: &Client,
    schema: &str,
    request: &RetrieveRequest,
    envelope: &QueryEnvelopePayload,
) -> Result<Vec<CandidatePayload>, Status> {
    if !validate_query_embedding(envelope).map_err(Status::invalid_argument)? {
        return Ok(Vec::new());
    }
    if !dense_schema_ready(client, schema).await? {
        return Ok(Vec::new());
    }
    let limit = usize::try_from(request.limit).unwrap_or(0).max(1);
    let candidate_window = candidate_window(limit);
    let vector = vector_literal(&envelope.query_embedding).map_err(Status::invalid_argument)?;
    let (allowed_source_labels, allowed_source_prefixes) =
        source_label_patterns(&envelope.allowed_source_labels);
    let allowed_workspace_roots = workspace_root_patterns(&envelope.allowed_workspace_roots);
    let sql = format!(
        r#"SELECT c.chunk_key AS id,
                  c.title,
                  c.content,
                  c.layer,
                  c.scope,
                  c.source_label,
                  c.source_path,
                  c.workspace_root,
                  COALESCE(c.updated_at::text, '') AS updated_at,
                  c.owner,
                  c.project_key,
                  c.environment,
                  c.team,
                  c.source_type,
                  c.operable,
                  c.freshness_days,
                  COALESCE(c.tags_json::text, '[]') AS tags_json,
                  (e.embedding_vector <=> $2::TEXT::vector)::DOUBLE PRECISION AS dense_distance,
                  (EXTRACT(EPOCH FROM (NOW() - c.updated_at))::DOUBLE PRECISION / 86400.0) AS age_days,
                  ROW_NUMBER() OVER (
                      ORDER BY e.embedding_vector <=> $2::TEXT::vector,
                               c.updated_at DESC,
                               c.source_label ASC,
                               c.chunk_key ASC
                  )::BIGINT AS dense_rank
             FROM {embeddings} e
             JOIN {chunks} c
               ON c.agent_id = e.agent_id
              AND c.chunk_key = e.chunk_key
            WHERE e.agent_id = $1
              AND e.model = $3
              AND e.embedding_vector IS NOT NULL
              AND c.agent_id = $1
              AND ($4 = '' OR c.project_key = '' OR c.project_key = $4)
              AND ($5 = '' OR c.environment = '' OR c.environment = $5)
              AND ($6 = '' OR c.team = '' OR c.team = $6)
              AND (
                    cardinality($7::TEXT[]) = 0
                    OR c.source_label = ANY($7::TEXT[])
                    OR EXISTS (
                        SELECT 1
                          FROM unnest($8::TEXT[]) AS prefix(value)
                         WHERE c.source_label LIKE prefix.value || '%' ESCAPE '\'
                    )
              )
              AND (
                    cardinality($9::TEXT[]) = 0
                    OR c.workspace_root = ''
                    OR EXISTS (
                        SELECT 1
                          FROM unnest($9::TEXT[]) AS root(value)
                         WHERE c.workspace_root = root.value
                            OR c.workspace_root LIKE root.value || '/%' ESCAPE '\'
                            OR c.source_path = root.value
                            OR c.source_path LIKE root.value || '/%' ESCAPE '\'
                    )
              )
            ORDER BY dense_distance ASC, c.updated_at DESC, c.source_label ASC, id ASC
            LIMIT $10"#,
        embeddings = qualified_relation(schema, "knowledge_embeddings"),
        chunks = qualified_relation(schema, "knowledge_chunks")
    );
    let rows = client
        .query(
            &sql,
            &[
                &request.agent_id,
                &vector,
                &envelope.query_embedding_model,
                &envelope.project_key,
                &envelope.environment,
                &envelope.team,
                &allowed_source_labels,
                &allowed_source_prefixes,
                &allowed_workspace_roots,
                &candidate_window,
            ],
        )
        .await
        .map_err(|error| {
            Status::internal(format!(
                "failed to query dense retrieval candidates: {error}"
            ))
        })?;
    Ok(rows.iter().map(dense_candidate_from_row).collect())
}

async fn query_supporting_evidence(
    client: &Client,
    schema: &str,
    request: &RetrieveRequest,
    envelope: &QueryEnvelopePayload,
    query: &str,
) -> Result<Vec<SupportingEvidencePayload>, Status> {
    let sql = format!(
        r#"WITH search AS (
               SELECT websearch_to_tsquery('simple', $2) AS query
           ),
           ranked AS (
               SELECT derivative_key AS evidence_key,
                      modality,
                      label,
                      LEFT(extracted_text, 720) AS excerpt,
                      confidence,
                      trust_level,
                      source_path,
                      source_url,
                      project_key,
                      workspace_fingerprint,
                      COALESCE(provenance_json::text, '{{}}') AS provenance_json,
                      ts_rank_cd(search_vector, search.query)::DOUBLE PRECISION AS lexical_score
                 FROM {artifacts}, search
                WHERE agent_id = $1
                  AND numnode(search.query) > 0
                  AND search_vector @@ search.query
                  AND ($3 = '' OR project_key = '' OR project_key = $3)
                  AND ($4 = '' OR workspace_fingerprint = '' OR workspace_fingerprint = $4)
                ORDER BY lexical_score DESC, confidence DESC, created_at DESC, derivative_key ASC
                LIMIT 48
           )
           SELECT *
             FROM ranked"#,
        artifacts = qualified_relation(schema, "artifact_derivatives")
    );
    let rows = client
        .query(
            &sql,
            &[
                &request.agent_id,
                &query,
                &envelope.project_key,
                &envelope.workspace_fingerprint,
            ],
        )
        .await
        .map_err(|error| {
            Status::internal(format!("failed to query supporting evidence: {error}"))
        })?;
    let max_lexical_score = rows
        .iter()
        .map(|row| row.get::<_, f64>("lexical_score"))
        .fold(0.0, f64::max);
    Ok(rows
        .iter()
        .map(|row| evidence_from_row(row, max_lexical_score))
        .collect())
}

async fn query_graph_context(
    client: &Client,
    schema: &str,
    agent_id: &str,
    query: &str,
    candidates: &[CandidatePayload],
) -> Result<(Vec<CanonicalEntity>, Vec<CanonicalRelation>), Status> {
    let terms = query_terms(query);
    let source_labels = candidates
        .iter()
        .map(|candidate| candidate.source_label.trim().to_string())
        .filter(|source_label| !source_label.is_empty())
        .collect::<BTreeSet<String>>()
        .into_iter()
        .collect::<Vec<String>>();
    if terms.is_empty() && source_labels.is_empty() {
        return Ok((Vec::new(), Vec::new()));
    }
    let entity_sql = format!(
        r#"SELECT entity_key,
                  entity_type,
                  label,
                  COALESCE(metadata_json::text, '{{}}') AS metadata_json,
                  COALESCE(updated_at::text, '') AS updated_at
             FROM {entities}
            WHERE agent_id = $1
              AND (
                    lower(entity_key) = ANY($2::TEXT[])
                    OR lower(label) = ANY($2::TEXT[])
                    OR EXISTS (
                        SELECT 1
                          FROM unnest($2::TEXT[]) AS term(value)
                         WHERE lower(entity_key) LIKE '%' || term.value || '%'
                            OR lower(label) LIKE '%' || term.value || '%'
                    )
              )
            ORDER BY updated_at DESC, entity_key ASC
            LIMIT 24"#,
        entities = qualified_relation(schema, "knowledge_entities")
    );
    let entity_rows = client
        .query(&entity_sql, &[&agent_id, &terms])
        .await
        .map_err(|error| knowledge_pg_error("query graph entities", error))?;
    let mut linked_entities = entity_rows
        .iter()
        .map(entity_from_row)
        .collect::<Vec<CanonicalEntity>>();
    let entity_keys = linked_entities
        .iter()
        .map(|item| item.entity_key.clone())
        .filter(|item| !item.is_empty())
        .collect::<Vec<String>>();
    if entity_keys.is_empty() && source_labels.is_empty() {
        return Ok((linked_entities, Vec::new()));
    }
    let relation_sql = format!(
        r#"SELECT relation_key,
                  relation_type,
                  source_entity_key,
                  target_entity_key,
                  weight,
                  COALESCE(metadata_json::text, '{{}}') AS metadata_json,
                  COALESCE(updated_at::text, '') AS updated_at
             FROM {relations}
            WHERE agent_id = $1
              AND (
                    source_entity_key = ANY($2::TEXT[])
                    OR target_entity_key = ANY($2::TEXT[])
                    OR (
                        cardinality($3::TEXT[]) > 0
                        AND (
                            metadata_json->>'source_label' = ANY($3::TEXT[])
                            OR metadata_json->>'sourceLabel' = ANY($3::TEXT[])
                            OR EXISTS (
                                SELECT 1
                                  FROM jsonb_array_elements_text(
                                           CASE
                                               WHEN jsonb_typeof(metadata_json->'source_labels') = 'array'
                                               THEN metadata_json->'source_labels'
                                               ELSE '[]'::jsonb
                                           END
                                       ) AS label(value)
                                 WHERE label.value = ANY($3::TEXT[])
                            )
                        )
                    )
              )
            ORDER BY weight DESC, updated_at DESC, relation_key ASC
            LIMIT 48"#,
        relations = qualified_relation(schema, "knowledge_relations")
    );
    let relation_rows = client
        .query(&relation_sql, &[&agent_id, &entity_keys, &source_labels])
        .await
        .map_err(|error| knowledge_pg_error("query graph relations", error))?;
    let relations = relation_rows
        .iter()
        .map(relation_from_row)
        .collect::<Vec<CanonicalRelation>>();
    let known_entity_keys = linked_entities
        .iter()
        .map(|entity| entity.entity_key.clone())
        .collect::<BTreeSet<String>>();
    let related_entity_keys = relations
        .iter()
        .flat_map(|relation| {
            [
                relation.source_entity_key.clone(),
                relation.target_entity_key.clone(),
            ]
        })
        .filter(|entity_key| !entity_key.is_empty() && !known_entity_keys.contains(entity_key))
        .collect::<BTreeSet<String>>()
        .into_iter()
        .collect::<Vec<String>>();
    if !related_entity_keys.is_empty() {
        let related_entity_sql = format!(
            r#"SELECT entity_key,
                      entity_type,
                      label,
                      COALESCE(metadata_json::text, '{{}}') AS metadata_json,
                      COALESCE(updated_at::text, '') AS updated_at
                 FROM {entities}
                WHERE agent_id = $1
                  AND entity_key = ANY($2::TEXT[])
                ORDER BY updated_at DESC, entity_key ASC
                LIMIT 48"#,
            entities = qualified_relation(schema, "knowledge_entities")
        );
        let related_entity_rows = client
            .query(&related_entity_sql, &[&agent_id, &related_entity_keys])
            .await
            .map_err(|error| {
                Status::internal(format!("failed to query related graph entities: {error}"))
            })?;
        linked_entities.extend(related_entity_rows.iter().map(entity_from_row));
    }
    Ok((linked_entities, relations))
}

async fn retrieve_payload(
    request: &RetrieveRequest,
    trace_id: String,
) -> Result<RetrieveResponse, Status> {
    let agent_id = request.agent_id.trim();
    if agent_id.is_empty() {
        return Err(Status::invalid_argument("agent_id is required"));
    }
    let envelope = envelope_from_request(request);
    let query = if !envelope.normalized_query.trim().is_empty() {
        envelope.normalized_query.trim().to_string()
    } else {
        request.query.trim().to_string()
    };
    if query.is_empty() {
        return Err(Status::invalid_argument("query is required"));
    }
    let embedding_present =
        validate_query_embedding(&envelope).map_err(Status::invalid_argument)?;
    let min_tier = QualityTier::from_env();
    if min_tier >= QualityTier::HybridDense && !embedding_present {
        return Err(Status::failed_precondition(
            "hybrid_dense retrieval requires a real query_embedding",
        ));
    }
    let pool = knowledge_postgres_pool().await?;
    let client = pool.connection(PostgresWorkload::Read, "retrieve").await?;
    let schema = knowledge_postgres_schema();
    let lexical_candidates =
        query_candidate_payloads(&client, &schema, request, &envelope, &query).await?;
    let dense_candidates =
        query_dense_candidate_payloads(&client, &schema, request, &envelope).await?;
    if min_tier >= QualityTier::HybridDense && dense_candidates.is_empty() {
        let schema_health = inspect_knowledge_schema().await;
        if schema_health.indexed_chunks_approx == 0 {
            let candidates = Vec::new();
            let supporting_evidence =
                query_supporting_evidence(&client, &schema, request, &envelope, &query).await?;
            let (linked_entities, graph_relations) =
                query_graph_context(&client, &schema, agent_id, &query, &candidates).await?;
            let ranked = rank_candidates(
                candidates,
                &supporting_evidence,
                &linked_entities,
                &graph_relations,
                &envelope,
                &query,
            );
            return Ok(build_retrieve_response(
                request,
                trace_id,
                ranked,
                linked_entities,
                graph_relations,
            ));
        }
        return Err(Status::failed_precondition(
            "hybrid_dense retrieval is not available for this query/schema/model",
        ));
    }
    let candidates = merge_candidate_payloads(lexical_candidates, dense_candidates);
    let supporting_evidence =
        query_supporting_evidence(&client, &schema, request, &envelope, &query).await?;
    let (linked_entities, graph_relations) =
        query_graph_context(&client, &schema, agent_id, &query, &candidates).await?;
    let ranked = rank_candidates(
        candidates,
        &supporting_evidence,
        &linked_entities,
        &graph_relations,
        &envelope,
        &query,
    );
    Ok(build_retrieve_response(
        request,
        trace_id,
        ranked,
        linked_entities,
        graph_relations,
    ))
}

async fn list_graph_payload(
    agent_id: &str,
    entity_type: &str,
    limit: u32,
) -> Result<(Vec<GraphEntity>, Vec<GraphRelation>), Status> {
    let schema = knowledge_postgres_schema();
    let client = knowledge_postgres_pool()
        .await?
        .connection(PostgresWorkload::Read, "list_graph")
        .await?;
    let capped_limit = i64::from(limit.max(1));
    let entity_table = qualified_relation(&schema, "knowledge_entities");
    let entity_rows = client
        .query(
            &format!(
                r#"SELECT entity_key,
                          entity_type,
                          label,
                          source_kind,
                          COALESCE(metadata_json::text, '{{}}') AS metadata_json,
                          COALESCE(updated_at::text, '') AS updated_at
                   FROM {entity_table}
                  WHERE agent_id = $1
                    AND ($2 = '' OR entity_type = $2)
                  ORDER BY updated_at DESC
                  LIMIT $3"#,
                entity_table = entity_table
            ),
            &[&agent_id, &entity_type, &capped_limit],
        )
        .await
        .map_err(|error| knowledge_pg_error("query graph entities", error))?;
    let entities = entity_rows
        .iter()
        .map(|row| GraphEntity {
            entity_key: row.get::<_, String>("entity_key"),
            entity_type: row.get::<_, String>("entity_type"),
            label: row.get::<_, String>("label"),
            source_kind: row.get::<_, String>("source_kind"),
            metadata: Some(struct_from_json_str(&row.get::<_, String>("metadata_json"))),
            updated_at: row.get::<_, String>("updated_at"),
            graph_score: 0.0,
            graph_hops: 0,
            relation_types: Vec::new(),
        })
        .collect::<Vec<GraphEntity>>();
    let entity_keys = entities
        .iter()
        .map(|item| item.entity_key.clone())
        .filter(|value| !value.is_empty())
        .collect::<Vec<String>>();
    if entity_keys.is_empty() {
        return Ok((entities, Vec::new()));
    }
    let relation_limit = capped_limit.saturating_mul(2).max(1);
    let relation_table = qualified_relation(&schema, "knowledge_relations");
    let relation_rows = client
        .query(
            &format!(
                r#"SELECT relation_key,
                          relation_type,
                          source_entity_key,
                          target_entity_key,
                          weight,
                          COALESCE(metadata_json::text, '{{}}') AS metadata_json,
                          COALESCE(updated_at::text, '') AS updated_at
                   FROM {relation_table}
                  WHERE agent_id = $1
                    AND source_entity_key = ANY($2::TEXT[])
                    AND target_entity_key = ANY($2::TEXT[])
                  ORDER BY updated_at DESC
                  LIMIT $3"#,
                relation_table = relation_table
            ),
            &[&agent_id, &entity_keys, &relation_limit],
        )
        .await
        .map_err(|error| knowledge_pg_error("query graph relations", error))?;
    let relations = relation_rows
        .iter()
        .map(|row| GraphRelation {
            relation_key: row.get::<_, String>("relation_key"),
            relation_type: row.get::<_, String>("relation_type"),
            source_entity_key: row.get::<_, String>("source_entity_key"),
            target_entity_key: row.get::<_, String>("target_entity_key"),
            weight: row.get::<_, f64>("weight"),
            metadata: Some(struct_from_json_str(&row.get::<_, String>("metadata_json"))),
            updated_at: row.get::<_, String>("updated_at"),
        })
        .collect::<Vec<GraphRelation>>();
    Ok((entities, relations))
}

#[derive(Default)]
struct RetrievalServer;

#[tonic::async_trait]
impl RetrievalEngineService for RetrievalServer {
    async fn retrieve(
        &self,
        request: Request<RetrieveRequest>,
    ) -> Result<Response<RetrieveResponse>, Status> {
        let payload = request.into_inner();
        let trace_id = format!(
            "retrieval-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis()
        );
        Ok(Response::new(retrieve_payload(&payload, trace_id).await?))
    }

    async fn list_graph(
        &self,
        request: Request<ListGraphRequest>,
    ) -> Result<Response<ListGraphResponse>, Status> {
        let payload = request.into_inner();
        let agent_id = payload.agent_id.trim();
        if agent_id.is_empty() {
            return Err(Status::invalid_argument("agent_id is required"));
        }
        let (entities, relations) =
            list_graph_payload(agent_id, payload.entity_type.trim(), payload.limit).await?;
        Ok(Response::new(ListGraphResponse {
            entities,
            relations,
        }))
    }

    async fn health(
        &self,
        _request: Request<HealthRequest>,
    ) -> Result<Response<HealthResponse>, Status> {
        let mut details = health_details(SERVICE_NAME);
        let schema_health = inspect_knowledge_schema().await;
        let min_coverage = min_vector_coverage();
        let actual_tier = schema_health.quality_tier(min_coverage);
        let min_tier = QualityTier::from_env();
        let rust_required_tier = if min_tier >= QualityTier::HybridReranked {
            QualityTier::HybridDense
        } else {
            min_tier
        };
        let bundle_ready = schema_health.bundle_ready() && actual_tier >= rust_required_tier;
        let dense_ready = schema_health.dense_ready(min_coverage);
        let mut capabilities = vec!["typed-contract"];
        if schema_health.postgres_ready
            && schema_health.knowledge_entities
            && schema_health.knowledge_relations
        {
            capabilities.push("graph_read");
        }
        if schema_health.bundle_ready() {
            capabilities.push("bundle-assembly");
            capabilities.push("lexical");
            capabilities.push("supporting_evidence");
            capabilities.push("deterministic-ranking");
        }
        if dense_ready {
            capabilities.push("hybrid_dense");
            capabilities.push("pgvector");
        }
        details.insert("authoritative".to_string(), bundle_ready.to_string());
        details.insert("production_ready".to_string(), bundle_ready.to_string());
        details.insert("cutover_allowed".to_string(), bundle_ready.to_string());
        details.insert("quality_tier".to_string(), actual_tier.as_str().to_string());
        details.insert(
            "min_quality_tier".to_string(),
            min_tier.as_str().to_string(),
        );
        details.insert("dense_ready".to_string(), dense_ready.to_string());
        details.insert(
            "rerank_ready".to_string(),
            (actual_tier >= QualityTier::HybridReranked).to_string(),
        );
        details.insert(
            "pgvector_ready".to_string(),
            schema_health.pgvector_extension.to_string(),
        );
        details.insert(
            "chunk_vector_coverage".to_string(),
            format!("{:.4}", schema_health.vector_coverage()),
        );
        details.insert(
            "vector_coverage_min".to_string(),
            format!("{min_coverage:.4}"),
        );
        details.insert(
            "candidate_window".to_string(),
            dense_window_limit().to_string(),
        );
        details.insert(
            "maturity".to_string(),
            if bundle_ready {
                "ga"
            } else if schema_health.bundle_ready() {
                "degraded"
            } else {
                "scaffold"
            }
            .to_string(),
        );
        details.insert(
            "bundle_assembly".to_string(),
            if schema_health.bundle_ready() {
                "enabled".to_string()
            } else {
                "disabled_until_real_index".to_string()
            },
        );
        details.insert(
            "postgres".to_string(),
            if schema_health.postgres_ready {
                "ready".to_string()
            } else if knowledge_postgres_dsn().is_empty() {
                "unconfigured".to_string()
            } else {
                "unreachable".to_string()
            },
        );
        details.insert(
            "postgres_pool_size".to_string(),
            schema_health.pool_size.to_string(),
        );
        if let Ok(pool) = knowledge_postgres_pool().await {
            details.extend(pool.health_details());
        }
        details.insert("postgres_schema".to_string(), knowledge_postgres_schema());
        details.insert(
            "indexed_chunks_approx".to_string(),
            schema_health.indexed_chunks_approx.to_string(),
        );
        details.insert(
            "indexed_embeddings_approx".to_string(),
            schema_health.indexed_embeddings_approx.to_string(),
        );
        details.insert(
            "indexed_artifacts_approx".to_string(),
            schema_health.indexed_artifacts_approx.to_string(),
        );
        details.insert(
            "chunk_vector_count".to_string(),
            schema_health.chunk_vector_count.to_string(),
        );
        details.insert(
            "artifact_vector_count".to_string(),
            schema_health.artifact_vector_count.to_string(),
        );
        details.insert(
            "required_tables".to_string(),
            [
                ("knowledge_chunks", schema_health.knowledge_chunks),
                ("knowledge_embeddings", schema_health.knowledge_embeddings),
                ("knowledge_entities", schema_health.knowledge_entities),
                ("knowledge_relations", schema_health.knowledge_relations),
                ("artifact_derivatives", schema_health.artifact_derivatives),
            ]
            .into_iter()
            .map(|(name, ready)| format!("{name}:{ready}"))
            .collect::<Vec<String>>()
            .join(","),
        );
        details.insert(
            "required_indexes".to_string(),
            [
                (
                    "idx_knowledge_chunks_lookup",
                    schema_health.idx_knowledge_chunks_lookup,
                ),
                (
                    "idx_knowledge_chunks_search",
                    schema_health.idx_knowledge_chunks_search,
                ),
                (
                    "idx_artifact_derivatives_lookup",
                    schema_health.idx_artifact_derivatives_lookup,
                ),
                (
                    "idx_artifact_derivatives_search",
                    schema_health.idx_artifact_derivatives_search,
                ),
                (
                    "idx_knowledge_embeddings_lookup",
                    schema_health.idx_knowledge_embeddings_lookup,
                ),
                (
                    "idx_knowledge_entities_lookup",
                    schema_health.idx_knowledge_entities_lookup,
                ),
                (
                    "idx_knowledge_relations_lookup",
                    schema_health.idx_knowledge_relations_lookup,
                ),
                (
                    "idx_knowledge_embeddings_vector_hnsw",
                    schema_health.idx_knowledge_embeddings_vector_hnsw,
                ),
                (
                    "idx_artifact_derivatives_vector_hnsw",
                    schema_health.idx_artifact_derivatives_vector_hnsw,
                ),
            ]
            .into_iter()
            .map(|(name, ready)| format!("{name}:{ready}"))
            .collect::<Vec<String>>()
            .join(","),
        );
        if !schema_health.error.is_empty() {
            details.insert("postgres_error".to_string(), schema_health.error);
        }
        details.insert("capabilities".to_string(), capabilities.join(","));
        Ok(Response::new(HealthResponse {
            service: SERVICE_NAME.to_string(),
            ready: bundle_ready,
            status: if bundle_ready { "ready" } else { "not_ready" }.to_string(),
            details,
        }))
    }
}

async fn serve_target(target: &str) -> Result<()> {
    let service = RetrievalEngineServiceServer::new(RetrievalServer);
    let uds_target = target.strip_prefix("unix://").unwrap_or(target);
    if target.starts_with("unix://") || target.starts_with('/') {
        if let Some(parent) = std::path::Path::new(uds_target).parent() {
            fs::create_dir_all(parent).await?;
        }
        if std::path::Path::new(uds_target).exists() {
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
        std::env::var("RETRIEVAL_GRPC_TARGET").unwrap_or_else(|_| "127.0.0.1:50062".to_string());
    serve_target(&target).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;
    use tokio_postgres::NoTls;

    fn candidate_fixture(id: &str, layer: &str, lexical_score: f64) -> CandidatePayload {
        CandidatePayload {
            id: id.to_string(),
            title: format!("{id} deploy policy"),
            content: "deploy rollback runbook".to_string(),
            layer: layer.to_string(),
            scope: "operational_policy".to_string(),
            source_label: format!("policy:{id}"),
            source_path: format!("/repo/{id}.md"),
            workspace_root: "/repo".to_string(),
            updated_at: "2026-01-01 00:00:00+00".to_string(),
            owner: "platform".to_string(),
            tags: vec!["deploy".to_string()],
            criticality: criticality_for_layer(layer),
            freshness: "fresh".to_string(),
            similarity: 0.0,
            lexical_rank: 1,
            dense_rank: -1,
            graph_rank: -1,
            lexical_score,
            dense_score: 0.0,
            rerank_score: 0.0,
            rerank_rank: -1,
            project_key: "KODA".to_string(),
            environment: "prod".to_string(),
            team: "platform".to_string(),
            source_type: "document".to_string(),
            operable: true,
            graph_hops: 0,
            graph_score: 0.0,
            graph_relation_types: Vec::new(),
            evidence_modalities: vec!["text".to_string()],
            reasons: Vec::new(),
        }
    }

    #[test]
    fn schema_health_requires_real_bundle_indexes() {
        let scaffold = KnowledgeSchemaHealth {
            postgres_configured: true,
            postgres_ready: true,
            knowledge_chunks: true,
            knowledge_embeddings: true,
            knowledge_entities: true,
            knowledge_relations: true,
            artifact_derivatives: true,
            idx_knowledge_chunks_lookup: true,
            idx_knowledge_chunks_search: false,
            idx_knowledge_embeddings_lookup: true,
            idx_knowledge_entities_lookup: true,
            idx_knowledge_relations_lookup: true,
            idx_artifact_derivatives_lookup: true,
            idx_artifact_derivatives_search: true,
            ..KnowledgeSchemaHealth::default()
        };
        assert!(!scaffold.bundle_ready());

        let ready = KnowledgeSchemaHealth {
            idx_knowledge_chunks_search: true,
            ..scaffold
        };
        assert!(ready.bundle_ready());
    }

    #[test]
    fn source_label_patterns_split_exact_and_prefix_wildcards() {
        let (exact, prefixes) =
            source_label_patterns(&["policy:*".to_string(), "runbook:deploy".to_string()]);

        assert_eq!(exact, vec!["runbook:deploy"]);
        assert_eq!(prefixes, vec!["policy:"]);
    }

    #[test]
    fn schema_health_promotes_dense_only_with_vector_coverage() {
        let health = KnowledgeSchemaHealth {
            postgres_configured: true,
            postgres_ready: true,
            knowledge_chunks: true,
            knowledge_embeddings: true,
            knowledge_entities: true,
            knowledge_relations: true,
            artifact_derivatives: true,
            idx_knowledge_chunks_lookup: true,
            idx_knowledge_chunks_search: true,
            idx_knowledge_embeddings_lookup: true,
            idx_knowledge_entities_lookup: true,
            idx_knowledge_relations_lookup: true,
            idx_artifact_derivatives_lookup: true,
            idx_artifact_derivatives_search: true,
            idx_knowledge_embeddings_vector_hnsw: true,
            idx_artifact_derivatives_vector_hnsw: true,
            pgvector_extension: true,
            knowledge_embedding_vector_column: true,
            artifact_embedding_vector_column: true,
            indexed_chunks_approx: 100,
            chunk_vector_count: 75,
            ..KnowledgeSchemaHealth::default()
        };

        assert!(health.bundle_ready());
        assert!(!health.dense_ready(0.80));
        assert_eq!(health.quality_tier(0.80), QualityTier::LexicalGraph);

        let ready = KnowledgeSchemaHealth {
            chunk_vector_count: 90,
            ..health
        };
        assert!(ready.dense_ready(0.80));
        assert_eq!(ready.quality_tier(0.80), QualityTier::HybridDense);
    }

    #[test]
    fn query_embedding_validation_rejects_dimension_mismatch() {
        let envelope = QueryEnvelopePayload {
            query_embedding: vec![0.1, 0.2],
            query_embedding_model: "sentence-transformers/test".to_string(),
            query_embedding_dimension: 3,
            ..QueryEnvelopePayload::default()
        };

        assert!(validate_query_embedding(&envelope).is_err());
    }

    #[test]
    fn dense_candidates_merge_with_lexical_without_losing_scope() {
        let mut lexical = candidate_fixture("shared", "workspace_doc", 0.25);
        lexical.project_key = "KODA".to_string();
        let mut dense = candidate_fixture("shared", "workspace_doc", 0.0);
        dense.lexical_score = 0.0;
        dense.dense_score = 0.94;
        dense.dense_rank = 1;
        let merged = merge_candidate_payloads(vec![lexical], vec![dense]);

        assert_eq!(merged.len(), 1);
        assert_eq!(merged[0].id, "shared");
        assert_eq!(merged[0].project_key, "KODA");
        assert_eq!(merged[0].lexical_score, 0.25);
        assert_eq!(merged[0].dense_score, 0.94);
        assert_eq!(merged[0].dense_rank, 1);
    }

    #[test]
    fn ranking_10k_candidates_stays_bounded_and_deterministic() {
        let envelope = QueryEnvelopePayload {
            normalized_query: "deploy rollback".to_string(),
            project_key: "KODA".to_string(),
            environment: "prod".to_string(),
            team: "platform".to_string(),
            allowed_workspace_roots: vec!["/repo".to_string()],
            ..QueryEnvelopePayload::default()
        };
        let mut candidates = (0..10_000)
            .map(|index| {
                let mut candidate = candidate_fixture(
                    &format!("candidate-{index:05}"),
                    if index % 17 == 0 {
                        "approved_runbook"
                    } else {
                        "observed_pattern"
                    },
                    0.15,
                );
                candidate.updated_at = format!("2026-01-{:02} 00:00:00+00", (index % 28) + 1);
                candidate
            })
            .collect::<Vec<CandidatePayload>>();
        let mut winner = candidate_fixture("winner", "canonical_policy", 1.0);
        winner.dense_score = 0.96;
        winner.dense_rank = 1;
        candidates.push(winner);

        let started = Instant::now();
        let ranked = rank_candidates(candidates, &[], &[], &[], &envelope, "deploy rollback");
        let elapsed = started.elapsed();

        assert_eq!(ranked[0].candidate.id, "winner");
        assert!(ranked[0].score > 0.8);
        assert!(
            elapsed.as_millis() < 2_000,
            "10k in-memory ranking exceeded bounded budget: {elapsed:?}"
        );
    }

    #[test]
    fn ranking_prioritizes_lexical_authoritative_scope_match() {
        let envelope = QueryEnvelopePayload {
            normalized_query: "deploy".to_string(),
            project_key: "KODA".to_string(),
            environment: "prod".to_string(),
            team: "platform".to_string(),
            allowed_workspace_roots: vec!["/repo".to_string()],
            ..QueryEnvelopePayload::default()
        };
        let mut weak = candidate_fixture("weak", "observed_pattern", 0.25);
        weak.updated_at = "2026-02-01 00:00:00+00".to_string();
        let strong = candidate_fixture("strong", "canonical_policy", 1.0);

        let ranked = rank_candidates(vec![weak, strong], &[], &[], &[], &envelope, "deploy");

        assert_eq!(ranked[0].candidate.id, "strong");
        assert!(ranked[0]
            .candidate
            .reasons
            .contains(&"authoritative_layer".to_string()));
        assert_eq!(ranked[0].candidate.dense_rank, -1);
        assert_eq!(ranked[0].candidate.dense_score, 0.0);
    }

    #[test]
    fn write_intent_does_not_make_non_operable_policy_authoritative() {
        let envelope = QueryEnvelopePayload {
            normalized_query: "deploy".to_string(),
            requires_write: true,
            ..QueryEnvelopePayload::default()
        };
        let mut candidate = candidate_fixture("readonly", "canonical_policy", 1.0);
        candidate.operable = false;
        let ranked = rank_candidates(vec![candidate], &[], &[], &[], &envelope, "deploy");
        let authoritative = build_authoritative(&ranked, envelope.requires_write);

        assert!(authoritative.is_empty());
        assert!(ranked[0]
            .candidate
            .reasons
            .contains(&"non_operable_reference".to_string()));
    }

    #[test]
    fn empty_bundle_returns_no_synthetic_authoritative_hits() {
        let response = build_retrieve_response(
            &RetrieveRequest {
                agent_id: "agent-a".to_string(),
                query: "deploy".to_string(),
                limit: 3,
                envelope: Some(RetrieveEnvelope {
                    normalized_query: "deploy".to_string(),
                    ..RetrieveEnvelope::default()
                }),
                ..RetrieveRequest::default()
            },
            "trace-test".to_string(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
        );

        assert!(response.selected_hits.is_empty());
        assert!(response.candidate_hits.is_empty());
        assert!(response.authoritative_evidence.is_empty());
        assert_eq!(response.effective_engine, "rust_grpc");
        assert!(response
            .uncertainty_notes
            .iter()
            .any(|note| note == "no candidate hits returned"));
    }

    #[tokio::test]
    #[ignore = "requires local PostgreSQL; run with KODA_INTEGRATION_TESTS=1 cargo test -p koda-retrieval-engine -- --ignored"]
    async fn retrieve_reads_seeded_postgres_bundle() {
        if std::env::var("KODA_INTEGRATION_TESTS").ok().as_deref() != Some("1") {
            return;
        }
        let dsn = std::env::var("POSTGRES_TEST_DSN")
            .or_else(|_| std::env::var("KNOWLEDGE_V2_POSTGRES_DSN"))
            .expect("POSTGRES_TEST_DSN or KNOWLEDGE_V2_POSTGRES_DSN is required");
        let schema = format!(
            "knowledge_v2_rust_retrieval_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis()
        );
        let (client, connection) = tokio_postgres::connect(&dsn, NoTls).await.expect("connect");
        tokio::spawn(async move {
            let _ = connection.await;
        });
        if client
            .batch_execute("CREATE EXTENSION IF NOT EXISTS vector")
            .await
            .is_err()
        {
            return;
        }
        let schema_ident = quote_ident(&schema);
        client
            .batch_execute(&format!(
                r#"CREATE SCHEMA {schema_ident};
                   CREATE TABLE {schema_ident}."knowledge_chunks" (
                       id BIGSERIAL PRIMARY KEY,
                       agent_id TEXT NOT NULL,
                       chunk_key TEXT NOT NULL,
                       document_key TEXT NOT NULL,
                       source_label TEXT NOT NULL,
                       source_path TEXT NOT NULL,
                       workspace_root TEXT NOT NULL DEFAULT '',
                       layer TEXT NOT NULL,
                       scope TEXT NOT NULL,
                       title TEXT NOT NULL,
                       content TEXT NOT NULL,
                       owner TEXT NOT NULL DEFAULT '',
                       project_key TEXT NOT NULL DEFAULT '',
                       environment TEXT NOT NULL DEFAULT '',
                       team TEXT NOT NULL DEFAULT '',
                       source_type TEXT NOT NULL DEFAULT 'document',
                       operable BOOLEAN NOT NULL DEFAULT TRUE,
                       freshness_days INTEGER NOT NULL DEFAULT 90,
                       tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                       metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                       updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                       search_vector TSVECTOR GENERATED ALWAYS AS (
                           to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, ''))
                       ) STORED
                   );
                   CREATE TABLE {schema_ident}."knowledge_embeddings" (
                       id BIGSERIAL PRIMARY KEY,
                       agent_id TEXT NOT NULL,
                       embedding_key TEXT NOT NULL,
                       chunk_key TEXT NOT NULL,
                       document_key TEXT NOT NULL,
                       model TEXT NOT NULL,
                       vector_json JSONB NOT NULL,
                       payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                       object_key TEXT NOT NULL,
                       embedding_vector VECTOR(2),
                       updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                   );
                   CREATE TABLE {schema_ident}."knowledge_entities" (
                       id BIGSERIAL PRIMARY KEY,
                       agent_id TEXT NOT NULL,
                       entity_key TEXT NOT NULL,
                       entity_type TEXT NOT NULL,
                       label TEXT NOT NULL,
                       source_kind TEXT NOT NULL DEFAULT 'knowledge',
                       metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                       updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                   );
                   CREATE TABLE {schema_ident}."knowledge_relations" (
                       id BIGSERIAL PRIMARY KEY,
                       agent_id TEXT NOT NULL,
                       relation_key TEXT NOT NULL,
                       relation_type TEXT NOT NULL,
                       source_entity_key TEXT NOT NULL,
                       target_entity_key TEXT NOT NULL,
                       weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                       metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                       updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                   );
                   CREATE TABLE {schema_ident}."artifact_derivatives" (
                       id BIGSERIAL PRIMARY KEY,
                       agent_id TEXT NOT NULL,
                       task_id BIGINT,
                       derivative_key TEXT NOT NULL,
                       artifact_id TEXT NOT NULL DEFAULT '',
                       project_key TEXT NOT NULL DEFAULT '',
                       workspace_fingerprint TEXT NOT NULL DEFAULT '',
                       modality TEXT NOT NULL,
                       label TEXT NOT NULL,
                       extracted_text TEXT NOT NULL DEFAULT '',
                       confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                       trust_level TEXT NOT NULL DEFAULT 'untrusted',
                       source_path TEXT NOT NULL DEFAULT '',
                       source_url TEXT NOT NULL DEFAULT '',
                       source_object_key TEXT NOT NULL DEFAULT '',
                       time_span TEXT NOT NULL DEFAULT '',
                       frame_ref TEXT NOT NULL DEFAULT '',
                       provenance_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                       embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                       embedding_vector VECTOR(2),
                       search_vector TSVECTOR GENERATED ALWAYS AS (
                           to_tsvector('simple', coalesce(label, '') || ' ' || coalesce(extracted_text, ''))
                       ) STORED,
                       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                   );
                   CREATE INDEX idx_knowledge_chunks_lookup ON {schema_ident}."knowledge_chunks"
                       (agent_id, project_key, environment, team, updated_at DESC);
                   CREATE INDEX idx_knowledge_chunks_search ON {schema_ident}."knowledge_chunks" USING GIN (search_vector);
                   CREATE INDEX idx_knowledge_embeddings_lookup ON {schema_ident}."knowledge_embeddings"
                       (agent_id, model, updated_at DESC);
                   CREATE INDEX idx_knowledge_entities_lookup ON {schema_ident}."knowledge_entities"
                       (agent_id, entity_type, updated_at DESC);
                   CREATE INDEX idx_knowledge_relations_lookup ON {schema_ident}."knowledge_relations"
                       (agent_id, relation_type, source_entity_key, target_entity_key);
                   CREATE INDEX idx_artifact_derivatives_lookup ON {schema_ident}."artifact_derivatives"
                       (agent_id, task_id, project_key, workspace_fingerprint, created_at DESC);
                   CREATE INDEX idx_artifact_derivatives_search ON {schema_ident}."artifact_derivatives" USING GIN (search_vector);
                   CREATE INDEX idx_knowledge_embeddings_vector_hnsw ON {schema_ident}."knowledge_embeddings"
                       USING hnsw (embedding_vector vector_cosine_ops);
                   CREATE INDEX idx_artifact_derivatives_vector_hnsw ON {schema_ident}."artifact_derivatives"
                       USING hnsw (embedding_vector vector_cosine_ops);"#
            ))
            .await
            .expect("create schema");
        client
            .execute(
                &format!(
                    r#"INSERT INTO {schema_ident}."knowledge_chunks"
                       (agent_id, chunk_key, document_key, source_label, source_path, workspace_root, layer, scope,
                        title, content, owner, project_key, environment, team, source_type, operable, freshness_days,
                        tags_json, metadata_json)
                       VALUES
                       ('AGENT_A', 'chunk-deploy', 'doc-deploy', 'policy:deploy', '/repo/runbooks/deploy.md',
                        '/repo', 'canonical_policy', 'operational_policy', 'Deploy policy',
                        'Use the deploy rollback runbook for production releases.', 'platform', 'KODA', 'prod',
                        'platform', 'document', true, 90, '["deploy"]'::jsonb, '{{}}'::jsonb)"#
                ),
                &[],
            )
            .await
            .expect("insert chunk");
        client
            .execute(
                &format!(
                    r#"INSERT INTO {schema_ident}."knowledge_embeddings"
                       (agent_id, embedding_key, chunk_key, document_key, model, vector_json, payload_json, object_key,
                        embedding_vector)
                       VALUES
                       ('AGENT_A', 'chunk-deploy', 'chunk-deploy', 'doc-deploy',
                        'sentence-transformers/test', '[1.0, 0.0]'::jsonb,
                        '{{"source_label":"policy:deploy"}}'::jsonb, 'obj', '[1.0,0.0]'::vector)"#
                ),
                &[],
            )
            .await
            .expect("insert embedding");
        client
            .execute(
                &format!(
                    r#"INSERT INTO {schema_ident}."artifact_derivatives"
                       (agent_id, derivative_key, project_key, workspace_fingerprint, modality, label, extracted_text,
                        confidence, trust_level, source_path, provenance_json, embedding_vector)
                       VALUES
                       ('AGENT_A', 'artifact-deploy', 'KODA', 'fp-a', 'ocr', 'Deploy screenshot',
                        'Production deploy runbook screenshot', 0.92, 'trusted', '/repo/runbooks/deploy.md',
                        '{{"source_label":"policy:deploy"}}'::jsonb, '[1.0,0.0]'::vector)"#
                ),
                &[],
            )
            .await
            .expect("insert artifact");
        client
            .execute(
                &format!(
                    r#"INSERT INTO {schema_ident}."knowledge_entities"
                       (agent_id, entity_key, entity_type, label, metadata_json)
                       VALUES ('AGENT_A', 'project:koda', 'project', 'koda', '{{}}'::jsonb)"#
                ),
                &[],
            )
            .await
            .expect("insert entity");
        client
            .execute(
                &format!(
                    r#"INSERT INTO {schema_ident}."knowledge_relations"
                       (agent_id, relation_key, relation_type, source_entity_key, target_entity_key, weight, metadata_json)
                       VALUES ('AGENT_A', 'rel-deploy', 'governs', 'project:koda', 'project:koda', 1.0,
                               '{{"source_label":"policy:deploy"}}'::jsonb)"#
                ),
                &[],
            )
            .await
            .expect("insert relation");

        std::env::set_var("KNOWLEDGE_V2_POSTGRES_DSN", dsn);
        std::env::set_var("KNOWLEDGE_V2_POSTGRES_SCHEMA", &schema);
        let response = retrieve_payload(
            &RetrieveRequest {
                agent_id: "AGENT_A".to_string(),
                query: "deploy production runbook".to_string(),
                limit: 3,
                envelope: Some(RetrieveEnvelope {
                    normalized_query: "deploy production runbook".to_string(),
                    project_key: "KODA".to_string(),
                    environment: "prod".to_string(),
                    team: "platform".to_string(),
                    workspace_fingerprint: "fp-a".to_string(),
                    allowed_source_labels: vec!["policy:*".to_string()],
                    allowed_workspace_roots: vec!["/repo".to_string()],
                    query_embedding: vec![1.0, 0.0],
                    query_embedding_model: "sentence-transformers/test".to_string(),
                    query_embedding_dimension: 2,
                    ..RetrieveEnvelope::default()
                }),
                ..RetrieveRequest::default()
            },
            "trace-integration".to_string(),
        )
        .await
        .expect("retrieve");

        assert_eq!(response.effective_engine, "rust_grpc+hybrid_dense");
        assert_eq!(response.selected_hits[0].source_label, "policy:deploy");
        assert!(response.selected_hits[0].dense_score > 0.9);
        assert!(!response.authoritative_evidence.is_empty());
        assert!(!response.supporting_evidence.is_empty());
        assert!(!response.graph_relations.is_empty());

        client
            .batch_execute(&format!("DROP SCHEMA {schema_ident} CASCADE"))
            .await
            .expect("drop schema");
    }
}
