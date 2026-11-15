import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useCreateAgent } from "@/hooks/use-create-agent";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

vi.mock("@/hooks/use-app-i18n", async () => {
  const { translateForLanguage } = await vi.importActual<typeof import("@/lib/i18n")>("@/lib/i18n");
  const t = (key: string, options?: Record<string, unknown>) => translateForLanguage("en-US", key, options);
  return {
    useAppI18n: () => ({ t, tl: (value: string) => value, i18n: { t }, language: "en-US" }),
  };
});

const showToast = vi.fn();

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ showToast }),
}));

function respond(body: unknown, status: number) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

describe("useCreateAgent", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    push.mockReset();
    showToast.mockReset();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("lets the server pick the id and health port, then opens the created agent", async () => {
    const fetchMock = vi.fn(() => respond({ id: "NEW_AGENT" }, 201));
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    const { result } = renderHook(() => useCreateAgent());

    await act(() => result.current.createAgent());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [path, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/control-plane/agents");
    const body = JSON.parse(String(init.body));
    expect(body).not.toHaveProperty("id");
    expect(body).not.toHaveProperty("runtime_endpoint");
    expect(body).not.toHaveProperty("storage_namespace");
    expect(body).toMatchObject({ display_name: "New agent", status: "paused" });
    expect(push).toHaveBeenCalledWith("/control-plane/agents/NEW_AGENT");
  });

  it("shows the id conflict when the server answers 409", async () => {
    globalThis.fetch = vi.fn(() =>
      respond({ error: "agent id NEW_AGENT already exists" }, 409),
    ) as unknown as typeof fetch;
    const { result } = renderHook(() => useCreateAgent());

    await act(() => result.current.createAgent());

    expect(showToast).toHaveBeenCalledWith("An agent with this ID already exists.", "error");
    expect(push).not.toHaveBeenCalled();
    expect(result.current.creating).toBe(false);
  });
});
