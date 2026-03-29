use anyhow::Result;
use koda_observability::{health_details, init_tracing};
use koda_proto::common::v1::{HealthRequest, HealthResponse};
use koda_proto::memory::v1::memory_engine_service_server::{
    MemoryEngineService, MemoryEngineServiceServer,
};
use koda_proto::memory::v1::{
    ApplyCurationActionRequest, ApplyCurationActionResponse, AuditLogItem, ClusterRequest,
    ClusterResponse, CounterEntry, CurationActionOperation, CurationClusterSummary, CurationItem,
    CurationOverlap, CurationOverview, DeduplicateRequest, DeduplicateResponse, DynamicField,
    DynamicList, DynamicStruct, DynamicValue, FilterOption, GetCurationDetailRequest,
    GetCurationDetailResponse, GetMemoryMapRequest, GetMemoryMapResponse, ListCurationItemsRequest,
    ListCurationItemsResponse, MaintenanceLogItem, MemoryDashboardFilter, MemoryGraphEdge,
    MemoryGraphNode, MemoryMapStats, MemoryMapSummary, MemoryRecordRow, Pagination, RecallContext,
    RecallLogItem, RecallRequest, RecallResponse, RecallResultItem, SessionFilterOption,
    UserFilterOption, UserMemoryCount,
};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashSet};
use tokio::fs;
use tokio::net::UnixListener;
use tokio_postgres::{Client, NoTls, Row};
use tokio_stream::wrappers::UnixListenerStream;
use tonic::transport::Server;
use tonic::{Request, Response, Status};

#[derive(Default)]
struct MemoryServer;

const MEMORY_SELECT_SQL: &str = r#"
    SELECT
        n.id,
        n.user_id,
        n.memory_type,
        n.content,
        COALESCE(n.session_id, '') AS session_id,
        n.agent_id,
        COALESCE(n.origin_kind, '') AS origin_kind,
        COALESCE(n.source_query_id, 0)::BIGINT AS source_query_id,
        COALESCE(n.source_task_id, 0)::BIGINT AS source_task_id,
        COALESCE(n.source_episode_id, 0)::BIGINT AS source_episode_id,
        COALESCE(n.project_key, '') AS project_key,
        COALESCE(n.environment, '') AS environment,
        COALESCE(n.team, '') AS team,
        COALESCE(n.importance, 0)::DOUBLE PRECISION AS importance,
        COALESCE(n.quality_score, 0)::DOUBLE PRECISION AS quality_score,
        COALESCE(n.extraction_confidence, 0)::DOUBLE PRECISION AS extraction_confidence,
        COALESCE(n.embedding_status, '') AS embedding_status,
        COALESCE(n.content_hash, '') AS content_hash,
        COALESCE(n.claim_kind, '') AS claim_kind,
        COALESCE(n.subject, '') AS subject,
        COALESCE(n.decision_source, '') AS decision_source,
        COALESCE(n.evidence_refs_json::text, '[]') AS evidence_refs_json,
        COALESCE(n.applicability_scope_json::text, '{}') AS applicability_scope_json,
        COALESCE(n.valid_until::text, '') AS valid_until,
        COALESCE(n.conflict_key, '') AS conflict_key,
        COALESCE(n.supersedes_memory_id, 0)::BIGINT AS supersedes_memory_id,
        COALESCE(n.memory_status, 'active') AS memory_status,
        COALESCE(n.retention_reason, '') AS retention_reason,
        COALESCE(n.embedding_attempts, 0)::BIGINT AS embedding_attempts,
        COALESCE(n.embedding_last_error, '') AS embedding_last_error,
        COALESCE(n.embedding_retry_at::text, '') AS embedding_retry_at,
        COALESCE(n.access_count, 0)::BIGINT AS access_count,
        COALESCE(n.last_accessed::text, '') AS last_accessed,
        COALESCE(n.last_recalled_at::text, '') AS last_recalled_at,
        COALESCE(n.created_at::text, '') AS created_at,
        COALESCE(n.expires_at::text, '') AS expires_at,
        COALESCE(n.is_active, false) AS is_active,
        COALESCE(n.metadata_json::text, '{}') AS metadata_json,
        COALESCE(n.vector_ref_id, '') AS vector_ref_id,
        COALESCE(
            (
                SELECT LEFT(q.query_text, 240)
                FROM query_history q
                WHERE q.agent_id = n.agent_id
                  AND q.id = n.source_query_id
                LIMIT 1
            ),
            ''
        ) AS source_query_preview
    FROM napkin_log n
"#;

fn memory_postgres_dsn() -> String {
    std::env::var("KNOWLEDGE_V2_POSTGRES_DSN").unwrap_or_default()
}

fn memory_postgres_schema() -> String {
    std::env::var("KNOWLEDGE_V2_POSTGRES_SCHEMA").unwrap_or_else(|_| "knowledge_v2".to_string())
}

