import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  AgentEditorRouteLoading,
  ControlPlaneCatalogLoading,
  ControlPlaneSystemLoading,
  MemoryRouteLoading,
  OverviewRouteLoading,
  RuntimeTaskRouteLoading,
  RuntimeRouteLoading,
  SessionsRouteLoading,
  TableRouteLoading,
} from "@/components/layout/route-loading";

describe("route loading skeletons", () => {
  it("renders stable loading shells for the main sidebar routes", () => {
    render(
      <div>
        <OverviewRouteLoading />
        <RuntimeRouteLoading />
        <TableRouteLoading />
        <SessionsRouteLoading />
        <MemoryRouteLoading />
        <ControlPlaneCatalogLoading />
        <ControlPlaneSystemLoading />
        <AgentEditorRouteLoading />
        <RuntimeTaskRouteLoading />
      </div>,
    );

    expect(screen.getByTestId("overview-route-loading")).toBeInTheDocument();
    expect(screen.getByTestId("runtime-route-loading")).toBeInTheDocument();
    expect(screen.getByTestId("table-route-loading")).toBeInTheDocument();
    expect(screen.getByTestId("sessions-route-loading")).toBeInTheDocument();
    expect(screen.getByTestId("memory-route-loading")).toBeInTheDocument();
    expect(screen.getByTestId("control-plane-catalog-loading")).toBeInTheDocument();
    expect(screen.getByTestId("control-plane-system-loading")).toBeInTheDocument();
    expect(screen.getByTestId("agent-editor-route-loading")).toBeInTheDocument();
    expect(screen.getByTestId("runtime-task-route-loading")).toBeInTheDocument();
  });
});
