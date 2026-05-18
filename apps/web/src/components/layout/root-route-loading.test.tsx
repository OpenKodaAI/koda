import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RootRouteLoadingForPathname } from "@/components/layout/root-route-loading";

describe("RootRouteLoadingForPathname", () => {
  it("uses the routines skeleton for the routines redirect segment", () => {
    render(<RootRouteLoadingForPathname pathname="/routines" />);

    expect(screen.getByTestId("routine-schedules-route-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("overview-route-loading")).not.toBeInTheDocument();
  });

  it("uses the routines skeleton for the schedules route", () => {
    render(<RootRouteLoadingForPathname pathname="/routines/schedules" />);

    expect(screen.getByTestId("routine-schedules-route-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("overview-route-loading")).not.toBeInTheDocument();
  });

  it("keeps the overview skeleton as the root fallback", () => {
    render(<RootRouteLoadingForPathname pathname="/" />);

    expect(screen.getByTestId("overview-route-loading")).toBeInTheDocument();
  });
});
