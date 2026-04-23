"use client";

import { useState } from "react";
import { Check, Copy, Download, Printer } from "lucide-react";
import { KodaMark } from "@/components/layout/koda-mark";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import { useAppI18n } from "@/hooks/use-app-i18n";

export interface StepRecoveryCodesProps {
  codes: string[];
  onConfirmed: () => void;
}

export function StepRecoveryCodes({ codes, onConfirmed }: StepRecoveryCodesProps) {
  const { t } = useAppI18n();
  const [copied, setCopied] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(codes.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2400);
    } catch {
      // Clipboard API failures are surfaced to the user via the download button below.
    }
  }

  function handleDownload() {
    const header = `${t("auth.setup.recovery_codes.file_header")}\n`;
    const blob = new Blob([header + codes.join("\n") + "\n"], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `koda-recovery-codes-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function handlePrint() {
    window.print();
  }

  if (!codes.length) {
    return (
      <div className="flex flex-col gap-4">
        <InlineAlert tone="warning">
          {t("auth.setup.recovery_codes.already_shown_banner")}
        </InlineAlert>
        <Button variant="accent" size="lg" onClick={onConfirmed} className="auth-submit">
          {t("auth.setup.recovery_codes.continue")}
        </Button>
      </div>
    );
  }

  return (
    <div className="auth-form">
      <div className="auth-form__hero">
        <KodaMark className="auth-form__logo" />
        <div className="auth-form__title-block">
          <h1 className="auth-form__title">{t("auth.setup.recovery_codes.title")}</h1>
          <p className="auth-form__subtitle">{t("auth.setup.recovery_codes.subtitle")}</p>
        </div>
      </div>

      <div className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-4 py-3">
        <ul className="grid grid-cols-2 gap-x-5 gap-y-2 font-mono text-[13.5px] tracking-[0.05em] text-[var(--text-primary)]">
          {codes.map((code) => (
            <li key={code} className="tabular-nums">
              {code}
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" onClick={handleCopy} className="flex-1">
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          <span>{copied ? t("auth.setup.recovery_codes.copied") : t("auth.setup.recovery_codes.copy_all")}</span>
        </Button>
        <Button variant="secondary" size="sm" onClick={handleDownload} className="flex-1">
          <Download className="h-4 w-4" />
          <span>{t("auth.setup.recovery_codes.download")}</span>
        </Button>
        <Button variant="secondary" size="sm" onClick={handlePrint} className="flex-1">
          <Printer className="h-4 w-4" />
          <span>{t("auth.setup.recovery_codes.print")}</span>
        </Button>
      </div>

      <label className="flex items-start gap-2.5 cursor-pointer rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2.5">
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(event) => setAcknowledged(event.target.checked)}
          className="mt-0.5 accent-[var(--accent)]"
        />
        <span className="text-[13px] leading-snug text-[var(--text-secondary)]">
          {t("auth.setup.recovery_codes.saved_checkbox")}
        </span>
      </label>

      <Button
        type="button"
        variant="accent"
        size="lg"
        disabled={!acknowledged}
        onClick={onConfirmed}
        className="auth-submit"
      >
        {t("auth.setup.recovery_codes.continue")}
      </Button>
    </div>
  );
}
