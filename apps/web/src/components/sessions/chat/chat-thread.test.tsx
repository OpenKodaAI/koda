import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/components/providers/i18n-provider";
import { ChatThread, type PendingChatMessage } from "@/components/sessions/chat/chat-thread";
import type { ExecutionArtifact, SessionMessage } from "@/lib/types";

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

function assistantMessage(overrides: Partial<SessionMessage> = {}): SessionMessage {
  return {
    id: overrides.id ?? "msg-assistant",
    role: "assistant",
    text: "Here is the voice note.",
    timestamp: "2026-03-28T10:01:00.000Z",
    model: "gpt-5.4-mini",
    cost_usd: 0.01,
    query_id: 2,
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

  it("loads older messages when the viewport is near the top", async () => {
    const onLoadOlder = vi.fn().mockResolvedValue(undefined);
    render(
      <I18nProvider initialLanguage="en-US">
        <ChatThread
          messages={[userMessage(), assistantMessage()]}
          hasOlder
          onLoadOlder={onLoadOlder}
        />
      </I18nProvider>,
    );

    const log = screen.getByRole("log");
    Object.defineProperties(log, {
      scrollHeight: { configurable: true, value: 1600 },
      clientHeight: { configurable: true, value: 520 },
      scrollTop: { configurable: true, value: 260, writable: true },
    });
    fireEvent.scroll(log);

    await waitFor(() => expect(onLoadOlder).toHaveBeenCalledTimes(1));
  });

  it("keeps the new-message affordance compact above the composer", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <ChatThread
          messages={[
            userMessage({ id: "msg-user-1", timestamp: "2026-03-28T10:00:00.000Z" }),
            assistantMessage({ id: "msg-assistant-1", timestamp: "2026-03-28T10:01:00.000Z" }),
          ]}
          footer={<div className="h-24">Composer</div>}
        />
      </I18nProvider>,
    );

    const log = screen.getByRole("log");
    Object.defineProperties(log, {
      scrollHeight: { configurable: true, value: 1200 },
      clientHeight: { configurable: true, value: 420 },
      scrollTop: { configurable: true, value: 120, writable: true },
    });
    fireEvent.scroll(log);

    const button = screen.getByRole("button", { name: /New messages/i });
    expect(button).toHaveClass("!w-9");
    expect(button).toHaveClass("!min-w-9");
    expect(button).toHaveClass("!max-w-9");
    expect(button).not.toHaveClass("w-full");
    expect(button).toHaveStyle({ width: "36px", minWidth: "36px", maxWidth: "36px" });
    expect(button.parentElement).toHaveClass("left-1/2");
    expect(button.parentElement).toHaveClass("-translate-x-1/2");
  });

  it("renders assistant audio artifacts as playable voice notes", async () => {
    const user = userEvent.setup();
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);

    render(
      <I18nProvider initialLanguage="en-US">
        <ChatThread
          agentId="ATLAS"
          messages={[
            assistantMessage({
              artifacts: [
                {
                  id: "artifact-77",
                  label: "voice-response-77.ogg",
                  kind: "audio",
                  content: null,
                  url: null,
                  path: "/runtime/tasks/77/artifacts/voice-response-77.ogg",
                  mime_type: "audio/ogg",
                  size_bytes: 2048,
                  source_type: "voice_response",
                  status: "complete",
                  text_content: null,
                  metadata: { runtime_artifact_id: "77" },
                },
              ],
            }),
          ]}
        />
      </I18nProvider>,
    );

    const audio = document.querySelector("audio");
    expect(audio?.getAttribute("src")).toBe("/api/runtime/artifacts/77/download?agent=ATLAS");
    const playButton = screen.getByRole("button", { name: /Play audio/i });
    expect(playButton.parentElement).toHaveClass("max-w-[320px]");
    expect(playButton.parentElement).toHaveClass("bg-[var(--panel-soft)]");
    expect(playButton.parentElement).not.toHaveClass("bg-[#302d46]");

    await user.click(playButton);
    expect(play).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /Pause audio/i }));
    expect(pause).toHaveBeenCalled();
    play.mockRestore();
    pause.mockRestore();
  });

  it("opens image artifacts in the chat preview instead of downloading on click", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider initialLanguage="en-US">
        <ChatThread
          agentId="ATLAS"
          messages={[
            assistantMessage({
              text: "",
              artifacts: [
                {
                  id: "artifact-88",
                  label: "generated scene.png",
                  kind: "image",
                  content: null,
                  url: "generated-scene.png",
                  path: "/runtime/tasks/88/artifacts/generated-scene.png",
                  mime_type: "image/png",
                  size_bytes: 4096,
                  source_type: "provider_output",
                  status: "complete",
                  text_content: null,
                  metadata: { runtime_artifact_id: "88" },
                },
                {
                  id: "artifact-89",
                  label: "second scene.png",
                  kind: "image",
                  content: null,
                  url: null,
                  path: "/runtime/tasks/89/artifacts/second-scene.png",
                  mime_type: "image/png",
                  size_bytes: 2048,
                  source_type: "provider_output",
                  status: "complete",
                  text_content: null,
                  metadata: { runtime_artifact_id: "89" },
                },
              ],
            }),
          ]}
        />
      </I18nProvider>,
    );

    expect(screen.queryByText("Here is the voice note.")).not.toBeInTheDocument();
    const firstPreviewButton = screen.getAllByRole("button", { name: /Open preview/i })[0];
    expect(
      within(firstPreviewButton).getByRole("status", {
        name: /Loading image preview/i,
      }),
    ).toBeInTheDocument();
    const preview = within(firstPreviewButton).getByRole("img", { name: /generated scene/i });
    const imageCard = preview.closest("[data-inline-image-artifact]");
    expect(preview).toHaveAttribute("src", "/api/runtime/artifacts/88/download?agent=ATLAS");
    expect(preview).toHaveClass("opacity-0");
    expect(imageCard).toHaveClass("w-full");
    Object.defineProperty(preview, "naturalWidth", {
      configurable: true,
      value: 1536,
    });
    Object.defineProperty(preview, "naturalHeight", {
      configurable: true,
      value: 1024,
    });
    fireEvent.load(preview);
    await waitFor(() =>
      expect(
        within(firstPreviewButton).queryByRole("status", {
          name: /Loading image preview/i,
        }),
      ).not.toBeInTheDocument(),
    );
    expect(imageCard).not.toHaveClass("w-full");
    expect(imageCard).toHaveClass("w-fit");
    expect(imageCard).toHaveClass("bg-transparent");
    expect(preview).toHaveClass("w-full", "h-full", "object-cover");
    expect(
      document.querySelector('a[href="/api/runtime/artifacts/88/download?agent=ATLAS"]'),
    ).toBeNull();
    const inlineDownload = screen.getAllByRole("button", { name: /^Download$/i })[0];
    expect(inlineDownload).toHaveClass("right-2", "top-2", "rounded-[var(--radius-chip)]");
    expect(inlineDownload).not.toHaveClass("rounded-full");

    await user.click(firstPreviewButton);

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: /generated-scene.png/i })).toBeInTheDocument();
    expect(within(dialog).getByRole("img", { name: /generated scene/i })).toHaveAttribute(
      "src",
      "/api/runtime/artifacts/88/download?agent=ATLAS",
    );
    const dialogDownload = within(dialog).getByRole("button", { name: /^Download$/i });
    expect(dialogDownload).toHaveClass("rounded-[var(--radius-chip)]");
    expect(dialogDownload).not.toHaveClass("rounded-full");
    expect(dialogDownload).not.toHaveClass("border-white/10");
    const previousButton = within(dialog).getByRole("button", { name: /Previous artifact/i });
    const nextButton = within(dialog).getByRole("button", { name: /Next artifact/i });
    expect(previousButton).toHaveStyle({
      position: "fixed",
      top: "50%",
      left: "16px",
      transform: "translateY(-50%)",
    });
    expect(nextButton).toHaveStyle({
      position: "fixed",
      top: "50%",
      right: "16px",
      transform: "translateY(-50%)",
    });
    expect(previousButton).toHaveClass("rounded-[var(--radius-chip)]");
    expect(nextButton).toHaveClass("rounded-[var(--radius-chip)]");
    expect(previousButton).not.toHaveClass("border-white/10");
    expect(nextButton).not.toHaveClass("border-white/10");

    await user.click(nextButton);
    expect(within(dialog).getByRole("heading", { name: /second-scene.png/i })).toBeInTheDocument();
    expect(within(dialog).getByText("2 / 2")).toBeInTheDocument();
  });

  it("shows a friendly fallback when an image artifact cannot load", async () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <ChatThread
          agentId="ATLAS"
          messages={[
            assistantMessage({
              text: "",
              artifacts: [
                {
                  id: "artifact-missing",
                  label: "missing render.png",
                  kind: "image",
                  content: null,
                  url: null,
                  path: "/runtime/tasks/90/artifacts/missing-render.png",
                  mime_type: "image/png",
                  size_bytes: 4096,
                  source_type: "provider_output",
                  status: "complete",
                  text_content: null,
                  metadata: { runtime_artifact_id: "90" },
                },
              ],
            }),
          ]}
        />
      </I18nProvider>,
    );

    fireEvent.error(screen.getByRole("img", { name: /missing render/i }));

    expect(await screen.findByText("Image preview unavailable")).toBeInTheDocument();
    expect(screen.getByText("missing-render.png")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Download$/i })).toBeInTheDocument();
  });

  it("renders adapted inline cards for every non-image artifact kind", () => {
    const makeArtifact = (
      kind: ExecutionArtifact["kind"],
      id: number,
      overrides: Partial<ExecutionArtifact> = {},
    ): ExecutionArtifact => ({
      id: `artifact-${id}`,
      label: `${kind}-artifact`,
      kind,
      content: null,
      url: null,
      path: `/runtime/tasks/${id}/artifacts/${kind}-artifact`,
      mime_type: "application/octet-stream",
      size_bytes: 2048,
      source_type: "provider_output",
      status: "complete",
      text_content: null,
      metadata: { runtime_artifact_id: String(id) },
      ...overrides,
    });

    const artifacts: ExecutionArtifact[] = [
      makeArtifact("video", 301, { mime_type: "video/mp4" }),
      makeArtifact("url", 302, {
        url: "https://example.com/report",
        path: null,
        label: "Example report",
        description: "External source",
        domain: "example.com",
        metadata: {},
      }),
      makeArtifact("code", 303, {
        label: "agent.ts",
        content: "export function run() { return 42; }",
        mime_type: "text/typescript",
      }),
      makeArtifact("text", 304, {
        label: "notes.txt",
        text_content: "Short generated note",
        mime_type: "text/plain",
      }),
      makeArtifact("html", 305, {
        label: "page.html",
        content: "<main>Hello</main>",
        mime_type: "text/html",
      }),
      makeArtifact("json", 306, {
        label: "data.json",
        content: { ok: true },
        mime_type: "application/json",
      }),
      makeArtifact("yaml", 307, {
        label: "config.yaml",
        content: "ok: true",
        mime_type: "application/yaml",
      }),
      makeArtifact("xml", 308, {
        label: "feed.xml",
        content: "<feed />",
        mime_type: "application/xml",
      }),
      makeArtifact("csv", 309, {
        label: "data.csv",
        content: "name,score\nKoda,100",
        mime_type: "text/csv",
      }),
      makeArtifact("tsv", 310, {
        label: "data.tsv",
        content: "name\tscore\nKoda\t100",
        mime_type: "text/tab-separated-values",
      }),
      makeArtifact("pdf", 311, { label: "brief.pdf", mime_type: "application/pdf" }),
      makeArtifact("docx", 312, {
        label: "brief.docx",
        mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      }),
      makeArtifact("spreadsheet", 313, {
        label: "sheet.xlsx",
        mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
      makeArtifact("file", 314, {
        label: "archive.bin",
        path: "/runtime/tasks/314/artifacts/archive.bin",
      }),
    ];

    render(
      <I18nProvider initialLanguage="en-US">
        <ChatThread
          agentId="ATLAS"
          messages={[assistantMessage({ text: "", artifacts })]}
        />
      </I18nProvider>,
    );

    for (const artifact of artifacts) {
      expect(
        document.querySelector(`[data-artifact-kind="${artifact.kind}"]`),
      ).toBeInTheDocument();
    }
    expect(document.querySelector('[data-artifact-visual="video"] video')).toHaveAttribute(
      "src",
      "/api/runtime/artifacts/301/download?agent=ATLAS",
    );
    expect(document.querySelector('[data-artifact-visual="video"]')).toHaveClass("w-fit");
    expect(document.querySelector('[data-artifact-visual="link"]')).toHaveTextContent(
      /Example report/i,
    );
    expect(document.querySelector('[data-artifact-visual="text"]')).toHaveTextContent(
      /return 42/i,
    );
    expect(document.querySelector('[data-artifact-visual="data"]')).toHaveTextContent(
      /ok/i,
    );
    expect(document.querySelectorAll('[data-artifact-visual="document"]')).toHaveLength(3);
    expect(document.querySelector('[data-artifact-visual="file"]')).toHaveTextContent(
      /archive.bin/i,
    );
  });
});
