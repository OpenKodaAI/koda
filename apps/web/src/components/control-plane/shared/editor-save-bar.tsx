"use client";

import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusDot } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface EditorSaveBarProps {
  dirty: boolean;
  saving?: boolean;
  changeCount?: number;
  onSave: () => void;
  onDiscard?: () => void;
  error?: string | null;
  className?: string;
}

export function EditorSaveBar({
  dirty,
  saving = false,
  changeCount,
  onSave,
  onDiscard,
  error,
  className,
}: EditorSaveBarProps) {
  const { t } = useAppI18n();
  const label = dirty
    ? typeof changeCount === "number" && changeCount !== 1
      ? t("controlPlane.saveBar.dirtyMany", {
          defaultValue: "{{n}} unsaved changes",
          n: changeCount,
        })
      : t("controlPlane.saveBar.dirty", {
          defaultValue: "1 unsaved change",
          n: changeCount ?? 1,
        })
    : t("controlPlane.saveBar.saved", { defaultValue: "All changes saved" });

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "sticky bottom-0 z-10 flex items-center justify-between gap-3",
        "border-t border-[var(--divider-hair)] bg-[var(--canvas)]/95 px-4 py-2.5 backdrop-blur-[6px]",
        className,
      )}
    >
      <div className="flex items-center gap-2.5 text-[0.8125rem] text-[var(--text-tertiary)]">
        {dirty ? <StatusDot tone="accent" pulse /> : <StatusDot tone="success" />}
        <span>{error ?? label}</span>
      </div>
      <div className="flex items-center gap-2">
        {onDiscard ? (
          <Button
            variant="ghost"
            size="md"
            type="button"
            onClick={onDiscard}
            disabled={!dirty || saving}
          >
            {t("controlPlane.saveBar.discard", { defaultValue: "Discard" })}
          </Button>
        ) : null}
        <Button
          variant="accent"
          size="md"
          type="button"
          onClick={onSave}
          disabled={!dirty || saving}
        >
          {saving ? (
            <Loader2 className="icon-sm animate-spin" strokeWidth={1.75} aria-hidden />
          ) : null}
          {t("controlPlane.saveBar.save", { defaultValue: "Save" })}
        </Button>
      </div>
    </div>
  );
}
