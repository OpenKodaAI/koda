use std::collections::BTreeMap;
use std::ops::{Deref, DerefMut};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, RwLock};
use std::time::Duration;

use bb8::{Pool, PooledConnection, RunError};
use bb8_postgres::PostgresConnectionManager;
use tokio::sync::{OwnedSemaphorePermit, Semaphore};
use tokio_postgres::{Client, NoTls};
use tonic::{Code, Status};

type PgManager = PostgresConnectionManager<NoTls>;

const DEFAULT_POOL_MAX_SIZE: u32 = 6;
const DEFAULT_MIN_IDLE: u32 = 0;
const DEFAULT_ACQUIRE_TIMEOUT_MS: u64 = 1_500;
const DEFAULT_QUERY_TIMEOUT_MS: u64 = 30_000;
const DEFAULT_IDLE_TIMEOUT_SECONDS: u64 = 300;
const DEFAULT_MAX_LIFETIME_SECONDS: u64 = 1_800;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum PostgresWorkload {
    Read,
    Write,
    Health,
    Maintenance,
}

impl PostgresWorkload {
    fn as_str(self) -> &'static str {
        match self {
            Self::Read => "read",
            Self::Write => "write",
            Self::Health => "health",
            Self::Maintenance => "maintenance",
        }
    }
}

#[derive(Debug, Clone)]
pub struct KodaPgPoolConfig {
    pub service_name: String,
    pub dsn: String,
    pub schema: String,
    pub application_name: String,
    pub max_size: u32,
    pub min_idle: u32,
    pub acquire_timeout: Duration,
    pub query_timeout_ms: u64,
    pub idle_timeout: Duration,
    pub max_lifetime: Duration,
    pub read_limit: usize,
    pub write_limit: usize,
    pub health_limit: usize,
    pub maintenance_limit: usize,
}