async fn memory_postgres_client() -> Result<Client, Status> {
    let dsn = memory_postgres_dsn();
    if dsn.trim().is_empty() {
        return Err(Status::failed_precondition(
            "knowledge postgres dsn is not configured",
        ));
    }
    let schema = memory_postgres_schema();
    let (client, connection) = tokio_postgres::connect(&dsn, NoTls)
        .await
        .map_err(|error| {
            Status::unavailable(format!("failed to connect to memory postgres: {error}"))
        })?;
    tokio::spawn(async move {
        let _ = connection.await;
    });
    client
        .batch_execute(&format!(r#"SET search_path TO "{schema}""#))
        .await
        .map_err(|error| Status::internal(format!("failed to set memory search_path: {error}")))?;
    Ok(client)
}

fn pg_string(row: &Row, column: &str) -> String {
    row.try_get::<_, String>(column)
        .or_else(|_| {
            row.try_get::<_, Option<String>>(column)
                .map(|value| value.unwrap_or_default())
        })
        .unwrap_or_default()
}

fn pg_i64(row: &Row, column: &str) -> i64 {
    row.try_get::<_, i64>(column)
        .or_else(|_| {
            row.try_get::<_, i32>(column)
                .map(i64::from)
                .or_else(|_| {
                    row.try_get::<_, Option<i64>>(column)
                        .map(|value| value.unwrap_or_default())
                })
                .or_else(|_| {
                    row.try_get::<_, Option<i32>>(column)
                        .map(|value| value.map(i64::from).unwrap_or_default())
                })
        })
        .unwrap_or_default()
}

fn pg_f64(row: &Row, column: &str) -> f64 {
    row.try_get::<_, f64>(column)
        .or_else(|_| row.try_get::<_, f32>(column).map(f64::from))
        .or_else(|_| {
            row.try_get::<_, Option<f64>>(column)
                .map(|value| value.unwrap_or_default())
        })
        .or_else(|_| {
            row.try_get::<_, Option<f32>>(column)
                .map(|value| value.map(f64::from).unwrap_or_default())
        })
        .unwrap_or_default()
}

fn pg_bool(row: &Row, column: &str) -> bool {
    row.try_get::<_, bool>(column)
        .or_else(|_| {
            row.try_get::<_, Option<bool>>(column)
                .map(|value| value.unwrap_or(false))
        })
        .unwrap_or(false)
}

fn optional_string_value(value: String) -> Value {
    if value.is_empty() {
        Value::Null
    } else {
        Value::String(value)
    }
}

fn optional_i64_value(value: i64) -> Value {
    if value > 0 {
        json!(value)
    } else {
        Value::Null
    }
}

fn parse_json_value(value: &Value) -> Value {
    match value {
        Value::Null => Value::Null,
        Value::String(raw) if raw.trim().is_empty() => Value::Null,
        Value::String(raw) => {
            serde_json::from_str::<Value>(raw).unwrap_or_else(|_| Value::String(raw.clone()))
        }
        other => other.clone(),
    }
}

fn memory_row_value(row: &Row) -> Value {
    json!({
        "id": pg_i64(row, "id"),
        "user_id": pg_i64(row, "user_id"),
        "memory_type": pg_string(row, "memory_type"),
        "content": pg_string(row, "content"),
        "session_id": pg_string(row, "session_id"),
        "agent_id": pg_string(row, "agent_id"),
        "origin_kind": pg_string(row, "origin_kind"),
        "source_query_id": pg_i64(row, "source_query_id"),
        "source_task_id": pg_i64(row, "source_task_id"),
        "source_episode_id": pg_i64(row, "source_episode_id"),
        "project_key": pg_string(row, "project_key"),
        "environment": pg_string(row, "environment"),
        "team": pg_string(row, "team"),
        "importance": pg_f64(row, "importance"),
        "quality_score": pg_f64(row, "quality_score"),
        "extraction_confidence": pg_f64(row, "extraction_confidence"),
        "embedding_status": pg_string(row, "embedding_status"),
        "content_hash": pg_string(row, "content_hash"),
        "claim_kind": pg_string(row, "claim_kind"),
        "subject": pg_string(row, "subject"),
        "decision_source": pg_string(row, "decision_source"),
        "evidence_refs_json": parse_json_value(&Value::String(pg_string(row, "evidence_refs_json"))),
        "applicability_scope_json": parse_json_value(&Value::String(pg_string(row, "applicability_scope_json"))),
        "valid_until": optional_string_value(pg_string(row, "valid_until")),
        "conflict_key": pg_string(row, "conflict_key"),
        "supersedes_memory_id": optional_i64_value(pg_i64(row, "supersedes_memory_id")),
        "memory_status": pg_string(row, "memory_status"),
        "retention_reason": pg_string(row, "retention_reason"),
        "embedding_attempts": pg_i64(row, "embedding_attempts"),
        "embedding_last_error": pg_string(row, "embedding_last_error"),
        "embedding_retry_at": optional_string_value(pg_string(row, "embedding_retry_at")),
        "access_count": pg_i64(row, "access_count"),
        "last_accessed": optional_string_value(pg_string(row, "last_accessed")),
        "last_recalled_at": optional_string_value(pg_string(row, "last_recalled_at")),
        "created_at": pg_string(row, "created_at"),
        "expires_at": optional_string_value(pg_string(row, "expires_at")),
        "is_active": pg_bool(row, "is_active"),
        "metadata_json": parse_json_value(&Value::String(pg_string(row, "metadata_json"))),
        "vector_ref_id": pg_string(row, "vector_ref_id"),
        "source_query_preview": pg_string(row, "source_query_preview"),
    })
}

fn dashboard_filter_from_request(filter: Option<&MemoryDashboardFilter>) -> Value {
    match filter {
        Some(filter) => dashboard_filter_value(filter),
        None => json!({}),
    }
}

async fn query_memory_rows(
    client: &Client,
    sql: &str,
    params: &[&(dyn tokio_postgres::types::ToSql + Sync)],
) -> Result<Vec<Value>, Status> {
    let rows = client
        .query(sql, params)
        .await
        .map_err(|error| Status::internal(format!("failed to query memory rows: {error}")))?;
    Ok(rows.iter().map(memory_row_value).collect())
}

async fn load_list_curation_payload(agent_id: &str, filters: &Value) -> Result<Value, Status> {
    let client = memory_postgres_client().await?;
    let total_row = client
        .query_one(
            "SELECT COUNT(*)::BIGINT AS total FROM napkin_log WHERE agent_id = $1",
            &[&agent_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query curation total: {error}")))?;
    let rows = query_memory_rows(
        &client,
        &format!(
            "{MEMORY_SELECT_SQL} WHERE n.agent_id = $1 ORDER BY COALESCE(n.last_accessed, n.created_at) DESC, n.id DESC LIMIT 5000"
        ),
        &[&agent_id],
    )
    .await?;
    let cluster_rows = client
        .query(
            "SELECT conflict_key, memory_count::BIGINT AS memory_count, COALESCE(latest_created_at::text, '') AS latest_created_at FROM memory_clusters WHERE agent_id = $1 ORDER BY latest_created_at DESC LIMIT 200",
            &[&agent_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query memory clusters: {error}")))?;
    Ok(json!({
        "agent_id": agent_id,
        "total": pg_i64(&total_row, "total"),
        "rows": rows,
        "all_rows": rows,
        "cluster_rows": cluster_rows.iter().map(|row| json!({
            "cluster_id": pg_string(row, "conflict_key"),
            "summary": pg_string(row, "conflict_key"),
            "memory_count": pg_i64(row, "memory_count"),
            "latest_created_at": optional_string_value(pg_string(row, "latest_created_at")),
        })).collect::<Vec<Value>>(),
        "filters": filters.clone(),
    }))
}

async fn load_memory_map_payload(agent_id: &str, filters: &Value) -> Result<Value, Status> {
    let client = memory_postgres_client().await?;
    let summary_row = client
        .query_one(
            r#"
            SELECT
                COUNT(*)::BIGINT AS total_memories,
                SUM(CASE WHEN is_active = true THEN 1 ELSE 0 END)::BIGINT AS active_memories,
                SUM(CASE WHEN COALESCE(memory_status, 'active') = 'superseded' THEN 1 ELSE 0 END)::BIGINT AS superseded_memories,
                SUM(CASE WHEN COALESCE(memory_status, 'active') = 'stale' THEN 1 ELSE 0 END)::BIGINT AS stale_memories,
                SUM(CASE WHEN COALESCE(memory_status, 'active') = 'invalidated' THEN 1 ELSE 0 END)::BIGINT AS invalidated_memories
            FROM napkin_log
            WHERE agent_id = $1
            "#,
            &[&agent_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query memory summary: {error}")))?;
    let type_rows = client
        .query(
            "SELECT memory_type, memory_count::BIGINT AS memory_count FROM memory_type_counts WHERE agent_id = $1",
            &[&agent_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query memory type counts: {error}")))?;
    let user_rows = client
        .query(
            "SELECT user_id::BIGINT AS user_id, memory_count::BIGINT AS memory_count, active_count::BIGINT AS active_count FROM memory_user_counts WHERE agent_id = $1",
            &[&agent_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query memory user counts: {error}")))?;
    let embedding_rows = client
        .query(
            "SELECT status, job_count::BIGINT AS job_count FROM memory_embedding_job_counts WHERE agent_id = $1",
            &[&agent_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query memory embedding jobs: {error}")))?;
    let quality_rows = client
        .query(
            "SELECT counter_key, counter_value::BIGINT AS counter_value, COALESCE(updated_at::text, '') AS updated_at FROM memory_quality_counters WHERE agent_id = $1",
            &[&agent_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query memory quality counters: {error}")))?;
    let cluster_rows = client
        .query(
            "SELECT conflict_key, memory_count::BIGINT AS memory_count, COALESCE(latest_created_at::text, '') AS latest_created_at FROM memory_clusters WHERE agent_id = $1",
            &[&agent_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query memory clusters: {error}")))?;
    let rows = query_memory_rows(
        &client,
        &format!(
            "{MEMORY_SELECT_SQL} WHERE n.agent_id = $1 ORDER BY COALESCE(n.last_accessed, n.created_at) DESC, n.id DESC LIMIT 1200"
        ),
        &[&agent_id],
    )
    .await?;
    let recent_recall = client
        .query(
            r#"
            SELECT id::BIGINT AS id, user_id::BIGINT AS user_id, task_id::BIGINT AS task_id, query_preview,
                   trust_score, total_considered::BIGINT AS total_considered, total_selected::BIGINT AS total_selected,
                   total_discarded::BIGINT AS total_discarded, conflict_group_count::BIGINT AS conflict_group_count,
                   selected_layers_csv, retrieval_sources_csv, COALESCE(created_at::text, '') AS created_at
            FROM memory_recall_log
            WHERE agent_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT 12
            "#,
            &[&agent_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query recent memory recall: {error}")))?;
    let maintenance_rows = client
        .query(
            r#"
            SELECT operation, memories_affected::BIGINT AS memories_affected, details, COALESCE(executed_at::text, '') AS executed_at
            FROM memory_maintenance_log
            WHERE agent_id = $1
            ORDER BY executed_at DESC
            LIMIT 12
            "#,
            &[&agent_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query memory maintenance log: {error}")))?;
    Ok(json!({
        "agent_id": agent_id,
        "summary_row": {
            "total_memories": pg_i64(&summary_row, "total_memories"),
            "active_memories": pg_i64(&summary_row, "active_memories"),
            "superseded_memories": pg_i64(&summary_row, "superseded_memories"),
            "stale_memories": pg_i64(&summary_row, "stale_memories"),
            "invalidated_memories": pg_i64(&summary_row, "invalidated_memories"),
        },
        "type_rows": type_rows.iter().map(|row| json!({
            "memory_type": pg_string(row, "memory_type"),
            "memory_count": pg_i64(row, "memory_count"),
        })).collect::<Vec<Value>>(),
        "user_rows": user_rows.iter().map(|row| json!({
            "user_id": pg_i64(row, "user_id"),
            "memory_count": pg_i64(row, "memory_count"),
            "active_count": pg_i64(row, "active_count"),
        })).collect::<Vec<Value>>(),
        "embedding_rows": embedding_rows.iter().map(|row| json!({
            "status": pg_string(row, "status"),
            "job_count": pg_i64(row, "job_count"),
        })).collect::<Vec<Value>>(),
        "quality_rows": quality_rows.iter().map(|row| json!({
            "counter_key": pg_string(row, "counter_key"),
            "counter_value": pg_i64(row, "counter_value"),
            "updated_at": optional_string_value(pg_string(row, "updated_at")),
        })).collect::<Vec<Value>>(),
        "cluster_rows": cluster_rows.iter().map(|row| json!({
            "cluster_id": pg_string(row, "conflict_key"),
            "memory_count": pg_i64(row, "memory_count"),
            "latest_created_at": optional_string_value(pg_string(row, "latest_created_at")),
        })).collect::<Vec<Value>>(),
        "rows": rows,
        "recent_recall": recent_recall.iter().map(|row| json!({
            "id": pg_i64(row, "id"),
            "user_id": pg_i64(row, "user_id"),
            "task_id": pg_i64(row, "task_id"),
            "query_preview": pg_string(row, "query_preview"),
            "trust_score": pg_f64(row, "trust_score"),
            "total_considered": pg_i64(row, "total_considered"),
            "total_selected": pg_i64(row, "total_selected"),
            "total_discarded": pg_i64(row, "total_discarded"),
            "conflict_group_count": pg_i64(row, "conflict_group_count"),
            "selected_layers_csv": pg_string(row, "selected_layers_csv"),
            "retrieval_sources_csv": pg_string(row, "retrieval_sources_csv"),
            "created_at": pg_string(row, "created_at"),
        })).collect::<Vec<Value>>(),
        "maintenance_rows": maintenance_rows.iter().map(|row| json!({
            "operation": pg_string(row, "operation"),
            "memories_affected": pg_i64(row, "memories_affected"),
            "details": pg_string(row, "details"),
            "executed_at": pg_string(row, "executed_at"),
        })).collect::<Vec<Value>>(),
        "filters": filters.clone(),
    }))
}

async fn load_curation_detail_payload(
    agent_id: &str,
    subject_id: &str,
    detail_kind: &str,
    cluster_id: &str,
) -> Result<Value, Status> {
    let client = memory_postgres_client().await?;
    if detail_kind.eq_ignore_ascii_case("cluster") {
        let effective_cluster_id = if cluster_id.trim().is_empty() {
            subject_id.trim()
        } else {
            cluster_id.trim()
        };
        let cluster_rows = query_memory_rows(
            &client,
            &format!(
                "{MEMORY_SELECT_SQL} WHERE n.agent_id = $1 AND COALESCE(n.conflict_key, '') = $2 ORDER BY n.created_at DESC, n.id DESC LIMIT 200"
            ),
            &[&agent_id, &effective_cluster_id],
        )
        .await?;
        if cluster_rows.is_empty() {
            return Err(Status::not_found("memory cluster not found"));
        }
        let recent_audits = client
            .query(
                r#"
                SELECT id::BIGINT AS id, task_id::BIGINT AS task_id, query_preview,
                       trust_score, considered_json::text AS considered_json, selected_json::text AS selected_json,
                       discarded_json::text AS discarded_json, conflicts_json::text AS conflicts_json,
                       explanations_json::text AS explanations_json, COALESCE(created_at::text, '') AS created_at,
                       COALESCE(timestamp::text, '') AS timestamp, details_json::text AS details_json
                FROM audit_events
                WHERE agent_id = $1 AND event_type = 'memory.curation.action'
                ORDER BY id DESC
                LIMIT 200
                "#,
                &[&agent_id],
            )
            .await
            .map_err(|error| Status::internal(format!("failed to query memory audit events: {error}")))?;
        return Ok(json!({
            "agent_id": agent_id,
            "detail_kind": "cluster",
            "cluster_id": effective_cluster_id,
            "cluster_rows": cluster_rows,
            "recent_audits": recent_audits.iter().map(|row| json!({
                "id": pg_i64(row, "id"),
                "task_id": pg_i64(row, "task_id"),
                "query_preview": pg_string(row, "query_preview"),
                "trust_score": pg_f64(row, "trust_score"),
                "considered_json": pg_string(row, "considered_json"),
                "selected_json": pg_string(row, "selected_json"),
                "discarded_json": pg_string(row, "discarded_json"),
                "conflicts_json": pg_string(row, "conflicts_json"),
                "explanations_json": pg_string(row, "explanations_json"),
                "created_at": pg_string(row, "created_at"),
                "timestamp": pg_string(row, "timestamp"),
                "details_json": pg_string(row, "details_json"),
            })).collect::<Vec<Value>>(),
        }));
    }

    let memory_id = subject_id
        .trim()
        .parse::<i64>()
        .map_err(|_| Status::invalid_argument("memory subject_id must be numeric"))?;
    let row = query_memory_rows(
        &client,
        &format!("{MEMORY_SELECT_SQL} WHERE n.id = $1 AND n.agent_id = $2"),
        &[&memory_id, &agent_id],
    )
    .await?
    .into_iter()
    .next()
    .ok_or_else(|| Status::not_found("memory not found"))?;
    let session_id = row
        .get("session_id")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let resolved_cluster_id = row
        .get("conflict_key")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let cluster_rows = if resolved_cluster_id.is_empty() {
        Vec::new()
    } else {
        query_memory_rows(
            &client,
            &format!(
                "{MEMORY_SELECT_SQL} WHERE n.agent_id = $1 AND COALESCE(n.conflict_key, '') = $2 ORDER BY n.created_at DESC, n.id DESC LIMIT 200"
            ),
            &[&agent_id, &resolved_cluster_id],
        )
        .await?
    };
    let related_rows = query_memory_rows(
        &client,
        &format!(
            "{MEMORY_SELECT_SQL} WHERE n.agent_id = $1 AND n.id <> $2 AND COALESCE(n.session_id, '') = COALESCE($3, '') ORDER BY COALESCE(n.last_accessed, n.created_at) DESC, n.id DESC LIMIT 12"
        ),
        &[&agent_id, &memory_id, &session_id],
    )
    .await?;
    let recent_audits = client
        .query(
            r#"
            SELECT id::BIGINT AS id, task_id::BIGINT AS task_id, query_preview,
                   trust_score, considered_json::text AS considered_json, selected_json::text AS selected_json,
                   discarded_json::text AS discarded_json, conflicts_json::text AS conflicts_json,
                   explanations_json::text AS explanations_json, COALESCE(created_at::text, '') AS created_at
            FROM memory_recall_log
            WHERE agent_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT 12
            "#,
            &[&agent_id],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query memory recall audits: {error}")))?;
    Ok(json!({
        "agent_id": agent_id,
        "detail_kind": "memory",
        "row": row,
        "cluster_id": if resolved_cluster_id.is_empty() { Value::Null } else { Value::String(resolved_cluster_id) },
        "cluster_rows": cluster_rows,
        "related_rows": related_rows,
        "recent_audits": recent_audits.iter().map(|audit_row| json!({
            "id": pg_i64(audit_row, "id"),
            "task_id": pg_i64(audit_row, "task_id"),
            "query_preview": pg_string(audit_row, "query_preview"),
            "trust_score": pg_f64(audit_row, "trust_score"),
            "considered_json": pg_string(audit_row, "considered_json"),
            "selected_json": pg_string(audit_row, "selected_json"),
            "discarded_json": pg_string(audit_row, "discarded_json"),
            "conflicts_json": pg_string(audit_row, "conflicts_json"),
            "explanations_json": pg_string(audit_row, "explanations_json"),
            "created_at": pg_string(audit_row, "created_at"),
        })).collect::<Vec<Value>>(),
    }))
}

async fn execute_action_plan(agent_id: &str, action_json: &Value) -> Result<(i64, Vec<i64>), Status> {
    let operations = action_json
        .get("operations")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let client = memory_postgres_client().await?;
    let mut updated_count = 0_i64;
    let mut affected_ids = Vec::<i64>::new();
    for operation in operations {
        match operation
            .get("op")
            .and_then(Value::as_str)
            .unwrap_or_default()
        {
            "batch_deactivate" => {
                let ids = payload_i64_list(&operation, "memory_ids");
                if ids.is_empty() {
                    continue;
                }
                let updated = client
                    .execute(
                        "UPDATE napkin_log SET is_active = false WHERE agent_id = $1 AND id = ANY($2::BIGINT[]) AND is_active = true",
                        &[&agent_id, &ids],
                    )
                    .await
                    .map_err(|error| Status::internal(format!("failed to batch deactivate memories: {error}")))?;
                updated_count += updated as i64;
                affected_ids.extend(ids);
            }
            "set_status" => {
                let memory_id = operation
                    .get("memory_id")
                    .and_then(Value::as_i64)
                    .unwrap_or_default();
                if memory_id <= 0 {
                    continue;
                }
                let memory_status = value_string(operation.get("memory_status"));
                let duplicate_of_memory_id = operation
                    .get("duplicate_of_memory_id")
                    .and_then(Value::as_i64)
                    .filter(|value| *value > 0);
                let updated = client
                    .execute(
                        "UPDATE napkin_log SET memory_status = $1, supersedes_memory_id = COALESCE($2, supersedes_memory_id) WHERE agent_id = $3 AND id = $4",
                        &[&memory_status, &duplicate_of_memory_id, &agent_id, &memory_id],
                    )
                    .await
                    .map_err(|error| Status::internal(format!("failed to set memory status: {error}")))?;
                updated_count += updated as i64;
                affected_ids.push(memory_id);
            }
            "review_state" => {
                let memory_id = operation
                    .get("memory_id")
                    .and_then(Value::as_i64)
                    .unwrap_or_default();
                if memory_id <= 0 {
                    continue;
                }
                let current = client
                    .query_opt(
                        "SELECT COALESCE(metadata_json::text, '{}') AS metadata_json FROM napkin_log WHERE agent_id = $1 AND id = $2",
                        &[&agent_id, &memory_id],
                    )
                    .await
                    .map_err(|error| Status::internal(format!("failed to load memory metadata: {error}")))?;
                let Some(current_row) = current else {
                    continue;
                };
                let mut metadata =
                    parse_json_value(&Value::String(pg_string(&current_row, "metadata_json")));
                if !metadata.is_object() {
                    metadata = json!({});
                }
                if let Some(map) = metadata.as_object_mut() {
                    let review_status = value_string(operation.get("review_status"));
                    map.insert(
                        "review_status".to_string(),
                        Value::String(review_status.clone()),
                    );
                    map.insert(
                        "review_reason".to_string(),
                        operation.get("reason").cloned().unwrap_or(Value::Null),
                    );
                    if let Some(duplicate) = operation
                        .get("duplicate_of_memory_id")
                        .and_then(Value::as_i64)
                        .filter(|value| *value > 0)
                    {
                        map.insert("duplicate_of_memory_id".to_string(), json!(duplicate));
                    } else if review_status != "merged" {
                        map.remove("duplicate_of_memory_id");
                    }
                }
                let memory_status = value_string(operation.get("memory_status"));
                let is_active = value_bool(operation.get("is_active"));
                let duplicate_of_memory_id = operation
                    .get("duplicate_of_memory_id")
                    .and_then(Value::as_i64)
                    .filter(|value| *value > 0);
                let expires_now = value_bool(operation.get("expires_now"));
                let updated = client
                    .execute(
                        r#"
                        UPDATE napkin_log
                        SET metadata_json = $1::jsonb,
                            memory_status = $2,
                            is_active = $3,
                            supersedes_memory_id = $4,
                            expires_at = CASE WHEN $5 THEN NOW() ELSE expires_at END
                        WHERE agent_id = $6 AND id = $7
                        "#,
                        &[
                            &metadata.to_string(),
                            &memory_status,
                            &is_active,
                            &duplicate_of_memory_id,
                            &expires_now,
                            &agent_id,
                            &memory_id,
                        ],
                    )
                    .await
                    .map_err(|error| {
                        Status::internal(format!("failed to persist review state: {error}"))
                    })?;
                updated_count += updated as i64;
                affected_ids.push(memory_id);
            }
            unsupported => {
                return Err(Status::invalid_argument(format!(
                    "unsupported memory action operation: {unsupported}"
                )));
            }
        }
    }
    affected_ids.sort_unstable();
    affected_ids.dedup();
    Ok((updated_count, affected_ids))
}

fn tokenize(value: &str) -> HashSet<String> {
    value
        .split(|ch: char| !ch.is_ascii_alphanumeric())
        .filter_map(|token| {
            let normalized = token.trim().to_ascii_lowercase();
            if normalized.len() >= 2 {
                Some(normalized)
            } else {
                None
            }
        })
        .collect()
}

fn overlap_score(query_tokens: &HashSet<String>, content: &str) -> f64 {
    if query_tokens.is_empty() {
        return 0.0;
    }
    let candidate_tokens = tokenize(content);
    if candidate_tokens.is_empty() {
        return 0.0;
    }
    let overlap = query_tokens.intersection(&candidate_tokens).count() as f64;
    overlap / (query_tokens.len() as f64)
}

fn clamp_score(score: f64) -> f64 {
    score.clamp(0.0, 1.0)
}

fn json_from_dynamic_value(value: Option<&DynamicValue>) -> Value {
    match value.and_then(|item| item.kind.as_ref()) {
        Some(koda_proto::memory::v1::dynamic_value::Kind::NullValue(_)) => Value::Null,
        Some(koda_proto::memory::v1::dynamic_value::Kind::BoolValue(raw)) => Value::Bool(*raw),
        Some(koda_proto::memory::v1::dynamic_value::Kind::NumberValue(raw)) => {
            serde_json::Number::from_f64(*raw)
                .map(Value::Number)
                .unwrap_or(Value::Null)
        }
        Some(koda_proto::memory::v1::dynamic_value::Kind::StringValue(raw)) => {
            Value::String(raw.clone())
        }
        Some(koda_proto::memory::v1::dynamic_value::Kind::StructValue(raw)) => {
            json_from_dynamic_struct(Some(raw))
        }
        Some(koda_proto::memory::v1::dynamic_value::Kind::ListValue(raw)) => Value::Array(
            raw.items
                .iter()
                .map(|item| json_from_dynamic_value(Some(item)))
                .collect(),
        ),
        None => Value::Null,
    }
}

fn json_from_dynamic_struct(value: Option<&DynamicStruct>) -> Value {
    let mut payload = serde_json::Map::new();
    if let Some(struct_value) = value {
        for field in &struct_value.fields {
            if field.key.trim().is_empty() {
                continue;
            }
            payload.insert(
                field.key.clone(),
                json_from_dynamic_value(field.value.as_ref()),
            );
        }
    }
    Value::Object(payload)
}

fn dynamic_value_from_json(value: &Value) -> DynamicValue {
    let kind = match value {
        Value::Null => koda_proto::memory::v1::dynamic_value::Kind::NullValue(true),
        Value::Bool(raw) => koda_proto::memory::v1::dynamic_value::Kind::BoolValue(*raw),
        Value::Number(raw) => koda_proto::memory::v1::dynamic_value::Kind::NumberValue(
            raw.as_f64().unwrap_or_default(),
        ),
        Value::String(raw) => koda_proto::memory::v1::dynamic_value::Kind::StringValue(raw.clone()),
        Value::Array(items) => {
            koda_proto::memory::v1::dynamic_value::Kind::ListValue(DynamicList {
                items: items.iter().map(dynamic_value_from_json).collect(),
            })
        }
        Value::Object(_) => koda_proto::memory::v1::dynamic_value::Kind::StructValue(
            dynamic_struct_from_json(value),
        ),
    };
    DynamicValue { kind: Some(kind) }
}

fn dynamic_struct_from_json(value: &Value) -> DynamicStruct {
    let fields = value
        .as_object()
        .map(|items| {
            items
                .iter()
                .map(|(key, value)| DynamicField {
                    key: key.clone(),
                    value: Some(dynamic_value_from_json(value)),
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    DynamicStruct { fields }
}

async fn load_recall_rows(
    agent_id: &str,
    limit: u32,
    context: Option<&RecallContext>,
) -> Result<Vec<Value>, Status> {
    let client = memory_postgres_client().await?;
    let user_id = context.map(|item| item.user_id).unwrap_or_default();
    let memory_types = context
        .map(|item| item.memory_types.clone())
        .unwrap_or_default();
    let project_key = context
        .map(|item| item.project_key.trim().to_string())
        .unwrap_or_default();
    let environment = context
        .map(|item| item.environment.trim().to_string())
        .unwrap_or_default();
    let team = context
        .map(|item| item.team.trim().to_string())
        .unwrap_or_default();
    let origin_kinds = context
        .map(|item| item.origin_kinds.clone())
        .unwrap_or_default();
    let session_id = context
        .map(|item| item.session_id.trim().to_string())
        .unwrap_or_default();
    let source_query_id = context.map(|item| item.source_query_id).unwrap_or_default();
    let source_task_id = context.map(|item| item.source_task_id).unwrap_or_default();
    let source_episode_id = context
        .map(|item| item.source_episode_id)
        .unwrap_or_default();
    let mut memory_statuses = context
        .map(|item| item.memory_statuses.clone())
        .unwrap_or_default();
    if memory_statuses.is_empty() {
        memory_statuses.push("active".to_string());
    }
    let scan_limit = i64::from(limit.max(1)).saturating_mul(8).clamp(40, 400);
    query_memory_rows(
        &client,
        &format!(
            r#"
            {MEMORY_SELECT_SQL}
            WHERE n.agent_id = $1
              AND ($2::BIGINT = 0 OR n.user_id = $2)
              AND (CARDINALITY($3::TEXT[]) = 0 OR n.memory_type = ANY($3::TEXT[]))
              AND ($4::TEXT = '' OR COALESCE(n.project_key, '') = $4 OR COALESCE(n.project_key, '') = '')
              AND ($5::TEXT = '' OR COALESCE(n.environment, '') = $5 OR COALESCE(n.environment, '') = '')
              AND ($6::TEXT = '' OR COALESCE(n.team, '') = $6 OR COALESCE(n.team, '') = '')
              AND (CARDINALITY($7::TEXT[]) = 0 OR COALESCE(n.origin_kind, '') = ANY($7::TEXT[]))
              AND ($8::TEXT = '' OR COALESCE(n.session_id, '') = $8 OR COALESCE(n.session_id, '') = '')
              AND ($9::BIGINT = 0 OR COALESCE(n.source_query_id, 0) = $9)
              AND ($10::BIGINT = 0 OR COALESCE(n.source_task_id, 0) = $10)
              AND ($11::BIGINT = 0 OR COALESCE(n.source_episode_id, 0) = $11)
              AND (CARDINALITY($12::TEXT[]) = 0 OR COALESCE(n.memory_status, 'active') = ANY($12::TEXT[]))
              AND COALESCE(n.is_active, false) = true
            ORDER BY COALESCE(n.last_accessed, n.created_at) DESC, n.id DESC
            LIMIT {scan_limit}
            "#
        ),
        &[
            &agent_id,
            &user_id,
            &memory_types,
            &project_key,
            &environment,
            &team,
            &origin_kinds,
            &session_id,
            &source_query_id,
            &source_task_id,
            &source_episode_id,
            &memory_statuses,
        ],
    )
    .await
}

fn infer_recall_source(row: &Value, context: Option<&RecallContext>) -> String {
    let session_filter = context
        .map(|item| item.session_id.trim().to_string())
        .unwrap_or_default();
    let source_query_filter = context.map(|item| item.source_query_id).unwrap_or_default();
    let source_task_filter = context.map(|item| item.source_task_id).unwrap_or_default();
    let source_episode_filter = context
        .map(|item| item.source_episode_id)
        .unwrap_or_default();
    if source_task_filter > 0 && row_i64(row, "source_task_id") == source_task_filter {
        return "task_link".to_string();
    }
    if source_query_filter > 0 && row_i64(row, "source_query_id") == source_query_filter {
        return "query".to_string();
    }
    if source_episode_filter > 0 && row_i64(row, "source_episode_id") == source_episode_filter {
        return "episode".to_string();
    }
    if !session_filter.is_empty() && row_text(row, "session_id") == session_filter {
        return "session".to_string();
    }
    "lexical".to_string()
}

fn infer_recall_layer(row: &Value) -> String {
    if row_text(row, "memory_type").eq_ignore_ascii_case("procedure") {
        return "procedural".to_string();
    }
    if row_i64(row, "source_episode_id") > 0 {
        return "episodic".to_string();
    }
    "conversational".to_string()
}

fn request_rows(rows: &[koda_proto::memory::v1::MemoryRecordRow]) -> Vec<Value> {
    rows.iter()
        .map(|row| {
            json!({
                "id": row.id,
                "content_hash": row.content_hash,
                "conflict_key": row.conflict_key,
                "quality_score": row.quality_score,
                "importance": row.importance,
                "created_at": row.created_at,
                "agent_id": row.agent_id,
                "memory_type": row.memory_type,
                "subject": row.subject,
                "content": row.content,
                "session_id": row.session_id,
                "user_id": row.user_id,
                "origin_kind": row.origin_kind,
                "source_query_id": row.source_query_id,
                "source_task_id": row.source_task_id,
                "source_episode_id": row.source_episode_id,
                "project_key": row.project_key,
                "environment": row.environment,
                "team": row.team,
                "extraction_confidence": row.extraction_confidence,
                "embedding_status": row.embedding_status,
                "claim_kind": row.claim_kind,
                "decision_source": row.decision_source,
                "evidence_refs": json_from_dynamic_value(row.evidence_refs.as_ref()),
                "applicability_scope": json_from_dynamic_value(row.applicability_scope.as_ref()),
                "valid_until": row.valid_until,
                "supersedes_memory_id": if row.supersedes_memory_id > 0 { json!(row.supersedes_memory_id) } else { Value::Null },
                "memory_status": row.memory_status,
                "retention_reason": row.retention_reason,
                "embedding_attempts": row.embedding_attempts,
                "embedding_last_error": row.embedding_last_error,
                "embedding_retry_at": row.embedding_retry_at,
                "access_count": row.access_count,
                "last_accessed": row.last_accessed,
                "last_recalled_at": row.last_recalled_at,
                "expires_at": row.expires_at,
                "is_active": row.is_active,
                "metadata": json_from_dynamic_struct(row.metadata.as_ref()),
                "vector_ref_id": row.vector_ref_id,
                "source_query_preview": row.source_query_preview,
            })
        })
        .collect()
}

fn dashboard_filter_value(filter: &MemoryDashboardFilter) -> Value {
    let mut payload = serde_json::Map::new();
    if filter.user_id > 0 {
        payload.insert("user_id".to_string(), json!(filter.user_id));
    }
    if !filter.session_id.trim().is_empty() {
        payload.insert("session_id".to_string(), json!(filter.session_id));
    }
    if filter.days > 0 {
        payload.insert("days".to_string(), json!(filter.days));
    }
    if filter.include_inactive {
        payload.insert("include_inactive".to_string(), Value::Bool(true));
    }
    if filter.limit > 0 {
        payload.insert("limit".to_string(), json!(filter.limit));
    }
    if filter.offset > 0 {
        payload.insert("offset".to_string(), json!(filter.offset));
    }
    for (key, value) in [
        ("review_status", filter.review_status.as_str()),
        ("memory_status", filter.memory_status.as_str()),
        ("memory_type", filter.memory_type.as_str()),
        ("query", filter.query.as_str()),
        ("cluster_id", filter.cluster_id.as_str()),
        ("origin_kind", filter.origin_kind.as_str()),
        ("kind", filter.kind.as_str()),
    ] {
        if !value.trim().is_empty() {
            payload.insert(key.to_string(), Value::String(value.to_string()));
        }
    }
    if filter.has_is_active {
        payload.insert("is_active".to_string(), Value::Bool(filter.is_active));
    }
    Value::Object(payload)
}

fn row_text(row: &Value, field: &str) -> String {
    row.get(field)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

fn row_f64(row: &Value, field: &str) -> f64 {
    row.get(field).and_then(Value::as_f64).unwrap_or_default()
}

fn row_i64(row: &Value, field: &str) -> i64 {
    row.get(field).and_then(Value::as_i64).unwrap_or_default()
}

fn row_bool(row: &Value, field: &str) -> bool {
    match row.get(field) {
        Some(Value::Bool(value)) => *value,
        Some(Value::Number(value)) => value.as_i64().unwrap_or_default() != 0,
        Some(Value::String(value)) => matches!(
            value.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes"
        ),
        _ => false,
    }
}

fn compressed(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .trim()
        .to_string()
}

fn clip_text(raw_value: &str, limit: usize) -> Option<String> {
    let text = compressed(raw_value);
    if text.is_empty() {
        return None;
    }
    if text.chars().count() <= limit {
        return Some(text);
    }
    let mut clipped = text
        .chars()
        .take(limit.saturating_sub(1))
        .collect::<String>();
    clipped = clipped.trim_end().to_string();
    clipped.push('…');
    Some(clipped)
}

fn row_metadata(row: &Value) -> Value {
    let parsed = row.get("metadata").cloned().unwrap_or_else(|| json!({}));
    if parsed.is_object() {
        parsed
    } else {
        json!({})
    }
}

fn review_status(row: &Value) -> String {
    let metadata = row_metadata(row);
    let explicit = metadata
        .get("review_status")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();
    if matches!(
        explicit.as_str(),
        "pending" | "approved" | "merged" | "discarded" | "expired" | "archived"
    ) {
        return explicit;
    }
    match row_text(row, "memory_status").to_ascii_lowercase().as_str() {
        "superseded" => "merged".to_string(),
        "stale" => "expired".to_string(),
        "rejected" => "discarded".to_string(),
        "invalidated" => "archived".to_string(),
        _ => "pending".to_string(),
    }
}

fn review_reason(row: &Value) -> Value {
    let metadata = row_metadata(row);
    match metadata
        .get("review_reason")
        .and_then(Value::as_str)
        .and_then(|value| clip_text(value, 400))
    {
        Some(value) => Value::String(value),
        None => Value::Null,
    }
}

fn duplicate_of_memory_id(row: &Value) -> Value {
    let metadata = row_metadata(row);
    if let Some(explicit) = metadata
        .get("duplicate_of_memory_id")
        .and_then(Value::as_i64)
    {
        if explicit > 0 {
            return json!(explicit);
        }
    }
    let supersedes = row_i64(row, "supersedes_memory_id");
    if supersedes > 0 {
        json!(supersedes)
    } else {
        Value::Null
    }
}

fn memory_title(row: &Value) -> String {
    if let Some(subject) = clip_text(&row_text(row, "subject"), 82) {
        return subject;
    }
    clip_text(&row_text(row, "content"), 82).unwrap_or_else(|| "Memória sem conteúdo".to_string())
}

fn memory_review_item(row: &Value) -> Value {
    let source_query_id = row_i64(row, "source_query_id");
    let cluster_id = row_text(row, "conflict_key");
    let semantic_strength = row_f64(row, "quality_score");
    let memory_type = {
        let kind = row_text(row, "memory_type");
        if kind.is_empty() {
            "fact".to_string()
        } else {
            kind
        }
    };
    let session_id = {
        let value = row_text(row, "session_id");
        if value.is_empty() {
            Value::Null
        } else {
            Value::String(value)
        }
    };
    let memory_status = {
        let status = row_text(row, "memory_status").to_ascii_lowercase();
        if status.is_empty() {
            "active".to_string()
        } else {
            status
        }
    };
    json!({
        "agent_id": row_text(row, "agent_id"),
        "id": row_i64(row, "id"),
        "memory_id": row_i64(row, "id"),
        "memory_type": memory_type,
        "title": memory_title(row),
        "content": row_text(row, "content"),
        "source_query_id": if source_query_id > 0 { json!(source_query_id) } else { Value::Null },
        "source_query_preview": row.get("source_query_preview").cloned().unwrap_or(Value::Null),
        "session_id": session_id,
        "user_id": row_i64(row, "user_id"),
        "importance": row_f64(row, "importance"),
        "access_count": row_i64(row, "access_count"),
        "created_at": row.get("created_at").cloned().unwrap_or(Value::Null),
        "last_accessed": row.get("last_accessed").cloned().unwrap_or(Value::Null),
        "expires_at": row.get("expires_at").cloned().unwrap_or(Value::Null),
        "review_status": review_status(row),
        "review_reason": review_reason(row),
        "duplicate_of_memory_id": duplicate_of_memory_id(row),
        "cluster_id": if cluster_id.is_empty() { Value::Null } else { Value::String(cluster_id) },
        "semantic_strength": if semantic_strength > 0.0 { json!(semantic_strength) } else { Value::Null },
        "memory_status": memory_status,
        "metadata": row_metadata(row),
        "is_active": row_bool(row, "is_active"),
    })
}

fn cluster_review_item(cluster_id: &str, rows: &[&Value]) -> Value {
    let mut review_counts: BTreeMap<String, usize> = BTreeMap::new();
    let mut type_counts: BTreeMap<String, usize> = BTreeMap::new();
    for row in rows {
        *review_counts.entry(review_status(row)).or_default() += 1;
        *type_counts
            .entry({
                let kind = row_text(row, "memory_type");
                if kind.is_empty() {
                    "fact".to_string()
                } else {
                    kind
                }
            })
            .or_default() += 1;
    }
    let dominant_type = type_counts
        .into_iter()
        .max_by_key(|(_, count)| *count)
        .map(|(kind, _)| kind)
        .unwrap_or_else(|| "fact".to_string());
    let representative = rows
        .iter()
        .max_by(|left, right| {
            let left_score = row_f64(left, "quality_score") + row_f64(left, "importance");
            let right_score = row_f64(right, "quality_score") + row_f64(right, "importance");
            left_score.total_cmp(&right_score)
        })
        .copied()
        .unwrap_or(&Value::Null);
    let session_ids: HashSet<String> = rows
        .iter()
        .map(|row| row_text(row, "session_id"))
        .filter(|value| !value.is_empty())
        .collect();
    let member_ids: Vec<i64> = rows
        .iter()
        .map(|row| row_i64(row, "id"))
        .filter(|value| *value > 0)
        .collect();
    let review_status_value = if review_counts.len() == 1 {
        review_counts
            .keys()
            .next()
            .cloned()
            .unwrap_or_else(|| "pending".to_string())
    } else {
        "pending".to_string()
    };
    let review_reason_value = if review_counts.len() == 1 {
        review_reason(representative)
    } else {
        Value::Null
    };
    let summary = clip_text(
        &format!(
            "{} {}",
            row_text(representative, "subject"),
            row_text(representative, "content")
        ),
        140,
    )
    .unwrap_or_else(|| "Agrupamento sem resumo".to_string());
    let semantic_strength = if rows.is_empty() {
        0.0
    } else {
        rows.iter()
            .map(|row| row_f64(row, "quality_score"))
            .sum::<f64>()
            / rows.len() as f64
    };
    json!({
        "cluster_id": cluster_id,
        "agent_id": row_text(representative, "agent_id"),
        "dominant_type": dominant_type,
        "summary": summary,
        "member_count": member_ids.len(),
        "member_ids": member_ids,
        "session_ids": session_ids.into_iter().collect::<Vec<String>>(),
        "semantic_strength": semantic_strength,
        "created_at": representative.get("created_at").cloned().unwrap_or(Value::Null),
        "review_status": review_status_value,
        "review_reason": review_reason_value,
    })
}

fn build_clusters(rows: &[Value]) -> Vec<Value> {
    let mut grouped: BTreeMap<String, Vec<&Value>> = BTreeMap::new();
    for row in rows {
        let cluster_id = row_text(row, "conflict_key");
        if cluster_id.is_empty() {
            continue;
        }
        grouped.entry(cluster_id).or_default().push(row);
    }
    let mut items: Vec<Value> = grouped
        .into_iter()
        .map(|(cluster_id, members): (String, Vec<&Value>)| {
            cluster_review_item(&cluster_id, &members)
        })
        .collect();
    items.sort_by(|left: &Value, right: &Value| {
        let left_members = left
            .get("member_count")
            .and_then(Value::as_i64)
            .unwrap_or_default();
        let right_members = right
            .get("member_count")
            .and_then(Value::as_i64)
            .unwrap_or_default();
        right_members.cmp(&left_members)
    });
    items
}

fn build_dedupe(rows: &[Value]) -> Value {
    let mut grouped: BTreeMap<String, Vec<i64>> = BTreeMap::new();
    for row in rows {
        let content_hash = row_text(row, "content_hash");
        if content_hash.is_empty() {
            continue;
        }
        let memory_id = row_i64(row, "id");
        if memory_id <= 0 {
            continue;
        }
        grouped.entry(content_hash).or_default().push(memory_id);
    }
    json!({
        "duplicate_groups": grouped
            .into_iter()
            .filter(|(_, memory_ids)| memory_ids.len() > 1)
            .map(|(content_hash, memory_ids)| json!({
                "content_hash": content_hash,
                "memory_ids": memory_ids,
            }))
            .collect::<Vec<Value>>(),
    })
}

fn recall_source_weight(source: &str) -> f64 {
    match source.trim().to_ascii_lowercase().as_str() {
        "query_link" => 0.20,
        "task_link" => 0.18,
        "episode" => 0.16,
        "session" => 0.12,
        "lexical" => 0.10,
        "canonical" => 0.06,
        _ => 0.0,
    }
}

fn recall_layer_weight(layer: &str) -> f64 {
    match layer.trim().to_ascii_lowercase().as_str() {
        "episodic" => 0.08,
        "procedural" => 0.07,
        "conversational" => 0.05,
        "proactive" => 0.03,
        _ => 0.0,
    }
}

fn recall_status_penalty(row: &Value) -> f64 {
    let status = row_text(row, "memory_status").to_ascii_lowercase();
    if !row_bool(row, "is_active") {
        return 0.20;
    }
    match status.as_str() {
        "superseded" => 0.16,
        "stale" => 0.18,
        "invalidated" => 0.24,
        "rejected" => 0.24,
        _ => 0.0,
    }
}

fn payload_rows(payload: &Value, field: &str) -> Vec<Value> {
    payload
        .get(field)
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
}

fn payload_object(payload: &Value, field: &str) -> Value {
    payload.get(field).cloned().unwrap_or_else(|| json!({}))
}

fn payload_i64_list(payload: &Value, field: &str) -> Vec<i64> {
    payload
        .get(field)
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| match item {
                    Value::Number(value) => value.as_i64(),
                    Value::String(value) => value.parse::<i64>().ok(),
                    _ => None,
                })
                .filter(|value| *value > 0)
                .collect::<Vec<i64>>()
        })
        .unwrap_or_default()
}

fn payload_string_list(payload: &Value, field: &str) -> Vec<String> {
    payload
        .get(field)
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(ToString::to_string)
                .collect::<Vec<String>>()
        })
        .unwrap_or_default()
}

fn row_ids(rows: &[Value]) -> Vec<i64> {
    let mut ids = rows
        .iter()
        .filter_map(|row| row.get("id").and_then(Value::as_i64))
        .filter(|value| *value > 0)
        .collect::<Vec<i64>>();
    ids.sort_unstable();
    ids.dedup();
    ids
}

fn row_cluster_ids(rows: &[Value]) -> Vec<String> {
    let mut ids = rows
        .iter()
        .map(|row| row_text(row, "conflict_key"))
        .filter(|value| !value.is_empty())
        .collect::<Vec<String>>();
    ids.sort();
    ids.dedup();
    ids
}

fn action_review_status(action: &str) -> Option<&'static str> {
    match action {
        "approve" => Some("approved"),
        "restore" => Some("pending"),
        "merge" => Some("merged"),
        "discard" => Some("discarded"),
        "expire" => Some("expired"),
        "archive" => Some("archived"),
        _ => None,
    }
}

fn action_memory_status(action: &str) -> Option<&'static str> {
    match action {
        "approve" | "restore" => Some("active"),
        "merge" => Some("superseded"),
        "discard" => Some("rejected"),
        "expire" => Some("stale"),
        "archive" => Some("invalidated"),
        _ => None,
    }
}

fn action_is_active(action: &str) -> Option<bool> {
    match action {
        "approve" | "restore" => Some(true),
        "merge" | "discard" | "expire" | "archive" => Some(false),
        _ => None,
    }
}

fn build_action_plan(action: &str, subject_id: &str, payload: &Value) -> Value {
    let mut target_type = payload
        .get("target_type")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();
    if target_type.is_empty() {
        target_type = if !payload_string_list(payload, "cluster_ids").is_empty()
            || payload
                .get("cluster_id")
                .and_then(Value::as_str)
                .map(|value| !value.trim().is_empty())
                .unwrap_or(false)
        {
            "cluster".to_string()
        } else {
            "memory".to_string()
        };
    }

    let cluster_rows = payload_rows(payload, "cluster_rows");
    let mut memory_ids = payload_i64_list(payload, "memory_ids");
    if memory_ids.is_empty() {
        if let Some(memory_id) = payload.get("memory_id").and_then(Value::as_i64) {
            if memory_id > 0 {
                memory_ids.push(memory_id);
            }
        }
    }
    if memory_ids.is_empty() && target_type == "cluster" && !cluster_rows.is_empty() {
        memory_ids.extend(row_ids(&cluster_rows));
    }
    if target_type == "memory" && memory_ids.is_empty() {
        if let Ok(memory_id) = subject_id.parse::<i64>() {
            if memory_id > 0 {
                memory_ids.push(memory_id);
            }
        }
    }
    memory_ids.sort_unstable();
    memory_ids.dedup();

    let mut cluster_ids = payload_string_list(payload, "cluster_ids");
    if cluster_ids.is_empty() {
        if let Some(cluster_id) = payload.get("cluster_id").and_then(Value::as_str) {
            let trimmed = cluster_id.trim();
            if !trimmed.is_empty() {
                cluster_ids.push(trimmed.to_string());
            }
        }
    }
    if target_type == "cluster" && cluster_ids.is_empty() && !subject_id.trim().is_empty() {
        cluster_ids.push(subject_id.trim().to_string());
    }
    if cluster_ids.is_empty() && target_type == "cluster" && !cluster_rows.is_empty() {
        cluster_ids.extend(row_cluster_ids(&cluster_rows));
    }
    cluster_ids.sort();
    cluster_ids.dedup();

    let reason = payload
        .get("reason")
        .and_then(Value::as_str)
        .and_then(|value| clip_text(value, 400))
        .map(Value::String)
        .unwrap_or(Value::Null);
    let duplicate_of_memory_id = payload
        .get("duplicate_of_memory_id")
        .and_then(Value::as_i64)
        .filter(|value| *value > 0)
        .or_else(|| {
            if action == "merge" && memory_ids.len() > 1 {
                memory_ids.first().copied()
            } else {
                None
            }
        })
        .map(Value::from)
        .unwrap_or(Value::Null);
    let requested_memory_status = payload
        .get("memory_status")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(|value| value.to_ascii_lowercase())
        .unwrap_or_default();

    let plan_base = json!({
        "subject_id": subject_id,
        "action": action,
        "target_type": target_type,
        "target_ids": if target_type == "cluster" {
            json!(cluster_ids.clone())
        } else {
            json!(memory_ids.clone())
        },
        "memory_ids": memory_ids.clone(),
        "cluster_ids": cluster_ids.clone(),
        "reason": reason.clone(),
        "duplicate_of_memory_id": duplicate_of_memory_id.clone(),
        "memory_status": if requested_memory_status.is_empty() {
            Value::Null
        } else {
            Value::String(requested_memory_status.clone())
        },
    });

    let invalid = |message: &str| {
        json!({
            "applied": false,
            "error": message,
            "operations": [],
            "updated_count": 0,
            "subject_id": subject_id,
            "action": action,
            "target_type": target_type,
            "memory_ids": memory_ids,
            "cluster_ids": cluster_ids,
        })
    };

    if target_type == "memory" && memory_ids.is_empty() {
        return invalid("no_memory_targets");
    }
    if target_type == "cluster" && cluster_ids.is_empty() {
        return invalid("no_cluster_targets");
    }

    if action == "deactivate" {
        return json!({
            "applied": true,
            "updated_count": memory_ids.len(),
            "operations": [
                {
                    "op": "batch_deactivate",
                    "memory_ids": memory_ids,
                }
            ],
            "subject_id": plan_base.get("subject_id").cloned().unwrap_or(Value::Null),
            "action": plan_base.get("action").cloned().unwrap_or(Value::Null),
            "target_type": plan_base.get("target_type").cloned().unwrap_or(Value::Null),
            "target_ids": plan_base.get("target_ids").cloned().unwrap_or(Value::Null),
            "memory_ids": plan_base.get("memory_ids").cloned().unwrap_or(Value::Null),
            "cluster_ids": plan_base.get("cluster_ids").cloned().unwrap_or(Value::Null),
            "reason": plan_base.get("reason").cloned().unwrap_or(Value::Null),
            "duplicate_of_memory_id": plan_base.get("duplicate_of_memory_id").cloned().unwrap_or(Value::Null),
            "memory_status": plan_base.get("memory_status").cloned().unwrap_or(Value::Null),
        });
    }

    if action == "set_status" {
        if memory_ids.len() != 1 {
            return invalid("exactly_one_memory_id_required");
        }
        if requested_memory_status.is_empty() {
            return invalid("memory_status_required");
        }
        return json!({
            "applied": true,
            "updated_count": 1,
            "operations": [
                {
                    "op": "set_status",
                    "memory_id": memory_ids[0],
                    "memory_status": requested_memory_status,
                    "duplicate_of_memory_id": duplicate_of_memory_id,
                }
            ],
            "subject_id": plan_base.get("subject_id").cloned().unwrap_or(Value::Null),
            "action": plan_base.get("action").cloned().unwrap_or(Value::Null),
            "target_type": plan_base.get("target_type").cloned().unwrap_or(Value::Null),
            "target_ids": plan_base.get("target_ids").cloned().unwrap_or(Value::Null),
            "memory_ids": plan_base.get("memory_ids").cloned().unwrap_or(Value::Null),
            "cluster_ids": plan_base.get("cluster_ids").cloned().unwrap_or(Value::Null),
            "reason": plan_base.get("reason").cloned().unwrap_or(Value::Null),
            "duplicate_of_memory_id": plan_base.get("duplicate_of_memory_id").cloned().unwrap_or(Value::Null),
            "memory_status": plan_base.get("memory_status").cloned().unwrap_or(Value::Null),
        });
    }

    let Some(review_status) = action_review_status(action) else {
        return invalid("unsupported_action");
    };
    let Some(memory_status) = action_memory_status(action) else {
        return invalid("unsupported_action");
    };
    let Some(is_active) = action_is_active(action) else {
        return invalid("unsupported_action");
    };

    let keeper_id = duplicate_of_memory_id
        .as_i64()
        .filter(|value| *value > 0)
        .or_else(|| {
            if action == "merge" {
                memory_ids.first().copied()
            } else {
                None
            }
        });

    if action == "merge" && (memory_ids.len() < 2 || keeper_id.is_none()) {
        return invalid("merge_requires_multiple_memory_ids");
    }

    let operations = memory_ids
        .iter()
        .filter_map(|memory_id| {
            if action == "merge" && Some(*memory_id) == keeper_id {
                return None;
            }
            Some(json!({
                "op": "review_state",
                "memory_id": memory_id,
                "review_status": review_status,
                "memory_status": memory_status,
                "is_active": is_active,
                "reason": reason,
                "duplicate_of_memory_id": if action == "merge" { keeper_id.map(Value::from).unwrap_or(Value::Null) } else { Value::Null },
                "expires_now": action == "expire",
            }))
        })
        .collect::<Vec<Value>>();

    json!({
        "applied": true,
        "updated_count": operations.len(),
        "operations": operations,
        "subject_id": plan_base.get("subject_id").cloned().unwrap_or(Value::Null),
        "action": plan_base.get("action").cloned().unwrap_or(Value::Null),
        "target_type": plan_base.get("target_type").cloned().unwrap_or(Value::Null),
        "target_ids": plan_base.get("target_ids").cloned().unwrap_or(Value::Null),
        "memory_ids": plan_base.get("memory_ids").cloned().unwrap_or(Value::Null),
        "cluster_ids": plan_base.get("cluster_ids").cloned().unwrap_or(Value::Null),
        "reason": plan_base.get("reason").cloned().unwrap_or(Value::Null),
        "duplicate_of_memory_id": keeper_id.map(Value::from).unwrap_or(Value::Null),
        "memory_status": Value::String(memory_status.to_string()),
        "review_status": Value::String(review_status.to_string()),
    })
}

fn build_memory_map(payload: &Value) -> Value {
    let summary_row = payload_object(payload, "summary_row");
    let type_rows = payload_rows(payload, "type_rows");
    let user_rows = payload_rows(payload, "user_rows");
    let embedding_rows = payload_rows(payload, "embedding_rows");
    let quality_rows = payload_rows(payload, "quality_rows");
    let cluster_rows = payload_rows(payload, "cluster_rows");
    let rows = payload_rows(payload, "rows");
    let recent_recall = payload_rows(payload, "recent_recall");
    let maintenance_rows = payload_rows(payload, "maintenance_rows");
    let filters_applied = payload_object(payload, "filters");

    let clusters = build_clusters(&rows);
    let total = summary_row
        .get("total_memories")
        .and_then(Value::as_i64)
        .unwrap_or(rows.len() as i64);
    let semantic_status = if rows.iter().any(|row| {
        !row_text(row, "conflict_key").is_empty() || !row_text(row, "vector_ref_id").is_empty()
    }) {
        "available"
    } else {
        "missing"
    };

    let memory_nodes: Vec<Value> = rows
        .iter()
        .map(|row| {
            let item = memory_review_item(row);
            let importance = item.get("importance").and_then(Value::as_f64).unwrap_or_default();
            let access_count = item.get("access_count").and_then(Value::as_i64).unwrap_or_default();
            let size = (24 + (importance * 48.0) as i64 + access_count).clamp(16, 96);
            json!({
                "id": format!("memory-{}", item.get("memory_id").and_then(Value::as_i64).unwrap_or_default()),
                "kind": "memory",
                "agent_id": item.get("agent_id").cloned().unwrap_or(Value::Null),
                "label": clip_text(item.get("title").and_then(Value::as_str).unwrap_or_default(), 34).unwrap_or_else(|| item.get("title").and_then(Value::as_str).unwrap_or_default().to_string()),
                "title": item.get("title").cloned().unwrap_or(Value::Null),
                "size": size,
                "cluster_id": item.get("cluster_id").cloned().unwrap_or(Value::Null),
                "created_at": item.get("created_at").cloned().unwrap_or(Value::Null),
                "related_count": 0,
                "source_query_text": item.get("source_query_preview").cloned().unwrap_or(Value::Null),
                "memory_id": item.get("memory_id").cloned().unwrap_or(Value::Null),
                "memory_type": item.get("memory_type").cloned().unwrap_or(Value::Null),
                "content": item.get("content").cloned().unwrap_or(Value::Null),
                "source_query_id": item.get("source_query_id").cloned().unwrap_or(Value::Null),
                "source_query_preview": item.get("source_query_preview").cloned().unwrap_or(Value::Null),
                "session_id": item.get("session_id").cloned().unwrap_or(Value::Null),
                "user_id": item.get("user_id").cloned().unwrap_or(Value::Null),
                "importance": item.get("importance").cloned().unwrap_or(Value::Null),
                "access_count": item.get("access_count").cloned().unwrap_or(Value::Null),
                "last_accessed": item.get("last_accessed").cloned().unwrap_or(Value::Null),
                "expires_at": item.get("expires_at").cloned().unwrap_or(Value::Null),
                "review_status": item.get("review_status").cloned().unwrap_or(Value::Null),
                "review_reason": item.get("review_reason").cloned().unwrap_or(Value::Null),
                "duplicate_of_memory_id": item.get("duplicate_of_memory_id").cloned().unwrap_or(Value::Null),
                "semantic_strength": item.get("semantic_strength").cloned().unwrap_or(Value::Null),
                "memory_status": item.get("memory_status").cloned().unwrap_or(Value::Null),
                "metadata": item.get("metadata").cloned().unwrap_or_else(|| json!({})),
                "is_active": item.get("is_active").cloned().unwrap_or(Value::Bool(false)),
            })
        })
        .collect();

    let learning_nodes: Vec<Value> = clusters
        .iter()
        .map(|cluster| {
            let member_count = cluster.get("member_count").and_then(Value::as_i64).unwrap_or_default();
            json!({
                "id": format!("learning-{}", cluster.get("cluster_id").and_then(Value::as_str).unwrap_or_default()),
                "kind": "learning",
                "agent_id": cluster.get("agent_id").cloned().unwrap_or(Value::Null),
                "label": clip_text(cluster.get("summary").and_then(Value::as_str).unwrap_or_default(), 34).unwrap_or_else(|| cluster.get("summary").and_then(Value::as_str).unwrap_or_default().to_string()),
                "title": cluster.get("summary").cloned().unwrap_or(Value::Null),
                "size": (40 + (member_count * 8)).clamp(32, 120),
                "cluster_id": cluster.get("cluster_id").cloned().unwrap_or(Value::Null),
                "created_at": cluster.get("created_at").cloned().unwrap_or(Value::Null),
                "related_count": 0,
                "dominant_type": cluster.get("dominant_type").cloned().unwrap_or(Value::Null),
                "importance": 0.6,
                "summary": cluster.get("summary").cloned().unwrap_or(Value::Null),
                "member_ids": cluster.get("member_ids").cloned().unwrap_or_else(|| json!([])),
                "member_count": cluster.get("member_count").cloned().unwrap_or(Value::Null),
                "session_ids": cluster.get("session_ids").cloned().unwrap_or_else(|| json!([])),
                "semantic_strength": cluster.get("semantic_strength").cloned().unwrap_or(Value::Null),
            })
        })
        .collect();

    let edges: Vec<Value> = clusters
        .iter()
        .flat_map(|cluster| {
            let cluster_id = cluster
                .get("cluster_id")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string();
            let learning_id = format!("learning-{}", cluster_id);
            let semantic_strength = cluster
                .get("semantic_strength")
                .cloned()
                .unwrap_or(Value::Null);
            cluster
                .get("member_ids")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default()
                .into_iter()
                .filter_map(move |memory_id| {
                    memory_id.as_i64().map(|parsed| {
                        json!({
                            "id": format!("learning:{}:memory-{}", cluster_id, parsed),
                            "source": learning_id,
                            "target": format!("memory-{}", parsed),
                            "type": "learning",
                            "weight": 1.0,
                            "label": "Cluster",
                            "similarity": semantic_strength,
                            "session_id": Value::Null,
                            "source_key": cluster_id,
                        })
                    })
                })
        })
        .collect();

    let mut user_counts: BTreeMap<i64, i64> = BTreeMap::new();
    let mut session_counts: BTreeMap<String, i64> = BTreeMap::new();
    let mut type_counts: BTreeMap<String, i64> = BTreeMap::new();
    for row in &rows {
        let user_id = row_i64(row, "user_id");
        if user_id > 0 {
            *user_counts.entry(user_id).or_default() += 1;
        }
        let session_id = row_text(row, "session_id");
        if !session_id.is_empty() {
            *session_counts.entry(session_id).or_default() += 1;
        }
        let memory_type = row_text(row, "memory_type");
        if !memory_type.is_empty() {
            *type_counts.entry(memory_type).or_default() += 1;
        }
    }

    let rendered_memories = memory_nodes.len();
    let learning_node_count = learning_nodes.len();
    let embedding_jobs = embedding_rows
        .iter()
        .filter_map(|row| {
            row.get("status")
                .and_then(Value::as_str)
                .map(|status| (status.to_string(), json!(row_i64(row, "job_count"))))
        })
        .collect::<serde_json::Map<String, Value>>();
    let quality_counters = quality_rows
        .iter()
        .filter_map(|row| {
            row.get("counter_key")
                .and_then(Value::as_str)
                .map(|key| (key.to_string(), json!(row_i64(row, "counter_value"))))
        })
        .collect::<serde_json::Map<String, Value>>();
    let filter_users = user_counts
        .iter()
        .map(|(user_id, count)| json!({"user_id": user_id, "label": format!("User {}", user_id), "count": count}))
        .collect::<Vec<Value>>();
    let filter_sessions = session_counts
        .iter()
        .map(|(session_id, count)| json!({"session_id": session_id, "label": session_id, "count": count, "last_used": Value::Null}))
        .collect::<Vec<Value>>();
    let filter_types = type_counts
        .iter()
        .map(|(memory_type, count)| json!({"value": memory_type, "label": memory_type, "count": count, "color": Value::Null}))
        .collect::<Vec<Value>>();
    let type_counts_map = type_rows
        .iter()
        .filter_map(|row| {
            row.get("memory_type")
                .and_then(Value::as_str)
                .map(|key| (key.to_string(), json!(row_i64(row, "memory_count"))))
        })
        .collect::<serde_json::Map<String, Value>>();
    let mut nodes = memory_nodes;
    nodes.extend(learning_nodes);

    json!({
        "agent_id": payload.get("agent_id").cloned().unwrap_or(Value::Null),
        "summary": {
            "total": total,
            "active": summary_row.get("active_memories").and_then(Value::as_i64).unwrap_or_default(),
            "superseded": summary_row.get("superseded_memories").and_then(Value::as_i64).unwrap_or_default(),
            "stale": summary_row.get("stale_memories").and_then(Value::as_i64).unwrap_or_default(),
            "invalidated": summary_row.get("invalidated_memories").and_then(Value::as_i64).unwrap_or_default(),
        },
        "embedding_jobs": embedding_jobs,
        "quality_counters": quality_counters,
        "top_clusters": cluster_rows,
        "recent_recall": recent_recall,
        "maintenance": maintenance_rows,
        "stats": {
            "total_memories": total,
            "rendered_memories": rendered_memories,
            "hidden_memories": (total - rendered_memories as i64).max(0),
            "active_memories": nodes.iter().filter(|node| node.get("kind").and_then(Value::as_str).unwrap_or_default() == "memory" && node.get("is_active").and_then(Value::as_bool).unwrap_or(false)).count(),
            "inactive_memories": nodes.iter().filter(|node| node.get("kind").and_then(Value::as_str).unwrap_or_default() == "memory" && !node.get("is_active").and_then(Value::as_bool).unwrap_or(false)).count(),
            "learning_nodes": learning_node_count,
            "users": user_counts.len(),
            "sessions": session_counts.len(),
            "semantic_edges": edges.len(),
            "contextual_edges": 0,
            "expiring_soon": 0,
            "maintenance_operations": maintenance_rows.len(),
            "last_maintenance_at": maintenance_rows.first().and_then(|row| row.get("executed_at")).cloned().unwrap_or(Value::Null),
            "semantic_status": semantic_status,
        },
        "filters": {
            "applied": filters_applied,
            "users": filter_users,
            "sessions": filter_sessions,
            "types": filter_types,
            "type_counts": type_counts_map,
            "user_counts": user_rows,
        },
        "nodes": nodes,
        "edges": edges,
        "semantic_status": semantic_status,
    })
}

fn build_list_curation_items(payload: &Value) -> Value {
    let rows = payload_rows(payload, "rows");
    let all_rows = payload_rows(payload, "all_rows");
    let filters = payload_object(payload, "filters");
    let limit = filters.get("limit").and_then(Value::as_i64).unwrap_or(50);
    let offset = filters.get("offset").and_then(Value::as_i64).unwrap_or(0);
    let total = payload
        .get("total")
        .and_then(Value::as_i64)
        .unwrap_or(rows.len() as i64);
    let effective_query = filters
        .get("query")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    let effective_memory_status = filters
        .get("memory_status")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    let effective_review_status = filters
        .get("review_status")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    let effective_memory_type = filters
        .get("memory_type")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    let effective_cluster_id = filters
        .get("cluster_id")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let kind = filters
        .get("kind")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let user_id_filter = filters.get("user_id").and_then(Value::as_i64);
    let is_active_filter = filters.get("is_active").and_then(Value::as_bool);

    let mut items: Vec<Value> = rows.iter().map(memory_review_item).collect();
    if !effective_review_status.is_empty() {
        items.retain(|item| {
            item.get("review_status")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_ascii_lowercase()
                == effective_review_status
        });
    }
    if !effective_memory_status.is_empty() {
        items.retain(|item| {
            item.get("memory_status")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_ascii_lowercase()
                == effective_memory_status
        });
    }
    if !effective_memory_type.is_empty() {
        items.retain(|item| {
            item.get("memory_type")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_ascii_lowercase()
                == effective_memory_type
        });
    }
    if !effective_cluster_id.is_empty() {
        items.retain(|item| {
            item.get("cluster_id")
                .and_then(Value::as_str)
                .unwrap_or_default()
                == effective_cluster_id
        });
    }
    if let Some(user_id) = user_id_filter {
        items.retain(|item| {
            item.get("user_id")
                .and_then(Value::as_i64)
                .unwrap_or_default()
                == user_id
        });
    }
    if let Some(is_active) = is_active_filter {
        items.retain(|item| {
            item.get("is_active")
                .and_then(Value::as_bool)
                .unwrap_or(false)
                == is_active
        });
    }
    if !effective_query.is_empty() {
        items.retain(|item| {
            let haystack = format!(
                "{} {} {}",
                item.get("title")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_ascii_lowercase(),
                item.get("content")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_ascii_lowercase(),
                item.get("source_query_preview")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_ascii_lowercase(),
            );
            haystack.contains(&effective_query)
        });
    }

    let mut clusters = build_clusters(&all_rows);
    if kind == "memory" {
        clusters.clear();
    } else if kind == "cluster" {
        items.clear();
    }
    let mut available_statuses: BTreeMap<String, i64> = BTreeMap::new();
    let mut available_types: BTreeMap<String, i64> = BTreeMap::new();
    for row in &all_rows {
        *available_statuses.entry(review_status(row)).or_default() += 1;
        let memory_type = row_text(row, "memory_type");
        if !memory_type.is_empty() {
            *available_types.entry(memory_type).or_default() += 1;
        }
    }
    let status_filters = ["pending", "approved", "merged", "discarded", "expired", "archived"]
        .iter()
        .map(|status| json!({"value": status, "label": status, "count": available_statuses.get(*status).copied().unwrap_or_default()}))
        .collect::<Vec<Value>>();
    let type_filters = available_types
        .iter()
        .map(|(memory_type, count)| json!({"value": memory_type, "label": memory_type, "color": Value::Null, "count": count}))
        .collect::<Vec<Value>>();

    json!({
        "agent_id": payload.get("agent_id").cloned().unwrap_or(Value::Null),
        "overview": {
            "pending_memories": all_rows.iter().filter(|row| review_status(row) == "pending").count(),
            "pending_clusters": clusters.iter().filter(|item| item.get("review_status").and_then(Value::as_str).unwrap_or_default() == "pending").count(),
            "expiring_soon": all_rows.iter().filter(|row| !row.get("expires_at").unwrap_or(&Value::Null).is_null()).count(),
            "discarded_last_7d": all_rows.iter().filter(|row| review_status(row) == "discarded").count(),
            "merged_last_7d": all_rows.iter().filter(|row| review_status(row) == "merged").count(),
            "approved_last_7d": all_rows.iter().filter(|row| review_status(row) == "approved").count(),
        },
        "items": items,
        "clusters": clusters,
        "available_filters": {
            "statuses": status_filters,
            "types": type_filters,
        },
        "filters": filters,
        "page": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + (items.len() as i64) < total,
        },
    })
}

fn audit_matches_cluster(row: &Value, cluster_id: &str) -> bool {
    let details = row.get("details").cloned().unwrap_or(Value::Null);
    if !details.is_object() {
        return false;
    }
    let target_type = details
        .get("target_type")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();
    let target_id = details
        .get("target_id")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_string();
    if target_type == "cluster" && target_id == cluster_id {
        return true;
    }
    details
        .get("cluster_ids")
        .and_then(Value::as_array)
        .map(|items| {
            items.iter().any(|item| {
                item.as_str()
                    .map(|value| value.trim() == cluster_id)
                    .unwrap_or(false)
            })
        })
        .unwrap_or(false)
}

fn build_curation_detail(payload: &Value) -> Value {
    let detail_kind = payload
        .get("detail_kind")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    let row = payload.get("row").cloned().unwrap_or(Value::Null);
    let cluster_rows = payload_rows(payload, "cluster_rows");
    let related_rows = payload_rows(payload, "related_rows");
    let recent_audits = payload_rows(payload, "recent_audits");
    if detail_kind == "cluster" {
        let cluster_id = payload
            .get("cluster_id")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let member_refs: Vec<&Value> = cluster_rows.iter().collect();
        let history = recent_audits
            .iter()
            .filter(|row| audit_matches_cluster(row, &cluster_id))
            .cloned()
            .collect::<Vec<Value>>();
        let overlaps = cluster_rows
            .iter()
            .filter_map(|row| {
                let session_id = row
                    .get("session_id")
                    .and_then(Value::as_str)?
                    .trim()
                    .to_string();
                if session_id.is_empty() {
                    return None;
                }
                Some(session_id)
            })
            .fold(BTreeMap::<String, i64>::new(), |mut acc, session_id| {
                *acc.entry(session_id).or_default() += 1;
                acc
            })
            .into_iter()
            .map(|(session_id, count)| json!({"session_id": session_id, "count": count}))
            .collect::<Vec<Value>>();
        return json!({
            "cluster": cluster_review_item(&cluster_id, &member_refs),
            "members": cluster_rows.iter().map(memory_review_item).collect::<Vec<Value>>(),
            "overlaps": overlaps,
            "history": history,
        });
    }
    let item = memory_review_item(&row);
    let cluster = if cluster_rows.is_empty() {
        Value::Null
    } else {
        let member_refs: Vec<&Value> = cluster_rows.iter().collect();
        json!({
            "summary": cluster_review_item(
                item.get("cluster_id").and_then(Value::as_str).unwrap_or_default(),
                &member_refs,
            ),
            "members": cluster_rows.iter().map(memory_review_item).collect::<Vec<Value>>(),
        })
    };
    json!({
        "memory": item.clone(),
        "item": item.clone(),
        "source_query_text": item.get("source_query_preview").cloned().unwrap_or(Value::Null),
        "session_name": row.get("session_id").cloned().unwrap_or(Value::Null),
        "related_memories": related_rows.iter().map(memory_review_item).collect::<Vec<Value>>(),
        "similar_memories": [],
        "cluster": cluster,
        "recent_audits": recent_audits,
        "history": payload.get("recent_audits").cloned().unwrap_or_else(|| json!([])),
    })
}

fn value_string(value: Option<&Value>) -> String {
    value
        .and_then(|item| item.as_str().map(ToString::to_string))
        .unwrap_or_default()
}

fn value_i64(value: Option<&Value>) -> i64 {
    value.and_then(Value::as_i64).unwrap_or_default()
}

fn value_f64(value: Option<&Value>) -> f64 {
    value.and_then(Value::as_f64).unwrap_or_default()
}

fn value_bool(value: Option<&Value>) -> bool {
    value.and_then(Value::as_bool).unwrap_or(false)
}

fn proto_memory_record_row(value: &Value) -> MemoryRecordRow {
    MemoryRecordRow {
        id: value_i64(value.get("id")),
        content_hash: value_string(value.get("content_hash")),
        conflict_key: value_string(value.get("conflict_key")),
        quality_score: value_f64(value.get("quality_score")),
        importance: value_f64(value.get("importance")),
        created_at: value_string(value.get("created_at")),
        agent_id: value_string(value.get("agent_id")),
        memory_type: value_string(value.get("memory_type")),
        subject: value_string(value.get("subject")),
        content: value_string(value.get("content")),
        session_id: value_string(value.get("session_id")),
        user_id: value_i64(value.get("user_id")),
        origin_kind: value_string(value.get("origin_kind")),
        source_query_id: value_i64(value.get("source_query_id")),
        source_task_id: value_i64(value.get("source_task_id")),
        source_episode_id: value_i64(value.get("source_episode_id")),
        project_key: value_string(value.get("project_key")),
        environment: value_string(value.get("environment")),
        team: value_string(value.get("team")),
        extraction_confidence: value_f64(value.get("extraction_confidence")),
        embedding_status: value_string(value.get("embedding_status")),
        claim_kind: value_string(value.get("claim_kind")),
        decision_source: value_string(value.get("decision_source")),
        evidence_refs: Some(dynamic_value_from_json(
            value
                .get("evidence_refs_json")
                .or_else(|| value.get("evidence_refs"))
                .unwrap_or(&Value::Null),
        )),
        applicability_scope: Some(dynamic_value_from_json(
            value
                .get("applicability_scope_json")
                .or_else(|| value.get("applicability_scope"))
                .unwrap_or(&Value::Null),
        )),
        valid_until: value_string(value.get("valid_until")),
        supersedes_memory_id: value_i64(value.get("supersedes_memory_id")),
        memory_status: value_string(value.get("memory_status")),
        retention_reason: value_string(value.get("retention_reason")),
        embedding_attempts: value_i64(value.get("embedding_attempts")),
        embedding_last_error: value_string(value.get("embedding_last_error")),
        embedding_retry_at: value_string(value.get("embedding_retry_at")),
        access_count: value_i64(value.get("access_count")),
        last_accessed: value_string(value.get("last_accessed")),
        last_recalled_at: value_string(value.get("last_recalled_at")),
        expires_at: value_string(value.get("expires_at")),
        is_active: value_bool(value.get("is_active")),
        metadata: Some(dynamic_struct_from_json(
            value.get("metadata").unwrap_or(&Value::Null),
        )),
        vector_ref_id: value_string(value.get("vector_ref_id")),
        source_query_preview: value_string(value.get("source_query_preview")),
    }
}

fn proto_curation_item(value: &Value) -> CurationItem {
    CurationItem {
        agent_id: value_string(value.get("agent_id")),
        id: value_i64(value.get("id")),
        memory_id: value_i64(value.get("memory_id")),
        memory_type: value_string(value.get("memory_type")),
        title: value_string(value.get("title")),
        content: value_string(value.get("content")),
        source_query_id: value_i64(value.get("source_query_id")),
        source_query_preview: value_string(value.get("source_query_preview")),
        session_id: value_string(value.get("session_id")),
        user_id: value_i64(value.get("user_id")),
        importance: value_f64(value.get("importance")),
        access_count: value_i64(value.get("access_count")),
        created_at: value_string(value.get("created_at")),
        last_accessed: value_string(value.get("last_accessed")),
        expires_at: value_string(value.get("expires_at")),
        review_status: value_string(value.get("review_status")),
        review_reason: value_string(value.get("review_reason")),
        duplicate_of_memory_id: value_i64(value.get("duplicate_of_memory_id")),
        cluster_id: value_string(value.get("cluster_id")),
        semantic_strength: value_f64(value.get("semantic_strength")),
        memory_status: value_string(value.get("memory_status")),
        metadata: Some(dynamic_struct_from_json(
            value.get("metadata").unwrap_or(&Value::Null),
        )),
        is_active: value_bool(value.get("is_active")),
    }
}

fn proto_cluster_summary(value: &Value) -> CurationClusterSummary {
    CurationClusterSummary {
        cluster_id: value_string(value.get("cluster_id")),
        agent_id: value_string(value.get("agent_id")),
        summary: value_string(value.get("summary")),
        memory_count: value_i64(value.get("memory_count")),
        latest_created_at: value_string(value.get("latest_created_at")),
        review_status: value_string(value.get("review_status")),
        dominant_type: value_string(value.get("dominant_type")),
        member_ids: value
            .get("member_ids")
            .and_then(Value::as_array)
            .map(|items| items.iter().filter_map(Value::as_i64).collect::<Vec<_>>())
            .unwrap_or_default(),
    }
}

fn proto_overview(value: &Value) -> CurationOverview {
    CurationOverview {
        pending_memories: value_i64(value.get("pending_memories")),
        pending_clusters: value_i64(value.get("pending_clusters")),
        expiring_soon: value_i64(value.get("expiring_soon")),
        discarded_last_7d: value_i64(value.get("discarded_last_7d")),
        merged_last_7d: value_i64(value.get("merged_last_7d")),
        approved_last_7d: value_i64(value.get("approved_last_7d")),
    }
}

fn proto_pagination(value: &Value) -> Pagination {
    Pagination {
        limit: value_i64(value.get("limit")),
        offset: value_i64(value.get("offset")),
        total: value_i64(value.get("total")),
        has_more: value_bool(value.get("has_more")),
    }
}

fn proto_counter_entries(value: &Value) -> Vec<CounterEntry> {
    match value {
        Value::Object(items) => items
            .iter()
            .map(|(key, raw)| CounterEntry {
                key: key.clone(),
                count: raw
                    .as_i64()
                    .unwrap_or_else(|| raw.as_f64().unwrap_or_default().round() as i64),
                updated_at: String::new(),
            })
            .collect(),
        Value::Array(items) => items
            .iter()
            .map(|item| CounterEntry {
                key: value_string(
                    item.get("key")
                        .or_else(|| item.get("counter_key"))
                        .or_else(|| item.get("status")),
                ),
                count: value_i64(
                    item.get("count")
                        .or_else(|| item.get("counter_value"))
                        .or_else(|| item.get("job_count")),
                ),
                updated_at: value_string(item.get("updated_at")),
            })
            .collect(),
        _ => Vec::new(),
    }
}

fn proto_memory_map_summary(value: &Value) -> MemoryMapSummary {
    MemoryMapSummary {
        total: value_i64(value.get("total")),
        active: value_i64(value.get("active")),
        superseded: value_i64(value.get("superseded")),
        stale: value_i64(value.get("stale")),
        invalidated: value_i64(value.get("invalidated")),
    }
}

fn proto_recall_log_item(value: &Value) -> RecallLogItem {
    RecallLogItem {
        id: value_i64(value.get("id")),
        user_id: value_i64(value.get("user_id")),
        task_id: value_i64(value.get("task_id")),
        query_preview: value_string(value.get("query_preview")),
        trust_score: value_f64(value.get("trust_score")),
        total_considered: value_i64(value.get("total_considered")),
        total_selected: value_i64(value.get("total_selected")),
        total_discarded: value_i64(value.get("total_discarded")),
        conflict_group_count: value_i64(value.get("conflict_group_count")),
        selected_layers_csv: value_string(value.get("selected_layers_csv")),
        retrieval_sources_csv: value_string(value.get("retrieval_sources_csv")),
        created_at: value_string(value.get("created_at")),
    }
}

fn proto_maintenance_log_item(value: &Value) -> MaintenanceLogItem {
    MaintenanceLogItem {
        operation: value_string(value.get("operation")),
        memories_affected: value_i64(value.get("memories_affected")),
        details: value_string(value.get("details")),
        executed_at: value_string(value.get("executed_at")),
    }
}

fn proto_audit_log_item(value: &Value) -> AuditLogItem {
    AuditLogItem {
        id: value_i64(value.get("id")),
        task_id: value_i64(value.get("task_id")),
        query_preview: value_string(value.get("query_preview")),
        trust_score: value_f64(value.get("trust_score")),
        considered: Some(dynamic_value_from_json(
            value.get("considered").unwrap_or(&Value::Null),
        )),
        selected: Some(dynamic_value_from_json(
            value.get("selected").unwrap_or(&Value::Null),
        )),
        discarded: Some(dynamic_value_from_json(
            value.get("discarded").unwrap_or(&Value::Null),
        )),
        conflicts: Some(dynamic_value_from_json(
            value.get("conflicts").unwrap_or(&Value::Null),
        )),
        explanations: Some(dynamic_value_from_json(
            value.get("explanations").unwrap_or(&Value::Null),
        )),
        created_at: value_string(value.get("created_at")),
        timestamp: value_string(value.get("timestamp")),
        details: Some(dynamic_value_from_json(
            value.get("details").unwrap_or(&Value::Null),
        )),
    }
}

fn proto_action_operation(value: &Value) -> CurationActionOperation {
    CurationActionOperation {
        op: value_string(value.get("op")),
        memory_id: value_i64(value.get("memory_id")),
        memory_ids: value
            .get("memory_ids")
            .and_then(Value::as_array)
            .map(|items| items.iter().filter_map(Value::as_i64).collect::<Vec<_>>())
            .unwrap_or_default(),
        review_status: value_string(value.get("review_status")),
        memory_status: value_string(value.get("memory_status")),
        is_active: value_bool(value.get("is_active")),
        reason: value_string(value.get("reason")),
        duplicate_of_memory_id: value_i64(value.get("duplicate_of_memory_id")),
        expires_now: value_bool(value.get("expires_now")),
    }
}

fn proto_memory_dashboard_filter(value: &Value) -> MemoryDashboardFilter {
    MemoryDashboardFilter {
        user_id: value_i64(value.get("user_id")),
        session_id: value_string(value.get("session_id")),
        days: value_i64(value.get("days")),
        include_inactive: value_bool(value.get("include_inactive")),
        limit: value_i64(value.get("limit")),
        offset: value_i64(value.get("offset")),
        review_status: value_string(value.get("review_status")),
        memory_status: value_string(value.get("memory_status")),
        memory_type: value_string(value.get("memory_type")),
        query: value_string(value.get("query")),
        cluster_id: value_string(value.get("cluster_id")),
        origin_kind: value_string(value.get("origin_kind")),
        kind: value_string(value.get("kind")),
        has_is_active: value.get("is_active").is_some(),
        is_active: value_bool(value.get("is_active")),
    }
}

fn proto_filter_option(value: &Value) -> FilterOption {
    FilterOption {
        value: value_string(value.get("value")),
        label: value_string(value.get("label")),
        count: value_i64(value.get("count")),
        color: value_string(value.get("color")),
    }
}

fn proto_user_filter_option(value: &Value) -> UserFilterOption {
    UserFilterOption {
        user_id: value_i64(value.get("user_id")),
        label: value_string(value.get("label")),
        count: value_i64(value.get("count")),
    }
}

fn proto_session_filter_option(value: &Value) -> SessionFilterOption {
    SessionFilterOption {
        session_id: value_string(value.get("session_id")),
        label: value_string(value.get("label")),
        count: value_i64(value.get("count")),
        last_used: value_string(value.get("last_used")),
    }
}

fn proto_memory_graph_node(value: &Value) -> MemoryGraphNode {
    MemoryGraphNode {
        id: value_string(value.get("id")),
        kind: value_string(value.get("kind")),
        agent_id: value_string(value.get("agent_id")),
        label: value_string(value.get("label")),
        title: value_string(value.get("title")),
        size: value_i64(value.get("size")),
        cluster_id: value_string(value.get("cluster_id")),
        created_at: value_string(value.get("created_at")),
        related_count: value_i64(value.get("related_count")),
        source_query_text: value_string(value.get("source_query_text")),
        memory_id: value_i64(value.get("memory_id")),
        memory_type: value_string(value.get("memory_type")),
        content: value_string(value.get("content")),
        source_query_id: value_i64(value.get("source_query_id")),
        source_query_preview: value_string(value.get("source_query_preview")),
        session_id: value_string(value.get("session_id")),
        user_id: value_i64(value.get("user_id")),
        importance: value_f64(value.get("importance")),
        access_count: value_i64(value.get("access_count")),
        last_accessed: value_string(value.get("last_accessed")),
        expires_at: value_string(value.get("expires_at")),
        review_status: value_string(value.get("review_status")),
        review_reason: value_string(value.get("review_reason")),
        duplicate_of_memory_id: value_i64(value.get("duplicate_of_memory_id")),
        semantic_strength: value_f64(value.get("semantic_strength")),
        memory_status: value_string(value.get("memory_status")),
        metadata: Some(dynamic_struct_from_json(
            value.get("metadata").unwrap_or(&Value::Null),
        )),
        is_active: value_bool(value.get("is_active")),
        dominant_type: value_string(value.get("dominant_type")),
        summary: value_string(value.get("summary")),
        member_ids: value
            .get("member_ids")
            .and_then(Value::as_array)
            .map(|items| items.iter().filter_map(Value::as_i64).collect::<Vec<_>>())
            .unwrap_or_default(),
        member_count: value_i64(value.get("member_count")),
        session_ids: value
            .get("session_ids")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(Value::as_str)
                    .map(ToString::to_string)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default(),
    }
}

fn proto_memory_graph_edge(value: &Value) -> MemoryGraphEdge {
    MemoryGraphEdge {
        id: value_string(value.get("id")),
        source: value_string(value.get("source")),
        target: value_string(value.get("target")),
        r#type: value_string(value.get("type")),
        weight: value_f64(value.get("weight")),
        label: value_string(value.get("label")),
        similarity: value_f64(value.get("similarity")),
        session_id: value_string(value.get("session_id")),
        source_key: value_string(value.get("source_key")),
    }
}

fn proto_memory_map_stats(value: &Value) -> MemoryMapStats {
    MemoryMapStats {
        total_memories: value_i64(value.get("total_memories")),
        rendered_memories: value_i64(value.get("rendered_memories")),
        hidden_memories: value_i64(value.get("hidden_memories")),
        active_memories: value_i64(value.get("active_memories")),
        inactive_memories: value_i64(value.get("inactive_memories")),
        learning_nodes: value_i64(value.get("learning_nodes")),
        users: value_i64(value.get("users")),
        sessions: value_i64(value.get("sessions")),
        semantic_edges: value_i64(value.get("semantic_edges")),
        contextual_edges: value_i64(value.get("contextual_edges")),
        expiring_soon: value_i64(value.get("expiring_soon")),
        maintenance_operations: value_i64(value.get("maintenance_operations")),
        last_maintenance_at: value_string(value.get("last_maintenance_at")),
        semantic_status: value_string(value.get("semantic_status")),
    }
}

fn proto_user_memory_count(value: &Value) -> UserMemoryCount {
    UserMemoryCount {
        user_id: value_i64(value.get("user_id")),
        memory_count: value_i64(value.get("memory_count")),
        active_count: value_i64(value.get("active_count")),
    }
}

fn proto_curation_overlap(value: &Value) -> CurationOverlap {
    CurationOverlap {
        session_id: value_string(value.get("session_id")),
        count: value_i64(value.get("count")),
    }
}

#[tonic::async_trait]
impl MemoryEngineService for MemoryServer {
    async fn recall(
        &self,
        request: Request<RecallRequest>,
    ) -> Result<Response<RecallResponse>, Status> {
        let request = request.into_inner();
        let query_tokens = tokenize(&request.query);
        let allowed_layers = request
            .allowed_layers
            .iter()
            .map(|item| item.to_ascii_lowercase())
            .collect::<HashSet<String>>();
        let allowed_sources = request
            .allowed_retrieval_sources
            .iter()
            .map(|item| item.to_ascii_lowercase())
            .collect::<HashSet<String>>();
        let recall_rows =
            load_recall_rows(&request.agent_id, request.limit, request.context.as_ref()).await?;
        let mut ranked_rows: BTreeMap<i64, (Value, String, String, f64)> = BTreeMap::new();
        for row in recall_rows {
            let memory_id = row_i64(&row, "id");
            if memory_id <= 0 {
                continue;
            }
            let retrieval_source = infer_recall_source(&row, request.context.as_ref());
            let layer = infer_recall_layer(&row);
            let layer_key = layer.to_ascii_lowercase();
            let source_key = retrieval_source.to_ascii_lowercase();
            if !allowed_layers.is_empty() && !allowed_layers.contains(&layer_key) {
                continue;
            }
            if !allowed_sources.is_empty() && !allowed_sources.contains(&source_key) {
                continue;
            }
            let lexical = overlap_score(
                &query_tokens,
                &format!(
                    "{} {} {}",
                    row_text(&row, "subject"),
                    row_text(&row, "content"),
                    row_text(&row, "source_query_preview")
                ),
            );
            let baseline = clamp_score(
                (clamp_score(row_f64(&row, "quality_score")) * 0.45)
                    + (clamp_score(row_f64(&row, "importance")) * 0.35)
                    + ((row_i64(&row, "access_count").clamp(0, 20) as f64 / 20.0) * 0.20),
            );
            let source_bonus = recall_source_weight(&source_key);
            let layer_bonus = recall_layer_weight(&layer_key);
            let status_penalty = recall_status_penalty(&row);
            let final_score = if query_tokens.is_empty() {
                clamp_score(baseline + source_bonus + layer_bonus - status_penalty)
            } else {
                clamp_score(
                    (lexical * 0.60) + (baseline * 0.25) + source_bonus + layer_bonus
                        - status_penalty,
                )
            };
            match ranked_rows.get(&memory_id) {
                Some((_, _, _, existing_score)) if *existing_score >= final_score => {}
                _ => {
                    ranked_rows.insert(memory_id, (row, retrieval_source, layer, final_score));
                }
            }
        }
        let mut items = ranked_rows
            .into_values()
            .map(|(row, retrieval_source, layer, score)| RecallResultItem {
                memory: Some(proto_memory_record_row(&row)),
                score,
                retrieval_source,
                layer,
            })
            .collect::<Vec<_>>();
        items.sort_by(|left, right| right.score.total_cmp(&left.score));
        if request.limit > 0 && items.len() > request.limit as usize {
            items.truncate(request.limit as usize);
        }
        Ok(Response::new(RecallResponse { items }))
    }

    async fn cluster(
        &self,
        request: Request<ClusterRequest>,
    ) -> Result<Response<ClusterResponse>, Status> {
        let request = request.into_inner();
        let rows = request_rows(&request.rows);
        Ok(Response::new(ClusterResponse {
            cluster_json: json!(build_clusters(&rows)).to_string(),
        }))
    }

    async fn deduplicate(
        &self,
        request: Request<DeduplicateRequest>,
    ) -> Result<Response<DeduplicateResponse>, Status> {
        let request = request.into_inner();
        let rows = request_rows(&request.rows);
        Ok(Response::new(DeduplicateResponse {
            dedupe_json: build_dedupe(&rows).to_string(),
        }))
    }

    async fn list_curation_items(
        &self,
        request: Request<ListCurationItemsRequest>,
    ) -> Result<Response<ListCurationItemsResponse>, Status> {
        let request = request.into_inner();
        let payload = load_list_curation_payload(
            &request.agent_id,
            &dashboard_filter_from_request(request.filters.as_ref()),
        )
        .await?;
        let rendered = build_list_curation_items(&payload);
        Ok(Response::new(ListCurationItemsResponse {
            agent_id: value_string(rendered.get("agent_id")),
            overview: Some(proto_overview(
                rendered.get("overview").unwrap_or(&Value::Null),
            )),
            items: rendered
                .get("items")
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_curation_item).collect::<Vec<_>>())
                .unwrap_or_default(),
            clusters: rendered
                .get("clusters")
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_cluster_summary).collect::<Vec<_>>())
                .unwrap_or_default(),
            page: Some(proto_pagination(
                rendered.get("page").unwrap_or(&Value::Null),
            )),
            filters: Some(proto_memory_dashboard_filter(
                rendered.get("filters").unwrap_or(&Value::Null),
            )),
            status_filters: rendered
                .get("available_filters")
                .and_then(|item| item.get("statuses"))
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_filter_option).collect::<Vec<_>>())
                .unwrap_or_default(),
            type_filters: rendered
                .get("available_filters")
                .and_then(|item| item.get("types"))
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_filter_option).collect::<Vec<_>>())
                .unwrap_or_default(),
        }))
    }

    async fn get_memory_map(
        &self,
        request: Request<GetMemoryMapRequest>,
    ) -> Result<Response<GetMemoryMapResponse>, Status> {
        let request = request.into_inner();
        let payload = load_memory_map_payload(
            &request.agent_id,
            &dashboard_filter_from_request(request.filters.as_ref()),
        )
        .await?;
        let rendered = build_memory_map(&payload);
        Ok(Response::new(GetMemoryMapResponse {
            agent_id: value_string(rendered.get("agent_id")),
            summary: Some(proto_memory_map_summary(
                rendered.get("summary").unwrap_or(&Value::Null),
            )),
            embedding_jobs: proto_counter_entries(
                rendered.get("embedding_jobs").unwrap_or(&Value::Null),
            ),
            quality_counters: proto_counter_entries(
                rendered.get("quality_counters").unwrap_or(&Value::Null),
            ),
            top_clusters: rendered
                .get("top_clusters")
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_cluster_summary).collect::<Vec<_>>())
                .unwrap_or_default(),
            recent_recall: rendered
                .get("recent_recall")
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_recall_log_item).collect::<Vec<_>>())
                .unwrap_or_default(),
            maintenance: rendered
                .get("maintenance")
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .map(proto_maintenance_log_item)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default(),
            nodes: rendered
                .get("nodes")
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .map(proto_memory_graph_node)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default(),
            edges: rendered
                .get("edges")
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .map(proto_memory_graph_edge)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default(),
            stats: Some(proto_memory_map_stats(
                rendered.get("stats").unwrap_or(&Value::Null),
            )),
            filters: Some(proto_memory_dashboard_filter(
                rendered
                    .get("filters")
                    .and_then(|item| item.get("applied"))
                    .unwrap_or(&Value::Null),
            )),
            filter_users: rendered
                .get("filters")
                .and_then(|item| item.get("users"))
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .map(proto_user_filter_option)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default(),
            filter_sessions: rendered
                .get("filters")
                .and_then(|item| item.get("sessions"))
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .map(proto_session_filter_option)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default(),
            filter_types: rendered
                .get("filters")
                .and_then(|item| item.get("types"))
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_filter_option).collect::<Vec<_>>())
                .unwrap_or_default(),
            type_counts: rendered
                .get("filters")
                .and_then(|item| item.get("type_counts"))
                .map(proto_counter_entries)
                .unwrap_or_default(),
            user_counts: rendered
                .get("filters")
                .and_then(|item| item.get("user_counts"))
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .map(proto_user_memory_count)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default(),
            semantic_status: value_string(rendered.get("semantic_status")),
        }))
    }

    async fn get_curation_detail(
        &self,
        request: Request<GetCurationDetailRequest>,
    ) -> Result<Response<GetCurationDetailResponse>, Status> {
        let request = request.into_inner();
        let payload = load_curation_detail_payload(
            &request.agent_id,
            &request.subject_id,
            &request.detail_kind,
            &request.cluster_id,
        )
        .await?;
        let rendered = build_curation_detail(&payload);
        let detail_kind = if rendered.get("memory").is_some() {
            "memory".to_string()
        } else {
            "cluster".to_string()
        };
        let cluster_summary_value = if detail_kind == "cluster" {
            rendered.get("cluster").unwrap_or(&Value::Null)
        } else {
            rendered
                .get("cluster")
                .and_then(|item| item.get("summary"))
                .unwrap_or(&Value::Null)
        };
        let cluster_members_value = if detail_kind == "cluster" {
            rendered.get("members")
        } else {
            rendered.get("cluster").and_then(|item| item.get("members"))
        };
        Ok(Response::new(GetCurationDetailResponse {
            detail_kind,
            memory: rendered.get("memory").map(proto_curation_item),
            related_memories: rendered
                .get("related_memories")
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_curation_item).collect::<Vec<_>>())
                .unwrap_or_default(),
            cluster_members: cluster_members_value
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_curation_item).collect::<Vec<_>>())
                .unwrap_or_default(),
            recent_audits: rendered
                .get("recent_audits")
                .or_else(|| rendered.get("history"))
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_audit_log_item).collect::<Vec<_>>())
                .unwrap_or_default(),
            cluster_summary: if cluster_summary_value.is_null() {
                None
            } else {
                Some(proto_cluster_summary(cluster_summary_value))
            },
            source_query_text: value_string(rendered.get("source_query_text")),
            session_name: value_string(rendered.get("session_name")),
            overlaps: rendered
                .get("overlaps")
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_curation_overlap).collect::<Vec<_>>())
                .unwrap_or_default(),
            history: rendered
                .get("history")
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_audit_log_item).collect::<Vec<_>>())
                .unwrap_or_default(),
        }))
    }

    async fn apply_curation_action(
        &self,
        request: Request<ApplyCurationActionRequest>,
    ) -> Result<Response<ApplyCurationActionResponse>, Status> {
        let request = request.into_inner();
        let cluster_rows = if request.target_type.trim().eq_ignore_ascii_case("cluster") {
            let mut cluster_ids = request
                .cluster_ids
                .iter()
                .map(|item| item.trim().to_string())
                .filter(|item| !item.is_empty())
                .collect::<Vec<String>>();
            if cluster_ids.is_empty() && !request.subject_id.trim().is_empty() {
                cluster_ids.push(request.subject_id.trim().to_string());
            }
            if cluster_ids.is_empty() {
                Vec::new()
            } else {
                let client = memory_postgres_client().await?;
                query_memory_rows(
                    &client,
                    &format!(
                        "{MEMORY_SELECT_SQL} WHERE n.agent_id = $1 AND COALESCE(n.conflict_key, '') = ANY($2::TEXT[]) ORDER BY n.created_at DESC, n.id DESC"
                    ),
                    &[&request.agent_id, &cluster_ids],
                )
                .await?
            }
        } else {
            Vec::new()
        };
        let payload = json!({
            "target_type": request.target_type,
            "target_ids": request.target_ids,
            "cluster_ids": request.cluster_ids,
            "memory_ids": request.memory_ids,
            "reason": if request.reason.trim().is_empty() { Value::Null } else { Value::String(request.reason.clone()) },
            "duplicate_of_memory_id": if request.duplicate_of_memory_id > 0 { json!(request.duplicate_of_memory_id) } else { Value::Null },
            "memory_status": if request.memory_status.trim().is_empty() { Value::Null } else { Value::String(request.memory_status.clone()) },
            "cluster_rows": cluster_rows,
        });
        let mut action_json = build_action_plan(&request.action, &request.subject_id, &payload);
        if value_string(action_json.get("error")).is_empty() {
            let (updated_count, affected_ids) =
                execute_action_plan(&request.agent_id, &action_json).await?;
            if let Some(object) = action_json.as_object_mut() {
                object.insert("applied".to_string(), Value::Bool(true));
                object.insert("updated_count".to_string(), json!(updated_count));
                object.insert("memory_ids".to_string(), json!(affected_ids));
            }
        }
        Ok(Response::new(ApplyCurationActionResponse {
            applied: action_json
                .get("applied")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            updated_count: value_i64(action_json.get("updated_count")),
            memory_ids: action_json
                .get("memory_ids")
                .and_then(Value::as_array)
                .map(|items| items.iter().filter_map(Value::as_i64).collect::<Vec<_>>())
                .unwrap_or_default(),
            duplicate_of_memory_id: value_i64(action_json.get("duplicate_of_memory_id")),
            operations: action_json
                .get("operations")
                .and_then(Value::as_array)
                .map(|items| items.iter().map(proto_action_operation).collect::<Vec<_>>())
                .unwrap_or_default(),
            error: value_string(action_json.get("error")),
            target_type: value_string(action_json.get("target_type")),
            cluster_ids: action_json
                .get("cluster_ids")
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .filter_map(Value::as_str)
                        .map(ToString::to_string)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default(),
            reason: value_string(action_json.get("reason")),
            memory_status: value_string(action_json.get("memory_status")),
            review_status: value_string(action_json.get("review_status")),
        }))
    }

    async fn health(
        &self,
        _request: Request<HealthRequest>,
    ) -> Result<Response<HealthResponse>, Status> {
        let mut details = health_details("koda-memory-engine");
        details.insert("authoritative".to_string(), "true".to_string());
        details.insert("production_ready".to_string(), "true".to_string());
        details.insert("maturity".to_string(), "authoritative".to_string());
        details.insert(
            "projection_mode".to_string(),
            "kernel_authoritative".to_string(),
        );
        details.insert(
            "action_mode".to_string(),
            "kernel_authoritative".to_string(),
        );
        details.insert(
            "capabilities".to_string(),
            "recall,cluster,deduplicate,memory_map,curation,curation_detail,curation_action"
                .to_string(),
        );
        Ok(Response::new(HealthResponse {
            service: "koda-memory-engine".to_string(),
            ready: true,
            status: "ready".to_string(),
            details,
        }))
    }
}

async fn serve_target(target: &str) -> Result<()> {
    let service = MemoryEngineServiceServer::new(MemoryServer);
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
    init_tracing("koda-memory-engine");
    let target =
        std::env::var("MEMORY_GRPC_TARGET").unwrap_or_else(|_| "127.0.0.1:50063".to_string());
    serve_target(&target).await
}

#[cfg(test)]
mod tests {
    use super::{overlap_score, tokenize};

    #[test]
    fn tokenize_discards_short_tokens() {
        let tokens = tokenize("a deploy API fix");
        assert!(tokens.contains("deploy"));
        assert!(tokens.contains("api"));
        assert!(tokens.contains("fix"));
        assert!(!tokens.contains("a"));
    }

    #[test]
    fn overlap_score_prefers_matching_terms() {
        let query_tokens = tokenize("deploy api service");
        assert!(
            overlap_score(&query_tokens, "deploy api rollout")
                > overlap_score(&query_tokens, "other topic")
        );
    }
}
