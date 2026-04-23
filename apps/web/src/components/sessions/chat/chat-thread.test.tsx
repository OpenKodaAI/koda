import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ChatThread, type PendingChatMessage } from "@/components/sessions/chat/chat-thread";
import type { SessionMessage } from "@/lib/types";

function userMessage(overrides: Partial<SessionMessage> = {}): SessionMessage {
  return {
    id: overrides.id ?? "msg-user",
    role: "user",
    text: "Hello there",
    timestamp: "2026-03-28T10:00:00.000Z",
    model: null,
    cost_usd: null,
    query_id: 1,
    session_id: "session-1",
    error: false,
    ...overrides,
  };
}

describe("ChatThread", () => {
  it("renders empty state when there are no messages", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <ChatThread messages={[]} />
      </I18nProvider>,
    );
    expect(screen.getByText(/What could we build today/i)).toBeInTheDocument();
  });

  it("renders a thinking indicator while the assistant is running", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <ChatThread messages={[userMessage()]} showThinking />
      </I18nProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/Thinking/i);
  });

  it("invokes onRetryPending when the retry affordance is clicked", async () => {
    const onRetryPending = vi.fn();
    const user = userEvent.setup();
    const pending: PendingChatMessage = {
      ...userMessage({ id: "msg-failed" }),
      requestId: "req-1",
      clientState: "failed",
      retryText: "Hello there",
    };

    render(
      <I18nProvider initialLanguage="en-US">
        <ChatThread messages={[]} pendingMessages={[pending]} onRetryPending={onRetryPending} />
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: /Retry/i }));
    expect(onRetryPending).toHaveBeenCalledWith("req-1");
  });

  it("exposes the thread viewport as a live log region", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <ChatThread messages={[userMessage()]} />
      </I18nProvider>,
    );
    const log = screen.getByRole("log");
    expect(log).toHaveAttribute("aria-live", "polite");
  });
});
