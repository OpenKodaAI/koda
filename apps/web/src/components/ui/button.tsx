import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { ChevronDown, type LucideIcon } from "lucide-react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "group inline-flex cursor-pointer items-center justify-center whitespace-nowrap border text-sm font-medium transition-[color,box-shadow,background-color,border-color,transform] disabled:pointer-events-none disabled:opacity-60 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "border-[color:var(--button-primary-bg)] bg-[var(--button-primary-bg)] text-[var(--button-primary-text)] hover:border-[color:var(--button-primary-hover)] hover:bg-[var(--button-primary-hover)] data-[state=open]:border-[color:var(--button-primary-hover)] data-[state=open]:bg-[var(--button-primary-hover)]",
        mono:
          "border-[color:var(--border-subtle)] bg-[var(--surface-elevated)] text-[var(--text-primary)] hover:border-[color:var(--border-strong)] hover:bg-[var(--surface-hover)]",
        destructive:
          "border-[color:var(--tone-danger-border)] bg-[var(--tone-danger-bg-strong)] text-[var(--tone-danger-text)] hover:border-[color:var(--tone-danger-border)] hover:bg-[var(--tone-danger-bg)]",
        secondary:
          "border-[color:var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-secondary)] hover:border-[color:var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] data-[state=open]:border-[color:var(--border-strong)] data-[state=open]:bg-[var(--surface-hover)]",
        outline:
          "border-[color:var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-secondary)] hover:border-[color:var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
        dashed:
          "border border-dashed border-[color:var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[var(--text-secondary)] hover:border-[color:var(--border-strong)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
        ghost: "border-transparent text-[var(--text-secondary)] hover:border-[color:var(--border-subtle)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
        dim: "border-transparent bg-transparent text-[var(--text-tertiary)] shadow-none hover:border-transparent hover:bg-transparent hover:text-[var(--text-primary)] dark:text-muted-foreground dark:hover:text-foreground",
        foreground: "border-transparent bg-transparent text-[var(--text-primary)] shadow-none hover:border-transparent hover:bg-transparent dark:text-foreground",
        inverse: "border-transparent bg-transparent text-inherit shadow-none hover:border-transparent hover:bg-transparent",
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
        lg: "h-10 gap-1.5 rounded-[var(--radius-panel-sm)] px-4 text-sm [&_svg:not([class*=size-])]:size-4",
        md: "h-8.5 gap-1.5 rounded-[var(--radius-panel-sm)] px-3 text-[0.8125rem] [&_svg:not([class*=size-])]:size-4",
        sm: "h-7 gap-1.25 rounded-[var(--radius-panel-sm)] px-2.5 text-xs [&_svg:not([class*=size-])]:size-3.5",
        icon: "size-8.5 shrink-0 rounded-[var(--radius-panel-sm)] p-0 [&_svg:not([class*=size-])]:size-4",
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
          "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        icon: "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        link: "h-auto rounded-none border-transparent bg-transparent p-0 text-[var(--text-primary)] shadow-none hover:bg-transparent dark:text-primary",
        input:
          "justify-start font-normal focus-visible:outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring/30",
      },
      placeholder: {
        true: "text-muted-foreground",
        false: "",
      },
    },
    compoundVariants: [
      {
        size: "md",
        autoHeight: true,
        className: "h-auto min-h-8.5",
      },
      {
        size: "sm",
        autoHeight: true,
        className: "h-auto min-h-7",
      },
      {
        size: "lg",
        autoHeight: true,
        className: "h-auto min-h-10",
      },
      {
        variant: "outline",
        mode: "input",
        placeholder: true,
        className: "text-muted-foreground",
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
        className: "border-transparent bg-transparent text-[var(--text-primary)] hover:bg-[var(--surface-hover)]",
      },
      {
        size: "icon",
        mode: "icon",
        className: "size-8.5 p-0",
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
