"use client";

import { translate } from "@/lib/i18n";
import {
  AlertTriangle,
  CheckCircle2,
  ShieldAlert,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import type {
  SandboxDoctorCheck,
  SandboxDoctorResult,
  SandboxDoctorStatus,
} from "@/lib/contracts/sandbox-doctor";
import { cn, formatDateTime } from "@/lib/utils";

type SandboxDoctorPanelProps = {
  result: SandboxDoctorResult | null;
  className?: string;
};

function statusTone(status: SandboxDoctorStatus | string | null | undefined): StatusDotTone {
  if (status === "passed") return "success";
  if (status === "warning" || status === "degraded") return "warning";
  if (status === "failed") return "danger";
  return "neutral";
}

function checkIcon(check: SandboxDoctorCheck) {
  if (check.status === "passed") return CheckCircle2;
  if (check.severity === "danger") return ShieldAlert;
  if (check.severity === "warning") return AlertTriangle;
  return ShieldCheck;
}

function PolicyDatum({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {label}
      </dt>
      <dd className="m-0 mt-1 truncate text-[0.8125rem] text-[var(--text-primary)]">{value}</dd>
    </div>
  );
}

export function SandboxDoctorPanel({ result, className }: SandboxDoctorPanelProps) {
  if (!result) {
    return (
      <section
        className={cn(
          "rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-4",
          className,
        )}
      >
        <div className="flex items-center gap-2">
          <StatusDot tone="neutral" />
          <h3 className="m-0 text-[0.875rem] font-medium text-[var(--text-primary)]">
            {translate("generated.runtime.sandbox_doctor_unavailable_894149c1")}</h3>
        </div>
        <div className="flex min-h-[118px] flex-col items-center justify-center gap-2 py-5 text-center">
          <Stethoscope className="h-4 w-4 text-[var(--text-quaternary)]" strokeWidth={1.75} />
          <p className="m-0 max-w-md text-[0.75rem] leading-5 text-[var(--text-tertiary)]">
            {translate("generated.runtime.no_sandbox_doctor_v1_result_is_published_for_524cf81a")}</p>
        </div>
      </section>
    );
  }

  const policy = result.effective_policy;
  const tone = statusTone(result.status);

  return (
    <section
      className={cn(
        "rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-4",
        className,
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="m-0 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
            {translate("generated.runtime.sandbox_doctor_v1_f69ac165")}</p>
          <h3 className="m-0 mt-1 flex items-center gap-2 text-[0.875rem] font-medium text-[var(--text-primary)]">
            <StatusDot tone={tone} />
            {translate("generated.runtime.sandbox_doctor_cba777ca")} {result.status}
          </h3>
          {result.generated_at ? (
            <p className="m-0 mt-1 text-[0.72rem] text-[var(--text-tertiary)]">
              {formatDateTime(result.generated_at)}
            </p>
          ) : null}
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-[var(--radius-chip)] border border-[var(--border-subtle)] px-2 py-1 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-tertiary)]">
          <StatusDot tone={tone} />
          {result.checks.length} {translate("generated.runtime.checks_0912fac7")}</span>
      </div>

      {policy ? (
        <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <PolicyDatum label={translate("generated.runtime.network_330b9529")} value={policy.network_mode ?? "—"} />
          <PolicyDatum label={translate("generated.runtime.shell_09982404")} value={policy.shell_mode ?? "—"} />
          <PolicyDatum label={translate("generated.runtime.browser_c68dcf82")} value={policy.browser_mode ?? "—"} />
          <PolicyDatum label="TTL" value={policy.ttl_seconds ? `${policy.ttl_seconds}s` : "—"} />
        </dl>
      ) : null}

      {result.degraded_components.length > 0 ? (
        <div className="mt-3 rounded-[var(--radius-panel-sm)] border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] px-3 py-2 text-[0.75rem] text-[var(--tone-warning-text)]">
          {translate("generated.runtime.degraded_0e6a3544")} {result.degraded_components.join(", ")}
        </div>
      ) : null}

      {result.checks.length > 0 ? (
        <div className="mt-4 divide-y divide-[var(--divider-hair)]">
          {result.checks.map((check) => {
            const Icon = checkIcon(check);
            return (
              <article key={check.id} className="grid grid-cols-[auto_1fr_auto] items-start gap-3 py-2.5">
                <Icon className="mt-0.5 h-4 w-4 text-[var(--text-tertiary)]" strokeWidth={1.75} />
                <div className="min-w-0">
                  <p className="m-0 truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
                    {check.title}
                  </p>
                  <p className="m-0 mt-0.5 text-[0.72rem] leading-5 text-[var(--text-tertiary)]">
                    {check.message ?? check.scope}
                  </p>
                  {check.user_action ? (
                    <p className="m-0 mt-1 text-[0.72rem] leading-5 text-[var(--text-secondary)]">
                      {check.user_action}
                    </p>
                  ) : null}
                </div>
                <span className="inline-flex items-center gap-1.5 font-mono text-[0.6875rem] text-[var(--text-tertiary)]">
                  <StatusDot tone={statusTone(check.status)} />
                  {check.status}
                </span>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
