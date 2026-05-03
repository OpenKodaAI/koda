import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, FORCE_SIGN_OUT_EVENT, useAuth } from "@/components/providers/auth-provider";
import { ToastProvider } from "@/hooks/use-toast";
import { ToastNotification } from "@/components/ui/toast-notification";
import { I18nProvider } from "@/components/providers/i18n-provider";

const replaceMock = vi.fn();
const refreshMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, refresh: refreshMock }),
}));

const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
const originalFetch = globalThis.fetch;

beforeEach(() => {
  replaceMock.mockReset();
  refreshMock.mockReset();
  fetchMock.mockReset().mockResolvedValue(new Response("{}", { status: 200 }));
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

const operator = {
  id: "op_1",
  email: "owner@koda.dev",
  username: "owner",
  display_name: "Owner",
};

const initialAuth = {
  authenticated: true,
  has_owner: true,
  bootstrap_required: false,
  auth_mode: "session",
  session_required: true,
  recovery_available: true,
  operator,
};

function Probe() {
  const auth = useAuth();
  return (
    <>
      <span data-testid="email">{auth.operator?.email ?? "anon"}</span>
      <button type="button" onClick={() => void auth.signOut()}>
        Sign out
      </button>
    </>
  );
}

function renderWithProviders(ui: React.ReactNode) {
  return render(
    <I18nProvider initialLanguage="en-US">
      <ToastProvider>
        <AuthProvider initialAuth={initialAuth}>
          {ui}
          <ToastNotification />
        </AuthProvider>
      </ToastProvider>
    </I18nProvider>,
  );
}

describe("AuthProvider", () => {
  it("exposes the initial operator", () => {
    renderWithProviders(<Probe />);
    expect(screen.getByTestId("email").textContent).toBe("owner@koda.dev");
  });

  it("clears the operator and redirects on signOut()", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Probe />);
    await user.click(screen.getByText("Sign out"));
    expect(screen.getByTestId("email").textContent).toBe("anon");
    expect(replaceMock).toHaveBeenCalledWith("/login");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/control-plane/auth/logout",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("redirects silently on a GET force-sign-out event", () => {
    renderWithProviders(<Probe />);
    act(() => {
      window.dispatchEvent(
        new CustomEvent(FORCE_SIGN_OUT_EVENT, {
          detail: { method: "GET", pathname: "/sessions/abc" },
        }),
      );
    });
    expect(replaceMock).toHaveBeenCalledWith(
      `/login?next=${encodeURIComponent("/sessions/abc")}`,
    );
  });

  it("shows the generic toast on a MUTATION force-sign-out event", () => {
    renderWithProviders(<Probe />);
    act(() => {
      window.dispatchEvent(
        new CustomEvent(FORCE_SIGN_OUT_EVENT, {
          detail: { method: "MUTATION", pathname: "/sessions" },
        }),
      );
    });
    expect(replaceMock).toHaveBeenCalledWith(
      `/login?next=${encodeURIComponent("/sessions")}`,
    );
    // The toast text comes from the translations bundle.
    expect(screen.getByText(/session has expired/i)).toBeInTheDocument();
  });

  it("ignores unsafe ?next paths from force-sign-out events", () => {
    renderWithProviders(<Probe />);
    act(() => {
      window.dispatchEvent(
        new CustomEvent(FORCE_SIGN_OUT_EVENT, {
          detail: { method: "GET", pathname: "//evil.com" },
        }),
      );
    });
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });
});
