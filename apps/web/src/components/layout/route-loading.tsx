import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";

function SkeletonLine({
  className,
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return <div className={cn("skeleton rounded-xl", className)} style={style} aria-hidden="true" />;
}

export function MetricStripSkeleton({ count = 4 }: { count?: number }) {
  const columns = Math.max(1, Math.min(count, 4));
  const mobileColumns = Math.max(1, Math.min(count, 2));

  return (
    <div
      className="metric-strip"
      data-count={count}
      style={{
        "--metric-strip-columns": String(columns),
        "--metric-strip-mobile-columns": String(mobileColumns),
      } as CSSProperties}
    >
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="metric-strip__item">
          <SkeletonLine className="mb-1 h-3 w-24 rounded" />
          <SkeletonLine className="h-6 w-16 rounded" />
          <SkeletonLine className="h-3 w-32 rounded" />
        </div>
      ))}
    </div>
  );
}

function CompactAgentSwitcherSkeleton() {
  return <SkeletonLine className="h-10 w-full rounded-[var(--radius-input)]" />;
}

function SoftTabsSkeleton({ count = 3, itemWidth = "w-24" }: { count?: number; itemWidth?: string }) {
  return (
    <div className="flex flex-wrap items-center gap-1 rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-1">
      {Array.from({ length: count }).map((_, index) => (
        <SkeletonLine key={index} className={cn("h-7 rounded-[var(--radius-panel-sm)]", itemWidth)} />
      ))}
    </div>
  );
}

export function SetupChecklistSkeleton() {
  return (
    <section className="relative flex flex-col gap-3 rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-4 py-3.5">
      <header className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-2">
          <SkeletonLine className="h-4 w-40 rounded" />
          <SkeletonLine className="h-3 w-72 rounded" />
        </div>
        <SkeletonLine className="h-7 w-7 rounded-[var(--radius-panel-sm)]" />
      </header>
      <div className="flex flex-col gap-0.5">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="flex items-center gap-3 border-t border-[color:var(--divider-hair)] px-1.5 py-2 first:border-t-0">
            <SkeletonLine className="h-6 w-6 rounded-full" />
            <SkeletonLine className="h-3 flex-1 rounded" />
            <SkeletonLine className="h-3.5 w-3.5 rounded" />
          </div>
        ))}
      </div>
    </section>
  );
}

export function ActivityHeatmapSkeleton() {
  return (
    <section className="relative flex w-full flex-col gap-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="w-[200px]">
          <CompactAgentSwitcherSkeleton />
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:justify-end">
          <SoftTabsSkeleton count={3} itemWidth="w-16" />
          <div className="hidden items-center gap-1.5 sm:flex">
            <SkeletonLine className="h-2.5 w-8 rounded" />
            <div className="flex gap-[3px]">
              {Array.from({ length: 5 }).map((_, index) => (
                <SkeletonLine key={index} className="h-[10px] w-[10px] rounded-[3px]" />
              ))}
            </div>
            <SkeletonLine className="h-2.5 w-8 rounded" />
          </div>
        </div>
      </header>

      <MetricStripSkeleton count={4} />

      <div className="flex w-full flex-col items-center gap-2">
        <div className="grid max-w-full grid-flow-col grid-rows-7 gap-[5px] overflow-hidden">
          {Array.from({ length: 26 * 7 }).map((_, index) => (
            <SkeletonLine key={index} className="h-7 w-7 rounded-[5px]" />
          ))}
        </div>
      </div>
    </section>
  );
}

