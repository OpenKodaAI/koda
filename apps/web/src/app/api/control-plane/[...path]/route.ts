import { NextRequest, NextResponse } from "next/server";
import { revalidatePath, revalidateTag } from "next/cache";
import { jsonErrorResponse, parseSchemaOrThrow } from "@/lib/api-utils";
import { ValidationError } from "@/lib/errors";
import { pathSegmentsSchema } from "@/lib/contracts/common";
import { resolveBodySchema } from "@/lib/contracts/proxy-body-schemas";
import "@/lib/contracts/agents";
import "@/lib/contracts/auth";
import "@/lib/contracts/workspaces";
import "@/lib/contracts/mcp";
import "@/lib/contracts/system";
import "@/lib/contracts/sessions";
import "@/lib/contracts/memory";
import "@/lib/contracts/evals";
import "@/lib/contracts/channel-gateway";
import "@/lib/contracts/onboarding-readiness";
import { controlPlaneFetch, sanitizeControlPlanePayload } from "@/lib/control-plane";
import { getControlPlaneMutationInvalidation } from "@/lib/control-plane-cache";
import { isTrustedDashboardRequest } from "@/lib/request-origin";
import {
  getWebOperatorTokenFromCookie,
  setOwnerExistsHintCookie,
} from "@/lib/web-operator-session";

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

const PUBLIC_CONTROL_PLANE_PATHS = new Set([
  "onboarding/status",
  "onboarding/readiness",
  "auth/status",
  "auth/bootstrap/exchange",
  "auth/login",
  "auth/register-owner",
]);

const UPSTREAM_UNAVAILABLE_HEADER = "X-Koda-Upstream-Unavailable";
const UPSTREAM_UNAVAILABLE_MESSAGE = "Control plane upstream is unavailable";

function isPublicControlPlanePath(path: string[]) {
  return PUBLIC_CONTROL_PLANE_PATHS.has(path.join("/"));
}

function readPositiveInt(searchParams: URLSearchParams, name: string, fallback: number) {
  const value = Number(searchParams.get(name));
  return Number.isInteger(value) && value > 0 ? value : fallback;
}

function readNonNegativeInt(searchParams: URLSearchParams, name: string, fallback: number) {
  const value = Number(searchParams.get(name));
  return Number.isInteger(value) && value >= 0 ? value : fallback;
}

function emptyPaginatedPayload(request: NextRequest) {
  const limit = readPositiveInt(request.nextUrl.searchParams, "limit", 50);
  const offset = readNonNegativeInt(request.nextUrl.searchParams, "offset", 0);

  return {
    items: [],
    page: {
      limit,
      offset,
      returned: 0,
      next_offset: null,
      has_more: false,
      total: null,
    },
    unavailable: true,
    error: UPSTREAM_UNAVAILABLE_MESSAGE,
  };
}

function emptyCollectionPayload() {
  return {
    items: [],
    count: 0,
    available: false,
    unavailable: true,
    error: UPSTREAM_UNAVAILABLE_MESSAGE,
  };
}

function emptyAgentStatsPayload(agentId: string) {
  return {
    agentId,
    totalTasks: 0,
    activeTasks: 0,
    completedTasks: 0,
    failedTasks: 0,
    queuedTasks: 0,
    totalQueries: 0,
    totalCost: 0,
    todayCost: 0,
    dbExists: false,
    recentTasks: [],
    dailyCosts: [],
    unavailable: true,
    error: UPSTREAM_UNAVAILABLE_MESSAGE,
  };
}

function emptyCostInsightsPayload(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  return {
    overview: {
      total_cost_usd: 0,
      today_cost_usd: 0,
      resolved_conversations: 0,
      unresolved_conversations: 0,
      avg_cost_per_resolved_conversation: 0,
      median_cost_per_resolved_conversation: 0,
      unresolved_cost_usd: 0,
      total_queries: 0,
      total_executions: 0,
      top_model: null,
      top_agent: null,
      top_task_type: null,
    },
    comparison: {
      previous_total_cost_usd: 0,
      total_delta_pct: null,
      previous_avg_cost_per_resolved_conversation: 0,
      avg_cost_per_resolved_delta_pct: null,
      previous_today_cost_usd: null,
      today_delta_pct: null,
      previous_resolved_conversations: 0,
    },
    peak_bucket: null,
    time_series: [],
    by_agent: [],
    by_model: [],
    by_task_type: [],
    resolved_conversations: [],
    conversation_rows: [],
    available_models: [],
    available_task_types: [],
    applied_filters: {
      agent_id: "all",
      agent_ids: searchParams.getAll("agent"),
      period: searchParams.get("period") ?? "30d",
      from: null,
      to: null,
      model: searchParams.get("model"),
      task_type: searchParams.get("taskType"),
      group_by: searchParams.get("groupBy") ?? "auto",
    },
    unavailable: true,
    error: UPSTREAM_UNAVAILABLE_MESSAGE,
  };
}

