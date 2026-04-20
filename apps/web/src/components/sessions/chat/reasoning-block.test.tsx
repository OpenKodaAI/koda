import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ReasoningBlock } from "@/components/sessions/chat/reasoning-block";

function renderBlock(props: Partial<React.ComponentProps<typeof ReasoningBlock>> = {}) {
  return render(
    <I18nProvider initialLanguage="en-US">
      <ReasoningBlock {...props}>
        <p data-testid="reasoning-body">Step one. Step two.</p>
      </ReasoningBlock>
    </I18nProvider>,
  );
}

describe("ReasoningBlock", () => {
  it("collapses the body by default", () => {
    renderBlock({ durationLabel: "3.2s" });

    const toggle = screen.getByRole("button", { expanded: false });
    expect(toggle).toHaveTextContent(/Thought for/i);
  });

  it("expands and collapses on click", async () => {
    const user = userEvent.setup();
    renderBlock({ durationLabel: "1.4s" });

    const toggle = screen.getByRole("button", { name: /Thought for/i });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("applies shimmer class while streaming", () => {
    renderBlock({ streaming: true });

    const toggle = screen.getByRole("button", { name: /Thinking/i });
    expect(toggle.querySelector(".chat-reasoning--streaming")).not.toBeNull();
  });
});
