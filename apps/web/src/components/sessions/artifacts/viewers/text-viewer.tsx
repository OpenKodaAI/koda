"use client";

import { useState } from "react";
import { Copy } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface TextViewerProps {
  text: string;
  filename?: string | null;
  showLineCount?: boolean;
}

export function TextViewer({ text, filename, showLineCount = true }: TextViewerProps) {
  const { t } = useAppI18n();
  const [copied, setCopied] = useState(false);
  const lineCount = text.split("\n").length;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between border-b border-[color:var(--divider-hair)] px-4 py-2">
        <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
          {filename ? `${filename} · ` : ""}
          {showLineCount ? `${lineCount} lines` : ""}
        </span>
        <Button type="button" variant="ghost" size="sm" onClick={handleCopy}>
          <Copy className="icon-xs" strokeWidth={1.75} aria-hidden />
          {copied
            ? t("common.copied", undefined)
            : t("common.copy", undefined)}
        </Button>
      </div>
      <pre
        className={cn(
          "m-0 max-h-[60vh] overflow-auto px-4 py-3 text-[0.8125rem] leading-[1.55] text-[var(--text-primary)]",
          "whitespace-pre-wrap break-words font-mono",
        )}
      >
        {text}
      </pre>
    </div>
  );
}
