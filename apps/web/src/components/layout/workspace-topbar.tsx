"use client";

import { useMemo } from "react";
import { Menu } from "lucide-react";
import { usePathname } from "next/navigation";
import { LanguageSwitcher } from "@/components/layout/language-switcher";
import { WorkspaceTopbarActions } from "@/components/layout/workspace-topbar-actions";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getRouteMeta } from "@/lib/route-meta";

interface WorkspaceTopbarProps {
  onOpenMobileNav?: () => void;
  isSidebarCollapsed?: boolean;
  onToggleSidebarCollapse?: () => void;
}

export function WorkspaceTopbar({
  onOpenMobileNav,
  isSidebarCollapsed = false,
  onToggleSidebarCollapse,
}: WorkspaceTopbarProps) {
  const pathname = usePathname();
  const { t } = useAppI18n();
  const routeMeta = useMemo(() => getRouteMeta(pathname, t), [pathname, t]);

  return (
    <header className="workspace-topbar" {...tourRoute("shell.topbar")}>
      <div className="workspace-topbar__inner">
        <div className="flex min-w-0 items-center gap-3 sm:gap-4">
          <button
            type="button"
            onClick={onOpenMobileNav}
            className="button-shell button-shell--secondary button-shell--icon h-10 w-10 text-[var(--text-secondary)] lg:!hidden"
            aria-label={t("topbar.openMenu")}
            {...tourAnchor("shell.topbar.menu-toggle")}
          >
            <Menu className="h-4 w-4" />
          </button>

          <div className="hidden lg:block">
            <button
              type="button"
              onClick={onToggleSidebarCollapse}
              className="workspace-topbar__sidebar-toggle"
              aria-label={
                isSidebarCollapsed
                  ? t("topbar.expandSidebar")
                  : t("topbar.collapseSidebar")
              }
              aria-pressed={isSidebarCollapsed}
              {...tourAnchor("shell.topbar.sidebar-toggle")}
            >
              <svg
                viewBox="0 0 20 20"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className="h-[18px] w-[18px]"
                aria-hidden="true"
              >
                <rect
                  x="10.5"
                  y="6.5"
                  width="7"
                  height="5"
                  rx="1"
                  transform="rotate(90 10.5 6.5)"
                  fill="currentColor"
                  opacity={isSidebarCollapsed ? 0.42 : 0.9}
                />
                <rect
                  x="3"
                  y="4"
                  width="14"
                  height="12"
                  rx="2.8"
                  stroke="currentColor"
                  strokeWidth="1.5"
                />
              </svg>
            </button>
          </div>

          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
              <h1 className="truncate text-[1rem] font-semibold tracking-[-0.05em] text-[var(--text-primary)] sm:text-[1.08rem]">
                {routeMeta.title}
              </h1>
              <span className="hidden h-1 w-1 rounded-full bg-[var(--text-quaternary)] lg:block" />
              <p className="hidden truncate text-[12.5px] text-[var(--text-tertiary)] lg:block">
                {routeMeta.summary}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <LanguageSwitcher className="shrink-0" />
          <div className="hidden lg:flex">
            <WorkspaceTopbarActions key={pathname} />
          </div>
        </div>
      </div>
    </header>
  );
}
