import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {
  asChild?: boolean;
  dotClassName?: string;
  disabled?: boolean;
}

export interface BadgeButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof badgeButtonVariants> {
  asChild?: boolean;
}

const badgeVariants = cva(
  "inline-flex items-center justify-center border border-transparent font-medium focus:outline-hidden focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-2 focus:ring-offset-[var(--canvas)] [&_svg]:-ms-px [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-[var(--panel-strong)] text-[var(--text-primary)]",
        secondary: "bg-[var(--panel-soft)] text-[var(--text-secondary)]",
        success: "bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]",
        warning: "bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]",
        info: "bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]",
        outline: "border border-[var(--border-subtle)] bg-transparent text-[var(--text-secondary)]",
        destructive: "bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]",
      },
      appearance: {
        default: "",
        light: "",
        outline: "",
        ghost: "border-transparent bg-transparent",
        solid: "",
      },
      disabled: {
        true: "pointer-events-none opacity-50",
      },
      size: {
        lg: "h-6 min-w-6 gap-1.5 rounded-[var(--radius-chip)] px-[0.5rem] text-xs [&_svg]:size-3.5",
        md: "h-[1.375rem] min-w-[1.375rem] gap-1.5 rounded-[var(--radius-chip)] px-[0.45rem] text-xs [&_svg]:size-3.5",
        sm: "h-5 min-w-5 gap-1 rounded-[6px] px-[0.325rem] text-[0.6875rem] leading-[0.75rem] [&_svg]:size-3",
        xs: "h-4 min-w-4 gap-1 rounded-[4px] px-[0.25rem] text-[0.625rem] leading-[0.5rem] [&_svg]:size-3",
      },
      shape: {
        default: "",
        circle: "rounded-full",
      },
    },
    compoundVariants: [
      {
        variant: "success",
        appearance: "solid",
        className: "bg-[var(--tone-success-bg-strong)]",
      },
      {
        variant: "warning",
        appearance: "solid",
        className: "bg-[var(--tone-warning-bg-strong)]",
      },
      {
        variant: "info",
        appearance: "solid",
        className: "bg-[var(--tone-info-bg-strong)]",
      },
      {
        variant: "destructive",
        appearance: "solid",
        className: "bg-[var(--tone-danger-bg-strong)]",
      },
      {
        variant: "primary",
        appearance: "light",
        className: "bg-[var(--surface-hover)] text-[var(--text-primary)]",
      },
      {
        variant: "secondary",
        appearance: "light",
        className: "bg-[var(--panel-soft)] text-[var(--text-secondary)]",
      },
      {
        variant: "success",
        appearance: "light",
        className: "bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]",
      },
      {
        variant: "warning",
        appearance: "light",
        className: "bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]",
      },
      {
        variant: "info",
        appearance: "light",
        className: "bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]",
      },
      {
        variant: "destructive",
        appearance: "light",
        className: "bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]",
      },
      {
        appearance: "ghost",
        size: "lg",
        className: "px-0",
      },
      {
        appearance: "ghost",
        size: "md",
        className: "px-0",
      },
      {
        appearance: "ghost",
        size: "sm",
        className: "px-0",
      },
      {
        appearance: "ghost",
        size: "xs",
        className: "px-0",
      },
    ],
    defaultVariants: {
      variant: "primary",
      appearance: "default",
      size: "md",
    },
  }
);

const badgeButtonVariants = cva(
  "inline-flex size-3.5 cursor-pointer items-center justify-center rounded-[4px] border border-transparent p-0 leading-none text-[var(--icon-secondary)] transition-colors hover:border-[var(--border-subtle)] hover:bg-[var(--surface-hover)] hover:text-[var(--icon-primary)] [&>svg]:size-3.5 [&>svg]:opacity-100!",
  {
    variants: {
      variant: {
        default: "",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

function Badge({
  className,
  variant,
  size,
  appearance,
  shape,
  asChild = false,
  disabled,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "span";

  return (
    <Comp
      data-slot="badge"
      className={cn(badgeVariants({ variant, size, appearance, shape, disabled }), className)}
      {...props}
    />
  );
}

function BadgeButton({
  className,
  variant,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof badgeButtonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";

  return (
    <Comp data-slot="badge-button" className={cn(badgeButtonVariants({ variant, className }))} {...props} />
  );
}

function BadgeDot({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="badge-dot"
      className={cn("size-1.5 rounded-full bg-[currentColor]", className)}
      {...props}
    />
  );
}

export { Badge, BadgeButton, BadgeDot, badgeVariants };
