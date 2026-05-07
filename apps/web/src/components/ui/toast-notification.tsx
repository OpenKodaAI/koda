"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  Info,
  LoaderCircle,
  TriangleAlert,
  X,
} from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast, type Toast, type ToastType } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

const MAX_VISIBLE = 4;

type TypeMeta = {
  titleKey: string;
  icon: typeof CheckCircle2;
  /** CSS background token (solid tonal fill for the whole toast). */
  bgVar: string;
  /** CSS foreground token (text/icon color that contrasts with `bgVar`). */
  fgVar: string;
};

/**
 * Tone palette tokens (from `globals.css`) provide a matching pair of
 * solid background + contrasting text for each theme. The dark theme uses
 * rich fills with light text (e.g. `#3f7353` + `#f3fbf6`); the light theme
 * uses pastel fills with dark text (e.g. `#d5e8db` + `#101010`). So a
 * single `bg`/`fg` pair works across themes automatically.
 */
const TOAST_META: Record<ToastType, TypeMeta> = {
  success: {
    titleKey: "toast.success",
    icon: CheckCircle2,
    bgVar: "--tone-success-bg-strong",
    fgVar: "--tone-success-text",
  },
  error: {
    titleKey: "toast.error",
    icon: AlertCircle,
    bgVar: "--tone-danger-bg-strong",
    fgVar: "--tone-danger-text",
  },
  warning: {
    titleKey: "toast.warning",
    icon: TriangleAlert,
    bgVar: "--tone-warning-bg-strong",
    fgVar: "--tone-warning-text",
  },
  info: {
    titleKey: "toast.info",
    icon: Info,
    bgVar: "--tone-info-bg-strong",
    fgVar: "--tone-info-text",
  },
  loading: {
    titleKey: "toast.loading",
    icon: LoaderCircle,
    bgVar: "--panel-strong",
    fgVar: "--text-primary",
  },
};

export function ToastNotification() {
  const { toasts } = useToast();
  // Persistent (in-progress) toasts always win the visible slots so a
  // running download is never pushed off-screen by ephemeral notifications.
  const sorted = [...toasts].sort((a, b) => {
    const aPersist = a.persistent ? 1 : 0;
    const bPersist = b.persistent ? 1 : 0;
    return bPersist - aPersist;
  });
  const visible = sorted.slice(0, MAX_VISIBLE);

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="pointer-events-none fixed inset-x-0 top-[calc(var(--shell-topbar-height)+0.75rem)] z-[120] flex justify-center px-4"
    >
      <div className="flex flex-col items-center gap-1.5">
        <AnimatePresence initial={false} mode="popLayout">
          {visible.map((toast) => (
            <ToastItem key={toast.id} toast={toast} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(0)} MB`;
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(0)} KB`;
  return `${bytes} B`;
}

function ToastItem({ toast }: { toast: Toast }) {
  const { t, tl } = useAppI18n();
  const { removeToast } = useToast();
  const meta = TOAST_META[toast.type];
  const Icon = meta.icon;
  const hasProgress = toast.progress !== undefined;
  const isDismissible = toast.dismissible ?? !toast.persistent;
  // Show the message body whenever it carries information distinct from the
  // type label. The previous rule restricted bodies to errors/progress/
  // persistent, which silently swallowed warning/info messages — e.g. a
  // non-OAuth connect failure landed as a bare "Warning" with no detail.
  const showMessage = Boolean(toast.message);
  const title = toast.title ? tl(toast.title) : t(meta.titleKey);
  const message = showMessage ? tl(toast.message) : "";
  const actionLabel = toast.action ? tl(toast.action.label) : "";
  const actionAriaLabel = toast.action
    ? tl(toast.action.ariaLabel ?? toast.action.label)
    : "";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.98 }}
      transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
      className="pointer-events-auto"
    >
      <div
        role="status"
        style={{
          background: `var(${meta.bgVar})`,
          color: `var(${meta.fgVar})`,
        }}
        className={cn(
          "flex items-center gap-2 rounded-[var(--radius-pill)] py-1.5 pr-1.5 pl-3 shadow-[var(--shadow-floating)]",
          "text-[0.8125rem] leading-5",
          (showMessage || hasProgress) &&
            "rounded-[var(--radius-panel-sm)] items-start py-2 pr-2.5 pl-3 min-w-[320px]",
        )}
      >
        <Icon
          strokeWidth={1.75}
          className={cn(
            "icon-sm shrink-0",
            toast.type === "loading" && "animate-spin",
            (showMessage || hasProgress) && "mt-0.5",
          )}
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate font-medium">
            {title}
          </span>
          {showMessage ? (
            <span className="mt-0.5 text-[0.75rem] opacity-85">
              {message}
            </span>
          ) : null}
          {hasProgress ? <ToastProgressBar toast={toast} /> : null}
        </div>
        {toast.action ? (
          <button
            type="button"
            onClick={toast.action.onClick}
            disabled={toast.action.disabled}
            aria-label={actionAriaLabel}
            className={cn(
              "ml-2 inline-flex h-6 shrink-0 items-center justify-center rounded-full px-2.5",
              "border border-current/20 text-[0.6875rem] font-medium leading-none opacity-85",
              "transition-[opacity,background-color,border-color] hover:bg-black/10 hover:opacity-100 dark:hover:bg-white/10",
              "disabled:pointer-events-none disabled:opacity-45",
            )}
          >
            {actionLabel}
          </button>
        ) : null}
        {isDismissible ? (
          <button
            type="button"
            onClick={() => removeToast(toast.id)}
            aria-label={tl("Fechar aviso")}
            className="ml-1 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full opacity-70 transition-[opacity,background-color] hover:bg-black/10 hover:opacity-100 dark:hover:bg-white/10"
          >
            <X className="icon-xs" strokeWidth={1.75} />
          </button>
        ) : null}
      </div>
    </motion.div>
  );
}

function ToastProgressBar({ toast }: { toast: Toast }) {
  const progress = toast.progress;
  if (!progress) return null;
  const { downloaded, total, label } = progress;
  const indeterminate = total <= 0;
  const percent = indeterminate ? 0 : Math.min(100, Math.max(0, (downloaded / total) * 100));
  const formattedLabel =
    label ??
    (indeterminate
      ? formatBytes(downloaded)
      : `${formatBytes(downloaded)} / ${formatBytes(total)} · ${Math.round(percent)}%`);

  return (
    <div className="mt-2 flex flex-col gap-1">
      <div
        role="progressbar"
        aria-valuenow={indeterminate ? undefined : Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={indeterminate ? undefined : 100}
        className={cn(
          "relative h-1 overflow-hidden rounded-full",
          "bg-black/15 dark:bg-white/15",
        )}
      >
        {indeterminate ? (
          <div
            className="absolute inset-y-0 w-1/3 animate-[toast-shimmer_1.4s_ease-in-out_infinite] rounded-full bg-current opacity-90"
            data-testid="toast-progress-indeterminate"
          />
        ) : (
          <div
            className="h-full rounded-full bg-current opacity-90 transition-[width] duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]"
            style={{ width: `${percent}%` }}
            data-testid="toast-progress-bar"
          />
        )}
      </div>
      <span className="text-[0.6875rem] font-mono opacity-75">{formattedLabel}</span>
    </div>
  );
}
