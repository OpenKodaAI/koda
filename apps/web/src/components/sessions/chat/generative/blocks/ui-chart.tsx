"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { z } from "zod";
import type { uiChartBlockSchema } from "@/lib/contracts/generative-ui";

export type UiChartBlock = z.infer<typeof uiChartBlockSchema>;

const SERIES_COLORS = [
  "var(--accent)",
  "var(--tone-info-dot)",
  "var(--tone-success-dot)",
  "var(--tone-warning-dot)",
];

function formatTick(value: unknown, unit: UiChartBlock["payload"]["unit"]): string {
  if (typeof value !== "number") return String(value);
  switch (unit) {
    case "cost_usd":
      return `$${value.toFixed(value < 1 ? 4 : 2)}`;
    case "ms":
      return `${value} ms`;
    case "percent":
      return `${value}%`;
    case "count":
    default:
      return new Intl.NumberFormat().format(value);
  }
}

export function UiChart({ block }: { block: UiChartBlock }) {
  const { title, kind, x_key, y_keys, data, unit } = block.payload;

  const tickFormatter = useMemo(
    () => (value: unknown) => formatTick(value, unit),
    [unit],
  );

  const series = y_keys.map((key, index) => ({
    key,
    color: SERIES_COLORS[index % SERIES_COLORS.length],
  }));

  const chart = (() => {
    if (kind === "bar") {
      return (
        <BarChart data={data}>
          <CartesianGrid stroke="var(--divider-hair)" vertical={false} />
          <XAxis dataKey={x_key} tick={{ fontSize: 11, fill: "var(--text-tertiary)" }} />
          <YAxis
            tick={{ fontSize: 11, fill: "var(--text-tertiary)" }}
            tickFormatter={tickFormatter}
            width={48}
          />
          <Tooltip
            cursor={{ fill: "var(--hover-tint)" }}
            contentStyle={{
              background: "var(--panel)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-chip)",
              fontSize: "0.75rem",
            }}
            formatter={(value) => formatTick(value, unit)}
          />
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} fill={s.color} radius={[2, 2, 0, 0]} />
          ))}
        </BarChart>
      );
    }
    if (kind === "area") {
      return (
        <AreaChart data={data}>
          <CartesianGrid stroke="var(--divider-hair)" vertical={false} />
          <XAxis dataKey={x_key} tick={{ fontSize: 11, fill: "var(--text-tertiary)" }} />
          <YAxis
            tick={{ fontSize: 11, fill: "var(--text-tertiary)" }}
            tickFormatter={tickFormatter}
            width={48}
          />
          <Tooltip
            contentStyle={{
              background: "var(--panel)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-chip)",
              fontSize: "0.75rem",
            }}
            formatter={(value) => formatTick(value, unit)}
          />
          {series.map((s) => (
            <Area
              key={s.key}
              dataKey={s.key}
              stroke={s.color}
              fill={s.color}
              fillOpacity={0.18}
              strokeWidth={1.5}
            />
          ))}
        </AreaChart>
      );
    }
    return (
      <LineChart data={data}>
        <CartesianGrid stroke="var(--divider-hair)" vertical={false} />
        <XAxis dataKey={x_key} tick={{ fontSize: 11, fill: "var(--text-tertiary)" }} />
        <YAxis
          tick={{ fontSize: 11, fill: "var(--text-tertiary)" }}
          tickFormatter={tickFormatter}
          width={48}
        />
        <Tooltip
          contentStyle={{
            background: "var(--panel)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-chip)",
            fontSize: "0.75rem",
          }}
          formatter={(value) => formatTick(value, unit)}
        />
        {series.map((s) => (
          <Line
            key={s.key}
            dataKey={s.key}
            stroke={s.color}
            strokeWidth={1.5}
            dot={false}
          />
        ))}
      </LineChart>
    );
  })();

  return (
    <div className="rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] p-3">
      {title ? (
        <h4 className="m-0 mb-2 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono,0.12em)] text-[var(--text-quaternary)]">
          {title}
        </h4>
      ) : null}
      <div className="h-[180px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          {chart}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