impl KodaPgPoolConfig {
    pub fn from_env(service_name: &str, service_pool_max_env: &str) -> Self {
        let max_size = env_u32_optional(service_pool_max_env)
            .filter(|value| *value > 0)
            .unwrap_or_else(|| {
                env_u32("KNOWLEDGE_V2_POSTGRES_POOL_MAX_SIZE", DEFAULT_POOL_MAX_SIZE)
            })
            .clamp(1, 256);
        let min_idle =
            env_u32("KNOWLEDGE_V2_POSTGRES_POOL_MIN_IDLE", DEFAULT_MIN_IDLE).min(max_size);
        let acquire_timeout_ms = env_u64(
            "KNOWLEDGE_V2_POSTGRES_ACQUIRE_TIMEOUT_MS",
            DEFAULT_ACQUIRE_TIMEOUT_MS,
        )
        .clamp(50, 60_000);
        let query_timeout_ms = env_u64(
            "KNOWLEDGE_V2_POSTGRES_QUERY_TIMEOUT_MS",
            DEFAULT_QUERY_TIMEOUT_MS,
        )
        .clamp(100, 600_000);
        let idle_timeout_seconds = env_u64(
            "KNOWLEDGE_V2_POSTGRES_IDLE_TIMEOUT_SECONDS",
            DEFAULT_IDLE_TIMEOUT_SECONDS,
        )
        .clamp(1, 86_400);
        let max_lifetime_seconds = env_u64(
            "KNOWLEDGE_V2_POSTGRES_MAX_LIFETIME_SECONDS",
            DEFAULT_MAX_LIFETIME_SECONDS,
        )
        .clamp(1, 86_400);
        Self::new(
            service_name,
            &std::env::var("KNOWLEDGE_V2_POSTGRES_DSN").unwrap_or_default(),
            &std::env::var("KNOWLEDGE_V2_POSTGRES_SCHEMA")
                .unwrap_or_else(|_| "knowledge_v2".to_string()),
            max_size,
            min_idle,
            acquire_timeout_ms,
            query_timeout_ms,
            idle_timeout_seconds,
            max_lifetime_seconds,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub fn new(
        service_name: &str,
        dsn: &str,
        schema: &str,
        max_size: u32,
        min_idle: u32,
        acquire_timeout_ms: u64,
        query_timeout_ms: u64,
        idle_timeout_seconds: u64,
        max_lifetime_seconds: u64,
    ) -> Self {
        let max_size = max_size.clamp(1, 256);
        let read_limit = usize::try_from(max_size)
            .unwrap_or(usize::MAX / 4)
            .saturating_mul(4)
            .max(16);
        let write_limit = usize::try_from(max_size).unwrap_or(usize::MAX).max(1);
        Self {
            service_name: service_name.to_string(),
            dsn: dsn.trim().to_string(),
            schema: normalize_schema(schema),
            application_name: service_name.to_string(),
            max_size,
            min_idle: min_idle.min(max_size),
            acquire_timeout: Duration::from_millis(acquire_timeout_ms.clamp(50, 60_000)),
            query_timeout_ms: query_timeout_ms.clamp(100, 600_000),
            idle_timeout: Duration::from_secs(idle_timeout_seconds.clamp(1, 86_400)),
            max_lifetime: Duration::from_secs(max_lifetime_seconds.clamp(1, 86_400)),
            read_limit,
            write_limit,
            health_limit: 1,
            maintenance_limit: write_limit,
        }
    }
}

#[derive(Debug, Clone)]
pub struct KodaPgPool {
    pool: Pool<PgManager>,
    config: KodaPgPoolConfig,
    gates: Arc<WorkloadGates>,
    metrics: Arc<KodaPgMetrics>,
}

impl KodaPgPool {
    pub async fn connect(config: KodaPgPoolConfig) -> Result<Self, Status> {
        if config.dsn.trim().is_empty() {
            return Err(Status::failed_precondition(
                "knowledge postgres dsn is not configured",
            ));
        }
        let manager = PostgresConnectionManager::new_from_stringlike(&config.dsn, NoTls)
            .map_err(|error| Status::unavailable(format!("invalid postgres dsn: {error}")))?;
        let pool = Pool::builder()
            .max_size(config.max_size)
            .min_idle(Some(config.min_idle))
            .connection_timeout(config.acquire_timeout)
            .idle_timeout(Some(config.idle_timeout))
            .max_lifetime(Some(config.max_lifetime))
            .build(manager)
            .await
            .map_err(|error| {
                Status::unavailable(format!("failed to create postgres pool: {error}"))
            })?;
        Ok(Self {
            gates: Arc::new(WorkloadGates::from_config(&config)),
            metrics: Arc::new(KodaPgMetrics::default()),
            pool,
            config,
        })
    }

    pub async fn connection(
        &self,
        workload: PostgresWorkload,
        operation: &'static str,
    ) -> Result<KodaPgConnection<'_>, Status> {
        let permit = self
            .gates
            .acquire(workload)
            .map_err(|error| Status::resource_exhausted(error.to_string()))?;
        let conn = match self.pool.get().await {
            Ok(conn) => conn,
            Err(RunError::TimedOut) => {
                self.metrics
                    .wait_timeout_total
                    .fetch_add(1, Ordering::Relaxed);
                self.metrics
                    .set_last_error(format!("{operation}: postgres pool acquire timed out"));
                return Err(Status::resource_exhausted(format!(
                    "{operation}: postgres pool acquire timed out"
                )));
            }
            Err(RunError::User(error)) => {
                self.metrics
                    .connect_error_total
                    .fetch_add(1, Ordering::Relaxed);
                self.metrics
                    .reconnect_pending
                    .store(true, Ordering::Relaxed);
                self.metrics.set_last_error(format!(
                    "{operation}: failed to acquire postgres connection: {error}"
                ));
                return Err(Status::unavailable(format!(
                    "{operation}: failed to acquire postgres connection: {error}"
                )));
            }
        };
        if let Err(error) = conn.batch_execute(&self.connection_setup_sql()).await {
            return Err(self.status_from_pg_error(operation, error));
        }
        self.metrics.record_successful_checkout();
        Ok(KodaPgConnection {
            conn,
            _permit: permit,
            pool: self,
        })
    }

    pub fn record_query_error(&self, operation: &str, error: &tokio_postgres::Error) {
        if is_query_timeout(error) {
            self.metrics
                .query_timeout_total
                .fetch_add(1, Ordering::Relaxed);
        }
        if error.is_closed() {
            self.metrics
                .connect_error_total
                .fetch_add(1, Ordering::Relaxed);
            self.metrics
                .reconnect_pending
                .store(true, Ordering::Relaxed);
        }
        self.metrics.set_last_error(format!("{operation}: {error}"));
    }

    pub fn status_from_pg_error(&self, operation: &str, error: tokio_postgres::Error) -> Status {
        self.record_query_error(operation, &error);
        if is_query_timeout(&error) {
            Status::deadline_exceeded(format!("{operation}: postgres query timed out"))
        } else if error.is_closed() {
            Status::unavailable(format!(
                "{operation}: postgres connection unavailable: {error}"
            ))
        } else {
            Status::internal(format!("{operation}: postgres query failed: {error}"))
        }
    }

    pub fn snapshot(&self) -> KodaPgPoolSnapshot {
        let state = self.pool.state();
        KodaPgPoolSnapshot {
            pool_max_size: self.config.max_size,
            pool_idle: state.idle_connections,
            pool_in_use: state.connections.saturating_sub(state.idle_connections),
            acquire_timeout_ms: millis(self.config.acquire_timeout),
            query_timeout_ms: self.config.query_timeout_ms,
            wait_timeout_total: self.metrics.wait_timeout_total.load(Ordering::Relaxed),
            connect_error_total: self.metrics.connect_error_total.load(Ordering::Relaxed),
            query_timeout_total: self.metrics.query_timeout_total.load(Ordering::Relaxed),
            reconnect_total: self.metrics.reconnect_total.load(Ordering::Relaxed),
            last_error: self.metrics.last_error(),
            read_in_flight: self.gates.in_flight(PostgresWorkload::Read),
            write_in_flight: self.gates.in_flight(PostgresWorkload::Write),
            health_in_flight: self.gates.in_flight(PostgresWorkload::Health),
            maintenance_in_flight: self.gates.in_flight(PostgresWorkload::Maintenance),
        }
    }

    pub fn health_details(&self) -> BTreeMap<String, String> {
        self.snapshot().details()
    }

    fn connection_setup_sql(&self) -> String {
        format!(
            "SET application_name = {}; SET statement_timeout = {}; SET search_path TO {};",
            quote_literal(&self.config.application_name),
            self.config.query_timeout_ms,
            quote_ident(&self.config.schema)
        )
    }
}

pub struct KodaPgConnection<'a> {
    conn: PooledConnection<'a, PgManager>,
    _permit: WorkloadPermit,
    pool: &'a KodaPgPool,
}

