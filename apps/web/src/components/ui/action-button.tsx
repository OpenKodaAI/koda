"use client";

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { LoaderCircle } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

type ActionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children?: ReactNode;
  leading?: ReactNode;
  trailing?: ReactNode;
  loading?: boolean;
  size?: "sm" | "md" | "icon";
  variant?: "action" | "primary" | "secondary" | "quiet" | "danger";
  status?: "idle" | "pending" | "success" | "error";
};

export const ActionButton = forwardRef<HTMLButtonElement, ActionButtonProps>(
  (
    {
      children,
      leading,
      trailing,
      loading = false,
      size = "md",
      variant = "action",
      status = "idle",
      className,
      disabled,
      ...props
    },
    ref,
  ) => {
    const { tl } = useAppI18n();
    const resolvedChildren = typeof children === "string" ? tl(children) : children;

    return (
      <button
        {...props}
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          variant === "action"
            ? "action-button"
            : "button-shell",
          variant === "primary" && "button-shell--primary",
          variant === "secondary" && "button-shell--secondary",
          variant === "quiet" && "button-shell--quiet",
          variant === "danger" && "button-shell--danger",
          size === "sm" && (variant === "action" ? "action-button--sm" : "button-shell--sm"),
          size === "icon" && (variant === "action" ? "action-button--icon" : "button-shell--icon"),
          loading && "action-button--loading",
          className,
        )}
        aria-busy={loading || undefined}
        data-loading={loading ? "true" : undefined}
        data-status={status !== "idle" ? status : undefined}
        aria-label={typeof props["aria-label"] === "string" ? tl(props["aria-label"]) : props["aria-label"]}
        title={typeof props.title === "string" ? tl(props.title) : props.title}
      >
        {loading ? (
          <LoaderCircle
            className={cn(
              "h-4 w-4 animate-spin",
              variant === "action" && "action-button__spinner",
            )}
            aria-hidden="true"
          />
        ) : (
          leading
        )}
        {resolvedChildren !== null && resolvedChildren !== undefined ? (
          <span
            className={cn(
              "inline-flex items-center",
              variant === "action" && "action-button__label",
            )}
          >
            {resolvedChildren}
          </span>
        ) : null}
        {!loading ? trailing : null}
      </button>
    );
  },
);

ActionButton.displayName = "ActionButton";
