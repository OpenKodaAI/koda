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
import { safeRedirectTarget } from "@/lib/safe-redirect";

/**
 * The auth contract (see `apps/web/CLAUDE.md`) folds every 4xx auth failure —
 * wrong password, unknown user, rate-limited, expired session — into ONE
 * generic message so timing/enumeration attacks gain no signal. Only
 * infrastructure failures (5xx, no response, network error) surface as a
 * distinct "service unavailable" message so the operator can tell it isn't
 * their credentials.
 */
function isUpstreamFailure(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status >= 500 || error.status === 0;
  }
  // Network failure (fetch threw before producing a Response) — treat as
  // service unavailable so the operator doesn't blame their password.
  return true;
}

export function LoginScreen() {
  const { t } = useAppI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!identifier.trim() || !password) {
      setError(t("auth.login.generic_error"));
      return;
    }
    setBusy(true);
    try {
      await requestJson("/api/control-plane/auth/login", {
        method: "POST",
        body: JSON.stringify({ identifier: identifier.trim(), password }),
      });
      const target = safeRedirectTarget(searchParams.get("next"));
      // replace (not push) so /login?next=X never sits in the back stack;
      // refresh invalidates the RSC payload so AuthProvider hydrates with
      // the new operator on the first paint.
      router.replace(target);
      router.refresh();
    } catch (error) {
      if (isUpstreamFailure(error)) {
        setError(
          t("auth.login.service_unavailable", {
            defaultValue:
              "Sign-in service is temporarily unavailable. Please try again in a moment.",
          }),
        );
      } else {
        // Generic message — never reveal whether the account exists.
        setError(t("auth.login.generic_error"));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <SetupFrame>
      <form onSubmit={handleSubmit} className="auth-form" noValidate>
        <div className="auth-form__hero">
          <KodaMark className="auth-form__logo" />
          <div className="auth-form__title-block">
            <h1 className="auth-form__title">{t("auth.login.title")}</h1>
            <p className="auth-form__subtitle">{t("auth.login.subtitle")}</p>
          </div>
        </div>

        <div className="auth-form__fields">
          <label className="auth-field" htmlFor="login-identifier">
            <span className="auth-field__label">{t("auth.login.identifier")}</span>
            <Input
              id="login-identifier"
              type="text"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              autoComplete="username"
              autoFocus
              disabled={busy}
              placeholder="owner@yourdomain.com"
              className="auth-input"
            />
          </label>
          <label className="auth-field" htmlFor="login-password">
            <span className="auth-field__label">{t("auth.login.password")}</span>
            <Input
              id="login-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
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
          aria-label={busy ? t("auth.login.submitting") : undefined}
          aria-busy={busy || undefined}
          className="auth-submit"
        >
          {busy ? (
            <InlineSpinner className="h-4 w-4" />
          ) : (
            t("auth.login.submit")
          )}
        </Button>

        <div className="text-center">
          <Link
            href="/forgot-password"
            className="text-[12px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
          >
            {t("auth.login.forgot_link")}
          </Link>
        </div>
      </form>
    </SetupFrame>
  );
}
