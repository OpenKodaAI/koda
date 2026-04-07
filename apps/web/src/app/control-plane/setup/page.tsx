import { redirect } from "next/navigation";
import { ControlPlaneOnboardingShell } from "@/components/control-plane/control-plane-onboarding-shell";
import { ControlPlaneSetup } from "@/components/control-plane/control-plane-setup";
import { ControlPlaneUnavailable } from "@/components/control-plane/control-plane-unavailable";
import {
  resolveControlPlaneDashboardAccess,
  sanitizeControlPlaneNextTarget,
} from "@/lib/control-plane-dashboard-access";

export default async function ControlPlaneSetupPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  const nextTarget = sanitizeControlPlaneNextTarget(next);
  const access = await resolveControlPlaneDashboardAccess();

  if (access.status === "ready") {
    return redirect(nextTarget ?? "/control-plane");
  }

  if (access.status === "unavailable") {
    return <ControlPlaneUnavailable />;
  }

  return (
    <ControlPlaneOnboardingShell>
      <ControlPlaneSetup
        initialStatus={access.onboardingStatus}
        authStatus={access.authStatus}
        nextTarget={nextTarget}
      />
    </ControlPlaneOnboardingShell>
  );
}
