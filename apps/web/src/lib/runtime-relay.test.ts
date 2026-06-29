// @vitest-environment node

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("runtime relay descriptor storage", () => {
  beforeEach(async () => {
    vi.resetModules();
  });

  afterEach(async () => {
    const { cleanupExpiredRuntimeRelayDescriptors } = await import("@/lib/runtime-relay");
    await cleanupExpiredRuntimeRelayDescriptors();
  });

  it("stores relay descriptors only in memory and can read them back", async () => {
    const { createRuntimeRelayDescriptor, readRuntimeRelayDescriptor } = await import(
      "@/lib/runtime-relay"
    );

    const relay = await createRuntimeRelayDescriptor({
      kind: "terminal",
      agentId: "ATLAS",
      taskId: 12,
      terminalId: 4,
      upstreamUrl: "ws://127.0.0.1:8123/ws",
      expiresAt: new Date(Date.now() + 30_000).toISOString(),
    });

    const stored = await readRuntimeRelayDescriptor(relay.id);
    expect(stored?.upstreamUrl).toBe("ws://127.0.0.1:8123/ws");
    expect(stored?.id).toBe(relay.id);
  });

  it("evicts expired relay descriptors from memory", async () => {
    const {
      createRuntimeRelayDescriptor,
      readRuntimeRelayDescriptor,
      cleanupExpiredRuntimeRelayDescriptors,
    } = await import("@/lib/runtime-relay");

    const relay = await createRuntimeRelayDescriptor({
      kind: "browser",
      agentId: "ATLAS",
      taskId: 12,
      upstreamUrl: "ws://127.0.0.1:8123/ws",
      expiresAt: new Date(Date.now() - 1_000).toISOString(),
    });

    await cleanupExpiredRuntimeRelayDescriptors();
    expect(await readRuntimeRelayDescriptor(relay.id)).toBeNull();
  });
});
