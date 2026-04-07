import { CheckCircle2, KeyRound, LogIn, Rocket } from "lucide-react";
import { KodaMark } from "@/components/layout/koda-mark";

const ONBOARDING_STEPS = [
  {
    title: "Get a setup code",
    description: "Run the installer or reissue a short-lived code from the CLI.",
    icon: KeyRound,
  },
  {
    title: "Create owner account",
    description: "Bootstrap the first local operator with a password.",
    icon: Rocket,
  },
  {
    title: "Sign in",
    description: "Open the HTTP-only operator session for the dashboard.",
    icon: LogIn,
  },
  {
    title: "Finish platform setup",
    description: "Configure access, verify the default provider, and optionally add the first agent.",
    icon: CheckCircle2,
  },
] as const;

export function ControlPlaneOnboardingShell({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(45,212,191,0.18),transparent_28%),radial-gradient(circle_at_bottom_right,rgba(59,130,246,0.16),transparent_34%),var(--surface-base)]">
      <div className="mx-auto flex min-h-screen w-full max-w-[1720px] flex-col gap-6 px-4 py-5 sm:px-6 lg:px-8 lg:py-8">
        <div className="grid flex-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
          <aside className="glass-card flex h-fit flex-col gap-6 rounded-[32px] px-6 py-7 xl:sticky xl:top-8">
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)]">
                <KodaMark className="h-7 w-7" />
              </span>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--text-secondary)]">
                  Koda onboarding
                </p>
                <h1 className="text-lg font-semibold tracking-[-0.05em] text-[var(--text-primary)]">
                  Secure first run
                </h1>
              </div>
            </div>

            <div className="space-y-3">
              <p className="text-[0.72rem] font-semibold uppercase tracking-[0.22em] text-[var(--text-secondary)]">
                Canonical flow
              </p>
              <p className="text-[2rem] font-semibold leading-tight tracking-[-0.07em] text-[var(--text-primary)]">
                First-run setup now lives in its own dedicated dashboard path.
              </p>
              <p className="max-w-sm text-sm leading-6 text-[var(--text-secondary)]">
                Most installs finish in two or three minutes. Complete auth and platform bootstrap
                here, then Koda opens the full control plane and agent catalog.
              </p>
            </div>

            <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-4">
              <div className="space-y-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-secondary)]">
                    Install commands
                  </p>
                  <p className="mt-1 text-sm text-[var(--text-secondary)]">
                    Use the same setup route for local installs, VPS, or headless hosts.
                  </p>
                </div>
                <div className="space-y-2 text-sm text-[var(--text-primary)]">
                  <div className="rounded-2xl border border-[var(--border-subtle)] bg-background px-3 py-2 font-mono">
                    koda install
                  </div>
                  <div className="rounded-2xl border border-[var(--border-subtle)] bg-background px-3 py-2 font-mono">
                    koda install --headless
                  </div>
                  <div className="rounded-2xl border border-[var(--border-subtle)] bg-background px-3 py-2 font-mono">
                    koda auth issue-code
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-3">
              {ONBOARDING_STEPS.map(({ title, description, icon: Icon }, index) => (
                <div
                  key={title}
                  className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--surface-panel-soft)] px-4 py-4"
                >
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-[var(--border-subtle)] bg-background text-[var(--text-primary)]">
                      <Icon className="h-4 w-4" />
                    </span>
                    <div className="space-y-1">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-secondary)]">
                        Step {index + 1}
                      </p>
                      <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
                      <p className="text-sm leading-6 text-[var(--text-secondary)]">{description}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="rounded-[24px] border border-emerald-400/25 bg-emerald-400/10 px-4 py-4">
              <div className="flex items-start gap-3">
                <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-200" />
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-emerald-100">Catalog unlocks after bootstrap</p>
                  <p className="text-sm leading-6 text-emerald-50/90">
                    `/control-plane/setup` is the onboarding route. `/control-plane` stays reserved
                    for the real control-plane home once setup is complete.
                  </p>
                </div>
              </div>
            </div>
          </aside>

          <div className="min-w-0">{children}</div>
        </div>
      </div>
    </div>
  );
}
