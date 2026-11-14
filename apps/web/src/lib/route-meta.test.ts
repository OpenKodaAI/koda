import { describe, expect, it } from "vitest";
import type { AppTranslator } from "@/lib/i18n";
import { getRouteMeta, getRouteShell } from "@/lib/route-meta";

const t: AppTranslator = (key) => key;

describe("getRouteMeta", () => {
  it("resolves the expected section metadata for representative routes", () => {
    expect(getRouteMeta("/control-plane/system", t)).toEqual({
      eyebrow: "routeMeta.system.eyebrow",
      title: "routeMeta.system.title",
      summary: "routeMeta.system.summary",
    });
    expect(getRouteMeta("/control-plane", t)).toEqual({
      eyebrow: "routeMeta.agents.eyebrow",
      title: "routeMeta.agents.title",
      summary: "routeMeta.agents.summary",
    });
    expect(getRouteMeta("/control-plane/agents/abc123", t)).toEqual({
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

  it("keeps the shell layout flags in the same registry", () => {
    expect(getRouteShell("/sessions")).toEqual({ layout: "fullBleed" });
    expect(getRouteShell("/sessions/abc123")).toEqual({ layout: "fullBleed" });
    expect(getRouteShell("/control-plane")).toEqual({ layout: "pane" });
    expect(getRouteShell("/control-plane/agents/abc123")).toEqual({
      layout: "pane",
      fullWidth: true,
    });
    expect(getRouteShell("/control-plane/system")).toEqual({ layout: "pane", clipStage: true });
    expect(getRouteShell("/control-plane/system/models")).toEqual({
      layout: "pane",
      clipStage: true,
    });
    expect(getRouteShell("/")).toEqual({ layout: "page" });
    expect(getRouteShell("/memory")).toEqual({ layout: "page" });
    // /control-plane/setup only redirects to /setup, so it has no shell branch.
    expect(getRouteShell("/control-plane/setup")).toEqual({ layout: "page" });
    expect(getRouteShell("/somewhere-else")).toEqual({ layout: "page" });
  });
});
