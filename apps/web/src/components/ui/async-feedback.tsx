"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, CheckCircle2, LoaderCircle, RotateCw } from "lucide-react";
import { ActionButton } from "@/components/ui/action-button";
import { PageEmptyState } from "@/components/ui/page-primitives";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useDelayedFlag } from "@/hooks/use-delayed-flag";
import type { AsyncActionState, LoadingVariant } from "@/lib/async-ui";
import { cn } from "@/lib/utils";

export function InlineSpinner({
  className,
}: {
  className?: string;
}) {
  return <LoaderCircle className={cn("async-spinner", className)} aria-hidden="true" />;
}

export function LoadingDots({
  label,
  className,
}: {
  label?: string;
  className?: string;
}) {
  const { t } = useAppI18n();

  return (
    <span className={cn("loading-dots", className)} role="status" aria-live="polite">
      <span>{label ?? t("async.loading")}</span>
      <span className="loading-dots__track" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
    </span>
  );
}

type AsyncActionButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "children"
> & {
  children: ReactNode;
  loading?: boolean;
  status?: AsyncActionState;
  loadingLabel?: string;
  variant?: "primary" | "secondary" | "quiet" | "danger";
  size?: "sm" | "md";
  icon?: LucideIcon;
  trailing?: boolean;
};

export function AsyncActionButton({
  children,
  loading = false,
  status = "idle",
  loadingLabel,
  variant = "primary",
  size = "md",
  icon: Icon,
  trailing = false,
  className,
  disabled,
  ...props
}: AsyncActionButtonProps) {
  const showLoading = useDelayedFlag(loading);
  const renderStatusIcon =
    showLoading ? (
      <InlineSpinner className="h-4 w-4" />
    ) : status === "success" ? (
      <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
    ) : status === "error" ? (
      <AlertTriangle className="h-4 w-4" aria-hidden="true" />
    ) : Icon ? (
      <Icon className="h-4 w-4" aria-hidden="true" />
    ) : null;

  return (
    <ActionButton
      {...props}
      disabled={disabled || loading}
      variant={variant}
      size={size}
      loading={loading}
      status={status}
      leading={!trailing ? renderStatusIcon : undefined}
      trailing={trailing ? renderStatusIcon : undefined}
      className={className}
    >
      {showLoading && loadingLabel ? loadingLabel : children}
    </ActionButton>
  );
}

export function BackgroundRefreshIndicator({
  refreshing,
  label,
  lastUpdated,
  className,
}: {
  refreshing: boolean;
  label?: string;
  lastUpdated?: number | null;
  className?: string;
}) {
  const { t } = useAppI18n();
  const showLoading = useDelayedFlag(refreshing, 180);

  return (
    <div
      className={cn("background-refresh-indicator", className)}
      role="status"
      aria-live="polite"
      data-refreshing={showLoading ? "true" : "false"}
    >
      {showLoading ? (
        <RotateCw className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
      ) : (
        <span className="background-refresh-indicator__dot" aria-hidden="true" />
      )}
      <span>
        {showLoading
          ? (label ?? t("async.updating"))
          : lastUpdated
            ? t("async.synced")
            : t("async.ready")}
      </span>
    </div>
  );
}

export function SectionSkeleton({
  variant = "section",
  rows = 3,
  className,
}: {
  variant?: LoadingVariant;
  rows?: number;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "glass-card-sm space-y-3 p-4",
        variant === "panel" && "min-h-[280px]",
        variant === "form" && "space-y-4",
        className,
      )}
      aria-hidden="true"
    >
      <div className="skeleton h-4 w-32 rounded-xl" />
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="space-y-2">
          <div className="skeleton h-3 w-24 rounded-xl" />
          <div className="skeleton h-11 w-full rounded-2xl" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({
  title,
  description,
  onRetry,
}: {
  title: string;
  description: string;
  onRetry?: () => void;
}) {
  const { t } = useAppI18n();

  return (
    <PageEmptyState
      icon={AlertTriangle}
      title={title}
      description={description}
      actions={
        onRetry ? (
          <AsyncActionButton
            type="button"
            variant="secondary"
            size="sm"
            onClick={onRetry}
            icon={RotateCw}
          >
            {t("async.retry")}
          </AsyncActionButton>
        ) : null
      }
    />
  );
}
