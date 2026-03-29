import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildControlPlaneDashboardUrl,
  fetchControlPlaneDashboardJson,
  fetchControlPlaneDashboardJsonAllowError,
} from "@/lib/control-plane-dashboard";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("control-plane-dashboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds canonical dashboard URLs with repeated bot filters", () => {
    expect(
      buildControlPlaneDashboardUrl("/executions", {
        bot: ["ATLAS", "KODA"],
        status: "running",
        limit: 100,
      }),
    ).toBe(
      "/api/control-plane/dashboard/executions?bot=ATLAS&bot=KODA&status=running&limit=100",
    );
  });

  it("fetches dashboard payloads through the canonical proxy", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toBe(
        "/api/control-plane/dashboard/costs?period=30d&bot=ATLAS",
      );
      return jsonResponse({ ok: true });
    });

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchControlPlaneDashboardJson<{ ok: boolean }>("/costs", {
        params: { period: "30d", bot: ["ATLAS"] },
        fallbackError: "failed",
      }),
    ).resolves.toEqual({ ok: true });
  });

  it("returns structured failures for non-2xx dashboard responses", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error: "dashboard offline" }, 503));

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchControlPlaneDashboardJsonAllowError<{ ok: boolean }>("/schedules", {
        fallbackError: "failed",
      }),
    ).resolves.toEqual({
      ok: false,
      status: 503,
      data: null,
      error: "dashboard offline",
    });
  });
});
