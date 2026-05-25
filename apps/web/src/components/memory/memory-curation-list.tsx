"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import type { MemoryClusterReviewItem, MemoryReviewItem } from "@/lib/types";
import { MemoryCurationRow } from "./memory-curation-row";

type Item = MemoryReviewItem | MemoryClusterReviewItem;

export function MemoryCurationList({
  items,
  selectedId,
  selectedBotId,
  checkedKeys,
  showAgent,
  title,
  subtitle,
  loading = false,
  emptyLabel,
  onSelect,
  onCheckChange,
}: {
  kind: "memory" | "cluster";
  items: Item[];
  selectedId: string | null;
  selectedBotId: string | null;
  checkedKeys: Set<string>;
  showAgent: boolean;
  title: string;
  subtitle: string;
  loading?: boolean;
  emptyLabel: string;
  onSelect: (item: Item) => void;
  onCheckChange: (item: Item, checked: boolean) => void;
}) {
  const { t } = useAppI18n();
  return (
    <section className="flex min-h-0 flex-col overflow-hidden border-b border-[var(--border-subtle)] xl:border-b-0 xl:border-r">
      <div className="border-b border-[var(--border-subtle)] px-4 py-4 sm:px-5">
        <div className="flex items-end justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[15px] font-semibold tracking-[-0.035em] text-[var(--text-primary)]">
              {title}
            </p>
            <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">{subtitle}</p>
          </div>
          <span className="eyebrow text-[10px] text-[var(--text-quaternary)]">{t("memory.curation.sortHint")}</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-3">
            {Array.from({ length: 8 }).map((_, index) => (
              <div key={index} className="skeleton mb-2 h-[74px] rounded-lg" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="flex min-h-[24rem] items-center justify-center px-6">
            <p className="text-[12px] text-[var(--text-tertiary)]">{emptyLabel}</p>
          </div>
        ) : (
          <div className="divide-y divide-[var(--border-subtle)]">
            {items.map((item) => {
              const key =
                "memory_id" in item
                  ? `${item.bot_id}::memory::${item.memory_id}`
                  : `${item.bot_id}::cluster::${item.cluster_id}`;
              const itemId = "memory_id" in item ? String(item.memory_id) : item.cluster_id;

              return (
                <MemoryCurationRow
                  key={key}
                  item={item}
                  selected={selectedId === itemId && selectedBotId === item.bot_id}
                  checked={checkedKeys.has(key)}
                  showAgent={showAgent}
                  onSelect={() => onSelect(item)}
                  onCheckChange={(checked) => onCheckChange(item, checked)}
                />
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
