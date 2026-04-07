"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { useLocalStorage } from "@/hooks/use-local-storage";
import { usePathname } from "next/navigation";
import { RouteStage } from "@/components/layout/route-stage";
import { Sidebar } from "@/components/layout/sidebar";
import { WorkspaceTopbar } from "@/components/layout/workspace-topbar";
import { AppTourProvider } from "@/components/providers/app-tour-provider";
import { ToastNotification } from "@/components/ui/toast-notification";
import { ToastProvider } from "@/hooks/use-toast";
import { sidebarCollapsedStorageCodec } from "@/lib/storage-codecs";
import { cn } from "@/lib/utils";

const SIDEBAR_EXPANDED_WIDTH = "16.5rem";
const SIDEBAR_COLLAPSED_WIDTH = "4.75rem";

interface AppShellProps {
  children: React.ReactNode;
}

function ShellViewportFrame({
  children,
  pathname,
  isSessionsRoute,
  isControlPlaneSetupRoute,
  isControlPlaneCatalogRoute,
  isControlPlaneAgentRoute,
}: {
  children: React.ReactNode;
  pathname: string;
  isSessionsRoute: boolean;
  isControlPlaneSetupRoute: boolean;
  isControlPlaneCatalogRoute: boolean;
  isControlPlaneAgentRoute: boolean;
}) {
  const isGeneralSettingsRoute = pathname.startsWith("/control-plane/system");
  const sessionsTopOffset = isSessionsRoute ? "0px" : "var(--shell-topbar-height)";

  return (
    <main
      id="conteudo-principal"
      className={cn(
        "workspace-main min-h-screen overflow-x-clip",
        isControlPlaneSetupRoute &&
          "!px-0 !pb-0 !pt-0 overflow-x-clip",
        isGeneralSettingsRoute &&
          "!px-0 !pb-0 !pt-[var(--shell-topbar-height)] overflow-x-clip lg:h-screen lg:overflow-hidden lg:!pl-[var(--shell-sidebar-width)]",
        isControlPlaneCatalogRoute &&
          "!px-0 !pb-0 !pt-[var(--shell-topbar-height)] overflow-x-clip lg:h-screen lg:overflow-hidden lg:!pl-[var(--shell-sidebar-width)]",
        isControlPlaneAgentRoute &&
          "!px-0 !pb-0 !pt-[var(--shell-topbar-height)] overflow-x-clip lg:h-screen lg:overflow-hidden lg:!pl-[var(--shell-sidebar-width)]",
        isSessionsRoute &&
          "!px-0 !pb-0 !pt-0 overflow-hidden lg:!pl-[var(--shell-sidebar-width)]"
      )}
    >
        <div
          className={cn(
            "flex flex-col",
            isSessionsRoute
              ? "h-[100dvh] min-h-[100dvh] overflow-hidden"
              : isControlPlaneSetupRoute
                ? "min-h-screen"
                : isControlPlaneCatalogRoute
                ? "mx-auto w-full min-h-[calc(100vh-var(--shell-topbar-height))] max-w-[1720px] lg:h-[calc(100dvh-var(--shell-topbar-height))] lg:min-h-[calc(100dvh-var(--shell-topbar-height))] lg:overflow-hidden lg:[&>.route-stage]:h-full"
                : isGeneralSettingsRoute
                ? "mx-auto w-full min-h-[calc(100vh-var(--shell-topbar-height))] max-w-[1720px] lg:h-[calc(100dvh-var(--shell-topbar-height))] lg:min-h-[calc(100dvh-var(--shell-topbar-height))] lg:overflow-hidden lg:[&>.route-stage]:h-full lg:[&>.route-stage]:overflow-hidden"
                : isControlPlaneAgentRoute
                  ? "w-full min-h-[calc(100vh-var(--shell-topbar-height))] lg:h-[calc(100dvh-var(--shell-topbar-height))] lg:min-h-[calc(100dvh-var(--shell-topbar-height))] lg:overflow-hidden lg:[&>.route-stage]:h-full"
                : "mx-auto min-h-[calc(100vh-var(--shell-topbar-height)-2rem)] max-w-[1720px]"
          )}
          style={isSessionsRoute ? ({ "--shell-topbar-height": sessionsTopOffset } as CSSProperties) : undefined}
      >
        <RouteStage>{children}</RouteStage>
      </div>
    </main>
  );
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const isSessionsRoute = pathname.startsWith("/sessions");
  const isControlPlaneSetupRoute = pathname === "/control-plane/setup";
  const isControlPlaneCatalogRoute = pathname === "/control-plane";
  const isControlPlaneAgentRoute =
    pathname.startsWith("/control-plane/agents/") || pathname.startsWith("/control-plane/bots/");
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useLocalStorage(
    "ui:sidebar-collapsed",
    false,
    sidebarCollapsedStorageCodec,
  );

  const sidebarWidth = isSidebarCollapsed
    ? SIDEBAR_COLLAPSED_WIDTH
    : SIDEBAR_EXPANDED_WIDTH;

  const shellStyle = useMemo(
    () =>
      ({
        "--shell-sidebar-width": sidebarWidth,
      }) as CSSProperties,
    [sidebarWidth]
  );

  useEffect(() => {
    document.documentElement.style.setProperty("--shell-sidebar-width", sidebarWidth);
  }, [sidebarWidth]);

  return (
    <ToastProvider>
      <AppTourProvider
        pathname={pathname}
        mobileNavOpen={isMobileNavOpen}
        onMobileNavOpenChange={setIsMobileNavOpen}
      >
        <div
          className="app-shell"
          data-sidebar-collapsed={isSidebarCollapsed ? "true" : "false"}
          style={shellStyle}
        >
          {!isControlPlaneSetupRoute ? (
            <Sidebar
              mobileOpen={isMobileNavOpen}
              onMobileOpenChange={setIsMobileNavOpen}
              collapsed={isSidebarCollapsed}
            />
          ) : null}
          {!isSessionsRoute && !isControlPlaneSetupRoute ? (
            <WorkspaceTopbar
              isSidebarCollapsed={isSidebarCollapsed}
              onToggleSidebarCollapse={() => setIsSidebarCollapsed((value) => !value)}
              onOpenMobileNav={() => setIsMobileNavOpen(true)}
            />
          ) : null}
          <ShellViewportFrame
            pathname={pathname}
            isSessionsRoute={isSessionsRoute}
            isControlPlaneSetupRoute={isControlPlaneSetupRoute}
            isControlPlaneCatalogRoute={isControlPlaneCatalogRoute}
            isControlPlaneAgentRoute={isControlPlaneAgentRoute}
          >
            {children}
          </ShellViewportFrame>
          <ToastNotification />
        </div>
      </AppTourProvider>
    </ToastProvider>
  );
}
