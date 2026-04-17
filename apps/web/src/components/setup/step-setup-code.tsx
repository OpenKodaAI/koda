"use client";

import { useState, type FormEvent } from "react";
import { ArrowUp, KeyRound, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson } from "@/lib/http-client";
import { cn } from "@/lib/utils";

interface StepSetupCodeProps {
  onExchanged: (registrationToken: string, expiresAt: string | null) => void;
  onRecoverySession: () => void;
}

interface BootstrapExchangeResponse {
  ok: boolean;
  registration_token: string;
  expires_at?: string | null;
}

export function StepSetupCode({ onExchanged, onRecoverySession }: StepSetupCodeProps) {
  const { t } = useAppI18n();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useRecovery, setUseRecovery] = useState(false);
  const [recoveryToken, setRecoveryToken] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const trimmed = code.trim();
    if (!trimmed) {
      setError(t("setup.errors.codeRequired"));
      return;
    }
    setBusy(true);
    try {
      const payload = await requestJson<BootstrapExchangeResponse>(
        "/api/control-plane/auth/bootstrap/exchange",
        {
          method: "POST",
          body: JSON.stringify({ code: trimmed }),
        },
      );
      onExchanged(payload.registration_token, payload.expires_at ?? null);
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : t("setup.errors.codeInvalid"),
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleRecoverySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const trimmed = recoveryToken.trim();
    if (!trimmed) {
      setError(t("setup.errors.codeRequired"));
      return;
    }
    setBusy(true);
    try {
      await requestJson("/api/control-plane/web-auth", {
        method: "POST",
        body: JSON.stringify({ token: trimmed }),
      });
      onRecoverySession();
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : t("setup.errors.generic"),
      );
    } finally {
      setBusy(false);
    }
  }

  if (useRecovery) {
    return (
      <form onSubmit={handleRecoverySubmit} className="flex flex-col gap-5" noValidate>
        <div className="flex flex-col items-center gap-2 text-center">
          <h1 className="m-0 text-[var(--font-size-display-sm)] font-medium leading-[1.15] tracking-[var(--tracking-display)] text-[var(--text-primary)]">
            {t("setup.recoveryToken.title")}
          </h1>
          <p className="m-0 max-w-[360px] text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
            {t("setup.recoveryToken.subtitle")}
          </p>
        </div>

        <InlineSubmitField
          value={recoveryToken}
          onChange={setRecoveryToken}
          placeholder={t("setup.recoveryToken.placeholder")}
          busy={busy}
          ariaLabel={t("setup.recoveryToken.title")}
          submitLabel={t("setup.recoveryToken.submit")}
          autoComplete="off"
        />

        {error ? <InlineAlert tone="danger">{error}</InlineAlert> : null}

        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="w-full"
          onClick={() => {
            setUseRecovery(false);
            setError(null);
          }}
        >
          {t("setup.recoveryToken.backToSetupCode")}
        </Button>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
      <div className="flex flex-col items-center gap-2 text-center">
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[var(--accent)]">
          <KeyRound className="icon-sm" />
        </span>
        <h1 className="m-0 text-[var(--font-size-display-sm)] font-medium leading-[1.15] tracking-[var(--tracking-display)] text-[var(--text-primary)]">
          {t("setup.setupCode.title")}
        </h1>
        <p className="m-0 max-w-[360px] text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
          {t("setup.setupCode.subtitle")}
        </p>
      </div>

      <InlineSubmitField
        value={code}
        onChange={(value) => setCode(value.toUpperCase())}
        placeholder={t("setup.setupCode.placeholder")}
        busy={busy}
        ariaLabel={t("setup.setupCode.title")}
        submitLabel={t("setup.setupCode.submit")}
        mono
        autoComplete="one-time-code"
      />

      {error ? <InlineAlert tone="danger">{error}</InlineAlert> : null}

      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="w-full"
        onClick={() => {
          setUseRecovery(true);
          setError(null);
        }}
      >
        {t("setup.setupCode.recoveryLink")}
      </Button>
    </form>
  );
}

interface InlineSubmitFieldProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  busy?: boolean;
  disabled?: boolean;
  ariaLabel: string;
  submitLabel: string;
  mono?: boolean;
  autoComplete?: string;
  type?: string;
}

export function InlineSubmitField({
  value,
  onChange,
  placeholder,
  busy = false,
  disabled,
  ariaLabel,
  submitLabel,
  mono = false,
  autoComplete,
  type = "text",
}: InlineSubmitFieldProps) {
  const canSubmit = Boolean(value.trim()) && !busy;
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2",
        "transition-[border-color,background-color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        "focus-within:border-[var(--accent)] focus-within:bg-[var(--panel)]",
      )}
    >
      <input
        type={type}
        autoFocus
        autoComplete={autoComplete}
        autoCorrect="off"
        spellCheck={false}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        disabled={busy || disabled}
        className={cn(
          "min-h-[32px] w-full bg-transparent px-1 text-[0.9375rem] leading-[1.4] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-quaternary)]",
          mono && "font-mono tracking-[0.14em]",
        )}
      />
      <button
        type="submit"
        disabled={!canSubmit}
        aria-label={submitLabel}
        className={cn(
          "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] border border-transparent transition-[background-color,border-color,color,transform] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
          "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel-soft)]",
          canSubmit
            ? "bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] active:scale-[0.96]"
            : "bg-[var(--surface-hover)] text-[var(--text-quaternary)]",
        )}
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
      </button>
    </div>
  );
}
