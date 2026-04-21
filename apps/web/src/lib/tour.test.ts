import { describe, expect, it } from "vitest";
import {
  APP_TOUR_VERSION,
  getFirstTourStepIdForChapter,
  getOptionalTourRecoveryAction,
  getTourChapterForPathname,
  getTourStepById,
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
    expect(getFirstTourStepIdForChapter("memory", "manual")).toBe("tour.memory.primary");
  });

  it("recovers optional route gaps in the correct direction", () => {
    expect(
      getOptionalTourRecoveryAction("tour.controlPlaneEditor.header", "auto", "/control-plane"),
    ).toBe("next");
    expect(
      getOptionalTourRecoveryAction("tour.controlPlaneEditor.publish", "auto", "/runtime"),
    ).toBe("back");
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
    expect(getTourStepById("tour.controlPlane.primaryAction")?.anchor).toBe("catalog.primary-actions");
    expect(getTourStepById("tour.controlPlaneEditor.publish")?.anchor).toBe("editor.save");
    expect(getTourStepById("tour.executions.filters")?.anchor).toBe("executions.search");
    expect(getTourStepById("tour.executions.table")?.fallbackAnchor).toBe("executions.metrics");
  });
});
