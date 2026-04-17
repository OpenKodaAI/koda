import type { HTMLAttributes, ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import type {
  ControlPlaneAuthStatus,
  ControlPlaneOnboardingStatus,
} from "@/lib/control-plane";

vi.mock("framer-motion", () => {
  const createMotion = (Tag: "div" | "button" | "aside") => {
    function MotionMock({ children, ...props }: HTMLAttributes<HTMLElement>) {
      return <Tag {...props}>{children}</Tag>;
    }
    MotionMock.displayName = `Motion${Tag[0]?.toUpperCase() ?? "D"}${Tag.slice(1)}Mock`;
    return MotionMock;
  };
  return {
    AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
    motion: new Proxy(
      {},
      {
        get: (_target, key: string) => {
          if (key === "button") return createMotion("button");
          if (key === "aside") return createMotion("aside");
          return createMotion("div");
        },
      },
    ),
  };
});

const routerRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: routerRefresh,
    replace: vi.fn(),
    push: vi.fn(),
  }),
  usePathname: () => "/setup",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/layout/koda-mark", () => ({
  KodaMark: () => <span data-testid="koda-mark" />,
}));
vi.mock("@/components/layout/language-switcher", () => ({
  LanguageSwitcher: () => <div data-testid="lang-switcher" />,
}));
vi.mock("@/components/layout/theme-switcher", () => ({
  ThemeSwitcher: () => <div data-testid="theme-switcher" />,
}));

function makeAuthStatus(overrides: Partial<ControlPlaneAuthStatus> = {}): ControlPlaneAuthStatus {
  return {
    authenticated: false,
    has_owner: false,
    bootstrap_required: true,
    auth_mode: "local_account",
    session_required: true,
    recovery_available: false,
    ...overrides,
  };
}

function makeOnboardingStatus(
  overrides: Partial<ControlPlaneOnboardingStatus> = {},
): ControlPlaneOnboardingStatus {
  return {
    has_owner: false,
    control_plane: { ready: true },
    storage: {
      database: { ready: true },
      object_storage: { ready: true },
    },
    providers: [],
    agents: [],
    system: {
      owner_name: null,
      owner_email: null,
      owner_github: null,
      allowed_user_ids: [],
      default_provider: null,
    },
    steps: {
      provider_configured: false,
      access_configured: false,
      agent_ready: false,
      storage_ready: true,
      onboarding_complete: false,
    },
    ...overrides,
  } as ControlPlaneOnboardingStatus;
}

afterEach(() => {
  routerRefresh.mockReset();
  vi.unstubAllGlobals();
});

describe("SetupScreen", () => {
  it("renders the setup-code step first when no session or owner", async () => {
    const { SetupScreen } = await import("@/components/setup/setup-screen");

    render(
      <I18nProvider initialLanguage="en-US">
        <SetupScreen
          authStatus={makeAuthStatus()}
          onboardingStatus={makeOnboardingStatus()}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Paste your setup code")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue/ })).toBeInTheDocument();
  });

  it("advances to register-owner after exchanging a setup code", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, registration_token: "tok-123", expires_at: null }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { SetupScreen } = await import("@/components/setup/setup-screen");

    render(
      <I18nProvider initialLanguage="en-US">
        <SetupScreen
          authStatus={makeAuthStatus()}
          onboardingStatus={makeOnboardingStatus()}
        />
      </I18nProvider>,
    );

    const input = screen.getByPlaceholderText("ABCD-EFGH-JKLM");
    fireEvent.change(input, { target: { value: "abcd-efgh-jklm" } });

    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));

    await waitFor(() => {
      expect(screen.getByText("Create the owner account")).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/control-plane/auth/bootstrap/exchange",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows the login step when owner already exists but no session", async () => {
    const { SetupScreen } = await import("@/components/setup/setup-screen");

    render(
      <I18nProvider initialLanguage="en-US">
        <SetupScreen
          authStatus={makeAuthStatus({ has_owner: true })}
          onboardingStatus={makeOnboardingStatus({ has_owner: true })}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Sign in to continue")).toBeInTheDocument();
  });

  it("shows the finish-platform step when session is active", async () => {
    const { SetupScreen } = await import("@/components/setup/setup-screen");

    render(
      <I18nProvider initialLanguage="en-US">
        <SetupScreen
          authStatus={makeAuthStatus({
            authenticated: true,
            has_owner: true,
            operator: { username: "owner", email: "owner@koda.dev", display_name: "Owner" },
          })}
          onboardingStatus={makeOnboardingStatus({ has_owner: true })}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Finish platform setup")).toBeInTheDocument();
  });
});
