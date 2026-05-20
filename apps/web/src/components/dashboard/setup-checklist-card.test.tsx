import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SetupChecklistCard, type SetupChecklistSnapshot } from "@/components/dashboard/setup-checklist-card";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { requestJson } from "@/lib/http-client";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/http-client", () => ({
  requestJson: vi.fn(),
}));

const requestJsonMock = vi.mocked(requestJson);

const baseSnapshot: SetupChecklistSnapshot = {
  providerReady: true,
  agentReady: true,
  telegramReady: true,
  channelReady: false,
  firstTaskReady: false,
  firstTraceReady: false,
  readinessStatus: "warning",
  primaryAgentId: "ATLAS",
  readinessActions: [],
};

function renderCard(snapshot: SetupChecklistSnapshot = baseSnapshot) {
  return render(
    <I18nProvider initialLanguage="pt-BR">
      <SetupChecklistCard snapshot={snapshot} />
    </I18nProvider>,
  );
}

describe("SetupChecklistCard", () => {
  beforeEach(() => {
    window.localStorage.clear();
    requestJsonMock.mockReset();
    requestJsonMock.mockResolvedValue({});
  });

  it("shows Phase 6 readiness steps and creates the first task through the backend", async () => {
    const user = userEvent.setup();
    renderCard();

    expect(screen.getByText("Pair Telegram sender")).toBeInTheDocument();
    expect(screen.getByText("Run first task")).toBeInTheDocument();
    expect(screen.getByText("Open first trace")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() =>
      expect(requestJsonMock).toHaveBeenCalledWith(
        "/api/control-plane/onboarding/first-task",
        {
          method: "POST",
          body: JSON.stringify({ agent_id: "ATLAS" }),
        },
      ),
    );
  });
});
