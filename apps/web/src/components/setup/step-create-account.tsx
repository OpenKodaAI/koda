"use client";

import { type FormEvent, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { KodaMark } from "@/components/layout/koda-mark";
import { BootstrapCodeInput } from "@/components/setup/bootstrap-code-input";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { Input } from "@/components/ui/input";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson } from "@/lib/http-client";

export interface StepCreateAccountProps {
  loopbackTrustEnabled: boolean;
  bootstrapFilePath: string | null;
  onRegistered: (result: RegisterOwnerResponse) => void;
}

export interface RegisterOwnerResponse {
  ok: boolean;
  recovery_codes: string[];
  operator: {
    id?: string | null;
    username?: string | null;
    email?: string | null;
    display_name?: string | null;
  } | null;
  auth: unknown;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_LENGTH = 12;

function scorePassword(password: string): { score: number; label: string; toneClass: string } {
  if (!password) {
    return { score: 0, label: "", toneClass: "bg-[var(--surface-hover)]" };
  }
  let score = 0;
  if (password.length >= MIN_LENGTH) score += 1;
  if (password.length >= 16) score += 1;
  const classes = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^a-zA-Z0-9]/].filter((rule) => rule.test(password)).length;
  score += Math.max(0, classes - 1);
  const unique = new Set(password).size;
  if (unique >= 8) score += 1;
  // 0-1 weak, 2-3 fair, 4-5 good, 6+ strong
  if (score <= 1) return { score: 1, label: "weak", toneClass: "bg-[var(--tone-danger-bg-strong)]" };
  if (score <= 3) return { score: 2, label: "fair", toneClass: "bg-[var(--tone-warning-bg-strong)]" };
  if (score <= 5) return { score: 3, label: "good", toneClass: "bg-[var(--tone-info-bg-strong)]" };
  return { score: 4, label: "strong", toneClass: "bg-[var(--tone-success-bg-strong)]" };
}

export function StepCreateAccount({
  loopbackTrustEnabled,
  bootstrapFilePath,
  onRegistered,
}: StepCreateAccountProps) {
  const { t } = useAppI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [bootstrapCode, setBootstrapCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const passwordMeter = useMemo(() => scorePassword(password), [password]);
  // The field is always visible so operators running behind a reverse proxy or
  // docker-compose can always paste their code. When the control plane reports
  // loopback trust, the code is optional — the server will fall back to
  // loopback-trust when the field is empty.
  const bootstrapCodeOptional = loopbackTrustEnabled;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Guard against React double-invocation / user double-click while the
    // previous request is still in flight.
    if (busy) return;
    setError(null);
    const trimmedEmail = email.trim();
    if (!EMAIL_RE.test(trimmedEmail)) {
      setError(t("auth.setup.create_account.errors.email_invalid"));
      return;
    }
    if (password.length < MIN_LENGTH) {
      setError(t("auth.setup.create_account.errors.password_too_short", { n: MIN_LENGTH }));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("auth.setup.create_account.errors.password_mismatch"));
      return;
    }
    if (!bootstrapCodeOptional && !bootstrapCode.trim()) {
      setError(t("auth.setup.create_account.errors.bootstrap_required"));
      return;
    }
    setBusy(true);
    try {
      const payload = await requestJson<RegisterOwnerResponse>(
        "/api/control-plane/auth/register-owner",
        {
          method: "POST",
          body: JSON.stringify({
            email: trimmedEmail,
            password,
            bootstrap_code: bootstrapCode.trim(),
          }),
        },
      );
      onRegistered(payload);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : t("auth.setup.create_account.errors.generic"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="auth-form" noValidate>
      <div className="auth-form__hero">
        <KodaMark className="auth-form__logo" />
        <div className="auth-form__title-block">
          <h1 className="auth-form__title">{t("auth.setup.create_account.title")}</h1>
          <p className="auth-form__subtitle">{t("auth.setup.create_account.subtitle")}</p>
        </div>
      </div>

      <div className="auth-form__fields">
        <Field label={t("auth.setup.create_account.email")} htmlFor="setup-email">
          <Input
            id="setup-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            autoFocus
            disabled={busy}
            placeholder="owner@yourdomain.com"
            className="auth-input"
          />
        </Field>

        <Field label={t("auth.setup.create_account.password")} htmlFor="setup-password">
          <Input
            id="setup-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            disabled={busy}
            placeholder={t("auth.setup.create_account.password_hint", { n: MIN_LENGTH })}
            className="auth-input"
          />
          {password ? (
            <div className="mt-2 flex items-center gap-2">
              <div className="relative h-1 flex-1 overflow-hidden rounded-full bg-[var(--surface-hover)]">
                <div
                  className={`absolute inset-y-0 left-0 ${passwordMeter.toneClass} transition-[width] duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]`}
                  style={{ width: `${Math.min(100, passwordMeter.score * 25)}%` }}
                />
              </div>
              <span className="text-[10.5px] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                {t(`auth.setup.create_account.strength.${passwordMeter.label}`)}
              </span>
            </div>
          ) : null}
        </Field>

        <Field label={t("auth.setup.create_account.confirm_password")} htmlFor="setup-confirm">
          <Input
            id="setup-confirm"
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            autoComplete="new-password"
            disabled={busy}
            placeholder="••••••••••••"
            className="auth-input"
          />
        </Field>

        <Field
          label={t("auth.setup.create_account.bootstrap_code")}
          htmlFor="setup-bootstrap"
          hint={
            bootstrapFilePath
              ? t("auth.setup.create_account.bootstrap_hint", { path: bootstrapFilePath })
              : t("auth.setup.create_account.bootstrap_hint_generic")
          }
        >
          <BootstrapCodeInput
            id="setup-bootstrap"
            value={bootstrapCode}
            onChange={setBootstrapCode}
            disabled={busy}
            ariaLabel={t("auth.setup.create_account.bootstrap_code")}
          />
        </Field>
      </div>

      {error ? <InlineAlert tone="danger">{error}</InlineAlert> : null}

      <Button
        type="submit"
        variant="accent"
        size="lg"
        disabled={busy}
        className="auth-submit"
      >
        {busy ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>{t("auth.setup.create_account.submitting")}</span>
          </>
        ) : (
          t("auth.setup.create_account.submit")
        )}
      </Button>
    </form>
  );
}

interface FieldProps {
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}

function Field({ label, htmlFor, hint, children }: FieldProps) {
  return (
    <label className="auth-field" htmlFor={htmlFor}>
      <span className="auth-field__label">{label}</span>
      {children}
      {hint ? <span className="auth-field__hint">{hint}</span> : null}
    </label>
  );
}
