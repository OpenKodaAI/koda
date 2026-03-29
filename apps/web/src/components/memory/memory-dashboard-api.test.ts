import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  MemoryDashboardRequestError,
  fetchMemoryCurationDetail,
  fetchMemoryCurationList,
  fetchMemoryMap,
  postMemoryCurationAction,
} from "./memory-dashboard-api";

describe("memory dashboard api", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches memory map from canonical control-plane endpoint and injects bot scope", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          stats: {
            total_memories: 2,
            rendered_memories: 2,
            hidden_memories: 0,
            active_memories: 2,
            inactive_memories: 0,
            learning_nodes: 0,
            users: 1,
            sessions: 1,
            semantic_edges: 0,
            contextual_edges: 0,
            expiring_soon: 0,
            maintenance_operations: 0,
            last_maintenance_at: null,
            semantic_status: "fallback",
          },
          filters: {
            applied: {
              user_id: 42,
              session_id: "sess-1",
              days: 30,
              include_inactive: false,
              limit: 160,
            },
            users: [],
            sessions: [],
            types: [],
          },
          nodes: [],
          edges: [],
          semantic_status: "fallback",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const payload = await fetchMemoryMap("ATLAS", {
      days: 30,
      includeInactive: false,
      limit: 160,
      userId: 42,
      sessionId: "sess-1",
    });

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/control-plane/dashboard/agents/ATLAS/memory-map?days=30&includeInactive=0&limit=160&userId=42&sessionId=sess-1",
      expect.objectContaining({
        cache: "no-store",
      }),
    );
    expect(payload.bot_id).toBe("ATLAS");
  });

  it("fetches memory curation from canonical endpoint and normalizes bot/page", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          overview: {
            pending_memories: 1,
            pending_clusters: 0,
            expiring_soon: 0,
            discarded_last_7d: 0,
            merged_last_7d: 0,
            approved_last_7d: 0,
          },
          items: [],
          clusters: [],
          available_filters: {
            statuses: [],
            types: [],
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const payload = await fetchMemoryCurationList("ATLAS", {
      search: "rollback",
      status: "pending",
      type: "procedure",
      kind: "memory",
      limit: 240,
    });

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/control-plane/dashboard/agents/ATLAS/memory-curation?kind=memory&limit=240&offset=0&search=rollback&status=pending&type=procedure",
      expect.objectContaining({
        cache: "no-store",
      }),
    );
    expect(payload.bot_id).toBe("ATLAS");
    expect(payload.page.total).toBe(0);
  });

  it("fetches detail routes for memories and clusters", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          item: {
            bot_id: "ATLAS",
            memory_id: 101,
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await fetchMemoryCurationDetail("ATLAS", {
      kind: "memory",
      id: "101",
    });

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/control-plane/dashboard/agents/ATLAS/memory-curation/101",
      expect.objectContaining({
        cache: "no-store",
      }),
    );
  });

  it("posts memory curation actions to canonical endpoint", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await postMemoryCurationAction("ATLAS", {
      target_type: "memory",
      target_ids: ["101"],
      action: "approve",
      duplicate_of_memory_id: null,
    });

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/control-plane/dashboard/agents/ATLAS/memory-curation/actions",
      expect.objectContaining({
        cache: "no-store",
        method: "POST",
      }),
    );
  });

  it("surfaces backend errors as request errors", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: "memory backend unavailable" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(
      fetchMemoryMap("ATLAS", {
        days: 30,
        includeInactive: false,
      }),
    ).rejects.toEqual(
      expect.objectContaining<Partial<MemoryDashboardRequestError>>({
        message: "memory backend unavailable",
        status: 503,
      }),
    );
  });
});
