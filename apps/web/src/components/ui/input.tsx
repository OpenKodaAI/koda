"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  sizeVariant?: "sm" | "md" | "lg";
  invalid?: boolean;
}

const sizeClasses: Record<NonNullable<InputProps["sizeVariant"]>, string> = {
  sm: "h-8 px-2.5 text-[0.75rem]",
  md: "h-9 px-3 text-[0.8125rem]",
  lg: "h-11 px-4 text-[0.875rem]",
};

export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, sizeVariant = "md", invalid, disabled, type = "text", ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      type={type}
      disabled={disabled}
      aria-invalid={invalid || undefined}
      className={cn(
        "w-full rounded-[var(--radius-input)] border bg-[var(--panel-soft)] text-[var(--text-primary)] outline-none",
        "placeholder:text-[var(--text-quaternary)]",
        "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "border-[var(--border-subtle)] hover:border-[var(--border-strong)]",
        "focus-visible:border-[var(--accent)]",
        invalid && "border-[var(--tone-danger-border)] focus-visible:border-[var(--tone-danger-border)]",
        disabled && "cursor-not-allowed opacity-60",
        sizeClasses[sizeVariant],
        className,
      )}
      {...props}
    />
  );
});
