"use client";

import { useMemo } from "react";
import type { BotStats } from "@/lib/types";

export interface DailyActivityCell {
  date: string;
  count: number;
  cost: number;
  intensity: 0 | 1 | 2 | 3 | 4;
}

export interface DailyActivityResult {
  cells: DailyActivityCell[];
  weeks: DailyActivityCell[][];
  totalDays: number;
  totalCount: number;
  maxCount: number;
  maxCost: number;
}

const DEFAULT_WEEKS = 26;
const DAYS_PER_WEEK = 7;

function isoDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function bucketIntensity(cost: number, count: number, maxCost: number): DailyActivityCell["intensity"] {
  if (count <= 0 && cost <= 0) return 0;
  if (maxCost <= 0) return count > 0 ? 1 : 0;
  const normalized = cost / maxCost;
  if (normalized > 0.7) return 4;
  if (normalized > 0.4) return 3;
  if (normalized > 0.15) return 2;
  return 1;
}

export function useDailyActivity(
  statsList: Array<{ stats?: BotStats | null }>,
  options: { weeks?: number } = {},
): DailyActivityResult {
  const weeks = options.weeks ?? DEFAULT_WEEKS;

  return useMemo(() => {
    const totalDays = weeks * DAYS_PER_WEEK;
    const byDate = new Map<string, { cost: number; count: number }>();

    for (const entry of statsList) {
      const daily = entry.stats?.dailyCosts ?? [];
      for (const item of daily) {
        if (!item?.date) continue;
        const prev = byDate.get(item.date) ?? { cost: 0, count: 0 };
        prev.cost += item.cost ?? 0;
        prev.count += 1;
        byDate.set(item.date, prev);
      }
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dayOfWeek = today.getDay();
    const endDate = new Date(today);
    endDate.setDate(today.getDate() + (DAYS_PER_WEEK - 1 - dayOfWeek));
    const startDate = new Date(endDate);
    startDate.setDate(endDate.getDate() - (totalDays - 1));

    const cells: DailyActivityCell[] = [];
    let maxCost = 0;
    let maxCount = 0;
    for (let i = 0; i < totalDays; i += 1) {
      const cursor = new Date(startDate);
      cursor.setDate(startDate.getDate() + i);
      const key = isoDate(cursor);
      const bucket = byDate.get(key);
      const cost = bucket?.cost ?? 0;
      const count = bucket?.count ?? 0;
      if (cost > maxCost) maxCost = cost;
      if (count > maxCount) maxCount = count;
      cells.push({ date: key, cost, count, intensity: 0 });
    }

    for (const cell of cells) {
      cell.intensity = bucketIntensity(cell.cost, cell.count, maxCost);
    }

    const weeksGrid: DailyActivityCell[][] = [];
    for (let i = 0; i < weeks; i += 1) {
      weeksGrid.push(cells.slice(i * DAYS_PER_WEEK, (i + 1) * DAYS_PER_WEEK));
    }

    const totalCount = cells.reduce((sum, cell) => sum + cell.count, 0);

    return { cells, weeks: weeksGrid, totalDays, totalCount, maxCount, maxCost };
  }, [statsList, weeks]);
}
