"use client";

import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getCurrentLanguage } from "@/lib/i18n";
import { cn, formatCost } from "@/lib/utils";
import { getBotChartColor, getBotLabel } from "@/lib/bot-constants";

interface CostChartProps {
  data: { botId: string; dailyCosts: { date: string; cost: number }[] }[];
  className?: string;
}

function mergeDailyCosts(
  data: { botId: string; dailyCosts: { date: string; cost: number }[] }[]
): Record<string, unknown>[] {
  const dateMap = new Map<string, Record<string, unknown>>();

  for (const series of data) {
    for (const entry of series.dailyCosts) {
      if (!dateMap.has(entry.date)) {
        dateMap.set(entry.date, { date: entry.date });
      }
      dateMap.get(entry.date)![series.botId] = entry.cost;
    }
  }

  return Array.from(dateMap.values()).sort((a, b) =>
    (a.date as string).localeCompare(b.date as string)
  );
}

function formatDateShort(dateStr: string): string {
  const date = new Date(dateStr + "T00:00:00");
  return date.toLocaleDateString(getCurrentLanguage(), { day: "2-digit", month: "short" });
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: { dataKey: string; value: number; color: string }[];
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;

  return (
    <div className="glass-card-sm min-w-[180px] px-3 py-3 text-xs shadow-2xl">
      <p className="mb-2 font-medium text-[var(--text-primary)]">
        {label ? formatDateShort(label) : ""}
      </p>
      {payload.map((entry) => (
        <div
          key={entry.dataKey}
          className="flex items-center justify-between gap-4 py-0.5"
        >
          <div className="flex items-center gap-2">
            <span
              className="block h-2 w-2 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span className="text-[var(--text-secondary)]">
              {getBotLabel(entry.dataKey)}
            </span>
          </div>
          <span className="font-medium tabular-nums text-[var(--text-primary)]">
            {formatCost(entry.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export function CostChart({ data, className }: CostChartProps) {
  const mergedData = mergeDailyCosts(data);
  const series = data.filter((entry) => entry.dailyCosts.length > 0);
  const botIds = series.map((entry) => entry.botId);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const update = () => setIsMobile(window.innerWidth < 640);
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  return (
    <div className={cn(className)}>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {botIds.map((botId) => (
          <span
            key={botId}
            className="inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-[11px] font-medium text-[var(--text-secondary)]"
            style={{
              borderColor: `color-mix(in srgb, ${getBotChartColor(botId)} 58%, #2b2d31)`,
              background: `linear-gradient(180deg, color-mix(in srgb, ${getBotChartColor(botId)} 28%, #2e3137) 0%, color-mix(in srgb, ${getBotChartColor(botId)} 16%, #17181b) 100%)`,
              color: "var(--text-primary)",
            }}
          >
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: getBotChartColor(botId) }}
            />
            {getBotLabel(botId)}
          </span>
        ))}
      </div>
      <div className={cn("w-full min-w-0", isMobile ? "h-[236px]" : "h-[336px]")}>
        <AreaChart
          responsive
          data={mergedData}
          style={{ width: "100%", height: "100%" }}
          margin={{ top: 8, right: 10, bottom: 2, left: isMobile ? -14 : 2 }}
        >
          <defs>
            {botIds.map((botId) => (
              <linearGradient
                key={botId}
                id={`cost-gradient-${botId}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop
                  offset="0%"
                  stopColor={getBotChartColor(botId)}
                  stopOpacity={0.42}
                />
                <stop
                  offset="100%"
                  stopColor={getBotChartColor(botId)}
                  stopOpacity={0.06}
                />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid
            strokeDasharray="2 6"
            stroke="var(--border-subtle)"
            vertical={false}
          />
          <XAxis
            dataKey="date"
            tickFormatter={formatDateShort}
            tick={{ fill: "var(--text-tertiary)", fontSize: isMobile ? 10 : 11 }}
            axisLine={{ stroke: "var(--border-subtle)" }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          {!isMobile && (
            <YAxis
              tickFormatter={(v: number) => formatCost(v)}
              tick={{ fill: "var(--text-tertiary)", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={66}
            />
          )}
          <Tooltip content={<CustomTooltip />} />
          {botIds.map((botId) => (
            <Area
              key={botId}
              type="monotone"
              dataKey={botId}
              stroke={getBotChartColor(botId)}
              strokeWidth={2.2}
              fill={`url(#cost-gradient-${botId})`}
              dot={false}
              isAnimationActive={false}
              activeDot={{
                r: 4,
                fill: getBotChartColor(botId),
                stroke: "var(--panel)",
                strokeWidth: 2,
              }}
            />
          ))}
        </AreaChart>
      </div>
    </div>
  );
}
