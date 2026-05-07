"use client";

import {
  AgentGlyph,
  MAX_AGENT_ORB_COLORS,
  type AgentState,
} from "@/components/ui/agent-glyph";

export interface AgentLike {
  id: string;
  color: string;
}

interface AgentGlyphGroupProps {
  agents: AgentLike[];
  state?: AgentState;
  active?: boolean;
  className?: string;
}

const FALLBACK_COLOR = "#A7ADB4";

export function selectAgentGlyphPreviewAgents(
  agents: AgentLike[],
): AgentLike[] {
  return agents.slice(0, MAX_AGENT_ORB_COLORS);
}

// Renders the canonical agent orb. Multi-agent previews keep only the first
// few colors so dense selectors remain readable and inexpensive to mount.
export function AgentGlyphGroup({
  agents,
  state,
  active,
  className,
}: AgentGlyphGroupProps) {
  if (agents.length === 0) return null;
  const first = agents[0];
  if (agents.length === 1) {
    return (
      <AgentGlyph
        agentId={first.id}
        color={first.color || FALLBACK_COLOR}
        state={state}
        active={active}
        className={className}
      />
    );
  }
  const previewAgents = selectAgentGlyphPreviewAgents(agents);
  return (
    <AgentGlyph
      agentId={`${previewAgents.map((a) => a.id).join(":")}:${agents.length}`}
      color={first.color || FALLBACK_COLOR}
      colors={previewAgents.map((a) => a.color || FALLBACK_COLOR)}
      state={state}
      active={active}
      className={className}
    />
  );
}
