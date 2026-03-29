"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

type CardContextType = {
  variant: "default" | "accent";
};

const CardContext = React.createContext<CardContextType>({
  variant: "default",
});

const useCardContext = () => React.useContext(CardContext);

const cardVariants = cva("flex flex-col items-stretch rounded-xl text-card-foreground", {
  variants: {
    variant: {
      default:
        "rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--surface-elevated-soft)] shadow-[inset_0_1px_0_rgba(255,255,255,0.018),0_12px_28px_rgba(0,0,0,0.12)]",
      accent:
        "rounded-[var(--radius-panel-sm)] bg-[rgba(255,255,255,0.014)] p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.014),0_8px_22px_rgba(0,0,0,0.1)]",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

const cardHeaderVariants = cva("flex min-h-14 flex-wrap items-center justify-between gap-2.5 px-5", {
  variants: {
    variant: {
      default: "border-b border-[var(--separator)]",
      accent: "",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

const cardContentVariants = cva("grow p-5", {
  variants: {
    variant: {
      default: "",
      accent: "rounded-t-xl bg-card [&:last-child]:rounded-b-xl",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

const cardTableVariants = cva("grid grow", {
  variants: {
    variant: {
      default: "",
      accent: "rounded-xl bg-card",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

const cardFooterVariants = cva("flex min-h-14 items-center px-5", {
  variants: {
    variant: {
      default: "border-t border-[var(--separator)]",
      accent: "mt-[2px] rounded-b-xl bg-card",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

function Card({
  className,
  variant = "default",
  ...props
}: React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof cardVariants>) {
  return (
    <CardContext.Provider value={{ variant: variant || "default" }}>
      <div data-slot="card" className={cn(cardVariants({ variant }), className)} {...props} />
    </CardContext.Provider>
  );
}

function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  const { variant } = useCardContext();
  return <div data-slot="card-header" className={cn(cardHeaderVariants({ variant }), className)} {...props} />;
}

function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  const { variant } = useCardContext();
  return <div data-slot="card-content" className={cn(cardContentVariants({ variant }), className)} {...props} />;
}

function CardTable({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  const { variant } = useCardContext();
  return <div data-slot="card-table" className={cn(cardTableVariants({ variant }), className)} {...props} />;
}

function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  const { variant } = useCardContext();
  return <div data-slot="card-footer" className={cn(cardFooterVariants({ variant }), className)} {...props} />;
}

function CardHeading({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-heading" className={cn("space-y-1", className)} {...props} />;
}

function CardToolbar({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-toolbar" className={cn("flex items-center gap-2.5", className)} {...props} />;
}

function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 data-slot="card-title" className={cn("text-base font-semibold leading-none tracking-tight", className)} {...props} />;
}

function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-description" className={cn("text-sm text-[var(--text-tertiary)]", className)} {...props} />;
}

export {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardHeading,
  CardTable,
  CardTitle,
  CardToolbar,
};
