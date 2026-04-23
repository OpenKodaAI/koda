"use client";

import Link from "next/link";
import { Clock } from "lucide-react";
import { useCallback } from "react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useRecents } from "@/hooks/use-recents";
import { getRouteMeta } from "@/lib/route-meta";
import { cn } from "@/lib/utils";

interface SidebarRecentsProps {
  collapsed: boolean;
  onNavigate?: (href: string) => void;
}

export function SidebarRecents({ collapsed, onNavigate }: SidebarRecentsProps) {
  const { t } = useAppI18n();
  const resolveLabel = useCallback(
    (path: string) => getRouteMeta(path, t).title,
    [t],
  );
  const { recents } = useRecents(resolveLabel);

  if (collapsed) return null;
  if (!recents.length) return null;

  return (
    <div className="flex flex-col gap-1">
      <div className="app-sidebar__section-label px-3 pb-1">
        {t("sidebar.recents")}
      </div>
      <ul className="flex flex-col gap-0.5">
        {recents.map((entry) => (
          <li key={entry.href}>
            <Link
              href={entry.href}
              scroll={false}
              onClick={() => onNavigate?.(entry.href)}
              className={cn("app-sidebar__link group")}
              title={entry.label}
            >
              <Clock className="app-sidebar__link-icon" aria-hidden="true" />
              <span className="max-w-[9.25rem] truncate whitespace-nowrap">
                {entry.label}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
