"use client";

import { useMemo, useState } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { Button } from "@/components/ui/button";
import { CSV_PAGE_SIZE, MAX_CSV_ROWS } from "@/lib/contracts/artifacts";
import { cn } from "@/lib/utils";
import { translate } from "@/lib/i18n";

export interface CsvViewerProps {
  content: string;
  filename?: string | null;
  delimiter?: string;
}

interface ParsedCsv {
  header: string[];
  rows: string[][];
  malformedLines: number;
  truncated: boolean;
}

function splitLine(line: string, delimiter: string): string[] {
  const out: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line.charAt(i);
    if (ch === '"') {
      if (inQuotes && line.charAt(i + 1) === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (ch === delimiter && !inQuotes) {
      out.push(current);
      current = "";
      continue;
    }
    current += ch;
  }
  out.push(current);
  return out;
}

function parseCsv(content: string, delimiter: string): ParsedCsv {
  const rawLines = content.split(/\r?\n/);
  const lines = rawLines[rawLines.length - 1] === "" ? rawLines.slice(0, -1) : rawLines;
  const truncated = lines.length > MAX_CSV_ROWS + 1;
  const usable = truncated ? lines.slice(0, MAX_CSV_ROWS + 1) : lines;
  if (usable.length === 0) {
    return { header: [], rows: [], malformedLines: 0, truncated };
  }
  const header = splitLine(usable[0], delimiter);
  const rows: string[][] = [];
  let malformed = 0;
  for (let i = 1; i < usable.length; i += 1) {
    const cells = splitLine(usable[i], delimiter);
    if (cells.length !== header.length && usable[i].trim() !== "") {
      malformed += 1;
    }
    rows.push(cells);
  }
  return { header, rows, malformedLines: malformed, truncated };
}

export function CsvViewer({
  content,
  filename,
  delimiter = ",",
}: CsvViewerProps) {
  const { t } = useAppI18n();
  const [page, setPage] = useState(0);

  const parsed = useMemo(() => parseCsv(content, delimiter), [content, delimiter]);
  const totalPages = Math.max(1, Math.ceil(parsed.rows.length / CSV_PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const start = safePage * CSV_PAGE_SIZE;
  const visible = parsed.rows.slice(start, start + CSV_PAGE_SIZE);

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between border-b border-[color:var(--divider-hair)] px-4 py-2">
        <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
          {filename ? `${filename} · ` : ""}
          {parsed.rows.length.toLocaleString()} {translate("generated.sessions.rows_bc4a72ac")}{parsed.truncated
            ? ` · truncated at ${MAX_CSV_ROWS.toLocaleString()}`
            : ""}
          {parsed.malformedLines > 0
            ? ` · ${parsed.malformedLines} malformed`
            : ""}
        </span>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={safePage === 0}
          >
            ‹
          </Button>
          <span className="font-mono text-[0.6875rem] text-[var(--text-tertiary)]">
            {safePage + 1}/{totalPages}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={safePage >= totalPages - 1}
          >
            ›
          </Button>
        </div>
      </div>
      <div className="max-h-[60vh] overflow-auto">
        <table className="w-full border-collapse text-[0.8125rem]">
          <thead className="sticky top-0 bg-[var(--panel-soft)]">
            <tr>
              {parsed.header.map((cell, i) => (
                <th
                  key={i}
                  scope="col"
                  className="border-b border-[color:var(--divider-hair)] px-3 py-1.5 text-left font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)]"
                >
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, rowIndex) => {
              const malformed = row.length !== parsed.header.length;
              return (
                <tr
                  key={start + rowIndex}
                  aria-invalid={malformed || undefined}
                  className={cn(malformed && "bg-[var(--tone-warning-bg)]")}
                >
                  {parsed.header.map((_, colIndex) => (
                    <td
                      key={colIndex}
                      className="border-b border-[color:var(--divider-hair)] px-3 py-1.5 text-[var(--text-secondary)]"
                    >
                      {row[colIndex] ?? ""}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {parsed.truncated ? (
        <p className="m-0 px-4 py-2 text-[0.75rem] text-[var(--tone-warning-text)]">
          {t("sessions.artifacts.csvTruncated", {
            defaultValue: `Preview is capped at ${MAX_CSV_ROWS.toLocaleString()} rows — download for full data.`,
          })}
        </p>
      ) : null}
    </div>
  );
}
