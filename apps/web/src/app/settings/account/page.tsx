import { AccountIdentityPanel } from "@/components/account/account-identity-panel";
import { SecuritySettingsCard } from "@/components/account/security-settings-card";
import { requireAuthenticatedSession } from "@/lib/auth-guard";

export const dynamic = "force-dynamic";

export default async function AccountSettingsPage() {
  await requireAuthenticatedSession();
  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-4 px-4 py-5 sm:px-6 lg:px-8">
      <header className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="m-0 text-[1.25rem] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
            Account
          </h1>
          <p className="m-0 mt-1 max-w-2xl text-[0.8125rem] leading-5 text-[var(--text-tertiary)]">
            Synced profile, password and recovery controls.
          </p>
        </div>
      </header>
      <AccountIdentityPanel />
      <SecuritySettingsCard />
    </div>
  );
}
