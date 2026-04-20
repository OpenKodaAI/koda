import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { SetupScreen } from "@/components/setup/setup-screen";
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

function renderSetup(props = {}) {
  return render(
    <I18nProvider>
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
