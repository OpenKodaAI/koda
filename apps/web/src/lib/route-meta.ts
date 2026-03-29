import type { AppTranslator } from "@/lib/i18n";

export interface RouteMeta {
  eyebrow: string;
  title: string;
  summary: string;
}

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
}> = [
  {
    match: (pathname) => pathname.startsWith("/control-plane/system"),
    key: "system",
  },
  {
    match: (pathname) =>
      pathname === "/control-plane" ||
      pathname.startsWith("/control-plane/agents/") ||
      pathname.startsWith("/control-plane/bots/"),
    key: "agents",
  },
  {
    match: (pathname) => pathname.startsWith("/runtime"),
    key: "runtime",
  },
  {
    match: (pathname) => pathname === "/",
    key: "overview",
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
  },
  {
    match: (pathname) => pathname.startsWith("/costs"),
    key: "costs",
  },
  {
    match: (pathname) => pathname.startsWith("/schedules"),
    key: "schedules",
  },
  {
    match: (pathname) => pathname.startsWith("/dlq"),
    key: "dlq",
  },
];

export function getRouteMeta(pathname: string, t: AppTranslator): RouteMeta {
  const routeKey = ROUTE_META.find((entry) => entry.match(pathname))?.key ?? "fallback";

  return {
    eyebrow: t(`routeMeta.${routeKey}.eyebrow`),
    title: t(`routeMeta.${routeKey}.title`),
    summary: t(`routeMeta.${routeKey}.summary`),
  };
}
