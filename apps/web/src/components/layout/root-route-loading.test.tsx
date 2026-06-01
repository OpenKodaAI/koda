import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RootRouteLoadingForPathname } from "@/components/layout/root-route-loading";

describe("RootRouteLoadingForPathname", () => {
  it("uses a neutral transition indicator for route changes", () => {
    render(<RootRouteLoadingForPathname pathname="/routines" />);

    expect(screen.getByTestId("root-route-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("routine-schedules-route-loading")).not.toBeInTheDocument();
    expect(screen.queryByTestId("overview-route-loading")).not.toBeInTheDocument();
  });

  it("does not depend on the previous pathname", () => {
    const { rerender } = render(<RootRouteLoadingForPathname pathname="/" />);

    expect(screen.getByTestId("root-route-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("overview-route-loading")).not.toBeInTheDocument();

    rerender(<RootRouteLoadingForPathname pathname="/executions" />);

    expect(screen.getByTestId("root-route-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("executions-route-loading")).not.toBeInTheDocument();
    expect(screen.queryByTestId("overview-route-loading")).not.toBeInTheDocument();
  });

  it("keeps the indicator accessible without visible loading copy", () => {
    render(<RootRouteLoadingForPathname pathname="/sessions" />);

    expect(screen.getByRole("status", { name: "Loading route" })).toBeInTheDocument();
    expect(screen.queryByText("Loading route", { selector: "div" })).not.toBeInTheDocument();
  });
});