function emptyOnboardingStatusPayload() {
  return {
    status: "unavailable",
    control_plane: {
      ready: false,
      reason: UPSTREAM_UNAVAILABLE_MESSAGE,
    },
    storage: {
      database: { ready: false, reason: UPSTREAM_UNAVAILABLE_MESSAGE },
      object_storage: { ready: false, reason: UPSTREAM_UNAVAILABLE_MESSAGE },
    },
    providers: [],
    agents: [],
    system: {
      owner_name: "",
      owner_email: "",
      owner_github: "",
      default_provider: "",
      allowed_user_ids: [],
    },
    steps: {
      provider_configured: false,
      access_configured: false,
      agent_ready: false,
      storage_ready: false,
      onboarding_complete: false,
    },
    unavailable: true,
    error: UPSTREAM_UNAVAILABLE_MESSAGE,
  };
}

function emptyOnboardingReadinessPayload() {
  return {
    schema_version: "onboarding_readiness.v1",
    status: "pending",
    primary_agent_id: "",
    generated_at: "",
    checks: [],
    summary: {
      passed: 0,
      warning: 0,
      failed: 0,
      pending: 0,
    },
    actions: [],
    unavailable: true,
    error: {
      code: "UPSTREAM_UNAVAILABLE",
      category: "dependency_unavailable",
      message: UPSTREAM_UNAVAILABLE_MESSAGE,
      retryable: true,
      user_action: "",
    },
  };
}

function unavailableReadPayload(path: string[], request: NextRequest): unknown | null {
  if (request.method !== "GET") {
    return null;
  }

  const joined = path.join("/");
  if (joined === "onboarding/status") {
    return emptyOnboardingStatusPayload();
  }
  if (joined === "onboarding/readiness") {
    return emptyOnboardingReadinessPayload();
  }

  if (path[0] !== "dashboard") {
    return null;
  }

  const dashboardPath = path.slice(1);
  const [area, second, third] = dashboardPath;

  if (area === "agents" && second === "summary") {
    return [];
  }
  if (area === "agents" && second && third === "stats") {
    return emptyAgentStatsPayload(second);
  }
  if (
    area === "agents" &&
    second &&
    ["executions", "sessions", "dlq", "schedules", "cron", "audit"].includes(third ?? "") &&
    dashboardPath.length === 3
  ) {
    return emptyPaginatedPayload(request);
  }
  if (area === "agents" && second && third === "costs") {
    return emptyCostInsightsPayload(request);
  }

  if (["executions", "sessions", "dlq", "schedules", "cron"].includes(area ?? "")) {
    return emptyPaginatedPayload(request);
  }
  if (area === "costs") {
    return emptyCostInsightsPayload(request);
  }

  if (area === "squads" && second === "overview") {
    return emptyCollectionPayload();
  }
  if (area === "squads" && second && ["threads", "activity", "metrics"].includes(third ?? "")) {
    return emptyCollectionPayload();
  }

  return null;
}

function unavailableReadResponse(path: string[], request: NextRequest) {
  const payload = unavailableReadPayload(path, request);
  if (payload === null) {
    return null;
  }

  return NextResponse.json(payload, {
    status: 200,
    headers: {
      "Cache-Control": "no-store",
      [UPSTREAM_UNAVAILABLE_HEADER]: "1",
    },
  });
}

function unauthorizedResponse() {
  return new Response(
    JSON.stringify({ error: "Operator session is required." }),
    {
      status: 401,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    },
  );
}

function forbiddenMutationResponse() {
  return new Response(
    JSON.stringify({ error: "Cross-site dashboard mutations are blocked." }),
    {
      status: 403,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    },
  );
}

