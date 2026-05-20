"use client";

import { Check, ChevronDown } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

export interface ComposerToolbarProps {
  agentId?: string | null;
  onAgentChange?: (agentId: string | undefined) => void;
  lockedAgent: boolean;
  modelLabel?: string | null;
}

export function ComposerToolbar({
  agentId,
  onAgentChange,
  lockedAgent,
  modelLabel,
}: ComposerToolbarProps) {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const activeAgent = agents.find((agent) => agent.id === agentId);
  const agentLabel = activeAgent?.label ?? agentId ?? null;
  const activeColor = activeAgent?.color ?? "#7A8799";

  return (
    <div className="flex items-center justify-between gap-3 px-3 pb-2 pt-1">
      <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
        {t("chat.composer.sendHint", undefined)}
      </span>
      <div className="flex items-center gap-2 text-[0.75rem] text-[var(--text-tertiary)]">
        {modelLabel ? (
          <span className="font-mono tracking-[-0.01em] text-[0.6875rem]">
            {modelLabel}
          </span>
        ) : null}
        {modelLabel && agentLabel ? (
          <span className="h-3 w-px bg-[var(--divider-hair)]" aria-hidden />
        ) : null}
        {agentLabel ? (
          lockedAgent ? (
            <span className="inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] bg-[var(--panel)] px-1.5 py-0.5 text-[var(--text-secondary)]">
              {agentId ? (
                <span
                  aria-hidden
                  className="h-4 w-1 shrink-0 rounded-full"
                  style={{ background: activeColor }}
                />
              ) : null}
              <span className="truncate max-w-[160px]">{agentLabel}</span>
            </span>
          ) : (
            <Popover>
              <PopoverTrigger asChild>
                <button
                  type="button"
                  className={cn(
                    "inline-flex items-center gap-1.5 truncate max-w-[200px]",
                    "rounded-[var(--radius-pill)] border border-[color:var(--border-subtle)]",
                    "bg-[var(--panel)] px-1.5 py-0.5 text-[var(--text-secondary)]",
                    "transition-[border-color,background-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                    "hover:border-[color:var(--border-strong)] hover:text-[var(--text-primary)]",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel-soft)]",
                  )}
                >
                  {agentId ? (
                    <span
                      aria-hidden
                      className="h-4 w-1 shrink-0 rounded-full"
                      style={{ background: activeColor }}
                    />
                  ) : null}
                  <span className="truncate">{agentLabel}</span>
                  <ChevronDown
                    className="icon-xs shrink-0 opacity-60"
                    strokeWidth={1.75}
                    aria-hidden
                  />
                </button>
              </PopoverTrigger>
              <PopoverContent align="end" sideOffset={8} className="w-72 p-1">
                <div className="px-2 pt-1.5 pb-0.5 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)]">
                  {t("chat.composer.agents", undefined)}
                </div>
                <ul role="listbox" className="flex flex-col">
                  {agents.map((agent) => {
                    const active = agent.id === agentId;
                    return (
                      <li key={agent.id}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={active}
                          onClick={() => onAgentChange?.(agent.id)}
                          className={cn(
                            "flex w-full items-center gap-2.5 rounded-[var(--radius-panel-sm)] px-2 py-1.5 text-left text-[0.8125rem]",
                            "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                            active
                              ? "bg-[var(--hover-tint)] text-[var(--text-primary)]"
                              : "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
                          )}
                        >
                          <span
                            aria-hidden
                            className="h-5 w-1 shrink-0 rounded-full"
                            style={{ background: agent.color ?? "#7A8799" }}
                          />
                          <span className="min-w-0 flex-1 truncate">
                            {agent.label || agent.id}
                          </span>
                          {active ? (
                            <Check
                              className="h-3.5 w-3.5 shrink-0 text-[var(--text-secondary)]"
                              strokeWidth={1.75}
                              aria-hidden
                            />
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </PopoverContent>
            </Popover>
          )
        ) : null}
      </div>
    </div>
  );
}
