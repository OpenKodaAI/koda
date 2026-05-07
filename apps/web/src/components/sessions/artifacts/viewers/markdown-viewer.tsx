"use client";

import { useState } from "react";
import { Code2, Eye } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { Button } from "@/components/ui/button";
import { SessionRichText } from "@/components/sessions/session-rich-text";
import { TextViewer } from "@/components/sessions/artifacts/viewers/text-viewer";

export interface MarkdownViewerProps {
  content: string;
  filename?: string | null;
}

export function MarkdownViewer({ content, filename }: MarkdownViewerProps) {
  const { t } = useAppI18n();
  const [showRaw, setShowRaw] = useState(false);

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between border-b border-[color:var(--divider-hair)] px-4 py-2">
        {filename ? (
          <span className="truncate text-[0.8125rem] text-[var(--text-secondary)]">
            {filename}
          </span>
        ) : (
          <span />
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setShowRaw((v) => !v)}
          aria-pressed={showRaw}
        >
          {showRaw ? (
            <>
              <Eye className="icon-xs" strokeWidth={1.75} aria-hidden />
              {t("sessions.artifacts.rendered", { defaultValue: "Rendered" })}
            </>
          ) : (
            <>
              <Code2 className="icon-xs" strokeWidth={1.75} aria-hidden />
              {t("sessions.artifacts.raw", { defaultValue: "Raw" })}
            </>
          )}
        </Button>
      </div>
      {showRaw ? (
        <TextViewer text={content} filename={null} showLineCount={false} />
      ) : (
        <div className="max-h-[60vh] overflow-auto px-4 py-3 text-[var(--font-size-md)] leading-[1.6] text-[var(--text-primary)]">
          <SessionRichText content={content} variant="assistant" />
        </div>
      )}
    </div>
  );
}
