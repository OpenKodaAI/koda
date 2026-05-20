"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { KodaMark } from "@/components/layout/koda-mark";
import { SetupFrame } from "@/components/setup/setup-frame";
import { InlineSpinner } from "@/components/ui/async-feedback";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { Input } from "@/components/ui/input";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { ApiError } from "@/lib/errors";
import { requestJson } from "@/lib/http-client";
import { isSafeRedirectTarget } from "@/lib/safe-redirect";
import { translate } from "@/lib/i18n";

const MIN_LENGTH = 12;

// See LoginScreen — every 4xx auth failure is folded into one generic copy.
// Only infra failures (5xx / network) get a distinct message.
function isUpstreamFailure(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status >= 500 || error.status === 0;
  }
  return true;
}

export function ForgotPasswordScreen() {
  const { t } = useAppI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [identifier, setIdentifier] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!identifier.trim() || !recoveryCode.trim()) {
      setError(t("auth.forgot.generic_error"));
      return;
    }
    if (newPassword.length < MIN_LENGTH) {
      setError(t("auth.forgot.password_too_short", { n: MIN_LENGTH }));
      return;
    }
    if (newPassword !== confirmPassword) {
      setError(t("auth.forgot.password_mismatch"));
      return;
    }
    setBusy(true);
    try {
      await requestJson("/api/control-plane/auth/password/recover", {
        method: "POST",
        body: JSON.stringify({
          identifier: identifier.trim(),
          recovery_code: recoveryCode.trim(),
          new_password: newPassword,
        }),
      });
      setSuccess(true);
      const nextParam = searchParams.get("next");
      const loginTarget = isSafeRedirectTarget(nextParam)
        ? `/login?next=${encodeURIComponent(nextParam)}`
        : "/login";
      // Auto-redirect after a brief success banner.
      setTimeout(() => {
        router.replace(loginTarget);
      }, 2000);
    } catch (error) {
      if (isUpstreamFailure(error)) {
        setError(
          t("auth.forgot.service_unavailable", undefined),
        );
      } else {
        setError(t("auth.forgot.generic_error"));
      }
    } finally {
      setBusy(false);
    }
  }

  if (success) {
    return (
      <SetupFrame>
        <div className="auth-form__hero">
          <KodaMark className="auth-form__logo" />
          <div className="auth-form__title-block">
            <h1 className="auth-form__title">{t("auth.forgot.success_title")}</h1>
            <p className="auth-form__subtitle">{t("auth.forgot.success")}</p>
          </div>
        </div>
      </SetupFrame>
    );
  }

  return (
    <SetupFrame>
      <form onSubmit={handleSubmit} className="auth-form" noValidate>
        <div className="auth-form__hero">
          <KodaMark className="auth-form__logo" />
          <div className="auth-form__title-block">
            <h1 className="auth-form__title">{t("auth.forgot.title")}</h1>
            <p className="auth-form__subtitle">{t("auth.forgot.subtitle")}</p>
          </div>
        </div>

        <div className="auth-form__fields">
          <label className="auth-field" htmlFor="forgot-identifier">
            <span className="auth-field__label">{t("auth.forgot.identifier")}</span>
            <Input
              id="forgot-identifier"
              type="text"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              autoComplete="username"
              autoFocus
              disabled={busy}
              placeholder={translate("generated.account.owner_yourdomain_com_8d7a5b9d")}
              className="auth-input"
            />
          </label>
          <label className="auth-field" htmlFor="forgot-code">
            <span className="auth-field__label">{t("auth.forgot.recovery_code")}</span>
            <Input
              id="forgot-code"
              type="text"
              value={recoveryCode}
              onChange={(event) => setRecoveryCode(event.target.value.toLowerCase())}
              autoCorrect="off"
              spellCheck={false}
              disabled={busy}
              placeholder={translate("generated.account.xxxx_xxxx_xxxx_d457e3cb")}
              className="auth-input auth-input--mono"
            />
          </label>
          <label className="auth-field" htmlFor="forgot-new-password">
            <span className="auth-field__label">{t("auth.forgot.new_password")}</span>
            <Input
              id="forgot-new-password"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              autoComplete="new-password"
              disabled={busy}
              placeholder="••••••••••••"
              className="auth-input"
            />
          </label>
          <label className="auth-field" htmlFor="forgot-confirm">
            <span className="auth-field__label">{t("auth.forgot.confirm_password")}</span>
            <Input
              id="forgot-confirm"
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              autoComplete="new-password"
              disabled={busy}
              placeholder="••••••••••••"
              className="auth-input"
            />
          </label>
        </div>

        {error ? <InlineAlert tone="danger">{error}</InlineAlert> : null}

        <Button
          type="submit"
          variant="accent"
          size="lg"
          disabled={busy}
          aria-label={busy ? t("auth.forgot.submitting") : undefined}
          aria-busy={busy || undefined}
          className="auth-submit"
        >
          {busy ? (
            <InlineSpinner className="h-4 w-4" />
          ) : (
            t("auth.forgot.submit")
          )}
        </Button>

        <div className="text-center">
          <Link
            href="/login"
            className="text-[12px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
          >
            {t("auth.forgot.back_to_login")}
          </Link>
        </div>
      </form>
    </SetupFrame>
  );
}
