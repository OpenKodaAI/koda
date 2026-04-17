import { redirect } from "next/navigation";
import { SetupScreen } from "@/components/setup/setup-screen";
import {
  ControlPlaneRequestError,
  getControlPlaneAuthStatus,
  getControlPlaneOnboardingStatus,
} from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function SetupPage() {
  let authStatus;
  let onboardingStatus;

  try {
    [authStatus, onboardingStatus] = await Promise.all([
      getControlPlaneAuthStatus(),
      getControlPlaneOnboardingStatus(),
    ]);
  } catch (error) {
    // If the control plane itself is unreachable we still render the setup shell —
    // the user can at least see the first step (setup code) and try to exchange one.
    if (error instanceof ControlPlaneRequestError && error.status === 401) {
      return <SetupScreen authStatus={null} onboardingStatus={null} />;
    }
    return <SetupScreen authStatus={null} onboardingStatus={null} />;
  }

  // Already fully onboarded → leave the setup route for the real app.
  if (authStatus.authenticated && onboardingStatus.steps.onboarding_complete) {
    redirect("/");
  }

  return <SetupScreen authStatus={authStatus} onboardingStatus={onboardingStatus} />;
}
