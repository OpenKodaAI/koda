"use client";

import { useState, type FormEvent } from "react";
import { ArrowUp, Eye, EyeOff, Loader2, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { Input } from "@/components/ui/input";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson } from "@/lib/http-client";
import { cn } from "@/lib/utils";

interface StepLoginProps {
  initialIdentifier?: string | null;
  recoveryAvailable?: boolean;
  onSignedIn: () => void;
  onRecoveryRequested: () => void;
}

export function StepLogin({
  initialIdentifier,
  recoveryAvailable,
  onSignedIn,
  onRecoveryRequested,
}: StepLoginProps) {
  const { t } = useAppI18n();
  const [identifier, setIdentifier] = useState(initialIdentifier ?? "");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = Boolean(identifier.trim()) && Boolean(password) && !busy;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!identifier.trim() || !password) {
      setError(t("setup.errors.credentialsRequired"));
      return;
    }
    setBusy(true);
    try {
      await requestJson("/api/control-plane/auth/login", {
        method: "POST",
        body: JSON.stringify({ identifier: identifier.trim(), password }),
      });
      onSignedIn();
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : t("setup.errors.generic"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
      <div className="flex flex-col items-center gap-2 text-center">
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[var(--accent)]">
          <LogIn className="icon-sm" />
        </span>
        <h1 className="m-0 text-[var(--font-size-display-sm)] font-medium leading-[1.15] tracking-[var(--tracking-display)] text-[var(--text-primary)]">
          {t("setup.login.title")}
        </h1>
        <p className="m-0 max-w-[360px] text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
          {t("setup.login.subtitle")}
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="text-[0.75rem] font-medium text-[var(--text-secondary)]">
            {t("setup.login.identifier")}
          </span>
          <Input
            sizeVariant="md"
            autoFocus
            autoComplete="username"
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            disabled={busy}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-[0.75rem] font-medium text-[var(--text-secondary)]">
            {t("setup.login.password")}
          </span>
          <div
            className={cn(
              "flex items-center gap-2 rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2",
              "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
              "focus-within:border-[var(--accent)] focus-within:bg-[var(--panel)]",
            )}
          >
            <input
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={busy}
              className="min-h-[32px] w-full bg-transparent px-1 text-[0.9375rem] leading-[1.4] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]"
            />
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={
                showPassword
                  ? t("setup.registerOwner.hidePassword")
                  : t("setup.registerOwner.showPassword")
              }
              className="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-quaternary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-secondary)]"
            >
              {showPassword ? <EyeOff className="icon-sm" /> : <Eye className="icon-sm" />}
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              aria-label={t("setup.login.submit")}
              className={cn(
                "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] border border-transparent transition-[background-color,border-color,color,transform] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel-soft)]",
                canSubmit
                  ? "bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] active:scale-[0.96]"
                  : "bg-[var(--surface-hover)] text-[var(--text-quaternary)]",
              )}
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowUp className="h-4 w-4" />
              )}
            </button>
          </div>
        </label>
      </div>

      {error ? <InlineAlert tone="danger">{error}</InlineAlert> : null}

      {recoveryAvailable ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="w-full"
          onClick={onRecoveryRequested}
        >
          {t("setup.login.recoveryLink")}
        </Button>
      ) : null}
    </form>
  );
}
