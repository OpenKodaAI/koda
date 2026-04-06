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
  variant?: "field" | "action-button" | "session-chip";
  menuPlacement?: "bottom-start" | "bottom-end" | "top-start" | "top-end";
  showSearch?: boolean;
  disabled?: boolean;
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
  singleRow = false,
  placeholder,
  variant = "field",
  menuPlacement = "bottom-start",
  showSearch,
  disabled = false,
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
    placeAbove: boolean;
  } | null>(null);
  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);
  const resolvedActiveBotId = useMemo(() => {
    if (!activeBotId) return undefined;
    return availableBotIds.find((botId) => botId.toLowerCase() === activeBotId.toLowerCase()) ?? undefined;
  }, [activeBotId, availableBotIds]);

  const resolvedBotIds = useMemo(
    () =>
      multiple
        ? resolveBotSelection(selectedBotIds, availableBotIds)
        : resolvedActiveBotId
          ? [resolvedActiveBotId]
          : [],
    [availableBotIds, multiple, resolvedActiveBotId, selectedBotIds],
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
  const shouldShowSearch = showSearch ?? bots.length > 7;

  const summaryLabel = multiple
    ? formatBotSelectionLabel(resolvedBotIds, bots)
    : resolvedActiveBotId
      ? selectedBots[0]?.label ?? resolvedActiveBotId
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
    : resolvedActiveBotId
      ? selectedBots[0]?.id ?? resolvedActiveBotId
      : showAll
        ? t("botSwitcher.noBotFilter")
        : t("botSwitcher.selectOne");

  const previewPool = selectedBots.length > 0 ? selectedBots : bots;
  const previewBots = previewPool.slice(0, 3);
  const previewOverflowCount = Math.max(previewPool.length - previewBots.length, 0);
  const actionBot = selectedBots[0] ?? null;
  const chipBot = selectedBots[0] ?? null;

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
      const preferredPlaceAbove = menuPlacement.startsWith("top");
      const spaceAbove = rect.top - viewportPadding - gap;
      const spaceBelow = window.innerHeight - rect.bottom - viewportPadding - gap;
      const placeAbove = preferredPlaceAbove
        ? !(spaceAbove < 220 && spaceBelow > spaceAbove)
        : spaceBelow < 260 && spaceAbove > spaceBelow;
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
        ? Math.max(180, spaceAbove)
        : Math.max(180, spaceBelow);

      setPanelPosition({
        top,
        left,
        width,
        maxHeight,
        placeAbove,
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

    onBotChange?.(resolvedActiveBotId === botId && showAll ? undefined : botId);
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
            disabled && "pointer-events-none opacity-70",
          )}
          onClick={() => {
            if (disabled) return;
            setOpen((current) => {
              if (current) {
                setSearch("");
              }
              return !current;
            });
          }}
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
          {!disabled && (
            <ChevronDown
              className={cn(
                "h-4 w-4 shrink-0 text-[var(--text-primary)] transition-transform duration-200",
                open && "rotate-180",
              )}
            />
          )}
        </ActionButton>
      ) : variant === "session-chip" ? (
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
          className={cn(
            "session-bot-chip flex min-h-[2.2rem] w-auto min-w-[10.75rem] max-w-full items-center justify-between gap-2 rounded-[0.95rem] border px-2.5 py-1.5 text-left transition-colors",
            disabled && "pointer-events-none opacity-70",
          )}
          aria-expanded={open}
          aria-haspopup="dialog"
          aria-label={multiple ? t("botSwitcher.ariaMultiple") : t("botSwitcher.ariaSingle")}
        >
          <span className="flex min-w-0 items-center gap-2.5">
            {chipBot ? (
              <BotAgentGlyph
                botId={chipBot.id}
                color={chipBot.color}
                variant="list"
                shape="swatch"
                className="h-7 w-7 shrink-0 bot-swatch--animated"
              />
            ) : (
              <span className="session-bot-chip__icon">
                <Bot className="h-4 w-4" />
              </span>
            )}

            <span className="min-w-0 truncate text-[12.5px] font-medium tracking-[-0.01em] text-[var(--text-primary)]">
              {summaryLabel}
            </span>
          </span>

          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 shrink-0 text-[var(--text-quaternary)] transition-transform duration-200",
              open && "rotate-180",
            )}
          />
        </button>
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
          className={cn(
            "field-shell flex w-full items-center justify-between gap-3 text-left",
            singleRow ? "min-h-[42px] px-3.5 py-2" : "min-h-[46px] px-4 py-2.5",
          )}
          aria-expanded={open}
          aria-haspopup="dialog"
          aria-label={multiple ? t("botSwitcher.ariaMultiple") : t("botSwitcher.ariaSingle")}
        >
          <span className="flex min-w-0 items-center gap-3">
            <span className="flex shrink-0 items-center -space-x-1.5">
              {previewBots.map((bot) => (
                <BotAgentGlyph
                  key={bot.id}
                  botId={bot.id}
                  color={bot.color}
                  variant="list"
                  shape="swatch"
                  className="bot-switcher__preview-glyph h-8 w-8 bot-swatch--animated"
                />
              ))}
              {previewOverflowCount > 0 ? (
                <span className="relative z-[1] flex h-8 w-8 items-center justify-center rounded-[0.72rem] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-[10px] font-semibold tracking-[-0.01em] text-[var(--text-secondary)]">
                  {previewOverflowCount}+
                </span>
              ) : null}
            </span>

            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-[var(--text-primary)]">
                {summaryLabel}
              </span>
              {!singleRow ? (
                <span className="mt-0.5 block truncate text-[11px] text-[var(--text-quaternary)]">
                  {helperLabel}
                </span>
              ) : null}
            </span>
          </span>

          <span className="flex shrink-0 items-center gap-2">
            {!singleRow && multiple && resolvedBotIds.length !== bots.length ? (
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
                transform: panelPosition?.placeAbove ? "translateY(-100%)" : undefined,
                visibility: panelPosition ? "visible" : "hidden",
              }}
            >
              {shouldShowSearch ? (
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
              ) : null}

              {showAll ? (
                <div className="border-b border-[var(--border-subtle)] p-2">
                  <button
                    type="button"
                    onClick={handleSelectAll}
                    className={cn(
                      "flex w-full items-center justify-between gap-3 rounded-[0.8rem] px-3 py-2.5 text-left transition-colors hover:bg-[var(--surface-hover)]",
                      variant === "session-chip" && "bot-switcher__menu-row bot-switcher__menu-row--session",
                    )}
                    aria-pressed={
                      multiple
                        ? resolvedBotIds.length === bots.length
                        : activeBotId === undefined
                    }
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      {variant === "session-chip" ? (
                        <span className="session-bot-chip__icon">
                          <Bot className="h-4 w-4" />
                        </span>
                      ) : (
                        <span
                          className={cn(
                            "flex h-5 w-5 shrink-0 items-center justify-center rounded-[0.45rem] border text-[var(--text-primary)]",
                            (multiple
                              ? resolvedBotIds.length === bots.length
                              : activeBotId === undefined)
                              ? "border-[var(--border-strong)] bg-[var(--surface-elevated)]"
                              : "border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]",
                            )}
                        >
                          {(multiple
                            ? resolvedBotIds.length === bots.length
                            : activeBotId === undefined) ? (
                            <Check className="h-3.5 w-3.5" />
                          ) : null}
                        </span>
                      )}
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-[var(--text-primary)]">
                          {t("botSwitcher.allBots")}
                        </span>
                        {variant === "session-chip" ? null : (
                          <span className="block text-[11px] text-[var(--text-quaternary)]">
                            {t("botSwitcher.botsVisible", { count: bots.length })}
                          </span>
                        )}
                      </span>
                    </span>
                    {variant === "session-chip" ? (
                      (multiple
                        ? resolvedBotIds.length === bots.length
                        : activeBotId === undefined) ? (
                        <Check className="h-4 w-4 shrink-0 text-[var(--text-secondary)]" />
                      ) : null
                    ) : (
                      <span className="text-[11px] text-[var(--text-quaternary)]">
                        {bots.length}
                      </span>
                    )}
                  </button>
                </div>
              ) : null}

              <div
                className="overflow-y-auto p-2"
                style={{ maxHeight: panelPosition ? Math.max(140, panelPosition.maxHeight - (shouldShowSearch ? 70 : 16)) : 320 }}
              >
                {visibleBots.length > 0 ? (
                  visibleBots.map((bot) => {
                    const isActive = selectedSet.has(bot.id);

                    return (
                      <button
                        key={bot.id}
                        type="button"
                        onClick={() => handleToggle(bot.id)}
                        className={cn(
                          "flex w-full items-center justify-between gap-3 rounded-[0.8rem] px-3 py-2.5 text-left transition-colors hover:bg-[var(--surface-hover)]",
                          variant === "session-chip" && "bot-switcher__menu-row bot-switcher__menu-row--session",
                        )}
                        aria-pressed={isActive}
                      >
                        <span className="flex min-w-0 items-center gap-3">
                          {variant === "session-chip" ? null : (
                            <span
                              className={cn(
                                "flex h-5 w-5 shrink-0 items-center justify-center rounded-[0.45rem] border text-[var(--text-primary)]",
                                isActive
                                  ? "border-[var(--border-strong)] bg-[var(--surface-elevated)]"
                                  : "border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]",
                              )}
                            >
                              {isActive ? <Check className="h-3.5 w-3.5" /> : null}
                            </span>
                          )}

                          <BotAgentGlyph
                            botId={bot.id}
                            color={bot.color}
                            variant="list"
                            shape="swatch"
                            className="bot-switcher__menu-glyph h-8 w-8 bot-swatch--animated"
                          />

                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium text-[var(--text-primary)]">
                              {bot.label}
                            </span>
                            {variant === "session-chip" ? null : (
                              <span className="block truncate text-[11px] font-mono text-[var(--text-quaternary)]">
                                {bot.id}
                              </span>
                            )}
                          </span>
                        </span>

                        {variant === "session-chip" ? (
                          isActive ? (
                            <Check className="h-4 w-4 shrink-0 text-[var(--text-secondary)]" />
                          ) : null
                        ) : !multiple ? (
                          isActive ? (
                            <span
                              className="h-2.5 w-2.5 shrink-0 rounded-full border border-[var(--border-strong)]"
                              style={{ backgroundColor: bot.color }}
                            />
                          ) : null
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
