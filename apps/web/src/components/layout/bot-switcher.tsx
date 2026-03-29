"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Bot, Check, ChevronDown, Search } from "lucide-react";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { ActionButton } from "@/components/ui/action-button";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  formatBotSelectionLabel,
  resolveBotSelection,
  toggleBotSelection,
} from "@/lib/bot-selection";
import { cn } from "@/lib/utils";

interface BotSwitcherProps {
  selectedBotIds?: string[];
  onSelectionChange?: (botIds: string[]) => void;
  activeBotId?: string;
  onBotChange?: (botId: string | undefined) => void;
  multiple?: boolean;
  showAll?: boolean;
  className?: string;
  fullWidth?: boolean;
  singleRow?: boolean;
  placeholder?: string;
  variant?: "field" | "action-button";
  menuPlacement?: "bottom-start" | "bottom-end" | "top-start" | "top-end";
}

export function BotSwitcher({
  selectedBotIds,
  onSelectionChange,
  activeBotId,
  onBotChange,
  multiple = false,
  showAll = true,
  className,
  fullWidth = false,
  placeholder,
  variant = "field",
  menuPlacement = "bottom-start",
}: BotSwitcherProps) {
  const { t } = useAppI18n();
  const { bots } = useBotCatalog();
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [panelPosition, setPanelPosition] = useState<{
    top: number;
    left: number;
    width: number;
    maxHeight: number;
  } | null>(null);
  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);

  const resolvedBotIds = useMemo(
    () =>
      multiple
        ? resolveBotSelection(selectedBotIds, availableBotIds)
        : activeBotId && availableBotIds.includes(activeBotId)
          ? [activeBotId]
          : [],
    [activeBotId, availableBotIds, multiple, selectedBotIds],
  );

  const selectedSet = useMemo(() => new Set(resolvedBotIds), [resolvedBotIds]);
  const selectedBots = useMemo(
    () => bots.filter((bot) => selectedSet.has(bot.id)),
    [bots, selectedSet],
  );
  const visibleBots = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return bots;

    return bots.filter((bot) =>
      `${bot.label} ${bot.id}`.toLowerCase().includes(query),
    );
  }, [bots, search]);
  const effectivePlaceholder = placeholder ?? t("botSwitcher.placeholder");

  const summaryLabel = multiple
    ? formatBotSelectionLabel(resolvedBotIds, bots)
    : activeBotId
      ? selectedBots[0]?.label ?? activeBotId
      : showAll
        ? t("botSwitcher.allBots")
        : effectivePlaceholder;

  const helperLabel = multiple
    ? resolvedBotIds.length === bots.length
      ? t("botSwitcher.botsVisible", { count: bots.length })
      : t("botSwitcher.botsSelectedOutOfTotal", {
          selected: resolvedBotIds.length,
          total: bots.length,
        })
    : activeBotId
      ? selectedBots[0]?.id ?? activeBotId
      : showAll
        ? t("botSwitcher.noBotFilter")
        : t("botSwitcher.selectOne");

  const previewPool = selectedBots.length > 0 ? selectedBots : bots;
  const previewBots = previewPool.slice(0, 3);
  const previewOverflowCount = Math.max(previewPool.length - previewBots.length, 0);
  const actionBot = selectedBots[0] ?? null;

  function closeMenu() {
    setOpen(false);
    setSearch("");
  }

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !panelRef.current?.contains(target)) {
        closeMenu();
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeMenu();
      }
    };

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !rootRef.current) return;

    const updatePosition = () => {
      if (!rootRef.current) return;

      const rect = rootRef.current.getBoundingClientRect();
      const viewportPadding = 12;
      const gap = 8;
      const width =
        variant === "action-button"
          ? Math.min(272, window.innerWidth - viewportPadding * 2)
          : Math.min(rect.width, window.innerWidth - viewportPadding * 2);

      const alignRight = menuPlacement.endsWith("end");
      const placeAbove = menuPlacement.startsWith("top");
      const left = alignRight
        ? Math.min(
            Math.max(rect.right - width, viewportPadding),
            window.innerWidth - viewportPadding - width,
          )
        : Math.min(
            Math.max(rect.left, viewportPadding),
            window.innerWidth - viewportPadding - width,
          );
      const top = placeAbove
        ? Math.max(viewportPadding, rect.top - gap)
        : Math.min(rect.bottom + gap, window.innerHeight - viewportPadding);
      const maxHeight = placeAbove
        ? Math.max(180, rect.top - viewportPadding - gap)
        : Math.max(180, window.innerHeight - rect.bottom - viewportPadding - gap);

      setPanelPosition({
        top,
        left,
        width,
        maxHeight,
      });
    };

    const frame = window.requestAnimationFrame(updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [menuPlacement, open, variant]);

  function handleSelectAll() {
    if (multiple) {
      onSelectionChange?.([]);
      return;
    }

    onBotChange?.(undefined);
    closeMenu();
  }

  function handleToggle(botId: string) {
    if (multiple) {
      onSelectionChange?.(
        toggleBotSelection(selectedBotIds, botId, availableBotIds),
      );
      return;
    }

    onBotChange?.(activeBotId === botId && showAll ? undefined : botId);
    closeMenu();
  }

  return (
    <div
      ref={rootRef}
      className={cn(
        "bot-switcher relative min-w-0",
        fullWidth && "w-full",
        className,
      )}
    >
      {variant === "action-button" ? (
        <ActionButton
          type="button"
          className={cn(
            "workspace-topbar__tool bot-switcher__action-trigger",
            open && "workspace-topbar__tool--active",
          )}
          onClick={() =>
            setOpen((current) => {
              if (current) {
                setSearch("");
              }
              return !current;
            })
          }
          aria-expanded={open}
          aria-haspopup="dialog"
          aria-label={multiple ? t("botSwitcher.ariaMultiple") : t("sessions.composer.selectBot")}
        >
          <span className="bot-switcher__action-value">
            <span className="bot-switcher__action-icon" aria-hidden="true">
              {actionBot ? (
                <BotAgentGlyph
                  botId={actionBot.id}
                  color={actionBot.color}
                  active
                  variant="list"
                  shape="swatch"
                  className="h-4 w-4"
                />
              ) : (
                <Bot className="h-4 w-4 text-[var(--text-primary)]" />
              )}
            </span>
            <span className="truncate">{summaryLabel}</span>
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 shrink-0 text-[var(--text-primary)] transition-transform duration-200",
              open && "rotate-180",
            )}
          />
        </ActionButton>
      ) : (
        <button
          type="button"
          onClick={() =>
            setOpen((current) => {
              if (current) {
                setSearch("");
              }
              return !current;
            })
          }
          className="field-shell flex min-h-[46px] w-full items-center justify-between gap-3 px-4 py-2.5 text-left"
          aria-expanded={open}
          aria-haspopup="dialog"
          aria-label={multiple ? t("botSwitcher.ariaMultiple") : t("botSwitcher.ariaSingle")}
        >
          <span className="flex min-w-0 items-center gap-3">
            <span className="flex shrink-0 items-center -space-x-2.5">
              {previewBots.map((bot) => (
                <span
                  key={bot.id}
                  className="relative z-[1] flex h-8 w-8 items-center justify-center rounded-full border border-[rgba(255,255,255,0.12)] bg-[rgba(10,10,10,0.98)] text-[var(--text-primary)] shadow-[0_8px_24px_rgba(0,0,0,0.28)]"
                >
                  <BotAgentGlyph
                    botId={bot.id}
                    color={bot.color}
                    active={selectedSet.has(bot.id)}
                    variant="list"
                    className="h-4 w-4"
                  />
                </span>
              ))}
              {previewOverflowCount > 0 ? (
                <span className="relative z-[1] flex h-8 w-8 items-center justify-center rounded-full border border-[rgba(255,255,255,0.12)] bg-[rgba(255,255,255,0.08)] text-[10px] font-semibold tracking-[-0.01em] text-[var(--text-secondary)] shadow-[0_8px_24px_rgba(0,0,0,0.24)]">
                  {previewOverflowCount}+
                </span>
              ) : null}
            </span>

            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-[var(--text-primary)]">
                {summaryLabel}
              </span>
              <span className="mt-0.5 block truncate text-[11px] text-[var(--text-quaternary)]">
                {helperLabel}
              </span>
            </span>
          </span>

          <span className="flex shrink-0 items-center gap-2">
            {multiple && resolvedBotIds.length !== bots.length ? (
              <span className="chip hidden sm:inline-flex">{resolvedBotIds.length}</span>
            ) : null}
            <ChevronDown
              className={cn(
                "h-4 w-4 text-[var(--text-quaternary)] transition-transform duration-200",
                open && "rotate-180",
              )}
            />
          </span>
        </button>
      )}

      {typeof document !== "undefined" && open
        ? createPortal(
            <div
              ref={panelRef}
              className="app-floating-panel bot-switcher__menu z-30 overflow-hidden rounded-[0.95rem]"
              role="dialog"
              aria-label={multiple ? t("botSwitcher.ariaMultiple") : t("botSwitcher.ariaSingle")}
              style={{
                position: "fixed",
                top: panelPosition?.top ?? 0,
                left: panelPosition?.left ?? 0,
                width: panelPosition?.width,
                maxHeight: panelPosition?.maxHeight,
                background:
                  variant === "action-button"
                    ? "linear-gradient(180deg, rgba(24, 24, 28, 0.14) 0%, rgba(10, 10, 12, 0.22) 100%), rgba(8, 8, 10, 0.06)"
                    : "linear-gradient(180deg, rgba(24, 24, 28, 0.16) 0%, rgba(10, 10, 12, 0.24) 100%), rgba(8, 8, 10, 0.08)",
                backdropFilter: "blur(52px) saturate(168%) brightness(1.08)",
                WebkitBackdropFilter:
                  "blur(52px) saturate(168%) brightness(1.08)",
                transform: menuPlacement.startsWith("top") ? "translateY(-100%)" : undefined,
                visibility: panelPosition ? "visible" : "hidden",
              }}
            >
              <div className="border-b border-[var(--border-subtle)] p-3">
                <label className="app-search">
                  <Search className="h-4 w-4 text-[var(--text-quaternary)]" />
                  <input
                    type="text"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder={t("botSwitcher.searchPlaceholder")}
                  />
                </label>
              </div>

              {showAll ? (
                <div className="border-b border-[var(--border-subtle)] p-2">
                  <button
                    type="button"
                    onClick={handleSelectAll}
                    className="flex w-full items-center justify-between gap-3 rounded-[0.8rem] px-3 py-2.5 text-left transition-colors hover:bg-[rgba(255,255,255,0.028)]"
                    aria-pressed={
                      multiple
                        ? resolvedBotIds.length === bots.length
                        : activeBotId === undefined
                    }
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      <span
                        className={cn(
                          "flex h-5 w-5 shrink-0 items-center justify-center rounded-[0.45rem] border text-[var(--text-primary)]",
                          (multiple
                            ? resolvedBotIds.length === bots.length
                            : activeBotId === undefined)
                            ? "border-[rgba(255,255,255,0.26)] bg-[rgba(255,255,255,0.12)]"
                            : "border-[var(--border-subtle)] bg-[rgba(255,255,255,0.03)]",
                        )}
                      >
                        {(multiple
                          ? resolvedBotIds.length === bots.length
                          : activeBotId === undefined) ? (
                          <Check className="h-3.5 w-3.5" />
                        ) : null}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-[var(--text-primary)]">
                          {t("botSwitcher.allBots")}
                        </span>
                        <span className="block text-[11px] text-[var(--text-quaternary)]">
                          {t("botSwitcher.botsVisible", { count: bots.length })}
                        </span>
                      </span>
                    </span>
                    <span className="text-[11px] text-[var(--text-quaternary)]">
                      {bots.length}
                    </span>
                  </button>
                </div>
              ) : null}

              <div
                className="overflow-y-auto p-2"
                style={{ maxHeight: panelPosition ? Math.max(140, panelPosition.maxHeight - 70) : 320 }}
              >
                {visibleBots.length > 0 ? (
                  visibleBots.map((bot) => {
                    const isActive = selectedSet.has(bot.id);

                    return (
                      <button
                        key={bot.id}
                        type="button"
                        onClick={() => handleToggle(bot.id)}
                        className="flex w-full items-center justify-between gap-3 rounded-[0.8rem] px-3 py-2.5 text-left transition-colors hover:bg-[rgba(255,255,255,0.028)]"
                        aria-pressed={isActive}
                      >
                        <span className="flex min-w-0 items-center gap-3">
                          <span
                            className={cn(
                              "flex h-5 w-5 shrink-0 items-center justify-center rounded-[0.45rem] border text-[var(--text-primary)]",
                              isActive
                                ? "border-[rgba(255,255,255,0.26)] bg-[rgba(255,255,255,0.12)]"
                                : "border-[var(--border-subtle)] bg-[rgba(255,255,255,0.03)]",
                            )}
                          >
                            {isActive ? <Check className="h-3.5 w-3.5" /> : null}
                          </span>

                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)]">
                            <BotAgentGlyph
                              botId={bot.id}
                              color={bot.color}
                              active={isActive}
                              variant="list"
                              className="h-4.5 w-4.5"
                            />
                          </span>

                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium text-[var(--text-primary)]">
                              {bot.label}
                            </span>
                            <span className="block truncate text-[11px] font-mono text-[var(--text-quaternary)]">
                              {bot.id}
                            </span>
                          </span>
                        </span>

                        {!multiple ? (
                          <span
                            className={cn(
                              "h-2.5 w-2.5 shrink-0 rounded-full",
                              isActive ? "opacity-100" : "opacity-0",
                            )}
                            style={{ backgroundColor: bot.color }}
                          />
                        ) : null}
                      </button>
                    );
                  })
                ) : (
                  <div className="px-3 py-6 text-center text-sm text-[var(--text-tertiary)]">
                    {t("botSwitcher.noResults")}
                  </div>
                )}
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