export function ExecutionHistorySkeleton() {
  return (
    <section className="w-full">
      <header className="mb-3 flex items-baseline justify-between px-3">
        <SkeletonLine className="h-5 w-36 rounded" />
        <SkeletonLine className="h-3 w-24 rounded" />
      </header>
      <ul className="flex w-full flex-col">
        {Array.from({ length: 8 }).map((_, index) => (
          <li key={index}>
            <div
              className={cn(
                "grid w-full grid-cols-[200px_minmax(0,1fr)_auto] items-center gap-5 px-3 py-3.5",
                index > 0 && "border-t border-[color:var(--divider-hair)]",
              )}
            >
              <div className="flex min-w-0 items-center gap-3">
                <SkeletonLine className="h-6 w-6 rounded-full" />
                <SkeletonLine className="h-3.5 w-32 rounded" />
              </div>
              <SkeletonLine className="h-3.5 w-[72%] rounded" />
              <div className="flex shrink-0 flex-col items-end gap-1.5">
                <SkeletonLine className="h-3 w-20 rounded" />
                <SkeletonLine className="h-2.5 w-12 rounded" />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function OverviewRouteLoading() {
  return (
    <div className="relative" data-testid="overview-route-loading">
      <section className="mx-auto flex w-full max-w-[760px] flex-col items-stretch gap-7 pb-2 pt-10">
        <header className="flex flex-col items-center gap-3 text-center">
          <SkeletonLine className="h-12 w-full max-w-[520px] rounded" />
        </header>
        <div className="flex flex-col gap-3">
          <SkeletonLine className="h-14 w-full rounded-[var(--radius-input)]" />
          <div className="flex flex-wrap items-center justify-center gap-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <SkeletonLine key={index} className="h-8 w-32 rounded-[var(--radius-pill)]" />
            ))}
          </div>
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-[1320px] flex-col gap-6 pt-6">
        <SetupChecklistSkeleton />
        <ActivityHeatmapSkeleton />
        <ExecutionHistorySkeleton />
      </div>
    </div>
  );
}

export function AccountRouteLoading() {
  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-4 px-4 py-5 sm:px-6 lg:px-8" data-testid="account-route-loading">
      <div className="space-y-2">
        <SkeletonLine className="h-5 w-28 rounded" />
        <SkeletonLine className="h-3 w-72 rounded" />
      </div>
      <div className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)]">
        <div className="border-b border-[var(--divider-hair)] px-5 py-4">
          <SkeletonLine className="h-4 w-32 rounded" />
        </div>
        <div className="grid lg:grid-cols-[260px_minmax(0,1fr)]">
          <div className="space-y-4 border-b border-[var(--divider-hair)] p-5 lg:border-b-0 lg:border-r">
            <div className="flex flex-col items-center gap-3">
              <SkeletonLine className="h-24 w-24 rounded-full" />
              <SkeletonLine className="h-3 w-32 rounded" />
            </div>
            <div className="grid grid-cols-5 gap-2">
              {Array.from({ length: 10 }).map((_, index) => (
                <SkeletonLine key={index} className="h-10 rounded-[var(--radius-panel-sm)]" />
              ))}
            </div>
          </div>
          <div>
            <div className="border-b border-[var(--divider-hair)] p-4">
              <SkeletonLine className="mb-2 h-2.5 w-24 rounded" />
              <div className="flex flex-col gap-2 sm:flex-row">
                <SkeletonLine className="h-9 flex-1 rounded-[var(--radius-input)]" />
                <div className="flex gap-2">
                  <SkeletonLine className="h-9 w-20 rounded-[var(--radius-panel-sm)]" />
                  <SkeletonLine className="h-9 w-20 rounded-[var(--radius-panel-sm)]" />
                </div>
              </div>
            </div>
            <div className="grid sm:grid-cols-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={index} className="flex items-start gap-3 border-b border-[var(--divider-hair)] px-4 py-3.5 sm:border-r">
                  <SkeletonLine className="h-7 w-7 rounded-md" />
                  <div className="min-w-0 flex-1 space-y-2">
                    <SkeletonLine className="h-2.5 w-20 rounded" />
                    <SkeletonLine className="h-3.5 w-32 rounded" />
                  </div>
                </div>
              ))}
            </div>
            <div className="col-span-full flex items-center justify-between gap-3 px-4 py-4">
              <SkeletonLine className="h-3 w-48 rounded" />
              <SkeletonLine className="h-9 w-24 rounded-[var(--radius-panel-sm)]" />
            </div>
          </div>
        </div>
      </div>
      <div className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)]">
        <div className="border-b border-[var(--divider-hair)] px-5 py-4">
          <div className="flex items-center gap-2">
            <SkeletonLine className="h-4 w-4 rounded" />
            <SkeletonLine className="h-4 w-36 rounded" />
          </div>
        </div>
        <div className="grid gap-px bg-[var(--divider-hair)] sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="bg-[var(--panel)] px-4 py-3">
              <SkeletonLine className="h-2.5 w-20 rounded" />
              <SkeletonLine className="mt-2 h-3.5 w-24 rounded" />
            </div>
          ))}
        </div>
        <div className="grid divide-y divide-[var(--divider-hair)] lg:grid-cols-2 lg:divide-x lg:divide-y-0">
          {Array.from({ length: 2 }).map((_, index) => (
            <div key={index} className="flex flex-col gap-3 p-5">
              <div className="flex items-start gap-3">
                <SkeletonLine className="h-8 w-8 rounded-lg" />
                <div className="space-y-2">
                  <SkeletonLine className="h-4 w-44 rounded" />
                  <SkeletonLine className="h-3 w-64 rounded" />
                </div>
              </div>
              <SkeletonLine className="h-9 w-full rounded-[var(--radius-input)]" />
              {index === 0 ? <SkeletonLine className="h-9 w-full rounded-[var(--radius-input)]" /> : null}
              <SkeletonLine className="h-9 w-44 rounded-[var(--radius-panel-sm)]" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function AuthRouteLoading() {
  return (
    <div className="relative flex min-h-[100dvh] w-full flex-col overflow-hidden bg-[var(--canvas)] text-[var(--text-primary)]" data-testid="auth-route-loading">
      <header className="relative z-10 flex h-14 shrink-0 items-center justify-end px-5">
        <div className="flex items-center gap-2">
          <SkeletonLine className="h-9 w-28 rounded-[var(--radius-input)]" />
          <SkeletonLine className="h-9 w-9 rounded-[var(--radius-input)]" />
        </div>
      </header>
      <main className="relative z-10 flex flex-1 flex-col items-center justify-center px-5 pb-16">
        <div className="flex w-full max-w-[440px] flex-col items-stretch gap-8">
          <div className="min-h-[300px]">
            <div className="auth-form">
              <div className="auth-form__hero">
                <SkeletonLine className="auth-form__logo rounded-[var(--radius-panel-sm)]" />
                <div className="auth-form__title-block">
                  <SkeletonLine className="mx-auto h-7 w-48 rounded" />
                  <SkeletonLine className="mx-auto h-3 w-72 rounded" />
                </div>
              </div>
              <div className="auth-form__fields">
                {Array.from({ length: 2 }).map((_, index) => (
                  <div key={index} className="auth-field">
                    <SkeletonLine className="h-3 w-24 rounded" />
                    <SkeletonLine className="h-11 w-full rounded-[var(--radius-input)]" />
                  </div>
                ))}
              </div>
              <SkeletonLine className="h-11 w-full rounded-[var(--radius-input)]" />
              <SkeletonLine className="mx-auto h-3 w-32 rounded" />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export function RuntimeRouteLoading() {
  return (
    <div className="runtime-shell space-y-6" data-testid="runtime-route-loading">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <SkeletonLine className="mb-2 h-3 w-20 rounded" />
          <SkeletonLine className="h-7 w-56 rounded" />
        </div>
        <div className="flex w-full flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center lg:w-auto lg:justify-end">
          <div className="w-full sm:w-[220px]">
            <CompactAgentSwitcherSkeleton />
          </div>
          <div className="inline-flex h-9 w-full items-center gap-2 rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 sm:w-auto">
            <SkeletonLine className="h-3.5 w-3.5 rounded-full" />
            <SkeletonLine className="h-3 w-44 rounded" />
          </div>
          <SoftTabsSkeleton count={4} itemWidth="w-20" />
        </div>
      </div>
      <MetricStripSkeleton count={4} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_320px]">
        <section>
          <header className="mb-2 flex items-baseline justify-between px-3">
            <SkeletonLine className="h-5 w-36 rounded" />
            <SkeletonLine className="h-3 w-12 rounded" />
          </header>
          <div className="flex flex-col">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="grid items-center gap-4 border-b border-[color:var(--divider-hair)] px-3 py-3 last:border-b-0 md:grid-cols-[minmax(0,1fr)_auto]">
                <div className="flex min-w-0 items-center gap-3">
                  <SkeletonLine className="h-7 w-7 rounded-full" />
                  <div className="min-w-0 flex-1 space-y-2">
                    <SkeletonLine className="h-3.5 w-[42%] rounded" />
                    <SkeletonLine className="h-3 w-[76%] rounded" />
                  </div>
                </div>
                <div className="flex items-center justify-end gap-3">
                  <SkeletonLine className="h-3 w-16 rounded" />
                  <SkeletonLine className="h-6 w-20 rounded-full" />
                </div>
              </div>
            ))}
          </div>
        </section>
        <aside>
          <header className="mb-2 flex items-baseline justify-between px-3">
            <SkeletonLine className="h-5 w-20 rounded" />
            <SkeletonLine className="h-3 w-10 rounded" />
          </header>
          <div className="flex flex-col">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="flex items-center justify-between gap-3 border-b border-[color:var(--divider-hair)] px-3 py-3 last:border-b-0">
                <div className="flex min-w-0 items-center gap-3">
                  <SkeletonLine className="h-7 w-7 rounded-full" />
                  <SkeletonLine className="h-3.5 w-28 rounded" />
                </div>
                <div className="flex items-center gap-3">
                  <SkeletonLine className="h-3 w-10 rounded" />
                  <SkeletonLine className="h-3 w-8 rounded" />
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}

export function TableRouteLoading() {
  return (
    <div className="min-w-0 space-y-4" data-testid="table-route-loading">
      {/* Controls bar — matches real: AgentSwitcher + search + filter row */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="max-w-[350px] min-w-[200px]">
          <div className="skeleton h-11 w-full rounded-xl" />
        </div>
        <div className="skeleton h-10 w-full rounded-lg xl:w-[280px] xl:flex-none" />
        <div className="app-filter-row w-full">
          <div className="skeleton h-7 w-16 rounded-full" />
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton h-9 w-20 rounded-full" />
          ))}
        </div>
      </div>

      {/* Metric strip */}
      <div className="metric-strip">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="metric-strip__item">
            <div className="skeleton h-3 w-16 mb-1" />
            <div className="skeleton h-6 w-20" />
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="app-section min-h-[520px] p-5 sm:p-6" />
    </div>
  );
}

