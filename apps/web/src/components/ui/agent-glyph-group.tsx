"use client";

import { AgentGlyph, type AgentState } from "@/components/ui/agent-glyph";

interface AgentLike {
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

// Renders the canonical agent orb, but when multiple agents are passed the
// shader splits its color ramp into one angular wedge per agent so every
// selected agent's color is visible in a single animated orb. Use this in
// any multi-select preview that needs to show "these N agents are picked".
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
  return (
    <AgentGlyph
      agentId={agents.map((a) => a.id).join(":")}
      color={first.color || FALLBACK_COLOR}
      colors={agents.map((a) => a.color || FALLBACK_COLOR)}
      state={state}
      active={active}
      className={className}
    />
  );
}
