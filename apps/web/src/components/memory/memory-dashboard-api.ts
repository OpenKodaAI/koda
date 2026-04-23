"use client";

import type {
  MemoryClusterReviewDetail,
  MemoryCurationAction,
  MemoryCurationResponse,
  MemoryMapResponse,
  MemoryReviewDetail,
  MemoryReviewStatus,
  MemoryTypeKey,
} from "@/lib/types";

type MemoryMapParams = {
  userId?: number | null;
  sessionId?: string | null;
  days: number;
  includeInactive: boolean;
  limit?: number;
  signal?: AbortSignal;
};

type MemoryCurationListParams = {
  search?: string;
  status?: MemoryReviewStatus | "all";
  type?: MemoryTypeKey | "all";
  kind: "memory" | "cluster";
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
};

type MemoryCurationActionPayload = {
  target_type: "memory" | "cluster";
  target_ids: string[];
  action: MemoryCurationAction;
  duplicate_of_memory_id?: number | null;
};

export class MemoryDashboardRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "MemoryDashboardRequestError";
    this.status = status;
  }
}

function createEmptyMemoryMapResponse(
  agentId: string,
  options: {
    days?: number;
    includeInactive?: boolean;
    limit?: number;
  } = {},
): MemoryMapResponse {
  const days = options.days ?? 30;
  const includeInactive = options.includeInactive ?? false;
  const limit = options.limit ?? 160;

  return {
    bot_id: agentId,
    stats: {
      total_memories: 0,
      rendered_memories: 0,
      hidden_memories: 0,
      active_memories: 0,
      inactive_memories: 0,
      learning_nodes: 0,
      users: 0,
      sessions: 0,
      semantic_edges: 0,
      contextual_edges: 0,
      expiring_soon: 0,
      maintenance_operations: 0,
      last_maintenance_at: null,
      semantic_status: "missing",
    },
    filters: {
      applied: {
        user_id: null,
        session_id: null,
        days,
        include_inactive: includeInactive,
        limit,
      },
      users: [],
      sessions: [],
      types: [],
    },
    nodes: [],
    edges: [],
    semantic_status: "missing",
  };
}

function buildDashboardPath(agentId: string, suffix: string, query?: URLSearchParams) {
  const base = `/api/control-plane/dashboard/agents/${encodeURIComponent(agentId)}`;
  return query && query.toString() ? `${base}${suffix}?${query.toString()}` : `${base}${suffix}`;
}

async function fetchDashboardJson<T>(
  url: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(url, {
    ...init,
    cache: "no-store",
  });

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "error" in payload
        ? String(payload.error)
        : `Memory dashboard request failed with status ${response.status}`;
    throw new MemoryDashboardRequestError(message, response.status);
  }

  return payload as T;
}

function normalizeMemoryMapResponse(
  agentId: string,
  payload: Omit<MemoryMapResponse, "bot_id"> & Partial<Pick<MemoryMapResponse, "bot_id">>,
): MemoryMapResponse {
  const fallback = createEmptyMemoryMapResponse(agentId, {
    days: payload.filters?.applied?.days,
    includeInactive: payload.filters?.applied?.include_inactive,
    limit: payload.filters?.applied?.limit,
  });

  return {
    ...fallback,
    ...payload,
    bot_id: payload.bot_id ?? agentId,
    stats: {
      ...fallback.stats,
      ...(payload.stats ?? {}),
    },
    filters: {
      ...fallback.filters,
      ...(payload.filters ?? {}),
      applied: {
        ...fallback.filters.applied,
        ...(payload.filters?.applied ?? {}),
      },
      users: Array.isArray(payload.filters?.users) ? payload.filters.users : fallback.filters.users,
      sessions: Array.isArray(payload.filters?.sessions)
        ? payload.filters.sessions
        : fallback.filters.sessions,
      types: Array.isArray(payload.filters?.types) ? payload.filters.types : fallback.filters.types,
    },
    nodes: Array.isArray(payload.nodes) ? payload.nodes : fallback.nodes,
    edges: Array.isArray(payload.edges) ? payload.edges : fallback.edges,
    semantic_status:
      payload.semantic_status ?? payload.stats?.semantic_status ?? fallback.semantic_status,
  };
}

function normalizeMemoryCurationResponse(
  agentId: string,
  payload: Omit<MemoryCurationResponse, "bot_id" | "page"> &
    Partial<Pick<MemoryCurationResponse, "bot_id" | "page">>,
): MemoryCurationResponse {
  const itemCount = Array.isArray(payload.items) ? payload.items.length : 0;
  const clusterCount = Array.isArray(payload.clusters) ? payload.clusters.length : 0;

  return {
    ...payload,
    bot_id: payload.bot_id ?? agentId,
    page: payload.page ?? {
      limit: itemCount + clusterCount,
      offset: 0,
      total: itemCount + clusterCount,
      has_more: false,
    },
  };
}

export async function fetchMemoryMap(
  agentId: string,
  params: MemoryMapParams,
): Promise<MemoryMapResponse> {
  const query = new URLSearchParams({
    days: String(params.days),
    includeInactive: params.includeInactive ? "1" : "0",
    limit: String(params.limit ?? 160),
  });

  if (params.userId != null) {
    query.set("userId", String(params.userId));
  }
  if (params.sessionId) {
    query.set("sessionId", params.sessionId);
  }

  const payload = await fetchDashboardJson<
    Omit<MemoryMapResponse, "bot_id"> & Partial<Pick<MemoryMapResponse, "bot_id">>
  >(buildDashboardPath(agentId, "/memory-map", query), {
    signal: params.signal,
  });
  return normalizeMemoryMapResponse(agentId, payload);
}

export async function fetchMemoryCurationList(
  agentId: string,
  params: MemoryCurationListParams,
): Promise<MemoryCurationResponse> {
  const query = new URLSearchParams({
    kind: params.kind,
    limit: String(params.limit ?? 240),
    offset: String(params.offset ?? 0),
  });

  if (params.search) {
    query.set("search", params.search);
  }
  if (params.status && params.status !== "all") {
    query.set("status", params.status);
  }
  if (params.type && params.type !== "all") {
    query.set("type", params.type);
  }

  const payload = await fetchDashboardJson<
    Omit<MemoryCurationResponse, "bot_id" | "page"> &
      Partial<Pick<MemoryCurationResponse, "bot_id" | "page">>
  >(buildDashboardPath(agentId, "/memory-curation", query), {
    signal: params.signal,
  });

  return normalizeMemoryCurationResponse(agentId, payload);
}

export async function fetchMemoryCurationDetail(
  agentId: string,
  entry: { kind: "memory"; id: string } | { kind: "cluster"; id: string },
): Promise<MemoryReviewDetail | MemoryClusterReviewDetail> {
  const suffix =
    entry.kind === "memory"
      ? `/memory-curation/${encodeURIComponent(entry.id)}`
      : `/memory-curation/clusters/${encodeURIComponent(entry.id)}`;
  return fetchDashboardJson<MemoryReviewDetail | MemoryClusterReviewDetail>(
    buildDashboardPath(agentId, suffix),
  );
}

export async function postMemoryCurationAction(
  agentId: string,
  payload: MemoryCurationActionPayload,
): Promise<void> {
  await fetchDashboardJson<Record<string, unknown>>(
    buildDashboardPath(agentId, "/memory-curation/actions"),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
}
