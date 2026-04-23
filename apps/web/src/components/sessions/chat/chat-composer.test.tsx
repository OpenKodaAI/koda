import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { AgentCatalogProvider } from "@/components/providers/agent-catalog-provider";
import { ChatComposer } from "@/components/sessions/chat/chat-composer";

const agentCatalog = [
  {
    id: "ATLAS",
    label: "ATLAS",
    color: "#ff5a5a",
    colorRgb: "255, 90, 90",
    initials: "MA",
    status: "active" as const,
    model: "Claude Opus 4.6",
  },
];

function renderComposer(props: Partial<React.ComponentProps<typeof ChatComposer>> = {}) {
  const onChange = props.onChange ?? vi.fn();
  const onSubmit = props.onSubmit ?? vi.fn();
  return {
    onChange,
    onSubmit,
    ...render(
      <I18nProvider initialLanguage="en-US">
        <AgentCatalogProvider initialAgents={agentCatalog}>
          <ChatComposer
            value=""
            onChange={onChange}
            onSubmit={onSubmit}
            agentId="ATLAS"
            {...props}
          />
        </AgentCatalogProvider>
      </I18nProvider>,
    ),
  };
}

describe("ChatComposer", () => {
  it("disables submit when textarea is empty", () => {
    renderComposer();
    const submit = screen.getByRole("button", { name: /^Send$/i });
    expect(submit).toBeDisabled();
  });

  it("submits on Cmd+Enter and leaves Enter for newlines", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    renderComposer({ value: "Hello world", onSubmit });

    const textarea = screen.getByPlaceholderText(/Send a message/i);
    await user.click(textarea);

    await user.keyboard("{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();

    await user.keyboard("{Meta>}{Enter}{/Meta}");
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("clamps textarea height at the configured maximum", () => {
    const tallText = Array.from({ length: 40 }, () => "Lorem ipsum dolor sit amet.").join("\n");
    renderComposer({ value: tallText });

    const textarea = screen.getByPlaceholderText(/Send a message/i) as HTMLTextAreaElement;
    expect(textarea.style.maxHeight).toBe("");
    const computedMaxClass = textarea.className.includes("max-h-[160px]");
    expect(computedMaxClass).toBe(true);
  });

  it("calls onAgentChange when selecting a different agent via the popover", async () => {
    const onAgentChange = vi.fn();
    const user = userEvent.setup();
    renderComposer({
      agentId: "ATLAS",
      onAgentChange,
    });

    await user.click(screen.getByRole("button", { name: "ATLAS" }));
    const optionButton = await screen.findByRole("option", { name: /ATLAS/i });
    await user.click(optionButton);

    expect(onAgentChange).toHaveBeenCalledWith("ATLAS");
  });
});
