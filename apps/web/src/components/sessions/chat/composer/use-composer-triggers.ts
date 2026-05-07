"use client";

import { useCallback, useEffect, useMemo, useState, type RefObject } from "react";
import {
  detectTrigger,
  type TriggerMatch,
} from "@/components/sessions/chat/composer/trigger-detection";

export type ComposerMenuKind = "slash" | "mention";

export interface ComposerTriggersState {
  caretPos: number | null;
  slashTrigger: TriggerMatch | null;
  mentionTrigger: TriggerMatch | null;
  /** The currently OPEN menu after dismissal handling. */
  activeMenu: ComposerMenuKind | null;
  /** Mark the active trigger as dismissed (Esc). Re-opens when caret leaves the range. */
  dismissActive: () => void;
  /** Programmatic close (e.g. after selection). Same semantics as dismiss. */
  closeActive: () => void;
  /** Sync caret from a textarea event handler. */
  syncFromTextarea: () => void;
}

function rangeEqual(a: TriggerMatch | null, b: TriggerMatch | null) {
  if (!a || !b) return false;
  return a.start === b.start;
}

/**
 * Tracks caret position inside `textareaRef` and derives whether the slash
 * or mention menu should be open based on the value and the current caret.
 *
 * Dismissals (Esc) are remembered until the caret leaves the dismissed range,
 * so retyping after dismiss does not re-open the same menu instantly.
 */
export function useComposerTriggers(
  value: string,
  textareaRef: RefObject<HTMLTextAreaElement | null>,
): ComposerTriggersState {
  const [caretPos, setCaretPos] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState<TriggerMatch | null>(null);

  const syncFromTextarea = useCallback(() => {
    const node = textareaRef.current;
    if (!node) {
      setCaretPos(null);
      return;
    }
    const next = node.selectionStart ?? node.value.length;
    setCaretPos((prev) => (prev === next ? prev : next));
  }, [textareaRef]);

  // Listen to selectionchange so caret updates from arrow keys / mouse clicks
  // without depending on synthetic React events.
  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    const handleSelectionChange = () => {
      if (document.activeElement === node) {
        syncFromTextarea();
      }
    };
    document.addEventListener("selectionchange", handleSelectionChange);
    return () => {
      document.removeEventListener("selectionchange", handleSelectionChange);
    };
  }, [syncFromTextarea, textareaRef]);

  // Re-sync caret on every value change in case React's batching kept the
  // selectionStart unchanged but the trigger boundary moved. The hook
  // intentionally mirrors textarea state into React state inside an effect,
  // which is the canonical valid case for the rule (synchronizing with an
  // external system that does not emit events for every state we care about).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    syncFromTextarea();
  }, [syncFromTextarea, value]);

  const slashTrigger = useMemo<TriggerMatch | null>(() => {
    if (caretPos === null) return null;
    return detectTrigger(value, caretPos, "/");
  }, [caretPos, value]);

  const mentionTrigger = useMemo<TriggerMatch | null>(() => {
    if (caretPos === null) return null;
    return detectTrigger(value, caretPos, "@");
  }, [caretPos, value]);

  // Reset dismissal when the active trigger changes range or disappears.
  // Synchronizing derived state into React state — the same canonical
  // exception as the caret-sync effect above.
  useEffect(() => {
    if (!dismissed) return;
    if (!rangeEqual(slashTrigger, dismissed) && !rangeEqual(mentionTrigger, dismissed)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDismissed(null);
    }
  }, [dismissed, slashTrigger, mentionTrigger]);

  const dismissActive = useCallback(() => {
    if (slashTrigger) {
      setDismissed(slashTrigger);
      return;
    }
    if (mentionTrigger) {
      setDismissed(mentionTrigger);
    }
  }, [mentionTrigger, slashTrigger]);

  const activeMenu = useMemo<ComposerMenuKind | null>(() => {
    if (slashTrigger && !rangeEqual(slashTrigger, dismissed)) return "slash";
    if (mentionTrigger && !rangeEqual(mentionTrigger, dismissed)) return "mention";
    return null;
  }, [dismissed, mentionTrigger, slashTrigger]);

  return {
    caretPos,
    slashTrigger,
    mentionTrigger,
    activeMenu,
    dismissActive,
    closeActive: dismissActive,
    syncFromTextarea,
  };
}
