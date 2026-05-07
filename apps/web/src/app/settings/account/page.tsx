import { AccountIdentityPanel } from "@/components/account/account-identity-panel";
import { SecuritySettingsCard } from "@/components/account/security-settings-card";
import { requireAuthenticatedSession } from "@/lib/auth-guard";

export const dynamic = "force-dynamic";

export default async function AccountSettingsPage() {
  await requireAuthenticatedSession();
  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-col gap-4 px-4 py-6 sm:px-6 lg:px-8">
      <AccountIdentityPanel />
      <SecuritySettingsCard />
    </div>
  );
}
