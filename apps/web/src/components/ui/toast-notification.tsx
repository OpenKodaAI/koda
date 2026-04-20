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
  const visible = toasts.slice(-MAX_VISIBLE);

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

function ToastItem({ toast }: { toast: Toast }) {
  const { t } = useAppI18n();
  const { removeToast } = useToast();
  const meta = TOAST_META[toast.type];
  const Icon = meta.icon;
  const showMessage = toast.type === "error" && Boolean(toast.message);

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
          showMessage && "rounded-[var(--radius-panel-sm)] items-start py-2 pr-2.5 pl-3",
        )}
      >
        <Icon
          strokeWidth={1.75}
          className={cn(
            "icon-sm shrink-0",
            toast.type === "loading" && "animate-spin",
          )}
        />
        <div className="flex min-w-0 flex-col">
          <span className="truncate font-medium">
            {toast.title ?? t(meta.titleKey)}
          </span>
          {showMessage ? (
            <span className="mt-0.5 text-[0.75rem] opacity-85">
              {toast.message}
            </span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => removeToast(toast.id)}
          aria-label="Close"
          className="ml-1 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full opacity-70 transition-[opacity,background-color] hover:bg-black/10 hover:opacity-100 dark:hover:bg-white/10"
        >
          <X className="icon-xs" strokeWidth={1.75} />
        </button>
      </div>
    </motion.div>
  );
}
