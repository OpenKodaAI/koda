"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";
import { Button } from "@/components/ui/button-1";
import { cn } from "@/lib/utils";

const alertVariants = cva(
  "flex w-full items-start gap-2.5 border shadow-[0_18px_44px_rgba(0,0,0,0.26)] backdrop-blur-xl transition-[transform,opacity,border-color,background-color,color] group-[.toaster]:w-full",
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
          "border-white/8 bg-[rgba(24,24,25,0.96)] text-[var(--text-primary)]",
      },
      {
        variant: "primary",
        appearance: "solid",
        className:
          "border-[rgba(120,164,255,0.4)] bg-[rgba(56,92,160,0.94)] text-white",
      },
      {
        variant: "destructive",
        appearance: "solid",
        className:
          "border-[rgba(225,138,152,0.42)] bg-[var(--tone-danger-bg-strong)] text-[var(--tone-danger-text)]",
      },
      {
        variant: "success",
        appearance: "solid",
        className:
          "border-[rgba(119,197,144,0.42)] bg-[var(--tone-success-bg-strong)] text-[var(--tone-success-text)]",
      },
      {
        variant: "info",
        appearance: "solid",
        className:
          "border-[rgba(120,166,255,0.42)] bg-[var(--tone-info-bg-strong)] text-[var(--tone-info-text)]",
      },
      {
        variant: "warning",
        appearance: "solid",
        className:
          "border-[rgba(228,180,84,0.42)] bg-[var(--tone-warning-bg-strong)] text-[var(--tone-warning-text)]",
      },
      {
        variant: "mono",
        appearance: "solid",
        className:
          "border-white/10 bg-[rgba(16,16,17,0.96)] text-[var(--text-primary)]",
      },
      {
        variant: "secondary",
        appearance: "outline",
        className:
          "border-white/10 bg-[rgba(19,19,20,0.88)] text-[var(--text-primary)] [&_[data-slot=alert-close]]:text-[var(--text-secondary)]",
      },
      {
        variant: "primary",
        appearance: "outline",
        className:
          "border-[rgba(120,164,255,0.24)] bg-[rgba(16,22,36,0.88)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[#8ab2ff]",
      },
      {
        variant: "destructive",
        appearance: "outline",
        className:
          "border-[rgba(225,138,152,0.24)] bg-[rgba(35,20,24,0.88)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-danger-dot)]",
      },
      {
        variant: "success",
        appearance: "outline",
        className:
          "border-[rgba(119,197,144,0.24)] bg-[rgba(18,30,23,0.88)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-success-dot)]",
      },
      {
        variant: "info",
        appearance: "outline",
        className:
          "border-[rgba(120,166,255,0.24)] bg-[rgba(18,22,32,0.88)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-info-dot)]",
      },
      {
        variant: "warning",
        appearance: "outline",
        className:
          "border-[rgba(228,180,84,0.24)] bg-[rgba(33,27,18,0.88)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-warning-dot)]",
      },
      {
        variant: "mono",
        appearance: "outline",
        className:
          "border-white/10 bg-[rgba(19,19,20,0.88)] text-[var(--text-primary)]",
      },
      {
        variant: "secondary",
        appearance: "light",
        className:
          "border-white/8 bg-[rgba(255,255,255,0.045)] text-[var(--text-primary)]",
      },
      {
        variant: "primary",
        appearance: "light",
        className:
          "border-[rgba(120,164,255,0.16)] bg-[rgba(69,95,155,0.16)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[#8ab2ff]",
      },
      {
        variant: "destructive",
        appearance: "light",
        className:
          "border-[rgba(225,138,152,0.14)] bg-[rgba(122,54,67,0.14)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-danger-dot)]",
      },
      {
        variant: "success",
        appearance: "light",
        className:
          "border-[rgba(119,197,144,0.14)] bg-[rgba(50,92,67,0.16)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-success-dot)]",
      },
      {
        variant: "info",
        appearance: "light",
        className:
          "border-[rgba(120,166,255,0.14)] bg-[rgba(47,85,142,0.16)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-info-dot)]",
      },
      {
        variant: "warning",
        appearance: "light",
        className:
          "border-[rgba(228,180,84,0.14)] bg-[rgba(123,91,36,0.16)] text-[var(--text-primary)] [&_[data-slot=alert-icon]]:text-[var(--tone-warning-dot)]",
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
          className="group size-6 shrink-0 self-start rounded-full text-[var(--text-quaternary)] hover:bg-white/6 hover:text-[var(--text-primary)]"
        >
          <X className="size-3.5 opacity-70 group-hover:opacity-100" />
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
