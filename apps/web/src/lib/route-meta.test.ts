import { describe, expect, it } from "vitest";
import type { AppTranslator } from "@/lib/i18n";
import { getRouteMeta } from "@/lib/route-meta";

const t: AppTranslator = (key) => key;

describe("getRouteMeta", () => {
  it("resolves the expected section metadata for representative routes", () => {
    expect(getRouteMeta("/control-plane/system", t)).toEqual({
      eyebrow: "routeMeta.system.eyebrow",
      title: "routeMeta.system.title",
      summary: "routeMeta.system.summary",
    });
    expect(getRouteMeta("/control-plane/agents/abc123", t)).toEqual({
      eyebrow: "routeMeta.agents.eyebrow",
      title: "routeMeta.agents.title",
      summary: "routeMeta.agents.summary",
    });
    expect(getRouteMeta("/control-plane/bots/abc123", t)).toEqual({
      eyebrow: "routeMeta.agents.eyebrow",
      title: "routeMeta.agents.title",
      summary: "routeMeta.agents.summary",
    });
    expect(getRouteMeta("/runtime/bots/abc123", t)).toEqual({
      eyebrow: "routeMeta.runtime.eyebrow",
      title: "routeMeta.runtime.title",
      summary: "routeMeta.runtime.summary",
    });
    expect(getRouteMeta("/sessions/abc123", t)).toEqual({
      eyebrow: "routeMeta.sessions.eyebrow",
      title: "routeMeta.sessions.title",
      summary: "routeMeta.sessions.summary",
    });
  });

  it("falls back cleanly for unknown routes", () => {
    expect(getRouteMeta("/somewhere-else", t)).toEqual({
      eyebrow: "routeMeta.fallback.eyebrow",
      title: "routeMeta.fallback.title",
      summary: "routeMeta.fallback.summary",
    });
  });
});
