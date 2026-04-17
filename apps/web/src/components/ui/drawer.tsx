"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  width?: string;
  side?: "right" | "left";
  children: React.ReactNode;
  className?: string;
  closeLabel?: string;
  footer?: React.ReactNode;
  modal?: boolean;
}

export function Drawer({
  open,
  onOpenChange,
  title,
  description,
  width = "min(560px, 92vw)",
  side = "right",
  children,
  className,
  closeLabel = "Close",
  footer,
  modal = false,
}: DrawerProps) {
  const positionClass =
    side === "right"
      ? "right-0 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:slide-in-from-right-4 data-[state=closed]:slide-out-to-right-4"
      : "left-0 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:slide-in-from-left-4 data-[state=closed]:slide-out-to-left-4";

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange} modal={modal}>
      <DialogPrimitive.Portal>
        {modal ? (
          <DialogPrimitive.Overlay
            className={cn(
              "fixed inset-0 z-[70] bg-[rgba(0,0,0,0.72)] backdrop-blur-[8px]",
              "data-[state=open]:animate-in data-[state=closed]:animate-out",
              "data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0",
            )}
          />
        ) : (
          <button
            type="button"
            aria-label={closeLabel}
            onClick={() => onOpenChange(false)}
            className={cn(
              "fixed inset-0 z-[70] cursor-default border-0 bg-[rgba(0,0,0,0.55)] backdrop-blur-[6px] transition-opacity",
              open ? "opacity-100" : "pointer-events-none opacity-0",
            )}
          />
        )}
        <DialogPrimitive.Content
          aria-describedby={description ? undefined : undefined}
          className={cn(
            "fixed inset-y-0 z-[71] flex h-full flex-col border-l border-[var(--border-subtle)] bg-[var(--panel-strong)] shadow-[var(--shadow-floating)] outline-none",
            positionClass,
            "duration-[220ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            className,
          )}
          style={{ width, maxWidth: "100vw" }}
        >
          <header className="flex items-start justify-between gap-3 border-b border-[var(--divider-hair)] px-5 py-4">
            <div className="min-w-0 flex-1">
              {title ? (
                <DialogPrimitive.Title className="m-0 text-[var(--font-size-md)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
                  {title}
                </DialogPrimitive.Title>
              ) : null}
              {description ? (
                <DialogPrimitive.Description className="m-0 mt-1 text-[0.8125rem] text-[var(--text-tertiary)]">
                  {description}
                </DialogPrimitive.Description>
              ) : null}
            </div>
            <DialogPrimitive.Close
              aria-label={closeLabel}
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] transition-[background-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel-strong)]"
            >
              <X className="h-4 w-4" />
            </DialogPrimitive.Close>
          </header>

          <div className="flex-1 min-h-0 overflow-y-auto">{children}</div>

          {footer ? (
            <footer className="shrink-0 border-t border-[var(--divider-hair)] px-5 py-3">
              {footer}
            </footer>
          ) : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export const DrawerClose = DialogPrimitive.Close;
