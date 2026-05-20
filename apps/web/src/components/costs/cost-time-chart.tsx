"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts";
import {
  ChartStyle,
  type ChartConfig,
  ChartTooltip,
} from "@/components/ui/line-charts-9";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getCurrentLanguage } from "@/lib/i18n";
import { cn, formatCost } from "@/lib/utils";
import { getAgentColor, getAgentLabel } from "@/lib/agent-constants";
import type { CostTimePoint } from "@/lib/types";

export type CostTimelineMode = "agent" | "model";

const MODEL_PALETTE = [
  "var(--tone-info-dot)",
  "var(--tone-success-dot)",
  "var(--tone-warning-dot)",
  "var(--tone-retry-dot)",
  "var(--text-quaternary)",
];

type CostSeries = {
  key: string;
  dataKey: string;
  label: string;
  color: string;
  total: number;
};

type CostChartDatum = {
  bucket: string;
  label: string;
  total: number;
  driverLabel: string | null;
  [key: string]: string | number | null;
};

function compactBucketLabel(label: string) {
  if (label.includes(":")) {
    return label.split(" ").pop() ?? label;
  }
  return label;
}

function formatAxisValue(value: number) {
  return new Intl.NumberFormat(getCurrentLanguage(), {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value > 0 && value < 10 ? 1 : 0,
    maximumFractionDigits: value > 0 && value < 10 ? 1 : 0,
  }).format(value);
}

function getPointValue(point: CostTimePoint, key: string, mode: CostTimelineMode) {
  return mode === "agent" ? (point.by_agent[key] ?? 0) : (point.by_model[key] ?? 0);
}

function getTopDriver(point: CostTimePoint, mode: CostTimelineMode) {
  const source = mode === "agent" ? point.by_agent : point.by_model;
  const winner = Object.entries(source).sort((left, right) => right[1] - left[1])[0]?.[0];
  if (!winner) return null;
  return mode === "agent" ? getAgentLabel(winner) : winner;
}

function buildSeries(points: CostTimePoint[], mode: CostTimelineMode) {
  const totals = new Map<string, number>();

  for (const point of points) {
    const source = mode === "agent" ? point.by_agent : point.by_model;
    for (const [key, value] of Object.entries(source)) {
      totals.set(key, (totals.get(key) ?? 0) + value);
    }
  }

  return [...totals.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, 5)
    .map(([key, total], index) => ({
      key,
      dataKey: `series_${index}`,
      total,
      color: mode === "agent" ? getAgentColor(key) : MODEL_PALETTE[index % MODEL_PALETTE.length],
      label: mode === "agent" ? getAgentLabel(key) : key,
    })) satisfies CostSeries[];
}

function buildChartData(points: CostTimePoint[], series: CostSeries[], mode: CostTimelineMode) {
  return points.map((point) => {
    const datum: CostChartDatum = {
      bucket: point.bucket,
      label: point.label,
      total: point.total_cost_usd,
      driverLabel: getTopDriver(point, mode),
    };

    for (const item of series) {
      datum[item.dataKey] = getPointValue(point, item.key, mode);
    }

    return datum;
  });
}

