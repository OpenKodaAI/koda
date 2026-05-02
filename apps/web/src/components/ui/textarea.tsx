"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Textarea — multi-line input matching the Input/Select visual contract.
 *
 * Use this everywhere instead of raw `<textarea>` so the entire app shares
 * one set of borders, focus rings, and color tokens. ``rows`` controls the
 * initial visible height; users can still resize with the corner handle.
 */

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, invalid, disabled, rows = 4, ...props },
  ref,
) {
  return (
    <textarea
      ref={ref}
      rows={rows}
      disabled={disabled}
      aria-invalid={invalid || undefined}
      className={cn(
        "w-full rounded-[var(--radius-input)] border bg-[var(--panel-soft)] px-3 py-2 text-[0.8125rem] text-[var(--text-primary)] outline-none",
        "placeholder:text-[var(--text-quaternary)]",
        "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "border-[var(--border-subtle)] hover:border-[var(--border-strong)]",
        "focus-visible:border-[var(--accent)]",
        "resize-y leading-[1.5]",
        invalid && "border-[var(--tone-danger-border)] focus-visible:border-[var(--tone-danger-border)]",
        disabled && "cursor-not-allowed opacity-60",
        className,
      )}
      {...props}
    />
  );
});
