"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  Info,
  LoaderCircle,
  TriangleAlert,
} from "lucide-react";
import {
  Alert,
  AlertContent,
  AlertDescription,
  AlertIcon,
  AlertTitle,
} from "@/components/ui/alert-1";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast, type Toast, type ToastType } from "@/hooks/use-toast";

const MAX_VISIBLE = 4;

const TOAST_META: Record<
  ToastType,
  {
    titleKey: string;
    variant: "success" | "destructive" | "info" | "warning" | "mono";
    appearance: "light" | "outline";
    icon: typeof CheckCircle2;
    iconTone?: "success" | "destructive" | "info" | "warning";
  }
> = {
  success: {
    titleKey: "toast.success",
    variant: "success",
    appearance: "light",
    icon: CheckCircle2,
    iconTone: "success",
  },
  error: {
    titleKey: "toast.error",
    variant: "destructive",
    appearance: "light",
    icon: AlertCircle,
    iconTone: "destructive",
  },
  warning: {
    titleKey: "toast.warning",
    variant: "warning",
    appearance: "light",
    icon: TriangleAlert,
    iconTone: "warning",
  },
  info: {
    titleKey: "toast.info",
    variant: "info",
    appearance: "light",
    icon: Info,
    iconTone: "info",
  },
  loading: {
    titleKey: "toast.loading",
    variant: "mono",
    appearance: "outline",
    icon: LoaderCircle,
    iconTone: "info",
  },
};

export function ToastNotification() {
  const { toasts } = useToast();
  const visible = toasts.slice(-MAX_VISIBLE);

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="pointer-events-none fixed inset-x-0 top-[calc(var(--shell-topbar-height)+0.9rem)] z-[120] flex justify-center px-4 sm:justify-end sm:px-5"
    >
      <div
        className="toaster group flex w-full max-w-[26rem] flex-col gap-2.5"
        style={{ ["--width" as string]: "min(26rem, calc(100vw - 2rem))" }}
      >
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

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -18, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -10, scale: 0.98 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className="pointer-events-auto"
    >
      <Alert
        variant={meta.variant}
        appearance={meta.appearance}
        icon={meta.iconTone}
        size="md"
        close
        onClose={() => removeToast(toast.id)}
        >
        <AlertIcon>
          <Icon className={toast.type === "loading" ? "animate-spin" : undefined} />
        </AlertIcon>
        <AlertContent>
          <AlertTitle>{toast.title ?? t(meta.titleKey)}</AlertTitle>
          <AlertDescription>{toast.message}</AlertDescription>
        </AlertContent>
      </Alert>
    </motion.div>
  );
}
