"use client";

import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown, Loader2, Plus, Search } from "lucide-react";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useCreateAgent } from "@/hooks/use-create-agent";
import {
  resolveAgentSelection,
  toggleAgentSelection,
} from "@/lib/agent-selection";
import { cn } from "@/lib/utils";

interface AgentSwitcherProps {
  selectedBotIds?: string[];
  onSelectionChange?: (agentIds: string[]) => void;
  activeBotId?: string;
  onAgentChange?: (agentId: string | undefined) => void;
  multiple?: boolean;
  showAll?: boolean;
  className?: string;
  fullWidth?: boolean;
  /** No-op retained for API compatibility. The trigger is always compact. */
  singleRow?: boolean;
  placeholder?: string;
  /** No-op retained for API compatibility; search visibility is auto-inferred. */
  variant?: "field" | "action-button" | "session-chip";
  menuPlacement?: "bottom-start" | "bottom-end" | "top-start" | "top-end";
  showSearch?: boolean;
  disabled?: boolean;
  /** Renders a "+" button beside the trigger that navigates to /control-plane. Default true. */
  showCreate?: boolean;
}

export function AgentSwitcher({
  selectedBotIds,
  onSelectionChange,
  activeBotId,
  onAgentChange,
  multiple = false,
  showAll = true,
  className,
  fullWidth = false,
  placeholder,
  menuPlacement = "bottom-start",
  showSearch,
  disabled = false,
  showCreate = true,
}: AgentSwitcherProps) {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const { creating, createAgent } = useCreateAgent();
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [panelPosition, setPanelPosition] = useState<{
    top: number;
    left: number;
    width: number;
    maxHeight: number;
    placeAbove: boolean;
  } | null>(null);

  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const resolvedActiveBotId = useMemo(() => {
    if (!activeBotId) return undefined;
    return (
      availableBotIds.find(
        (agentId) => agentId.toLowerCase() === activeBotId.toLowerCase(),
      ) ?? undefined
    );
  }, [activeBotId, availableBotIds]);

  const resolvedBotIds = useMemo(
    () =>
      multiple
        ? resolveAgentSelection(selectedBotIds, availableBotIds)
        : resolvedActiveBotId
          ? [resolvedActiveBotId]
          : [],
    [availableBotIds, multiple, resolvedActiveBotId, selectedBotIds],
  );

  const selectedSet = useMemo(() => new Set(resolvedBotIds), [resolvedBotIds]);
  const selectedAgents = useMemo(
    () => agents.filter((agent) => selectedSet.has(agent.id)),
    [agents, selectedSet],
  );

  const visibleAgents = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return agents;
    return agents.filter((agent) =>
      `${agent.label} ${agent.id}`.toLowerCase().includes(query),
    );
  }, [agents, search]);

  const shouldShowSearch = showSearch ?? true;

  const activeSingleAgent = multiple ? selectedAgents[0] ?? null : selectedAgents[0] ?? null;
  const allSelected = multiple && resolvedBotIds.length === agents.length && agents.length > 0;

  const summaryLabel = multiple
    ? resolvedBotIds.length === 0 || allSelected
      ? t("agentSwitcher.allAgents")
      : resolvedBotIds.length === 1
        ? selectedAgents[0]?.label ?? resolvedBotIds[0]
        : t("agentSwitcher.agentsSelectedOutOfTotal", {
            selected: resolvedBotIds.length,
            total: agents.length,
          })
    : resolvedActiveBotId
      ? selectedAgents[0]?.label ?? resolvedActiveBotId
      : showAll
        ? t("agentSwitcher.allAgents")
        : placeholder ?? t("agentSwitcher.placeholder");

  function closeMenu() {
    setOpen(false);
    setSearch("");
  }

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !rootRef.current?.contains(target) &&
        !panelRef.current?.contains(target)
      ) {
        closeMenu();
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeMenu();
    };
    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !rootRef.current) return;

    const updatePosition = () => {
      if (!rootRef.current) return;
      const rect = rootRef.current.getBoundingClientRect();
      const pad = 12;
      const gap = 6;
      const width = Math.min(
        Math.max(220, rect.width),
        window.innerWidth - pad * 2,
      );
      const alignRight = menuPlacement.endsWith("end");
      const preferredPlaceAbove = menuPlacement.startsWith("top");
      const spaceAbove = rect.top - pad - gap;
      const spaceBelow = window.innerHeight - rect.bottom - pad - gap;
      const placeAbove = preferredPlaceAbove
        ? !(spaceAbove < 220 && spaceBelow > spaceAbove)
        : spaceBelow < 260 && spaceAbove > spaceBelow;
      const left = alignRight
        ? Math.min(
            Math.max(rect.right - width, pad),
            window.innerWidth - pad - width,
          )
        : Math.min(
            Math.max(rect.left, pad),
            window.innerWidth - pad - width,
          );
      const top = placeAbove
        ? Math.max(pad, rect.top - gap)
        : Math.min(rect.bottom + gap, window.innerHeight - pad);
      const maxHeight = placeAbove
        ? Math.max(200, spaceAbove)
        : Math.max(200, spaceBelow);
      setPanelPosition({ top, left, width, maxHeight, placeAbove });
    };

    const frame = window.requestAnimationFrame(updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [menuPlacement, open]);

  useEffect(() => {
    if (open && shouldShowSearch) {
      const timer = window.setTimeout(() => searchRef.current?.focus(), 40);
      return () => window.clearTimeout(timer);
    }
  }, [open, shouldShowSearch]);

  function handleSelectAll() {
    if (multiple) {
      onSelectionChange?.([]);
      return;
    }
    onAgentChange?.(undefined);
    closeMenu();
  }

  function handleToggle(agentId: string) {
    if (multiple) {
      onSelectionChange?.(
        toggleAgentSelection(selectedBotIds, agentId, availableBotIds),
      );
      return;
    }
    onAgentChange?.(
      resolvedActiveBotId === agentId && showAll ? undefined : agentId,
    );
    closeMenu();
  }

  return (
    <div
      ref={rootRef}
      className={cn(
        "agent-switcher relative min-w-0",
        fullWidth ? "w-full" : "inline-flex",
        className,
      )}
    >
      <div
        className={cn(
          "flex items-center",
          showCreate && "field-shell h-10 gap-1 py-1",
          fullWidth && "w-full",
        )}
        style={
          showCreate
            ? {
                width: fullWidth ? "100%" : "fit-content",
                borderRadius: "var(--radius-input)",
                paddingInline: "0.2rem",
              }
            : undefined
        }
      >
        <button
          type="button"
          onClick={() => {
            if (disabled) return;
            setOpen((current) => {
              if (current) setSearch("");
              return !current;
            });
          }}
          disabled={disabled}
          className={cn(
            "flex h-8 w-full min-w-[180px] max-w-[240px] items-center justify-between gap-2.5",
            "rounded-[calc(var(--radius-input)-4px)] bg-transparent px-2 text-left",
            "transition-colors duration-[var(--transition-fast)]",
            "hover:bg-[var(--hover-tint)]",
            "focus-visible:outline-none",
            "disabled:cursor-not-allowed disabled:opacity-60",
            open && "bg-[var(--hover-tint)]",
          )}
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-label={
            multiple ? t("agentSwitcher.ariaMultiple") : t("agentSwitcher.ariaSingle")
          }
        >
          <span className="flex min-w-0 items-center gap-2.5">
            {activeSingleAgent ? (
              <span
                className="agent-swatch agent-swatch--animated h-6 w-6 shrink-0"
                aria-hidden="true"
                style={
                  { "--agent-orb-color": activeSingleAgent.color } as CSSProperties
                }
              >
                <span className="agent-swatch__halo" />
                <span className="agent-swatch__base" />
                <span className="agent-swatch__swirl" />
                <span className="agent-swatch__shine" />
                <span className="agent-swatch__grain" />
              </span>
            ) : null}
            <span className="block min-w-0 truncate text-sm font-medium text-[var(--text-primary)]">
              {summaryLabel}
            </span>
            {multiple && resolvedBotIds.length > 1 && !allSelected ? (
              <span className="inline-flex h-5 shrink-0 items-center rounded-full bg-[var(--panel-strong)] px-2 text-[10px] font-semibold tabular-nums text-[var(--text-secondary)]">
                {resolvedBotIds.length}
              </span>
            ) : null}
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 shrink-0 text-[var(--text-quaternary)] transition-transform duration-200",
              open && "rotate-180",
            )}
          />
        </button>

        {showCreate ? (
          <button
            type="button"
            onClick={() => void createAgent()}
            disabled={creating}
            className={cn(
              "inline-flex h-8 w-8 shrink-0 items-center justify-center",
              "rounded-[calc(var(--radius-input)-4px)] bg-[var(--panel-strong)] text-[var(--text-primary)]",
              "transition-colors duration-[var(--transition-fast)]",
              "hover:bg-[var(--surface-hover)] active:scale-[0.96]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]",
              "disabled:cursor-not-allowed disabled:opacity-60",
            )}
            aria-label={t("agentSwitcher.createAria")}
          >
            {creating ? (
              <Loader2 className="icon-sm animate-spin" strokeWidth={1.75} />
            ) : (
              <Plus className="icon-sm" strokeWidth={1.75} />
            )}
          </button>
        ) : null}
      </div>

      {typeof document !== "undefined"
        ? createPortal(
            <AnimatePresence initial={false}>
              {open ? (
                <motion.div
                  ref={panelRef}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
                  className="app-floating-panel agent-board-ws-selector__menu"
                  role="listbox"
                  aria-label={
                    multiple
                      ? t("agentSwitcher.ariaMultiple")
                      : t("agentSwitcher.ariaSingle")
                  }
                  style={{
                    position: "fixed",
                    zIndex: 80,
                    top: panelPosition?.top ?? 0,
                    left: panelPosition?.left ?? 0,
                    width: panelPosition?.width,
                    maxHeight: panelPosition?.maxHeight,
                    transform: panelPosition?.placeAbove
                      ? "translateY(-100%)"
                      : undefined,
                    visibility: panelPosition ? "visible" : "hidden",
                    overflow: "hidden",
                    display: "flex",
                    flexDirection: "column",
                  }}
                >
                  {shouldShowSearch ? (
                    <div className="border-b border-[color:var(--divider-hair)] px-2 py-2">
                      <label className="flex items-center gap-2 rounded-[calc(var(--radius-input)-4px)] bg-[var(--panel-soft)] px-2.5">
                        <Search className="h-3.5 w-3.5 text-[var(--text-quaternary)]" />
                        <input
                          ref={searchRef}
                          type="text"
                          value={search}
                          onChange={(event) => setSearch(event.target.value)}
                          placeholder={t("agentSwitcher.searchPlaceholder")}
                          className="h-8 w-full bg-transparent text-[0.8125rem] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
                        />
                      </label>
                    </div>
                  ) : null}

                  <div className="flex-1 overflow-y-auto">
                    {showAll ? (
                      <button
                        type="button"
                        role="option"
                        aria-selected={allSelected || resolvedBotIds.length === 0}
                        className={cn(
                          "agent-board-ws-selector__item text-left",
                          (allSelected || resolvedBotIds.length === 0) &&
                            "agent-board-ws-selector__item--active",
                        )}
                        onClick={handleSelectAll}
                      >
                        <span
                          className="agent-board-ws-selector__dot"
                          aria-hidden="true"
                          style={{ backgroundColor: "var(--text-quaternary)" }}
                        />
                        <span className="min-w-0 flex-1 truncate">
                          {t("agentSwitcher.allAgents")}
                        </span>
                        <span className="agent-board-ws-selector__item-count">
                          {agents.length}
                        </span>
                      </button>
                    ) : null}

                    {visibleAgents.length > 0 ? (
                      visibleAgents.map((agent) => {
                        const isActive = selectedSet.has(agent.id);
                        return (
                          <button
                            key={agent.id}
                            type="button"
                            role="option"
                            aria-selected={isActive}
                            className={cn(
                              "agent-board-ws-selector__item text-left",
                              isActive && "agent-board-ws-selector__item--active",
                            )}
                            onClick={() => handleToggle(agent.id)}
                          >
                            <span
                              className="agent-board-ws-selector__dot"
                              aria-hidden="true"
                              style={{ backgroundColor: agent.color }}
                            />
                            <span className="min-w-0 flex-1 truncate">
                              {agent.label}
                            </span>
                            {isActive ? (
                              <Check className="h-3.5 w-3.5 shrink-0 text-[var(--text-secondary)]" />
                            ) : null}
                          </button>
                        );
                      })
                    ) : (
                      <div className="px-3 py-6 text-center text-[0.8125rem] text-[var(--text-tertiary)]">
                        {t("agentSwitcher.noResults")}
                      </div>
                    )}
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>,
            document.body,
          )
        : null}
    </div>
  );
}
