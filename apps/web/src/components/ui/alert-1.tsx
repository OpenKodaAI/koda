"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";
import { Button } from "@/components/ui/button-1";
import { cn } from "@/lib/utils";

const alertVariants = cva(
  "flex w-full items-start gap-2.5 border transition-[transform,opacity,border-color,background-color,color] group-[.toaster]:w-full",
  {
    variants: {
      variant: {
        secondary: "",
        primary: "",
        destructive: "",
        success: "",
        info: "",
        mono: "",
        warning: "",
      },
      icon: {
        primary: "",
        destructive: "",
        success: "",
        info: "",
        warning: "",
      },
      appearance: {
        solid: "",
        outline: "",
        light: "",
        stroke: "text-[var(--text-primary)]",
      },
      size: {
        lg: "rounded-[1rem] p-4 text-base [&>[data-slot=alert-icon]>svg]:size-5.5 [&_[data-slot=alert-close]]:mt-0.5",
        md: "rounded-[0.95rem] p-3.5 text-sm [&>[data-slot=alert-icon]>svg]:size-5 [&_[data-slot=alert-close]]:mt-0.5",
        sm: "rounded-[0.85rem] px-3 py-2.5 text-xs [&>[data-slot=alert-icon]>svg]:size-4 [&_[data-slot=alert-close]]:mt-0.25",
      },
    },
    compoundVariants: [
      {
        variant: "secondary",
        appearance: "solid",
        className:
          "border-[var(--border-subtle)] bg-[var(--surface-elevated)] text-[var(--text-primary)]",
      },
      {
        variant: "primary",
        appearance: "solid",
        className:
          "border-[var(--tone-info-border)] bg-[var(--tone-info-bg-strong)] text-[var(--tone-info-text)]",
      },
      {
        variant: "destructive",
        appearance: "solid",
        className:
          "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg-strong)] text-[var(--tone-danger-text)]",
      },
      {
        variant: "success",
        appearance: "solid",
        className:
          "border-[var(--tone-success-border)] bg-[var(--tone-success-bg-strong)] text-[var(--tone-success-text)]",
      },
      {
        variant: "info",
        appearance: "solid",
        className:
          "border-[var(--tone-info-border)] bg-[var(--tone-info-bg-strong)] text-[var(--tone-info-text)]",
      },
      {
        variant: "warning",
        appearance: "solid",
        className:
          "border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg-strong)] text-[var(--tone-warning-text)]",
      },
      {
        variant: "mono",
        appearance: "solid",
        className:
          "border-[var(--border-subtle)] bg-[var(--surface-elevated)] text-[var(--text-primary)]",
      },
      {
        variant: "secondary",
        appearance: "outline",
        className:
          "border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-primary)] [&_[data-slot=alert-close]]:text-[var(--text-secondary)]",
      },
      {
        variant: "primary",
        appearance: "outline",
        className:
          "border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-info-dot)]",
      },
      {
        variant: "destructive",
        appearance: "outline",
        className:
          "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-danger-dot)]",
      },
      {
        variant: "success",
        appearance: "outline",
        className:
          "border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-success-dot)]",
      },
      {
        variant: "info",
        appearance: "outline",
        className:
          "border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-info-dot)]",
      },
      {
        variant: "warning",
        appearance: "outline",
        className:
          "border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-warning-dot)]",
      },
      {
        variant: "mono",
        appearance: "outline",
        className:
          "border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-primary)]",
      },
      {
        variant: "secondary",
        appearance: "light",
        className:
          "border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-primary)]",
      },
      {
        variant: "primary",
        appearance: "light",
        className:
          "border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-info-dot)]",
      },
      {
        variant: "destructive",
        appearance: "light",
        className:
          "border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-danger-dot)]",
      },
      {
        variant: "success",
        appearance: "light",
        className:
          "border-[var(--tone-success-border)] bg-[var(--tone-success-bg)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-success-dot)]",
      },
      {
        variant: "info",
        appearance: "light",
        className:
          "border-[var(--tone-info-border)] bg-[var(--tone-info-bg)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-info-dot)]",
      },
      {
        variant: "warning",
        appearance: "light",
        className:
          "border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-warning-dot)]",
      },
      {
        variant: "mono",
        icon: "primary",
        className: "[&_[data-slot=alert-icon]]:text-[#8ab2ff]",
      },
      {
        variant: "mono",
        icon: "warning",
        className: "[&_[data-slot=alert-icon]]:text-[var(--tone-warning-dot)]",
      },
      {
        variant: "mono",
        icon: "success",
        className: "[&_[data-slot=alert-icon]]:text-[var(--tone-success-dot)]",
      },
      {
        variant: "mono",
        icon: "destructive",
        className: "[&_[data-slot=alert-icon]]:text-[var(--tone-danger-dot)]",
      },
      {
        variant: "mono",
        icon: "info",
        className: "[&_[data-slot=alert-icon]]:text-[var(--tone-info-dot)]",
      },
    ],
    defaultVariants: {
      variant: "secondary",
      appearance: "solid",
      size: "md",
    },
  },
);

interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {
  close?: boolean;
  onClose?: () => void;
}

interface AlertIconProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {}

function Alert({
  className,
  variant,
  size,
  icon,
  appearance,
  close = false,
  onClose,
  children,
  ...props
}: AlertProps) {
  return (
    <div
      data-slot="alert"
      role="alert"
      className={cn(alertVariants({ variant, size, icon, appearance }), className)}
      {...props}
    >
      {children}
      {close ? (
        <Button
          size="sm"
          variant="inverse"
          mode="icon"
          type="button"
          onClick={onClose}
          aria-label="Dismiss"
          data-slot="alert-close"
          className="group size-6 shrink-0 self-start rounded-full text-[var(--icon-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--icon-primary)]"
        >
          <X className="size-3.5" />
        </Button>
      ) : null}
    </div>
  );
}

function AlertTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <div
      data-slot="alert-title"
      className={cn("grow tracking-[-0.02em]", className)}
      {...props}
    />
  );
}

function AlertIcon({ children, className, ...props }: AlertIconProps) {
  return (
    <div
      data-slot="alert-icon"
      className={cn("mt-0.5 shrink-0 text-current", className)}
      {...props}
    >
      {children}
    </div>
  );
}

function AlertToolbar({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="alert-toolbar"
      className={cn("shrink-0", className)}
      {...props}
    >
      {children}
    </div>
  );
}

function AlertDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <div
      data-slot="alert-description"
      className={cn(
        "text-[13px] leading-relaxed text-[var(--text-secondary)] [&_p]:mb-2 [&_p]:leading-relaxed last:[&_p]:mb-0",
        className,
      )}
      {...props}
    />
  );
}

function AlertContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="alert-content"
      className={cn("min-w-0 flex-1 space-y-1.5 [&_[data-slot=alert-title]]:font-semibold", className)}
      {...props}
    />
  );
}

export {
  Alert,
  AlertContent,
  AlertDescription,
  AlertIcon,
  AlertTitle,
  AlertToolbar,
};
