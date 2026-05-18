import {
  AccountRouteLoading,
  AgentEditorRouteLoading,
  AuthRouteLoading,
  ControlPlaneCatalogLoading,
  ControlPlaneSystemLoading,
  CostRouteLoading,
  DLQRouteLoading,
  ExecutionsRouteLoading,
  MemoryRouteLoading,
  OverviewRouteLoading,
  RoutineSchedulesRouteLoading,
  RuntimeRouteLoading,
  RuntimeTaskRouteLoading,
  SessionsRouteLoading,
} from "@/components/layout/route-loading";

function normalizePathname(pathname: string | null | undefined): string {
  if (!pathname) return "/";
  const [path] = pathname.split("?");
  if (!path || path === "") return "/";
  return path.startsWith("/") ? path : `/${path}`;
}

export function RootRouteLoadingForPathname({
  pathname,
}: {
  pathname?: string | null;
}) {
  const path = normalizePathname(pathname);

  if (
    path === "/login" ||
    path.startsWith("/login/") ||
    path === "/setup" ||
    path.startsWith("/setup/") ||
    path === "/forgot-password" ||
    path.startsWith("/forgot-password/") ||
    path === "/oauth" ||
    path.startsWith("/oauth/")
  ) {
    return <AuthRouteLoading />;
  }

  if (path === "/settings/account" || path.startsWith("/settings/account/")) {
    return <AccountRouteLoading />;
  }

  if (path.startsWith("/runtime/") && path.includes("/tasks/")) {
    return <RuntimeTaskRouteLoading />;
  }
  if (path === "/runtime" || path.startsWith("/runtime/")) {
    return <RuntimeRouteLoading />;
  }

  if (path === "/executions/dlq" || path.startsWith("/executions/dlq/")) {
    return <DLQRouteLoading />;
  }
  if (
    path === "/executions" ||
    path.startsWith("/executions/") ||
    path === "/tasks" ||
    path.startsWith("/tasks/")
  ) {
    return <ExecutionsRouteLoading />;
  }

  if (path === "/routines" || path.startsWith("/routines/")) {
    return <RoutineSchedulesRouteLoading />;
  }

  if (path === "/costs" || path.startsWith("/costs/")) {
    return <CostRouteLoading />;
  }

  if (path === "/memory" || path.startsWith("/memory/")) {
    return <MemoryRouteLoading />;
  }

  if (path === "/sessions" || path.startsWith("/sessions/")) {
    return <SessionsRouteLoading />;
  }

  if (path === "/control-plane/system" || path.startsWith("/control-plane/system/")) {
    return <ControlPlaneSystemLoading />;
  }
  if (path.startsWith("/control-plane/agents/")) {
    return <AgentEditorRouteLoading />;
  }
  if (path === "/control-plane" || path.startsWith("/control-plane/")) {
    return <ControlPlaneCatalogLoading />;
  }

  return <OverviewRouteLoading />;
}
