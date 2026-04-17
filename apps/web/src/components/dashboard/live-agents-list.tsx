"use client";

import { memo } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { BotAgentGlyph } from "@/components/dashboard/bot-agent-glyph";
import type { BotDisplay } from "@/lib/bot-constants";
import type { BotStats, Task } from "@/lib/types";
import { cn } from "@/lib/utils";

const LIVE_STATUSES: Task["status"][] = ["queued", "running", "retrying"];

export interface LiveAgentsListEntry {
  bot: BotDisplay;
  stats?: BotStats;
}

interface LiveAgentsListProps {
  entries: LiveAgentsListEntry[];
  title: string;
  emptyLabel: string;
  viewAllLabel: string;
  viewAllHref?: string;
  statusLabels: {
    active: (count: number) => string;
    idle: string;
    waiting: string;
  };
  onSelectBot?: (botId: string) => void;
  className?: string;
}

function pickFeaturedTask(stats?: BotStats): Task | null {
  if (!stats?.recentTasks?.length) return null;
  return (
    stats.recentTasks.find((task) => LIVE_STATUSES.includes(task.status)) ??
    stats.recentTasks[0] ??
    null
  );
}

function statusToneClass(stats?: BotStats) {
  if (!stats?.dbExists) return "bg-[var(--tone-warning-dot)]";
  if ((stats.activeTasks ?? 0) > 0) return "bg-[var(--tone-info-dot)]";
  return "bg-[var(--tone-success-dot)]";
}

function LiveAgentsListComponent({
  entries,
  title,
  emptyLabel,
  viewAllLabel,
  viewAllHref,
  statusLabels,
  onSelectBot,
  className,
}: LiveAgentsListProps) {
  return (
    <section
      className={cn(
        "flex flex-col gap-3 rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)] p-5",
        className,
      )}
    >
      <header className="flex items-center justify-between gap-2">
        <h3 className="m-0 text-[var(--font-size-md)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
          {title}
        </h3>
        {viewAllHref ? (
          <Link
            href={viewAllHref}
            className="inline-flex items-center gap-1 text-[0.8125rem] text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)]"
          >
            {viewAllLabel}
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        ) : null}
      </header>

      {entries.length === 0 ? (
        <p className="m-0 text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
          {emptyLabel}
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-[color:var(--divider-hair)]">
          {entries.map((entry) => {
            const featured = pickFeaturedTask(entry.stats);
            const activeCount = entry.stats?.activeTasks ?? 0;
            const statusLabel = activeCount > 0
              ? statusLabels.active(activeCount)
              : entry.stats?.dbExists
                ? statusLabels.idle
                : statusLabels.waiting;

            const detail = featured?.query_text?.trim() ?? statusLabel;

            return (
              <li key={entry.bot.id}>
                <button
                  type="button"
                  onClick={() => onSelectBot?.(entry.bot.id)}
                  className={cn(
                    "flex w-full items-center gap-3 py-2.5 text-left transition-colors",
                    "hover:text-[var(--text-primary)]",
                  )}
                >
                  <BotAgentGlyph
                    botId={entry.bot.id}
                    color={entry.bot.color}
                    active={activeCount > 0}
                    variant="list"
                    className="h-6 w-6 shrink-0"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-[var(--font-size-sm)] font-medium text-[var(--text-primary)]">
                        {entry.bot.label}
                      </span>
                      <span
                        className={cn(
                          "inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full",
                          statusToneClass(entry.stats),
                        )}
                        aria-hidden="true"
                      />
                    </div>
                    <p className="m-0 truncate text-[0.75rem] text-[var(--text-tertiary)]">
                      {detail}
                    </p>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function arePropsEqual(prev: LiveAgentsListProps, next: LiveAgentsListProps): boolean {
  if (prev.title !== next.title) return false;
  if (prev.emptyLabel !== next.emptyLabel) return false;
  if (prev.viewAllLabel !== next.viewAllLabel) return false;
  if (prev.viewAllHref !== next.viewAllHref) return false;
  if (prev.className !== next.className) return false;
  if (prev.onSelectBot !== next.onSelectBot) return false;
  if (prev.statusLabels !== next.statusLabels) return false;
  if (prev.entries.length !== next.entries.length) return false;
  for (let i = 0; i < prev.entries.length; i += 1) {
    const a = prev.entries[i]!;
    const b = next.entries[i]!;
    if (a.bot.id !== b.bot.id) return false;
    const aActive = a.stats?.activeTasks ?? 0;
    const bActive = b.stats?.activeTasks ?? 0;
    if (aActive !== bActive) return false;
    const aTask = a.stats?.recentTasks?.[0]?.id ?? null;
    const bTask = b.stats?.recentTasks?.[0]?.id ?? null;
    if (aTask !== bTask) return false;
    if ((a.stats?.dbExists ?? false) !== (b.stats?.dbExists ?? false)) return false;
  }
  return true;
}

export const LiveAgentsList = memo(LiveAgentsListComponent, arePropsEqual);
