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
          "border-white/70 bg-[#f3f3f3] text-[#0f0f10] shadow-[inset_0_1px_0_rgba(255,255,255,0.55),0_10px_26px_rgba(0,0,0,0.22)] hover:border-white hover:bg-white hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.65),0_12px_32px_rgba(0,0,0,0.24)] data-[state=open]:border-white data-[state=open]:bg-white",
        mono:
          "border-zinc-800 bg-zinc-950 text-white shadow-[0_10px_24px_rgba(0,0,0,0.24)] hover:border-zinc-700 hover:bg-zinc-900 dark:border-zinc-300/70 dark:bg-zinc-300 dark:text-black dark:hover:border-zinc-200 dark:hover:bg-zinc-200",
        destructive:
          "border-[color-mix(in_srgb,var(--tone-danger-border)_70%,transparent)] bg-[var(--tone-danger-bg-strong)] text-[var(--tone-danger-text)] shadow-[0_10px_24px_rgba(0,0,0,0.2)] hover:border-[color-mix(in_srgb,var(--tone-danger-border)_85%,white_8%)] hover:bg-[var(--tone-danger-bg)]",
        secondary:
          "border-white/10 bg-white/[0.02] text-[var(--text-secondary)] shadow-[inset_0_1px_0_rgba(255,255,255,0.02),0_8px_20px_rgba(0,0,0,0.08)] hover:border-white/18 hover:bg-white/[0.055] hover:text-[var(--text-primary)] hover:shadow-[0_12px_28px_rgba(0,0,0,0.16)] data-[state=open]:border-white/18 data-[state=open]:bg-white/[0.055]",
        outline:
          "border-white/12 bg-white/[0.018] text-[var(--text-secondary)] shadow-[inset_0_1px_0_rgba(255,255,255,0.018),0_6px_18px_rgba(0,0,0,0.06)] hover:border-white/18 hover:bg-white/[0.045] hover:text-[var(--text-primary)]",
        dashed:
          "border border-dashed border-white/12 bg-white/[0.014] text-[var(--text-secondary)] hover:border-white/20 hover:bg-white/[0.04] hover:text-[var(--text-primary)]",
        ghost: "border-transparent text-[var(--text-secondary)] hover:border-white/10 hover:bg-white/[0.045] hover:text-[var(--text-primary)]",
        dim: "border-transparent bg-transparent text-muted-foreground shadow-none hover:border-transparent hover:bg-transparent hover:text-foreground",
        foreground: "border-transparent bg-transparent text-foreground shadow-none hover:border-transparent hover:bg-transparent",
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
          "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 active:translate-y-0 active:scale-[0.985]",
        icon: "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 active:translate-y-0 active:scale-[0.985]",
        link: "h-auto rounded-none border-transparent bg-transparent p-0 text-primary shadow-none hover:bg-transparent",
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
        className: "border-transparent bg-transparent text-primary hover:bg-primary/8",
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
