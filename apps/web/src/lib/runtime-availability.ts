import type {
  RuntimeAvailability,
  RuntimeAvailabilityStatus,
  RuntimeAgentHealth,
  RuntimeEnvironment,
  RuntimeQueueItem,
  RuntimeReadiness,
} from "@/lib/runtime-types";

export interface RuntimeEndpointSnapshot<T> {
  ok: boolean;
  status: number;
  data: T | null;
  error?: string;
}

interface RuntimeAvailabilityInputs {
  readiness: RuntimeEndpointSnapshot<RuntimeReadiness>;
  health: RuntimeEndpointSnapshot<RuntimeAgentHealth>;
  queues: RuntimeEndpointSnapshot<{ items?: RuntimeQueueItem[] }>;
  environments: RuntimeEndpointSnapshot<{ items?: RuntimeEnvironment[] }>;
  hasRuntimeToken: boolean;
}

function availability(errors: string[] = []): RuntimeAvailability {
  return {
    health: "unknown",
    database: "unknown",
    runtime: "unknown",
    browser: "unknown",
    attach: "unknown",
    errors,
  };
}

export function withAvailabilityStatus(
  current: RuntimeAvailabilityStatus,
  next: RuntimeAvailabilityStatus
): RuntimeAvailabilityStatus {
  if (current === "offline" || next === "offline") return "offline";
  if (current === "disabled" || next === "disabled") {
    return next === "available" ? "partial" : "disabled";
  }
  if (current === "available" && next === "available") return "available";
  if (current === "unknown") return next;
  if (next === "unknown") return current;
  if (current === next) return current;
  return "partial";
}

export function resolveRuntimeAvailability({
  readiness,
  health,
  queues,
  environments,
  hasRuntimeToken,
}: RuntimeAvailabilityInputs): RuntimeAvailability {
  const errors = [readiness.error, health.error, queues.error, environments.error].filter(
    (value): value is string => Boolean(value)
  );
  const snapshot = health.data?.runtime ?? null;
  const runtimeRoutesAvailable = queues.ok || environments.ok;
  const readinessReady = Boolean(readiness.data?.ready);
  const startupPhase = String(readiness.data?.startup?.phase || "");
  const runtimeRoutesDisabled =
    readiness.ok && queues.status === 404 && environments.status === 404;
  const runtimeSnapshotAvailable = Boolean(snapshot && !snapshot.error);
  const databaseReady = Boolean(
    health.data?.database?.ready ?? health.data?.database?.reachable,
  );
  const hasBrowserSurface =
    (environments.data?.items || []).some(
      (env) => Boolean(env.browser_transport || env.novnc_port || env.display_id)
    ) || Boolean(snapshot?.browser_sessions_active);
  const state = availability(errors);

  state.health =
    readiness.ok && startupPhase === "ready"
      ? "available"
      : readiness.ok
        ? "partial"
        : health.ok
          ? "partial"
          : "offline";
  state.database = databaseReady
    ? "available"
    : readiness.ok
      ? "partial"
      : health.ok
        ? "unavailable"
        : "unknown";
  state.runtime = runtimeRoutesAvailable && readinessReady
    ? "available"
    : !readiness.ok && !health.ok
      ? "offline"
    : runtimeRoutesDisabled
      ? "disabled"
        : readiness.ok || runtimeSnapshotAvailable
          ? "partial"
          : "unavailable";
  state.browser = hasBrowserSurface
    ? state.runtime === "available"
      ? "available"
      : "partial"
    : state.runtime === "available"
      ? "partial"
      : "unavailable";
  state.attach = hasRuntimeToken
    ? state.runtime === "available"
      ? "available"
      : state.runtime
    : "unavailable";

  return state;
}
