import { cn } from "@/lib/utils";
import { translate } from "@/lib/i18n";
import { getSemanticStyle, getSemanticTone, getSemanticVars } from "@/lib/theme-semantic";
import { STATUS_CONFIG } from "../dashboard/status-indicator";

const FALLBACK_LABEL_KEYS: Record<string, string> = {
  completed: "runtime.labels.completed",
  running: "runtime.labels.running",
  queued: "runtime.labels.queued",
  failed: "runtime.labels.failed",
  retrying: "runtime.labels.retrying",
};

interface StatusPillProps {
  status: string;
}

export function StatusPill({ status }: StatusPillProps) {
  const statusConf = STATUS_CONFIG[status];
  const semanticTone = statusConf ? getSemanticTone(status) : "neutral";
  const semanticVars = getSemanticVars(semanticTone);
  const label = statusConf?.labelKey
    ? translate(statusConf.labelKey)
    : FALLBACK_LABEL_KEYS[status]
      ? translate(FALLBACK_LABEL_KEYS[status])
      : status.charAt(0).toUpperCase() + status.slice(1);
  const dotColor = statusConf?.color ?? "var(--tone-neutral-dot)";
  const animation = statusConf?.animationClass;

  return (
    <span
      className={cn(
        "status-pill inline-flex min-h-[28px] items-center gap-2 rounded-lg border px-2.5 py-1 text-[10.5px] font-semibold tracking-[0.01em]",
        animation
      )}
      style={getSemanticStyle(semanticTone)}
    >
      <span
        className="status-pill__dot h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: statusConf ? semanticVars.dot : dotColor }}
      />
      {label}
    </span>
  );
}
