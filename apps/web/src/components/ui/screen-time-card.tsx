"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { cn } from "@/lib/utils";

interface AppUsage {
  icon: React.ReactNode;
  name: string;
  duration: string;
  color?: string;
}

interface ScreenTimeCardProps {
  totalHours: number;
  totalMinutes: number;
  barData: number[];
  timeLabels?: string[];
  topApps: AppUsage[];
  className?: string;
}

export const ScreenTimeCard = ({
  totalHours,
  totalMinutes,
  barData,
  timeLabels = ["00h", "06h", "12h", "18h", "23h"],
  topApps,
  className,
}: ScreenTimeCardProps) => {
  const { t } = useAppI18n();
  const safeBarData = barData.length > 0 ? barData : Array.from({ length: 24 }, () => 0);
  const maxValue = Math.max(...safeBarData, 1);
  const normalizedData = safeBarData.map((value) => Math.max(value, 0) / maxValue);

  const getBarStyle = (height: number) => {
    if (height >= 0.74) {
      return {
        background:
          "linear-gradient(180deg, #E4B454 0%, #98702D 100%)",
      };
    }

    if (height >= 0.4) {
      return {
        background:
          "linear-gradient(180deg, #78A6FF 0%, #3C69AE 100%)",
      };
    }

    return {
      background:
        "linear-gradient(180deg, #A9B2BE 0%, #525963 100%)",
    };
  };

  const barVariants = {
    hidden: { scaleY: 0, opacity: 0.3 },
    visible: (index: number) => ({
      scaleY: 1,
      opacity: 1,
      transition: {
        delay: index * 0.018,
        type: "spring" as const,
        stiffness: 110,
        damping: 16,
      },
    }),
  };

  return (
    <div
      className={cn(
        "w-full text-[var(--text-primary)]",
        className
      )}
    >
      <div className={cn(
        "grid gap-5 lg:items-stretch",
        topApps.length > 0 ? "lg:grid-cols-[minmax(0,1.7fr)_minmax(260px,0.68fr)]" : ""
      )}>
        <div className="min-w-0">
          <div className="relative flex h-full min-h-[300px] flex-col overflow-hidden">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                  {t("screenTime.aggregate", { defaultValue: "Aggregate activity" })}
                </p>
                <div className="mt-1.5 flex items-end gap-3">
                  <span className="text-[1.9rem] font-semibold tracking-[-0.06em] text-[var(--text-primary)] sm:text-[2.15rem]">
                    {totalHours}h {totalMinutes}m
                  </span>
                  <span className="pb-1 text-[11px] font-medium text-[var(--text-tertiary)]">
                    {t("screenTime.last24h", { defaultValue: "in the last 24h" })}
                  </span>
                </div>
              </div>
              <p className="shrink-0 text-[11px] font-medium text-[var(--text-tertiary)]">
                {t("screenTime.hourlyWindow", { defaultValue: "consolidated hourly window" })}
              </p>
            </div>

            <div className="pointer-events-none absolute inset-x-4 top-[88px] flex h-[168px] flex-col justify-between sm:inset-x-5 sm:top-[92px] sm:h-[182px]">
              <div className="border-t border-dashed border-[var(--border-subtle)]" />
              <div className="border-t border-dashed border-[var(--border-subtle)]" />
              <div className="border-t border-dashed border-[var(--border-subtle)]" />
            </div>

            <div className="relative z-10 mb-3 flex h-[168px] flex-1 items-end gap-[4px] sm:h-[182px]">
              {normalizedData.map((height, index) => {
                const isHighlighted = height > 0.62;

                return (
                  <motion.div
                    key={index}
                    custom={index}
                    variants={barVariants}
                    initial="hidden"
                    animate="visible"
                    className={cn("min-w-0 flex-1 origin-bottom rounded-lg")}
                    style={{
                      ...getBarStyle(height),
                      boxShadow: isHighlighted
                        ? "inset 0 0 0 1px rgba(255,255,255,0.12), 0 8px 14px rgba(0,0,0,0.18)"
                        : "inset 0 0 0 1px rgba(255,255,255,0.06)",
                      height: `${Math.max(height * 100, 8)}%`,
                    }}
                  />
                );
              })}
            </div>

            <div className="flex items-center justify-between gap-3 text-[11px] font-medium text-[var(--text-tertiary)]">
              {timeLabels.map((label) => (
                <span key={label}>{label}</span>
              ))}
            </div>
          </div>
        </div>

        {topApps.length > 0 && <div className="min-w-0 border-t border-[var(--border-subtle)] pt-4 lg:flex lg:flex-col lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
          <div className="mb-3 flex items-center justify-between gap-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              {t("screenTime.focusBots", { defaultValue: "Bots in focus" })}
            </p>
            <span className="text-[11px] text-[var(--text-quaternary)]">
              {t("screenTime.items", { count: topApps.length, defaultValue: "{{count}} items" })}
            </span>
          </div>

          <div className="flex flex-col gap-2.5 lg:flex-1 lg:justify-center">
            {topApps.map((app, index) => (
              <motion.div
                key={`${app.name}-${index}`}
                initial={{ opacity: 0, x: 18 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.08 + 0.18 }}
                className="flex items-center gap-3 rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.022)] px-3 py-2.5"
                style={
                  app.color
                    ? {
                        background: `linear-gradient(180deg, color-mix(in srgb, ${app.color} 24%, #26282d) 0%, color-mix(in srgb, ${app.color} 14%, #16171a) 100%)`,
                        borderColor: `color-mix(in srgb, ${app.color} 54%, #292b31)`,
                      }
                    : undefined
                }
                >
                <div
                  className="flex h-7 w-7 shrink-0 items-center justify-center text-[var(--text-primary)]"
                  style={app.color ? { color: app.color } : undefined}
                >
                  {app.icon}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="line-clamp-1 text-sm font-medium text-[var(--text-primary)]">
                    {app.name}
                  </p>
                  <p className="line-clamp-1 text-xs text-[var(--text-tertiary)]">
                    {app.duration}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>}
      </div>
    </div>
  );
};
