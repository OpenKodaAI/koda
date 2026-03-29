"use client";

import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { cn } from "@/lib/utils";

interface BotOrbPreviewProps {
  botId: string;
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

export function BotOrbPreview({
  botId,
  color,
  size = "md",
  active = false,
  className,
}: BotOrbPreviewProps) {
  return (
    <BotAgentGlyph
      botId={botId}
      color={color}
      active={active}
      className={cn(SIZE_CLASS_MAP[size], className)}
    />
  );
}
