import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { BlockRenderer } from "@/components/sessions/chat/generative/block-renderer";

function renderBlock(raw: unknown, onAction?: (id: string, action: string) => void) {
  return render(
    <I18nProvider initialLanguage="en-US">
      <BlockRenderer raw={raw} onAction={onAction} />
    </I18nProvider>,
  );
}

describe("BlockRenderer", () => {
  it("renders a ui_card block with title and body", () => {
    renderBlock({
      id: "c1",
      version: 1,
      block_type: "ui_card",
      payload: { title: "Hello", body: "World" },
    });
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("World")).toBeInTheDocument();
  });

  it("fires onAction for ui_card footer button clicks", async () => {
    const onAction = vi.fn();
    renderBlock(
      {
        id: "c1",
        version: 1,
        block_type: "ui_card",
        payload: {
          title: "Decision",
          footer_actions: [
            {
              id: "approve",
              label: "Approve",
              tone: "accent",
              action: { kind: "submit" },
            },
          ],
        },
      },
      onAction,
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Approve/i }));
    expect(onAction).toHaveBeenCalledWith("c1", "approve");
  });

  it("renders a ui_callout with tone and body", () => {
    renderBlock({
      id: "cal1",
      version: 1,
      block_type: "ui_callout",
      payload: {
        tone: "warning",
        title: "Heads up",
        body: "Rate limit approaching.",
      },
    });
    expect(screen.getByText("Heads up")).toBeInTheDocument();
    expect(screen.getByText(/Rate limit approaching/i)).toBeInTheDocument();
  });

  it("renders a ui_steps list with each item label", () => {
    renderBlock({
      id: "s1",
      version: 1,
      block_type: "ui_steps",
      payload: {
        items: [
          { id: "1", label: "Plan", status: "done" },
          { id: "2", label: "Apply", status: "running" },
          { id: "3", label: "Verify", status: "pending" },
        ],
      },
    });
    expect(screen.getByText("Plan")).toBeInTheDocument();
    expect(screen.getByText("Apply")).toBeInTheDocument();
    expect(screen.getByText("Verify")).toBeInTheDocument();
  });

  it("renders a Skeleton when state is 'streaming'", () => {
    renderBlock({
      id: "x",
      version: 1,
      block_type: "ui_card",
      state: "streaming",
      payload: {},
    });
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("Hello")).toBeNull();
  });

  it("renders UnsupportedBlock when block_type is unknown", () => {
    renderBlock({
      id: "x",
      version: 1,
      block_type: "ui_unknown",
      payload: {},
    });
    expect(screen.getByText(/Unsupported block/i)).toBeInTheDocument();
  });

  it("renders UnsupportedBlock when payload fails schema validation", () => {
    renderBlock({
      id: "x",
      version: 1,
      block_type: "ui_card",
      // missing required `title`
      payload: { body: "no title" },
    });
    expect(screen.getByText(/Unsupported block/i)).toBeInTheDocument();
  });
});
