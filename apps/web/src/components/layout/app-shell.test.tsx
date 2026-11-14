import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/app-shell";
import { PLACEHOLDER_SECRETS_PATH } from "@/components/layout/placeholder-secrets-banner";
import { I18nProvider } from "@/components/providers/i18n-provider";
import type { ControlPlaneAuthStatus } from "@/lib/control-plane";
import { LOCALE_COOKIE_KEY } from "@/lib/i18n";

const ROTATION_URL =
  "https://github.com/OpenKodaAI/koda/blob/main/docs/install/local.md#rotating-placeholder-postgres-and-object-storage-secrets";

const navigation = vi.hoisted(() => ({ pathname: "/" }));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => ({
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
    replace: vi.fn(),
  }),
}));

// The shell's chrome is covered by its own tests; stub it so this test only
// exercises the frame, the real AuthProvider and the real banner.
vi.mock("@/components/layout/sidebar", () => ({ Sidebar: () => null }));
vi.mock("@/components/layout/workspace-topbar", () => ({ WorkspaceTopbar: () => null }));
vi.mock("@/components/command-bar/command-bar-modal", () => ({ CommandBarModal: () => null }));
vi.mock("@/components/layout/active-downloads-rebinder", () => ({
  ActiveDownloadsRebinder: () => null,
}));
vi.mock("@/components/ui/toast-notification", () => ({ ToastNotification: () => null }));
vi.mock("@/components/providers/app-tour-provider", () => ({
  AppTourProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const SIGNED_IN: ControlPlaneAuthStatus = {
  authenticated: true,
  has_owner: true,
  bootstrap_required: false,
  auth_mode: "local_account",
  session_required: true,
  recovery_available: true,
  operator: { id: "op-1", username: "owner", email: "owner@example.test", display_name: "Owner" },
};

function installFetch(placeholderKeys: string[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url === PLACEHOLDER_SECRETS_PATH) {
      return new Response(
        JSON.stringify({ placeholder_keys: placeholderKeys, rotation_url: ROTATION_URL }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderShell(pathname: string, initialAuth: ControlPlaneAuthStatus | null = SIGNED_IN) {
  navigation.pathname = pathname;
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider initialLanguage="en-US">
        <AppShell serverPathname={pathname} initialAuth={initialAuth}>
          <p>route content</p>
        </AppShell>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.cookie = `${LOCALE_COOKIE_KEY}=; path=/; max-age=0`;
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AppShell placeholder-secrets banner", () => {
  it.each([
    ["a regular route", "/"],
    ["the full-bleed sessions route", "/sessions"],
    ["a full-bleed agent route", "/control-plane/agents/agent-1"],
  ])("shows the banner above the route content on %s", async (_label, pathname) => {
    const fetchMock = installFetch(["POSTGRES_PASSWORD", "S3_SECRET_ACCESS_KEY"]);

    renderShell(pathname);

    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("Database and object-storage secrets are still placeholders");
    expect(within(banner).getByRole("link", { name: "Rotation steps" })).toHaveAttribute(
      "href",
      ROTATION_URL,
    );
    // Inside the dashboard frame, directly before the route stage, so fixed-height
    // routes give the stage the space left after the banner.
    const main = screen.getByRole("main");
    expect(main).toContainElement(banner);
    const routeStage = screen.getByText("route content").closest(".route-stage");
    expect(routeStage).not.toBeNull();
    expect(banner.nextElementSibling).toBe(routeStage);
    expect(fetchMock).toHaveBeenCalledWith(PLACEHOLDER_SECRETS_PATH, expect.anything());
  });

  it("shows nothing when every storage secret is real", async () => {
    const fetchMock = installFetch([]);

    renderShell("/");

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(PLACEHOLDER_SECRETS_PATH, expect.anything()),
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.getByText("route content")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("leaves the full-screen auth routes alone", async () => {
    const fetchMock = installFetch(["POSTGRES_PASSWORD"]);

    renderShell("/login", null);

    expect(screen.getByText("route content")).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchMock).not.toHaveBeenCalledWith(PLACEHOLDER_SECRETS_PATH, expect.anything());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
