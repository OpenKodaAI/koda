"use client";

import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { useAppI18n } from "@/hooks/use-app-i18n";

/* -------------------------------------------------------------------------- */
/*  InheritedContext — visual indicator for inherited workspace/squad values   */
/* -------------------------------------------------------------------------- */

interface InheritedContextProps {
  source: "workspace" | "squad";
  children: ReactNode;
}

export function InheritedContext({ source, children }: InheritedContextProps) {
  const { tl } = useAppI18n();

  const borderColor =
    source === "workspace"
      ? "border-[rgba(76,127,209,0.4)]"
      : "border-[rgba(113,219,190,0.4)]";

  const label =
    source === "workspace"
      ? tl("Herdado do workspace")
      : tl("Herdado do squad");

  return (
    <div className={`text-xs text-[var(--text-quaternary)] border-l-2 ${borderColor} pl-2 mb-2`}>
      <span className="font-medium text-[var(--text-tertiary)]">[{label}]</span>{" "}
      {children}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  InheritedList — renders a list of inherited string values                  */
/* -------------------------------------------------------------------------- */

interface InheritedListProps {
  source: "workspace" | "squad";
  label: string;
  items: string[];
}

export function InheritedList({ source, label, items }: InheritedListProps) {
  if (!items || items.length === 0) return null;

  return (
    <InheritedContext source={source}>
      <span className="font-medium">{label}:</span>{" "}
      {items.join(", ")}
    </InheritedContext>
  );
}

/* -------------------------------------------------------------------------- */
/*  InheritedValue — renders a single inherited scalar value                   */
/* -------------------------------------------------------------------------- */

interface InheritedValueProps {
  source: "workspace" | "squad";
  label: string;
  value: string | number | null | undefined;
}

export function InheritedValue({ source, label, value }: InheritedValueProps) {
  if (value === null || value === undefined || value === "") return null;

  return (
    <InheritedContext source={source}>
      <span className="font-medium">{label}:</span> {String(value)}
    </InheritedContext>
  );
}

/* -------------------------------------------------------------------------- */
/*  InheritedPromptPreview — renders inherited markdown prompt blocks          */
/* -------------------------------------------------------------------------- */

interface InheritedPromptPreviewProps {
  source: "workspace" | "squad";
  label: string;
  value: string;
}

export function InheritedPromptPreview({
  source,
  label,
  value,
}: InheritedPromptPreviewProps) {
  if (!value.trim()) return null;

  const accentClass =
    source === "workspace"
      ? "border-[rgba(76,127,209,0.18)] bg-[rgba(76,127,209,0.08)]"
      : "border-[rgba(113,219,190,0.18)] bg-[rgba(113,219,190,0.08)]";

  return (
    <section className={`overflow-hidden rounded-2xl border ${accentClass}`}>
      <div className="border-b border-[rgba(255,255,255,0.08)] px-4 py-3">
        <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
          {label}
        </div>
      </div>
      <div className="session-richtext max-h-56 overflow-auto px-4 py-4 text-sm leading-7 text-[var(--text-secondary)]">
        <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{value}</ReactMarkdown>
      </div>
    </section>
  );
}
