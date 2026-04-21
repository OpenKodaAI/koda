"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Loader2 } from "lucide-react";
import { KodaMark } from "@/components/layout/koda-mark";
import { SetupFrame } from "@/components/setup/setup-frame";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { Input } from "@/components/ui/input";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson } from "@/lib/http-client";

export function LoginScreen() {
  const { t } = useAppI18n();
  const router = useRouter();
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
      router.replace("/");
      router.refresh();
    } catch {
      // Always show the generic message — never reveal whether the account exists.
      setError(t("auth.login.generic_error"));
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
          className="auth-submit"
        >
          {busy ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{t("auth.login.submitting")}</span>
            </>
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
