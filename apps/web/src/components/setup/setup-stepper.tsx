"use client";

import { cn } from "@/lib/utils";

interface SetupStepperProps {
  total: number;
  current: number; // 0-indexed
  className?: string;
}

export function SetupStepper({ total, current, className }: SetupStepperProps) {
  return (
    <div
      className={cn("flex items-center justify-center gap-2.5", className)}
      role="progressbar"
      aria-valuemin={1}
      aria-valuemax={total}
      aria-valuenow={Math.min(Math.max(current + 1, 1), total)}
      aria-label="Setup progress"
    >
      {Array.from({ length: total }).map((_, index) => {
        const state =
          index < current ? "past" : index === current ? "active" : "future";
        return (
          <span
            key={index}
            className={cn(
              "inline-block h-1.5 rounded-full transition-[width,background-color] duration-[220ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
              state === "active" && "w-6 bg-[var(--accent)]",
              state === "past" && "w-1.5 bg-[var(--text-primary)]",
              state === "future" && "w-1.5 bg-[var(--panel-strong)]",
            )}
            aria-hidden="true"
          />
        );
      })}
    </div>
  );
}
