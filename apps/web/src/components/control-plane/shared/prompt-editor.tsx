"use client";

import { useMemo, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { SessionRichText } from "@/components/sessions/session-rich-text";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAutoGrowTextarea } from "@/hooks/use-auto-grow-textarea";
import { cn } from "@/lib/utils";

interface PromptEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  minHeight?: number;
  maxHeight?: number;
  disabled?: boolean;
  hint?: string;
  className?: string;
}

export function PromptEditor({
  value,
  onChange,
  placeholder,
  minHeight = 120,
  maxHeight = 480,
  disabled = false,
  hint,
  className,
}: PromptEditorProps) {
  const { t } = useAppI18n();
  const [previewOpen, setPreviewOpen] = useState(false);
  const textareaRef = useAutoGrowTextarea(value, { minHeight, maxHeight });
  const charCount = value.length;

  const resolvedPlaceholder =
    placeholder ??
    t("controlPlane.prompt.placeholder", {
      defaultValue: "Write the markdown instructions…",
    });

  const wordCount = useMemo(() => {
    if (!value.trim()) return 0;
    return value.trim().split(/\s+/).length;
  }, [value]);

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div
        className={cn(
          "flex flex-col rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)]",
          "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          "focus-within:border-[var(--accent)] focus-within:bg-[var(--panel)]",
          disabled && "opacity-70",
        )}
      >
        {previewOpen ? (
          <div
            className="min-h-[120px] max-h-[480px] overflow-y-auto px-4 py-3 text-[0.875rem] leading-[1.6] text-[var(--text-primary)]"
            aria-label={t("controlPlane.prompt.preview", { defaultValue: "Preview" })}
          >
            {value.trim() ? (
              <SessionRichText content={value} variant="assistant" />
            ) : (
              <p className="m-0 text-[var(--text-quaternary)]">{resolvedPlaceholder}</p>
            )}
          </div>
        ) : (
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            disabled={disabled}
            placeholder={resolvedPlaceholder}
            spellCheck
            autoComplete="off"
            className={cn(
              "resize-none bg-transparent px-4 py-3 font-mono text-[0.8125rem] leading-[1.55]",
              "text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)] outline-none",
            )}
            style={{ minHeight, maxHeight }}
          />
        )}
      </div>

      <div className="flex items-center justify-between gap-3 px-1 text-[0.6875rem] text-[var(--text-tertiary)]">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPreviewOpen((value) => !value)}
            className="inline-flex items-center gap-1 rounded-[var(--radius-panel-sm)] px-1.5 py-0.5 transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-secondary)]"
          >
            {previewOpen ? (
              <EyeOff className="icon-xs" strokeWidth={1.75} aria-hidden />
            ) : (
              <Eye className="icon-xs" strokeWidth={1.75} aria-hidden />
            )}
            <span>
              {previewOpen
                ? t("controlPlane.prompt.edit", { defaultValue: "Edit" })
                : t("controlPlane.prompt.preview", { defaultValue: "Preview" })}
            </span>
          </button>
          {hint ? <span className="hidden sm:inline">· {hint}</span> : null}
        </div>
        <span className="font-mono text-[var(--text-quaternary)]">
          {wordCount} · {charCount} chars
        </span>
      </div>
    </div>
  );
}
