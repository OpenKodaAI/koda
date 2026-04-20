import type { ReactNode } from "react";

export function SettingsFieldGroup({
  title,
  children,
}: {
  title: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4 border-b border-[var(--divider-hair)] py-6 first:pt-0 last:border-b-0">
      {title ? (
        <header className="flex min-w-0 flex-col gap-1">
          <h3 className="m-0 text-[0.9375rem] font-medium tracking-[-0.01em] text-[var(--text-primary)]">
            {title}
          </h3>
        </header>
      ) : null}
      <div className="flex flex-col gap-3">{children}</div>
    </section>
  );
}
