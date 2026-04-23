"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type MovingBorderProps = {
  children: React.ReactNode;
  className?: string;
  outerClassName?: string;
  borderWidth?: number;
  gradientWidth?: number;
  radius?: number;
  duration?: number;
  colors?: string[];
  isCircle?: boolean;
};

/**
 * Traveling-gradient border built with pure CSS — a bright dot orbits the
 * perimeter, leaving a smooth moving highlight that respects the outer shape.
 * This version uses CSS keyframes only so it works consistently in
 * React Compiler / Turbopack environments where GSAP's ticker can be
 * paused unexpectedly.
 */
export function MovingBorder({
  children,
  className,
  outerClassName,
  borderWidth = 1,
  radius = 15,
  gradientWidth,
  duration = 3,
  colors = ["#355bd2"],
  isCircle = false,
}: MovingBorderProps) {
  const effectiveRadius = isCircle ? 9999 : radius;
  const resolvedGradientWidth = gradientWidth ?? borderWidth * 10;

  // Pick one color for the dot — for now we keep it simple and use the first.
  // The aurora inside the sigil already animates color, so cycling the border
  // color on top can feel noisy.
  const dotColor = colors[0] ?? "#355bd2";

  return (
    <div
      className={cn(
        "moving-border-outer relative overflow-hidden",
        outerClassName,
      )}
      style={
        {
          padding: `${borderWidth}px`,
          borderRadius: `${effectiveRadius + borderWidth}px`,
          "--moving-border-duration": `${duration}s`,
          "--moving-border-color": dotColor,
          "--moving-border-dot-size": `${resolvedGradientWidth}px`,
        } as React.CSSProperties
      }
    >
      <span aria-hidden className="moving-border-spinner">
        <span className="moving-border-dot" />
      </span>

      <div
        className={cn("relative z-30", className)}
        style={{ borderRadius: `${effectiveRadius}px` }}
      >
        {children}
      </div>
    </div>
  );
}
