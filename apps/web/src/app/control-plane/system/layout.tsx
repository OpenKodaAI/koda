import { redirect } from "next/navigation";
import { ControlPlaneUnavailable } from "@/components/control-plane/control-plane-unavailable";
import { SettingsSidebar } from "@/components/control-plane/system/settings-sidebar";
import { UnsavedChangesGuard } from "@/components/control-plane/system/unsaved-changes-guard";
import { SettingsModalHost } from "@/components/control-plane/system/settings-modal-host";
import { ToastNotification } from "@/components/ui/toast-notification";
import { SystemSettingsProvider } from "@/hooks/use-system-settings";
import { ToastProvider } from "@/hooks/use-toast";
import {
  ControlPlaneRequestError,
  getControlPlaneCoreIntegrations,
  getGeneralSystemSettings,
} from "@/lib/control-plane";
import {
  buildControlPlaneSetupHref,
  resolveControlPlaneDashboardAccess,
} from "@/lib/control-plane-dashboard-access";

export default async function SystemSettingsLayout({ children }: { children: React.ReactNode }) {
  const access = await resolveControlPlaneDashboardAccess();

  if (access.status === "setup_required") {
    return redirect(buildControlPlaneSetupHref("/control-plane/system"));
  }

  if (access.status === "unavailable") {
    return <ControlPlaneUnavailable />;
  }

  let settings: Awaited<ReturnType<typeof getGeneralSystemSettings>> | null = null;
  let coreIntegrations: Awaited<ReturnType<typeof getControlPlaneCoreIntegrations>> | null = null;

  try {
    [settings, coreIntegrations] = await Promise.all([
      getGeneralSystemSettings(),
      getControlPlaneCoreIntegrations(),
    ]);
  } catch (error) {
    if (error instanceof ControlPlaneRequestError && error.status === 401) {
      return redirect(buildControlPlaneSetupHref("/control-plane/system"));
    }
    return <ControlPlaneUnavailable />;
  }

  if (!settings || !coreIntegrations) {
    return <ControlPlaneUnavailable />;
  }

  return (
    <ToastProvider>
      <SystemSettingsProvider settings={settings} coreIntegrations={coreIntegrations}>
        <div className="flex h-full min-h-0 flex-1 overflow-hidden">
          <SettingsSidebar />
          <main className="flex flex-1 min-h-0 flex-col overflow-hidden">{children}</main>
        </div>
        <UnsavedChangesGuard />
        <SettingsModalHost />
        <ToastNotification />
      </SystemSettingsProvider>
    </ToastProvider>
  );
}
