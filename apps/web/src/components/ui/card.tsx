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

const cardVariants = cva(
  "flex flex-col items-stretch rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)] text-[var(--text-primary)] shadow-none transition-[border-color,background-color] duration-[200ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
  {
    variants: {
      variant: {
        default: "",
        accent: "",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

const cardHeaderVariants = cva(
  "flex min-h-12 flex-wrap items-center justify-between gap-2.5 border-b border-[color:var(--divider-hair)] px-4",
);

const cardContentVariants = cva("grow p-4");

const cardTableVariants = cva("grid grow");

const cardFooterVariants = cva(
  "flex min-h-12 items-center border-t border-[color:var(--divider-hair)] px-4",
);

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
  useCardContext();
  return <div data-slot="card-header" className={cn(cardHeaderVariants(), className)} {...props} />;
}

function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  useCardContext();
  return <div data-slot="card-content" className={cn(cardContentVariants(), className)} {...props} />;
}

function CardTable({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  useCardContext();
  return <div data-slot="card-table" className={cn(cardTableVariants(), className)} {...props} />;
}

function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  useCardContext();
  return <div data-slot="card-footer" className={cn(cardFooterVariants(), className)} {...props} />;
}

function CardHeading({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-heading" className={cn("space-y-1", className)} {...props} />;
}

function CardToolbar({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-toolbar" className={cn("flex items-center gap-2", className)} {...props} />;
}

function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      data-slot="card-title"
      className={cn("text-[var(--font-size-md)] font-medium leading-none tracking-[var(--tracking-tight)]", className)}
      {...props}
    />
  );
}

function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-[var(--font-size-sm)] text-[var(--text-tertiary)]", className)}
      {...props}
    />
  );
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
