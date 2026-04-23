"use client";

import { AgentGlyph } from "@/components/dashboard/agent-glyph";
import { cn } from "@/lib/utils";

interface AgentOrbPreviewProps {
  agentId: string;
  color: string;
  size?: "sm" | "md" | "lg";
  active?: boolean;
  className?: string;
}

const SIZE_CLASS_MAP: Record<"sm" | "md" | "lg", string> = {
  sm: "h-8 w-8",
  md: "h-12 w-12",
  lg: "h-18 w-18",
};

export function AgentOrbPreview({
  agentId,
  color,
  size = "md",
  active = false,
  className,
}: AgentOrbPreviewProps) {
  return (
    <AgentGlyph
      agentId={agentId}
      color={color}
      active={active}
      className={cn(SIZE_CLASS_MAP[size], className)}
    />
  );
}
