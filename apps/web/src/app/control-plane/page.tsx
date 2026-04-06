import { ControlPlaneUnavailable } from "@/components/control-plane/control-plane-unavailable";
import { ControlPlaneSetup } from "@/components/control-plane/control-plane-setup";
import { CatalogLayout } from "@/components/control-plane/catalog/catalog-layout";
import {
  getControlPlaneAuthStatus,
  ControlPlaneRequestError,
  getControlPlaneBots,
  getControlPlaneCoreProviders,
  getControlPlaneOnboardingStatus,
  getGeneralSystemSettings,
  getControlPlaneWorkspaces,
} from "@/lib/control-plane";

export default async function ControlPlanePage() {
  let authStatus;
  let onboardingStatus;

  try {
    [authStatus, onboardingStatus] = await Promise.all([
      getControlPlaneAuthStatus(),
      getControlPlaneOnboardingStatus(),
    ]);
  } catch (error) {
    if (error instanceof ControlPlaneRequestError && error.status === 401) {
      return <ControlPlaneUnavailable />;
    }
    return <ControlPlaneUnavailable />;
  }

  if (!authStatus.authenticated || !onboardingStatus.steps.onboarding_complete) {
    return <ControlPlaneSetup initialStatus={onboardingStatus} authStatus={authStatus} />;
  }

  let payload:
    | {
        bots: Awaited<ReturnType<typeof getControlPlaneBots>>;
        coreProviders: Awaited<ReturnType<typeof getControlPlaneCoreProviders>>;
        workspaces: Awaited<ReturnType<typeof getControlPlaneWorkspaces>>;
        generalSettings: Awaited<ReturnType<typeof getGeneralSystemSettings>> | null;
      }
    | null = null;

  try {
    const [bots, coreProviders, workspaces, generalSettings] = await Promise.all([
      getControlPlaneBots(),
      getControlPlaneCoreProviders(),
      getControlPlaneWorkspaces(),
      getGeneralSystemSettings().catch(() => null),
    ]);

    payload = { bots, coreProviders, workspaces, generalSettings };
  } catch (error) {
    if (error instanceof ControlPlaneRequestError && error.status === 401) {
      return <ControlPlaneUnavailable />;
    }
    return <ControlPlaneUnavailable />;
  }

  if (!payload) {
    return <ControlPlaneUnavailable />;
  }

  return (
    <CatalogLayout
      bots={payload.bots}
      coreProviders={payload.coreProviders}
      workspaces={payload.workspaces}
      generalSettings={payload.generalSettings}
    />
  );
}
