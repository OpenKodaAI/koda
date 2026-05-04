import { describe, expect, it } from "vitest";
import { MAX_AGENT_ORB_COLORS } from "@/components/ui/agent-glyph";
import { selectAgentGlyphPreviewAgents } from "@/components/ui/agent-glyph-group";

describe("selectAgentGlyphPreviewAgents", () => {
  it("caps dense selector palettes to the orb color limit", () => {
    const agents = Array.from({ length: MAX_AGENT_ORB_COLORS + 3 }, (_, i) => ({
      id: `agent-${i}`,
      color: `#00000${i}`,
    }));

    const previewAgents = selectAgentGlyphPreviewAgents(agents);

    expect(previewAgents).toHaveLength(MAX_AGENT_ORB_COLORS);
    expect(previewAgents.map((agent) => agent.id)).toEqual([
      "agent-0",
      "agent-1",
      "agent-2",
      "agent-3",
      "agent-4",
    ]);
  });

  it("keeps smaller selector palettes intact", () => {
    const agents = [
      { id: "planning", color: "#78A8FF" },
      { id: "ops", color: "#74D99F" },
    ];

    expect(selectAgentGlyphPreviewAgents(agents)).toEqual(agents);
  });
});
