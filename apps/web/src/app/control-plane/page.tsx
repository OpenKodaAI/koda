import { redirect } from "next/navigation";
import { CatalogLayout } from "@/components/control-plane/catalog/catalog-layout";
import {
  ControlPlaneRequestError,
  getControlPlaneAgents,
  getControlPlaneWorkspaces,
} from "@/lib/control-plane";

export default async function ControlPlanePage() {
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
