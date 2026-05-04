"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ToastType = "success" | "error" | "info" | "warning" | "loading";

export type ToastProgress = {
  downloaded: number;
  total: number;
  label?: string;
};

export type Toast = {
  id: string;
  title?: string;
  message: string;
  type: ToastType;
  durationMs: number;
  /** When true, the toast does NOT auto-dismiss and the close button is hidden. */
  persistent?: boolean;
  /** Renders a progress bar inside the toast when present. `total = 0` is rendered as indeterminate. */
  progress?: ToastProgress;
  /** Whether the close button is rendered. Defaults to !persistent. */
  dismissible?: boolean;
  action?: {
    label: string;
    onClick: () => void;
    disabled?: boolean;
    ariaLabel?: string;
  };
};

export type ShowToastOptions = {
  /** Stable id — pass to target the same toast across `updateToast` calls. */
  id?: string;
  title?: string;
  durationMs?: number;
  persistent?: boolean;
  progress?: ToastProgress;
  dismissible?: boolean;
  action?: Toast["action"];
};

type ToastContextValue = {
  toasts: Toast[];
  /** Returns the (stable or generated) id so callers can target it via updateToast. */
  showToast: (
    message: string,
    type?: ToastType,
    options?: ShowToastOptions,
  ) => string;
  /** Patch any subset of fields on an existing toast (no-op if id missing). */
  updateToast: (id: string, partial: Partial<Toast>) => void;
  removeToast: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const DEFAULT_DURATION_BY_TYPE: Record<ToastType, number> = {
  success: 5200,
  error: 5200,
  info: 5200,
  warning: 5200,
  loading: 3200,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Record<string, number>>({});

  useEffect(() => {
    const timers = timersRef.current;

    return () => {
      Object.values(timers).forEach((timer) => {
        window.clearTimeout(timer);
      });
    };
  }, []);

  const clearTimerFor = useCallback((id: string) => {
    const timer = timersRef.current[id];
    if (timer) {
      window.clearTimeout(timer);
      delete timersRef.current[id];
    }
  }, []);

  const removeToast = useCallback(
    (id: string) => {
      clearTimerFor(id);
      setToasts((prev) => prev.filter((t) => t.id !== id));
    },
    [clearTimerFor],
  );

  const scheduleDismiss = useCallback(
    (id: string, durationMs: number) => {
      clearTimerFor(id);
      timersRef.current[id] = window.setTimeout(() => removeToast(id), durationMs);
    },
    [clearTimerFor, removeToast],
  );

  const showToast = useCallback(
    (
      message: string,
      type: ToastType = "info",
      options: ShowToastOptions = {},
    ): string => {
      const id = options.id ?? crypto.randomUUID();
      const persistent = options.persistent === true;
      const dismissible = options.dismissible ?? !persistent;
      const durationMs =
        options.durationMs ?? DEFAULT_DURATION_BY_TYPE[type];
      const toast: Toast = {
        id,
        title: options.title,
        message,
        type,
        durationMs,
        persistent,
        progress: options.progress,
        dismissible,
        action: options.action,
      };

      setToasts((prev) => {
        // Stable id may target an existing toast; replace in place so a
        // re-render of the source component doesn't spawn duplicates.
        const existingIndex = prev.findIndex((t) => t.id === id);
        if (existingIndex >= 0) {
          const next = [...prev];
          next[existingIndex] = toast;
          return next;
        }
        return [...prev, toast];
      });

      if (!persistent) {
        scheduleDismiss(id, durationMs);
      } else {
        clearTimerFor(id);
      }
      return id;
    },
    [clearTimerFor, scheduleDismiss],
  );

  const updateToast = useCallback(
    (id: string, partial: Partial<Toast>) => {
      setToasts((prev) => {
        const idx = prev.findIndex((t) => t.id === id);
        if (idx < 0) return prev;
        const merged: Toast = { ...prev[idx], ...partial, id };
        const next = [...prev];
        next[idx] = merged;
        // Auto-dismiss handling: if the toast just transitioned away from
        // persistent (e.g. download completed), schedule a dismiss.
        if (prev[idx].persistent === true && merged.persistent !== true) {
          scheduleDismiss(id, merged.durationMs);
        } else if (prev[idx].persistent !== true && merged.persistent === true) {
          // Switching INTO persistent should clear any pending auto-dismiss.
          clearTimerFor(id);
        }
        return next;
      });
    },
    [clearTimerFor, scheduleDismiss],
  );

  const contextValue = useMemo(
    () => ({
      toasts,
      showToast,
      updateToast,
      removeToast,
    }),
    [removeToast, showToast, toasts, updateToast],
  );

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
