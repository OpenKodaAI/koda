import { describe, expect, it } from "vitest";
import {
  CONTROL_PLANE_CACHE_TAGS,
  getControlPlaneFetchConfig,
  getControlPlaneMutationInvalidation,
} from "@/lib/control-plane-cache";

describe("control-plane cache helpers", () => {
  it("builds catalog fetch config with short revalidation", () => {
    expect(
      getControlPlaneFetchConfig("catalog", [CONTROL_PLANE_CACHE_TAGS.catalog]),
    ).toEqual({
      cache: "force-cache",
      next: {
        revalidate: 15,
        tags: [CONTROL_PLANE_CACHE_TAGS.catalog],
      },
    });
  });

  it("builds detail fetch config with shorter revalidation", () => {
    expect(
      getControlPlaneFetchConfig("detail", [CONTROL_PLANE_CACHE_TAGS.agent("ATLAS")]),
    ).toEqual({
      cache: "force-cache",
      next: {
        revalidate: 5,
        tags: [CONTROL_PLANE_CACHE_TAGS.agent("ATLAS")],
      },
    });
  });

  it("keeps live fetches out of the cache", () => {
    expect(getControlPlaneFetchConfig("live")).toEqual({ cache: "no-store" });
  });

  it("invalidates agent detail and catalog paths for agent mutations", () => {
    expect(
      getControlPlaneMutationInvalidation(["agents", "ATLAS", "publish"]),
    ).toEqual({
      tags: [
        CONTROL_PLANE_CACHE_TAGS.catalog,
        CONTROL_PLANE_CACHE_TAGS.agentCatalog,
        CONTROL_PLANE_CACHE_TAGS.agent("ATLAS"),
      ],
      paths: ["/control-plane", "/control-plane/agents/ATLAS"],
    });
  });

  it("skips browser-side runtime access invalidation entirely", () => {
    expect(
      getControlPlaneMutationInvalidation(["agents", "ATLAS", "runtime-access"]),
    ).toEqual({
      tags: [],
      paths: [],
    });
  });

  it("invalidates system pages for system settings mutations", () => {
    expect(
      getControlPlaneMutationInvalidation(["system-settings", "general"]),
    ).toEqual({
      tags: [
        CONTROL_PLANE_CACHE_TAGS.system,
        CONTROL_PLANE_CACHE_TAGS.systemGeneral,
      ],
      paths: ["/control-plane", "/control-plane/system"],
    });
  });
});
