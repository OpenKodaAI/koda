"use client";

import { type ReactNode } from "react";

interface SessionGroupProps {
  label: string;
  children: ReactNode;
}

export function SessionGroup({ label, children }: SessionGroupProps) {
  return (
    <section className="flex flex-col gap-0.5">
      <header className="flex h-5 items-center px-2.5">
        <span className="font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
          {label}
        </span>
      </header>
      <div className="flex flex-col">{children}</div>
    </section>
  );
}
