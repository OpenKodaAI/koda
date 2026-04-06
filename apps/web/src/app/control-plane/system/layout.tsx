import { ControlPlaneUnavailable } from "@/components/control-plane/control-plane-unavailable";
import { SettingsSidebar } from "@/components/control-plane/system/settings-sidebar";
import { UnsavedChangesGuard } from "@/components/control-plane/system/unsaved-changes-guard";
import { SettingsModalHost } from "@/components/control-plane/system/settings-modal-host";
import { ToastNotification } from "@/components/ui/toast-notification";
import { SystemSettingsProvider } from "@/hooks/use-system-settings";
import { ToastProvider } from "@/hooks/use-toast";
import {
  getControlPlaneCoreIntegrations,
  getGeneralSystemSettings,
} from "@/lib/control-plane";

export default async function SystemSettingsLayout({ children }: { children: React.ReactNode }) {
  let settings: Awaited<ReturnType<typeof getGeneralSystemSettings>> | null = null;
  let coreIntegrations: Awaited<ReturnType<typeof getControlPlaneCoreIntegrations>> | null = null;

  try {
    [settings, coreIntegrations] = await Promise.all([
      getGeneralSystemSettings(),
      getControlPlaneCoreIntegrations(),
    ]);
  } catch {
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
