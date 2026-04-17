"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
import {
  buildSidebarFooterSections,
  buildSidebarPrimarySections,
  isSidebarItemActive,
  type SidebarNavItem,
  type SidebarNavSection,
} from "@/components/layout/sidebar-nav";
import { KodaMark } from "@/components/layout/koda-mark";
import { SidebarRecents } from "@/components/layout/sidebar-recents";
import { useAppTour } from "@/hooks/use-app-tour";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { usePrefetchRouteData } from "@/hooks/use-prefetch-route-data";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { cn } from "@/lib/utils";

interface SidebarProps {
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
  collapsed?: boolean;
}

function isPlainLeftClick(event: React.MouseEvent<HTMLAnchorElement>) {
  return (
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  );
}

function SidebarNavLink({
  item,
  pathname,
  pendingHref,
  collapsed,
  onNavigate,
  onIntentPrefetch,
}: {
  item: SidebarNavItem;
  pathname: string;
  pendingHref: string | null;
  collapsed: boolean;
  onNavigate: (href: string) => void;
  onIntentPrefetch: (item: SidebarNavItem) => void;
}) {
  const isActive = isSidebarItemActive(pathname, item);
  const isPending = pendingHref === item.href && !isActive;

  return (
    <Link
      href={item.href}
      prefetch={item.prefetchStrategy === "viewport"}
      scroll={false}
      {...tourAnchor(`shell.sidebar.nav.${item.href === "/" ? "home" : item.href.slice(1).replace(/\//g, ".")}`)}
      onClick={(event) => {
        if (!isPlainLeftClick(event) || isActive) {
          return;
        }
        onNavigate(item.href);
      }}
      onMouseEnter={() => onIntentPrefetch(item)}
      onFocus={() => onIntentPrefetch(item)}
      className={cn(
        "app-sidebar__link group",
        isActive && "is-active",
        isPending && "is-pending",
        collapsed &&
          "lg:h-12 lg:min-h-0 lg:w-12 lg:self-center lg:justify-center lg:gap-0 lg:rounded-lg lg:px-0",
      )}
      aria-current={isActive ? "page" : undefined}
      aria-busy={isPending || undefined}
      data-pending={isPending ? "true" : undefined}
      title={isPending ? item.loadingLabel : item.label}
    >
      <item.icon className="app-sidebar__link-icon" />
      <span
        className={cn(
          "max-w-[9.25rem] truncate whitespace-nowrap transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
          collapsed && "lg:hidden",
        )}
      >
        {item.label}
      </span>
    </Link>
  );
}

function SidebarNavSectionGroup({
  section,
  pathname,
  pendingHref,
  collapsed,
  onNavigate,
  onIntentPrefetch,
}: {
  section: SidebarNavSection;
  pathname: string;
  pendingHref: string | null;
  collapsed: boolean;
  onNavigate: (href: string) => void;
  onIntentPrefetch: (item: SidebarNavItem) => void;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1",
        collapsed && "lg:items-center lg:gap-1.5",
      )}
    >
      {!collapsed ? (
        <div className="app-sidebar__section-label px-3 pb-1">
          {section.label}
        </div>
      ) : null}

      <div className={cn("flex flex-col gap-0.5", collapsed && "lg:items-center lg:gap-1")}>
        {section.items.map((item) => (
          <SidebarNavLink
            key={item.href}
            item={item}
            pathname={pathname}
            pendingHref={pendingHref}
            collapsed={collapsed}
            onNavigate={onNavigate}
            onIntentPrefetch={onIntentPrefetch}
          />
        ))}
      </div>
    </div>
  );
}

