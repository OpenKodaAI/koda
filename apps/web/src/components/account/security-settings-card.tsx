"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCcw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InlineAlert } from "@/components/ui/inline-alert";
import { Input } from "@/components/ui/input";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { requestJson } from "@/lib/http-client";

interface RecoverySummary {
  total: number;
  remaining: number;
  generated_at: string | null;
}

export function SecuritySettingsCard() {
  const { t } = useAppI18n();
  const [summary, setSummary] = useState<RecoverySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [changeBusy, setChangeBusy] = useState(false);
  const [changeError, setChangeError] = useState<string | null>(null);
  const [changeOk, setChangeOk] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const [regenBusy, setRegenBusy] = useState(false);
  const [regenError, setRegenError] = useState<string | null>(null);
  const [regenPassword, setRegenPassword] = useState("");
  const [regenCodes, setRegenCodes] = useState<string[] | null>(null);

  const refreshSummary = useCallback(async () => {
    setLoading(true);
    try {
      const data = await requestJson<RecoverySummary>("/api/control-plane/auth/recovery-codes");
      setSummary(data);
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Failed to load security info.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshSummary();
  }, [refreshSummary]);

  async function handleChangePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setChangeError(null);
    setChangeOk(false);
    if (newPassword.length < 12) {
      setChangeError(t("auth.forgot.password_too_short", { n: 12 }));
      return;
    }
    setChangeBusy(true);
    try {
      await requestJson("/api/control-plane/auth/password/change", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setChangeOk(true);
    } catch (error) {
      setChangeError(error instanceof Error ? error.message : t("auth.forgot.generic_error"));
    } finally {
      setChangeBusy(false);
    }
  }

  async function handleRegenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRegenError(null);
    setRegenCodes(null);
    setRegenBusy(true);
    try {
      const data = await requestJson<{ recovery_codes: string[] }>(
        "/api/control-plane/auth/recovery-codes/regenerate",
        {
          method: "POST",
          body: JSON.stringify({ current_password: regenPassword }),
        },
      );
      setRegenCodes(data.recovery_codes || []);
      setRegenPassword("");
      await refreshSummary();
    } catch (error) {
      setRegenError(error instanceof Error ? error.message : t("auth.forgot.generic_error"));
    } finally {
      setRegenBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="icon-sm text-[var(--accent)]" strokeWidth={1.75} />
          <span>{t("auth.settings.security.title")}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <form onSubmit={handleChangePassword} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-[var(--text-secondary)]">
              {t("auth.settings.security.change_password")}
            </span>
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
          {changeOk ? <InlineAlert tone="success">{t("auth.forgot.success_title")}</InlineAlert> : null}
          <Button type="submit" variant="accent" size="sm" disabled={changeBusy} className="self-start">
            {changeBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            <span>{t("auth.settings.security.change_password")}</span>
          </Button>
        </form>

        <div className="border-t border-[color:var(--divider-hair)]" />

        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="m-0 text-[13px] font-medium text-[var(--text-primary)]">
                {t("auth.settings.security.regenerate_codes")}
              </h3>
              {summary ? (
                <p className="m-0 text-[11.5px] text-[var(--text-tertiary)]">
                  {t("auth.settings.security.codes_remaining", {
                    remaining: summary.remaining,
                    total: summary.total,
                  })}
                </p>
              ) : loading ? (
                <p className="m-0 text-[11.5px] text-[var(--text-quaternary)]">…</p>
              ) : null}
            </div>
          </div>
          {loadError ? <InlineAlert tone="warning">{loadError}</InlineAlert> : null}
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
              {regenBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
              <span>{t("auth.settings.security.regenerate_codes")}</span>
            </Button>
          </form>
          {regenCodes && regenCodes.length > 0 ? (
            <div className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-3">
              <ul className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[12.5px] tabular-nums text-[var(--text-primary)]">
                {regenCodes.map((code) => (
                  <li key={code}>{code}</li>
                ))}
              </ul>
              <p className="mt-2 text-[11.5px] text-[var(--text-quaternary)]">
                {t("auth.setup.recovery_codes.subtitle")}
              </p>
            </div>
          ) : null}
        </section>
      </CardContent>
    </Card>
  );
}
