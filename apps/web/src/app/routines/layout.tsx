import type { ReactNode } from "react";
import { RoutinesContextProvider } from "@/components/routines/routines-context";
import { RoutinesShell } from "@/components/routines/routines-shell";
import { ToastNotification } from "@/components/ui/toast-notification";
import { ToastProvider } from "@/hooks/use-toast";
import { ControlPlaneRequestError, getGeneralSystemSettings } from "@/lib/control-plane";

export default async function RoutinesLayout({ children }: { children: ReactNode }) {
  let defaultTimezone = "UTC";
  try {
    const settings = await getGeneralSystemSettings();
    defaultTimezone = settings.values.account.scheduler_default_timezone || "UTC";
  } catch (error) {
    // Fall back to UTC; the editor still lets the user pick another zone.
    if (!(error instanceof ControlPlaneRequestError)) {
      throw error;
    }
  }

  return (
    <ToastProvider>
      <RoutinesContextProvider defaultTimezone={defaultTimezone}>
        <RoutinesShell>{children}</RoutinesShell>
      </RoutinesContextProvider>
      <ToastNotification />
    </ToastProvider>
  );
}