impl Deref for KodaPgConnection<'_> {
    type Target = Client;

    fn deref(&self) -> &Self::Target {
        &self.conn
    }
}

impl DerefMut for KodaPgConnection<'_> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.conn
    }
}

impl KodaPgConnection<'_> {
    pub fn pool(&self) -> &KodaPgPool {
        self.pool
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct KodaPgPoolSnapshot {
    pub pool_max_size: u32,
    pub pool_idle: u32,
    pub pool_in_use: u32,
    pub acquire_timeout_ms: u64,
    pub query_timeout_ms: u64,
    pub wait_timeout_total: u64,
    pub connect_error_total: u64,
    pub query_timeout_total: u64,
    pub reconnect_total: u64,
    pub last_error: String,
    pub read_in_flight: usize,
    pub write_in_flight: usize,
    pub health_in_flight: usize,
    pub maintenance_in_flight: usize,
}

impl KodaPgPoolSnapshot {
    pub fn details(&self) -> BTreeMap<String, String> {
        let mut details = BTreeMap::new();
        details.insert(
            "postgres_pool_max_size".to_string(),
            self.pool_max_size.to_string(),
        );
        details.insert("postgres_pool_idle".to_string(), self.pool_idle.to_string());
        details.insert(
            "postgres_pool_in_use".to_string(),
            self.pool_in_use.to_string(),
        );
        details.insert(
            "postgres_acquire_timeout_ms".to_string(),
            self.acquire_timeout_ms.to_string(),
        );
        details.insert(
            "postgres_query_timeout_ms".to_string(),
            self.query_timeout_ms.to_string(),
        );
        details.insert(
            "postgres_wait_timeout_total".to_string(),
            self.wait_timeout_total.to_string(),
        );
        details.insert(
            "postgres_connect_error_total".to_string(),
            self.connect_error_total.to_string(),
        );
        details.insert(
            "postgres_query_timeout_total".to_string(),
            self.query_timeout_total.to_string(),
        );
        details.insert(
            "postgres_reconnect_total".to_string(),
            self.reconnect_total.to_string(),
        );
        details.insert("postgres_last_error".to_string(), self.last_error.clone());
        details.insert(
            "postgres_workload_read_in_flight".to_string(),
            self.read_in_flight.to_string(),
        );
        details.insert(
            "postgres_workload_write_in_flight".to_string(),
            self.write_in_flight.to_string(),
        );
        details.insert(
            "postgres_workload_health_in_flight".to_string(),
            self.health_in_flight.to_string(),
        );
        details.insert(
            "postgres_workload_maintenance_in_flight".to_string(),
            self.maintenance_in_flight.to_string(),
        );
        details
    }
}

#[derive(Debug)]
struct WorkloadGate {
    limit: usize,
    semaphore: Arc<Semaphore>,
    in_flight: Arc<AtomicUsize>,
}

#[derive(Debug)]
struct WorkloadGates {
    read: WorkloadGate,
    write: WorkloadGate,
    health: WorkloadGate,
    maintenance: WorkloadGate,
}

impl WorkloadGates {
    fn from_config(config: &KodaPgPoolConfig) -> Self {
        Self::new(
            config.read_limit,
            config.write_limit,
            config.health_limit,
            config.maintenance_limit,
        )
    }

    fn new(read: usize, write: usize, health: usize, maintenance: usize) -> Self {
        Self {
            read: WorkloadGate::new(read),
            write: WorkloadGate::new(write),
            health: WorkloadGate::new(health),
            maintenance: WorkloadGate::new(maintenance),
        }
    }

    fn acquire(&self, workload: PostgresWorkload) -> Result<WorkloadPermit, WorkloadSaturated> {
        self.gate(workload).acquire(workload)
    }

    fn in_flight(&self, workload: PostgresWorkload) -> usize {
        self.gate(workload).in_flight.load(Ordering::Relaxed)
    }

    fn gate(&self, workload: PostgresWorkload) -> &WorkloadGate {
        match workload {
            PostgresWorkload::Read => &self.read,
            PostgresWorkload::Write => &self.write,
            PostgresWorkload::Health => &self.health,
            PostgresWorkload::Maintenance => &self.maintenance,
        }
    }
}

impl WorkloadGate {
    fn new(limit: usize) -> Self {
        let limit = limit.max(1);
        Self {
            limit,
            semaphore: Arc::new(Semaphore::new(limit)),
            in_flight: Arc::new(AtomicUsize::new(0)),
        }
    }

    fn acquire(&self, workload: PostgresWorkload) -> Result<WorkloadPermit, WorkloadSaturated> {
        let permit = self
            .semaphore
            .clone()
            .try_acquire_owned()
            .map_err(|_| WorkloadSaturated {
                workload,
                limit: self.limit,
            })?;
        self.in_flight.fetch_add(1, Ordering::Relaxed);
        Ok(WorkloadPermit {
            _permit: permit,
            in_flight: self.in_flight.clone(),
        })
    }
}

#[derive(Debug)]
struct WorkloadSaturated {
    workload: PostgresWorkload,
    limit: usize,
}

impl std::fmt::Display for WorkloadSaturated {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            formatter,
            "postgres workload '{}' is saturated (limit={})",
            self.workload.as_str(),
            self.limit
        )
    }
}

