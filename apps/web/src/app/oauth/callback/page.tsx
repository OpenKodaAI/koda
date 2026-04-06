"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { requestJson } from "@/lib/http-client";

type OAuthCallbackResponse = {
  success: boolean;
  server_key?: string;
  agent_id?: string;
  provider_account_label?: string;
  error?: string;
};

type CallbackState = {
  status: "idle" | "loading" | "success" | "error";
  message: string;
  error: string | null;
};

function parseServerKeyFromWindowName() {
  if (typeof window === "undefined") return "";
  const prefix = "koda-oauth:";
  if (window.name.startsWith(prefix)) {
    return window.name.slice(prefix.length).trim();
  }
  return "";
}

export default function OAuthCallbackPage() {
  const searchParams = useSearchParams();
  const code = searchParams.get("code") || "";
  const state = searchParams.get("state") || "";
  const error = searchParams.get("error") || "";
  const errorDescription = searchParams.get("error_description") || "";
  const serverKeyFromQuery = searchParams.get("server_key") || "";
  const [callbackState, setCallbackState] = useState<CallbackState>(() => {
    if (error) {
      const message = errorDescription || error;
      return { status: "error", message, error: message };
    }
    if (!code || !state) {
      return {
        status: "idle",
        message: "Aguardando os parametros de autenticacao...",
        error: null,
      };
    }
    return {
      status: "loading",
      message: "Concluindo a autenticacao...",
      error: null,
    };
  });
  const [serverKeyFromPopup] = useState(() =>
    typeof window === "undefined" ? "" : parseServerKeyFromWindowName(),
  );
  const [hasOpener] = useState(
    () => typeof window !== "undefined" && Boolean(window.opener),
  );

  const serverKey = useMemo(
    () => serverKeyFromQuery || serverKeyFromPopup,
    [serverKeyFromPopup, serverKeyFromQuery],
  );

  useEffect(() => {
    let isActive = true;
    let closeTimer: ReturnType<typeof setTimeout> | null = null;

    const notifyParent = (payload: OAuthCallbackResponse & { status: "success" | "error" }) => {
      if (!hasOpener || !window.opener) return;
      window.opener.postMessage(
        {
          type: "koda:oauth:callback",
          status: payload.status,
          serverKey: payload.server_key || serverKey,
          agentId: payload.agent_id || "",
          error: payload.error || "",
        },
        window.location.origin,
      );
    };

    const finishWithError = (message: string) => {
      if (!isActive) return;
      setCallbackState({ status: "error", message, error: message });
      notifyParent({ success: false, status: "error", error: message });
    };

    const finishWithSuccess = (payload: OAuthCallbackResponse) => {
      if (!isActive) return;
      const providerLabel = payload.provider_account_label
        ? ` ${payload.provider_account_label}`
        : "";
      const message = `Conectado com sucesso${providerLabel}`.trim();
      setCallbackState({ status: "success", message, error: null });
      notifyParent({
        ...payload,
        status: "success",
      });
      closeTimer = setTimeout(() => window.close(), 1200);
    };

    if (error) {
      finishWithError(errorDescription || error);
      return () => {
        isActive = false;
        if (closeTimer) clearTimeout(closeTimer);
      };
    }

    if (!code || !state) {
      return () => {
        isActive = false;
        if (closeTimer) clearTimeout(closeTimer);
      };
    }

    void (async () => {
      try {
        const payload = await requestJson<OAuthCallbackResponse>(
          `/api/control-plane/connections/oauth/callback?state=${encodeURIComponent(state)}&code=${encodeURIComponent(code)}`,
        );
        if (!payload.success) {
          finishWithError(payload.error || "Falha ao concluir autenticacao.");
          return;
        }
        finishWithSuccess(payload);
      } catch (err) {
        finishWithError(err instanceof Error ? err.message : "Falha ao concluir autenticacao.");
      }
    })();

    return () => {
      isActive = false;
      if (closeTimer) clearTimeout(closeTimer);
    };
  }, [code, error, errorDescription, hasOpener, serverKey, state]);

  const icon =
    callbackState.status === "success" ? (
      <CheckCircle2 size={48} className="text-[var(--tone-success-dot)]" />
    ) : callbackState.status === "error" ? (
      <XCircle size={48} className="text-[var(--tone-danger-dot)]" />
    ) : (
      <Loader2 size={32} className="animate-spin text-[var(--icon-secondary)]" />
    );

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--surface-base)] px-6 text-[var(--text-primary)]">
      <div className="flex w-full max-w-md flex-col items-center gap-4 rounded-[1.25rem] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-8 py-10 text-center">
        {icon}
        <p className="text-lg font-semibold">{callbackState.message}</p>
        {serverKey ? (
          <p className="text-xs text-[var(--text-quaternary)]">
            {serverKey}
          </p>
        ) : null}
        {callbackState.error ? (
          <p className="text-sm text-[var(--text-secondary)]">{callbackState.error}</p>
        ) : null}
        <p className="text-xs text-[var(--text-quaternary)]">
          {hasOpener ? "Fechando esta janela..." : "Você pode fechar esta janela manualmente."}
        </p>
        <button
          type="button"
          onClick={() => window.close()}
          className="mt-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
        >
          Fechar
        </button>
      </div>
    </div>
  );
}
