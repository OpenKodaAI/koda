"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { useLocalStorage } from "@/hooks/use-local-storage";
import { usePathname } from "next/navigation";
import { CommandBarModal } from "@/components/command-bar/command-bar-modal";
import { PlaceholderSecretsBanner } from "@/components/layout/placeholder-secrets-banner";
import { RouteStage } from "@/components/layout/route-stage";
import { Sidebar } from "@/components/layout/sidebar";
import { WorkspaceTopbar } from "@/components/layout/workspace-topbar";
import { AppTourProvider } from "@/components/providers/app-tour-provider";
import { AuthProvider } from "@/components/providers/auth-provider";
import { ToastNotification } from "@/components/ui/toast-notification";
import { ActiveDownloadsRebinder } from "@/components/layout/active-downloads-rebinder";
import { ToastProvider } from "@/hooks/use-toast";
import type { ControlPlaneAuthStatus } from "@/lib/control-plane";
import { getRouteShell, type RouteShell } from "@/lib/route-meta";
import { sidebarCollapsedStorageCodec } from "@/lib/storage-codecs";
import { cn } from "@/lib/utils";

const SIDEBAR_EXPANDED_WIDTH = "15rem";
const SIDEBAR_COLLAPSED_WIDTH = "3.5rem";

interface AppShellProps {
  children: React.ReactNode;
  serverPathname?: string;
  initialAuth?: ControlPlaneAuthStatus | null;
}

function ShellViewportFrame({
  children,
  shell,
}: {
  children: React.ReactNode;
  shell: RouteShell;
}) {
  const isPage = shell.layout === "page";
  const isPane = shell.layout === "pane";
  const isFullBleed = shell.layout === "fullBleed";

  return (
    <main
      id="conteudo-principal"
      className={cn(
        "workspace-main min-h-screen overflow-x-clip",
        isPane &&
          "!px-0 !pb-0 !pt-[var(--shell-topbar-height)] lg:h-screen lg:overflow-hidden lg:!pl-[var(--shell-sidebar-width)]",
        // Below lg the topbar stays (it holds the menu trigger), so the frame
        // starts under it; from lg up the route owns the whole viewport.
        isFullBleed &&
          "!px-0 !pb-0 !pt-[var(--shell-topbar-height)] overflow-hidden lg:!pt-0 lg:!pl-[var(--shell-sidebar-width)]"
      )}
    >
      <div
        className={cn(
          "flex flex-col",
          isPage && "mx-auto min-h-[calc(100vh-var(--shell-topbar-height)-2rem)] max-w-[1720px]",
          isPane &&
            "w-full min-h-[calc(100vh-var(--shell-topbar-height))] lg:h-[calc(100dvh-var(--shell-topbar-height))] lg:min-h-[calc(100dvh-var(--shell-topbar-height))] lg:overflow-hidden lg:[&>.route-stage]:flex-1 lg:[&>.route-stage]:!min-h-0",
          isPane && !shell.fullWidth && "mx-auto max-w-[1720px]",
          isPane && shell.clipStage && "lg:[&>.route-stage]:overflow-hidden",
          isFullBleed &&
            "h-[calc(100dvh-var(--shell-topbar-height))] min-h-[calc(100dvh-var(--shell-topbar-height))] overflow-hidden lg:h-[100dvh] lg:min-h-[100dvh] [&>.route-stage]:flex-1 [&>.route-stage]:!min-h-0"
        )}
      >
        <PlaceholderSecretsBanner
          className={isPage ? "mb-4" : "rounded-none border-x-0 border-t-0"}
        />
        <RouteStage>{children}</RouteStage>
      </div>
    </main>
  );
}

const FULL_SCREEN_AUTH_ROUTES: ReadonlyArray<string> = ["/setup", "/login", "/forgot-password"];

function isFullScreenAuthRoute(pathname: string): boolean {
  return FULL_SCREEN_AUTH_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}

export function AppShell({ children, serverPathname, initialAuth = null }: AppShellProps) {
  const clientPathname = usePathname();
  // During SSR, usePathname() returns null. Fall back to the server-provided
  // pathname (read from the request headers in layout.tsx) so the shell
  // doesn't flash around /setup, /login, or /forgot-password.
  const pathname = clientPathname || serverPathname || "";
  const isAuthRoute = isFullScreenAuthRoute(pathname);
  const shell = getRouteShell(pathname);
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

  // Full-screen bypass: the auth flows (setup, login, forgot-password) own the
  // viewport — no sidebar, no topbar, no shell frame.
  if (isAuthRoute) {
    return <>{children}</>;
  }

  return (
    <ToastProvider>
      <AuthProvider initialAuth={initialAuth}>
        <AppTourProvider
          pathname={pathname}
          onMobileNavOpenChange={setIsMobileNavOpen}
        >
          <div
            className="app-shell"
            data-sidebar-collapsed={isSidebarCollapsed ? "true" : "false"}
            style={shellStyle}
          >
            <Sidebar
              mobileOpen={isMobileNavOpen}
              onMobileOpenChange={setIsMobileNavOpen}
              collapsed={isSidebarCollapsed}
            />
            <WorkspaceTopbar
              className={shell.layout === "fullBleed" ? "lg:hidden" : undefined}
              isSidebarCollapsed={isSidebarCollapsed}
              onToggleSidebarCollapse={() => setIsSidebarCollapsed((value) => !value)}
              onOpenMobileNav={() => setIsMobileNavOpen(true)}
            />
            <ShellViewportFrame shell={shell}>{children}</ShellViewportFrame>
            <ToastNotification />
            <ActiveDownloadsRebinder />
            <CommandBarModal />
          </div>
        </AppTourProvider>
      </AuthProvider>
    </ToastProvider>
  );
}
