"use client";

import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";
import { CalendarClock, KeyRound, LoaderCircle, RefreshCcw, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { InlineAlert } from "@/components/ui/inline-alert";
import { Input } from "@/components/ui/input";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useToast } from "@/hooks/use-toast";
import { requestJson } from "@/lib/http-client";
import { formatDateTime } from "@/lib/utils";

interface RecoverySummary {
  total: number;
  remaining: number;
  generated_at: string | null;
}

function SecurityMetric({
  label,
  value,
  loading = false,
}: {
  label: string;
  value: ReactNode;
  loading?: boolean;
}) {
  return (
    <div className="min-w-0 bg-[var(--panel)] px-4 py-3">
      <p className="m-0 font-mono text-[0.625rem] uppercase leading-4 tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {label}
      </p>
      <div className="m-0 mt-1 min-h-5 text-[0.8125rem] leading-5 text-[var(--text-primary)]">
        {loading ? (
          <span className="inline-flex h-3 w-16 animate-pulse rounded bg-[var(--panel-soft)]" aria-label="Loading" />
        ) : (
          value
        )}
      </div>
    </div>
  );
}

function SecurityActionHeader({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--panel-soft)] text-[var(--text-tertiary)]">
        <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <h3 className="m-0 text-[0.875rem] font-medium text-[var(--text-primary)]">
          {title}
        </h3>
        <p className="m-0 mt-1 text-[0.75rem] leading-5 text-[var(--text-tertiary)]">
          {description}
        </p>
      </div>
    </div>
  );
}

