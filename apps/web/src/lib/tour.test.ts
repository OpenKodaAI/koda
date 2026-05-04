import { describe, expect, it } from "vitest";
import {
  APP_TOUR_VERSION,
  getFirstTourStepIdForChapter,
  getOptionalTourRecoveryAction,
  getTourChapterForPathname,
  getTourStepById,
  getTourStepsForMode,
  matchesTourRoutePattern,
  resolveTourPersistenceState,
  type TourChapterId,
  type TourStepId,
} from "@/lib/tour";

describe("tour helpers", () => {
  it("matches static and dynamic tour routes", () => {
    expect(matchesTourRoutePattern("/", "/")).toBe(true);
    expect(matchesTourRoutePattern("/control-plane", "/control-plane")).toBe(true);
    expect(matchesTourRoutePattern("/control-plane/agents/ATLAS", "/control-plane/agents/:agentId")).toBe(true);
    expect(matchesTourRoutePattern("/control-plane/agents/ATLAS/runs", "/control-plane/agents/:agentId")).toBe(false);
  });

  it("maps representative paths to the expected chapters", () => {
    expect(getTourChapterForPathname("/")).toBe("overview");
    expect(getTourChapterForPathname("/control-plane")).toBe("control_plane_catalog");
    expect(getTourChapterForPathname("/control-plane/agents/ATLAS")).toBe("control_plane_editor");
    expect(getTourChapterForPathname("/runtime/any")).toBe("runtime");
    expect(getTourChapterForPathname("/sessions")).toBe("sessions");
  });

  it("resolves the first step for a chapter", () => {
    expect(getFirstTourStepIdForChapter("control_plane_catalog", "auto")).toBe(
      "tour.controlPlane.primaryAction",
    );
    expect(getFirstTourStepIdForChapter("memory", "manual")).toBeNull();
  });

  it("uses seven actionable steps for automatic and manual onboarding", () => {
    const expected = [
      "tour.welcome",
      "tour.shell.sidebar",
      "tour.shell.topbar",
      "tour.overview.metrics",
      "tour.overview.livePlan",
      "tour.controlPlane.primaryAction",
      "tour.controlPlane.board",
      "tour.runtime.header",
      "tour.complete",
    ];

    expect(getTourStepsForMode("auto").map((step) => step.id)).toEqual(expected);
    expect(getTourStepsForMode("manual").map((step) => step.id)).toEqual(expected);
  });

  it("falls through optional route gaps outside the short tour", () => {
    expect(
      getOptionalTourRecoveryAction("tour.controlPlaneEditor.header", "manual", "/control-plane"),
    ).toBe("next");
    expect(
      getOptionalTourRecoveryAction("tour.controlPlaneEditor.publish", "manual", "/runtime"),
    ).toBe("next");
  });

  it("normalizes persisted state across invalid versions and step ids", () => {
    expect(
      resolveTourPersistenceState({
      version: APP_TOUR_VERSION - 1,
      status: "completed",
      currentStepId: "tour.complete" as TourStepId,
      completedChapters: ["overview" as TourChapterId],
      updatedAt: 1,
      completedAt: 1,
      skippedAt: null,
      }),
    ).toMatchObject({
      version: APP_TOUR_VERSION,
      status: "pending",
      currentStepId: null,
      completedChapters: [],
    });

    expect(
      resolveTourPersistenceState({
      version: APP_TOUR_VERSION,
      status: "running",
      currentStepId: "tour.unknown" as TourStepId,
      completedChapters: ["overview" as TourChapterId, "nope" as TourChapterId],
      updatedAt: 12,
      completedAt: null,
      skippedAt: null,
      }),
    ).toMatchObject({
      status: "running",
      currentStepId: null,
      completedChapters: ["overview"],
    });
  });

  it("keeps step definitions aligned with the mounted anchors", () => {
    expect(getTourStepById("tour.shell.topbar")?.anchor).toBe("shell.topbar.actions");
    expect(getTourStepById("tour.overview.metrics")?.fallbackAnchor).toBe("overview.agent-switcher");
    expect(getTourStepById("tour.overview.livePlan")?.anchor).toBe("overview.activity");
    expect(getTourStepById("tour.controlPlane.primaryAction")?.anchor).toBe("catalog.create-bot");
    expect(getTourStepById("tour.controlPlane.board")?.anchor).toBe("catalog.board");
    expect(getTourStepById("tour.controlPlaneEditor.publish")?.anchor).toBe("editor.save");
    expect(getTourStepById("tour.runtime.header")?.fallbackAnchor).toBe("runtime.metrics");
    expect(getTourStepById("tour.executions.filters")?.anchor).toBe("executions.search");
    expect(getTourStepById("tour.executions.table")?.fallbackAnchor).toBe("executions.metrics");
  });
});
