import { describe, expect, it } from "vitest";
import { ACTIVITY_HEATMAP_PRIMARY } from "@/lib/activity-palette";
import { getEdgeStyle, getNodeStyle } from "./memory-graph-visuals";

describe("memory graph visuals", () => {
  it("uses the activity heatmap green for focused memory map states", () => {
    const expectedAccent = `var(--memory-graph-accent, ${ACTIVITY_HEATMAP_PRIMARY})`;
    const node = {} as Parameters<typeof getNodeStyle>[0];
    const edge = {} as Parameters<typeof getEdgeStyle>[0];

    expect(getNodeStyle(node, "hovered")).toMatchObject({
      fill: expectedAccent,
      stroke: expectedAccent,
    });
    expect(getNodeStyle(node, "selected")).toMatchObject({
      fill: expectedAccent,
      stroke: expectedAccent,
    });
    expect(getNodeStyle(node, "neighbor")).toMatchObject({
      fill: expectedAccent,
      stroke: expectedAccent,
    });
    expect(getEdgeStyle(edge, "active").stroke).toBe(expectedAccent);
  });
});
