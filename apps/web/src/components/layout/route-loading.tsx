import { cn } from "@/lib/utils";

function SkeletonLine({
  className,
}: {
  className?: string;
}) {
  return <div className={cn("skeleton rounded-xl", className)} aria-hidden="true" />;
}

export function OverviewRouteLoading() {
  return (
    <div className="space-y-4" data-testid="overview-route-loading">
      <div className="app-toolbar-card">
        <SkeletonLine className="h-9 w-full max-w-[22rem] rounded-[var(--radius-input)]" />
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="glass-card-sm p-5">
            <SkeletonLine className="mb-3 h-3 w-20 rounded" />
            <SkeletonLine className="mb-4 h-7 w-28 rounded" />
            <SkeletonLine className="h-3 w-32 rounded" />
          </div>
        ))}
      </div>
      <div className="glass-card p-6">
        <div className="mb-5 flex items-center justify-between">
          <div className="space-y-1.5">
            <SkeletonLine className="h-3 w-32 rounded" />
            <SkeletonLine className="h-5 w-56 rounded" />
          </div>
          <SkeletonLine className="h-9 w-32 rounded-[var(--radius-input)]" />
        </div>
        <div className="space-y-2.5">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="flex items-center gap-3">
              <SkeletonLine className="h-2.5 w-2.5 rounded-full" />
              <SkeletonLine className="h-3 w-[72%] rounded" />
              <SkeletonLine className="ml-auto h-3 w-12 rounded" />
            </div>
          ))}
        </div>
      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(340px,0.85fr)]">
        <div className="glass-card p-6">
          <SkeletonLine className="mb-4 h-3 w-28 rounded" />
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, index) => (
              <div key={index} className="flex items-center gap-3">
                <SkeletonLine className="h-8 w-8 rounded-full" />
                <div className="flex-1 space-y-1.5">
                  <SkeletonLine className="h-3 w-[68%] rounded" />
                  <SkeletonLine className="h-2.5 w-[45%] rounded" />
                </div>
                <SkeletonLine className="h-3 w-14 rounded" />
              </div>
            ))}
          </div>
        </div>
        <div className="glass-card p-6">
          <SkeletonLine className="mb-4 h-3 w-24 rounded" />
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="flex items-center gap-3">
                <SkeletonLine className="h-2.5 w-2.5 rounded-full" />
                <SkeletonLine className="h-3 flex-1 rounded" />
                <SkeletonLine className="h-3 w-10 rounded" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function RuntimeRouteLoading() {
  return (
    <div className="runtime-shell runtime-shell--wide space-y-5" data-testid="runtime-route-loading">
      <div className="runtime-toolbar runtime-toolbar--standard">
        <div className="runtime-toolbar__controls">
          <SkeletonLine className="h-11 w-full rounded-xl" />
          <div className="app-search">
            <SkeletonLine className="h-4 w-4 rounded-full" />
            <SkeletonLine className="h-4 w-52" />
          </div>
          <div className="runtime-filter-row">
            {Array.from({ length: 4 }).map((_, index) => (
              <SkeletonLine key={index} className="h-9 w-24 rounded-full" />
            ))}
          </div>
          <SkeletonLine className="h-7 w-20 rounded-full justify-self-start lg:justify-self-end" />
        </div>
      </div>
      <div className="metric-strip">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="metric-strip__item">
            <SkeletonLine className="h-3 w-20 mb-2" />
            <SkeletonLine className="h-6 w-16" />
          </div>
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_300px]">
        <div className="runtime-panel runtime-panel--dense min-h-[420px] p-0">
          <div className="runtime-panel__header">
            <SkeletonLine className="h-4 w-32" />
          </div>
          <div className="runtime-live-list">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="runtime-live-row">
                <div className="runtime-live-row__main">
                  <SkeletonLine className="h-2.5 w-2.5 rounded-full" />
                  <SkeletonLine className="h-3 w-20" />
                  <SkeletonLine className="h-3 w-12" />
                  <SkeletonLine className="h-6 w-20 rounded-full" />
                  <SkeletonLine className="h-3 w-[38%]" />
                </div>
                <div className="runtime-live-row__side">
                  <SkeletonLine className="h-3 w-12" />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="runtime-panel runtime-panel--dense min-h-[420px] p-0">
          <div className="runtime-panel__header">
            <SkeletonLine className="h-4 w-16" />
          </div>
          <div className="runtime-agent-rail">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="runtime-agent-row">
                <div className="runtime-agent-row__identity">
                  <SkeletonLine className="h-2.5 w-2.5 rounded-full" />
                  <SkeletonLine className="h-3 w-24" />
                </div>
                <div className="flex items-center gap-3">
                  <SkeletonLine className="h-3 w-14" />
                  <SkeletonLine className="h-3 w-12" />
                </div>
              </div>
            ))}
          </div>
        </div>
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

