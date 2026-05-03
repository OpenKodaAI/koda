"use client";

import { useMemo, useState } from "react";
import { Code2, Eye } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { Button } from "@/components/ui/button";
import { TextViewer } from "@/components/sessions/artifacts/viewers/text-viewer";
import { cn } from "@/lib/utils";

export interface JsonViewerProps {
  content: string;
  filename?: string | null;
}

interface JsonNodeProps {
  name: string | number | null;
  value: unknown;
  depth: number;
}

function valuePreview(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string") return `"${value.length > 40 ? value.slice(0, 40) + "…" : value}"`;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return `Array(${value.length})`;
  return `Object(${Object.keys(value as object).length})`;
}

function JsonNode({ name, value, depth }: JsonNodeProps) {
  const [open, setOpen] = useState(depth < 1);
  const isObject = typeof value === "object" && value !== null;

  const label = (
    <span className="font-mono text-[0.8125rem]">
      {name !== null ? (
        <span className="text-[var(--text-secondary)]">
          {typeof name === "number" ? name : `"${name}"`}:{" "}
        </span>
      ) : null}
    </span>
  );

  if (!isObject) {
    return (
      <div
        className="font-mono text-[0.8125rem]"
        style={{ paddingLeft: `${depth * 12}px` }}
      >
        {label}
        <span
          className={cn(
            value === null && "text-[var(--text-quaternary)]",
            typeof value === "string" && "text-[var(--tone-info-text)]",
            typeof value === "number" && "text-[var(--tone-success-text)]",
            typeof value === "boolean" && "text-[var(--tone-warning-text)]",
          )}
        >
          {value === null ? "null" : typeof value === "string" ? `"${value}"` : String(value)}
        </span>
      </div>
    );
  }

  const isArray = Array.isArray(value);
  const entries = isArray
    ? (value as unknown[]).map((v, i) => [i, v] as const)
    : Object.entries(value as Record<string, unknown>);

  return (
    <div style={{ paddingLeft: `${depth * 12}px` }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="font-mono text-[0.8125rem] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      >
        {open ? "▾" : "▸"} {label}
        {open ? (isArray ? "[" : "{") : valuePreview(value)}
      </button>
      {open ? (
        <>
          <div className="flex flex-col">
            {entries.map(([key, v]) => (
              <JsonNode
                key={String(key)}
                name={isArray ? Number(key) : String(key)}
                value={v}
                depth={depth + 1}
              />
            ))}
          </div>
          <div
            className="font-mono text-[0.8125rem] text-[var(--text-secondary)]"
            style={{ paddingLeft: `${depth * 12}px` }}
          >
            {isArray ? "]" : "}"}
          </div>
        </>
      ) : null}
    </div>
  );
}

export function JsonViewer({ content, filename }: JsonViewerProps) {
  const { t } = useAppI18n();
  const [showRaw, setShowRaw] = useState(false);

  const parsed = useMemo(() => {
    try {
      return { ok: true, value: JSON.parse(content) as unknown };
    } catch (error) {
      return {
        ok: false as const,
        error: error instanceof Error ? error.message : "Invalid JSON",
      };
    }
  }, [content]);

  if (!parsed.ok) {
    return (
      <div className="flex flex-col">
        <p className="m-0 px-4 py-2 text-[0.75rem] text-[var(--tone-danger-dot)]">
          {t("sessions.artifacts.invalidJson", { defaultValue: "Invalid JSON" })}: {parsed.error}
        </p>
        <TextViewer text={content} filename={filename} />
      </div>
    );
  }

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
              {t("sessions.artifacts.tree", { defaultValue: "Tree" })}
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
        <TextViewer text={content} filename={null} />
      ) : (
        <div className="max-h-[60vh] overflow-auto px-4 py-3">
          <JsonNode name={null} value={(parsed as { value: unknown }).value} depth={0} />
        </div>
      )}
    </div>
  );
}
