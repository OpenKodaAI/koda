import type { ComponentType, SVGProps } from "react";
import {
  ControlPlaneNavIcon,
  CostsNavIcon,
  DlqNavIcon,
  ExecutionsNavIcon,
  GeneralSettingsNavIcon,
  MemoryNavIcon,
  OverviewNavIcon,
  RuntimeNavIcon,
  SessionsNavIcon,
  SchedulesNavIcon,
} from "@/components/layout/sidebar-nav-icons";
import type { AppTranslator } from "@/lib/i18n";

export type SidebarNavItem = {
  href: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  kind: "primary" | "footer";
  freshnessTier: "catalog" | "detail" | "live";
  prefetchStrategy: "viewport" | "intent";
  loadingLabel: string;
  match: "exact" | "startsWith" | "memory";
};

export type SidebarNavSection = {
  label: string;
  items: SidebarNavItem[];
};

function buildItem(
  t: AppTranslator,
  href: string,
  itemKey: string,
  icon: ComponentType<SVGProps<SVGSVGElement>>,
  kind: "primary" | "footer",
  freshnessTier: "catalog" | "detail" | "live",
  prefetchStrategy: "viewport" | "intent",
  match: "exact" | "startsWith" | "memory",
): SidebarNavItem {
  return {
    href,
    label: t(`sidebar.items.${itemKey}`),
    icon,
    kind,
    freshnessTier,
    prefetchStrategy,
    loadingLabel: t(`sidebar.loading.${itemKey}`),
    match,
  };
}

export function buildSidebarPrimarySections(t: AppTranslator): SidebarNavSection[] {
  return [
    {
      label: t("sidebar.sections.atlas"),
      items: [
        buildItem(t, "/", "home", OverviewNavIcon, "primary", "live", "viewport", "exact"),
        buildItem(t, "/runtime", "runtime", RuntimeNavIcon, "primary", "live", "viewport", "startsWith"),
        buildItem(
          t,
          "/control-plane",
          "agents",
          ControlPlaneNavIcon,
          "primary",
          "catalog",
          "intent",
          "startsWith",
        ),
      ],
    },
    {
      label: t("sidebar.sections.operations"),
      items: [
        buildItem(
          t,
          "/executions",
          "executions",
          ExecutionsNavIcon,
          "primary",
          "live",
          "intent",
          "startsWith",
        ),
        buildItem(
          t,
          "/sessions",
          "sessions",
          SessionsNavIcon,
          "primary",
          "live",
          "intent",
          "startsWith",
        ),
        buildItem(
          t,
          "/schedules",
          "schedules",
          SchedulesNavIcon,
          "primary",
          "live",
          "viewport",
          "startsWith",
        ),
        buildItem(t, "/dlq", "dlq", DlqNavIcon, "primary", "live", "viewport", "startsWith"),
      ],
    },
    {
      label: t("sidebar.sections.analysis"),
      items: [
        buildItem(t, "/memory", "memory", MemoryNavIcon, "primary", "live", "intent", "memory"),
        buildItem(t, "/costs", "costs", CostsNavIcon, "primary", "live", "viewport", "startsWith"),
      ],
    },
  ];
}

export function buildSidebarFooterSections(t: AppTranslator): SidebarNavSection[] {
  return [
    {
      label: t("sidebar.sections.system"),
      items: [
        buildItem(
          t,
          "/control-plane/system",
          "generalSettings",
          GeneralSettingsNavIcon,
          "footer",
          "catalog",
          "intent",
          "startsWith",
        ),
      ],
    },
  ];
}

export function isSidebarItemActive(pathname: string, item: SidebarNavItem) {
  if (item.match === "exact") {
    return pathname === item.href;
  }

  if (item.match === "memory") {
    return pathname === "/memory";
  }

  if (item.href === "/control-plane") {
    return (
      pathname === "/control-plane" ||
      pathname.startsWith("/control-plane/agents/") ||
      pathname.startsWith("/control-plane/bots/")
    );
  }

  return pathname.startsWith(item.href);
}
