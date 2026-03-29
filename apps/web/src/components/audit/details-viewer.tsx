 "use client";

import type { ReactNode } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface DetailsViewerProps {
  data: Record<string, unknown>;
}

function renderValue(value: unknown, indent: number): ReactNode {
  if (value === null || value === undefined) {
    return <span className="syn-null">null</span>;
  }

  if (typeof value === "boolean") {
    return (
      <span className="syn-boolean">{value ? "true" : "false"}</span>
    );
  }

  if (typeof value === "number") {
    return <span className="syn-number">{value}</span>;
  }

  if (typeof value === "string") {
    return (
      <span className="syn-string">
        &quot;{value}&quot;
      </span>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="syn-bracket">[]</span>;
    }
    return (
      <span>
        <span className="syn-bracket">[</span>
        {value.map((item, i) => (
          <div key={i} style={{ paddingLeft: `${(indent + 1) * 16}px` }}>
            {renderValue(item, indent + 1)}
            {i < value.length - 1 && <span className="syn-bracket">,</span>}
          </div>
        ))}
        <div style={{ paddingLeft: `${indent * 16}px` }}>
          <span className="syn-bracket">]</span>
        </div>
      </span>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) {
      return <span className="syn-bracket">{"{}"}</span>;
    }
    return (
      <span>
        <span className="syn-bracket">{"{"}</span>
        {entries.map(([key, val], i) => (
          <div key={key} style={{ paddingLeft: `${(indent + 1) * 16}px` }}>
            <span className="syn-key">&quot;{key}&quot;</span>
            <span className="syn-bracket">: </span>
            {renderValue(val, indent + 1)}
            {i < entries.length - 1 && (
              <span className="syn-bracket">,</span>
            )}
          </div>
        ))}
        <div style={{ paddingLeft: `${indent * 16}px` }}>
          <span className="syn-bracket">{"}"}</span>
        </div>
      </span>
    );
  }

  return <span className="syn-bracket">{String(value)}</span>;
}

export function DetailsViewer({ data }: DetailsViewerProps) {
  const { tl } = useAppI18n();
  const entries = Object.entries(data);

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)] bg-[linear-gradient(180deg,rgba(16,16,16,0.92)_0%,rgba(11,11,11,0.96)_100%)] shadow-[inset_0_1px_0_rgba(255,255,255,0.015)]">
      <div className="flex items-center justify-between border-b border-[rgba(236,236,236,0.06)] px-4 py-2.5">
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          {tl("JSON")}
        </span>
      </div>
      <div className="p-4">
        <pre className="font-mono text-[12px] leading-6">
          {entries.length === 0 ? (
            <span className="syn-null italic">{tl("Vazio")}</span>
          ) : (
            <span>
              <span className="syn-bracket">{"{"}</span>
              {entries.map(([key, val], i) => (
                <div key={key} style={{ paddingLeft: "16px" }}>
                  <span className="syn-key">&quot;{key}&quot;</span>
                  <span className="syn-bracket">: </span>
                  {renderValue(val, 1)}
                  {i < entries.length - 1 && (
                    <span className="syn-bracket">,</span>
                  )}
                </div>
              ))}
              <span className="syn-bracket">{"}"}</span>
            </span>
          )}
        </pre>
      </div>
    </div>
  );
}
