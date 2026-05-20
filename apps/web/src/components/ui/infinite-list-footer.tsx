"use client";

import { useEffect } from "react";
import { LoaderCircle } from "lucide-react";
import { useInViewport } from "@/hooks/use-in-viewport";
import { cn } from "@/lib/utils";

type InfiniteListFooterProps = {
  hasMore: boolean;
  loading: boolean;
  onLoadMore: () => void;
  label?: string;
  className?: string;
};

export function InfiniteListFooter({
  hasMore,
  loading,
  onLoadMore,
  label = "Load more",
  className,
}: InfiniteListFooterProps) {
  const { ref, inView } = useInViewport<HTMLDivElement>({
    rootMargin: "520px 0px",
    threshold: 0,
  });

  useEffect(() => {
    if (!hasMore || loading || !inView) return;
    onLoadMore();
  }, [hasMore, inView, loading, onLoadMore]);

  if (!hasMore && !loading) {
    return <div ref={ref} className={cn("h-px", className)} aria-hidden="true" />;
  }

  return (
    <div
      ref={ref}
      className={cn("flex items-center justify-center px-4 py-4", className)}
    >
      {loading ? (
        <div
          className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[color:var(--border-subtle)] bg-[var(--panel)] text-[var(--text-tertiary)]"
          role="status"
          aria-label={label}
        >
          <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
        </div>
      ) : (
        <button
          type="button"
          onClick={onLoadMore}
          className="inline-flex h-8 items-center justify-center rounded-full border border-[color:var(--border-subtle)] bg-[var(--panel)] px-3 text-[0.75rem] font-medium text-[var(--text-secondary)] transition-colors duration-[140ms] hover:bg-[var(--panel-strong)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--accent)]"
        >
          {label}
        </button>
      )}
    </div>
  );
}
