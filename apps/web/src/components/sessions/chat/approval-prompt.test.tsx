import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
        body: {
          decision: "approve",
          edited_params: null,
          response_text: null,
          rationale: "trusted",
        },
      }),
    );
    expect(onResolved).toHaveBeenCalledWith("approve");
  });

  it("submits edited parameters and shows a diff", async () => {
    (mutateControlPlaneDashboardJson as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      approval: { approval_id: "op-1", decision: "edit" },
    });

    const onResolved = vi.fn();
    renderWithClient(
      <ApprovalPrompt
        agentId="bot-1"
        sessionId="sess-1"
        approvalId="op-1"
        toolName="write_file"
        schema={{
          type: "object",
          properties: {
            path: { type: "string" },
            force: { type: "boolean" },
          },
        }}
        originalParams={{ path: "/tmp/foo", force: false }}
        onResolved={onResolved}
      />,
    );

    expect(screen.getByLabelText(/edited parameters json/i)).toBeInTheDocument();
    expect(screen.getByText(/No parameter changes/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/edited parameters json/i), {
      target: {
        value: JSON.stringify({ path: "/tmp/foo", force: true }, null, 2),
      },
    });

    expect(screen.getByText((content) => /\-\s+"force": false/.test(content))).toBeInTheDocument();
    expect(screen.getByText((content) => /\+\s+"force": true/.test(content))).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/optional rationale/i), {
      target: { value: "limit to tmp" },
    });
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));

    await waitFor(() => {
      expect(mutateControlPlaneDashboardJson).toHaveBeenCalledWith(
        "/agents/bot-1/approvals/op-1",
        expect.objectContaining({
          method: "POST",
          body: {
            decision: "edit",
            edited_params: { path: "/tmp/foo", force: true },
            response_text: null,
            rationale: "limit to tmp",
          },
        }),
      );
    });
    expect(onResolved).toHaveBeenCalledWith("edit");
  });

  it("submits a synthetic response", async () => {
    (mutateControlPlaneDashboardJson as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      approval: { approval_id: "op-1", decision: "respond" },
    });

    renderWithClient(
      <ApprovalPrompt
        agentId="bot-1"
        sessionId="sess-1"
        approvalId="op-1"
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/response text for respond/i), {
      target: { value: "Use the cached value." },
    });
    fireEvent.click(screen.getByRole("button", { name: /respond/i }));

    await waitFor(() => {
      expect(mutateControlPlaneDashboardJson).toHaveBeenCalledWith(
        "/agents/bot-1/approvals/op-1",
        expect.objectContaining({
          method: "POST",
          body: {
            decision: "respond",
            edited_params: null,
            response_text: "Use the cached value.",
            rationale: null,
          },
        }),
      );
    });
  });

  it("blocks edited submission until JSON is valid", async () => {
    renderWithClient(
      <ApprovalPrompt
        agentId="bot-1"
        sessionId="sess-1"
        approvalId="op-1"
        originalParams={{ path: "/tmp/foo" }}
      />,
    );

    const editor = screen.getByLabelText(/edited parameters json/i);
    fireEvent.change(editor, { target: { value: "{" } });

    await waitFor(() => {
      expect(editor).toHaveAttribute("aria-invalid", "true");
    });

    fireEvent.click(screen.getByRole("button", { name: /edit/i }));

    expect(await screen.findByText(/Fix invalid JSON/i)).toBeInTheDocument();
    expect(mutateControlPlaneDashboardJson).not.toHaveBeenCalled();
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

    fireEvent.click(screen.getByRole("button", { name: /reject/i }));

    expect(await screen.findByText(/network down/i)).toBeInTheDocument();
    expect(screen.getByText(/Review the approval details/i)).toBeInTheDocument();
  });
});
