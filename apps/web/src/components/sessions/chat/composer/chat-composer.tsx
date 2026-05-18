"use client";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import {
  ComposerInput,
  type ComposerInputHandle,
} from "./composer-input";
import {
  ComposerMentionBadges,
  type TrackedMention,
} from "./composer-mention-badges";
import { ComposerToolbar } from "./composer-toolbar";
import { ComposerSlashMenuContent } from "./composer-slash-menu";
import { ComposerMentionMenuContent } from "./composer-mention-menu";
import {
  applyReplacement,
  clearTrigger,
} from "./trigger-detection";
import {
  useComposerTriggers,
  type ComposerTriggerSource,
} from "./use-composer-triggers";
import type { ChatCommand } from "@/lib/contracts/chat-commands";
import type { Mention } from "@/lib/contracts/sessions";
import type { MentionCandidate } from "@/hooks/use-mention-suggestions";

export interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  agentId?: string | null;
  onAgentChange?: (agentId: string | undefined) => void;
  lockedAgent?: boolean;
  modelLabel?: string | null;
  disabled?: boolean;
  busy?: boolean;
  placeholder?: string;
  helper?: string | null;
  error?: string | null;
  /**
   * Called when the user picks a `/` command whose action is `execute` or
   * `remote`. The composer clears the `/foo` trigger token before the
   * callback fires; the parent decides what the action does (open drawer,
   * trigger mutation, etc.).
   */
  onCommandExecute?: (command: ChatCommand) => void;
  /**
   * Notified whenever the active set of mentions changes. Parent should
   * stash the latest array and include it in the send-message payload.
   */
  onMentionsChange?: (mentions: Mention[]) => void;
}

