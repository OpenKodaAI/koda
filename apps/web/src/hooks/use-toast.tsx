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

export type Toast = {
  id: string;
  title?: string;
  message: string;
  type: ToastType;
  durationMs: number;
};

export type ShowToastOptions = {
  title?: string;
  durationMs?: number;
};

type ToastContextValue = {
  toasts: Toast[];
  showToast: (
    message: string,
    type?: ToastType,
    options?: ShowToastOptions,
  ) => void;
  removeToast: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

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

  const removeToast = useCallback((id: string) => {
    const timer = timersRef.current[id];
    if (timer) {
      window.clearTimeout(timer);
      delete timersRef.current[id];
    }

    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (
      message: string,
      type: ToastType = "info",
      options: ShowToastOptions = {},
    ) => {
      const id = crypto.randomUUID();
      const toast: Toast = {
        id,
        title: options.title,
        message,
        type,
        durationMs:
          options.durationMs ?? (type === "loading" ? 3200 : 5200),
      };

      setToasts((prev) => [...prev, toast]);

      timersRef.current[id] = window.setTimeout(() => {
        removeToast(id);
      }, toast.durationMs);
    },
    [removeToast],
  );

  const contextValue = useMemo(
    () => ({
      toasts,
      showToast,
      removeToast,
    }),
    [removeToast, showToast, toasts],
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
