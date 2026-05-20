"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { Plus } from "lucide-react";
import {
  buildSidebarFooterSections,
  buildSidebarPrimarySections,
  isSidebarItemActive,
  type SidebarNavItem,
} from "@/components/layout/sidebar-nav";
import { KodaMark } from "@/components/layout/koda-mark";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { tourAnchor, tourRoute } from "@/components/tour/tour-attrs";
import { cn } from "@/lib/utils";

interface SidebarProps {
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
  collapsed?: boolean;
}

function isPlainLeftClick(event: MouseEvent<HTMLAnchorElement>) {
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
  visualPathname,
  pendingHref,
  collapsed,
  onNavigate,
  onPrefetch,
}: {
  item: SidebarNavItem;
  pathname: string;
  visualPathname: string;
  pendingHref: string | null;
  collapsed: boolean;
  onNavigate: (href: string) => void;
  onPrefetch: (href: string) => void;
}) {
  const isActualActive = isSidebarItemActive(pathname, item);
  const isActive = isSidebarItemActive(visualPathname, item);
  const isPending = pendingHref === item.href && !isActualActive;

  return (
    <Link
      href={item.href}
      prefetch
      scroll={false}
      {...tourAnchor(`shell.sidebar.nav.${item.href === "/" ? "home" : item.href.slice(1).replace(/\//g, ".")}`)}
      onFocus={() => onPrefetch(item.href)}
      onPointerEnter={() => onPrefetch(item.href)}
      onTouchStart={() => onPrefetch(item.href)}
      onClick={(event) => {
        if (!isPlainLeftClick(event) || isActualActive) {
          return;
        }
        onPrefetch(item.href);
        onNavigate(item.href);
      }}
      className={cn(
        "app-sidebar__link group",
        isActive && "is-active",
        isPending && "is-pending",
        collapsed &&
          "lg:h-12 lg:min-h-0 lg:w-12 lg:self-center lg:justify-center lg:gap-0 lg:rounded-lg lg:px-0",
      )}
      aria-current={isActive ? "page" : undefined}
      title={item.label}
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

function SidebarNavList({
  items,
  pathname,
  visualPathname,
  pendingHref,
  collapsed,
  onNavigate,
  onPrefetch,
}: {
  items: SidebarNavItem[];
  pathname: string;
  visualPathname: string;
  pendingHref: string | null;
  collapsed: boolean;
  onNavigate: (href: string) => void;
  onPrefetch: (href: string) => void;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-0.5",
        collapsed && "lg:items-center lg:gap-1",
      )}
    >
      {items.map((item) => (
        <SidebarNavLink
          key={item.href}
          item={item}
          pathname={pathname}
          visualPathname={visualPathname}
          pendingHref={pendingHref}
          collapsed={collapsed}
          onNavigate={onNavigate}
          onPrefetch={onPrefetch}
        />
      ))}
    </div>
  );
}

