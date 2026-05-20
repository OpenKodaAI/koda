"use client";

import { useId, useMemo, useState } from "react";
import { SessionRichText } from "@/components/sessions/session-rich-text";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useAutoGrowTextarea } from "@/hooks/use-auto-grow-textarea";
import { cn } from "@/lib/utils";
import { translate } from "@/lib/i18n";

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
  const editorId = useId();
  const textareaRef = useAutoGrowTextarea(value, { minHeight, maxHeight });
  const charCount = value.length;

  const resolvedPlaceholder =
    placeholder ??
    t("controlPlane.prompt.placeholder", undefined);

  const wordCount = useMemo(() => {
    if (!value.trim()) return 0;
    return value.trim().split(/\s+/).length;
  }, [value]);

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div
        className={cn(
          "relative flex flex-col rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)]",
          "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          "focus-within:border-[var(--accent)] focus-within:bg-[var(--panel)]",
          disabled && "opacity-70",
        )}
      >
        <div
          className="absolute right-2 top-2 z-10 inline-flex items-center gap-0.5 rounded-[6px] bg-[var(--panel-soft)] p-0.5 shadow-[0_1px_8px_rgba(0,0,0,0.16)]"
          role="tablist"
          aria-label={t("controlPlane.prompt.modeTabs", undefined)}
        >
          <button
            type="button"
            id={`${editorId}-preview-tab`}
            role="tab"
            onClick={() => setPreviewOpen(true)}
            disabled={disabled}
            aria-label={t("controlPlane.prompt.preview", undefined)}
            aria-selected={previewOpen}
            aria-controls={`${editorId}-preview-panel`}
            className={cn(
              "rounded-[5px] px-2.5 py-1 text-[11px] font-semibold leading-none text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)] disabled:pointer-events-none",
              previewOpen &&
                "bg-[var(--surface-hover)] text-[var(--text-primary)] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03)]",
            )}
          >
            {t("controlPlane.prompt.preview", undefined)}
          </button>
          <button
            type="button"
            id={`${editorId}-markdown-tab`}
            role="tab"
            onClick={() => setPreviewOpen(false)}
            disabled={disabled}
            aria-label={t("controlPlane.prompt.markdown", undefined)}
            aria-selected={!previewOpen}
            aria-controls={`${editorId}-markdown-panel`}
            className={cn(
              "rounded-[5px] px-2.5 py-1 text-[11px] font-semibold leading-none text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)] disabled:pointer-events-none",
              !previewOpen &&
                "bg-[var(--surface-hover)] text-[var(--text-primary)] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03)]",
            )}
          >
            {t("controlPlane.prompt.markdown", undefined)}
          </button>
        </div>

        {previewOpen ? (
          <div
            id={`${editorId}-preview-panel`}
            role="tabpanel"
            aria-labelledby={`${editorId}-preview-tab`}
            className="min-h-[120px] max-h-[480px] overflow-y-auto px-4 pb-3 pt-11 text-[0.875rem] leading-[1.6] text-[var(--text-primary)]"
            aria-label={t("controlPlane.prompt.preview", undefined)}
          >
            {value.trim() ? (
              <SessionRichText content={value} variant="assistant" />
            ) : (
              <p className="m-0 text-[var(--text-quaternary)]">{resolvedPlaceholder}</p>
            )}
          </div>
        ) : (
          <textarea
            id={`${editorId}-markdown-panel`}
            ref={textareaRef}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            disabled={disabled}
            placeholder={resolvedPlaceholder}
            spellCheck
            autoComplete="off"
            className={cn(
              "resize-none bg-transparent px-4 pb-3 pt-11 font-mono text-[0.8125rem] leading-[1.55]",
              "text-[var(--text-primary)] placeholder:text-[var(--text-quaternary)] outline-none",
            )}
            style={{ minHeight, maxHeight }}
          />
        )}
      </div>

      <div className="flex items-center justify-between gap-3 px-1 text-[0.6875rem] text-[var(--text-tertiary)]">
        <div className="min-w-0">{hint ? <span className="hidden sm:inline">{hint}</span> : null}</div>
        <span className="font-mono text-[var(--text-quaternary)]">
          {wordCount} · {charCount} {translate("generated.controlPlane.chars_cf66e897")}</span>
      </div>
    </div>
  );
}
