import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { ForgotPasswordScreen } from "@/components/auth/forgot-password-screen";
import { I18nProvider } from "@/components/providers/i18n-provider";

const replaceMock = vi.fn();

const searchParamsGetMock = vi.fn<(name: string) => string | null>(() => null);

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, refresh: vi.fn() }),
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
  (requestJson as ReturnType<typeof vi.fn>).mockReset();
});

describe("ForgotPasswordScreen", () => {
  it("renders identifier, recovery code, and new password fields", () => {
    render(
      <I18nProvider>
        <ForgotPasswordScreen />
      </I18nProvider>,
    );
    expect(screen.getByLabelText(/email|usuário|username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/recovery|recuperação|recuperaci/i)).toBeInTheDocument();
    expect(screen.getAllByLabelText(/password|senha/i).length).toBeGreaterThanOrEqual(2);
  });

  it("rejects short passwords before calling the API", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <ForgotPasswordScreen />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText(/email|usuário|username/i), "owner");
    await user.type(screen.getByLabelText(/recovery|recuperação|recuperaci/i), "aaaa-bbbb-cccc");
    const passwordFields = screen.getAllByLabelText(/password|senha/i);
    await user.type(passwordFields[0], "short");
    await user.type(passwordFields[1], "short");
    await user.click(screen.getByRole("button", { name: /reset|resetar|restablecer/i }));
    expect(requestJson).not.toHaveBeenCalled();
  });

  it("displays a success view after reset", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <ForgotPasswordScreen />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText(/email|usuário|username/i), "owner");
    await user.type(screen.getByLabelText(/recovery|recuperação|recuperaci/i), "aaaa-bbbb-cccc");
    const passwordFields = screen.getAllByLabelText(/password|senha/i);
    await user.type(passwordFields[0], "BrandNewPassw0rd!Now");
    await user.type(passwordFields[1], "BrandNewPassw0rd!Now");
    await user.click(screen.getByRole("button", { name: /reset|resetar|restablecer/i }));
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("shows the recovery code in the issued uppercase format and submits it upper-cased", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage="en-US">
        <ForgotPasswordScreen />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText(/email|username/i), "owner");
    const codeField = screen.getByLabelText(/recovery/i);
    expect(codeField).toHaveAttribute("placeholder", "XXXX-XXXX-XXXX");
    expect(codeField).toHaveAttribute("autocapitalize", "characters");
    expect(codeField).toHaveClass("uppercase");
    await user.type(codeField, "  abcd-efgh-jklm ");
    const passwordFields = screen.getAllByLabelText(/password/i);
    await user.type(passwordFields[0], "BrandNewPassw0rd!Now");
    await user.type(passwordFields[1], "BrandNewPassw0rd!Now");
    await user.click(screen.getByRole("button", { name: /reset/i }));

    expect(requestJson).toHaveBeenCalledTimes(1);
    const [url, init] = (requestJson as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/api/control-plane/auth/password/recover");
    expect(JSON.parse(String(init.body))).toMatchObject({
      identifier: "owner",
      recovery_code: "ABCD-EFGH-JKLM",
    });
  });

  it("keeps the caret in place when the recovery code is edited mid-string", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage="en-US">
        <ForgotPasswordScreen />
      </I18nProvider>,
    );
    const codeField = screen.getByLabelText(/recovery/i) as HTMLInputElement;
    await user.type(codeField, "ABDE");
    await user.type(codeField, "c", { initialSelectionStart: 2, initialSelectionEnd: 2 });
    expect(codeField).toHaveValue("ABcDE");
    expect(codeField.selectionStart).toBe(3);
  });

  it("uses a spinner-only visual state while resetting", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () => new Promise(() => {}),
    );
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage="en-US">
        <ForgotPasswordScreen />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText(/email|username/i), "owner");
    await user.type(screen.getByLabelText(/recovery/i), "aaaa-bbbb-cccc");
    const passwordFields = screen.getAllByLabelText(/password/i);
    await user.type(passwordFields[0], "BrandNewPassw0rd!Now");
    await user.type(passwordFields[1], "BrandNewPassw0rd!Now");
    await user.click(screen.getByRole("button", { name: /reset/i }));

    const busyButton = screen.getByRole("button", { name: /resetting/i });
    expect(busyButton).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText(/resetting/i)).not.toBeInTheDocument();
  });
});
