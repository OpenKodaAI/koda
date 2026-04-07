"use client";

import { useEffect, useRef } from "react";
import { ArrowUp, LoaderCircle } from "lucide-react";
import { BotSwitcher } from "@/components/layout/bot-switcher";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface SessionChatComposerProps {
  botId?: string | null;
  onBotChange?: (botId: string | undefined) => void;
  lockedBot?: boolean;
  value: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  disabled?: boolean;
  submitting?: boolean;
  helperText?: string;
  error?: string | null;
  placeholder?: string;
}

const MAX_TEXTAREA_HEIGHT = 240;

export function SessionChatComposer({
  botId,
  onBotChange,
  lockedBot = false,
  value,
  onChange,
  onSubmit,
  disabled = false,
  submitting = false,
  helperText,
  error,
  placeholder,
}: SessionChatComposerProps) {
  const { t } = useAppI18n();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const canSubmit = Boolean(onSubmit && value.trim() && !disabled && !submitting);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [value]);

  return (
    <div className="px-4 py-4 sm:px-6">
      <div className="mx-auto max-w-[52rem]">
        <div className="rounded-[1.5rem] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-4 py-4">
          {!lockedBot || submitting ? (
            <div className="mb-3 flex items-center justify-between gap-3">
              {!lockedBot ? (
              <BotSwitcher
                activeBotId={botId ?? undefined}
                onBotChange={onBotChange}
                showAll={false}
                placeholder={t("sessions.composer.selectBot", {
                  defaultValue: "Select bot",
                })}
                variant="session-chip"
                menuPlacement="bottom-start"
                className="w-full max-w-[13.5rem]"
              />
              ) : <span />}
              {submitting ? (
                <span className="truncate text-[11px] font-medium text-[var(--text-tertiary)]">
                  {t("sessions.composer.sendingMessage")}
                </span>
              ) : null}
            </div>
          ) : null}

          <div className="flex items-end gap-3">
            <textarea
              ref={textareaRef}
              rows={1}
              value={value}
              onChange={(event) => onChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (canSubmit) {
                    onSubmit?.();
                  }
                }
              }}
              disabled={disabled}
              placeholder={
                placeholder ??
                (disabled
                  ? t("sessions.composer.disabledPlaceholder")
                  : t("sessions.composer.enabledPlaceholder"))
              }
              className={cn(
                "max-h-[240px] min-h-[54px] flex-1 resize-none bg-transparent px-1 py-2 text-[15px] leading-7 text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]",
                disabled && "cursor-not-allowed opacity-60"
              )}
            />

            <button
              type="button"
              onClick={() => onSubmit?.()}
              disabled={!canSubmit}
              className={cn(
                "button-shell button-shell--icon h-11 w-11 shrink-0 rounded-[1rem] transition-all",
                canSubmit
                  ? "button-shell--primary"
                  : "button-shell--secondary text-[var(--text-quaternary)]"
              )}
              aria-label={t("sessions.composer.send")}
            >
              {submitting ? <LoaderCircle className="h-4.5 w-4.5 animate-spin" /> : <ArrowUp className="h-4.5 w-4.5" />}
            </button>
          </div>

          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[12px]">
            <p className={cn(error ? "text-[var(--tone-danger-dot)]" : "text-[var(--text-tertiary)]")}>
              {error || helperText || t("sessions.composer.syncHint")}
            </p>
            <p className="text-[var(--text-quaternary)]">{t("sessions.composer.enterToSend")}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