export function SecuritySettingsCard() {
  const { t, tl } = useAppI18n();
  const { showToast } = useToast();
  const { runAction, isPending } = useAsyncAction();
  const [summary, setSummary] = useState<RecoverySummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [changeError, setChangeError] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const [regenError, setRegenError] = useState<string | null>(null);
  const [regenPassword, setRegenPassword] = useState("");
  const [regenCodes, setRegenCodes] = useState<string[] | null>(null);
  const loading = isPending("account.security.summary");
  const changeBusy = isPending("account.security.password");
  const regenBusy = isPending("account.security.recovery");

  const refreshSummary = useCallback(
    async (successMessage = tl("Security status updated.")) => {
      setLoadError(null);
      await runAction(
        "account.security.summary",
        () => requestJson<RecoverySummary>("/api/control-plane/auth/recovery-codes"),
        {
          successMessage,
          errorMessage: tl("Could not load security info."),
          onSuccess: (data) => {
            setSummary(data);
            setLoadError(null);
          },
          onError: (error) => {
            setLoadError(error.message);
          },
        },
      );
    },
    [runAction, tl],
  );

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void refreshSummary(tl("Security status loaded."));
    }, 0);
    return () => window.clearTimeout(handle);
  }, [refreshSummary, tl]);

  async function handleChangePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setChangeError(null);
    if (newPassword.length < 12) {
      const message = t("auth.forgot.password_too_short", { n: 12 });
      setChangeError(message);
      showToast(message, "warning");
      return;
    }

    await runAction(
      "account.security.password",
      () => requestJson("/api/control-plane/auth/password/change", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      }),
      {
        successMessage: tl("Password updated."),
        errorMessage: t("auth.forgot.generic_error"),
        onSuccess: () => {
          setCurrentPassword("");
          setNewPassword("");
        },
        onError: (error) => {
          setChangeError(error.message);
        },
      },
    );
  }

  async function handleRegenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRegenError(null);
    setRegenCodes(null);
    const data = await runAction(
      "account.security.recovery",
      () => requestJson<{ recovery_codes: string[] }>(
        "/api/control-plane/auth/recovery-codes/regenerate",
        {
          method: "POST",
          body: JSON.stringify({ current_password: regenPassword }),
        },
      ),
      {
        successMessage: tl("Recovery codes regenerated."),
        errorMessage: t("auth.forgot.generic_error"),
        onError: (error) => {
          setRegenError(error.message);
        },
      },
    );

    if (data) {
      setRegenCodes(data.recovery_codes || []);
      setRegenPassword("");
      await refreshSummary(tl("Recovery status refreshed."));
    }
  }

  return (
    <Card>
      <CardHeader className="px-5 py-4">
        <div className="flex min-w-0 items-start justify-between gap-4">
          <div className="min-w-0">
            <CardTitle>{t("auth.settings.security.title")}</CardTitle>
            <CardDescription>{tl("Password rotation and recovery-code controls stay private to this operator account.")}</CardDescription>
          </div>
          {loading ? (
            <LoaderCircle className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-[var(--text-tertiary)]" strokeWidth={1.75} aria-label="Loading" />
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col p-0">
        <div className="grid gap-px bg-[var(--divider-hair)] sm:grid-cols-3">
          <SecurityMetric
            label={tl("Recovery codes")}
            value={summary ? `${summary.remaining}/${summary.total}` : "—"}
            loading={loading && !summary}
          />
          <SecurityMetric
            label={tl("Generated")}
            value={summary?.generated_at ? formatDateTime(summary.generated_at) : "—"}
            loading={loading && !summary}
          />
          <SecurityMetric label={tl("Password")} value={tl("Operator managed")} />
        </div>

        {loadError ? (
          <div className="px-5 pt-4">
            <InlineAlert tone="warning">{loadError}</InlineAlert>
          </div>
        ) : null}

        <div className="grid min-w-0 divide-y divide-[var(--divider-hair)] lg:grid-cols-2 lg:divide-x lg:divide-y-0">
          <form
            onSubmit={handleChangePassword}
            className="flex min-w-0 flex-col gap-3 p-5"
          >
            <SecurityActionHeader
              icon={KeyRound}
              title={t("auth.settings.security.change_password")}
              description={tl("Use your current password before setting a new one.")}
            />
            <div className="flex flex-col gap-2">
              <Input
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                autoComplete="current-password"
                placeholder={t("auth.settings.security.need_current_password")}
                disabled={changeBusy}
              />
              <Input
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                autoComplete="new-password"
                placeholder={t("auth.forgot.new_password")}
                disabled={changeBusy}
              />
            </div>
            {changeError ? <InlineAlert tone="danger">{changeError}</InlineAlert> : null}
            <Button type="submit" variant="accent" size="sm" disabled={changeBusy} className="self-start">
              {changeBusy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
              <span>{t("auth.settings.security.change_password")}</span>
            </Button>
          </form>

          <section className="flex min-w-0 flex-col gap-3 p-5">
            <SecurityActionHeader
              icon={CalendarClock}
              title={t("auth.settings.security.regenerate_codes")}
              description={
                summary
                  ? t("auth.settings.security.codes_remaining", {
                      count: summary.remaining,
                      total: summary.total,
                    })
                  : tl("Current password required before codes rotate.")
              }
            />
            <form onSubmit={handleRegenerate} className="flex flex-col gap-2">
              <Input
                type="password"
                value={regenPassword}
                onChange={(event) => setRegenPassword(event.target.value)}
                autoComplete="current-password"
                placeholder={t("auth.settings.security.need_current_password")}
                disabled={regenBusy}
              />
              {regenError ? <InlineAlert tone="danger">{regenError}</InlineAlert> : null}
              <Button type="submit" variant="secondary" size="sm" disabled={regenBusy} className="self-start">
                {regenBusy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
                <span>{t("auth.settings.security.regenerate_codes")}</span>
              </Button>
            </form>
          </section>
        </div>

        {regenCodes && regenCodes.length > 0 ? (
          <div className="border-t border-[var(--divider-hair)] px-5 py-4">
            <ul className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[12.5px] tabular-nums text-[var(--text-primary)] sm:grid-cols-3">
              {regenCodes.map((code) => (
                <li key={code}>{code}</li>
              ))}
            </ul>
            <p className="mt-2 text-[11.5px] text-[var(--text-quaternary)]">
              {t("auth.setup.recovery_codes.subtitle")}
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