export function Sidebar({
  mobileOpen,
  onMobileOpenChange,
  collapsed = false,
}: SidebarProps) {
  const { t } = useAppI18n();
  const { currentStep, status } = useAppTour();
  const pathname = usePathname();
  const router = useRouter();
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const prefetchRouteData = usePrefetchRouteData();
  const primarySections = buildSidebarPrimarySections(t);
  const footerSections = buildSidebarFooterSections(t);

  const intentTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleIntentPrefetch = useCallback(
    (item: SidebarNavItem) => {
      if (item.prefetchStrategy !== "intent") {
        return;
      }

      if (intentTimerRef.current) {
        clearTimeout(intentTimerRef.current);
      }

      intentTimerRef.current = setTimeout(() => {
        router.prefetch(item.href);
        prefetchRouteData(item.href);
      }, 150);
    },
    [prefetchRouteData, router],
  );

  useEffect(() => {
    return () => {
      if (intentTimerRef.current) clearTimeout(intentTimerRef.current);
    };
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => onMobileOpenChange(false));
    return () => window.cancelAnimationFrame(frame);
  }, [onMobileOpenChange, pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    if (typeof window === "undefined") return;
    if (window.innerWidth >= 1024) return;
    if (status !== "running") return;
    if (currentStep?.anchor?.startsWith("shell.sidebar")) return;

    const frame = window.requestAnimationFrame(() => onMobileOpenChange(false));
    return () => window.cancelAnimationFrame(frame);
  }, [currentStep?.anchor, mobileOpen, onMobileOpenChange, status]);

  useEffect(() => {
    if (!mobileOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onMobileOpenChange(false);
      }
    };

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [mobileOpen, onMobileOpenChange]);

  return (
    <>
      <div
        className={cn(
          "app-overlay-backdrop bg-[var(--overlay-backdrop)] backdrop-blur-sm transition-opacity duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:hidden",
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        style={{ zIndex: 40 }}
        onClick={() => onMobileOpenChange(false)}
        aria-hidden="true"
      />

      <aside
        className={cn(
          "glass-sidebar fixed inset-y-0 left-0 z-50 flex w-[min(18.75rem,calc(100vw-0.75rem))] max-w-[calc(100vw-0.75rem)] flex-col overflow-hidden transition-[width,transform] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] will-change-transform lg:w-[var(--shell-sidebar-width)] lg:max-w-none lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          collapsed && "lg:w-[3.5rem]"
        )}
        aria-label={t("sidebar.ariaLabel")}
        {...tourRoute("shell.sidebar")}
      >
        <div
          className={cn(
            "flex h-full flex-col px-3 pb-4 pt-4 transition-[padding] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
            collapsed && "lg:px-1.5"
          )}
        >
          <div className="px-1">
            <Link
              href="/"
              aria-label="Koda"
              {...tourAnchor("shell.sidebar.brand")}
              className={cn(
                "group flex items-center gap-2 rounded-[var(--radius-panel-sm)] px-1.5 py-1 transition-colors",
                collapsed && "lg:justify-center lg:px-0"
              )}
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center">
                <KodaMark className="h-8 w-8" />
              </span>
              <span className={cn("min-w-0", collapsed && "lg:hidden")}>
                <span className="block max-w-[9.75rem] whitespace-nowrap text-[1.125rem] font-medium tracking-[-0.04em] text-[var(--text-primary)] transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]">
                  Koda
                </span>
              </span>
            </Link>
          </div>

          <div className={cn("mt-4", collapsed && "lg:mt-3 lg:flex lg:justify-center")}>
            <Link
              href="/runtime"
              aria-label={t("sidebar.newSessionLabel")}
              onClick={() => {
                setPendingHref("/runtime");
                onMobileOpenChange(false);
              }}
              className={cn(
                "inline-flex min-h-[34px] items-center justify-center gap-2 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel)] px-3 text-[13px] font-medium text-[var(--text-primary)] transition-[background-color,border-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--border-strong)] hover:bg-[var(--panel-strong)]",
                "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--sidebar-surface)]",
                collapsed ? "lg:h-9 lg:w-9 lg:px-0" : "w-full",
              )}
              {...tourAnchor("shell.sidebar.new-session")}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              <span className={cn(collapsed && "lg:hidden")}>{t("sidebar.newSession")}</span>
            </Link>
          </div>

          <nav className={cn("mt-5 flex flex-col gap-3", collapsed && "lg:mt-3 lg:items-center lg:gap-3")}>
            {primarySections.map((section) => (
              <SidebarNavSectionGroup
                key={section.label}
                section={section}
                pathname={pathname}
                pendingHref={pendingHref}
                collapsed={collapsed}
                onNavigate={(href) => {
                  setPendingHref(href);
                  onMobileOpenChange(false);
                }}
                onIntentPrefetch={handleIntentPrefetch}
              />
            ))}
          </nav>

          <div className={cn("mt-4", collapsed && "lg:hidden")}>
            <SidebarRecents
              collapsed={collapsed}
              onNavigate={(href) => {
                setPendingHref(href);
                onMobileOpenChange(false);
              }}
            />
          </div>

          <div
            className={cn(
              "mt-auto pt-4",
            )}
          >
            <nav className={cn("flex flex-col gap-3", collapsed && "lg:items-center lg:gap-2")}>
              {footerSections.map((section) => (
                <SidebarNavSectionGroup
                  key={section.label}
                  section={section}
                  pathname={pathname}
                  pendingHref={pendingHref}
                  collapsed={collapsed}
                  onNavigate={(href) => {
                    setPendingHref(href);
                    onMobileOpenChange(false);
                  }}
                  onIntentPrefetch={handleIntentPrefetch}
                />
              ))}
            </nav>
          </div>
        </div>
      </aside>
    </>
  );
}