export function ExecutionsRouteLoading() {
  return (
    <div className="min-w-0 space-y-4" data-testid="executions-route-loading">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="max-w-[350px] min-w-[200px]">
          <div className="skeleton h-11 w-full rounded-xl" />
        </div>
        <div className="skeleton h-10 w-full rounded-lg xl:w-[280px] xl:flex-none" />
        <div className="app-filter-row w-full">
          <div className="skeleton h-7 w-16 rounded-full" />
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-9 w-24 rounded-full" />
          ))}
        </div>
      </div>

      <div className="metric-strip">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="metric-strip__item">
            <div className="skeleton h-3 w-16 mb-2 rounded-xl" />
            <div className="skeleton h-6 w-20 rounded-xl" />
          </div>
        ))}
      </div>

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
    <div className="h-full overflow-hidden" data-testid="sessions-route-loading">
      <div className="grid h-full min-h-0 gap-0 lg:grid-cols-[380px_minmax(0,1fr)]">
        <div className="border-r border-[var(--border-subtle)] p-4">
          <SkeletonLine className="mb-4 h-11 w-full" />
          <SkeletonLine className="mb-4 h-11 w-full" />
          <div className="space-y-3">
            {Array.from({ length: 7 }).map((_, index) => (
              <SkeletonLine key={index} className="h-[76px] w-full rounded-2xl" />
            ))}
          </div>
        </div>
        <div className="p-6">
          <SkeletonLine className="mb-4 h-8 w-48" />
          <SkeletonLine className="mb-6 h-4 w-64" />
          <div className="space-y-4">
            {Array.from({ length: 6 }).map((_, index) => (
              <SkeletonLine key={index} className="h-20 w-full rounded-2xl" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function MemoryRouteLoading() {
  return (
    <div className="space-y-4" data-testid="memory-route-loading">
      {/* Controls bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="max-w-[350px] min-w-[200px]">
          <div className="skeleton h-9 w-full rounded-[var(--radius-input)]" />
        </div>
        <div className="flex items-center gap-2">
          <div className="skeleton h-9 w-24 rounded-[var(--radius-input)]" />
          <div className="skeleton h-9 w-24 rounded-[var(--radius-input)]" />
        </div>
      </div>

      {/* Filter section */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="skeleton h-9 w-24 rounded-full" />
          ))}
        </div>
      </div>

      {/* Main content — list of memory cards */}
      <div className="glass-card p-5 sm:p-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="skeleton h-3 w-40 rounded" />
          <div className="skeleton h-3 w-20 rounded" />
        </div>
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              key={index}
              className="flex items-start gap-3 border-t border-[color:var(--divider-hair)] pt-3 first:border-0 first:pt-0"
            >
              <div className="skeleton-circle h-2 w-2 mt-2" />
              <div className="flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="skeleton h-3 w-24 rounded" />
                  <div className="skeleton h-3 w-16 rounded-full" />
                  <div className="skeleton h-3 w-10 rounded" />
                </div>
                <div className="skeleton h-3 w-[85%] rounded" />
                <div className="skeleton h-3 w-[62%] rounded" />
              </div>
              <div className="skeleton h-3 w-10 rounded" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ControlPlaneCatalogLoading() {
  return (
    <div className="grid h-full min-h-0 gap-6 p-5 sm:p-6 xl:grid-cols-[340px_minmax(0,1fr)]" data-testid="control-plane-catalog-loading">
      <div className="space-y-4">
        <SkeletonLine className="h-12 w-full rounded-2xl" />
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, index) => (
            <SkeletonLine key={index} className="h-[96px] w-full rounded-2xl" />
          ))}
        </div>
      </div>
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          <SkeletonLine className="h-10 w-10 rounded-2xl" />
          <div className="space-y-2">
            <SkeletonLine className="h-6 w-48" />
            <SkeletonLine className="h-5 w-24 rounded-full" />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <SkeletonLine key={index} className="h-10 w-24 rounded-full" />
          ))}
        </div>
        <div className="glass-card min-h-[520px] p-6" />
      </div>
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
