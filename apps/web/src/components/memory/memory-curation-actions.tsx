"use client";

import { Archive, Check, Clock3, GitMerge, RotateCcw, Trash2 } from "lucide-react";
import {
  SELECT_ALL_VALUE,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface MemoryCurationActionsProps {
  kind: "memory" | "cluster";
  busy?: boolean;
  compact?: boolean;
  selectedCount?: number;
  canMerge?: boolean;
  className?: string;
  mergeTargetOptions?: Array<{ value: number; label: string }>;
  mergeTargetId?: number | null;
  onMergeTargetChange?: (value: number | null) => void;
  onAction: (action: "approve" | "discard" | "expire" | "archive" | "restore" | "merge") => void;
}

export function MemoryCurationActions({
  kind,
  busy = false,
  compact = false,
  selectedCount = 1,
  canMerge = false,
  className,
  mergeTargetOptions = [],
  mergeTargetId = null,
  onMergeTargetChange,
  onAction,
}: MemoryCurationActionsProps) {
  const { t } = useAppI18n();
  return (
    <div
      className={cn(
        "flex items-center gap-2 overflow-x-auto whitespace-nowrap pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        compact && "gap-1.5",
        className
      )}
    >
      <button
        type="button"
        className={cn(
          "button-shell button-shell--secondary shrink-0",
          compact && "button-shell--sm"
        )}
        onClick={() => onAction("approve")}
        disabled={busy}
      >
        <Check className="h-4 w-4" />
        {t("memory.curation.actions.approve")}
      </button>

      {kind === "memory" ? (
        <button
          type="button"
          className={cn(
            "button-shell button-shell--secondary shrink-0",
            compact && "button-shell--sm"
          )}
          onClick={() => onAction("expire")}
          disabled={busy}
        >
          <Clock3 className="h-4 w-4" />
          {t("memory.curation.actions.expire")}
        </button>
      ) : null}

      <button
        type="button"
        className={cn(
          "button-shell button-shell--secondary shrink-0",
          compact && "button-shell--sm"
        )}
        onClick={() => onAction("archive")}
        disabled={busy}
      >
        <Archive className="h-4 w-4" />
        {t("memory.curation.actions.archive")}
      </button>

      <button
        type="button"
        className={cn(
          "button-shell button-shell--secondary shrink-0",
          compact && "button-shell--sm"
        )}
        onClick={() => onAction("discard")}
        disabled={busy}
      >
        <Trash2 className="h-4 w-4" />
        {t("memory.curation.actions.discard")}
      </button>

      <button
        type="button"
        className={cn(
          "button-shell button-shell--quiet shrink-0",
          compact && "button-shell--sm"
        )}
        onClick={() => onAction("restore")}
        disabled={busy}
      >
        <RotateCcw className="h-4 w-4" />
        {t("memory.curation.actions.restore")}
      </button>

      {kind === "memory" && canMerge ? (
        <div className="flex items-center gap-2">
          {mergeTargetOptions.length > 0 && onMergeTargetChange ? (
            <Select
              value={mergeTargetId != null ? String(mergeTargetId) : SELECT_ALL_VALUE}
              onValueChange={(v) =>
                onMergeTargetChange(v === SELECT_ALL_VALUE ? null : Number(v))
              }
              disabled={busy}
            >
              <SelectTrigger
                className={cn("w-[13rem] shrink-0", compact && "w-[11.5rem]")}
              >
                <SelectValue placeholder={t("memory.curation.actions.mergeTarget")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={SELECT_ALL_VALUE}>
                  {t("memory.curation.actions.mergeTarget")}
                </SelectItem>
                {mergeTargetOptions.map((option) => (
                  <SelectItem key={option.value} value={String(option.value)}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}

          <button
            type="button"
            className={cn(
              "button-shell button-shell--primary shrink-0",
              compact && "button-shell--sm"
            )}
            onClick={() => onAction("merge")}
            disabled={busy || (selectedCount <= 1 && !mergeTargetId)}
            title={
              selectedCount > 1
                ? t("memory.curation.actions.mergeSelectedHint")
                : t("memory.curation.actions.mergeChooseHint")
            }
          >
            <GitMerge className="h-4 w-4" />
            {t("memory.curation.actions.merge")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
