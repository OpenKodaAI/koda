"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { cn, formatDuration } from "@/lib/utils";
import type { z } from "zod";
import type { uiTableBlockSchema } from "@/lib/contracts/generative-ui";

export type UiTableBlock = z.infer<typeof uiTableBlockSchema>;

type Column = UiTableBlock["payload"]["columns"][number];
type Row = UiTableBlock["payload"]["rows"][number];
type Cell = string | number | boolean | null;

function formatCell(value: Cell, format: Column["format"]): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  switch (format) {
    case "number":
      return typeof value === "number"
        ? new Intl.NumberFormat().format(value)
        : String(value);
    case "duration":
      return typeof value === "number" ? formatDuration(value) : String(value);
    case "cost":
      return typeof value === "number"
        ? `$${value.toFixed(value < 1 ? 4 : 2)}`
        : String(value);
    case "date": {
      if (typeof value !== "string") return String(value);
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
    }
    case "status":
    case "text":
    default:
      return String(value);
  }
}

function compareCells(a: Cell, b: Cell): number {
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

export function UiTable({ block }: { block: UiTableBlock }) {
  const { title, columns, rows, empty_label } = block.payload;
  const [sort, setSort] = useState<{
    key: string;
    direction: "asc" | "desc";
  } | null>(null);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.sortable) return rows;
    const next = [...rows].sort((a, b) =>
      compareCells(a[sort.key] as Cell, b[sort.key] as Cell),
    );
    return sort.direction === "asc" ? next : next.reverse();
  }, [columns, rows, sort]);

  const toggleSort = (key: string) => {
    setSort((current) => {
      if (current?.key !== key) return { key, direction: "asc" };
      if (current.direction === "asc") return { key, direction: "desc" };
      return null;
    });
  };

  return (
    <div className="rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] overflow-hidden">
      {title ? (
        <h4 className="m-0 px-3 pt-2 pb-1 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)] border-b border-[color:var(--divider-hair)]">
          {title}
        </h4>
      ) : null}
      {sortedRows.length === 0 ? (
        <p className="m-0 px-3 py-4 text-[0.8125rem] text-[var(--text-tertiary)]">
          {empty_label ?? "No rows"}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[0.8125rem]">
            <thead>
              <tr>
                {columns.map((column) => {
                  const isSortKey = sort?.key === column.key;
                  return (
                    <th
                      key={column.key}
                      scope="col"
                      className={cn(
                        "border-b border-[color:var(--divider-hair)] px-3 py-1.5 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)]",
                        column.align === "end" && "text-right",
                        column.align === "center" && "text-center",
                        column.align === "start" && "text-left",
                      )}
                    >
                      {column.sortable ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(column.key)}
                          className="inline-flex items-center gap-1 text-[var(--text-quaternary)] hover:text-[var(--text-primary)]"
                        >
                          {column.label}
                          {isSortKey ? (
                            sort?.direction === "asc" ? (
                              <ArrowUp className="icon-xs" strokeWidth={1.75} aria-hidden />
                            ) : (
                              <ArrowDown className="icon-xs" strokeWidth={1.75} aria-hidden />
                            )
                          ) : null}
                        </button>
                      ) : (
                        column.label
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={cn(
                        "border-b border-[color:var(--divider-hair)] px-3 py-1.5 text-[var(--text-secondary)] last:border-b-0",
                        column.align === "end" && "text-right",
                        column.align === "center" && "text-center",
                        column.align === "start" && "text-left",
                        column.format === "number" || column.format === "cost" || column.format === "duration"
                          ? "font-mono tabular-nums"
                          : "",
                      )}
                    >
                      {formatCell((row as Row)[column.key] as Cell, column.format)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
