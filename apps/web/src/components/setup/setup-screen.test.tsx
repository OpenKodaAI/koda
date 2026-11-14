import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { SetupScreen } from "@/components/setup/setup-screen";
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

function renderSetup(props = {}, language?: AppLanguage) {
  return render(
    <I18nProvider initialLanguage={language}>
      <SetupScreen
        authStatus={{
          authenticated: false,
          has_owner: false,
          bootstrap_required: true,
          auth_mode: "local_account",
          session_required: false,
          recovery_available: false,
          loopback_trust_enabled: true,
          bootstrap_file_path: "/var/lib/koda/state/control_plane/bootstrap.txt",
        }}
        {...props}
      />
    </I18nProvider>,
  );
}

beforeEach(() => {
  replaceMock.mockClear();
  refreshMock.mockClear();
  (requestJson as ReturnType<typeof vi.fn>).mockReset();
  window.sessionStorage.clear();
  // The i18n provider persists the active language and applies it on the next mount; reset
  // it so every test, in any order, renders the language it asks for.
  window.localStorage.clear();
  document.cookie = `${LOCALE_COOKIE_KEY}=; path=/; max-age=0`;
});

describe("SetupScreen (create account step)", () => {
  it("renders the create-account step by default", () => {
    renderSetup();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getAllByLabelText(/password|senha/i).length).toBeGreaterThan(0);
  });

  it("shows the bootstrap code field regardless of loopback trust", () => {
    renderSetup();
    expect(
      screen.getByRole("group", { name: /bootstrap code|código de bootstrap/i }),
    ).toBeInTheDocument();
  });

  it("shows the bootstrap code field when loopback trust is disabled", () => {
    renderSetup({
      authStatus: {
        authenticated: false,
        has_owner: false,
        bootstrap_required: true,
        auth_mode: "local_account",
        session_required: false,
        recovery_available: false,
        loopback_trust_enabled: false,
        bootstrap_file_path: "/state/bootstrap.txt",
      },
    });
    expect(
      screen.getByRole("group", { name: /bootstrap code|código de bootstrap/i }),
    ).toBeInTheDocument();
  });

  it("rejects mismatched passwords without calling the API", async () => {
    const user = userEvent.setup();
    renderSetup();
    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    const passwordFields = screen.getAllByLabelText(/password|senha/i);
    await user.type(passwordFields[0], "CorrectHorseBattery!9");
    await user.type(passwordFields[1], "Different123!Password");
    await user.click(screen.getByRole("button", { name: /create account|criar conta/i }));
    expect(requestJson).not.toHaveBeenCalled();
  });

  it("advances to recovery codes step on successful registration", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      recovery_codes: ["aaaa-bbbb-cccc", "dddd-eeee-ffff"],
      operator: null,
      auth: null,
    });
    const user = userEvent.setup();
    renderSetup();
    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    const passwordFields = screen.getAllByLabelText(/password|senha/i);
    await user.type(passwordFields[0], "CorrectHorseBattery!9");
    await user.type(passwordFields[1], "CorrectHorseBattery!9");
    await user.click(screen.getByRole("button", { name: /create account|criar conta/i }));
    await screen.findByText(/aaaa-bbbb-cccc/);
    expect(screen.getByText(/dddd-eeee-ffff/)).toBeInTheDocument();
  });

  it("says HTTPS is required when the dashboard refuses owner creation over plain HTTP", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("Sign-in needs HTTPS.", 403, { reason: "INSECURE_TRANSPORT" }),
    );
    const user = userEvent.setup();
    renderSetup();
    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    const passwordFields = screen.getAllByLabelText(/password|senha/i);
    await user.type(passwordFields[0], "CorrectHorseBattery!9");
    await user.type(passwordFields[1], "CorrectHorseBattery!9");
    await user.click(screen.getByRole("button", { name: /create account|criar conta/i }));
    expect(
      await screen.findByText(/over plain HTTP/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Sign-in needs HTTPS\./)).not.toBeInTheDocument();
  });

  it("uses a spinner-only visual state while creating the owner", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () => new Promise(() => {}),
    );
    const user = userEvent.setup();
    renderSetup();
    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    const passwordFields = screen.getAllByLabelText(/password|senha/i);
    await user.type(passwordFields[0], "CorrectHorseBattery!9");
    await user.type(passwordFields[1], "CorrectHorseBattery!9");
    await user.click(screen.getByRole("button", { name: /create account|criar conta/i }));

    const busyButton = screen.getByRole("button", { name: /creating/i });
    expect(busyButton).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText(/creating/i)).not.toBeInTheDocument();
  });

  it("does not advance when registration returns no recovery codes", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      recovery_codes: [],
      operator: null,
      auth: null,
    });
    const user = userEvent.setup();
    renderSetup();
    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    const passwordFields = screen.getAllByLabelText(/password|senha/i);
    await user.type(passwordFields[0], "CorrectHorseBattery!9");
    await user.type(passwordFields[1], "CorrectHorseBattery!9");
    await user.click(screen.getByRole("button", { name: /create account|criar conta/i }));
    expect(await screen.findByText(/recovery codes were not issued/i)).toBeInTheDocument();
    expect(screen.queryByText(/save your recovery codes|salve seus códigos/i)).not.toBeInTheDocument();
  });

  it("requires the acknowledge checkbox before leaving recovery codes", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      recovery_codes: ["aaaa-bbbb-cccc"],
      operator: null,
      auth: null,
    });
    const user = userEvent.setup();
    renderSetup();
    await user.type(screen.getByLabelText(/email/i), "owner@example.com");
    const passwordFields = screen.getAllByLabelText(/password|senha/i);
    await user.type(passwordFields[0], "CorrectHorseBattery!9");
    await user.type(passwordFields[1], "CorrectHorseBattery!9");
    await user.click(screen.getByRole("button", { name: /create account|criar conta/i }));
    const continueButton = await screen.findByRole("button", { name: /workspace|espaço de trabajo|espacio de trabajo/i });
    expect(continueButton).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    expect(continueButton).not.toBeDisabled();
  });
});

