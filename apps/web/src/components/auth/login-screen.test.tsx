import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { LoginScreen } from "@/components/auth/login-screen";
import { I18nProvider } from "@/components/providers/i18n-provider";

const replaceMock = vi.fn();
const refreshMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, refresh: refreshMock }),
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

  it("shows a generic error when credentials are rejected", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("Invalid credentials."));
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
    expect(await screen.findByText(/invalid credentials|credenciais inválidas|inválidas/i)).toBeInTheDocument();
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
});
