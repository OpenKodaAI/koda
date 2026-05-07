import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { ApprovalPrompt } from "@/components/sessions/chat/approval-prompt";

vi.mock("@/lib/control-plane-dashboard", () => ({
  mutateControlPlaneDashboardJson: vi.fn(),
}));

import { mutateControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("ApprovalPrompt", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("submits approval with rationale", async () => {
    (mutateControlPlaneDashboardJson as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      approval: { approval_id: "op-1", decision: "approved" },
    });

    const onResolved = vi.fn();
    renderWithClient(
      <ApprovalPrompt
        agentId="bot-1"
        sessionId="sess-1"
        approvalId="op-1"
        toolName="shell rm -rf"
        reasons={["Write access outside allowed path"]}
        preview="rm -rf /tmp/foo"
        onResolved={onResolved}
      />,
    );

    expect(screen.getByText(/Approval required/i)).toBeInTheDocument();
    expect(screen.getByText(/shell rm -rf/i)).toBeInTheDocument();
    expect(screen.getByText(/Write access/i)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/optional rationale/i), {
      target: { value: "trusted" },
    });
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));

    await Promise.resolve();
    await Promise.resolve();

    expect(mutateControlPlaneDashboardJson).toHaveBeenCalledWith(
      "/agents/bot-1/approvals/op-1",
      expect.objectContaining({
        method: "POST",
        body: { decision: "approve", rationale: "trusted" },
      }),
    );
    expect(onResolved).toHaveBeenCalledWith("approve");
  });

  it("surfaces errors from the API", async () => {
    (mutateControlPlaneDashboardJson as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("network down"),
    );

    renderWithClient(
      <ApprovalPrompt
        agentId="bot-1"
        sessionId="sess-1"
        approvalId="op-1"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /deny/i }));

    await Promise.resolve();
    await Promise.resolve();
    expect(await screen.findByText(/network down/i)).toBeInTheDocument();
  });
});
