"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import { getBotColor, getBotLabel } from "@/lib/bot-constants";
import { getMemoryTypeLabel } from "@/lib/memory-constants";
import type {
  MemoryClusterReviewItem,
  MemoryReviewItem,
  MemoryReviewStatus,
} from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";

type RowItem = MemoryReviewItem | MemoryClusterReviewItem;

function getStatusColor(status: MemoryReviewStatus) {
  switch (status) {
    case "approved":
      return "var(--tone-success-dot)";
    case "merged":
      return "var(--tone-retry-dot)";
    case "discarded":
      return "var(--tone-danger-dot)";
    case "expired":
      return "var(--tone-warning-dot)";
    case "archived":
      return "var(--tone-neutral-dot)";
    default:
      return "var(--tone-info-dot)";
  }
}

function MemoryRowStatus({ status }: { status: MemoryReviewStatus }) {
  const { t } = useAppI18n();
  const color = getStatusColor(status);
  const label = t(`memory.curation.status.${status}`, {
    defaultValue: status,
  }).toLowerCase();

  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-[var(--text-tertiary)]">
      <span
        className="h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  );
}

export function MemoryCurationRow({
  item,
  selected,
  checked,
  showBot,
  onSelect,
  onCheckChange,
}: {
  item: RowItem;
  selected: boolean;
  checked: boolean;
  showBot: boolean;
  onSelect: () => void;
  onCheckChange: (checked: boolean) => void;
}) {
  const { t } = useAppI18n();
  const isMemory = "memory_id" in item;
  const botColor = getBotColor(item.bot_id);
  const botLabel = getBotLabel(item.bot_id);
  const title = isMemory
    ? item.title
    : t("memory.curation.detail.memoriesConnected", { count: item.member_count });
  const preview = isMemory
    ? item.source_query_preview || item.content
    : item.summary;
  const typeLabel = isMemory
    ? getMemoryTypeLabel(item.memory_type, t)
    : getMemoryTypeLabel(item.dominant_type, t);
  const meta = isMemory
    ? [
        typeLabel,
        item.semantic_strength != null
          ? `${Math.round(item.semantic_strength * 100)}%`
          : null,
        t("memory.curation.detail.accessesMeta", { value: item.access_count }),
      ]
    : [
        typeLabel,
        t("memory.map.memoryCount", { count: item.member_count }),
        t("memory.curation.row.sessionCount", {
          count: item.session_ids.length,
          defaultValue: `${item.session_ids.length} sessions`,
        }),
      ];
  const activityAt = isMemory ? item.last_accessed ?? item.created_at : item.created_at;

  return (
    <div
      className={cn(
        "group flex items-start gap-3 px-4 py-3.5 transition-colors sm:px-5",
        selected ? "bg-[rgba(255,255,255,0.026)]" : "hover:bg-[rgba(255,255,255,0.014)]"
      )}
      style={selected ? { boxShadow: `inset 2px 0 0 ${botColor}` } : undefined}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onCheckChange(event.target.checked)}
        className="mt-1 h-4 w-4 shrink-0 rounded border-[var(--border-subtle)] bg-transparent accent-[var(--interactive-active-top)]"
        aria-label={t("memory.curation.row.select", {
          title,
          defaultValue: `Select ${title}`,
        })}
      />

      <button
        type="button"
        onClick={onSelect}
        className="flex min-w-0 flex-1 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[var(--text-tertiary)]">
                {showBot ? (
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: botColor }}
                    />
                    {botLabel}
                  </span>
                ) : null}
                {showBot ? <span>•</span> : null}
                <span>{typeLabel}</span>
              </div>

              <p className="mt-1 truncate text-[14px] font-medium tracking-[-0.03em] text-[var(--text-primary)]">
                {title}
              </p>
              <p className="mt-1 line-clamp-2 text-[13px] leading-5 text-[var(--text-secondary)]">
                {preview}
              </p>
            </div>

            <div className="shrink-0 text-right">
              <span className="block text-[11px] text-[var(--text-tertiary)]">
                {formatRelativeTime(activityAt)}
              </span>
              <div className="mt-1">
                <MemoryRowStatus status={item.review_status} />
              </div>
            </div>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[var(--text-tertiary)]">
            {meta.filter(Boolean).map((value, index) => (
              <span key={`${value}-${index}`} className="inline-flex items-center gap-2">
                {index > 0 ? <span>•</span> : null}
                <span>{value}</span>
              </span>
            ))}
          </div>
        </div>
      </button>
    </div>
  );
}
