import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RoomAgentMentionMeta } from "@/components/sessions/chat/room-agent-mention";
import { SessionRichText } from "@/components/sessions/session-rich-text";

/**
 * A chat thread re-renders every message whenever anything above it changes (a page of older
 * messages arriving, a stream chunk, a scroll-state update). The rendered markdown must survive
 * that: if its element types changed on every render, React would replace each paragraph, list
 * item, heading, table cell and link, losing any text selection and churning the DOM of the whole
 * thread (and any test holding a found node, as the sessions page test did).
 */
describe("SessionRichText", () => {
  const content = "First paragraph with a [link](https://example.com).\n\n- an item\n\n## A heading";

  function nodes() {
    return {
      paragraph: screen.getByText(/First paragraph/, { selector: "p" }),
      link: screen.getByRole("link", { name: "link" }),
      item: screen.getByText("an item"),
      heading: screen.getByRole("heading", { name: "A heading" }),
    };
  }

  it("keeps its markdown elements when it re-renders with the same content", () => {
    const { rerender } = render(<SessionRichText content={content} variant="user" />);
    const before = nodes();

    rerender(<SessionRichText content={content} variant="user" />);

    const after = nodes();
    for (const name of Object.keys(before) as Array<keyof typeof before>) {
      expect(after[name], name).toBe(before[name]);
      expect(before[name].isConnected, name).toBe(true);
    }
  });

  it("keeps its markdown elements when the mention lookup is rebuilt", () => {
    const mention: RoomAgentMentionMeta = { id: "ATLAS", label: "Atlas", color: null };
    const lookup = () => new Map<string, RoomAgentMentionMeta>([["atlas", mention]]);
    const withMention = `Ask @atlas first. ${content}`;
    const { rerender } = render(<SessionRichText content={withMention} mentionsByToken={lookup()} mentionVariant="inline" />);
    const before = nodes();
    const mentionNode = screen.getByText("@atlas");

    // A caller may build the lookup in render, so each render can pass a new Map.
    rerender(<SessionRichText content={withMention} mentionsByToken={lookup()} mentionVariant="inline" />);

    const after = nodes();
    for (const name of Object.keys(before) as Array<keyof typeof before>) {
      expect(after[name], name).toBe(before[name]);
    }
    expect(screen.getByText("@atlas")).toBe(mentionNode);
  });
});
