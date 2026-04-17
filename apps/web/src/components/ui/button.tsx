import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { ChevronDown, type LucideIcon } from "lucide-react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "group inline-flex cursor-pointer items-center justify-center whitespace-nowrap border text-sm font-medium transition-[color,background-color,border-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] disabled:pointer-events-none disabled:opacity-60 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "border-[color:var(--button-primary-bg)] bg-[var(--button-primary-bg)] text-[var(--button-primary-text)] hover:border-[color:var(--button-primary-hover)] hover:bg-[var(--button-primary-hover)] data-[state=open]:border-[color:var(--button-primary-hover)] data-[state=open]:bg-[var(--button-primary-hover)]",
        accent:
          "border-[color:var(--accent)] bg-[var(--accent)] text-white hover:border-[color:var(--accent-hover)] hover:bg-[var(--accent-hover)] data-[state=open]:border-[color:var(--accent-hover)] data-[state=open]:bg-[var(--accent-hover)]",
        mono:
          "border-[color:var(--border-subtle)] bg-[var(--panel)] text-[var(--text-primary)] hover:border-[color:var(--border-strong)] hover:bg-[var(--surface-hover)]",
        destructive:
          "border-[color:var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)] hover:border-[color:var(--tone-danger-border)] hover:bg-[var(--tone-danger-bg-strong)]",
        secondary:
          "border-[color:var(--border-subtle)] bg-[var(--panel-soft)] text-[var(--text-secondary)] hover:border-[color:var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] data-[state=open]:border-[color:var(--border-strong)] data-[state=open]:bg-[var(--surface-hover)]",
        outline:
          "border-[color:var(--border-subtle)] bg-transparent text-[var(--text-secondary)] hover:border-[color:var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
        dashed:
          "border-dashed border-[color:var(--border-subtle)] bg-transparent text-[var(--text-secondary)] hover:border-[color:var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
        ghost:
          "border-transparent bg-transparent text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
        dim:
          "border-transparent bg-transparent text-[var(--text-tertiary)] hover:bg-transparent hover:text-[var(--text-primary)]",
        foreground:
          "border-transparent bg-transparent text-[var(--text-primary)] hover:bg-transparent",
        inverse:
          "border-transparent bg-transparent text-inherit hover:bg-transparent",
      },
      appearance: {
        default: "",
        ghost: "",
      },
      underline: {
        solid: "",
        dashed: "",
      },
      underlined: {
        solid: "",
        dashed: "",
      },
      size: {
        lg: "h-9 gap-1.5 rounded-[var(--radius-panel-sm)] px-4 text-[0.875rem] [&_svg:not([class*=size-])]:size-4",
        md: "h-8 gap-1.5 rounded-[var(--radius-panel-sm)] px-3 text-[0.8125rem] [&_svg:not([class*=size-])]:size-4",
        sm: "h-7 gap-1.25 rounded-[var(--radius-panel-sm)] px-2.5 text-xs [&_svg:not([class*=size-])]:size-3.5",
        icon: "size-8 shrink-0 rounded-[var(--radius-panel-sm)] p-0 [&_svg:not([class*=size-])]:size-4",
      },
      autoHeight: {
        true: "",
        false: "",
      },
      shape: {
        default: "",
        circle: "rounded-full",
      },
      mode: {
        default:
          "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
        icon: "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
        link: "h-auto rounded-none border-transparent bg-transparent p-0 text-[var(--text-primary)] hover:bg-transparent",
        input:
          "justify-start font-normal focus-visible:outline-hidden focus-visible:ring-[3px] focus-visible:ring-[var(--accent-muted)]",
      },
      placeholder: {
        true: "text-[var(--text-quaternary)]",
        false: "",
      },
    },
    compoundVariants: [
      {
        size: "md",
        autoHeight: true,
        className: "h-auto min-h-8",
      },
      {
        size: "sm",
        autoHeight: true,
        className: "h-auto min-h-7",
      },
      {
        size: "lg",
        autoHeight: true,
        className: "h-auto min-h-9",
      },
      {
        variant: "outline",
        mode: "input",
        placeholder: true,
        className: "text-[var(--text-quaternary)]",
      },
      {
        variant: "primary",
        mode: "link",
        underline: "solid",
        className: "hover:underline hover:underline-offset-4",
      },
      {
        variant: "primary",
        mode: "link",
        underlined: "solid",
        className: "underline underline-offset-4",
      },
      {
        variant: "primary",
        appearance: "ghost",
        className:
          "border-transparent bg-transparent text-[var(--text-primary)] hover:bg-[var(--surface-hover)]",
      },
      {
        size: "icon",
        mode: "icon",
        className: "size-8 p-0",
      },
    ],
    defaultVariants: {
      variant: "primary",
      mode: "default",
      size: "md",
      shape: "default",
      appearance: "default",
      autoHeight: false,
      placeholder: false,
    },
  }
);

function Button({
  className,
  selected,
  variant,
  shape,
  appearance,
  mode,
  size,
  autoHeight,
  underlined,
  underline,
  asChild = false,
  placeholder = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    selected?: boolean;
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot : "button";

  return (
    <Comp
      data-slot="button"
      className={cn(
        buttonVariants({
          variant,
          size,
          shape,
          appearance,
          mode,
          autoHeight,
          placeholder,
          underlined,
          underline,
          className,
        }),
        asChild && props.disabled && "pointer-events-none opacity-50"
      )}
      {...(selected && { "data-state": "open" })}
      {...props}
    />
  );
}

interface ButtonArrowProps extends React.SVGProps<SVGSVGElement> {
  icon?: LucideIcon;
}

function ButtonArrow({ icon: Icon = ChevronDown, className, ...props }: ButtonArrowProps) {
  return <Icon data-slot="button-arrow" className={cn("-me-1 ms-auto", className)} {...props} />;
}

export { Button, ButtonArrow, buttonVariants };
