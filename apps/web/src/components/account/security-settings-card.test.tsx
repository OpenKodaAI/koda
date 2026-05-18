import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SecuritySettingsCard } from "@/components/account/security-settings-card";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ToastNotification } from "@/components/ui/toast-notification";
import { ToastProvider } from "@/hooks/use-toast";
import { requestJson } from "@/lib/http-client";

vi.mock("@/lib/http-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/http-client")>("@/lib/http-client");
  return {
    ...actual,
    requestJson: vi.fn(),
  };
});

const requestJsonMock = vi.mocked(requestJson);

function renderCard() {
  return render(
    <I18nProvider initialLanguage="en-US">
      <ToastProvider>
        <SecuritySettingsCard />
        <ToastNotification />
      </ToastProvider>
    </I18nProvider>,
  );
}

beforeEach(() => {
  requestJsonMock.mockReset();
});

describe("SecuritySettingsCard", () => {
  it("loads recovery-code status into the compact security summary", async () => {
    requestJsonMock.mockResolvedValueOnce({
      total: 10,
      remaining: 7,
      generated_at: "2026-05-17T10:00:00Z",
    });

    renderCard();

    expect(await screen.findByText("7/10")).toBeInTheDocument();
    expect(screen.getByText("Operator managed")).toBeInTheDocument();
    expect(await screen.findByText("Security status loaded.")).toBeInTheDocument();
    expect(requestJsonMock).toHaveBeenCalledWith("/api/control-plane/auth/recovery-codes");
  });

  it("regenerates recovery codes and refreshes the summary", async () => {
    const user = userEvent.setup();
    requestJsonMock
      .mockResolvedValueOnce({
        total: 10,
        remaining: 7,
        generated_at: "2026-05-17T10:00:00Z",
      })
      .mockResolvedValueOnce({ recovery_codes: ["R-111", "R-222"] })
      .mockResolvedValueOnce({
        total: 10,
        remaining: 10,
        generated_at: "2026-05-17T10:30:00Z",
      });

    renderCard();
    await screen.findByText("7/10");

    const currentPasswordFields = screen.getAllByPlaceholderText(
      "Enter your current password to continue.",
    );
    await user.type(currentPasswordFields[1], "CorrectHorseBattery!9");
    await user.click(screen.getByRole("button", { name: "Regenerate recovery codes" }));

    expect(await screen.findByText("R-111")).toBeInTheDocument();
    expect(screen.getByText("R-222")).toBeInTheDocument();
    expect(await screen.findByText("Recovery codes regenerated.")).toBeInTheDocument();
    expect(await screen.findByText("Recovery status refreshed.")).toBeInTheDocument();
    await waitFor(() => expect(requestJsonMock).toHaveBeenCalledTimes(3));
    expect(requestJsonMock).toHaveBeenNthCalledWith(
      2,
      "/api/control-plane/auth/recovery-codes/regenerate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ current_password: "CorrectHorseBattery!9" }),
      }),
    );
  });

  it("changes the password with loading-safe request feedback", async () => {
    const user = userEvent.setup();
    requestJsonMock
      .mockResolvedValueOnce({
        total: 10,
        remaining: 7,
        generated_at: "2026-05-17T10:00:00Z",
      })
      .mockResolvedValueOnce({ ok: true });

    renderCard();
    await screen.findByText("7/10");

    const currentPasswordFields = screen.getAllByPlaceholderText(
      "Enter your current password to continue.",
    );
    const newPasswordField = screen.getByPlaceholderText("New password");
    await user.type(currentPasswordFields[0], "CorrectHorseBattery!9");
    await user.type(newPasswordField, "NewCorrectHorseBattery!9");
    await user.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByText("Password updated.")).toBeInTheDocument();
    await waitFor(() => expect(requestJsonMock).toHaveBeenCalledTimes(2));
    expect(requestJsonMock).toHaveBeenNthCalledWith(
      2,
      "/api/control-plane/auth/password/change",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          current_password: "CorrectHorseBattery!9",
          new_password: "NewCorrectHorseBattery!9",
        }),
      }),
    );
    expect(currentPasswordFields[0]).toHaveValue("");
    expect(newPasswordField).toHaveValue("");
  });
});
