import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  extractRoomAgentMentionIds,
  roomAgentMentionLiteral,
  roomAgentMentionToken,
  RoomMentionRichText,
  splitRoomAgentMentions,
  type RoomAgentMentionMeta,
} from "@/components/sessions/chat/room-agent-mention";

vi.mock("@/components/ui/agent-glyph", () => ({
  AgentGlyph: ({ agentId }: { agentId: string }) => (
    <span data-testid={`agent-glyph-${agentId}`} />
  ),
}));

const sage: RoomAgentMentionMeta = {
  id: "DEMO_SAGE",
  label: "Sage",
  color: "#7c5cff",
};

function mentionMap() {
  return new Map<string, RoomAgentMentionMeta>([
    [sage.id.toLowerCase(), sage],
    [roomAgentMentionToken(sage).toLowerCase(), sage],
  ]);
}

describe("room agent mentions", () => {
  it("splits known agent mentions while leaving unknown tokens as text", () => {
    const segments = splitRoomAgentMentions(
      "Ask @DEMO_SAGE and @UNKNOWN_AGENT next.",
      mentionMap(),
    );

    expect(segments).toEqual([
      { kind: "text", text: "Ask " },
      { kind: "mention", mention: sage, raw: "@DEMO_SAGE" },
      { kind: "text", text: " and @UNKNOWN_AGENT next." },
    ]);
  });

  it("renders a minimal badge with the agent orb", () => {
    render(<RoomMentionRichText text="Ask @DEMO_SAGE" mentionsByToken={mentionMap()} />);

    expect(screen.getByText("@Sage")).toBeInTheDocument();
    expect(screen.getByText("@Sage").closest("[data-agent-mention]")).toHaveClass(
      "text-[var(--tone-info-dot)]",
    );
    expect(screen.getByTestId("agent-glyph-DEMO_SAGE")).toBeInTheDocument();
  });

  it("uses display-name tokens when they are safe for inline composer text", () => {
    expect(roomAgentMentionToken(sage)).toBe("Sage");
    expect(roomAgentMentionLiteral(sage)).toBe("@Sage");
  });

  it("extracts semantic mentions from id and display-name tokens without duplicates", () => {
    expect(
      extractRoomAgentMentionIds(
        "Ask @Sage then ask @DEMO_SAGE again.",
        mentionMap(),
      ),
    ).toEqual(["DEMO_SAGE"]);
  });

  it("renders inline mentions as blue raw text for textarea highlighting", () => {
    render(
      <RoomMentionRichText
        text="Ask @Sage"
        mentionsByToken={mentionMap()}
        variant="inline"
      />,
    );

    expect(screen.getByText("@Sage")).toHaveClass("text-[var(--tone-info-dot)]");
    expect(screen.queryByTestId("agent-glyph-DEMO_SAGE")).not.toBeInTheDocument();
  });
});