export function CostTimeChart({
  points,
  mode,
  onModeChange,
  className,
}: {
  points: CostTimePoint[];
  mode: CostTimelineMode;
  onModeChange?: (mode: CostTimelineMode) => void;
  className?: string;
}) {
  const { t } = useAppI18n();
  const [hoveredBucket, setHoveredBucket] = useState<string | null>(null);
  const [hoveredSeriesKey, setHoveredSeriesKey] = useState<string | null>(null);
  const chartHostRef = useRef<HTMLDivElement | null>(null);
  const chartId = `cost-time-${useId().replace(/:/g, "")}`;
  const [chartSize, setChartSize] = useState({ width: 0, height: 0 });

  const series = useMemo(() => buildSeries(points, mode), [mode, points]);
  const data = useMemo(() => buildChartData(points, series, mode), [mode, points, series]);
  const pointMap = useMemo(() => new Map(points.map((point) => [point.bucket, point])), [points]);

  const peakDatum = useMemo(() => {
    if (data.length === 0) return null;
    return data.reduce((best, point) => (point.total > best.total ? point : best), data[0]);
  }, [data]);

  const activeDatum = data.find((item) => item.bucket === hoveredBucket) ?? peakDatum ?? data[0] ?? null;
  const primaryColor = series[0]?.color ?? "var(--tone-info-dot)";

  useEffect(() => {
    const node = chartHostRef.current;
    if (!node) return;

    const update = () => {
      const rect = node.getBoundingClientRect();
      setChartSize({
        width: Math.max(0, Math.floor(rect.width)),
        height: Math.max(0, Math.floor(rect.height)),
      });
    };

    update();

    const observer = new ResizeObserver(update);
    observer.observe(node);

    return () => observer.disconnect();
  }, []);

  const chartConfig = useMemo(() => {
    const config: ChartConfig = {
      total: {
        label: "Custo total",
        color: primaryColor,
      },
    };

    for (const item of series) {
      config[item.dataKey] = {
        label: item.label,
        color: item.color,
      };
    }

    return config;
  }, [primaryColor, series]);

  if (points.length === 0 || data.length === 0) {
    return (
      <div
        className={cn(
          "flex min-h-[300px] items-center justify-center gap-2 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]",
          className
        )}
      >
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[var(--text-quaternary)]" />
        <span>{t("costs.page.timeChart.emptyShort", undefined)}</span>
      </div>
    );
  }

  return (
    <section
      className={cn(
        "overflow-hidden rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel)]",
        className
      )}
    >
      <div className="border-b border-[var(--divider-hair)] px-3 py-3">
        <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <p className="eyebrow truncate">{t("costs.chart.eyebrow")}</p>
            <h3 className="mt-1 truncate text-[var(--font-size-md)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
              {t("costs.chart.title")}
            </h3>
          </div>

          <div className="flex min-w-0 flex-wrap items-center gap-2 lg:justify-end">
            <div className="inline-flex min-w-0 items-center gap-2 rounded-[var(--radius-chip)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-2.5 py-1 text-[0.75rem]">
              <span className="truncate font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                {activeDatum?.label ?? t("costs.page.timeChart.noBucket", undefined)}
              </span>
              <span className="shrink-0 font-mono text-[var(--text-primary)]">
                {activeDatum ? formatCost(activeDatum.total) : "—"}
              </span>
              <span className="hidden min-w-0 truncate text-[var(--text-tertiary)] sm:inline">
                {activeDatum?.driverLabel
                  ? t("costs.page.timeChart.driver", { value: activeDatum.driverLabel })
                  : t("costs.page.timeChart.noDriver", undefined)}
              </span>
            </div>

            <SoftTabs
              items={[
                { id: "agent", label: t("costs.mode.byAgent") },
                { id: "model", label: t("costs.mode.byModel") },
              ]}
              value={mode}
              onChange={(id) => onModeChange?.(id as CostTimelineMode)}
              ariaLabel={t("costs.page.timeChart.modeLabel", undefined)}
              className="self-start"
            />
          </div>
        </div>

        <div className="mt-2 flex gap-3 overflow-x-auto pb-1">
          {series.map((item) => {
            const isDimmed = hoveredSeriesKey != null && hoveredSeriesKey !== item.key;

            return (
              <button
                key={item.key}
                type="button"
                onMouseEnter={() => setHoveredSeriesKey(item.key)}
                onMouseLeave={() => setHoveredSeriesKey(null)}
                onFocus={() => setHoveredSeriesKey(item.key)}
                onBlur={() => setHoveredSeriesKey(null)}
                className="inline-flex max-w-[180px] shrink-0 items-center gap-1.5 rounded-[var(--radius-chip)] px-0 py-1 text-[0.6875rem] transition-colors"
                style={{
                  color: isDimmed ? "var(--text-secondary)" : "var(--text-primary)",
                }}
              >
                <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="p-3">
        <div ref={chartHostRef} className="h-[232px] w-full min-w-0">
          {chartSize.width > 0 && chartSize.height > 0 ? (
            <div
              data-slot="chart"
              data-chart={chartId}
              className="h-full w-full min-w-0 text-xs [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-curve.recharts-tooltip-cursor]:stroke-border [&_.recharts-dot[stroke='#fff']]:stroke-transparent [&_.recharts-layer]:outline-hidden [&_.recharts-surface]:outline-hidden"
            >
              <ChartStyle id={chartId} config={chartConfig} />
              <ComposedChart
                width={chartSize.width}
                height={chartSize.height}
                data={data}
                margin={{ top: 8, right: 10, left: 0, bottom: 4 }}
                onMouseMove={(state) => {
                  const payload = (
                    state as { activePayload?: Array<{ payload?: CostChartDatum }> } | undefined
                  )?.activePayload?.[0]?.payload;
                  setHoveredBucket(payload?.bucket ?? null);
                }}
                onMouseLeave={() => setHoveredBucket(null)}
              >
            {activeDatum ? (
              <ReferenceLine
                x={activeDatum.label}
                stroke="var(--border-strong)"
                strokeDasharray="3 3"
                strokeOpacity={0.55}
                strokeWidth={1}
              />
            ) : null}

            <XAxis
              dataKey="label"
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 12, fill: "var(--text-tertiary)" }}
              tickMargin={14}
              interval="preserveStartEnd"
              minTickGap={24}
              tickFormatter={compactBucketLabel}
            />

            <YAxis
              axisLine={false}
              tickLine={false}
              width={48}
              tick={{ fontSize: 11, fill: "var(--text-tertiary)" }}
              tickMargin={12}
              tickFormatter={formatAxisValue}
            />

            <ChartTooltip
              cursor={{
                strokeDasharray: "3 3",
                stroke: "var(--border-strong)",
                strokeOpacity: 0.55,
              }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const datum = payload[0]?.payload as CostChartDatum | undefined;
                if (!datum) return null;

                const point = pointMap.get(datum.bucket);
                const rows = point
                  ? series
                      .map((item) => ({
                        ...item,
                        value: getPointValue(point, item.key, mode),
                      }))
                      .filter((item) => item.value > 0)
                      .sort((left, right) => right.value - left.value)
                      .slice(0, 4)
                  : [];

                return (
                  <div className="min-w-[min(220px,calc(100vw-3rem))] max-w-[calc(100vw-3rem)] rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3 py-2">
                    <div className="flex min-w-0 items-center justify-between gap-3">
                      <p className="truncate text-[11px] font-medium text-[var(--text-tertiary)]">{datum.label}</p>
                      <p className="shrink-0 font-mono text-[0.875rem] font-medium text-[var(--text-primary)]">
                        {formatCost(datum.total)}
                      </p>
                    </div>

                    {rows.length > 0 ? (
                      <div className="mt-2 space-y-1.5">
                        {rows.map((item) => (
                          <div key={item.key} className="flex items-center justify-between gap-3 text-[12px]">
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
                              <span className="truncate text-[var(--text-secondary)]">{item.label}</span>
                            </div>
                            <span className="font-mono text-[var(--text-primary)]">{formatCost(item.value)}</span>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              }}
            />

            <Area
              type="monotone"
              dataKey="total"
              stroke="transparent"
              fill={primaryColor}
              fillOpacity={0.06}
            />

            <Line
              type="monotone"
              dataKey="total"
              stroke={primaryColor}
              strokeWidth={1.75}
              dot={(props) => {
                const { cx, cy, payload } = props as {
                  cx?: number;
                  cy?: number;
                  payload?: CostChartDatum;
                };
                if (cx == null || cy == null || !payload) return null;

                const isHighlighted =
                  payload.bucket === peakDatum?.bucket || payload.bucket === activeDatum?.bucket;

                if (!isHighlighted) {
                  return <g key={`dot-${payload.bucket}`} />;
                }

                return (
                  <circle
                    key={`dot-${payload.bucket}`}
                    cx={cx}
                    cy={cy}
                    r={4.5}
                    fill={primaryColor}
                    stroke="var(--surface-elevated)"
                    strokeWidth={1.5}
                  />
                );
              }}
              activeDot={{
                r: 5,
                fill: primaryColor,
                stroke: "var(--surface-elevated)",
                strokeWidth: 1.5,
              }}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
              </ComposedChart>
            </div>
          ) : (
            <div className="h-full w-full rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]" />
          )}
        </div>
      </div>
    </section>
  );
}
