"use client";

import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";

interface BotAgentGlyphProps {
  botId: string;
  color: string;
  className?: string;
  active?: boolean;
  variant?: "card" | "list";
  shape?: "orb" | "swatch";
}

export function getBotOrbColor(color: string): string {
  return color || "#A7ADB4";
}

export function BotAgentGlyph({
  botId,
  color,
  className,
  active = false,
  variant = "card",
  shape = "orb",
}: BotAgentGlyphProps) {
  void botId;
  const orbColor = getBotOrbColor(color);
  const isListVariant = variant === "list";
  const isSwatch = shape === "swatch";
  const glyphClass = isSwatch ? "bot-swatch" : "bot-orb";

  const style = {
    "--bot-orb-color": orbColor,
  } as CSSProperties;

  return (
    <span
      className={cn(
        glyphClass,
        isListVariant ? "h-8 w-8" : "h-12 w-12",
        active && (isSwatch ? "bot-swatch--active" : "bot-orb--active"),
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
