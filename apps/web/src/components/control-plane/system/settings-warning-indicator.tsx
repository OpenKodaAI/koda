"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import { ActionButton } from "@/components/ui/action-button";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useSystemSettings } from "@/hooks/use-system-settings";
import { cn } from "@/lib/utils";

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function SettingsWarningIndicator({
  compact = false,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  const { localWarnings } = useSystemSettings();
  const { tl } = useAppI18n();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [panelPosition, setPanelPosition] = useState<{
    top?: number;
    bottom?: number;
    left: number;
    width: number;
    maxHeight: number;
    placement: "top" | "bottom";
  } | null>(null);

  const countLabel = useMemo(() => {
    if (localWarnings.length === 1) {
      return compact ? "1" : tl("1 aviso");
    }

    return compact ? String(localWarnings.length) : tl("{{count}} avisos", { count: localWarnings.length });
  }, [compact, localWarnings.length, tl]);

  const title = useMemo(() => {
    return localWarnings.length === 1
      ? tl("1 aviso de configuração")
      : tl("{{count}} avisos de configuração", { count: localWarnings.length });
  }, [localWarnings.length, tl]);

  const updatePanelPosition = useCallback(() => {
    if (!triggerRef.current || !panelRef.current) {
      return;
    }

    const triggerRect = triggerRef.current.getBoundingClientRect();
    const viewportPadding = 12;
    const gap = 10;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const width = Math.min(compact ? 320 : 360, viewportWidth - viewportPadding * 2);
    const desiredMaxHeight = Math.min(520, viewportHeight - viewportPadding * 2);

    const availableAbove = triggerRect.top - viewportPadding - gap;
    const availableBelow = viewportHeight - triggerRect.bottom - viewportPadding - gap;
    const minimumComfortHeight = compact ? 180 : 220;
    const placeAbove = !compact;
    const maxHeight = placeAbove
      ? Math.max(140, Math.min(desiredMaxHeight, availableAbove))
      : Math.max(minimumComfortHeight, Math.min(desiredMaxHeight, availableBelow));
    const left = compact
      ? clamp(triggerRect.right - width, viewportPadding, viewportWidth - viewportPadding - width)
      : clamp(triggerRect.left, viewportPadding, viewportWidth - viewportPadding - width);

    setPanelPosition({
      top: placeAbove ? undefined : Math.max(viewportPadding, triggerRect.bottom + gap),
      bottom: placeAbove ? Math.max(viewportPadding, viewportHeight - triggerRect.top + gap) : undefined,
      left,
      width,
      maxHeight,
      placement: placeAbove ? "top" : "bottom",
    });
  }, [compact]);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !panelRef.current?.contains(target)) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;

    const frame = window.requestAnimationFrame(updatePanelPosition);
    window.addEventListener("resize", updatePanelPosition);
    window.addEventListener("scroll", updatePanelPosition, true);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePanelPosition);
      window.removeEventListener("scroll", updatePanelPosition, true);
    };
  }, [open, updatePanelPosition]);

  if (!localWarnings.length) return null;
  if (typeof document === "undefined") return null;

  return (
    <div
      ref={rootRef}
      className={cn(
        "settings-warning-anchor flex",
        compact ? "justify-end" : "w-full",
        className,
      )}
    >
      <ActionButton
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={title}
        leading={<AlertTriangle className="h-3.5 w-3.5 shrink-0" />}
        className={cn(
          "workspace-topbar__tool settings-warning-indicator",
          compact ? "settings-warning-indicator--compact" : "w-full justify-start",
          open && "workspace-topbar__tool--active settings-warning-indicator--active",
        )}
      >
        {countLabel}
      </ActionButton>

      {createPortal(
        <AnimatePresence initial={false}>
          {open ? (
            <motion.div
              ref={panelRef}
              initial={{
                opacity: 0,
                y: panelPosition?.placement === "top" ? 8 : -8,
                scale: 0.985,
              }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{
                opacity: 0,
                y: panelPosition?.placement === "top" ? 6 : -6,
                scale: 0.985,
              }}
              transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
              role="dialog"
              aria-label={title}
              className="app-floating-panel settings-warning-popover fixed z-[90] flex flex-col overflow-hidden rounded-[0.95rem] border border-[rgba(214,164,64,0.18)]"
              style={{
                position: "fixed",
                top: panelPosition?.top,
                bottom: panelPosition?.bottom,
                left: panelPosition?.left ?? 0,
                width: panelPosition?.width,
                maxHeight: panelPosition?.maxHeight,
                visibility: panelPosition ? "visible" : "hidden",
                backdropFilter: "blur(52px) saturate(172%) brightness(1.08)",
                WebkitBackdropFilter: "blur(52px) saturate(172%) brightness(1.08)",
              }}
            >
              <div className="relative z-[1] border-b border-[rgba(255,255,255,0.06)] px-4 py-3">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[0.75rem] border border-[rgba(214,164,64,0.24)] bg-[rgba(166,117,25,0.12)] text-[var(--tone-warning-dot)]">
                    <AlertTriangle className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-[var(--text-primary)]">{title}</p>
                    <p className="text-xs text-[var(--text-quaternary)]">
                      {tl("Revise estes pontos antes de publicar configurações globais.")}
                    </p>
                  </div>
                </div>
              </div>

              <div className="relative z-[1] min-h-0 flex-1 overflow-y-auto px-3 py-3">
                <ul className="space-y-1.5">
                  {localWarnings.map((warning, index) => (
                    <li
                      key={`${warning}-${index}`}
                      className="rounded-[0.8rem] border border-[rgba(255,255,255,0.05)] bg-[rgba(255,255,255,0.024)] px-3 py-2.5"
                    >
                      <div className="flex items-start gap-2.5">
                        <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--tone-warning-dot)]" />
                        <span className="text-sm leading-6 text-[var(--text-secondary)]">
                          {tl(warning)}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>,
        document.body,
      )}
    </div>
  );
}