#[derive(Debug)]
struct WorkloadPermit {
    _permit: OwnedSemaphorePermit,
    in_flight: Arc<AtomicUsize>,
}

impl Drop for WorkloadPermit {
    fn drop(&mut self) {
        self.in_flight.fetch_sub(1, Ordering::Relaxed);
    }
}

#[derive(Debug, Default)]
struct KodaPgMetrics {
    wait_timeout_total: AtomicU64,
    connect_error_total: AtomicU64,
    query_timeout_total: AtomicU64,
    reconnect_total: AtomicU64,
    reconnect_pending: AtomicBool,
    last_error: RwLock<String>,
}

impl KodaPgMetrics {
    fn record_successful_checkout(&self) {
        if self.reconnect_pending.swap(false, Ordering::Relaxed) {
            self.reconnect_total.fetch_add(1, Ordering::Relaxed);
        }
    }

    fn set_last_error(&self, value: String) {
        if let Ok(mut guard) = self.last_error.write() {
            *guard = value;
        }
    }

    fn last_error(&self) -> String {
        self.last_error
            .read()
            .map(|guard| guard.clone())
            .unwrap_or_default()
    }
}

fn env_u32_optional(key: &str) -> Option<u32> {
    std::env::var(key)
        .ok()
        .and_then(|raw| raw.trim().parse::<u32>().ok())
}

