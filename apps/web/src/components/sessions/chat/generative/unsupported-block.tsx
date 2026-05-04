"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import { InlineAlert } from "@/components/ui/inline-alert";

export interface UnsupportedBlockProps {
  blockType?: string;
  /** When provided, renders a collapsible <details> with the raw payload — dev/debug only. */
  raw?: unknown;
}

const isDev =
  typeof process !== "undefined" && process.env.NODE_ENV !== "production";

export function UnsupportedBlock({ blockType, raw }: UnsupportedBlockProps) {
  const { t } = useAppI18n();

  return (
    <InlineAlert tone="warning">
      <p className="m-0 font-medium">
        {t("chat.blocks.unsupported.title", { defaultValue: "Unsupported block" })}
      </p>
      <p className="m-0 mt-0.5 text-[0.8125rem] opacity-90">
        {t("chat.blocks.unsupported.body", {
          defaultValue: "This message includes content this client can’t render yet.",
        })}
        {blockType ? (
          <>
            {" "}
            <code className="font-mono text-[0.75rem] opacity-80">
              {blockType}
            </code>
          </>
        ) : null}
      </p>
      {isDev && raw !== undefined ? (
        <details className="mt-2 text-[0.6875rem]">
          <summary className="cursor-pointer text-[var(--text-tertiary)]">
            Raw payload
          </summary>
          <pre className="mt-1 max-h-48 overflow-auto rounded-[var(--radius-chip)] bg-[var(--panel-strong)] p-2 text-[var(--text-secondary)] whitespace-pre-wrap break-all">
            {JSON.stringify(raw, null, 2)}
          </pre>
        </details>
      ) : null}
    </InlineAlert>
  );
}
