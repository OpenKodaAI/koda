"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useBlockSubmit } from "@/hooks/use-block-submit";
import { cn } from "@/lib/utils";
import type { z } from "zod";
import type { uiChoiceBlockSchema } from "@/lib/contracts/generative-ui";

export type UiChoiceBlock = z.infer<typeof uiChoiceBlockSchema>;

export interface UiChoiceProps {
  block: UiChoiceBlock;
  agentId?: string | null;
  sessionId?: string | null;
}

export function UiChoice({ block, agentId, sessionId }: UiChoiceProps) {
  const { prompt, multi, options, submit_label } = block.payload;
  const [selected, setSelected] = useState<string[]>([]);
  const blockSubmit = useBlockSubmit({
    agentId,
    sessionId,
    blockId: block.id,
  });

  const toggle = (id: string) => {
    if (multi) {
      setSelected((prev) =>
        prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id],
      );
    } else {
      setSelected([id]);
    }
  };

  const handleSubmit = () => {
    void blockSubmit.submit({
      block_type: "ui_choice",
      values: { selection: selected },
    });
  };

  const disabled =
    blockSubmit.isPending || blockSubmit.isSubmitted || selected.length === 0;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!disabled) handleSubmit();
      }}
      className="rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] p-3 flex flex-col gap-3"
      data-submitted={blockSubmit.isSubmitted || undefined}
    >
      <p className="m-0 text-[var(--font-size-md)] text-[var(--text-primary)]">
        {prompt}
      </p>
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        {options.map((option) => {
          const active = selected.includes(option.id);
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => toggle(option.id)}
              disabled={blockSubmit.isPending || blockSubmit.isSubmitted}
              aria-pressed={active}
              className={cn(
                "flex flex-col items-start rounded-[var(--radius-panel-sm)] border px-3 py-2 text-left text-[0.8125rem] transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                active
                  ? "border-[var(--accent)] bg-[var(--panel)] text-[var(--text-primary)]"
                  : "border-[color:var(--border-subtle)] bg-transparent text-[var(--text-secondary)] hover:border-[color:var(--border-strong)] hover:text-[var(--text-primary)]",
                "disabled:opacity-50 disabled:cursor-not-allowed",
              )}
            >
              <span className="font-medium">{option.label}</span>
              {option.description ? (
                <span className="text-[0.75rem] text-[var(--text-quaternary)] mt-0.5">
                  {option.description}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      {blockSubmit.error ? (
        <p className="m-0 text-[0.75rem] text-[var(--tone-danger-dot)]">
          {blockSubmit.error}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button
          type="submit"
          variant="accent"
          size="sm"
          disabled={disabled}
          aria-busy={blockSubmit.isPending}
        >
          {blockSubmit.isSubmitted ? "✓" : submit_label}
        </Button>
      </div>
    </form>
  );
}
