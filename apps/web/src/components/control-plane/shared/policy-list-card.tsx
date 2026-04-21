"use client";

import { useState, type KeyboardEvent, type ReactNode } from "react";
import { Plus, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

export interface PolicyListCardProps {
  title: ReactNode;
  description?: ReactNode;
  items: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  emptyLabel?: string;
  className?: string;
  readOnly?: boolean;
}

export function PolicyListCard({
  title,
  description,
  items,
  onChange,
  placeholder,
  emptyLabel,
  className,
  readOnly = false,
}: PolicyListCardProps) {
  const { t } = useAppI18n();
  const [draft, setDraft] = useState("");

  function commit() {
    const value = draft.trim();
    if (!value) return;
    onChange([...items, value]);
    setDraft("");
  }

  function remove(index: number) {
    const next = items.filter((_, cursor) => cursor !== index);
    onChange(next);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      commit();
    }
  }

  return (
    <div
      className={cn(
        "rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-4",
        className,
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h4 className="m-0 text-[0.8125rem] font-medium text-[var(--text-primary)]">{title}</h4>
          {description ? (
            <p className="m-0 text-[0.75rem] leading-[1.5] text-[var(--text-tertiary)]">
              {description}
            </p>
          ) : null}
        </div>
        <span className="shrink-0 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
          {items.length}
        </span>
      </header>

      {items.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-1.5">
          {items.map((item, index) => (
            <li
              key={`${item}-${index}`}
              className="flex items-center gap-2 rounded-[var(--radius-panel-sm)] bg-[var(--panel)] px-2.5 py-1.5 text-[0.8125rem] text-[var(--text-primary)]"
            >
              <span className="min-w-0 flex-1 truncate">{item}</span>
              {!readOnly ? (
                <button
                  type="button"
                  aria-label={t("controlPlane.policy.remove", { defaultValue: "Remove" })}
                  onClick={() => remove(index)}
                  className="inline-flex h-6 w-6 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-quaternary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
                >
                  <X className="icon-xs" strokeWidth={1.75} aria-hidden />
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-[0.75rem] text-[var(--text-quaternary)]">
          {emptyLabel ?? t("controlPlane.policy.empty", { defaultValue: "Nothing defined yet." })}
        </p>
      )}

      {!readOnly ? (
        <div className="mt-3 flex items-center gap-2">
          <Input
            sizeVariant="sm"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              placeholder ??
              t("controlPlane.policy.addPlaceholder", {
                defaultValue: "Add new rule…",
              })
            }
          />
          <button
            type="button"
            onClick={commit}
            disabled={!draft.trim()}
            aria-label={t("controlPlane.policy.add", { defaultValue: "Add" })}
            className={cn(
              "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] border transition-colors",
              draft.trim()
                ? "border-[var(--accent)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]"
                : "border-[var(--border-subtle)] bg-[var(--panel)] text-[var(--text-quaternary)]",
            )}
          >
            <Plus className="icon-sm" strokeWidth={1.75} aria-hidden />
          </button>
        </div>
      ) : null}
    </div>
  );
}