fn env_u32(key: &str, default: u32) -> u32 {
    env_u32_optional(key).unwrap_or(default)
}

fn env_u64(key: &str, default: u64) -> u64 {
    std::env::var(key)
        .ok()
        .and_then(|raw| raw.trim().parse::<u64>().ok())
        .unwrap_or(default)
}

fn millis(value: Duration) -> u64 {
    u64::try_from(value.as_millis()).unwrap_or(u64::MAX)
}

fn normalize_schema(value: &str) -> String {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        "knowledge_v2".to_string()
    } else {
        trimmed.to_string()
    }
}

fn quote_ident(identifier: &str) -> String {
    format!("\"{}\"", identifier.replace('"', "\"\""))
}

fn quote_literal(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

fn is_query_timeout(error: &tokio_postgres::Error) -> bool {
    error
        .as_db_error()
        .is_some_and(|db_error| *db_error.code() == tokio_postgres::error::SqlState::QUERY_CANCELED)
}

pub fn status_code_name(status: &Status) -> &'static str {
    match status.code() {
        Code::Ok => "ok",
        Code::Cancelled => "cancelled",
        Code::Unknown => "unknown",
        Code::InvalidArgument => "invalid_argument",
        Code::DeadlineExceeded => "deadline_exceeded",
        Code::NotFound => "not_found",
        Code::AlreadyExists => "already_exists",
        Code::PermissionDenied => "permission_denied",
        Code::ResourceExhausted => "resource_exhausted",
        Code::FailedPrecondition => "failed_precondition",
        Code::Aborted => "aborted",
        Code::OutOfRange => "out_of_range",
        Code::Unimplemented => "unimplemented",
        Code::Internal => "internal",
        Code::Unavailable => "unavailable",
        Code::DataLoss => "data_loss",
        Code::Unauthenticated => "unauthenticated",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;

    #[test]
    fn config_clamps_and_derives_workload_limits() {
        let config = KodaPgPoolConfig::new("svc", "postgresql://example", "", 2, 99, 1, 1, 0, 0);
        assert_eq!(config.schema, "knowledge_v2");
        assert_eq!(config.max_size, 2);
        assert_eq!(config.min_idle, 2);
        assert_eq!(config.read_limit, 16);
        assert_eq!(config.write_limit, 2);
        assert_eq!(config.health_limit, 1);
        assert_eq!(millis(config.acquire_timeout), 50);
        assert_eq!(config.query_timeout_ms, 100);
    }

    #[test]
    fn workload_gate_fails_closed_when_saturated() {
        let gates = WorkloadGates::new(1, 1, 1, 1);
        let permit = gates.acquire(PostgresWorkload::Read).expect("first permit");
        assert_eq!(gates.in_flight(PostgresWorkload::Read), 1);
        let blocked = gates
            .acquire(PostgresWorkload::Read)
            .expect_err("saturated");
        assert_eq!(
            blocked.to_string(),
            "postgres workload 'read' is saturated (limit=1)"
        );
        drop(permit);
        assert_eq!(gates.in_flight(PostgresWorkload::Read), 0);
        assert!(gates.acquire(PostgresWorkload::Read).is_ok());
    }

    #[test]
    fn pool_snapshot_details_are_stable() {
        let snapshot = KodaPgPoolSnapshot {
            pool_max_size: 6,
            pool_idle: 2,
            pool_in_use: 4,
            acquire_timeout_ms: 1500,
            query_timeout_ms: 30000,
            wait_timeout_total: 1,
            connect_error_total: 2,
            query_timeout_total: 3,
            reconnect_total: 4,
            last_error: "x".to_string(),
            read_in_flight: 5,
            write_in_flight: 6,
            health_in_flight: 7,
            maintenance_in_flight: 8,
        };
        let details = snapshot.details();
        assert_eq!(details["postgres_pool_max_size"], "6");
        assert_eq!(details["postgres_pool_idle"], "2");
        assert_eq!(details["postgres_pool_in_use"], "4");
        assert_eq!(details["postgres_wait_timeout_total"], "1");
        assert_eq!(details["postgres_workload_health_in_flight"], "7");
    }

    #[test]
    fn reconnect_metric_counts_first_success_after_connection_error() {
        let metrics = KodaPgMetrics::default();
        metrics.record_successful_checkout();
        assert_eq!(metrics.reconnect_total.load(Ordering::Relaxed), 0);

        metrics.reconnect_pending.store(true, Ordering::Relaxed);
        metrics.record_successful_checkout();
        metrics.record_successful_checkout();

        assert_eq!(metrics.reconnect_total.load(Ordering::Relaxed), 1);
    }

    #[tokio::test]
    #[ignore = "requires local PostgreSQL; run with KODA_INTEGRATION_TESTS=1 cargo test -p koda-postgres -- --ignored"]
    async fn live_pool_enforces_limits_and_recovers_after_backend_termination() {
        if std::env::var("KODA_INTEGRATION_TESTS").ok().as_deref() != Some("1") {
            return;
        }
        let dsn = std::env::var("KODA_POSTGRES_TEST_DSN")
            .or_else(|_| std::env::var("KNOWLEDGE_V2_POSTGRES_DSN"))
            .expect("KODA_POSTGRES_TEST_DSN or KNOWLEDGE_V2_POSTGRES_DSN is required");
        let schema = format!("koda_pg_pool_test_{}", std::process::id());
        let schema_ident = quote_ident(&schema);
        let (admin, admin_connection) = tokio_postgres::connect(&dsn, NoTls)
            .await
            .expect("admin connect");
        tokio::spawn(async move {
            let _ = admin_connection.await;
        });
        admin
            .batch_execute(&format!("CREATE SCHEMA IF NOT EXISTS {schema_ident}"))
            .await
            .expect("create schema");

        let pool = KodaPgPool::connect(KodaPgPoolConfig::new(
            "koda-postgres-test",
            &dsn,
            &schema,
            1,
            0,
            100,
            500,
            5,
            60,
        ))
        .await
        .expect("pool connect");

        let held = pool
            .connection(PostgresWorkload::Read, "hold connection")
            .await
            .expect("hold connection");
        let started = Instant::now();
        let blocked = match pool
            .connection(PostgresWorkload::Read, "blocked checkout")
            .await
        {
            Ok(_) => panic!("pool_max=1 must backpressure concurrent checkout"),
            Err(status) => status,
        };
        assert_eq!(blocked.code(), Code::ResourceExhausted);
        assert!(
            started.elapsed() < Duration::from_secs(2),
            "checkout should fail fast under pool pressure"
        );
        drop(held);

        let conn = pool
            .connection(PostgresWorkload::Read, "read backend pid")
            .await
            .expect("connection before terminate");
        let pid: i32 = conn
            .query_one("SELECT pg_backend_pid()", &[])
            .await
            .expect("backend pid")
            .get(0);
        admin
            .execute("SELECT pg_terminate_backend($1)", &[&pid])
            .await
            .expect("terminate backend");
        drop(conn);

        let conn = pool
            .connection(PostgresWorkload::Read, "reconnect after terminate")
            .await
            .expect("pool should reconnect");
        let one: i32 = conn
            .query_one("SELECT 1", &[])
            .await
            .expect("query after reconnect")
            .get(0);
        assert_eq!(one, 1);

        admin
            .batch_execute(&format!("DROP SCHEMA IF EXISTS {schema_ident} CASCADE"))
            .await
            .expect("drop schema");
    }
}
