"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { tourAnchor } from "@/components/tour/tour-attrs";
import { cn } from "@/lib/utils";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface HeaderProps {
  title?: string;
  description?: string;
  breadcrumb?: { label: string; href?: string }[];
  meta?: ReactNode;
  children?: ReactNode;
}

export function PageHeader({
  title,
  description,
  breadcrumb,
  meta,
  children,
}: HeaderProps) {
  const { tl } = useAppI18n();
  const hasHeading = Boolean(title || description);
  const hasLeadContent = Boolean((breadcrumb && breadcrumb.length > 0) || hasHeading || meta);

  return (
    <header className="page-header" {...tourAnchor("page.header")}>
      <div className="page-header__row">
        {hasLeadContent ? (
          <div className="page-header__lead">
            {breadcrumb && breadcrumb.length > 0 ? (
              <nav
                aria-label={tl("Breadcrumb")}
                className={cn(
                  "page-header__breadcrumb",
                  hasHeading || meta ? "mb-2" : "mb-0"
                )}
              >
                {breadcrumb.map((item, index) => (
                  <span
                    key={`${item.label}-${index}`}
                    className="inline-flex min-w-0 items-center gap-2"
                  >
                    {index > 0 && (
                      <span className="text-[var(--text-quaternary)]">/</span>
                    )}
                    {item.href ? (
                      <Link
                        href={item.href}
                        className="truncate transition-colors hover:text-[var(--text-primary)]"
                      >
                        {tl(item.label)}
                      </Link>
                    ) : (
                      <span className="truncate text-[var(--text-secondary)]">
                        {tl(item.label)}
                      </span>
                    )}
                  </span>
                ))}
              </nav>
            ) : null}

            {hasHeading ? (
              <div className="page-header__copy">
                {title ? (
                  <h1 className="page-header__title">
                    {tl(title)}
                  </h1>
                ) : null}

                {description && (
                  <p className="page-header__description">
                    {tl(description)}
                  </p>
                )}
              </div>
            ) : null}

            {meta && (
              <div className={cn("page-header__meta", hasHeading ? "mt-2.5" : "")}>
                {meta}
              </div>
            )}
          </div>
        ) : null}

        {children && (
          <div className={cn("page-header__actions", !hasLeadContent && "page-header__actions--full")}>
            {children}
          </div>
        )}
      </div>
    </header>
  );
}
