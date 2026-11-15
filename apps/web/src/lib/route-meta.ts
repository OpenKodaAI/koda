import type { AppTranslator } from "@/lib/i18n";

export interface RouteMeta {
  eyebrow: string;
  title: string;
  summary: string;
}

/**
 * How the app shell frames a route.
 * - `page`: the default scrolling page in the 1720px column.
 * - `pane`: from `lg` up the route fills the viewport below the topbar and
 *   scrolls inside its own panes.
 * - `fullBleed`: the route owns the whole viewport height. From `lg` up the
 *   topbar is hidden; below `lg` it stays, since it holds the menu trigger.
 */
export interface RouteShell {
  layout: "page" | "pane" | "fullBleed";
  /** Pane routes that span the full width instead of the 1720px column. */
  fullWidth?: boolean;
  /** Pane routes whose route stage clips its own overflow. */
  clipStage?: boolean;
}

const DEFAULT_ROUTE_SHELL: RouteShell = { layout: "page" };

const ROUTE_META: Array<{
  match: (pathname: string) => boolean;
  key:
    | "system"
    | "agents"
    | "runtime"
    | "overview"
    | "executions"
    | "memory"
    | "sessions"
    | "costs"
    | "schedules"
    | "dlq";
  shell?: RouteShell;
}> = [
  {
    match: (pathname) => pathname.startsWith("/control-plane/system"),
    key: "system",
    shell: { layout: "pane", clipStage: true },
  },
  {
    match: (pathname) => pathname === "/control-plane",
    key: "agents",
    shell: { layout: "pane" },
  },
  {
    match: (pathname) => pathname.startsWith("/control-plane/agents/"),
    key: "agents",
    shell: { layout: "pane", fullWidth: true },
  },
  {
    match: (pathname) => pathname.startsWith("/runtime"),
    key: "runtime",
  },
  {
    match: (pathname) => pathname === "/",
    key: "overview",
  },
  // DLQ is checked before the generic /executions match because it lives
  // under /executions/dlq.
  {
    match: (pathname) => pathname.startsWith("/executions/dlq"),
    key: "dlq",
  },
  {
    match: (pathname) => pathname.startsWith("/executions"),
    key: "executions",
  },
  {
    match: (pathname) => pathname.startsWith("/memory"),
    key: "memory",
  },
  {
    match: (pathname) => pathname.startsWith("/sessions"),
    key: "sessions",
    shell: { layout: "fullBleed" },
  },
  {
    match: (pathname) => pathname.startsWith("/costs"),
    key: "costs",
  },
  {
    match: (pathname) => pathname.startsWith("/routines"),
    key: "schedules",
  },
];

function findRoute(pathname: string) {
  return ROUTE_META.find((entry) => entry.match(pathname));
}

export function getRouteMeta(pathname: string, t: AppTranslator): RouteMeta {
  const routeKey = findRoute(pathname)?.key ?? "fallback";

  return {
    eyebrow: t(`routeMeta.${routeKey}.eyebrow`),
    title: t(`routeMeta.${routeKey}.title`),
    summary: t(`routeMeta.${routeKey}.summary`),
  };
}

export function getRouteShell(pathname: string): RouteShell {
  return findRoute(pathname)?.shell ?? DEFAULT_ROUTE_SHELL;
}
