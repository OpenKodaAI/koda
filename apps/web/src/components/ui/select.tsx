"use client";

import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown, ChevronUp, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Sentinel value for "no selection" / "all" items. Radix Select rejects
 * `SelectItem value=""`, so use this constant for any option that maps to
 * `null | undefined | ""` in the underlying state.
 *
 *   <Select
 *     value={x ?? SELECT_ALL_VALUE}
 *     onValueChange={(v) => setX(v === SELECT_ALL_VALUE ? null : v)}
 *   >
 *     ...
 *     <SelectItem value={SELECT_ALL_VALUE}>Todos</SelectItem>
 *   </Select>
 */
export const SELECT_ALL_VALUE = "__all__";

export type SelectTriggerSize = "sm" | "md" | "lg";

const triggerSizeClasses: Record<SelectTriggerSize, string> = {
  sm: "h-8 px-2.5 text-[0.75rem]",
  md: "h-9 px-3 text-[0.8125rem]",
  lg: "h-11 px-4 text-[0.875rem]",
};

const Select = SelectPrimitive.Root;

const SelectGroup = SelectPrimitive.Group;

const SelectValue = SelectPrimitive.Value;

interface SelectTriggerProps extends React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger> {
  sizeVariant?: SelectTriggerSize;
  invalid?: boolean;
}

