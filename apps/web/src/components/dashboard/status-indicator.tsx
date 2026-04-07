import { cn } from "@/lib/utils";
import { translate } from "@/lib/i18n";
import {
  getSemanticStyle,
  getSemanticTone,
  getSemanticVars,
} from "@/lib/theme-semantic";

export const STATUS_CONFIG: Record<
  string,
  { color: string; labelKey: string; animationClass?: string }
> = {
  completed: { color: "var(--status-completed)", labelKey: "runtime.labels.completed" },
  running: {
    color: "var(--status-running)",
    labelKey: "runtime.labels.running",
    animationClass: "status-running",
  },
  queued: { color: "var(--status-queued)", labelKey: "runtime.labels.queued" },
  failed: { color: "var(--status-failed)", labelKey: "runtime.labels.failed" },
  retrying: {
    color: "var(--status-retrying)",
    labelKey: "runtime.labels.retrying",
    animationClass: "status-retrying",
  },
};

interface StatusIndicatorProps {
  status: string;
  showLabel?: boolean;
  className?: string;
}

export function StatusIndicator({
  status,
  showLabel = false,
  className,
}: StatusIndicatorProps) {
  const statusConf = STATUS_CONFIG[status];
  const config = statusConf ?? { color: "var(--text-tertiary)" };
  const label = statusConf?.labelKey ? translate(statusConf.labelKey) : status;
  const isPill = showLabel;
  const tone = statusConf ? getSemanticTone(status) : "neutral";
  const toneVars = getSemanticVars(tone);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-lg text-[10.5px] font-semibold tracking-[0.01em]",
        isPill
          ? "min-h-[28px] border px-2.5 py-1"
          : "border-none bg-transparent px-0 py-0 text-[var(--text-secondary)]",
        className
      )}
      style={
        isPill ? getSemanticStyle(tone) : undefined
      }
    >
      <span
        className={cn("block shrink-0 rounded-full", config.animationClass)}
        style={{
          width: 8,
          height: 8,
          backgroundColor: statusConf ? toneVars.dot : config.color,
        }}
      />
      {showLabel && <span>{label}</span>}
    </span>
  );
}
