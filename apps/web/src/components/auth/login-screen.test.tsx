import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { LoginScreen } from "@/components/auth/login-screen";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ApiError } from "@/lib/errors";
import {
  type AppLanguage,
  LOCALE_COOKIE_KEY,
  SUPPORTED_LANGUAGES,
  translateForLanguage,
} from "@/lib/i18n";

const replaceMock = vi.fn();
const refreshMock = vi.fn();

const searchParamsGetMock = vi.fn<(name: string) => string | null>(() => null);

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, refresh: refreshMock }),
  useSearchParams: () => ({ get: searchParamsGetMock }),
}));

vi.mock("@/lib/http-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http-client")>("@/lib/http-client");
  return {
    ...actual,
    requestJson: vi.fn(),
  };
});

import { requestJson } from "@/lib/http-client";

beforeEach(() => {
  replaceMock.mockClear();
  refreshMock.mockClear();
  (requestJson as ReturnType<typeof vi.fn>).mockReset();
  // The i18n provider persists the active language and applies it on the next mount; reset
  // it so every test, in any order, renders the language it asks for.
  window.localStorage.clear();
  document.cookie = `${LOCALE_COOKIE_KEY}=; path=/; max-age=0`;
});

describe("LoginScreen", () => {
  it("renders identifier and password fields with a submit button", () => {
    render(
      <I18nProvider>
        <LoginScreen />
      </I18nProvider>,
    );
    expect(screen.getByLabelText(/email|usuário|username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password|senha/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in|entrar/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /lost my password|esqueci|olvidé/i })).toBeInTheDocument();
  });

  it("shows a generic error when credentials are rejected (4xx)", async () => {
    // Simulates the proxy returning 401 — wrong password / unknown user /
    // locked account all collapse here per the auth contract.
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("Invalid credentials.", 401),
    );
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <LoginScreen />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText(/email|usuário|username/i), "owner");
    await user.type(screen.getByLabelText(/password|senha/i), "wrong-password-attempt-XX");
    await user.click(screen.getByRole("button", { name: /sign in|entrar/i }));
    // Error is always generic — never reveals whether the account exists.
    expect(
      await screen.findByText(/invalid credentials|credenciais inválidas|inválidas/i),
    ).toBeInTheDocument();
  });

  it("says HTTPS is required when the dashboard refuses sign-in over plain HTTP", async () => {
    // The refusal is decided before any credential is checked, so naming it
    // reveals nothing about accounts.
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("Sign-in needs HTTPS.", 403, { reason: "INSECURE_TRANSPORT" }),
    );
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage="en-US">
        <LoginScreen />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText(/email|username/i), "owner");
    await user.type(screen.getByLabelText(/password/i), "any-password");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/over plain HTTP/i)).toBeInTheDocument();
    expect(screen.queryByText(/invalid credentials/i)).not.toBeInTheDocument();
  });

  it("shows a service-unavailable message when the upstream is down (503)", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("Login service did not respond within 6000ms", 503),
    );
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <LoginScreen />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText(/email|usuário|username/i), "owner");
    await user.type(screen.getByLabelText(/password|senha/i), "any-password");
    await user.click(screen.getByRole("button", { name: /sign in|entrar/i }));
    expect(
      await screen.findByText(
        /service is temporarily unavailable|temporariamente indisponível|momentaneamente/i,
      ),
    ).toBeInTheDocument();
  });

  it("shows a service-unavailable message when fetch fails (network error)", async () => {
    // No status — plain Error simulates `fetch` throwing before producing a Response.
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("fetch failed"),
    );
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <LoginScreen />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText(/email|usuário|username/i), "owner");
    await user.type(screen.getByLabelText(/password|senha/i), "any-password");
    await user.click(screen.getByRole("button", { name: /sign in|entrar/i }));
    expect(
      await screen.findByText(
        /service is temporarily unavailable|temporariamente indisponível|momentaneamente/i,
      ),
    ).toBeInTheDocument();
  });

  it("redirects to dashboard on successful login", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <LoginScreen />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText(/email|usuário|username/i), "owner");
    await user.type(screen.getByLabelText(/password|senha/i), "CorrectHorseBattery!9");
    await user.click(screen.getByRole("button", { name: /sign in|entrar/i }));
    await vi.waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/");
    });
  });

  it("uses a spinner-only visual state while submitting", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () => new Promise(() => {}),
    );
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage="en-US">
        <LoginScreen />
      </I18nProvider>,
    );

    await user.type(screen.getByLabelText(/email|username/i), "owner");
    await user.type(screen.getByLabelText(/password/i), "CorrectHorseBattery!9");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    const busyButton = screen.getByRole("button", { name: /signing in/i });
    expect(busyButton).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText(/signing in/i)).not.toBeInTheDocument();
  });
});

describe("LoginScreen rate limiting (ADR-038)", () => {
  function tr(language: AppLanguage, key: string, options?: Record<string, unknown>) {
    return translateForLanguage(language, key, options);
  }

  function seconds(language: AppLanguage, value: number) {
    return new Intl.NumberFormat(language, { style: "unit", unit: "second", unitDisplay: "long" }).format(value);
  }

  async function submitLogin(language: AppLanguage) {
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage={language}>
        <LoginScreen />
      </I18nProvider>,
    );
    fireEvent.change(screen.getByLabelText(tr(language, "auth.login.identifier")), {
      target: { value: "owner" },
    });
    fireEvent.change(screen.getByLabelText(tr(language, "auth.login.password")), {
      target: { value: "wrong-password-attempt-XX" },
    });
    await user.click(screen.getByRole("button", { name: tr(language, "auth.login.submit") }));
  }

  it.each(SUPPORTED_LANGUAGES)("tells a rate-limited client how long to wait in %s", async (language) => {
    // The login bucket (10 per 5 minutes) takes its next request 30 s after a burst.
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("Too many attempts. Try again later.", 429, { retryAfterSeconds: 30 }),
    );

    await submitLogin(language);

    // The DOM matcher folds the no-break space some locales put before "seconds".
    const expected = tr(language, "auth.rate_limited.with_wait", { duration: seconds(language, 30) }).replace(
      /\s+/g,
      " ",
    );
    expect(expected).not.toBe("auth.rate_limited.with_wait");
    expect(await screen.findByText(expected)).toBeInTheDocument();
    expect(screen.queryByText(tr(language, "auth.login.generic_error"))).not.toBeInTheDocument();
  });

  it("asks to wait a moment when the response names no wait", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("rate limit exceeded", 429),
    );

    await submitLogin("en-US");

    expect(await screen.findByText(tr("en-US", "auth.rate_limited.no_wait"))).toBeInTheDocument();
    expect(screen.queryByText(tr("en-US", "auth.login.generic_error"))).not.toBeInTheDocument();
  });

  it.each(SUPPORTED_LANGUAGES)("keeps a locked account on the generic error in %s", async (language) => {
    // The per-account lockout answers exactly like a wrong password: not a 429.
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("Invalid credentials.", 400),
    );

    await submitLogin(language);

    expect(await screen.findByText(tr(language, "auth.login.generic_error"))).toBeInTheDocument();
    expect(screen.queryByText(tr(language, "auth.rate_limited.no_wait"))).not.toBeInTheDocument();
  });
});