const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  SelectTriggerProps
>(({ className, children, sizeVariant = "md", invalid, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    data-slot="select-trigger"
    aria-invalid={invalid || undefined}
    className={cn(
      "flex w-full items-center justify-between gap-2 rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] text-[var(--text-primary)]",
      "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
      "hover:border-[var(--border-strong)]",
      "focus:outline-none focus-visible:border-[var(--border-strong)] focus-visible:bg-[var(--panel)]",
      "data-[state=open]:border-[var(--border-strong)] data-[state=open]:bg-[var(--panel)]",
      "data-[placeholder]:text-[var(--text-quaternary)]",
      "disabled:cursor-not-allowed disabled:opacity-60",
      invalid && "border-[var(--tone-danger-border)] focus-visible:border-[var(--tone-danger-border)]",
      triggerSizeClasses[sizeVariant],
      className,
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className="icon-sm shrink-0 text-[var(--text-tertiary)]" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;

const SelectScrollUpButton = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.ScrollUpButton>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollUpButton>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollUpButton
    ref={ref}
    className={cn("flex cursor-default items-center justify-center py-1 text-[var(--text-tertiary)]", className)}
    {...props}
  >
    <ChevronUp className="icon-sm" />
  </SelectPrimitive.ScrollUpButton>
));
SelectScrollUpButton.displayName = SelectPrimitive.ScrollUpButton.displayName;

const SelectScrollDownButton = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.ScrollDownButton>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollDownButton>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollDownButton
    ref={ref}
    className={cn("flex cursor-default items-center justify-center py-1 text-[var(--text-tertiary)]", className)}
    {...props}
  >
    <ChevronDown className="icon-sm" />
  </SelectPrimitive.ScrollDownButton>
));
SelectScrollDownButton.displayName = SelectPrimitive.ScrollDownButton.displayName;

const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
>(({ className, children, position = "popper", sideOffset = 6, ...props }, ref) => {
  const [query, setQuery] = React.useState("");
  const [hasMatches, setHasMatches] = React.useState(true);
  const contentRef = React.useRef<React.ElementRef<typeof SelectPrimitive.Content>>(null);
  const normalizedQuery = query.trim().toLowerCase();
  const setRefs = React.useCallback(
    (node: React.ElementRef<typeof SelectPrimitive.Content> | null) => {
      contentRef.current = node;
      if (typeof ref === "function") {
        ref(node);
      } else if (ref) {
        ref.current = node;
      }
    },
    [ref],
  );

  React.useEffect(() => {
    const items = Array.from(
      contentRef.current?.querySelectorAll<HTMLElement>("[data-slot='select-item']") ?? [],
    );
    if (items.length === 0) {
      setHasMatches(true);
      return;
    }

    let visibleCount = 0;
    for (const item of items) {
      const matches =
        !normalizedQuery || item.textContent?.toLowerCase().includes(normalizedQuery);
      item.hidden = !matches;
      if (matches) visibleCount += 1;
    }
    const labels = Array.from(
      contentRef.current?.querySelectorAll<HTMLElement>("[data-slot='select-label']") ?? [],
    );
    for (const label of labels) {
      const groupItems = Array.from(
        label.parentElement?.querySelectorAll<HTMLElement>("[data-slot='select-item']") ?? [],
      );
      label.hidden =
        normalizedQuery.length > 0 &&
        groupItems.length > 0 &&
        groupItems.every((item) => item.hidden);
    }
    setHasMatches(visibleCount > 0);
  }, [normalizedQuery, children]);

  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        ref={setRefs}
        data-slot="select-content"
        sideOffset={sideOffset}
        position={position}
        className={cn(
          // z-[90] keeps the dropdown above modals/drawers (z-[70..80]). Without
          // this bump, Selects rendered inside modals get clipped behind them.
          "app-floating-panel relative z-[90] min-w-[10rem] overflow-hidden text-[var(--text-primary)]",
          "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
          "data-[side=bottom]:slide-in-from-top-1 data-[side=top]:slide-in-from-bottom-1",
          className,
        )}
        {...props}
      >
        <div className="border-b border-[var(--divider-hair)] px-2.5 py-2">
          <div
            className="flex h-8 items-center gap-2 rounded-[var(--radius-input)] px-2.5 text-[var(--text-tertiary)] transition-[background-color,box-shadow] duration-150 focus-within:bg-[var(--panel-soft)] focus-within:shadow-[inset_0_0_0_1px_var(--border-strong)]"
            onPointerDown={(event) => event.stopPropagation()}
          >
            <Search size={13} className="shrink-0 text-[var(--text-quaternary)]" />
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDownCapture={(event) => {
                if (event.key !== "Escape") event.stopPropagation();
              }}
              placeholder="Search..."
              aria-label="Search options"
              className="h-full w-full min-w-0 bg-transparent text-[0.8125rem] text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)]"
              style={{ outline: "none", border: "none", boxShadow: "none" }}
            />
            {query ? (
              <button
                type="button"
                onClick={() => setQuery("")}
                aria-label="Clear search"
                className="flex h-5 w-5 shrink-0 items-center justify-center rounded-[var(--radius-chip)] text-[var(--text-quaternary)] transition-colors focus-visible:text-[var(--text-primary)] focus-visible:outline-none"
              >
                <X size={12} />
              </button>
            ) : null}
          </div>
        </div>
        <SelectScrollUpButton />
        <SelectPrimitive.Viewport
          className={cn(
            "max-h-[20rem] p-1",
            position === "popper" &&
              "h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)]",
          )}
        >
          {children}
          {!hasMatches ? (
            <div className="px-3 py-4 text-center text-xs text-[var(--text-quaternary)]">
              No options found.
            </div>
          ) : null}
        </SelectPrimitive.Viewport>
        <SelectScrollDownButton />
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
});
SelectContent.displayName = SelectPrimitive.Content.displayName;

const SelectLabel = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Label>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Label>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.Label
    ref={ref}
    data-slot="select-label"
    className={cn(
      "px-2 pb-1 pt-2 text-[10px] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]",
      className,
    )}
    {...props}
  />
));
SelectLabel.displayName = SelectPrimitive.Label.displayName;

const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    data-slot="select-item"
    className={cn(
      "relative flex w-full cursor-default select-none items-center gap-2 rounded-[var(--radius-panel-sm)] py-1.5 pl-7 pr-2 text-[0.8125rem] text-[var(--text-secondary)] outline-none",
      "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
      "focus:text-[var(--text-primary)]",
      "data-[state=checked]:bg-[var(--panel-strong)] data-[state=checked]:text-[var(--text-primary)]",
      "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      className,
    )}
    {...props}
  >
    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <Check className="icon-sm text-[var(--accent)]" />
      </SelectPrimitive.ItemIndicator>
    </span>

    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
SelectItem.displayName = SelectPrimitive.Item.displayName;

const SelectSeparator = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Separator>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Separator>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.Separator
    ref={ref}
    className={cn("my-1 h-px bg-[var(--divider-hair)]", className)}
    {...props}
  />
));
SelectSeparator.displayName = SelectPrimitive.Separator.displayName;

export {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectScrollDownButton,
  SelectScrollUpButton,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
};
