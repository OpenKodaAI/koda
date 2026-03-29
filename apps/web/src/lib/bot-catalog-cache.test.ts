import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({
  unstable_cache:
    <TArgs extends unknown[], TResult>(fn: (...args: TArgs) => Promise<TResult>) =>
    (...args: TArgs) =>
      fn(...args),
}));

describe("bot-catalog-cache", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("returns an empty catalog when the control plane is unavailable", async () => {
    vi.doMock("@/lib/control-plane", () => {
      class MockControlPlaneRequestError extends Error {
        status: number;

        constructor(message: string, status = 503) {
          super(message);
          this.name = "ControlPlaneRequestError";
          this.status = status;
        }
      }

      return {
        ControlPlaneRequestError: MockControlPlaneRequestError,
        getControlPlaneBots: vi.fn(async () => {
          throw new MockControlPlaneRequestError("fetch failed", 503);
        }),
      };
    });

    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { getCachedBotDisplays } = await import("@/lib/bot-catalog-cache");

    await expect(getCachedBotDisplays()).resolves.toEqual([]);
    expect(warnSpy).toHaveBeenCalledWith(
      "bot_catalog_cache_unavailable",
      expect.objectContaining({ message: "fetch failed" }),
    );
  });

  it("rethrows non-control-plane failures", async () => {
    vi.doMock("@/lib/control-plane", () => ({
      ControlPlaneRequestError: class ControlPlaneRequestError extends Error {},
      getControlPlaneBots: vi.fn(async () => {
        throw new Error("unexpected decode failure");
      }),
    }));

    const { getCachedBotDisplays } = await import("@/lib/bot-catalog-cache");

    await expect(getCachedBotDisplays()).rejects.toThrow("unexpected decode failure");
  });
});
