import { describe, expect, it } from "vitest";
import { resolveRuntimeAvailability } from "@/lib/runtime-availability";
import type {
  RuntimeAgentHealth,
  RuntimeEnvironment,
  RuntimeQueueItem,
  RuntimeReadiness,
} from "@/lib/runtime-types";

function endpoint<T>(overrides: Partial<{
  ok: boolean;
  status: number;
  data: T | null;
  error?: string;
}> = {}) {
  return {
    ok: overrides.ok ?? true,
    status: overrides.status ?? 200,
    data: overrides.data ?? null,
    error: overrides.error,
  };
}

describe("resolveRuntimeAvailability", () => {
  it("marks runtime as disabled when health has snapshot but runtime routes are missing", () => {
    const state = resolveRuntimeAvailability({
      readiness: endpoint<RuntimeReadiness>({
        data: {
          ready: true,
          startup: { phase: "ready" },
        },
      }),
      health: endpoint<RuntimeAgentHealth>({
        data: {
          status: "healthy",
          database: { reachable: true },
          runtime: { active_environments: 1 },
        },
      }),
      queues: endpoint<{ items?: RuntimeQueueItem[] }>({
        ok: false,
        status: 404,
        error: "Runtime request failed with status 404",
      }),
      environments: endpoint<{ items?: RuntimeEnvironment[] }>({
        ok: false,
        status: 404,
        error: "Runtime request failed with status 404",
      }),
      hasRuntimeToken: true,
    });

    expect(state.runtime).toBe("disabled");
    expect(state.attach).toBe("disabled");
  });

  it("marks runtime as partial when health exposes snapshot but runtime routes are unhealthy", () => {
    const state = resolveRuntimeAvailability({
      readiness: endpoint<RuntimeReadiness>({
        data: {
          ready: false,
          startup: { phase: "bootstrapping" },
        },
      }),
      health: endpoint<RuntimeAgentHealth>({
        data: {
          status: "healthy",
          database: { reachable: true },
          runtime: { active_environments: 2, browser_sessions_active: 1 },
        },
      }),
      queues: endpoint<{ items?: RuntimeQueueItem[] }>({
        ok: false,
        status: 503,
        error: "queue service down",
      }),
      environments: endpoint<{ items?: RuntimeEnvironment[] }>({
        ok: false,
        status: 503,
        error: "environment service down",
      }),
      hasRuntimeToken: true,
    });

    expect(state.runtime).toBe("partial");
    expect(state.browser).toBe("partial");
    expect(state.attach).toBe("partial");
  });

  it("marks runtime as available only when runtime routes respond", () => {
    const state = resolveRuntimeAvailability({
      readiness: endpoint<RuntimeReadiness>({
        data: {
          ready: true,
          startup: { phase: "ready" },
        },
      }),
      health: endpoint<RuntimeAgentHealth>({
        data: {
          status: "healthy",
          database: { reachable: true },
          runtime: { active_environments: 1 },
        },
      }),
      queues: endpoint<{ items?: RuntimeQueueItem[] }>({
        data: { items: [{ task_id: 10, status: "queued" }] },
      }),
      environments: endpoint<{ items?: RuntimeEnvironment[] }>({
        data: { items: [] },
      }),
      hasRuntimeToken: false,
    });

    expect(state.runtime).toBe("available");
    expect(state.attach).toBe("unavailable");
  });
});