function TableToolbarSkeleton({
  search = false,
  tabs = false,
  action = false,
}: {
  search?: boolean;
  tabs?: boolean;
  action?: boolean;
}) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
      <div className="w-full md:w-[220px] md:flex-none">
        <CompactAgentSwitcherSkeleton />
      </div>
      {search ? (
        <div className="w-full md:min-w-[200px] md:flex-1">
          <SkeletonLine className="h-10 w-full rounded-[var(--radius-input)]" />
        </div>
      ) : null}
      {tabs ? (
        <div className="w-full md:w-auto md:shrink-0 md:ml-auto">
          <SoftTabsSkeleton count={3} itemWidth="w-24" />
        </div>
      ) : null}
      {action ? (
        <div className="md:ml-auto">
          <SkeletonLine className="h-9 w-36 rounded-[var(--radius-input)]" />
        </div>
      ) : null}
    </div>
  );
}

function CostLedgerSkeleton() {
  return (
    <section className="overflow-hidden rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)]">
      <div className="flex min-w-0 items-center justify-between gap-4 border-b border-[var(--border-subtle)] px-4 py-3 sm:px-5">
        <div className="min-w-0 space-y-2">
          <SkeletonLine className="h-3 w-24 rounded" />
          <SkeletonLine className="h-5 w-40 rounded" />
        </div>
        <SkeletonLine className="h-3 w-14 rounded" />
      </div>
      <div className="divide-y divide-[var(--border-subtle)]">
        {Array.from({ length: 5 }).map((_, index) => (
          <article key={index} className="grid min-w-0 gap-3 px-4 py-3 sm:px-5 lg:grid-cols-[minmax(0,1fr)_112px] lg:items-center">
            <div className="min-w-0 space-y-2">
              <div className="flex min-w-0 items-center gap-3">
                <SkeletonLine className="h-3.5 w-44 rounded" />
                <SkeletonLine className="h-3 w-20 rounded" />
                <SkeletonLine className="h-3 w-16 rounded" />
              </div>
              <SkeletonLine className="h-3 w-[72%] rounded" />
              <SkeletonLine className="h-3 w-[54%] rounded" />
            </div>
            <div className="flex items-center justify-between gap-3 text-left lg:block lg:text-right">
              <SkeletonLine className="h-3 w-12 rounded lg:ml-auto" />
              <SkeletonLine className="h-4 w-20 rounded lg:ml-auto lg:mt-2" />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function CostRouteLoading() {
  return (
    <div className="min-w-0 space-y-4" data-testid="cost-route-loading">
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
        <div className="w-full md:w-[220px] md:flex-none">
          <CompactAgentSwitcherSkeleton />
        </div>
        <SoftTabsSkeleton count={3} itemWidth="w-20" />
        <div className="w-full md:w-auto md:flex-none md:ml-auto">
          <SkeletonLine className="h-9 min-w-[160px] rounded-[var(--radius-panel-sm)]" />
        </div>
        <div className="w-full md:w-auto md:flex-none">
          <SkeletonLine className="h-9 min-w-[160px] rounded-[var(--radius-panel-sm)]" />
        </div>
      </div>

      <section className="space-y-4">
        <MetricStripSkeleton count={4} />
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.9fr)] xl:items-start">
          <div className="min-h-[360px] rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)]" />
          <div className="min-h-[360px] rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)]" />
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-4">
            <SkeletonLine className="mb-4 h-5 w-40 rounded" />
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((__, rowIndex) => (
                <div key={rowIndex} className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-[color:var(--divider-hair)] py-2.5 last:border-b-0">
                  <div className="space-y-2">
                    <SkeletonLine className="h-3 w-36 rounded" />
                    <SkeletonLine className="h-2.5 w-24 rounded" />
                  </div>
                  <SkeletonLine className="h-4 w-14 rounded" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      <CostLedgerSkeleton />
    </div>
  );
}

function DLQTableSkeleton() {
  const stickyLastStyle = { "--sticky-last-width": "192px" } as CSSProperties;

  return (
    <>
      <div className="hidden md:block">
        <div className="table-shell" style={stickyLastStyle}>
          <table className="glass-table glass-table--sticky-last min-w-[1340px] table-fixed">
            <colgroup>
              <col className="w-[140px]" />
              <col className="w-[128px]" />
              <col className="w-[360px]" />
              <col className="w-[360px]" />
              <col className="w-[160px]" />
              <col className="w-[192px]" />
            </colgroup>
            <thead>
              <tr>
                {Array.from({ length: 6 }).map((_, index) => (
                  <th
                    key={index}
                    className={cn(index === 5 && "text-right")}
                  >
                    <SkeletonLine className={cn("h-3 w-20 rounded", index === 5 && "ml-auto")} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 5 }).map((_, index) => (
                <tr key={index}>
                  <td>
                    <SkeletonLine className="mb-2 h-3 w-16 rounded" />
                    <SkeletonLine className="h-2.5 w-24 rounded" />
                  </td>
                  <td>
                    <SkeletonLine className="mb-2 h-3 w-12 rounded" />
                    <SkeletonLine className="h-2.5 w-20 rounded" />
                  </td>
                  <td>
                    <SkeletonLine className="mb-2 h-3 w-[84%] rounded" />
                    <SkeletonLine className="h-3 w-[62%] rounded" />
                  </td>
                  <td>
                    <SkeletonLine className="mb-2 h-3 w-[78%] rounded" />
                    <SkeletonLine className="h-2.5 w-32 rounded" />
                  </td>
                  <td>
                    <SkeletonLine className="mb-2 h-3 w-20 rounded" />
                    <SkeletonLine className="h-2.5 w-24 rounded" />
                  </td>
                  <td className="text-right">
                    <SkeletonLine className="ml-auto h-3 w-20 rounded" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="flex flex-col md:hidden">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="flex flex-col gap-2 border-b border-[color:var(--divider-hair)] py-3 last:border-b-0">
            <SkeletonLine className="h-3 w-32 rounded" />
            <SkeletonLine className="h-3 w-full rounded" />
            <SkeletonLine className="h-3 w-2/3 rounded" />
          </div>
        ))}
      </div>
    </>
  );
}

export function DLQDataLoading() {
  return (
    <div className="space-y-4">
      <MetricStripSkeleton count={4} />
      <DLQTableSkeleton />
    </div>
  );
}

export function DLQRouteLoading() {
  return (
    <div className="space-y-4" data-testid="dlq-route-loading">
      <TableToolbarSkeleton tabs />
      <DLQDataLoading />
    </div>
  );
}

function RoutineTableSkeleton() {
  const cols = "md:grid-cols-[minmax(160px,180px)_minmax(220px,1fr)_118px_154px_96px_minmax(140px,170px)_144px]";
  return (
    <div className="overflow-x-auto overflow-y-hidden rounded-[var(--radius-shell)] border border-[color:var(--border-subtle)] bg-[var(--panel)] overscroll-x-contain">
      <div className="hidden min-w-[1200px] md:block" role="table">
        <div className={cn("grid items-center gap-3 border-b border-[color:var(--divider-hair)] px-4 py-2.5", cols)}>
          {Array.from({ length: 7 }).map((_, index) => (
            <div
              key={index}
              className={cn(index === 6 && "sticky-table-last sticky-table-last--header -mr-4 py-1.5 pl-4 pr-4")}
            >
              <SkeletonLine className={cn("h-3 rounded", index === 1 ? "w-24" : "w-16", index === 6 && "ml-auto")} />
            </div>
          ))}
        </div>
        <div className="flex flex-col">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className={cn("sticky-table-row grid items-center gap-3 border-b border-[color:var(--divider-hair)] px-4 py-3 last:border-b-0", cols)}>
              <div className="flex min-w-0 items-center gap-2.5">
                <SkeletonLine className="h-7 w-7 rounded-full" />
                <div className="min-w-0 flex-1 space-y-2">
                  <SkeletonLine className="h-3 w-28 rounded" />
                  <SkeletonLine className="h-2.5 w-20 rounded" />
                </div>
              </div>
              <div className="min-w-0 space-y-2">
                <SkeletonLine className="h-3.5 w-[76%] rounded" />
                <SkeletonLine className="h-3 w-[58%] rounded" />
              </div>
              <div className="min-w-0 space-y-2">
                <SkeletonLine className="h-3 w-20 rounded" />
                <SkeletonLine className="h-2.5 w-12 rounded" />
              </div>
              <div className="min-w-0 space-y-2">
                <SkeletonLine className="h-2.5 w-24 rounded" />
                <SkeletonLine className="h-2.5 w-20 rounded" />
              </div>
              <SkeletonLine className="ml-auto h-3 w-16 rounded" />
              <SkeletonLine className="h-3 w-28 rounded" />
              <div className="sticky-table-last -mr-4 flex justify-end gap-1 py-1 pl-4 pr-4">
                {Array.from({ length: 4 }).map((__, actionIndex) => (
                  <SkeletonLine key={actionIndex} className="h-7 w-7 rounded-[var(--radius-chip)]" />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-col md:hidden">
        {Array.from({ length: 4 }).map((_, index) => (
          <article key={index} className="flex flex-col gap-3 border-b border-[color:var(--divider-hair)] px-4 py-3 last:border-b-0">
            <div className="flex items-start gap-3">
              <SkeletonLine className="h-7 w-7 rounded-full" />
              <div className="min-w-0 flex-1 space-y-2">
                <SkeletonLine className="h-3.5 w-32 rounded" />
                <SkeletonLine className="h-3 w-[78%] rounded" />
                <SkeletonLine className="h-3 w-[62%] rounded" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {Array.from({ length: 3 }).map((__, statIndex) => (
                <SkeletonLine key={statIndex} className={cn("h-3 rounded", statIndex === 2 && "col-span-2")} />
              ))}
            </div>
            <div className="flex gap-1">
              {Array.from({ length: 4 }).map((__, actionIndex) => (
                <SkeletonLine key={actionIndex} className="h-7 w-7 rounded-[var(--radius-chip)]" />
              ))}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

export function RoutinesDataLoading() {
  return (
    <div className="space-y-4">
      <MetricStripSkeleton count={4} />
      <RoutineTableSkeleton />
    </div>
  );
}

export function RoutineSchedulesRouteLoading() {
  return (
    <div className="space-y-4" data-testid="routine-schedules-route-loading">
      <TableToolbarSkeleton action />
      <RoutinesDataLoading />
    </div>
  );
}

export function ExecutionsRouteLoading() {
  return (
    <div className="min-w-0 space-y-4" data-testid="executions-route-loading">
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
        <div className="w-full md:w-[220px] md:flex-none">
          <CompactAgentSwitcherSkeleton />
        </div>
        <div className="w-full md:min-w-[200px] md:flex-1">
          <SkeletonLine className="h-10 w-full rounded-[var(--radius-input)]" />
        </div>
        <div className="w-full md:w-auto md:shrink-0">
          <SoftTabsSkeleton count={5} itemWidth="w-20" />
        </div>
      </div>

      <MetricStripSkeleton count={4} />

      <div className="hidden md:block">
        <div className="max-w-full overflow-x-auto overflow-y-hidden overscroll-x-contain">
          <table className="glass-table w-full table-fixed">
            <colgroup>
              <col className="w-[102px]" />
              <col className="w-[128px]" />
              <col className="w-[360px]" />
              <col className="w-[182px]" />
              <col className="w-[88px]" />
              <col className="w-[94px]" />
              <col className="w-[148px]" />
            </colgroup>
            <thead>
              <tr>
                {Array.from({ length: 7 }).map((_, index) => (
                  <th key={index}>
                    <div className="skeleton h-3 w-16 rounded-xl" />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 6 }).map((_, index) => (
                <tr key={index}>
                  <td><div className="skeleton h-3 w-14 rounded-xl" /></td>
                  <td><div className="flex items-center gap-2"><div className="skeleton-circle h-2.5 w-2.5" /><div className="skeleton h-3 w-20 rounded-xl" /></div></td>
                  <td><div className="space-y-2"><div className="skeleton h-3 w-[78%] rounded-xl" /><div className="skeleton h-3 w-[62%] rounded-xl" /></div></td>
                  <td><div className="flex items-center gap-2"><div className="skeleton-circle h-2.5 w-2.5" /><div className="skeleton h-3 w-16 rounded-xl" /></div></td>
                  <td><div className="ml-auto skeleton h-3 w-16 rounded-xl" /></td>
                  <td><div className="ml-auto skeleton h-3 w-14 rounded-xl" /></td>
                  <td><div className="ml-auto space-y-2"><div className="ml-auto skeleton h-3 w-16 rounded-xl" /><div className="ml-auto skeleton h-3 w-24 rounded-xl" /></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="space-y-3 p-4 md:hidden">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="app-card-row space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex items-center gap-2">
                    <div className="skeleton-circle h-2.5 w-2.5" />
                    <div className="skeleton h-3 w-16 rounded-xl" />
                  </div>
                  <div className="skeleton-circle h-2.5 w-2.5" />
                </div>
                <div className="flex items-center gap-2">
                  <div className="skeleton h-3 w-12 rounded-xl" />
                  <div className="skeleton-circle h-1.5 w-1.5" />
                  <div className="skeleton h-3 w-16 rounded-xl" />
                </div>
                <div className="space-y-2">
                  <div className="skeleton h-3 w-full rounded-xl" />
                  <div className="skeleton h-3 w-[82%] rounded-xl" />
                </div>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2.5">
              {Array.from({ length: 4 }).map((_, idx) => (
                <div key={idx} className="border-b border-[var(--border-subtle)] px-0 py-2">
                  <div className="skeleton h-2.5 w-14 rounded-xl" />
                  <div className="mt-2 skeleton h-3 w-16 rounded-xl" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function SessionsRouteLoading() {
  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-[var(--canvas)]" data-testid="sessions-route-loading">
      <div className="grid h-full min-h-0 flex-1 gap-0 lg:grid-cols-[380px_minmax(0,1fr)]">
        <div className="hidden h-full min-h-0 border-r border-[var(--border-subtle)] md:flex md:flex-col">
          <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--divider-hair)] px-3">
            <SkeletonLine className="h-4 w-32 rounded" />
            <SkeletonLine className="h-8 w-8 rounded-[var(--radius-panel-sm)]" />
          </div>
          <div className="border-b border-[var(--divider-hair)] p-3">
            <SkeletonLine className="h-9 w-full rounded-[var(--radius-input)]" />
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-hidden p-2">
            {Array.from({ length: 9 }).map((_, index) => (
              <div key={index} className="rounded-[var(--radius-panel-sm)] px-3 py-2.5">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <SkeletonLine className="h-3.5 w-32 rounded" />
                  <SkeletonLine className="h-2.5 w-10 rounded" />
                </div>
                <SkeletonLine className="h-3 w-[82%] rounded" />
              </div>
            ))}
          </div>
        </div>
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--divider-hair)] px-4">
            <div className="flex items-center gap-3">
              <SkeletonLine className="h-8 w-8 rounded-[var(--radius-panel-sm)] md:hidden" />
              <SkeletonLine className="h-4 w-48 rounded" />
            </div>
            <SkeletonLine className="h-8 w-8 rounded-[var(--radius-panel-sm)]" />
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">
            <div className="mx-auto flex w-full max-w-[760px] flex-col gap-4 px-4 py-6">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className={cn("flex", index % 2 === 0 ? "justify-start" : "justify-end")}>
                  <SkeletonLine className={cn("h-20 rounded-[var(--radius-panel-sm)]", index % 2 === 0 ? "w-[78%]" : "w-[62%]")} />
                </div>
              ))}
            </div>
          </div>
          <div className="shrink-0 border-t border-[var(--divider-hair)] px-4 py-3">
            <div className="mx-auto w-full max-w-[760px]">
              <SkeletonLine className="h-24 w-full rounded-[var(--radius-panel)]" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function MemoryRouteLoading() {
  return (
    <div className="flex h-[calc(100dvh-var(--shell-topbar-height)-2rem)] flex-col gap-3" data-testid="memory-route-loading">
      <div className="flex flex-wrap items-center gap-2">
        <div className="w-full sm:w-[220px]">
          <CompactAgentSwitcherSkeleton />
        </div>
        <SoftTabsSkeleton count={2} itemWidth="w-20" />
        <div className="ml-auto hidden items-center gap-3 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)] px-3 py-1.5 md:flex">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="flex items-baseline gap-1.5">
              <SkeletonLine className="h-2.5 w-14 rounded" />
              <SkeletonLine className="h-3 w-5 rounded" />
            </div>
          ))}
        </div>
        <SkeletonLine className="h-9 w-24 rounded-[var(--radius-input)]" />
        <SkeletonLine className="h-9 w-9 rounded-[var(--radius-input)]" />
      </div>
      <div className="relative flex-1 overflow-hidden rounded-[14px] border border-[color:var(--border-subtle)] bg-[color:var(--panel-soft)]">
        <div className="absolute inset-0 opacity-70">
          {Array.from({ length: 28 }).map((_, index) => (
            <SkeletonLine
              key={index}
              className="absolute h-2 w-2 rounded-full"
              style={{
                left: `${8 + ((index * 29) % 84)}%`,
                top: `${10 + ((index * 17) % 76)}%`,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export function ControlPlaneCatalogLoading() {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 px-3 py-3 sm:px-4 md:px-6" data-testid="control-plane-catalog-loading">
      <section className="agent-board flex min-h-0 flex-col gap-3 lg:h-full lg:gap-4">
        <div className="agent-board-toolbar shrink-0">
          <div className="flex flex-col gap-3 md:flex-row md:items-center">
            <div className="w-full md:min-w-[200px] md:flex-1">
              <SkeletonLine className="h-10 w-full rounded-[var(--radius-input)]" />
            </div>
            <div className="field-shell flex h-10 items-center gap-1 self-start p-1 md:self-auto" style={{ width: "fit-content", borderRadius: "var(--radius-input)" }}>
              <SkeletonLine className="h-8 w-36 rounded-[var(--radius-panel-sm)]" />
              <SkeletonLine className="h-8 w-8 rounded-[var(--radius-panel-sm)]" />
            </div>
          </div>
        </div>

        <MetricStripSkeleton count={4} />

        <div className="agent-board-shell flex min-h-0 flex-1 flex-col overflow-visible lg:overflow-hidden">
          <div className="catalog-lane-rail flex min-h-0 flex-1 items-stretch gap-4 overflow-x-auto pb-2">
            {Array.from({ length: 3 }).map((_, laneIndex) => (
              <section
                key={laneIndex}
                className="agent-board-lane agent-board-lane--default flex h-full min-h-0 flex-shrink-0 snap-start flex-col overflow-hidden rounded-[0.5rem] border px-0 py-0"
                style={{ width: "calc((100% - 2rem) / 3)" }}
              >
                <div className="agent-board-lane__header agent-board-lane__header--plain">
                  <div className="agent-board-lane__heading">
                    <SkeletonLine className="h-4 w-28 rounded" />
                  </div>
                </div>
                <div className="flex min-h-0 flex-1 flex-col gap-2 px-2.5 py-2">
                  <div className="agent-board-list">
                    {Array.from({ length: 4 }).map((__, cardIndex) => (
                      <div key={cardIndex} className="rounded-[0.5rem] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-3">
                        <div className="mb-3 flex items-center gap-3">
                          <SkeletonLine className="h-8 w-8 rounded-full" />
                          <div className="min-w-0 flex-1 space-y-2">
                            <SkeletonLine className="h-3.5 w-28 rounded" />
                            <SkeletonLine className="h-2.5 w-20 rounded" />
                          </div>
                        </div>
                        <SkeletonLine className="h-3 w-[82%] rounded" />
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

export function ControlPlaneSystemLoading() {
  return (
    <div
      className="flex h-full min-h-0 flex-1 overflow-hidden"
      data-testid="control-plane-system-loading"
    >
      {/* Sidebar — matches real: w-[200px] with p-3 */}
      <nav className="hidden md:flex w-[200px] shrink-0 flex-col gap-1 border-r border-[var(--border-subtle)] p-3">
        {Array.from({ length: 4 }).map((_, index) => (
          <SkeletonLine key={index} className="h-9 w-full rounded-md" />
        ))}
      </nav>

      {/* Mobile tabs */}
      <div className="flex md:hidden overflow-x-auto border-b border-[var(--border-subtle)] px-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <SkeletonLine key={index} className="h-7 w-20 mx-1 my-2 rounded-md" />
        ))}
      </div>

      {/* Content area — matches real: px-6 pt-6 lg:px-10 */}
      <main className="flex flex-1 min-h-0 flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto px-6 pt-6 lg:px-10">
          <div className="space-y-6">
            {/* Section title + description */}
            <div>
              <SkeletonLine className="h-6 w-48 mb-2" />
              <SkeletonLine className="h-4 w-72" />
            </div>

            {/* Field group 1 */}
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated-soft)]">
              <div className="border-b border-[var(--border-subtle)] px-5 py-3">
                <SkeletonLine className="h-3.5 w-28" />
              </div>
              <div className="flex flex-col gap-4 p-4">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="space-y-2">
                    <SkeletonLine className="h-3 w-32" />
                    <SkeletonLine className="h-10 w-full rounded-lg" />
                  </div>
                ))}
              </div>
            </div>

            {/* Field group 2 */}
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated-soft)]">
              <div className="border-b border-[var(--border-subtle)] px-5 py-3">
                <SkeletonLine className="h-3.5 w-24" />
              </div>
              <div className="flex flex-col gap-4 p-4">
                {Array.from({ length: 2 }).map((_, index) => (
                  <div key={index} className="space-y-2">
                    <SkeletonLine className="h-3 w-36" />
                    <SkeletonLine className="h-10 w-full rounded-lg" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Save bar — matches real: sticky bottom */}
        <div className="shrink-0 flex items-center justify-end gap-3 border-t border-[var(--border-subtle)] bg-[var(--canvas)] px-6 py-3 lg:px-10">
          <SkeletonLine className="h-9 w-32 rounded-lg" />
        </div>
      </main>
    </div>
  );
}

export function AgentEditorRouteLoading() {
  return (
    <div
      className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[var(--surface-canvas)]"
      data-testid="agent-editor-route-loading"
    >
      {/* Topbar — mirrors EditorHeader: back link, sigil, breadcrumb, title, action buttons */}
      <header className="border-b border-[var(--border-subtle)] bg-[var(--surface-canvas)] px-4 py-2 lg:px-5 lg:py-2">
        <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <SkeletonLine className="h-7 w-7 rounded-lg" />
            <SkeletonLine className="h-9 w-9 rounded-full" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <SkeletonLine className="h-2.5 w-32 rounded" />
              <SkeletonLine className="h-5 w-48 rounded" />
            </div>
          </div>
          <div className="flex items-center gap-2 xl:justify-end">
            <SkeletonLine className="h-9 w-20 rounded-xl" />
            <SkeletonLine className="h-9 w-24 rounded-xl" />
          </div>
        </div>
      </header>

      <div className="grid h-full min-h-0 flex-1 overflow-hidden lg:grid-cols-[auto_minmax(0,1fr)]">
        {/* Step rail — mirrors the left FLUXO nav */}
        <aside className="h-full min-h-0 border-b border-[var(--border-subtle)] bg-[var(--surface-canvas)] lg:border-b-0 lg:border-r">
          <div className="flex h-full flex-col px-2 py-3 lg:px-2.5 lg:py-4">
            <div className="mb-2 px-1.5">
              <SkeletonLine className="h-2.5 w-12 rounded" />
            </div>
            <div className="flex flex-1 flex-col gap-1.5 pr-1">
              {Array.from({ length: 8 }).map((_, index) => (
                <div key={index} className="flex items-center gap-2.5 rounded-lg px-2 py-2">
                  <SkeletonLine className="h-7 w-7 rounded-md" />
                  <SkeletonLine className="h-3 w-24 rounded" />
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* Content area — mirrors ActiveStepRenderer padding */}
        <div className="relative flex h-full min-h-0 flex-col overflow-hidden">
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 lg:px-8 lg:py-6">
            <div className="flex max-w-[900px] flex-col gap-6">
              {/* Soft tabs placeholder */}
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <SkeletonLine className="h-9 w-56 rounded-full" />
                <SkeletonLine className="h-3 w-40 rounded" />
              </div>

              {/* Section header */}
              <div className="flex items-center gap-2.5">
                <SkeletonLine className="h-3.5 w-3.5 rounded" />
                <div className="flex-1 space-y-1.5">
                  <SkeletonLine className="h-2.5 w-24 rounded" />
                  <SkeletonLine className="h-3.5 w-64 rounded" />
                </div>
              </div>

              {/* Content body — a few input-shaped lines mirroring form controls */}
              <div className="flex flex-col gap-4">
                <div className="space-y-1.5">
                  <SkeletonLine className="h-2.5 w-20 rounded" />
                  <SkeletonLine className="h-9 w-full rounded-[var(--radius-input)]" />
                </div>
                <div className="space-y-1.5">
                  <SkeletonLine className="h-2.5 w-28 rounded" />
                  <SkeletonLine className="h-9 w-full rounded-[var(--radius-input)]" />
                </div>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  {Array.from({ length: 3 }).map((_, index) => (
                    <div key={index} className="space-y-1.5">
                      <SkeletonLine className="h-2.5 w-20 rounded" />
                      <SkeletonLine className="h-9 w-full rounded-[var(--radius-input)]" />
                    </div>
                  ))}
                </div>
                <SkeletonLine className="h-[220px] w-full rounded-[var(--radius-input)]" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function RuntimeTaskRouteLoading() {
  return (
    <div className="runtime-shell runtime-shell--wide space-y-5" data-testid="runtime-task-route-loading">
      <div className="runtime-hero">
        <div className="space-y-3">
          <SkeletonLine className="h-5 w-28" />
          <SkeletonLine className="h-12 w-full max-w-[40rem]" />
        </div>
        <div className="flex gap-3">
          <SkeletonLine className="h-10 w-28 rounded-xl" />
          <SkeletonLine className="h-10 w-28 rounded-xl" />
          <SkeletonLine className="h-10 w-28 rounded-xl" />
        </div>
      </div>
      <div className="runtime-stage min-h-[620px]" />
    </div>
  );
}
