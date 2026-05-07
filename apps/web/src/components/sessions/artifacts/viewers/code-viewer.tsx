"use client";

import { useState } from "react";
import { Copy, WrapText } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { Button } from "@/components/ui/button";
import { detectLanguage } from "@/components/sessions/artifacts/language-detection";
import { cn } from "@/lib/utils";

export interface CodeViewerProps {
  code: string;
  filename?: string | null;
}

export function CodeViewer({ code, filename }: CodeViewerProps) {
  const { t } = useAppI18n();
  const [softWrap, setSoftWrap] = useState(false);
  const [copied, setCopied] = useState(false);
  const language = detectLanguage(filename);
  const lines = code.split("\n");

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  return (
    <div className="flex flex-col" data-language={language}>
      <div className="flex items-center justify-between border-b border-[color:var(--divider-hair)] px-4 py-2">
        <div className="flex items-center gap-2">
          {filename ? (
            <span className="truncate text-[0.8125rem] text-[var(--text-secondary)]">
              {filename}
            </span>
          ) : null}
          <span className="font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)]">
            {language}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setSoftWrap((v) => !v)}
            aria-pressed={softWrap}
          >
            <WrapText className="icon-xs" strokeWidth={1.75} aria-hidden />
            {softWrap
              ? t("sessions.artifacts.wrapOff", { defaultValue: "No wrap" })
              : t("sessions.artifacts.wrapOn", { defaultValue: "Wrap" })}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={handleCopy}>
            <Copy className="icon-xs" strokeWidth={1.75} aria-hidden />
            {copied
              ? t("common.copied", { defaultValue: "Copied" })
              : t("common.copy", { defaultValue: "Copy" })}
          </Button>
        </div>
      </div>
      <div className="max-h-[60vh] overflow-auto">
        <pre
          className={cn(
            "m-0 grid grid-cols-[auto_1fr] gap-x-4 px-4 py-3 text-[0.8125rem] leading-[1.6]",
            "text-[var(--text-primary)] font-mono",
            softWrap ? "whitespace-pre-wrap break-words" : "whitespace-pre",
          )}
        >
          {lines.map((line, index) => (
            <div key={index} className="contents">
              <span
                aria-hidden
                className="select-none text-right text-[var(--text-quaternary)]"
              >
                {index + 1}
              </span>
              <span>{line || " "}</span>
            </div>
          ))}
        </pre>
      </div>
    </div>
  );
}
