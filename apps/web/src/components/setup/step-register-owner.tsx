"use client";

import { useState, type FormEvent } from "react";
import { ArrowRight, Eye, EyeOff, UserCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { Input } from "@/components/ui/input";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson } from "@/lib/http-client";
import { cn } from "@/lib/utils";

interface StepRegisterOwnerProps {
  registrationToken: string;
  initialEmail?: string | null;
  initialDisplayName?: string | null;
  onRegistered: () => void;
}

interface DashboardAuthResponse {
  ok: boolean;
  operator?: {
    username?: string | null;
    email?: string | null;
    display_name?: string | null;
  } | null;
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function StepRegisterOwner({
  registrationToken,
  initialEmail,
  initialDisplayName,
  onRegistered,
}: StepRegisterOwnerProps) {
  const { t } = useAppI18n();
  const [displayName, setDisplayName] = useState(initialDisplayName ?? "");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState(initialEmail ?? "");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<"email" | "password" | "username", string>>>(
    {},
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    const trimmedUsername = username.trim();
    const trimmedEmail = email.trim();
    const nextFieldErrors: typeof fieldErrors = {};

    if (!trimmedUsername) {
      nextFieldErrors.username = t("setup.errors.usernameRequired");
    }
    if (!EMAIL_REGEX.test(trimmedEmail)) {
      nextFieldErrors.email = t("setup.errors.emailInvalid");
    }
    if (password.length < 8) {
      nextFieldErrors.password = t("setup.errors.passwordTooShort");
    }

    if (Object.keys(nextFieldErrors).length) {
      setFieldErrors(nextFieldErrors);
      return;
    }

    setBusy(true);
    try {
      await requestJson<DashboardAuthResponse>("/api/control-plane/auth/register-owner", {
        method: "POST",
        body: JSON.stringify({
          registration_token: registrationToken,
          username: trimmedUsername,
          email: trimmedEmail,
          password,
          display_name: displayName.trim(),
        }),
      });
      onRegistered();
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
          <UserCircle className="icon-sm" />
        </span>
        <h1 className="m-0 text-[var(--font-size-display-sm)] font-medium leading-[1.15] tracking-[var(--tracking-display)] text-[var(--text-primary)]">
          {t("setup.registerOwner.title")}
        </h1>
        <p className="m-0 max-w-[360px] text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
          {t("setup.registerOwner.subtitle")}
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <LabelledInput
          label={t("setup.registerOwner.displayName")}
          optional
          value={displayName}
          onChange={setDisplayName}
          disabled={busy}
          autoComplete="name"
        />
        <LabelledInput
          label={t("setup.registerOwner.username")}
          value={username}
          onChange={setUsername}
          disabled={busy}
          autoComplete="username"
          error={fieldErrors.username}
        />
        <LabelledInput
          label={t("setup.registerOwner.email")}
          type="email"
          value={email}
          onChange={setEmail}
          disabled={busy}
          autoComplete="email"
          error={fieldErrors.email}
        />
        <LabelledInput
          label={t("setup.registerOwner.password")}
          type={showPassword ? "text" : "password"}
          value={password}
          onChange={setPassword}
          disabled={busy}
          autoComplete="new-password"
          error={fieldErrors.password}
          suffix={
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? t("setup.registerOwner.hidePassword") : t("setup.registerOwner.showPassword")}
              className="inline-flex h-6 w-6 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-quaternary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-secondary)]"
            >
              {showPassword ? <EyeOff className="icon-sm" /> : <Eye className="icon-sm" />}
            </button>
          }
        />
      </div>

      {error ? <InlineAlert tone="danger">{error}</InlineAlert> : null}

      <Button
        type="submit"
        variant="accent"
        size="lg"
        disabled={busy}
        className="w-full"
      >
        {busy ? t("setup.registerOwner.submitting") : t("setup.registerOwner.submit")}
        {!busy ? <ArrowRight className="icon-sm ms-1" /> : null}
      </Button>
    </form>
  );
}

function LabelledInput({
  label,
  optional,
  value,
  onChange,
  disabled,
  type = "text",
  autoComplete,
  error,
  suffix,
}: {
  label: string;
  optional?: boolean;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  type?: string;
  autoComplete?: string;
  error?: string;
  suffix?: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-center justify-between text-[0.75rem] font-medium text-[var(--text-secondary)]">
        {label}
        {optional ? (
          <span className="text-[0.6875rem] text-[var(--text-quaternary)]">optional</span>
        ) : null}
      </span>
      <div className="relative">
        <Input
          sizeVariant="md"
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          autoComplete={autoComplete}
          invalid={Boolean(error)}
          className={cn(suffix ? "pe-10" : undefined)}
        />
        {suffix ? (
          <span className="absolute end-2 top-1/2 -translate-y-1/2">{suffix}</span>
        ) : null}
      </div>
      {error ? (
        <span className="text-[0.6875rem] text-[var(--tone-danger-dot)]">{error}</span>
      ) : null}
    </label>
  );
}
