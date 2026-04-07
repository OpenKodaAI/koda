import { redirect } from "next/navigation";
import { ControlPlaneUnavailable } from "@/components/control-plane/control-plane-unavailable";
import { CatalogLayout } from "@/components/control-plane/catalog/catalog-layout";
import {
  ControlPlaneRequestError,
  getControlPlaneBots,
  getControlPlaneCoreProviders,
  getGeneralSystemSettings,
  getControlPlaneWorkspaces,
} from "@/lib/control-plane";
import {
  buildControlPlaneSetupHref,
  resolveControlPlaneDashboardAccess,
} from "@/lib/control-plane-dashboard-access";

export default async function ControlPlanePage() {
  const access = await resolveControlPlaneDashboardAccess();

  if (access.status === "setup_required") {
    return redirect(buildControlPlaneSetupHref());
  }

  if (access.status === "unavailable") {
    return <ControlPlaneUnavailable />;
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
      return redirect(buildControlPlaneSetupHref());
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