export function ChatComposer({
  value,
  onChange,
  onSubmit,
  agentId,
  onAgentChange,
  lockedAgent = false,
  modelLabel,
  disabled = false,
  busy = false,
  placeholder,
  helper,
  error,
  onCommandExecute,
  onMentionsChange,
}: ChatComposerProps) {
  const { t } = useAppI18n();
  const inputRef = useRef<ComposerInputHandle | null>(null);
  const canSubmit = Boolean(value.trim()) && !disabled && !busy;
  const baseId = useId();
  const slashListboxId = `${baseId}-slash`;
  const slashIdPrefix = `${baseId}-slash-opt`;
  const mentionListboxId = `${baseId}-mention`;
  const mentionIdPrefix = `${baseId}-mention-opt`;

  const triggerSource = useMemo<ComposerTriggerSource>(
    () => ({
      getCaretIndex: () => inputRef.current?.selectionStart ?? null,
      getDomNode: () => inputRef.current?.domNode ?? null,
    }),
    [],
  );
  const triggers = useComposerTriggers(value, triggerSource);
  const [activeIndex, setActiveIndex] = useState(0);
  const slashItemsRef = useRef<ChatCommand[]>([]);
  const mentionItemsRef = useRef<MentionCandidate[]>([]);
  const [mentionBadges, setMentionBadges] = useState<TrackedMention[]>([]);

  const isSlashOpen = triggers.activeMenu === "slash";
  const isMentionOpen = triggers.activeMenu === "mention";

  // Notify parent every time the mentions array changes.
  useEffect(() => {
    onMentionsChange?.(
      mentionBadges.map(({ kind, slug }) => ({ kind, slug })),
    );
  }, [mentionBadges, onMentionsChange]);

  const setCaretAndValue = useCallback(
    (next: { text: string; caret: number }) => {
      onChange(next.text);
      requestAnimationFrame(() => {
        const node = inputRef.current;
        if (!node) return;
        node.focus();
        node.setSelectionRange(next.caret);
        triggers.syncFromTextarea();
      });
    },
    [onChange, triggers],
  );

  const handleSlashSelect = useCallback(
    (command: ChatCommand) => {
      if (!triggers.slashTrigger) return;
      const action = command.action;
      if (action.kind === "insert") {
        const next = applyReplacement(value, triggers.slashTrigger, action.template);
        setCaretAndValue(next);
        return;
      }
      const next = clearTrigger(value, triggers.slashTrigger);
      setCaretAndValue(next);
      triggers.closeActive();
      onCommandExecute?.(command);
    },
    [onCommandExecute, setCaretAndValue, triggers, value],
  );

  const handleMentionSelect = useCallback(
    (candidate: MentionCandidate) => {
      if (!triggers.mentionTrigger) return;
      // Strip the @-trigger token from the textarea — the badge row above is
      // the only visible representation of the mention.
      const next = clearTrigger(value, triggers.mentionTrigger);
      setMentionBadges((current) => {
        if (
          current.some(
            (m) => m.kind === candidate.kind && m.slug === candidate.slug,
          )
        ) {
          return current;
        }
        return [
          ...current,
          {
            kind: candidate.kind,
            slug: candidate.slug,
            label: candidate.label,
          },
        ];
      });
      triggers.closeActive();
      setCaretAndValue(next);
    },
    [setCaretAndValue, triggers, value],
  );

  const handleSlashQueryChange = useCallback(
    (nextQuery: string) => {
      if (!triggers.slashTrigger) return;
      const replacement = `/${nextQuery}`;
      const next = applyReplacement(value, triggers.slashTrigger, replacement);
      setCaretAndValue(next);
    },
    [setCaretAndValue, triggers, value],
  );

  const handleMentionQueryChange = useCallback(
    (nextQuery: string) => {
      if (!triggers.mentionTrigger) return;
      const replacement = `@${nextQuery}`;
      const next = applyReplacement(value, triggers.mentionTrigger, replacement);
      setCaretAndValue(next);
    },
    [setCaretAndValue, triggers, value],
  );

  const handleMentionRemove = useCallback((mention: TrackedMention) => {
    setMentionBadges((current) =>
      current.filter(
        (m) => !(m.kind === mention.kind && m.slug === mention.slug),
      ),
    );
  }, []);

  const handleSubmit = useCallback(
    (event?: FormEvent) => {
      event?.preventDefault();
      if (!canSubmit) return;
      if (isSlashOpen || isMentionOpen) return;
      onSubmit();
    },
    [canSubmit, isMentionOpen, isSlashOpen, onSubmit],
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (isSlashOpen || isMentionOpen) {
        const items: Array<unknown> = isSlashOpen
          ? slashItemsRef.current
          : mentionItemsRef.current;
        if (event.key === "ArrowDown") {
          event.preventDefault();
          if (items.length === 0) return;
          setActiveIndex((idx) => (idx + 1) % items.length);
          return;
        }
        if (event.key === "ArrowUp") {
          event.preventDefault();
          if (items.length === 0) return;
          setActiveIndex((idx) => (idx - 1 + items.length) % items.length);
          return;
        }
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          if (isSlashOpen) {
            const cmd = slashItemsRef.current[activeIndex];
            if (cmd) handleSlashSelect(cmd);
          } else {
            const candidate = mentionItemsRef.current[activeIndex];
            if (candidate) handleMentionSelect(candidate);
          }
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          triggers.dismissActive();
          return;
        }
      }

      if (event.key !== "Enter") return;
      if (event.shiftKey) return;
      const submitModifier = event.metaKey || event.ctrlKey;
      if (!submitModifier) return;
      event.preventDefault();
      handleSubmit();
    },
    [
      activeIndex,
      handleMentionSelect,
      handleSlashSelect,
      handleSubmit,
      isMentionOpen,
      isSlashOpen,
      triggers,
    ],
  );

  const activeTriggerStart = isSlashOpen
    ? triggers.slashTrigger?.start ?? null
    : isMentionOpen
      ? triggers.mentionTrigger?.start ?? null
      : null;
  useEffect(() => {
    if (activeTriggerStart !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveIndex(0);
    }
  }, [activeTriggerStart]);

  const handleSlashItemsChange = useCallback((items: ChatCommand[]) => {
    slashItemsRef.current = items;
    if (items.length === 0) {
      setActiveIndex(0);
    } else {
      setActiveIndex((idx) => Math.min(idx, items.length - 1));
    }
  }, []);

  const handleMentionItemsChange = useCallback((items: MentionCandidate[]) => {
    mentionItemsRef.current = items;
    if (items.length === 0) {
      setActiveIndex(0);
    } else {
      setActiveIndex((idx) => Math.min(idx, items.length - 1));
    }
  }, []);

  const resolvedPlaceholder =
    placeholder ?? t("chat.composer.placeholder", { defaultValue: "Send a message…" });

  const activeItemId = isSlashOpen
    ? `${slashIdPrefix}-${activeIndex}`
    : isMentionOpen
      ? `${mentionIdPrefix}-${activeIndex}`
      : undefined;
  const activeListboxId = isSlashOpen
    ? slashListboxId
    : isMentionOpen
      ? mentionListboxId
      : undefined;
  const popoverOpen = isSlashOpen || isMentionOpen;

  return (
    <form
      onSubmit={handleSubmit}
      className="mx-auto w-full max-w-[760px] px-6 pb-5 pt-2 lg:px-8"
      aria-label={t("chat.composer.placeholder", { defaultValue: "Send a message…" })}
    >
      <Popover
        open={popoverOpen}
        onOpenChange={(next) => {
          if (!next) triggers.closeActive();
        }}
      >
        <PopoverAnchor asChild>
          <div
            className={cn(
              "flex flex-col rounded-[var(--radius-input)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] shadow-[var(--shadow-xs)]",
              "transition-[border-color,background-color,box-shadow] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
              "focus-within:border-[color:var(--border-strong)] focus-within:bg-[var(--panel)] focus-within:shadow-[0_0_0_1px_var(--border-strong)]",
              disabled && "opacity-70",
            )}
            role="combobox"
            aria-expanded={popoverOpen}
            aria-haspopup="listbox"
            aria-controls={activeListboxId}
          >
            <ComposerMentionBadges
              mentions={mentionBadges}
              onRemove={handleMentionRemove}
            />
            <ComposerInput
              ref={inputRef}
              value={value}
              onChange={onChange}
              onKeyDown={handleKeyDown}
              onSubmit={handleSubmit}
              disabled={disabled}
              busy={busy}
              canSubmit={canSubmit}
              placeholder={resolvedPlaceholder}
              activeDescendantId={activeItemId}
              onSelect={triggers.syncFromTextarea}
            />
            <ComposerToolbar
              agentId={agentId}
              onAgentChange={onAgentChange}
              lockedAgent={lockedAgent}
              modelLabel={modelLabel}
            />
          </div>
        </PopoverAnchor>
        <PopoverContent
          align="start"
          side="top"
          sideOffset={8}
          className="composer-suggestions-panel w-[420px] max-w-[calc(100vw-3rem)] p-0"
          onOpenAutoFocus={(event) => event.preventDefault()}
          onCloseAutoFocus={(event) => event.preventDefault()}
          onPointerDownOutside={(event) => {
            const target = event.target as HTMLElement | null;
            if (target?.closest('textarea')) {
              event.preventDefault();
            }
          }}
        >
          {isSlashOpen ? (
            <ComposerSlashMenuContent
              query={triggers.slashTrigger?.query ?? ""}
              onQueryChange={handleSlashQueryChange}
              agentId={agentId}
              activeIndex={activeIndex}
              onActiveIndex={setActiveIndex}
              onItemsChange={handleSlashItemsChange}
              onSelect={handleSlashSelect}
              listboxId={slashListboxId}
              idPrefix={slashIdPrefix}
            />
          ) : null}
          {isMentionOpen ? (
            <ComposerMentionMenuContent
              query={triggers.mentionTrigger?.query ?? ""}
              onQueryChange={handleMentionQueryChange}
              agentId={agentId}
              activeIndex={activeIndex}
              onActiveIndex={setActiveIndex}
              onItemsChange={handleMentionItemsChange}
              onSelect={handleMentionSelect}
              listboxId={mentionListboxId}
              idPrefix={mentionIdPrefix}
            />
          ) : null}
        </PopoverContent>
      </Popover>

      {error ? (
        <p className="mt-2 px-1 text-[0.75rem] text-[var(--tone-danger-dot)]">{error}</p>
      ) : helper ? (
        <p className="mt-2 px-1 text-[0.75rem] text-[var(--text-tertiary)]">{helper}</p>
      ) : null}
    </form>
  );
}
