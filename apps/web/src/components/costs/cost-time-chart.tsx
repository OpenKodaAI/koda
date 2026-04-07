"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { TrendingUp } from "lucide-react";
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
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getCurrentLanguage } from "@/lib/i18n";
import { cn, formatCost } from "@/lib/utils";
import { getBotLabel } from "@/lib/bot-constants";
import type { CostTimePoint } from "@/lib/types";

export type CostTimelineMode = "bot" | "model";

const BOT_PALETTE = ["#FF4B33", "#FF8A3D", "#FFC552", "#94E676", "#7AC6FF"];
const MODEL_PALETTE = ["#FF613F", "#FF8F5A", "#FFC85E", "#7FD7B8", "#78A6FF"];

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
  return mode === "bot" ? (point.by_bot[key] ?? 0) : (point.by_model[key] ?? 0);
}

function getTopDriver(point: CostTimePoint, mode: CostTimelineMode) {
  const source = mode === "bot" ? point.by_bot : point.by_model;
  const winner = Object.entries(source).sort((left, right) => right[1] - left[1])[0]?.[0];
  if (!winner) return null;
  return mode === "bot" ? getBotLabel(winner) : winner;
}

function buildSeries(points: CostTimePoint[], mode: CostTimelineMode) {
  const totals = new Map<string, number>();

  for (const point of points) {
    const source = mode === "bot" ? point.by_bot : point.by_model;
    for (const [key, value] of Object.entries(source)) {
      totals.set(key, (totals.get(key) ?? 0) + value);
    }
  }

  const palette = mode === "bot" ? BOT_PALETTE : MODEL_PALETTE;

  return [...totals.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, 5)
    .map(([key, total], index) => ({
      key,
      dataKey: `series_${index}`,
      total,
      color: palette[index % palette.length],
      label: mode === "bot" ? getBotLabel(key) : key,
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

  const lowDatum = useMemo(() => {
    if (data.length === 0) return null;
    return data.reduce((best, point) => (point.total < best.total ? point : best), data[0]);
  }, [data]);

  const lastDatum = data.at(-1) ?? null;
  const activeDatum = data.find((item) => item.bucket === hoveredBucket) ?? peakDatum ?? data[0] ?? null;
  const primaryColor = series[0]?.color ?? "#FF8A3D";

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
          "flex min-h-[360px] items-center justify-center rounded-[18px] border border-dashed border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] text-sm text-[var(--text-tertiary)]",
        className
      )}
    >
        {t("costs.page.timeChart.empty", {
          defaultValue: "Not enough data to build the temporal origin.",
        })}
      </div>
    );
  }

  const totalDelta =
    data.length > 1 && data[0].total > 0
      ? ((data[data.length - 1].total - data[0].total) / data[0].total) * 100
      : null;

  return (
    <section
      className={cn(
        "overflow-hidden rounded-[18px] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-5 sm:p-6",
        className
      )}
    >
      <div className="flex flex-col gap-4 border-b border-[var(--border-subtle)] pb-4">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-start">
          <div className="min-w-0">
            <p className="eyebrow">{t("costs.chart.eyebrow")}</p>
            <h3 className="mt-2 text-[1.15rem] font-semibold tracking-[-0.05em] text-[var(--text-primary)] sm:text-[1.35rem]">
              {t("costs.chart.title")}
            </h3>
            <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px] text-[var(--text-secondary)]">
              <span className="inline-flex items-center gap-2">
                <span className="text-[var(--text-tertiary)]">{t("costs.page.timeChart.peak", { defaultValue: "Peak:" })}</span>
                <span className="font-medium text-[var(--text-primary)]">
                  {peakDatum ? formatCost(peakDatum.total) : "—"}
                </span>
              </span>
              <span className="inline-flex items-center gap-2">
                <span className="text-[var(--text-tertiary)]">{t("costs.page.timeChart.base", { defaultValue: "Base:" })}</span>
                <span className="font-medium text-[var(--text-primary)]">
                  {lowDatum ? formatCost(lowDatum.total) : "—"}
                </span>
              </span>
              <span className="inline-flex items-center gap-2">
                <span className="text-[var(--text-tertiary)]">{t("costs.page.timeChart.buckets", { defaultValue: "Buckets:" })}</span>
                <span className="font-medium text-[var(--text-primary)]">{data.length}</span>
              </span>
              <span className="inline-flex items-center gap-2">
                <span className="text-[var(--text-tertiary)]">{t("costs.page.timeChart.variation", { defaultValue: "Variation:" })}</span>
                <span
                  className={cn(
                    "font-medium",
                    totalDelta != null && totalDelta >= 0
                      ? "text-[var(--tone-success-dot)]"
                      : "text-[var(--tone-warning-dot)]"
                  )}
                >
                  {totalDelta == null ? "—" : `${totalDelta > 0 ? "+" : ""}${totalDelta.toFixed(1)}%`}
                </span>
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-start justify-start gap-2 xl:justify-end">
            <div className="rounded-[14px] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-3.5 py-2.5 text-right">
              <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[var(--text-quaternary)]">
                {activeDatum?.label ?? t("costs.page.timeChart.noBucket", { defaultValue: "No bucket" })}
              </p>
              <p className="mt-1 font-mono text-[0.96rem] font-medium text-[var(--text-primary)]">
                {activeDatum ? formatCost(activeDatum.total) : "—"}
              </p>
              <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">
                {activeDatum?.driverLabel
                  ? t("costs.page.timeChart.driver", {
                      defaultValue: "Driver · {{value}}",
                      value: activeDatum.driverLabel,
                    })
                  : t("costs.page.timeChart.noDriver", { defaultValue: "No dominant driver" })}
              </p>
            </div>

            <div className="segmented-control segmented-control--single-row cost-time-chart__mode-toggle self-start">
              {(["bot", "model"] as CostTimelineMode[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => onModeChange?.(item)}
                  className={cn("segmented-control__option", mode === item && "is-active")}
                  aria-pressed={mode === item}
                >
                  {item === "bot" ? t("costs.mode.byBot") : t("costs.mode.byModel")}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
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
                className="inline-flex items-center gap-2 rounded-[12px] border px-3 py-1.5 text-[11px] font-medium transition-all"
                style={{
                  borderColor: isDimmed
                    ? "var(--border-subtle)"
                    : `color-mix(in srgb, ${item.color} 42%, var(--border-subtle) 58%)`,
                  background: isDimmed
                    ? "var(--surface-panel-soft)"
                    : `color-mix(in srgb, ${item.color} 10%, var(--surface-panel-soft) 90%)`,
                  color: isDimmed ? "var(--text-secondary)" : "var(--text-primary)",
                }}
              >
                <span className="h-2.5 w-2.5 rounded-[2px]" style={{ backgroundColor: item.color }} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="pt-4">
        <div ref={chartHostRef} className="h-[340px] w-full min-w-0">
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
                margin={{ top: 18, right: 12, left: 6, bottom: 12 }}
                onMouseMove={(state) => {
                  const payload = (
                    state as { activePayload?: Array<{ payload?: CostChartDatum }> } | undefined
                  )?.activePayload?.[0]?.payload;
                  setHoveredBucket(payload?.bucket ?? null);
                }}
                onMouseLeave={() => setHoveredBucket(null)}
              >
            <defs>
              <linearGradient id="costAreaGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={primaryColor} stopOpacity={0.2} />
                <stop offset="100%" stopColor={primaryColor} stopOpacity={0} />
              </linearGradient>
              <pattern id="costDotGrid" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
                <circle
                  cx="10"
                  cy="10"
                  r="1"
                  fill="color-mix(in srgb, var(--text-primary) 10%, transparent)"
                />
              </pattern>
            </defs>

            <rect x="0" y="0" width="100%" height="100%" fill="url(#costDotGrid)" style={{ pointerEvents: "none" }} />
            {activeDatum ? (
              <ReferenceLine
                x={activeDatum.label}
                stroke={primaryColor}
                strokeDasharray="4 4"
                strokeOpacity={0.45}
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
              tick={{ fontSize: 12, fill: "var(--text-tertiary)" }}
              tickMargin={12}
              tickFormatter={formatAxisValue}
            />

            <ChartTooltip
              cursor={{
                strokeDasharray: "3 3",
                stroke: "color-mix(in srgb, var(--text-primary) 20%, transparent)",
                strokeOpacity: 0.5,
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
                  <div className="min-w-[min(220px,calc(100vw-3rem))] max-w-[calc(100vw-3rem)] rounded-[14px] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-3.5 py-3">
                    <p className="text-[11px] font-medium text-[var(--text-tertiary)]">{datum.label}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <p className="font-mono text-[1rem] font-semibold text-[var(--text-primary)]">
                        {formatCost(datum.total)}
                      </p>
                      <span className="inline-flex items-center gap-1 text-[11px] text-[var(--tone-success-dot)]">
                        <TrendingUp className="h-3.5 w-3.5" />
                        {datum.driverLabel ?? "Sem driver"}
                      </span>
                    </div>

                    {rows.length > 0 ? (
                      <div className="mt-3 space-y-2">
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
              fill="url(#costAreaGradient)"
              fillOpacity={1}
            />

            <Line
              type="monotone"
              dataKey="total"
              stroke={primaryColor}
              strokeWidth={2.25}
              dot={(props) => {
                const { cx, cy, payload } = props as {
                  cx?: number;
                  cy?: number;
                  payload?: CostChartDatum;
                };
                if (cx == null || cy == null || !payload) return null;

                const isHighlighted =
                  payload.bucket === peakDatum?.bucket ||
                  payload.bucket === lowDatum?.bucket ||
                  payload.bucket === lastDatum?.bucket ||
                  payload.bucket === activeDatum?.bucket;

                if (!isHighlighted) {
                  return <g key={`dot-${payload.bucket}`} />;
                }

                return (
                  <circle
                    key={`dot-${payload.bucket}`}
                    cx={cx}
                    cy={cy}
                    r={5.5}
                    fill={primaryColor}
                    stroke="var(--surface-elevated)"
                    strokeWidth={2}
                  />
                );
              }}
              activeDot={{
                r: 6,
                fill: primaryColor,
                stroke: "var(--surface-elevated)",
                strokeWidth: 2,
              }}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
              </ComposedChart>
            </div>
          ) : (
            <div className="h-full w-full rounded-[18px] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]" />
          )}
        </div>
      </div>
    </section>
  );
}