describe("SetupScreen rate limiting (ADR-038)", () => {
  function tr(language: AppLanguage, key: string, options?: Record<string, unknown>) {
    return translateForLanguage(language, key, options);
  }

  function minutes(language: AppLanguage, value: number) {
    return new Intl.NumberFormat(language, { style: "unit", unit: "minute", unitDisplay: "long" }).format(value);
  }

  async function submitSetup(language: AppLanguage) {
    const user = userEvent.setup();
    renderSetup({}, language);
    // Look every field up before typing: the strength meter joins the password label.
    const email = screen.getByLabelText(tr(language, "auth.setup.create_account.email"));
    const password = screen.getByLabelText(tr(language, "auth.setup.create_account.password"));
    const confirm = screen.getByLabelText(tr(language, "auth.setup.create_account.confirm_password"));
    fireEvent.change(email, { target: { value: "owner@example.com" } });
    fireEvent.change(password, { target: { value: "CorrectHorseBattery!9" } });
    fireEvent.change(confirm, { target: { value: "CorrectHorseBattery!9" } });
    await user.click(
      screen.getByRole("button", { name: tr(language, "auth.setup.create_account.submit") }),
    );
  }

  it.each(SUPPORTED_LANGUAGES)("tells a rate-limited client how long to wait in %s", async (language) => {
    // The setup bucket (30 per hour) takes its next request 2 minutes after a burst.
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("Too many attempts. Try again later.", 429, { retryAfterSeconds: 120 }),
    );

    await submitSetup(language);

    const expected = tr(language, "auth.rate_limited.with_wait", { duration: minutes(language, 2) });
    expect(expected).not.toBe("auth.rate_limited.with_wait");
    expect(await screen.findByText(expected)).toBeInTheDocument();
    expect(screen.queryByText("Too many attempts. Try again later.")).not.toBeInTheDocument();
  });

  it("asks to wait a moment when the response names no wait", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("rate limit exceeded", 429),
    );

    await submitSetup("en-US");

    expect(await screen.findByText(tr("en-US", "auth.rate_limited.no_wait"))).toBeInTheDocument();
    expect(screen.queryByText("rate limit exceeded")).not.toBeInTheDocument();
  });

  it("keeps any other setup failure on its own message", async () => {
    (requestJson as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("Setup code is invalid or expired.", 400),
    );

    await submitSetup("en-US");

    expect(await screen.findByText("Setup code is invalid or expired.")).toBeInTheDocument();
    expect(screen.queryByText(tr("en-US", "auth.rate_limited.no_wait"))).not.toBeInTheDocument();
  });
});

describe("SetupScreen password strength meter", () => {
  // One password per strength, by the meter's score (length, character classes, distinct characters).
  const STRENGTHS = [
    ["weak", "short"],
    ["fair", "abcdefghijkl"],
    ["good", "abcdefghijK1"],
    ["strong", "abcdefghijklmnK1!"],
  ] as const;

  it.each(SUPPORTED_LANGUAGES)("names each strength in %s", (language) => {
    renderSetup({}, language);
    const password = screen.getByLabelText(
      translateForLanguage(language, "auth.setup.create_account.password"),
    );

    for (const [strength, value] of STRENGTHS) {
      const key = `auth.setup.create_account.strength.${strength}`;
      const label = translateForLanguage(language, key);
      fireEvent.change(password, { target: { value } });

      expect(label, `${language} ${strength}`).not.toBe(key);
      expect(screen.getByText(label)).toBeInTheDocument();
      expect(document.body.textContent).not.toContain("auth.setup.create_account.strength");
    }
  });
});
