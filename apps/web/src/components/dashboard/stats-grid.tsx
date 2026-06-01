"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { cn } from "@/lib/utils";

interface StatItem {
  label: string;
  value: string | number;
  trend?: string;
  sparklineData?: number[];
  sparklineColor?: string;
}

interface StatsGridProps {
  stats: StatItem[];
  className?: string;
}

type ParsedAnimatedValue =
  | {
      canAnimate: true;
      target: number;
      prefix: string;
      suffix: string;
      decimals: number;
      separator: "." | ",";
    }
  | {
      canAnimate: false;
      raw: string;
    };

function easeOutCubic(progress: number) {
  return 1 - Math.pow(1 - progress, 3);
}

function parseAnimatedValue(value: string | number): ParsedAnimatedValue {
  if (typeof value === "number") {
    return {
      canAnimate: true,
      target: value,
      prefix: "",
      suffix: "",
      decimals: Number.isInteger(value) ? 0 : 2,
      separator: ".",
    };
  }

  const match = value.match(/^([^0-9-]*)(-?\d+(?:[.,]\d+)?)(.*)$/);
  if (!match) {
    return { canAnimate: false, raw: value };
  }

  const [, prefix, numericPart, suffix] = match;
  const separator = numericPart.includes(",") ? "," : ".";
  const decimals = numericPart.includes(".") || numericPart.includes(",")
    ? numericPart.split(/[.,]/)[1]?.length ?? 0
    : 0;

  return {
    canAnimate: true,
    target: Number(numericPart.replace(",", ".")),
    prefix,
    suffix,
    decimals,
    separator,
  };
}

function formatAnimatedNumber(value: number, decimals: number, separator: string) {
  const formatted = value.toFixed(decimals);
  return separator === "," ? formatted.replace(".", ",") : formatted;
}

function AnimatedStatValue({ value }: { value: string | number }) {
  const parsed = useMemo(() => parseAnimatedValue(value), [value]);
  const [displayValue, setDisplayValue] = useState(0);
  const rafRef = useRef<number | null>(null);
  const displayedRef = useRef(0);

  useEffect(() => {
    if (!parsed.canAnimate) return undefined;

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const startValue = displayedRef.current;
    const endValue = parsed.target;

    if (prefersReducedMotion || startValue === endValue) {
      rafRef.current = window.requestAnimationFrame(() => {
        displayedRef.current = endValue;
        setDisplayValue(endValue);
      });
      return undefined;
    }

    const duration = 380;
    const startedAt = performance.now();

    const tick = (now: number) => {
      const progress = Math.min((now - startedAt) / duration, 1);
      const eased = easeOutCubic(progress);
      const nextValue = startValue + (endValue - startValue) * eased;
      displayedRef.current = nextValue;
      setDisplayValue(nextValue);

      if (progress < 1) {
        rafRef.current = window.requestAnimationFrame(tick);
      } else {
        displayedRef.current = endValue;
        setDisplayValue(endValue);
      }
    };

    if (rafRef.current) window.cancelAnimationFrame(rafRef.current);
    rafRef.current = window.requestAnimationFrame(tick);

    return () => {
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current);
    };
  }, [parsed]);

  if (!parsed.canAnimate) return <>{value}</>;

  return (
    <>
      {parsed.prefix}
      {formatAnimatedNumber(displayValue, parsed.decimals, parsed.separator)}
      {parsed.suffix}
    </>
  );
}

const MiniSparkline = memo(function MiniSparkline({ data, color }: { data: number[]; color: string }) {
  const chartData = useMemo(() => data.map((value) => ({ value })), [data]);
  const gradientId = `sparkline-${color.replace(/[^a-z0-9]/gi, "")}`;

  return (
    <div className="h-14 w-28 shrink-0">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 4, right: 2, left: 2, bottom: 4 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            fill={`url(#${gradientId})`}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
});

export const StatsGrid = memo(function StatsGrid({ stats, className }: StatsGridProps) {
  const hasExtendedGrid = stats.length > 4;

  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4",
        hasExtendedGrid && "xl:grid-cols-6",
        className
      )}
    >
      {stats.map((stat, index) => (
        <div
          key={stat.label}
          className={cn(
            "app-kpi-card glass-card-sm animate-in px-4 py-4 sm:px-5 sm:py-4",
            `stagger-${index + 1}`
          )}
        >
          <div className="flex items-end justify-between gap-3">
            <div className="min-w-0">
              <p className="app-kpi-card__label">{stat.label}</p>
              <p className="app-kpi-card__value tabular-nums">
                <AnimatedStatValue value={stat.value} />
              </p>
              {stat.trend && (
                <p className="app-kpi-card__hint line-clamp-1">{stat.trend}</p>
              )}
            </div>
            {stat.sparklineData && stat.sparklineData.length > 1 && (
              <MiniSparkline
                data={stat.sparklineData}
                color={stat.sparklineColor ?? "rgba(180,180,180,0.6)"}
              />
            )}
          </div>
        </div>
      ))}
    </div>
  );
});
