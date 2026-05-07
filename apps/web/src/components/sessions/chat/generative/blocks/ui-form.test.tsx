import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { UiForm, type UiFormBlock } from "@/components/sessions/chat/generative/blocks/ui-form";

vi.mock("@/lib/control-plane-dashboard", () => ({
  mutateControlPlaneDashboardJson: vi.fn(),
}));

import { mutateControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";

const baseBlock: UiFormBlock = {
  id: "form_1",
  version: 1,
  state: "complete",
  block_type: "ui_form",
  payload: {
    fields: [
      { kind: "text", id: "name", label: "Name", required: true, max: 64 },
      {
        kind: "select",
        id: "env",
        label: "Env",
        required: false,
        options: [
          { value: "dev", label: "Dev" },
          { value: "prod", label: "Prod" },
        ],
      },
    ],
    submit_label: "Submit",
  },
};

function renderForm(block: UiFormBlock = baseBlock) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLanguage="en-US">
        <UiForm block={block} agentId="ATLAS" sessionId="sess-1" />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("UiForm", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders fields and submit button", () => {
    renderForm();
    expect(screen.getByLabelText(/Name/i)).toBeInTheDocument();
    expect(screen.getByText(/Env/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Submit/i })).toBeInTheDocument();
  });

  it("blocks submit with a local error when required fields are empty", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole("button", { name: /Submit/i }));
    expect(await screen.findByText(/Name is required/i)).toBeInTheDocument();
    expect(mutateControlPlaneDashboardJson).not.toHaveBeenCalled();
  });

  it("submits the validated payload and disables resubmit", async () => {
    (mutateControlPlaneDashboardJson as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
    });
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/Name/i), "Ryan");
    await user.click(screen.getByRole("button", { name: /Submit/i }));

    await waitFor(() => {
      expect(mutateControlPlaneDashboardJson).toHaveBeenCalledWith(
        "/agents/ATLAS/sessions/sess-1/blocks/form_1/submit",
        expect.objectContaining({
          method: "POST",
          body: expect.objectContaining({
            block_type: "ui_form",
            values: expect.objectContaining({ name: "Ryan" }),
          }),
        }),
      );
    });

    // After success, the button shows ✓ and is disabled.
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /✓/ });
      expect(btn).toBeDisabled();
    });
  });

  it("ignores duplicate submit clicks while a request is in flight", async () => {
    let resolve: (v: unknown) => void = () => {};
    (mutateControlPlaneDashboardJson as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise((r) => { resolve = r; }),
    );
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/Name/i), "Ryan");
    await user.click(screen.getByRole("button", { name: /Submit/i }));
    await user.click(screen.getByRole("button", { name: /Submit/i }));

    // Only one outbound request despite two clicks.
    expect(mutateControlPlaneDashboardJson).toHaveBeenCalledTimes(1);
    resolve({ ok: true });
  });
});
