"use client";

import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";

interface AgentAgentGlyphProps {
  agentId: string;
  color: string;
  className?: string;
  active?: boolean;
  variant?: "card" | "list";
  shape?: "orb" | "swatch";
}

export function getAgentOrbColor(color: string): string {
  return color || "#A7ADB4";
}

export function AgentGlyph({
  agentId,
  color,
  className,
  active = false,
  variant = "card",
  shape = "orb",
}: AgentAgentGlyphProps) {
  void agentId;
  const orbColor = getAgentOrbColor(color);
  const isListVariant = variant === "list";
  const isSwatch = shape === "swatch";
  const glyphClass = isSwatch ? "agent-swatch" : "agent-orb";

  const style = {
    "--agent-orb-color": orbColor,
  } as CSSProperties;

  return (
    <span
      className={cn(
        glyphClass,
        isListVariant ? "h-8 w-8" : "h-12 w-12",
        active && (isSwatch ? "agent-swatch--active" : "agent-orb--active"),
        className
      )}
      style={style}
      aria-hidden="true"
    >
      <span className={`${glyphClass}__halo`} />
      <span className={`${glyphClass}__base`} />
      <span className={`${glyphClass}__swirl`} />
      <span className={`${glyphClass}__shine`} />
      <span className={`${glyphClass}__grain`} />
    </span>
  );
}
