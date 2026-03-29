import "server-only";

import {
  getControlPlaneBot,
  type ControlPlaneBot,
  getServerControlPlaneRuntimeAccess,
  type ControlPlaneServerRuntimeAccess,
} from "@/lib/control-plane";
import { resolveRuntimeAvailability } from "@/lib/runtime-availability";
import { normalizeRuntimeRequestError } from "@/lib/runtime-errors";
import { translateLiteralForLanguage } from "@/lib/i18n";
import type {
  RuntimeBotHealth,
  RuntimeBrowserSession,
  RuntimeBrowserState,
  RuntimeCheckpoint,
  RuntimeEnvironment,
  RuntimeEvent,
  RuntimeGuardrailHit,
  RuntimeOverview,
  RuntimeQueueItem,
  RuntimeReadiness,
  RuntimeSessions,
  RuntimeTaskBundle,
  RuntimeTaskDetail,
  RuntimeWarning,
  RuntimeWorkspaceDiff,
  RuntimeWorkspaceStatus,
  RuntimeWorkspaceTreeEntry,
} from "@/lib/runtime-types";

type RuntimeRequestInit = Omit<RequestInit, "body"> & {
  body?: BodyInit | null;
  timeoutMs?: number;
};

interface RuntimeJsonResponse<T> {
  ok: boolean;
  status: number;
  data: T | null;
  error?: string;
}

type RuntimeAccessCapability = "read" | "mutate" | "attach";

type RuntimeAccessOptions = {
  capability?: RuntimeAccessCapability;
  includeSensitive?: boolean;
};

export interface RuntimeBotConfig {
  id: string;
  label: string;
  color: string;
  colorRgb: string;
  healthUrl: string;
  runtimeBaseUrl: string;
  runtimeRequestToken: string | null;
  accessScopeToken: string | null;
  status?: string;
}

const DEFAULT_TIMEOUT_MS = Number.parseInt(
  process.env.RUNTIME_FETCH_TIMEOUT_MS || "10000",
  10,
);

export class RuntimeRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "RuntimeRequestError";
    this.status = status;
  }
}

function deriveRuntimeBaseUrl(healthUrl: string) {
  try {
    const parsed = new URL(healthUrl);
    if (parsed.pathname.endsWith("/health")) {
      parsed.pathname = parsed.pathname.slice(0, -"/health".length) || "/";
    }
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return healthUrl.replace(/\/health\/?$/, "");
  }
}

function buildBotConfigFromControlPlane(bot: ControlPlaneBot): RuntimeBotConfig {
  const appearance = bot.appearance || {};
  const runtimeEndpoint = bot.runtime_endpoint || {};
  const healthUrl =
    String(runtimeEndpoint.health_url || "").trim() ||
    `http://127.0.0.1:${String(runtimeEndpoint.health_port || "8080")}/health`;

  return {
    id: bot.id,
    label: String(appearance.label || bot.display_name || bot.id),
    color: String(appearance.color || "#A7ADB4"),
    colorRgb: String(appearance.color_rgb || "167, 173, 180"),
    healthUrl,
    runtimeBaseUrl:
      String(runtimeEndpoint.runtime_base_url || "").trim() ||
      deriveRuntimeBaseUrl(healthUrl),
    runtimeRequestToken: null,
    accessScopeToken: null,
    status: bot.status,
  };
}

function applyRuntimeAccess(
  bot: RuntimeBotConfig,
  runtimeAccess: ControlPlaneServerRuntimeAccess | null,
): RuntimeBotConfig {
  if (!runtimeAccess) {
    return bot;
  }

  return {
    ...bot,
    healthUrl: runtimeAccess.health_url || bot.healthUrl,
    runtimeBaseUrl: runtimeAccess.runtime_base_url || bot.runtimeBaseUrl,
    runtimeRequestToken:
      runtimeAccess.runtime_request_token || bot.runtimeRequestToken,
    accessScopeToken: runtimeAccess.access_scope_token || bot.accessScopeToken,
  };
}

