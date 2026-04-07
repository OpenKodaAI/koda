import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/layout/app-shell";

let pathname = "/";

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
}));

vi.mock("@/hooks/use-local-storage", () => ({
  useLocalStorage: () => [false, vi.fn()],
}));

vi.mock("@/components/layout/sidebar", () => ({
  Sidebar: () => <div>sidebar</div>,
}));

vi.mock("@/components/layout/workspace-topbar", () => ({
  WorkspaceTopbar: () => <div>Agents • Catalog, editing and publishing for agents.</div>,
}));

vi.mock("@/components/providers/app-tour-provider", () => ({
  AppTourProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/ui/toast-notification", () => ({
  ToastNotification: () => null,
}));

vi.mock("@/hooks/use-toast", () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/layout/route-stage", () => ({
  RouteStage: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe("AppShell", () => {
  beforeEach(() => {
    pathname = "/";
  });

  it("hides the operational chrome on /control-plane/setup", () => {
    pathname = "/control-plane/setup";

    render(
      <AppShell>
        <div>setup-content</div>
      </AppShell>,
    );

    expect(screen.queryByText("sidebar")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Agents • Catalog, editing and publishing for agents."),
    ).not.toBeInTheDocument();
    expect(screen.getByText("setup-content")).toBeInTheDocument();
  });

  it("keeps the operational chrome on normal control-plane routes", () => {
    pathname = "/control-plane";

    render(
      <AppShell>
        <div>catalog-content</div>
      </AppShell>,
    );

    expect(screen.getByText("sidebar")).toBeInTheDocument();
    expect(screen.getByText("Agents • Catalog, editing and publishing for agents.")).toBeInTheDocument();
    expect(screen.getByText("catalog-content")).toBeInTheDocument();
  });
});
