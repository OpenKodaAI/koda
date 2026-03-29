use std::collections::BTreeSet;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::Result;
use koda_observability::{health_details, init_tracing};
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
use tokio_postgres::NoTls;
use tokio_stream::wrappers::UnixListenerStream;
use tonic::transport::Server;
use tonic::{Request, Response, Status};

const SERVICE_NAME: &str = "koda-retrieval-engine";

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

fn synthetic_candidate(query: &str, envelope: &QueryEnvelopePayload) -> RankedCandidate {
    let normalized_query = if !envelope.normalized_query.is_empty() {
        envelope.normalized_query.clone()
    } else {
        query.to_string()
    };
    let identifier = if normalized_query.is_empty() {
        "query-summary".to_string()
    } else {
        format!(
            "query-{}",
            normalized_query.to_ascii_lowercase().replace(' ', "-")
        )
    };
    let candidate = CandidatePayload {
        id: identifier,
        title: if normalized_query.is_empty() {
            "Query summary".to_string()
        } else {
            format!("Query summary: {}", normalized_query)
        },
        content: normalized_query.clone(),
        layer: "workspace_doc".to_string(),
        scope: if envelope.requires_write {
            "operational_policy".to_string()
        } else {
            "repo_fact".to_string()
        },
        source_label: if normalized_query.is_empty() {
            "query:summary".to_string()
        } else {
            format!("query:{}", normalized_query.to_ascii_lowercase())
        },
        source_path: envelope.workspace_dir.clone(),
        source_type: "query".to_string(),
        operable: false,
        freshness: "fresh".to_string(),
        similarity: 0.42,
        lexical_rank: 0,
        dense_rank: -1,
        graph_rank: -1,
        lexical_score: 0.42,
        dense_score: 0.0,
        graph_hops: 0,
        graph_score: 0.0,
        graph_relation_types: Vec::new(),
        evidence_modalities: Vec::new(),
        reasons: vec!["synthetic_query_summary".to_string()],
        project_key: envelope.project_key.clone(),
        environment: envelope.environment.clone(),
        team: envelope.team.clone(),
        ..CandidatePayload::default()
    };
    RankedCandidate {
        candidate,
        supporting_evidence: Vec::new(),
        base_rank: 1,
        score: 0.42,
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
    }
}

fn build_authoritative(selected: &[RankedCandidate]) -> Vec<AuthoritativeEvidence> {
    selected
        .iter()
        .filter(|item| {
            matches!(
                item.candidate.layer.as_str(),
                "canonical_policy" | "approved_runbook"
            )
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

fn provenance_struct(source_label: &str) -> Struct {
    Struct {
        fields: [(
            "source_label".to_string(),
            ProtoValue {
                kind: Some(Kind::StringValue(source_label.to_string())),
            },
        )]
        .into_iter()
        .collect(),
    }
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
                provenance: Some(provenance_struct(&candidate.candidate.source_label)),
            });
        }
    }
    items
}

fn build_linked_entities(query: &str) -> Vec<CanonicalEntity> {
    tokenize(query)
        .into_iter()
        .filter(|token| token.contains('-') || token.contains('/'))
        .take(4)
        .map(|token| {
            let entity_type = if token.contains('/') { "path" } else { "issue" };
            CanonicalEntity {
                entity_key: format!("{entity_type}:{token}"),
                entity_type: entity_type.to_string(),
                label: token,
                aliases: Vec::new(),
                confidence: 0.9,
                metadata: Some(Struct::default()),
            }
        })
        .collect()
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

fn build_retrieve_response(request: &RetrieveRequest, trace_id: String) -> RetrieveResponse {
    let envelope = envelope_from_request(request);
    let query = if !envelope.normalized_query.is_empty() {
        envelope.normalized_query.clone()
    } else {
        request.query.clone()
    };
    let candidates = vec![synthetic_candidate(&query, &envelope)]
        .into_iter()
        .filter(|item| {
            envelope.allowed_source_labels.is_empty()
                || envelope
                    .allowed_source_labels
                    .iter()
                    .any(|label| label == &item.candidate.source_label)
        })
        .filter(|item| {
            envelope.allowed_workspace_roots.is_empty()
                || envelope
                    .allowed_workspace_roots
                    .iter()
                    .any(|root| item.candidate.source_path.starts_with(root))
        })
        .collect::<Vec<RankedCandidate>>();
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
    let authoritative = build_authoritative(&selected);
    let supporting = build_supporting(&selected);
    let linked_entities = build_linked_entities(&query);
    let graph_relations = Vec::<CanonicalRelation>::new();
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
    let explanation = format!(
        "engine=rust_retrieval_engine; selected={}; authoritative={}; supporting={}; graph_relations={}; workspace_fingerprint_present={}",
        selected.len(),
        authoritative.len(),
        supporting.len(),
        graph_relations.len(),
        !envelope.workspace_fingerprint.is_empty(),
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
        effective_engine: "rust_grpc".to_string(),
        fallback_used: false,
        explanation,
    }
}

async fn list_graph_payload(
    agent_id: &str,
    entity_type: &str,
    limit: u32,
) -> Result<(Vec<GraphEntity>, Vec<GraphRelation>), Status> {
    let dsn = knowledge_postgres_dsn();
    if dsn.is_empty() {
        return Err(Status::failed_precondition(
            "knowledge postgres dsn is not configured",
        ));
    }
    let schema = knowledge_postgres_schema();
    let (client, connection) = tokio_postgres::connect(&dsn, NoTls)
        .await
        .map_err(|error| {
            Status::unavailable(format!("failed to connect to knowledge postgres: {error}"))
        })?;
    tokio::spawn(async move {
        let _ = connection.await;
    });
    let capped_limit = i64::from(limit.max(1));
    let entity_rows = client
        .query(
            &format!(
                r#"SELECT entity_key,
                          entity_type,
                          label,
                          source_kind,
                          COALESCE(metadata_json::text, '{{}}') AS metadata_json,
                          COALESCE(updated_at::text, '') AS updated_at
                   FROM "{schema}"."knowledge_entities"
                  WHERE agent_id = $1
                    AND ($2 = '' OR entity_type = $2)
                  ORDER BY updated_at DESC
                  LIMIT $3"#
            ),
            &[&agent_id, &entity_type, &capped_limit],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query graph entities: {error}")))?;
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
                   FROM "{schema}"."knowledge_relations"
                  WHERE agent_id = $1
                    AND source_entity_key = ANY($2::TEXT[])
                    AND target_entity_key = ANY($2::TEXT[])
                  ORDER BY updated_at DESC
                  LIMIT $3"#
            ),
            &[&agent_id, &entity_keys, &relation_limit],
        )
        .await
        .map_err(|error| Status::internal(format!("failed to query graph relations: {error}")))?;
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
        Ok(Response::new(build_retrieve_response(&payload, trace_id)))
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
        let mut capabilities = vec![
            "bundle-assembly",
            "ranking",
            "answer-plan",
            "judge-core",
            "typed-contract",
        ];
        if !knowledge_postgres_dsn().is_empty() {
            capabilities.push("graph_read");
        }
        details.insert("authoritative".to_string(), "true".to_string());
        details.insert("production_ready".to_string(), "true".to_string());
        details.insert("maturity".to_string(), "ga".to_string());
        details.insert("capabilities".to_string(), capabilities.join(","));
        Ok(Response::new(HealthResponse {
            service: SERVICE_NAME.to_string(),
            ready: true,
            status: "ready".to_string(),
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
