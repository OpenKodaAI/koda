import { redirect } from "next/navigation";
import { CatalogLayout } from "@/components/control-plane/catalog/catalog-layout";
import {
  getControlPlaneAuthStatus,
  ControlPlaneRequestError,
  getControlPlaneAgents,
  getControlPlaneWorkspaces,
} from "@/lib/control-plane";

function redirectToAuth(hasOwner: boolean): never {
  redirect(hasOwner ? "/login" : "/setup");
}

export default async function ControlPlanePage() {
  let authStatus;

  try {
    authStatus = await getControlPlaneAuthStatus();
  } catch (error) {
    if (error instanceof ControlPlaneRequestError && error.status === 401) {
      redirect("/login");
    }
    throw error;
  }

  if (!authStatus.authenticated) {
    redirectToAuth(authStatus.has_owner);
  }

  let payload: {
    agents: Awaited<ReturnType<typeof getControlPlaneAgents>>;
    workspaces: Awaited<ReturnType<typeof getControlPlaneWorkspaces>>;
  };

  try {
    const [agents, workspaces] = await Promise.all([
      getControlPlaneAgents(),
      getControlPlaneWorkspaces(),
    ]);

    payload = { agents, workspaces };
  } catch (error) {
    if (error instanceof ControlPlaneRequestError && error.status === 401) {
      redirect("/login");
    }
    throw error;
  }

  return (
    <CatalogLayout agents={payload.agents} workspaces={payload.workspaces} />
  );
}
