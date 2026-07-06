"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import type { ControlPlaneAuthStatus } from "@/lib/control-plane";
import { isSafeRedirectTarget } from "@/lib/safe-redirect";

export const FORCE_SIGN_OUT_EVENT = "koda:force-sign-out";

export type ForceSignOutDetail = {
  /** GET = silent redirect; MUTATION = toast + redirect (data was being written). */
  method: "GET" | "MUTATION";
  /** Pre-redirect path the operator was on (round-tripped via `?next=`). */
  pathname: string;
};

export type AuthOperator = NonNullable<ControlPlaneAuthStatus["operator"]>;

type ClientOverride = "signed-out" | null;

type AuthContextValue = {
  operator: AuthOperator | null;
  isAuthenticated: boolean;
  signOut: () => Promise<void>;
  updateOperator: (operator: AuthOperator) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export interface AuthProviderProps {
  initialAuth: ControlPlaneAuthStatus | null;
  children: ReactNode;
}

export function AuthProvider({ initialAuth, children }: AuthProviderProps) {
  const router = useRouter();
  const { showToast } = useToast();
  const { t } = useAppI18n();
  // The operator is derived from the server-rendered `initialAuth` prop. The
  // only client-side override is "signed-out" (sign-out button or 401 event).
  // The override is short-lived: both branches that set it navigate to /login,
  // which unmounts the AuthProvider (login lives outside AppShell's dashboard
  // tree). On the next sign-in, the provider remounts with override = null.
  const [override, setOverride] = useState<ClientOverride>(null);
  const [clientAuth, setClientAuth] = useState<ControlPlaneAuthStatus | null>(null);
  const [operatorOverride, setOperatorOverride] = useState<AuthOperator | null>(null);
  const operator =
    override === "signed-out"
      ? null
      : (operatorOverride ?? initialAuth?.operator ?? clientAuth?.operator ?? null);

  const signOut = useCallback(async () => {
    setOverride("signed-out");
    setOperatorOverride(null);
    router.replace("/login");
    router.refresh();
    try {
      await fetch("/api/control-plane/auth/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
    } catch {
      // Ignore upstream failures — the proxy will hard-clear the cookie on
      // the next request whether or not the upstream POST succeeded.
    }
  }, [router]);

  const updateOperator = useCallback(
    (nextOperator: AuthOperator) => {
      setOperatorOverride(nextOperator);
      setClientAuth((current) => ({
        ...(current ?? initialAuth ?? {
          authenticated: true,
          has_owner: true,
          bootstrap_required: false,
          auth_mode: "local_account",
          session_required: true,
          recovery_available: false,
        }),
        authenticated: true,
        operator: nextOperator,
      }));
      router.refresh();
    },
    [initialAuth, router],
  );

  useEffect(() => {
    function handleForceSignOut(event: Event) {
      const detail = (event as CustomEvent<ForceSignOutDetail>).detail;
      if (!detail) return;
      setOverride("signed-out");
      if (detail.method === "MUTATION") {
        showToast(t("auth.session_expired"), "warning", {
          id: "auth.session_expired",
          durationMs: 6000,
        });
      }
      const safeNext = isSafeRedirectTarget(detail.pathname)
        ? detail.pathname
        : null;
      const target = safeNext
        ? `/login?next=${encodeURIComponent(safeNext)}`
        : "/login";
      router.replace(target);
      router.refresh();
    }

    window.addEventListener(FORCE_SIGN_OUT_EVENT, handleForceSignOut);
    return () => {
      window.removeEventListener(FORCE_SIGN_OUT_EVENT, handleForceSignOut);
    };
  }, [router, showToast, t]);

  useEffect(() => {
    if (override === "signed-out" || initialAuth?.operator || clientAuth?.operator) {
      return;
    }

    let cancelled = false;
    void fetch("/api/control-plane/auth/status", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) return null;
        return (await response.json()) as ControlPlaneAuthStatus;
      })
      .then((status) => {
        if (!cancelled && status?.authenticated) {
          setClientAuth(status);
        }
      })
      .catch(() => {
        // A transient auth-status miss should not interrupt an otherwise valid
        // dashboard render; the next navigation/focus can try again.
      });

    return () => {
      cancelled = true;
    };
  }, [clientAuth?.operator, initialAuth?.operator, override]);

  const value = useMemo<AuthContextValue>(
    () => ({
      operator,
      isAuthenticated: Boolean(operator),
      signOut,
      updateOperator,
    }),
    [operator, signOut, updateOperator],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

/** Read auth state without throwing if no provider exists (e.g. on `/login`). */
export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext);
}
