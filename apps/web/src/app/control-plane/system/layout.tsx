import { cookies } from "next/headers";
import { ControlPlaneUnavailable } from "@/components/control-plane/control-plane-unavailable";
import { SettingsSidebar } from "@/components/control-plane/system/settings-sidebar";
import { UnsavedChangesGuard } from "@/components/control-plane/system/unsaved-changes-guard";
import { SettingsModalHost } from "@/components/control-plane/system/settings-modal-host";
import { SystemSettingsProvider } from "@/hooks/use-system-settings";
import { ToastProvider } from "@/hooks/use-toast";
import { getGeneralSystemSettings } from "@/lib/control-plane";
import { LOCALE_COOKIE_KEY, translateForLanguage } from "@/lib/i18n";

export default async function SystemSettingsLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies();
  const language = cookieStore.get(LOCALE_COOKIE_KEY)?.value;
  let settings: Awaited<ReturnType<typeof getGeneralSystemSettings>> | null = null;

  try {
    settings = await getGeneralSystemSettings();
  } catch (error) {
    const description =
      error instanceof Error
        ? error.message
        : translateForLanguage(language, "controlPlane.system.loadDescription", {
            defaultValue: "Could not load global system settings.",
          });
    return (
      <ControlPlaneUnavailable
        title={translateForLanguage(language, "controlPlane.system.loadTitle", {
          defaultValue: "Failed to load system settings",
        })}
        description={description}
      />
    );
  }

  if (!settings) {
    return (
      <ControlPlaneUnavailable
        title={translateForLanguage(language, "controlPlane.system.loadTitle", {
          defaultValue: "Failed to load system settings",
        })}
        description={translateForLanguage(language, "controlPlane.system.loadDescription", {
          defaultValue: "Could not load global system settings.",
        })}
      />
    );
  }

  return (
    <ToastProvider>
      <SystemSettingsProvider settings={settings}>
        <div className="flex h-full min-h-0 flex-1 overflow-hidden">
          <SettingsSidebar />
          <main className="flex flex-1 min-h-0 flex-col overflow-hidden">{children}</main>
        </div>
        <UnsavedChangesGuard />
        <SettingsModalHost />
      </SystemSettingsProvider>
    </ToastProvider>
  );
}
