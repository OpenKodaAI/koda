"use client";

import { memo } from "react";
import {
  AgentGlyph,
  type AgentState,
} from "@/components/ui/agent-glyph";
import { cn } from "@/lib/utils";

export type AgentSigilSize = "xs" | "sm" | "md" | "lg" | "xl";
export type AgentSigilStatus =
  | "active"
  | "running"
  | "retrying"
  | "queued"
  | "idle"
  | "paused"
  | "error"
  | "unknown";

interface AgentSigilProps {
  agentId: string;
  label?: string | null;
  color?: string | null;
  status?: AgentSigilStatus | string;
  state?: AgentState;
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

/**
 * Map a status string to the orb's foreground animation.
 *
 * The orb has four animation buckets:
 *   - ``null``      → idle (gentle ambient motion only)
 *   - ``thinking``  → task is actively executing
 *   - ``listening`` → task is queued, waiting for a worker
 *   - ``talking``   → agent is emitting streamed output (TTS / live response)
 *
 * Only realtime *execution* states drive the animation. The control-plane
 * definition status (``"active"`` = agent is enabled, ``"paused"`` = agent
 * is disabled, etc.) describes whether the agent is wired up — it does NOT
 * describe whether work is in flight, so it must NOT trigger the active
 * animations. An "active but idle" agent stays idle on the orb.
 *
 * Callers that DO have realtime activity context (the home / executions /
 * runtime screens) can bypass this fallback by passing ``state`` directly,
 * e.g. via ``deriveAgentState({activeTasks, featuredStatus})``.
 */
function statusToState(status: AgentSigilProps["status"]): AgentState {
  switch (status) {
    case "running":
    case "retrying":
      return "thinking";
    case "queued":
      return "listening";
    default:
      // Includes "active", "paused", "idle", "error", "unknown",
      // "completed", "failed", "cancelled", and any other definition
      // status the catalog might invent. None of these are realtime
      // execution signals, so the orb stays idle.
      return null;
  }
}

function AgentSigilImpl({
  agentId,
  label,
  color,
  status,
  state,
  size = "md",
  className,
}: AgentSigilProps) {
  const sigilColor = color && color.trim().length > 0 ? color : "#A7ADB4";
  const resolvedState = state ?? statusToState(status);

  return (
    <span
      role="img"
      aria-label={label ?? agentId}
      className={cn("inline-flex shrink-0", SIZE_CLASSES[size], className)}
    >
      <AgentGlyph
        agentId={agentId}
        color={sigilColor}
        state={resolvedState}
        className="h-full w-full"
      />
    </span>
  );
}

export const AgentSigil = memo(AgentSigilImpl);
export { statusToState as __statusToState_for_test };