export async function getRuntimeBotConfig(
  botId: string,
  options: RuntimeAccessOptions = {},
): Promise<RuntimeBotConfig | null> {
  const [botFromControlPlane, runtimeAccess] = await Promise.all([
    getControlPlaneBot(botId).catch(() => null),
    getServerControlPlaneRuntimeAccess(botId, options).catch(() => null),
  ]);

  const baseBot = botFromControlPlane
    ? buildBotConfigFromControlPlane(botFromControlPlane)
    : null;
  if (!baseBot) {
    return null;
  }

  return applyRuntimeAccess(baseBot, runtimeAccess);
}

export async function requireRuntimeBotConfig(
  botId: string,
  options: RuntimeAccessOptions = {},
): Promise<RuntimeBotConfig> {
  const bot = await getRuntimeBotConfig(botId, options);
  if (!bot) {
    throw new RuntimeRequestError("Bot not found", 404);
  }
  return bot;
}

function buildRuntimeUrl(
  baseUrl: string,
  pathname: string,
  searchParams?: URLSearchParams,
) {
  const target = new URL(
    pathname,
    baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`,
  );
  if (searchParams) {
    target.search = searchParams.toString();
  }
  return target.toString();
}

async function parseResponseBody(response: Response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json().catch(() => null);
  }
  return response.text().catch(() => "");
}

async function runtimeFetchForBot(
  bot: RuntimeBotConfig,
  pathname: string,
  init: RuntimeRequestInit = {},
  searchParams?: URLSearchParams,
) {
  const headers = new Headers(init.headers);

  if (bot.runtimeRequestToken) {
    headers.set("X-Runtime-Token", bot.runtimeRequestToken);
  }

  if (
    !headers.has("X-Runtime-Access-Scope") &&
    bot.accessScopeToken &&
    searchParams?.get("include_sensitive")?.trim().toLowerCase() === "true"
  ) {
    headers.set("X-Runtime-Access-Scope", bot.accessScopeToken);
  }

  return fetch(buildRuntimeUrl(bot.runtimeBaseUrl, pathname, searchParams), {
    ...init,
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(init.timeoutMs ?? DEFAULT_TIMEOUT_MS),
  });
}

export async function runtimeFetch(
  botId: string,
  pathname: string,
  init: RuntimeRequestInit = {},
  searchParams?: URLSearchParams,
  access: RuntimeAccessOptions = {},
) {
  const bot = await requireRuntimeBotConfig(botId, {
    capability: access.capability ?? "read",
    includeSensitive:
      access.includeSensitive ??
      searchParams?.get("include_sensitive")?.trim().toLowerCase() === "true",
  });
  return runtimeFetchForBot(bot, pathname, init, searchParams);
}

async function runtimeFetchJsonForBot<T>(
  bot: RuntimeBotConfig,
  pathname: string,
  init: RuntimeRequestInit = {},
  searchParams?: URLSearchParams,
): Promise<RuntimeJsonResponse<T>> {
  const timeoutMs = init.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  try {
    const response = await runtimeFetchForBot(
      bot,
      pathname,
      { ...init, timeoutMs },
      searchParams,
    );
    const body = await parseResponseBody(response);
    const error =
      !response.ok && body && typeof body === "object" && "error" in body
        ? String(body.error)
        : !response.ok
          ? `Runtime request failed with status ${response.status}`
          : undefined;

    return {
      ok: response.ok,
      status: response.status,
      data: response.ok ? (body as T) : null,
      error,
    };
  } catch (error) {
    return {
      ok: false,
      status: 503,
      data: null,
      error: normalizeRuntimeRequestError(error, timeoutMs),
    };
  }
}

export async function runtimeFetchJson<T>(
  botId: string,
  pathname: string,
  init: RuntimeRequestInit = {},
  searchParams?: URLSearchParams,
  access: RuntimeAccessOptions = {},
): Promise<RuntimeJsonResponse<T>> {
  const bot = await requireRuntimeBotConfig(botId, {
    capability: access.capability ?? "read",
    includeSensitive:
      access.includeSensitive ??
      searchParams?.get("include_sensitive")?.trim().toLowerCase() === "true",
  });
  return runtimeFetchJsonForBot(bot, pathname, init, searchParams);
}

function buildRuntimeSnapshot(
  queues: RuntimeQueueItem[],
  environments: RuntimeEnvironment[],
) {
  const activeEnvironments = environments.filter((env) =>
    ["active", "cleaning"].includes(String(env.status || "")),
  );
  const retainedEnvironments = environments.filter(
    (env) => String(env.status || "") === "retained",
  );
  const recoveryBacklog = environments.filter((env) => {
    const phase = String(env.current_phase || "").toLowerCase();
    const status = String(env.status || "").toLowerCase();
    return phase.includes("recover") || status.includes("recover") || status === "failed";
  }).length;
  const cleanupBacklog = environments.filter((env) => {
    const phase = String(env.current_phase || "").toLowerCase();
    const status = String(env.status || "").toLowerCase();
    return phase.includes("cleanup") || status === "cleaning";
  }).length;
  const browserSessionsActive = environments.filter((env) =>
    Boolean(env.browser_transport || env.novnc_port || env.display_id),
  ).length;

  return {
    active_environments: activeEnvironments.length,
    retained_environments: retainedEnvironments.length,
    stale_environments: 0,
    cleanup_backlog: cleanupBacklog,
    recovery_backlog: recoveryBacklog,
    browser_sessions_active: browserSessionsActive,
    queues,
  };
}

function buildHealthFromReadiness(
  readiness: RuntimeReadiness | null,
  snapshot: ReturnType<typeof buildRuntimeSnapshot> | null,
): RuntimeBotHealth | null {
  if (!readiness && !snapshot) {
    return null;
  }

  return {
    status: readiness?.ready ? "ok" : "degraded",
    database: {
      ready:
        readiness?.knowledge_v2?.primary_backend?.ready ??
        readiness?.ready ??
        false,
    },
    runtime: snapshot,
  };
}

async function fetchReadiness(
  bot: RuntimeBotConfig,
): Promise<RuntimeJsonResponse<RuntimeReadiness>> {
  return runtimeFetchJsonForBot<RuntimeReadiness>(bot, "/api/runtime/readiness");
}

export async function getRuntimeOverview(
  botId: string,
  language?: string | null,
): Promise<RuntimeOverview> {
  const bot = await requireRuntimeBotConfig(botId);
  const [readiness, queues, environments] = await Promise.all([
    fetchReadiness(bot),
    runtimeFetchJsonForBot<{ items?: RuntimeQueueItem[] }>(
      bot,
      "/api/runtime/queues",
    ),
    runtimeFetchJsonForBot<{ items?: RuntimeEnvironment[] }>(
      bot,
      "/api/runtime/environments",
    ),
  ]);

  const queueItems = queues.data?.items ?? [];
  const runtimeEnvironments = environments.data?.items ?? [];
  const snapshot = buildRuntimeSnapshot(queueItems, runtimeEnvironments);
  const health = {
    ok: readiness.ok,
    status: readiness.status,
    data: buildHealthFromReadiness(readiness.data, snapshot),
    error: readiness.error,
  };
  const availabilityState = resolveRuntimeAvailability({
    readiness,
    health,
    queues,
    environments,
    hasRuntimeToken: Boolean(bot.runtimeRequestToken),
  });

  const activeTaskIds = Array.from(
    new Set(
      [
        ...queueItems
          .filter((item) =>
            ["queued", "running", "retrying"].includes(
              String(item.status || ""),
            ),
          )
          .map((item) => item.task_id),
        ...runtimeEnvironments
          .filter((env) =>
            ["active", "cleaning"].includes(String(env.status || "")),
          )
          .map((env) => env.task_id),
      ].filter((taskId) => Number.isFinite(taskId)),
    ),
  );
  const retainedTaskIds = Array.from(
    new Set(
      runtimeEnvironments
        .filter((env) => String(env.status || "") === "retained")
        .map((env) => env.task_id),
    ),
  );
  const incidents = [
    readiness.data?.startup?.phase &&
    readiness.data.startup.phase !== "ready"
      ? translateLiteralForLanguage(
          language,
          "Bootstrap do runtime em fase {{phase}}",
          { phase: readiness.data.startup.phase },
        )
      : null,
    readiness.data?.background_loops &&
    !readiness.data.background_loops.critical_ready
      ? translateLiteralForLanguage(
          language,
          "{{count}} loop(s) críticos degradados",
          {
            count:
              readiness.data.background_loops.degraded_loops?.length ??
              0,
          },
        )
      : null,
    readiness.data?.knowledge_v2 &&
    readiness.data.knowledge_v2.ready === false
      ? translateLiteralForLanguage(
          language,
          "Knowledge runtime degradado",
        )
      : null,
    snapshot?.stale_environments
      ? translateLiteralForLanguage(language, "{{count}} ambiente(s) sem heartbeat recente", {
          count: snapshot.stale_environments,
        })
      : null,
    snapshot?.recovery_backlog
      ? translateLiteralForLanguage(language, "{{count}} ambiente(s) aguardando recovery", {
          count: snapshot.recovery_backlog,
        })
      : null,
    snapshot?.cleanup_backlog
      ? translateLiteralForLanguage(language, "{{count}} ambiente(s) aguardando cleanup", {
          count: snapshot.cleanup_backlog,
        })
      : null,
    availabilityState.runtime === "disabled"
      ? translateLiteralForLanguage(language, "Runtime frontend desabilitado")
      : availabilityState.runtime === "partial"
        ? translateLiteralForLanguage(language, "Runtime frontend degradado")
        : availabilityState.runtime === "offline" ||
            availabilityState.runtime === "unavailable"
          ? translateLiteralForLanguage(language, "Runtime indisponível")
          : null,
  ].filter((value): value is string => Boolean(value));

  return {
    botId: bot.id,
    botLabel: bot.label,
    botColor: bot.color,
    baseUrl: bot.runtimeBaseUrl,
    fetchedAt: new Date().toISOString(),
    health: health.data,
    snapshot,
    readiness: readiness.data,
    availability: availabilityState,
    queues: queueItems,
    environments: runtimeEnvironments,
    incidents,
    activeTaskIds,
    retainedTaskIds,
  };
}

export async function getRuntimeTaskSnapshot(
  botId: string,
  taskId: number,
  options: { includeSensitive?: boolean } = {},
) {
  const searchParams = new URLSearchParams();
  if (options.includeSensitive) {
    searchParams.set("include_sensitive", "true");
  }

  return runtimeFetchJson<{
    task?: RuntimeTaskDetail;
    environment?: RuntimeEnvironment | null;
    warnings?: RuntimeWarning[];
    guardrails?: RuntimeGuardrailHit[];
    asset_refs?: Array<Record<string, unknown>>;
  }>(
    botId,
    `/api/runtime/tasks/${taskId}`,
    {},
    searchParams.size ? searchParams : undefined,
  );
}

export async function listRuntimeTaskSnapshots(
  botId: string,
  taskIds: number[],
  options: { includeSensitive?: boolean } = {},
) {
  const uniqueTaskIds = Array.from(
    new Set(taskIds.filter((taskId) => Number.isFinite(taskId))),
  );

  const results = await Promise.all(
    uniqueTaskIds.map(async (taskId) => ({
      taskId,
      response: await getRuntimeTaskSnapshot(botId, taskId, options),
    })),
  );

  return new Map(
    results
      .map(({ taskId, response }) =>
        response.ok && response.data?.task ? ([taskId, response.data] as const) : null,
      )
      .filter(
        (
          entry,
        ): entry is readonly [
          number,
          {
            task?: RuntimeTaskDetail;
            environment?: RuntimeEnvironment | null;
            warnings?: RuntimeWarning[];
            guardrails?: RuntimeGuardrailHit[];
            asset_refs?: Array<Record<string, unknown>>;
          },
        ] => Boolean(entry),
      ),
  );
}

export async function getRuntimeTaskBundle(
  botId: string,
  taskId: number,
): Promise<RuntimeTaskBundle> {
  const bot = await requireRuntimeBotConfig(botId);
  const [
    detail,
    events,
    artifacts,
    checkpoints,
    terminals,
    browser,
    workspaceTree,
    workspaceStatus,
    workspaceDiff,
    services,
    resources,
    loop,
    sessions,
  ] = await Promise.all([
    runtimeFetchJsonForBot<{
      task?: RuntimeTaskDetail;
      environment?: RuntimeEnvironment | null;
      warnings?: RuntimeTaskBundle["warnings"];
      guardrails?: RuntimeTaskBundle["guardrails"];
    }>(bot, `/api/runtime/tasks/${taskId}`),
    runtimeFetchJsonForBot<{ items?: RuntimeEvent[] }>(
      bot,
      `/api/runtime/tasks/${taskId}/events`,
    ),
    runtimeFetchJsonForBot<{ items?: RuntimeTaskBundle["artifacts"] }>(
      bot,
      `/api/runtime/tasks/${taskId}/artifacts`,
    ),
    runtimeFetchJsonForBot<{ items?: RuntimeCheckpoint[] }>(
      bot,
      `/api/runtime/tasks/${taskId}/checkpoints`,
    ),
    runtimeFetchJsonForBot<{ items?: RuntimeTaskBundle["terminals"] }>(
      bot,
      `/api/runtime/tasks/${taskId}/terminals`,
    ),
    runtimeFetchJsonForBot<{
      browser?: RuntimeBrowserState;
      sessions?: RuntimeBrowserSession[];
    }>(bot, `/api/runtime/tasks/${taskId}/browser`),
    runtimeFetchJsonForBot<{ items?: RuntimeWorkspaceTreeEntry[] }>(
      bot,
      `/api/runtime/tasks/${taskId}/workspace/tree`,
    ),
    runtimeFetchJsonForBot<RuntimeWorkspaceStatus>(
      bot,
      `/api/runtime/tasks/${taskId}/workspace/status`,
    ),
    runtimeFetchJsonForBot<RuntimeWorkspaceDiff>(
      bot,
      `/api/runtime/tasks/${taskId}/workspace/diff`,
    ),
    runtimeFetchJsonForBot<{ items?: RuntimeTaskBundle["services"] }>(
      bot,
      `/api/runtime/tasks/${taskId}/services`,
    ),
    runtimeFetchJsonForBot<{ items?: RuntimeTaskBundle["resources"] }>(
      bot,
      `/api/runtime/tasks/${taskId}/resources`,
    ),
    runtimeFetchJsonForBot<{
      cycles?: RuntimeTaskBundle["loopCycles"];
      guardrails?: RuntimeTaskBundle["guardrails"];
    }>(bot, `/api/runtime/tasks/${taskId}/loop`),
    runtimeFetchJsonForBot<RuntimeSessions>(
      bot,
      `/api/runtime/tasks/${taskId}/sessions`,
    ),
  ]);

  if (!detail.ok || !detail.data?.task) {
    throw new RuntimeRequestError(
      detail.error || "Task not found",
      detail.status || 404,
    );
  }

  const errors = [
    detail.error,
    events.error,
    artifacts.error,
    checkpoints.error,
    terminals.error,
    browser.error,
    workspaceTree.error,
    workspaceStatus.error,
    workspaceDiff.error,
    services.error,
    resources.error,
    loop.error,
    sessions.error,
  ].filter((value): value is string => Boolean(value));

  return {
    botId,
    fetchedAt: new Date().toISOString(),
    availability: {
      health: "unknown",
      database: "unknown",
      runtime: "available",
      browser: browser.ok ? "available" : "partial",
      attach: bot.runtimeRequestToken ? "available" : "unavailable",
      errors,
    },
    task: detail.data.task,
    environment: detail.data.environment ?? null,
    warnings: detail.data.warnings ?? [],
    guardrails: loop.data?.guardrails ?? detail.data.guardrails ?? [],
    events: events.data?.items ?? [],
    artifacts: artifacts.data?.items ?? [],
    checkpoints: checkpoints.data?.items ?? [],
    terminals: terminals.data?.items ?? [],
    browser: browser.data?.browser ?? {},
    browserSessions: browser.data?.sessions ?? [],
    workspaceTree: workspaceTree.data?.items ?? [],
    workspaceStatus: workspaceStatus.data ?? {
      ok: false,
      text: "workspace status unavailable",
    },
    workspaceDiff: workspaceDiff.data ?? {
      ok: false,
      text: "workspace diff unavailable",
      truncated: false,
    },
    services: services.data?.items ?? [],
    resources: resources.data?.items ?? [],
    loopCycles: loop.data?.cycles ?? [],
    sessions: sessions.data ?? {
      attach_sessions: [],
      browser_sessions: [],
      terminals: [],
    },
    errors,
  };
}
