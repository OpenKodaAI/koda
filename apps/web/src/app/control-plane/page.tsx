import { cookies } from "next/headers";
import { ControlPlaneUnavailable } from "@/components/control-plane/control-plane-unavailable";
import { CatalogLayout } from "@/components/control-plane/catalog/catalog-layout";
import {
  getControlPlaneBots,
  getControlPlaneCoreProviders,
  getControlPlaneWorkspaces,
} from "@/lib/control-plane";
import { LOCALE_COOKIE_KEY, translateForLanguage } from "@/lib/i18n";

export default async function ControlPlanePage() {
  const cookieStore = await cookies();
  const language = cookieStore.get(LOCALE_COOKIE_KEY)?.value;
  let payload:
    | {
        bots: Awaited<ReturnType<typeof getControlPlaneBots>>;
        coreProviders: Awaited<ReturnType<typeof getControlPlaneCoreProviders>>;
        workspaces: Awaited<ReturnType<typeof getControlPlaneWorkspaces>>;
      }
    | null = null;

  try {
    const [bots, coreProviders, workspaces] = await Promise.all([
      getControlPlaneBots(),
      getControlPlaneCoreProviders(),
      getControlPlaneWorkspaces(),
    ]);

    payload = { bots, coreProviders, workspaces };
  } catch (error) {
    const description =
      error instanceof Error
        ? error.message
        : translateForLanguage(language, "controlPlane.unavailable.pageTitle", {
            defaultValue: "Could not load the bot list.",
          });
    return <ControlPlaneUnavailable description={description} />;
  }

  if (!payload) {
    return (
      <ControlPlaneUnavailable
        description={translateForLanguage(language, "controlPlane.unavailable.pageTitle", {
          defaultValue: "Could not load the bot list.",
        })}
      />
    );
  }

  return (
    <CatalogLayout
      bots={payload.bots}
      coreProviders={payload.coreProviders}
      workspaces={payload.workspaces}
    />
  );
}
