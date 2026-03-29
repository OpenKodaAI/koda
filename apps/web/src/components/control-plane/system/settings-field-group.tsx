import type { ReactNode } from "react";

export function SettingsFieldGroup({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated-soft)]">
      {title && (
        <div className="border-b border-[var(--border-subtle)] px-5 py-3">
          <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            {title}
          </h3>
        </div>
      )}
      <div className="flex flex-col gap-1 p-4">{children}</div>
    </div>
  );
}
