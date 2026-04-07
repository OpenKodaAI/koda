"use client";

import { KodaMark } from "@/components/layout/koda-mark";

export function ControlPlaneUnavailable() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="glass-card w-full max-w-lg p-8">
        <div className="flex flex-col items-center gap-6 text-center">
          <KodaMark className="h-8 w-auto" />
          <div className="space-y-2">
            <h2 className="text-lg font-medium text-[var(--text-primary)]">
              Control plane is temporarily unavailable
            </h2>
            <p className="text-sm text-[var(--text-quaternary)]">
              Koda could not reach the control-plane backend or its setup status. Check the
              dashboard, health endpoint, and doctor output, then try the onboarding route again.
            </p>
          </div>
          <a
            href="/control-plane/setup"
            className="button-primary-bottom inline-flex rounded-[0.65rem] px-4 py-3 text-sm font-medium"
          >
            Open dashboard setup
          </a>
        </div>
      </div>
    </div>
  );
}