async function handleControlPlaneProxy(request: NextRequest, { params }: RouteContext) {
  let path: string[];

  try {
    const raw = await params;
    path = parseSchemaOrThrow(
      pathSegmentsSchema,
      raw.path ?? [],
      "Invalid control plane path.",
    );
  } catch (error) {
    return jsonErrorResponse(error, "Invalid control plane path.");
  }

  const operatorToken = await getWebOperatorTokenFromCookie();
  const publicPath = isPublicControlPlanePath(path);
  if (!operatorToken && !publicPath) {
    return unauthorizedResponse();
  }
  if (!isTrustedDashboardRequest(request)) {
    return forbiddenMutationResponse();
  }

  if (path[path.length - 1] === "runtime-access") {
    return new Response(
      JSON.stringify({
        error: "runtime access is only available from server-side modules",
      }),
      {
        status: 403,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        },
      },
    );
  }
  const pathname = `/api/control-plane/${path.join("/")}`;
  const upstreamUrl = new URL(pathname, "http://local.invalid");
  upstreamUrl.search = request.nextUrl.search;

  let body: string | ArrayBuffer | undefined;
  const incomingContentType = request.headers.get("content-type") || "";
  const isMultipart = incomingContentType.toLowerCase().startsWith("multipart/");

  if (request.method !== "GET" && request.method !== "HEAD") {
    if (isMultipart) {
      // Multipart bodies are binary (and must keep their boundary). Reading
      // them as text mangles the JPEG/PNG bytes and the upstream then sees a
      // length-mismatched payload, which surfaces as a generic
      // "upstream unavailable" to the operator. Forward the bytes as-is and
      // skip JSON-schema validation since multipart is never JSON.
      body = await request.arrayBuffer();
    } else {
      const rawBody = await request.text();

      const schema = resolveBodySchema(request.method, path);
      if (schema && rawBody) {
        let parsed: unknown;
        try {
          parsed = JSON.parse(rawBody);
        } catch {
          return jsonErrorResponse(
            new ValidationError("Request body is not valid JSON."),
            "Invalid request data.",
          );
        }
        try {
          const validated = parseSchemaOrThrow(schema, parsed, "Invalid request data.");
          body = JSON.stringify(validated);
        } catch (error) {
          return jsonErrorResponse(error, "Invalid request data.");
        }
      } else {
        body = rawBody || undefined;
      }
    }
  }

  // Preserve the exact incoming Content-Type — for multipart that includes the
  // boundary token, which is required for the upstream parser to find part
  // separators.
  const upstreamContentType = isMultipart
    ? incomingContentType
    : incomingContentType || "application/json";

  let response: Response;
  try {
    response = await controlPlaneFetch(
      upstreamUrl.pathname + upstreamUrl.search,
      {
        method: request.method,
        headers: {
          "Content-Type": upstreamContentType,
        },
        body,
      },
      {
        tier: "live",
        // Multipart uploads run image-processing work upstream (Pillow decode +
        // re-encode + disk write); the default 10s budget is tight in dev.
        // Bump it for binary bodies so the operator never sees a spurious
        // "upstream unavailable" while the backend is still processing.
        ...(isMultipart ? { timeoutMs: 30_000 } : {}),
      },
    );
  } catch (error) {
    const fallback = unavailableReadResponse(path, request);
    if (fallback) {
      return fallback;
    }
    return jsonErrorResponse(error, UPSTREAM_UNAVAILABLE_MESSAGE);
  }

  if (response.status === 503) {
    const fallback = unavailableReadResponse(path, request);
    if (fallback) {
      return fallback;
    }
  }

  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }
  // Dynamic JSON payloads must never be cached, but binary asset responses
  // (room photos, artifact downloads) carry their own immutable cache hints
  // and should be passed through verbatim — otherwise the operator pays for
  // a fresh fetch on every navigation. Honour the upstream Cache-Control /
  // ETag for non-JSON responses; force no-store for JSON.
  if (contentType?.includes("application/json")) {
    headers.set("Cache-Control", "no-store");
  } else {
    const upstreamCacheControl = response.headers.get("cache-control");
    headers.set("Cache-Control", upstreamCacheControl ?? "no-store");
    const upstreamEtag = response.headers.get("etag");
    if (upstreamEtag) headers.set("ETag", upstreamEtag);
    const upstreamLastModified = response.headers.get("last-modified");
    if (upstreamLastModified) headers.set("Last-Modified", upstreamLastModified);
  }
  headers.set("X-Content-Type-Options", "nosniff");

  if (
    response.ok &&
    ["POST", "PUT", "PATCH", "DELETE"].includes(request.method)
  ) {
    const invalidation = getControlPlaneMutationInvalidation(path);

    for (const tag of invalidation.tags) {
      revalidateTag(tag, "max");
    }

    revalidatePath("/", "layout");

    for (const routePath of invalidation.paths) {
      revalidatePath(routePath);
    }
  }

  if (contentType?.includes("application/json")) {
    const payload = await response.json().catch(() => null);
    const sanitized = sanitizeControlPlanePayload(pathname, payload);
    const finalResponse = new NextResponse(JSON.stringify(sanitized), {
      status: response.status,
      headers,
    });
    // Sync the owner-exists hint cookie whenever we observe it from the
    // control plane. Server Component pages cannot set cookies directly, so
    // we do it here on the next response the client sees.
    if (
      pathname === "/api/control-plane/auth/status" ||
      pathname === "/api/control-plane/onboarding/status"
    ) {
      if (sanitized && typeof sanitized === "object" && "has_owner" in sanitized) {
        setOwnerExistsHintCookie(finalResponse, Boolean((sanitized as { has_owner?: boolean }).has_owner));
      }
    }
    return finalResponse;
  }

  return new Response(response.body, {
    status: response.status,
    headers,
  });
}

export const GET = handleControlPlaneProxy;
export const POST = handleControlPlaneProxy;
export const PUT = handleControlPlaneProxy;
export const PATCH = handleControlPlaneProxy;
export const DELETE = handleControlPlaneProxy;