export function Sidebar({
  mobileOpen,
  onMobileOpenChange,
  collapsed = false,
}: SidebarProps) {
  const { t } = useAppI18n();
  const pathname = usePathname();
  const router = useRouter();
  const [optimisticNavigation, setOptimisticNavigation] = useState<{
    from: string;
    href: string;
  } | null>(null);
  const prefetchedHrefRef = useRef(new Set<string>());
  const primaryItems = buildSidebarPrimarySections(t).flatMap((section) => section.items);
  const footerItems = buildSidebarFooterSections(t).flatMap((section) => section.items);
  const allItems = useMemo(
    () => [...primaryItems, ...footerItems],
    [footerItems, primaryItems],
  );
  const viewportPrefetchKey = allItems
    .filter((item) => item.prefetchStrategy === "viewport")
    .map((item) => item.href)
    .join("|");
  const pendingHref = optimisticNavigation?.from === pathname ? optimisticNavigation.href : null;
  const visualPathname = pendingHref ?? pathname;

  const prefetchHref = useCallback(
    (href: string) => {
      if (prefetchedHrefRef.current.has(href)) {
        return;
      }
      prefetchedHrefRef.current.add(href);
      try {
        router.prefetch(href);
      } catch {
        prefetchedHrefRef.current.delete(href);
      }
    },
    [router],
  );

  const navigateOptimistically = useCallback(
    (href: string) => {
      setOptimisticNavigation({ from: pathname, href });
      onMobileOpenChange(false);
    },
    [onMobileOpenChange, pathname],
  );

  // Close the mobile menu on route navigation (but only when pathname actually
  // changes — not on initial mount). The previous version re-fired on every
  // mount via RAF, which combined with the tour-route-bridge effect below
  // caused the menu to "open and close instantly" on user clicks.
  const lastPathnameRef = useRef(pathname);
  useEffect(() => {
    if (lastPathnameRef.current === pathname) return;
    lastPathnameRef.current = pathname;
    onMobileOpenChange(false);
  }, [onMobileOpenChange, pathname]);

  useEffect(() => {
    if (!optimisticNavigation) return;

    const timeout = window.setTimeout(() => {
      setOptimisticNavigation(null);
    }, 8000);

    return () => window.clearTimeout(timeout);
  }, [optimisticNavigation]);

  useEffect(() => {
    const hrefs = viewportPrefetchKey.split("|").filter(Boolean);
    if (hrefs.length === 0) {
      return undefined;
    }

    const idleWindow = window as Window & {
      cancelIdleCallback?: (handle: number) => void;
      requestIdleCallback?: (
        callback: IdleRequestCallback,
        options?: IdleRequestOptions,
      ) => number;
    };
    const run = () => hrefs.forEach(prefetchHref);

    if (typeof idleWindow.requestIdleCallback === "function") {
      const handle = idleWindow.requestIdleCallback(run, { timeout: 1600 });
      return () => idleWindow.cancelIdleCallback?.(handle);
    }

    const timeout = window.setTimeout(run, 120);
    return () => window.clearTimeout(timeout);
  }, [prefetchHref, viewportPrefetchKey]);

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
          "app-overlay-backdrop transition-opacity duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:hidden",
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        style={{ zIndex: 49 }}
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
              prefetch
              scroll={false}
              {...tourAnchor("shell.sidebar.brand")}
              onFocus={() => prefetchHref("/")}
              onPointerEnter={() => prefetchHref("/")}
              onTouchStart={() => prefetchHref("/")}
              onClick={(event) => {
                if (!isPlainLeftClick(event) || pathname === "/") {
                  return;
                }
                prefetchHref("/");
                navigateOptimistically("/");
              }}
              className={cn(
                "group flex items-center gap-2 rounded-[var(--radius-panel-sm)] px-1.5 py-1 transition-colors",
                collapsed && "lg:justify-center lg:px-0"
              )}
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center">
                <KodaMark className="h-7 w-7" />
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
              prefetch
              scroll={false}
              aria-label={t("sidebar.newSessionLabel")}
              onFocus={() => prefetchHref("/runtime")}
              onPointerEnter={() => prefetchHref("/runtime")}
              onTouchStart={() => prefetchHref("/runtime")}
              onClick={(event) => {
                if (!isPlainLeftClick(event) || pathname.startsWith("/runtime")) {
                  return;
                }
                prefetchHref("/runtime");
                navigateOptimistically("/runtime");
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

          <nav className={cn("mt-5", collapsed && "lg:mt-3 lg:items-center")}>
            <SidebarNavList
              items={primaryItems}
              pathname={pathname}
              visualPathname={visualPathname}
              pendingHref={pendingHref}
              collapsed={collapsed}
              onNavigate={navigateOptimistically}
              onPrefetch={prefetchHref}
            />
          </nav>

          <div className="mt-auto pt-4">
            <nav className={cn(collapsed && "lg:items-center")}>
              <SidebarNavList
                items={footerItems}
                pathname={pathname}
                visualPathname={visualPathname}
                pendingHref={pendingHref}
                collapsed={collapsed}
                onNavigate={navigateOptimistically}
                onPrefetch={prefetchHref}
              />
            </nav>
          </div>
        </div>
      </aside>
    </>
  );
}
