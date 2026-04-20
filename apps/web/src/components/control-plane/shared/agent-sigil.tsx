"use client";

import { memo } from "react";
import { AgentGlyph } from "@/components/dashboard/agent-glyph";
import { cn } from "@/lib/utils";

export type AgentSigilSize = "xs" | "sm" | "md" | "lg" | "xl";
export type AgentSigilStatus =
  | "active"
  | "running"
  | "idle"
  | "paused"
  | "error"
  | "unknown";

interface AgentSigilProps {
  agentId: string;
  label?: string | null;
  color?: string | null;
  status?: AgentSigilStatus | string;
  size?: AgentSigilSize;
  className?: string;
}

const SIZE_CLASSES: Record<AgentSigilSize, string> = {
  xs: "h-6 w-6",
  sm: "h-8 w-8",
  md: "h-10 w-10",
  lg: "h-12 w-12",
  xl: "h-16 w-16",
};

function AgentSigilImpl({
  agentId,
  label,
  color,
  size = "md",
  className,
}: AgentSigilProps) {
  const sigilColor = color && color.trim().length > 0 ? color : "#A7ADB4";

  return (
    <span
      role="img"
      aria-label={label ?? agentId}
      className={cn("inline-flex shrink-0", SIZE_CLASSES[size], className)}
    >
      <AgentGlyph
        agentId={agentId}
        color={sigilColor}
        shape="swatch"
        className="h-full w-full"
      />
    </span>
  );
}

export const AgentSigil = memo(AgentSigilImpl);
